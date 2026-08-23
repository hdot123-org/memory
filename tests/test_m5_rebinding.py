"""INFRA-527: M5 事件时 session 重绑定行为测试。

覆盖 trigger-ci-droid.sh M5 流程的 4 条关键路径（VAL-TRIGCI-003 补齐，
兑现 test_write_pending_ci_hardening.py L210 的迁移承诺）：

1. 新 schema（无 session_id）→ 重绑定选择存活 session 并注入
2. 旧 schema（session_id 存在）→ session 存活，直接使用
3. 旧 schema（session_id 存在）→ session 已死，重绑定找到存活 session
4. 全部候选死亡 → fallback + 标记 rebinding_failed（pending 文件保留）

回归守护（INFRA-527 根因）：
- 新 schema pending 文件（write-pending-ci.sh M5 版写入的格式）的字段解析
  不得错位——旧实现的 ``read`` 前导空格剥离导致 SESSION_ID 吞掉 PR 号，
  100% 误报 ci_pr_mismatch，CI 通知静默丢失。

测试用 stub HTTP server 模拟 Factory Sessions API（沿用
test_trigger_ci_droid_fallback.py 的隔离模式），严禁向生产 session 注入。

Session ID 编码约定（stub 控制探活/注入结果）：
- 含 "dead"     → 探活 404（Session does not exist）
- 含 "alive"    → 探活 200 + 注入 200（messageId 返回）
- 含 "5xx"      → 注入 504（本文件未使用，保留与 fallback 测试一致的约定）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
TRIGGER_SCRIPT = REPO_ROOT / "webhook-scripts" / "trigger-ci-droid.sh"


class StubSessionsAPIHandler(BaseHTTPRequestHandler):
    """Stub Factory Sessions API：按 session_id 关键字返回受控响应。"""

    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler 签名
        pass

    def _json(self, status: int, payload: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_GET(self):
        """探活：GET /api/v0/sessions/{id}"""
        path = self.path.removeprefix("/api/v0")
        if path.startswith("/sessions/") and not path.endswith("/messages"):
            session_id = path.split("/")[-1]
            if "dead" in session_id:
                self._json(404, {"detail": "Session does not exist", "status": 404})
            else:
                self._json(200, {"id": session_id, "status": "active"})
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        """注入：POST /api/v0/sessions/{id}/messages"""
        path = self.path.removeprefix("/api/v0")
        if path.startswith("/sessions/") and path.endswith("/messages"):
            content_length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(content_length)
            session_id = path.split("/")[-2]
            if "dead" in session_id:
                self._json(410, {"error": "Gone"})
            else:
                self._json(200, {"messageId": f"msg-{int(time.time() * 1000)}", "status": "queued"})
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


def _make_env(stub_base: str, tmp_path: Path) -> dict:
    """构造隔离环境：临时 LOCK/LOG 目录 + stub API + dry-run。

    - WEBHOOK_BASE / LOCK_DIR / LOG_DIR → tmp_path 沙箱（不触碰 ~/.factory）
    - SESSIONS_INDEX → tmp_path 沙箱 sessions-index.json
    - FACTORY_TOKEN → 动态拼接假值（仅满足 ^fk- 前缀校验；stub 不验证真实性）
    - ECHO_DROID=1 / POSTHOG_DRY_RUN=1 → 不派生真实 droid、不发真实事件
    """
    import shutil

    home = tmp_path / "home"
    (home / ".factory").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["FACTORY_API_BASE"] = stub_base
    env["FACTORY_TOKEN"] = "fk-" + "test-stub-" + "not-real"
    env["POSTHOG_DRY_RUN"] = "1"
    env["ECHO_DROID"] = "1"
    env["PYTHON_BIN"] = sys.executable
    env["WEBHOOK_BASE"] = str(tmp_path / "webhook")
    env["LOCK_DIR"] = str(tmp_path / "locks")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["MAX_RETRIES"] = "2"
    env["RETRY_DELAY"] = "1"
    env["SESSIONS_INDEX"] = str(tmp_path / "home" / ".factory" / "sessions-index.json")
    for d in ("webhook", "locks", "logs"):
        (tmp_path / d).mkdir(exist_ok=True)
    flock_path = shutil.which("flock")
    if flock_path:
        env["FLOCK_BIN"] = flock_path
    return env


def _write_pending(locks_dir: Path, pr_number: int, *, session_id: str | None, cwd: str) -> Path:
    """写入 pending-ci 文件。session_id=None → M5 新 schema。"""
    data: dict = {
        "pr_number": str(pr_number),
        "cwd": cwd,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if session_id is not None:
        # Old schema: session_id first（与历史写入格式一致）
        data = {"session_id": session_id, **data}
    file_path = locks_dir / f"pending-ci-{pr_number}.json"
    file_path.write_text(json.dumps(data))
    return file_path


def _write_sessions_index(env: dict, entries: list[dict], default_cwd: str) -> None:
    """写入沙箱 sessions-index.json（顶层 mission-session + orchestrator role）。"""
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
    Path(env["SESSIONS_INDEX"]).write_text(json.dumps(payload))


def _run_trigger(env: dict, pr_number: int) -> tuple[int, str]:
    result = subprocess.run(
        ["bash", str(TRIGGER_SCRIPT), str(pr_number), "test-branch", "abc123", "passed"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO_ROOT),
    )
    return result.returncode, result.stdout + result.stderr


PROJECT_CWD = "/test/project"


class TestM5NewSchemaRebinding:
    """路径 1：新 schema（无 session_id）→ 事件时重绑定选择存活 session 并注入。"""

    def test_new_schema_rebinds_to_alive_session(self, stub_api_server, tmp_path):
        env = _make_env(stub_api_server, tmp_path)
        locks_dir = Path(env["LOCK_DIR"])

        # 候选按 mtime 降序：dead-session 较新，alive-session 较旧。
        # select_session_at_event_time 返回 mtime 最高的 dead-session（stub 404），
        # 探活失败后……见下：当前实现只取 top-1，探活失败即判 rebinding_failed。
        # 因此本用例让 top-1 直接是 alive（mtime 更高），验证「重绑定 → 存活 → 注入」。
        _write_sessions_index(
            env,
            [
                {"sessionId": "alive-session-2", "mtime": 2000},
                {"sessionId": "dead-session-1", "mtime": 1000},
            ],
            PROJECT_CWD,
        )
        pending = _write_pending(locks_dir, 9101, session_id=None, cwd=PROJECT_CWD)

        rc, output = _run_trigger(env, 9101)

        # 回归守护（INFRA-527 根因）：新 schema 不得误报 ci_pr_mismatch
        assert "PR number mismatch" not in output, "New-schema pending file must not trip ci_pr_mismatch"
        assert "corrupted" not in output.lower(), "New-schema pending file must not be quarantined as corrupted"

        # 走到事件时重绑定
        assert "event-time rebinding" in output or "event-time session selection" in output
        assert "Selected session via event-time rebinding: alive-session-2" in output

        # 注入到重绑定选中的 session
        assert "POSTing to" in output and "alive-session-2" in output

        # 成功路径：pending 文件标记 injected_at（保留审计）
        data = json.loads(pending.read_text())
        assert "injected_at" in data
        assert data.get("message_id", "").startswith("msg-")


class TestM5OldSchemaAlive:
    """路径 2：旧 schema（session_id 存在）→ session 存活，直接使用（不重绑定）。"""

    def test_old_schema_alive_session_used_directly(self, stub_api_server, tmp_path):
        env = _make_env(stub_api_server, tmp_path)
        locks_dir = Path(env["LOCK_DIR"])

        # sessions-index 提供一个 mtime 更高的干扰项，验证旧 schema 存活时不重绑定
        _write_sessions_index(
            env,
            [
                {"sessionId": "alive-index-newest", "mtime": 2000},
                {"sessionId": "alive-session-1", "mtime": 1000},
            ],
            PROJECT_CWD,
        )
        _write_pending(locks_dir, 9102, session_id="alive-session-1", cwd=PROJECT_CWD)

        rc, output = _run_trigger(env, 9102)

        assert "Old schema detected" in output
        assert "alive-session-1 is alive" in output
        # 不触发重绑定（selected-via-rebinding 不应出现）
        assert "Selected session via event-time rebinding" not in output
        assert "POSTing to" in output and "alive-session-1" in output


class TestM5OldSchemaDeadRebind:
    """路径 3：旧 schema（session_id 存在）→ session 已死 → 重绑定找到存活 session。"""

    def test_old_schema_dead_session_rebinds_alive(self, stub_api_server, tmp_path):
        env = _make_env(stub_api_server, tmp_path)
        locks_dir = Path(env["LOCK_DIR"])

        _write_sessions_index(
            env,
            [
                {"sessionId": "alive-session-2", "mtime": 2000},
                {"sessionId": "dead-session-1", "mtime": 1000},
            ],
            PROJECT_CWD,
        )
        pending = _write_pending(locks_dir, 9103, session_id="dead-session-1", cwd=PROJECT_CWD)

        rc, output = _run_trigger(env, 9103)

        assert "dead-session-1 is dead" in output
        assert "Selected session via event-time rebinding: alive-session-2" in output
        assert "POSTing to" in output and "alive-session-2" in output

        # 注入成功写 injected_at
        data = json.loads(pending.read_text())
        assert "injected_at" in data


class TestM5AllDeadFallback:
    """路径 4：全部候选死亡 → fallback + 标记 rebinding_failed（文件保留）。"""

    def test_all_dead_marks_rebinding_failed_and_falls_back(self, stub_api_server, tmp_path):
        env = _make_env(stub_api_server, tmp_path)
        locks_dir = Path(env["LOCK_DIR"])

        _write_sessions_index(
            env,
            [
                {"sessionId": "dead-session-2", "mtime": 2000},
                {"sessionId": "dead-session-1", "mtime": 1000},
            ],
            PROJECT_CWD,
        )
        pending = _write_pending(locks_dir, 9104, session_id="dead-session-1", cwd=PROJECT_CWD)

        rc, output = _run_trigger(env, 9104)

        assert "dead-session-1 is dead" in output
        assert "No live session available" in output
        assert "FALLBACK: Spawning droid exec" in output

        # pending 文件保留（审计轨迹）且标记 rebinding_failed + fallback_dispatched_at
        assert pending.exists(), "Pending file must be preserved (audit trail)"
        data = json.loads(pending.read_text())
        assert "rebinding_failed" in data
        assert data.get("rebinding_reason") == "all_candidates_dead"
        assert "fallback_dispatched_at" in data


class TestM5CandidateFiltering:
    """重绑定候选筛选：worker 子会话 / 非本 cwd / 非顶层会话不得入选。"""

    def test_worker_and_foreign_cwd_sessions_excluded(self, stub_api_server, tmp_path):
        env = _make_env(stub_api_server, tmp_path)
        locks_dir = Path(env["LOCK_DIR"])

        # 三种应被过滤的干扰项 + 一个合格的 alive 候选
        _write_sessions_index(
            env,
            [
                # worker 子会话（callingSessionId 非空）——mtime 最高，诱使误选
                {"sessionId": "alive-worker", "mtime": 5000, "callingSessionId": "parent-1"},
                # 其他仓库的会话
                {"sessionId": "alive-foreign-cwd", "mtime": 4000, "cwd": "/other/project"},
                # 非 orchestrator role 的顶层会话
                {"sessionId": "alive-not-orchestrator", "mtime": 3000, "role": "worker"},
                # 唯一合格候选
                {"sessionId": "alive-orchestrator", "mtime": 100},
            ],
            PROJECT_CWD,
        )
        _write_pending(locks_dir, 9105, session_id=None, cwd=PROJECT_CWD)

        rc, output = _run_trigger(env, 9105)

        assert "Selected session via event-time rebinding: alive-orchestrator" in output
        assert "POSTing to" in output and "alive-orchestrator" in output


class TestM5RegressionFieldAlignment:
    """回归守护（INFRA-527 根因）：新 schema 字段解析不得错位。"""

    def test_new_schema_pr_number_not_eaten_by_session_id(self, stub_api_server, tmp_path):
        """空 session_id 下 PENDING_PR 必须仍是 pr_number（不得左移为 created_at）。"""
        env = _make_env(stub_api_server, tmp_path)
        locks_dir = Path(env["LOCK_DIR"])
        _write_sessions_index(env, [], PROJECT_CWD)
        _write_pending(locks_dir, 9106, session_id=None, cwd=PROJECT_CWD)

        rc, output = _run_trigger(env, 9106)

        # 到达 session 选择阶段即证明 pr 校验通过（错位时在此前就 mismatch 退出）
        assert "PR number mismatch" not in output
        assert "Pending PR from file: 9106" in output, "PENDING_PR must stay aligned under empty session_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
