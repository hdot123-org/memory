"""INFRA-521: write-pending-ci.sh M3 硬化语义回归测试。

覆盖受管副本 ``webhook-scripts/write-pending-ci.sh``（PR #978 回填）的
会话探活与锁语义，对应 TD-WEBHOOK-03 技术债修复：

- 显式 SESSION_ID 探活 404 → fail-fast，拒绝写入死会话 pending 文件
- 显式 SESSION_ID 探活不可达（HTTP 000/5xx）→ fail-fast
- 无 token → fail-fast（不允许写未经验证的 pending 文件）
- sessions-index 候选迭代：mtime 降序逐个探活，404 顺延下一个
- 全部候选死 → fail-fast，不发死会话路由
- 活跃候选 → 原子写入 pending-ci JSON（tmp+mv，无 .tmp 残留）
- 候选筛选：仅顶层 mission-session + orchestrator role + cwd 匹配

测试用 stub HTTP server 模拟 Factory Sessions API（沿用
test_trigger_ci_droid_fallback.py 的隔离模式），HOME 重定向到临时目录，
严禁触碰生产 ``~/.factory`` 路径。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "webhook-scripts" / "write-pending-ci.sh"


class StubSessionsAPIHandler(BaseHTTPRequestHandler):
    """Stub Factory Sessions API。

    会话 ID 编码控制探活结果：
    - 含 "nonexistent" → 404（会话不存在）
    - 含 "unreachable" → 500（API 故障）
    - 其他 → 200（会话存活）
    """

    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler 签名
        pass

    def do_GET(self):
        path = self.path.removeprefix("/api/v0")
        if path.startswith("/sessions/") and not path.endswith("/messages"):
            session_id = path.split("/")[-1]
            if "nonexistent" in session_id:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"detail": "Session does not exist", "status": 404}).encode())
                return
            if "unreachable" in session_id:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"detail": "internal error"}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"id": session_id, "status": "active", "createdAt": datetime.now(UTC).isoformat()}).encode()
            )
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture(scope="module")
def stub_api_server():
    server = HTTPServer(("127.0.0.1", 0), StubSessionsAPIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/api/v0"
    server.shutdown()


def _run_script(script: Path, *args: str, env: dict) -> tuple[int, str, str]:
    result = subprocess.run(
        ["bash", str(script), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=env.get("_TEST_CWD", str(REPO_ROOT)),
    )
    return result.returncode, result.stdout, result.stderr


def _make_env(stub_base: str, tmp_path: Path, *, cwd: Path | None = None) -> dict:
    """构造隔离环境：HOME 重定向 + stub API + dry-run PostHog。

    - HOME → tmp_path/home（LOCKS_DIR / SESSIONS_INDEX 全部指向沙箱）
    - FACTORY_API_BASE → stub server
    - FACTORY_TOKEN → 动态拼接假值（仅满足 ^fk- 前缀校验；stub 不验证真实性，
      禁止在源码中出现完整 token 字面量）
    - POSTHOG_DRY_RUN=1 → 不发送真实分析事件
    """
    home = tmp_path / "home"
    (home / ".factory" / "webhook" / "locks").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["FACTORY_API_BASE"] = stub_base
    env["FACTORY_TOKEN"] = "fk-" + "test-stub-" + "not-real"
    env["POSTHOG_DRY_RUN"] = "1"
    env["PYTHON_BIN"] = sys.executable
    if cwd is not None:
        env["_TEST_CWD"] = str(cwd)
    return env


def _init_sandbox_repo(tmp_path: Path) -> tuple[Path, str]:
    """初始化沙箱 git 仓库，返回 (repo_path, toplevel)。

    PROJECT_CWD 探测依赖 git rev-parse --show-toplevel；macOS 上该命令返回
    解析符号链接后的路径（/private/var/...），与 pytest tmp_path 的字面值
    （/var/folders/...）不同，sessions-index 的 cwd 必须使用 toplevel 原值。
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True, text=True)
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    return repo, toplevel


def _write_sessions_index(home: Path, entries: list[dict], default_cwd: str = "/sandbox/repo") -> None:
    """写入沙箱 sessions-index.json。"""
    payload = {
        "entries": [
            {
                "sessionId": e["sessionId"],
                "cwd": e.get("cwd", default_cwd),
                "mtime": e["mtime"],
                "callingSessionId": e.get("callingSessionId"),
                "tags": [{"name": "mission-session", "metadata": {"role": e.get("role", "orchestrator")}}],
            }
            for e in entries
        ]
    }
    index_path = home / ".factory" / "sessions-index.json"
    index_path.write_text(json.dumps(payload))


