"""INFRA-521 + M5: write-pending-ci.sh 回归测试。

M3 硬化语义（PR #978）：
- 原子写入 pending-ci JSON（tmp+mv，无 .tmp 残留）

M5 事件时重绑定（PR #986）：
- write-pending-ci.sh 仅写 {pr_number, cwd, created_at}，不再包含 session_id
- 会话探活与选择职责已迁移至 trigger-ci-droid.sh（事件时重绑定）
- write-pending-ci.sh 不再接受 session_id 参数，不再探测 API

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
# VAL-WPC-001: M5 write-pending-ci.sh 基础功能（无 session_id 参数）
# M5 变更：session 选择职责迁移至 trigger-ci-droid.sh
# ============================================================================
class TestM5BasicWrite:
    def test_write_pending_without_session_id(self, stub_api_server, tmp_path):
        """M5: write-pending-ci.sh 仅接收 PR_NUMBER，不接收 session_id。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9103", env=env)
        assert code == 0, f"Expected success, stderr: {stderr}"
        pending = _read_pending(Path(env["HOME"]), 9103)
        assert pending is not None
        # M5 schema: {pr_number, cwd, created_at} - NO session_id
        assert "session_id" not in pending, "M5 schema should not contain session_id"
        assert pending["pr_number"] == "9103"
        assert pending["created_at"]
        assert pending["cwd"] == toplevel

    def test_write_pending_schema_fields(self, stub_api_server, tmp_path):
        """M5: pending 文件仅包含 pr_number, cwd, created_at 三个字段。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9104", env=env)
        assert code == 0, f"Expected success, stderr: {stderr}"
        pending = _read_pending(Path(env["HOME"]), 9104)
        assert pending is not None
        assert set(pending.keys()) == {"pr_number", "cwd", "created_at"}

    def test_no_api_probe_in_write(self, stub_api_server, tmp_path):
        """M5: write-pending-ci.sh 不再探测 API（职责已迁移至 trigger-ci-droid.sh）。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        # 即使不设置 FACTORY_TOKEN，脚本也应成功（因为不再需要探测 API）
        env.pop("FACTORY_TOKEN", None)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9105", env=env)
        assert code == 0, f"Expected success without token (M5 no probe), stderr: {stderr}"
        pending = _read_pending(Path(env["HOME"]), 9105)
        assert pending is not None
        assert pending["pr_number"] == "9105"


# ============================================================================
# VAL-WPC-002: sessions-index 候选迭代（已迁移至 trigger-ci-droid.sh）
# M5 变更：write-pending-ci.sh 不再负责 session 选择，此测试类保留但仅验证迁移完整性
# ============================================================================
class TestCandidateIteration:
    """M5 后此测试类不再适用。session 选择逻辑已迁移至 trigger-ci-droid.sh。

    原测试覆盖的 mtime 排序、worker 过滤、cwd 匹配等逻辑现在由
    test_trigger_ci_droid_fallback.py 覆盖（见 VAL-TRIGCI-003）。
    """

    pass


# ============================================================================
# VAL-WPC-003: 原子写入 — tmp+mv，成功后无 .tmp 残留、内容为合法 JSON
# ============================================================================
class TestAtomicWrite:
    def test_no_tmp_residue_and_valid_json(self, stub_api_server, tmp_path):
        """写入成功后 locks 目录无 .tmp.* 残留文件，pending 内容合法。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        code, _, stderr = _run_script(SCRIPT_PATH, "9301", env=env)
        assert code == 0, f"Expected success, stderr: {stderr}"
        locks_dir = Path(env["HOME"]) / ".factory" / "webhook" / "locks"
        tmp_files = list(locks_dir.glob("pending-ci-9301.json.tmp.*"))
        assert not tmp_files, f"Atomic write left tmp residue: {tmp_files}"
        pending = _read_pending(Path(env["HOME"]), 9301)
        assert pending is not None
        # M5 schema: 仅 pr_number, cwd, created_at
        assert set(pending) == {"pr_number", "cwd", "created_at"}


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
        """不在 git 仓库：报错退出。"""
        plain = tmp_path / "plain"
        plain.mkdir()
        env = _make_env(stub_api_server, tmp_path, cwd=plain)
        code, stdout, stderr = _run_script(SCRIPT_PATH, "9401", env=env)
        combined = stdout + stderr
        assert code != 0
        assert "Not in a git repository" in combined or "git repository" in combined.lower()

    def test_invalid_pr_number_rejected(self, stub_api_server, tmp_path):
        """非法 PR_NUMBER（0、负数、非数字）应被拒绝。"""
        repo, toplevel = _init_sandbox_repo(tmp_path)
        env = _make_env(stub_api_server, tmp_path, cwd=repo)
        for bad_pr in ["0", "-1", "abc", "", "1.5"]:
            code, stdout, stderr = _run_script(SCRIPT_PATH, bad_pr, env=env)
            assert code != 0, f"Expected non-zero exit for PR_NUMBER={bad_pr!r}"
            assert _read_pending(Path(env["HOME"]), int(bad_pr) if bad_pr.isdigit() else 0) is None


# ============================================================================
# M5 迁移说明：TestMtimeScanProbeRC 和 TestCandidateIteration 已废弃
# ============================================================================
# 原 BLK-M3-R1-1 probe rc 捕获测试和 TestCandidateIteration 的 mtime 扫描逻辑
# 已迁移至 trigger-ci-droid.sh（事件时重绑定）。
# 相关测试覆盖位于 tests/test_trigger_ci_droid_*.py
# 本文件仅保留 write-pending-ci.sh 的职责：写 {pr_number, cwd, created_at}


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
