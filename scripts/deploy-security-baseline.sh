#!/usr/bin/env bash
# Deploy CI security baseline to a target repository
# Usage: ./deploy-security-baseline.sh /path/to/target/repo
# or:    ./deploy-security-baseline.sh --repo owner/repo-name

set -euo pipefail

# Resolve script directory (memory-core repo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source repo template paths
TEMPLATE_DIR="$REPO_ROOT/.github/workflows"
SCRIPT_SRC="$REPO_ROOT/scripts"

# Target repo
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 /path/to/target/repo  OR  $0 --repo owner/repo-name"
  exit 1
fi

# Handle --repo flag (clone or use gh)
if [[ "$TARGET" == "--repo" ]]; then
  REPO_NAME="${2:-}"
  if [[ -z "$REPO_NAME" ]]; then
    echo "Error: --repo requires a repository name (owner/repo)"
    exit 1
  fi
  # Clone to temp, deploy, push
  TMPDIR=$(mktemp -d)
  gh repo clone "$REPO_NAME" "$TMPDIR" 2>/dev/null || {
    echo "Error: Cannot clone $REPO_NAME"
    rm -rf "$TMPDIR"
    exit 1
  }
  TARGET="$TMPDIR"
  CLEANUP=true
fi

echo "=== Deploying security baseline to: $TARGET ==="

# 1. Copy droid-review.yml
mkdir -p "$TARGET/.github/workflows"
if [[ ! -f "$TARGET/.github/workflows/droid-review.yml" ]] || [[ "${FORCE:-}" == "1" ]]; then
  cp "$TEMPLATE_DIR/droid-review.yml" "$TARGET/.github/workflows/droid-review.yml"
  echo "  [+] droid-review.yml deployed (pull_request_target + security review)"
else
  echo "  [o] droid-review.yml already exists, skipping (use FORCE=1 to overwrite)"
fi

# 2. Copy auto-merge.yml
if [[ ! -f "$TARGET/.github/workflows/auto-merge.yml" ]] || [[ "${FORCE:-}" == "1" ]]; then
  cp "$TEMPLATE_DIR/auto-merge.yml" "$TARGET/.github/workflows/auto-merge.yml"
  echo "  [+] auto-merge.yml deployed (SHA-pinned)"
else
  echo "  [o] auto-merge.yml already exists, skipping"
fi

# 3. Copy check_droid_review.sh
mkdir -p "$TARGET/scripts"
if [[ ! -f "$TARGET/scripts/check_droid_review.sh" ]] || [[ "${FORCE:-}" == "1" ]]; then
  cp "$SCRIPT_SRC/check_droid_review.sh" "$TARGET/scripts/check_droid_review.sh"
  chmod +x "$TARGET/scripts/check_droid_review.sh"
  echo "  [+] check_droid_review.sh deployed (whitelist: only success passes)"
else
  echo "  [o] check_droid_review.sh already exists, skipping"
fi

# 4. Copy security templates
mkdir -p "$TARGET/docs/templates"
for tmpl in validation-contract-security-template.md features-security-template.md agents-security-directive-template.md; do
  if [[ -f "$REPO_ROOT/docs/templates/$tmpl" ]]; then
    cp "$REPO_ROOT/docs/templates/$tmpl" "$TARGET/docs/templates/$tmpl"
    echo "  [+] docs/templates/$tmpl deployed"
  fi
done

# 5. Set enforce_admins if it's a GitHub repo with gh available
REPO_FULL_NAME=$(cd "$TARGET" && gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null || echo "")
if [[ -n "$REPO_FULL_NAME" ]] && [[ "${SKIP_BRANCH_PROTECTION:-}" != "1" ]]; then
  echo "  [*] Setting enforce_admins=true for $REPO_FULL_NAME..."
  
  # Get current protection rules
  EXISTING=$(gh api "repos/$REPO_FULL_NAME/branches/main/protection" 2>/dev/null || echo "")
  
  if [[ -n "$EXISTING" ]]; then
    # Update existing protection
    gh api "repos/$REPO_FULL_NAME/branches/main/protection" -X PUT \
      --input - << 'PROTECT_EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["ci-ok", "droid-review"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  },
  "restrictions": null
}
PROTECT_EOF
    echo "  [+] enforce_admins=true set"
  else
    echo "  [!] No branch protection found, skipping enforce_admins (set up branch protection first)"
  fi
fi

# 6. Commit if cloned via --repo
if [[ "${CLEANUP:-}" == "true" ]]; then
  cd "$TARGET"
  git add -A
  git commit -m "chore(security): 部署安全基线（droid-review + auto-merge + check脚本 + 安全模板）" 2>/dev/null || true
  git push origin main 2>/dev/null || git push origin master 2>/dev/null || true
  rm -rf "$TARGET"
  echo "  [+] Pushed to remote and cleaned up"
fi

echo ""
echo "=== Security baseline deployment complete ==="
echo ""
echo "Next steps:"
echo "  1. Configure required secrets: FACTORY_API_KEY, NVIDIA_KONG_PROXY_KEY"
echo "  2. Ensure ci.yml references check_droid_review.sh"
echo "  3. Verify branch protection is active"