def _read_pending(home: Path, pr_number: int) -> dict | None:
    f = home / ".factory" / "webhook" / "locks" / f"pending-ci-{pr_number}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


# ============================================================================
# VAL-WPC-001: 显式 SESSION_ID 探活失败 → fail-fast，拒绝写入死会话 pending
# ============================================================================
class TestExplicitSessionProbe:
    def test_explicit_404_fails_fast_no_pending(self, stub_api_server, tmp_path):
        """显式 SESSION_ID 探活 404：退出码非 0，pending 文件不落盘。"""
        env = _make_env(stub_api_server, tmp_path)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9101", "probe-nonexistent-session", env=env)
        combined = stdout + stderr
        assert code != 0, "Explicit 404 session must fail fast"
        assert "does not exist" in combined or "404" in combined
        assert _read_pending(Path(env["HOME"]), 9101) is None, "No pending file should be written for dead session"

    def test_explicit_unreachable_fails_fast(self, stub_api_server, tmp_path):
        """显式 SESSION_ID 探活 5xx：fail-fast，不写未经验证的 pending。"""
        env = _make_env(stub_api_server, tmp_path)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9102", "probe-unreachable-session", env=env)
        combined = stdout + stderr
        assert code != 0
        assert "unreachable" in combined.lower() or "unvalidated" in combined.lower()
        assert _read_pending(Path(env["HOME"]), 9102) is None

    def test_explicit_alive_writes_pending(self, stub_api_server, tmp_path):
        """显式 SESSION_ID 探活 200：写入 pending 文件，字段完整。"""
        env = _make_env(stub_api_server, tmp_path)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9103", "probe-alive-session", env=env)
        assert code == 0, f"Expected success, stderr: {stderr}"
        pending = _read_pending(Path(env["HOME"]), 9103)
        assert pending is not None
        assert pending["session_id"] == "probe-alive-session"
        assert pending["pr_number"] == "9103"
        assert pending["created_at"]
        assert pending["cwd"] == str(REPO_ROOT)  # 默认 cwd = 脚本运行目录（git root）

    def test_no_token_fails_fast(self, stub_api_server, tmp_path):
        """无可用 token：拒绝写未经验证的 pending（fail-fast）。"""
        env = _make_env(stub_api_server, tmp_path)
        # get_factory_token 依次尝试 FACTORY_TOKEN / 1Password MCP；清空两者
        env.pop("FACTORY_TOKEN", None)
        # op-mcp.sh 由 SCRIPT_DIR/lib 相对定位，HOME 重定向后不可达 → 无 token
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9104", "probe-any-session", env=env)
        combined = stdout + stderr
        assert code != 0
        assert "token unavailable" in combined.lower() or "cannot probe" in combined.lower()
        assert _read_pending(Path(env["HOME"]), 9104) is None


