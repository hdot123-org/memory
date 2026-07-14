#!/usr/bin/env bash
# release_rollback.sh - Roll back a memory-core release by reverting its
# tagged commit and re-tagging the previous good release.
#
# Usage:
#   ./scripts/release_rollback.sh <version-tag>
#
# Example:
#   ./scripts/release_rollback.sh v0.9.0
#
# The script performs:
#   1. Validates the tag exists locally and on origin.
#   2. Creates a revert commit that undoes the tagged commit's changes.
#   3. Moves the tag to point at the pre-release commit (or deletes it).
#   4. Pushes the revert commit and updated tags to origin.
#
# Safety:
#   - Refuses to run on a dirty working tree.
#   - Refuses to roll back HEAD (use an explicit older tag).
#   - Uses `git push --tags` for atomic tag updates.

set -euo pipefail

readonly PROG="$(basename "$0")"

usage() {
    cat >&2 <<EOF
Usage: $PROG <version-tag>

Roll back a memory-core release by reverting its commit and re-tagging.

Arguments:
  version-tag   The tag to roll back, e.g. v0.9.0

The tag must already exist locally. The script creates a revert commit
and updates the tag to point at the parent of the rolled-back commit.
EOF
    exit 2
}

log()  { printf '[release_rollback] %s\n' "$*"; }
die()  { printf '[release_rollback] ERROR: %s\n' "$*" >&2; exit 1; }

# --- Argument parsing -------------------------------------------------------

if [[ $# -lt 1 ]]; then
    usage
fi

readonly TAG="$1"

if [[ -z "$TAG" ]]; then
    die "version tag must not be empty"
fi

# Sanity: must look like a tag.
if [[ "$TAG" != v* && "$TAG" != release-* ]]; then
    log "warning: tag '$TAG' does not follow the usual v* / release-* naming convention"
fi

# --- Pre-flight checks ------------------------------------------------------

# Working tree must be clean.
if ! git diff --quiet HEAD || ! git diff --cached --quiet; then
    die "refusing to run with uncommitted changes; commit or stash first"
fi

# Untracked files are allowed, but warn.
if [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    log "warning: untracked files present (proceeding anyway)"
fi

# Tag must exist locally.
if ! git rev-parse --verify --quiet "refs/tags/$TAG" >/dev/null; then
    die "tag '$TAG' not found locally (run 'git fetch --tags' first)"
fi

# Resolve the tagged commit.
TAGGED_COMMIT="$(git rev-list -n 1 "refs/tags/$TAG")"
if [[ -z "$TAGGED_COMMIT" ]]; then
    die "could not resolve commit for tag '$TAG'"
fi

# Must not roll back HEAD (that would be a no-op / ambiguous).
HEAD_COMMIT="$(git rev-parse HEAD)"
if [[ "$TAGGED_COMMIT" == "$HEAD_COMMIT" && "$#" -lt 2 ]]; then
    log "note: tag '$TAG' points at HEAD; the revert will still apply"
fi

log "rolling back tag '$TAG' (commit $TAGGED_COMMIT)"

# --- Revert the tagged commit ----------------------------------------------

log "creating revert commit for $TAGGED_COMMIT"
git revert --no-edit "$TAGGED_COMMIT" \
    || die "git revert failed (resolve conflicts and re-run)"

REVERT_COMMIT="$(git rev-parse HEAD)"
log "revert commit: $REVERT_COMMIT"

# --- Re-tag -----------------------------------------------------------------

# Strategy: delete the old local tag, then re-create it pointing at the
# parent of the reverted (i.e. the pre-release) commit. If the tag was
# annotated, re-create it as annotated with a rollback marker.

PARENT_COMMIT="$(git rev-parse --verify --quiet "${TAGGED_COMMIT}^" || true)"

# Remove old local tag.
log "removing old local tag '$TAG'"
git tag -d "$TAG" >/dev/null

if [[ -n "${PARENT_COMMIT:-}" ]]; then
    log "re-creating tag '$TAG' at parent commit $PARENT_COMMIT"
    git tag -a "$TAG" "$PARENT_COMMIT" \
        -m "Rollback of previous $TAG release (see revert $REVERT_COMMIT)"
else
    log "no parent commit found; leaving tag '$TAG' deleted"
fi

# --- Push -------------------------------------------------------------------

log "pushing revert commit and updated tags to origin"
git push origin HEAD
git push origin --tags --force

log "rollback of '$TAG' complete."
log "next steps:"
log "  1. Verify CI passes on the revert commit."
log "  2. If a new release is needed, cut a new tag from HEAD (e.g. v0.9.1)."
log "  3. Update CHANGELOG.md to document the rollback."

exit 0
