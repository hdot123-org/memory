#!/bin/bash
# wiki-refresh.sh — GitLab/GitHub push webhook → 本机 droid 执行 /wiki
# 由 adnanh/webhook 调用，立即返回 accepted，后台执行 /wiki
# 支持多项目：通过 repositories.yml 路由（gitlabProject 或 githubRepo）→ repoPath
# 自动检测 payload 格式：GitHub (repository.full_name) vs GitLab (project.git_http_url)

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

set -uo pipefail

# === 参数 ===
# $1 = GitLab project.git_http_url (empty for GitHub payloads)
# $2 = GitHub repository.full_name  (empty for GitLab payloads)
# $3 = ref (refs/heads/main)
# $4 = after (commit sha)
GITLAB_URL="${1:-}"
GITHUB_FULLNAME="${2:-}"
REF="${3:-}"
COMMIT_SHA="${4:-}"

# 从 ref 提取分支名 (refs/heads/main → main)
BRANCH="${REF#refs/heads/}"

# === payload 格式检测 ===
if [ -n "$GITHUB_FULLNAME" ]; then
    PAYLOAD_SOURCE="github"
elif [ -n "$GITLAB_URL" ]; then
    PAYLOAD_SOURCE="gitlab"
else
    PAYLOAD_SOURCE="unknown"
fi

# === 配置 ===
WEBHOOK_BASE="/Users/busiji/.factory/webhook"
LOG_DIR="${WEBHOOK_BASE}/logs"
LOCK_DIR="${WEBHOOK_BASE}/locks"
REPO_CONFIG="/Users/busiji/.factory/config/repositories.yml"

# === 日志 ===
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${LOG_DIR}/wiki-refresh-${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "=== wiki-refresh.sh started ==="
log "PAYLOAD_SOURCE=$PAYLOAD_SOURCE GITLAB_URL=$GITLAB_URL GITHUB_FULLNAME=$GITHUB_FULLNAME BRANCH=$BRANCH COMMIT=$COMMIT_SHA"

if [ "$BRANCH" != "main" ]; then
    log "SKIP: branch=$BRANCH is not main"
    exit 0
fi

# === 仓库路由 ===
# GitHub payload: 用 repository.full_name 匹配 repositories.yml 的 githubRepo
# GitLab payload: 从 project.git_http_url 提取 path 匹配 gitlabProject
# GitHub is now primary; GitLab kept as fallback for backward compatibility.

route_repo() {
    local payload_source="$1"
    local gitlab_url="$2"
    local github_fullname="$3"
    if [ ! -f "$REPO_CONFIG" ]; then
        echo ""
        return
    fi
    PAYLOAD_SOURCE="$payload_source" GITLAB_URL="$gitlab_url" GITHUB_FULLNAME="$github_fullname" python3 -c "
import yaml, os, re

with open('$REPO_CONFIG') as f:
    cfg = yaml.safe_load(f)

payload_source = os.environ.get('PAYLOAD_SOURCE', '')
github_fullname = os.environ.get('GITHUB_FULLNAME', '').strip()
gitlab_url = os.environ.get('GITLAB_URL', '').strip()

if payload_source == 'github' and github_fullname:
    # GitHub: 直接匹配 githubRepo (e.g. hdot123/memory)
    for td in cfg.get('teams', {}).values():
        for repo in td.get('repos', []):
            if repo.get('githubRepo', '') == github_fullname:
                print(os.path.expanduser(repo.get('repoPath', '')))
                exit()
elif payload_source == 'gitlab' and gitlab_url:
    # GitLab: 从 URL 提取 project path 后匹配 gitlabProject
    repo_url = gitlab_url.rstrip('/')
    match = re.search(r'://[^/]+/(.+?)(?:\.git)?\$', repo_url)
    if not match:
        print('')
        exit()
    gitlab_project = match.group(1)
    for td in cfg.get('teams', {}).values():
        for repo in td.get('repos', []):
            gp = repo.get('gitlabProject', '')
            if gp == gitlab_project:
                print(os.path.expanduser(repo.get('repoPath', '')))
                exit()
    # GitLab fallback: 若无 gitlabProject 映射，尝试用 githubRepo 的 path 部分匹配
    for td in cfg.get('teams', {}).values():
        for repo in td.get('repos', []):
            gh = repo.get('githubRepo', '')
            if gh and gh.split('/')[-1] == gitlab_project.split('/')[-1]:
                print(os.path.expanduser(repo.get('repoPath', '')))
                exit()
print('')
" 2>/dev/null || echo ""
}

REPO_PATH=$(route_repo "$PAYLOAD_SOURCE" "$GITLAB_URL" "$GITHUB_FULLNAME")

if [ -z "$REPO_PATH" ] || [ ! -d "$REPO_PATH" ]; then
    log "ERROR: Cannot route payload to valid local path (source=$PAYLOAD_SOURCE gitlab_url=$GITLAB_URL github_fullname=$GITHUB_FULLNAME got: $REPO_PATH)"
    log "Check repositories.yml githubRepo/gitlabProject mapping"
    exit 1
fi

if [ "$PAYLOAD_SOURCE" = "github" ]; then
    log "Routed: $GITHUB_FULLNAME -> $REPO_PATH"
    REPO_KEY=$(echo "$GITHUB_FULLNAME" | tr '/' '-')
else
    log "Routed: $GITLAB_URL -> $REPO_PATH"
    REPO_KEY=$(basename "$REPO_PATH")
fi

# === 并发防护：flock 互斥锁 ===
mkdir -p "$LOCK_DIR" 2>/dev/null || true
WIKI_LOCK="${LOCK_DIR}/wiki-${REPO_KEY}.lock"
exec 9>"$WIKI_LOCK"
if ! flock -n 9; then
    log "SKIP: Another wiki-refresh instance is already running for $REPO_KEY (lock: $WIKI_LOCK)"
    exit 0
fi
log "Acquired flock: $WIKI_LOCK"

# 拉取最新代码 (GitHub is now primary remote → origin)
cd "$REPO_PATH" || { log "ERROR: cd $REPO_PATH failed"; exit 1; }

# Capture git pull output and check exit status
if ! git pull origin main 2>&1 | tee -a "$LOG_FILE"; then
    log "ERROR: git pull origin main failed — aborting wiki refresh"
    log "Will not start droid /wiki to avoid working with stale code"
    exit 1
fi

# === 异步执行 ===
(
    log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

    log "--- async wiki generation started for $(basename "$REPO_PATH") ---"
    log "Launching droid exec /wiki..."

    DROID_OUTPUT=$("${DROID_BIN:-$(command -v droid || echo /usr/local/bin/droid)}" exec \
        --auto high \
        "/wiki" 2>&1) || DROID_EXIT=$?

    DROID_EXIT=${DROID_EXIT:-0}
    log "droid exec finished with exit code: $DROID_EXIT"
    log "Output (last 500 chars): ${DROID_OUTPUT: -500}"
    log "--- async wiki generation completed ---"

) >> "$LOG_FILE" 2>&1 &

log "Background wiki process started: PID=$!"
exit 0
