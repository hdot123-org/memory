#!/usr/bin/env bash
# Repo delivery consistency health check
# Usage:
#   bash scripts/repo_health_check.sh --ci     # CI gate mode (local only, no network)
#   bash scripts/repo_health_check.sh --full   # Full mode (includes gh CLI remote checks)
set -euo pipefail

# ── Mode parsing ──────────────────────────────────────────────────────────────
MODE="ci"
case "${1:-}" in
  --ci)   MODE="ci" ;;
  --full) MODE="full" ;;
  "")     MODE="ci" ;;
  *)      echo "Usage: $0 [--ci|--full]"; exit 2 ;;
esac

# ── Resolve repo root ────────────────────────────────────────────────────────
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ── Counters ──────────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0
RESULTS=()

record() {
  local tag="$1" name="$2" status="$3" detail="${4:-}"
  local pad
  pad=$(printf '%0.s.' {1..30})
  if [[ -n "$detail" ]]; then
    RESULTS+=("[${tag}] ${name} ${pad} ${status} (${detail})")
  else
    RESULTS+=("[${tag}] ${name} ${pad} ${status}")
  fi
  if [[ "$status" == "PASS" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

# ── Extract version from pyproject.toml using python tomllib ──────────────────
get_pyproject_version() {
  python3 -c "
import sys
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print(data['project']['version'])
"
}

# ── CHECK 1: Version consistency across pyproject / constants / README ───────
PYPROJECT_VERSION=""
check_version_consistency() {
  local pyproject_ver constants_ver readme_ver

  pyproject_ver="$(get_pyproject_version)"
  PYPROJECT_VERSION="$pyproject_ver"

  # constants.py: CURRENT_MEMORY_VERSION = "X.Y.Z"
  constants_ver="$(python3 -c "
import re, sys
found = False
for path in ['memory_core/constants.py', 'constants.py']:
    try:
        with open(path) as f:
            for line in f:
                m = re.match(r'^CURRENT_MEMORY_VERSION\s*=\s*[\"\\']([^\"\\' ]+)[\"\\']', line)
                if m:
                    print(m.group(1))
                    found = True
                    break
        if found:
            break
    except FileNotFoundError:
        continue
if not found:
    print('NOT_FOUND')
")"

  # README.md: "- Current documented release: vX.Y.Z"
  readme_ver="$(python3 -c "
import re
ver = 'NOT_FOUND'
try:
    with open('README.md') as f:
        for line in f:
            m = re.search(r'Current documented release:\s*v?(\d+\.\d+\.\d+)', line)
            if m:
                ver = m.group(1)
                break
except FileNotFoundError:
    pass
print(ver)
")"

  if [[ "$pyproject_ver" == "$constants_ver" && "$pyproject_ver" == "$readme_ver" ]]; then
    record "CHECK" "version-consistency" "PASS" "v${pyproject_ver}"
  else
    record "CHECK" "version-consistency" "FAIL" "pyproject=${pyproject_ver} constants=${constants_ver} readme=${readme_ver}"
  fi
}

# ── CHECK 2: README install command version references ───────────────────────
check_readme_install_versions() {
  local expected_ver="$PYPROJECT_VERSION"
  if [[ -z "$expected_ver" ]]; then
    record "CHECK" "readme-install-versions" "FAIL" "no expected version"
    return
  fi

  # Find all @vX.Y.Z references in README (install commands)
  local mismatches=""
  local found_refs
  found_refs="$(python3 -c "
import re
refs = set()
try:
    with open('README.md') as f:
        content = f.read()
    # Match @vX.Y.Z patterns (install commands)
    for m in re.finditer(r'@v(\d+\.\d+\.\d+)', content):
        refs.add(m.group(1))
except FileNotFoundError:
    pass
for r in sorted(refs):
    print(r)
")"

  local all_match=true
  while IFS= read -r ver; do
    [[ -z "$ver" ]] && continue
    if [[ "$ver" != "$expected_ver" ]]; then
      mismatches="${mismatches}${ver} "
      all_match=false
    fi
  done <<< "$found_refs"

  if $all_match; then
    record "CHECK" "readme-install-versions" "PASS"
  else
    record "CHECK" "readme-install-versions" "FAIL" "mismatched: ${mismatches}"
  fi
}

# ── CHECK 3: GitLab residue in tracked files ─────────────────────────────────
check_gitlab_residue() {
  # Search patterns as specified in requirements
  local patterns="GitLab-first|sync-to-github|\.gitlab-ci\.yml|one-way mirror|push gitlab|merge request"
  
  # Search tracked files, exclude:
  # - CHANGELOG.md (historical records allowed)
  # - Python source files (may legitimately reference .gitlab-ci.yml for CI detection)
  # - Shell scripts (may contain patterns in conditionals or as tool definitions)
  # - Markdown docs in memory/docs/ (contain legitimate historical context about GitLab workflows)
  # - Markdown docs in docs/specs/ and docs/architecture/ (protocol specs and architecture docs
  #   migrated from memory/docs/, contain legitimate CI workflow descriptions referencing GitLab)
  #
  # Use grep instead of rg for portability: rg skips staged-but-uncommitted files
  # by default, which breaks tests that git add without committing.
  local file_list matches
  file_list="$(git ls-files | grep -v 'CHANGELOG\.md$' | grep -v '\.py$' | grep -v '\.sh$' | grep -v '^memory/docs/' | grep -v '^docs/specs/' | grep -v '^docs/architecture/' || true)"
  
  matches=""
  if [[ -n "$file_list" ]]; then
    matches="$(echo "$file_list" | tr '\n' '\0' | xargs -0 grep -n -E "${patterns}" 2>/dev/null | grep -v ':[0-9]*:\s*#' || true)"
  fi
  
  local count=0
  if [[ -n "$matches" ]]; then
    count="$(echo "$matches" | wc -l | tr -d ' ')"
  fi

  if [[ "$count" -eq 0 ]]; then
    record "CHECK" "gitlab-residue" "PASS" "0 matches"
  else
    record "CHECK" "gitlab-residue" "FAIL" "${count} matches"
  fi
}

# ── CHECK 4 (FULL only): Tags/releases alignment ─────────────────────────────
check_tags_releases() {
  # Use gh release list to find the latest published release (not git describe,
  # which only finds ancestor tags and misses releases merged via squash/PR)
  local latest_tag
  latest_tag="$(gh release list --limit 50 2>/dev/null | grep -v 'Draft' | grep -v 'Pre-release' | head -1 | awk '{print $1}' || echo "")"

  # Fallback: also try including pre-releases but excluding drafts
  if [[ -z "$latest_tag" ]]; then
    latest_tag="$(gh release list --limit 50 2>/dev/null | grep -v 'Draft' | head -1 | awk '{print $1}' || echo "")"
  fi

  if [[ -z "$latest_tag" ]]; then
    record "FULL" "tags-releases-align" "FAIL" "no published releases found"
    return
  fi

  # Check if latest tag has a published release (not draft)
  local release_info
  release_info="$(gh release view "$latest_tag" --json isDraft,isPrerelease,publishedAt 2>/dev/null || echo "")"

  if [[ -z "$release_info" ]]; then
    record "FULL" "tags-releases-align" "FAIL" "${latest_tag} has no release"
    return
  fi

  local is_draft
  is_draft="$(echo "$release_info" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('isDraft', False))")"

  if [[ "$is_draft" == "True" ]]; then
    record "FULL" "tags-releases-align" "FAIL" "${latest_tag} is draft"
    return
  fi

  # Check for orphan drafts (drafts without matching tags)
  local draft_count
  draft_count="$(gh release list --limit 50 2>/dev/null | grep -c 'Draft' || true)"

  if [[ "$draft_count" -gt 0 ]]; then
    record "FULL" "tags-releases-align" "FAIL" "${draft_count} orphan draft(s)"
    return
  fi

  record "FULL" "tags-releases-align" "PASS" "${latest_tag} published"
}

# ── CHECK 5 (FULL only): Release workflow health ──────────────────────────────
check_release_workflow() {
  # Use gh release list to find the latest published release (not git describe)
  local latest_tag
  latest_tag="$(gh release list --limit 50 2>/dev/null | grep -v 'Draft' | grep -v 'Pre-release' | head -1 | awk '{print $1}' || echo "")"

  # Fallback: also try including pre-releases but excluding drafts
  if [[ -z "$latest_tag" ]]; then
    latest_tag="$(gh release list --limit 50 2>/dev/null | grep -v 'Draft' | head -1 | awk '{print $1}' || echo "")"
  fi

  if [[ -z "$latest_tag" ]]; then
    record "FULL" "release-workflow-health" "FAIL" "no published releases"
    return
  fi

  local run_info
  run_info="$(gh run list --workflow=release-and-dispatch.yml --limit 5 --json status,conclusion,headBranch 2>/dev/null || echo "")"

  if [[ -z "$run_info" || "$run_info" == "[]" ]]; then
    record "FULL" "release-workflow-health" "FAIL" "no runs found"
    return
  fi

  # Check if latest run is success
  # Priority: main branch (workflow_dispatch re-runs) > tag branch (tag push triggers)
  local latest_conclusion
  latest_conclusion="$(echo "$run_info" | python3 -c "
import sys, json
runs = json.load(sys.stdin)
# First check main branch runs (workflow_dispatch re-triggers)
main_runs = [r for r in runs if r.get('headBranch','') == 'main']
if main_runs:
    print(main_runs[0].get('conclusion','unknown'))
    sys.exit(0)
# Then check tag-specific runs
for r in runs:
    if r.get('headBranch','') == '${latest_tag}':
        print(r.get('conclusion','unknown'))
        sys.exit(0)
# Fallback to most recent run
if runs:
    print(runs[0].get('conclusion','unknown'))
else:
    print('none')
")"

  if [[ "$latest_conclusion" == "success" ]]; then
    record "FULL" "release-workflow-health" "PASS"
  else
    record "FULL" "release-workflow-health" "FAIL" "conclusion=${latest_conclusion}"
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo "=== Repo Health Check (${MODE} mode) ==="
echo ""

# CHECK 1: Version consistency
check_version_consistency

# CHECK 2: README install versions
check_readme_install_versions

# CHECK 3: GitLab residue
check_gitlab_residue

# --full mode: additional remote checks
if [[ "$MODE" == "full" ]]; then
  if [[ "$FAIL_COUNT" -eq 0 ]]; then
    check_tags_releases
    check_release_workflow
  else
    echo ""
    echo "Skipping --full checks because --ci checks failed."
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
for r in "${RESULTS[@]}"; do
  echo "  $r"
done
echo ""

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "Summary: ${PASS_COUNT}/${TOTAL} PASS"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi

exit 0