# ============================================================================
# VAL-WPC-002: sessions-index 候选迭代 — mtime 降序探活，404 顺延
# ============================================================================
class TestCandidateIteration:
    def test_dead_first_alive_second_selected(self, stub_api_server, tmp_path):
        """mtime 最新的候选死（404）→ 顺延探活次新候选并选中。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        home = Path(env["HOME"])
        _write_sessions_index(
            home,
            [
                {"sessionId": "cand-nonexistent-new", "mtime": 2000},
                {"sessionId": "cand-alive-old", "mtime": 1000},
            ],
            default_cwd=toplevel,
        )
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9201", env=env)
        assert code == 0, f"Expected success, stderr: {stderr}"
        combined = stdout + stderr
        assert "dead (404), trying next candidate" in combined
        assert "cand-alive-old is alive" in combined
        pending = _read_pending(home, 9201)
        assert pending is not None
        assert pending["session_id"] == "cand-alive-old"
        assert pending["cwd"] == toplevel

    def test_all_candidates_dead_fails_fast(self, stub_api_server, tmp_path):
        """全部候选死（404）：fail-fast 退出，不发死会话路由。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        home = Path(env["HOME"])
        _write_sessions_index(
            home,
            [
                {"sessionId": "cand-nonexistent-a", "mtime": 3000},
                {"sessionId": "cand-nonexistent-b", "mtime": 2000},
                {"sessionId": "cand-nonexistent-c", "mtime": 1000},
            ],
            default_cwd=toplevel,
        )
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9202", env=env)
        combined = stdout + stderr
        assert code != 0
        assert "All candidate sessions are dead" in combined
        assert _read_pending(home, 9202) is None

    def test_worker_and_mismatched_cwd_filtered(self, stub_api_server, tmp_path):
        """候选筛选：worker 子会话与 cwd 不匹配的会话被过滤，仅顶层 orchestrator 入选。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        home = Path(env["HOME"])
        _write_sessions_index(
            home,
            [
                # worker（callingSessionId 非空，mtime 最新）→ 过滤
                {"sessionId": "cand-worker-latest", "mtime": 5000, "callingSessionId": "parent-1"},
                # cwd 不匹配（mtime 次新）→ 过滤
                {"sessionId": "cand-alive-otherrepo", "mtime": 4000, "cwd": "/other/repo"},
                # 顶层 orchestrator（cwd 匹配，mtime 最旧）→ 选中
                {"sessionId": "cand-alive-orch", "mtime": 1000},
            ],
            default_cwd=toplevel,
        )
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9203", env=env)
        assert code == 0, f"Expected success, stderr: {stderr}"
        pending = _read_pending(home, 9203)
        assert pending is not None
        assert pending["session_id"] == "cand-alive-orch"


# ============================================================================
# VAL-WPC-003: 原子写入 — tmp+mv，成功后无 .tmp 残留、内容为合法 JSON
# ============================================================================
class TestAtomicWrite:
    def test_no_tmp_residue_and_valid_json(self, stub_api_server, tmp_path):
        """写入成功后 locks 目录无 .tmp.* 残留文件，pending 内容合法。"""
        env = _make_env(stub_api_server, tmp_path)
        code, _, stderr = _run_script(SCRIPT_PATH, "9301", "probe-alive-session", env=env)
        assert code == 0, f"Expected success, stderr: {stderr}"
        locks_dir = Path(env["HOME"]) / ".factory" / "webhook" / "locks"
        tmp_files = list(locks_dir.glob("pending-ci-9301.json.tmp.*"))
        assert not tmp_files, f"Atomic write left tmp residue: {tmp_files}"
        pending = _read_pending(Path(env["HOME"]), 9301)
        assert pending is not None
        assert set(pending) == {"session_id", "pr_number", "created_at", "cwd"}


# ============================================================================
# VAL-WPC-004: 参数与环境守卫
# ============================================================================
class TestGuards:
    def test_missing_pr_number_usage_error(self, stub_api_server, tmp_path):
        """缺 PR_NUMBER 参数：usage 报错非 0 退出。"""
        env = _make_env(stub_api_server, tmp_path)
        code, stdout, stderr = _run_script(SCRIPT_PATH, env=env)
        assert code != 0
        assert "Usage" in stdout or "Usage" in stderr

    def test_not_a_git_repo_fails(self, stub_api_server, tmp_path):
        """无显式 SESSION_ID 且不在 git 仓库：报错退出。"""
        plain = tmp_path / "plain"
        plain.mkdir()
        env = _make_env(stub_api_server, tmp_path, cwd=plain)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9401", env=env)
        combined = stdout + stderr
        assert code != 0
        assert "Not in a git repository" in combined or "git repository" in combined.lower()

    def test_shellcheck_clean(self):
        """受管副本通过 shellcheck（与 CI Shell lint 步骤同一标准）。"""
        from tests.shellcheck_helpers import assert_shellcheck_clean

        assert_shellcheck_clean(SCRIPT_PATH)


# ============================================================================
# 生产一致性：受管副本与生产脚本字节一致（回填完整性快照）
# ============================================================================
class TestProdSync:
    PROD_SCRIPT = Path.home() / ".factory" / "webhook" / "scripts" / "write-pending-ci.sh"

    def test_managed_copy_matches_production(self):
        """受管副本与 ~/.factory 生产脚本一致（PR #978 回填基线）。

        生产脚本在 CI runner 上不存在 → skip（本地/mission 环境执行）。
        """
        if not self.PROD_SCRIPT.exists():
            pytest.skip("production script not present on this machine")
        assert SCRIPT_PATH.read_bytes() == self.PROD_SCRIPT.read_bytes(), (
            "webhook-scripts/write-pending-ci.sh drifted from production; "
            "run scripts/sync-webhook-scripts.sh to reconcile"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
