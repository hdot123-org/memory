"""Tests for daily_kb_audit.py SSH/systemd and HTTP endpoint checks.

Covers:
- _check_systemd_services (lines 840-946): mock _run_ssh
- HTTP endpoint health check in check_server (lines 1108-1171): mock subprocess.run
"""

import subprocess
from unittest.mock import MagicMock

import pytest

from memory_core.tools.daily_kb_audit import (
    _check_systemd_services,
    check_server,
)

# ---------------------------------------------------------------------------
# _check_systemd_services tests (lines 840-946)
# ---------------------------------------------------------------------------


class TestCheckSystemdServices:
    """Tests for _check_systemd_services function."""

    def test_empty_services_returns_empty(self, monkeypatch):
        """Empty services list returns empty dict without calling SSH."""
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda *a, **kw: pytest.fail("Should not call _run_ssh"),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services("srv", "server1", [], global_v, record_v)
        assert result == {}
        assert global_v == []
        assert record_v == []

    def test_ssh_command_fails_rc_nonzero(self, monkeypatch):
        """When _run_ssh returns non-zero rc, all services marked unknown."""
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (1, "", "Permission denied"),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["nginx", "mysql"], global_v, record_v
        )
        assert result == {"nginx": "unknown", "mysql": "unknown"}
        assert len(global_v) == 1
        assert len(record_v) == 1
        assert global_v[0]["type"] == "service_down"
        assert global_v[0]["severity"] == "warning"
        assert "systemctl" in global_v[0]["file"]

    def test_service_active_running(self, monkeypatch):
        """Service with ActiveState=active, SubState=running is marked running."""
        mock_output = (
            "=== nginx ===\n"
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=running\n"
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (0, mock_output, ""),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["nginx"], global_v, record_v
        )
        assert result == {"nginx": "running"}
        assert global_v == []
        assert record_v == []

    def test_service_not_found(self, monkeypatch):
        """Service with LoadState=not-found gets warning violation."""
        mock_output = (
            "=== custom-svc ===\n"
            "LoadState=not-found\n"
            "ActiveState=inactive\n"
            "SubState=dead\n"
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (0, mock_output, ""),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["custom-svc"], global_v, record_v
        )
        assert result == {"custom-svc": "not-found"}
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "warning"
        assert "not-found" in global_v[0]["detail"]

    def test_service_abnormal_state(self, monkeypatch):
        """Service with abnormal state gets critical violation."""
        mock_output = (
            "=== nginx ===\n"
            "LoadState=loaded\n"
            "ActiveState=failed\n"
            "SubState=failed\n"
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (0, mock_output, ""),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["nginx"], global_v, record_v
        )
        assert result == {"nginx": "failed/failed"}
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "critical"
        assert "ActiveState=failed" in global_v[0]["detail"]

    def test_service_missing_from_output(self, monkeypatch):
        """Service not found in parsed output gets warning violation."""
        mock_output = (
            "=== other-svc ===\n"
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=running\n"
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (0, mock_output, ""),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["missing-svc"], global_v, record_v
        )
        assert result == {"missing-svc": "unknown"}
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "warning"

    def test_multiple_services_mixed_states(self, monkeypatch):
        """Multiple services with different states parsed correctly."""
        mock_output = (
            "=== nginx ===\n"
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=running\n"
            "=== mysql ===\n"
            "LoadState=loaded\n"
            "ActiveState=failed\n"
            "SubState=failed\n"
            "=== redis ===\n"
            "LoadState=not-found\n"
            "ActiveState=inactive\n"
            "SubState=dead\n"
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (0, mock_output, ""),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["nginx", "mysql", "redis"], global_v, record_v
        )
        assert result["nginx"] == "running"
        assert result["mysql"] == "failed/failed"
        assert result["redis"] == "not-found"
        # nginx is ok, so only mysql and redis violations
        assert len(global_v) == 2
        assert len(record_v) == 2

    def test_empty_output_all_services_unknown(self, monkeypatch):
        """Empty SSH output means all services are unknown."""
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (0, "", ""),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["nginx"], global_v, record_v
        )
        assert result == {"nginx": "unknown"}
        assert len(global_v) == 1

    def test_partial_output_with_blank_lines(self, monkeypatch):
        """Output with blank lines and whitespace is parsed correctly."""
        mock_output = (
            "\n"
            "=== nginx ===\n"
            "  LoadState=loaded  \n"
            "  ActiveState=active  \n"
            "  SubState=running  \n"
            "\n"
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit._run_ssh",
            lambda alias, cmds: (0, mock_output, ""),
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = _check_systemd_services(
            "srv", "server1", ["nginx"], global_v, record_v
        )
        assert result == {"nginx": "running"}
        assert global_v == []


# ---------------------------------------------------------------------------
# HTTP endpoint health check tests (lines 1108-1171)
# ---------------------------------------------------------------------------


class TestHTTPEndpointHealthCheck:
    """Tests for HTTP endpoint health check in check_server."""

    def _make_server_with_http(self, endpoints):
        """Helper to create a server config with HTTP endpoints."""
        return {
            "name": "test-server",
            "host": "192.168.1.1",
            "ssh_alias": None,
            "checks": {
                "ssh": False,
                "http_endpoints": endpoints,
            },
        }

    def test_http_endpoint_success(self, monkeypatch):
        """HTTP endpoint returns expected status code, no violation."""
        mock_result = MagicMock()
        mock_result.stdout = "200"
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            lambda *a, **kw: mock_result,
        )
        server = self._make_server_with_http([
            {"url": "http://example.com/health", "name": "api", "expected_status": 200}
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"]["api"]["status"] == 200
        assert record["http_endpoints"]["api"]["ok"] is True
        assert global_v == []

    def test_http_endpoint_timeout(self, monkeypatch):
        """HTTP endpoint timeout triggers critical violation."""
        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="curl", timeout=7)

        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            raise_timeout,
        )
        server = self._make_server_with_http([
            {"url": "http://example.com/slow", "name": "slow-api"}
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"]["slow-api"]["status"] == -2
        assert record["http_endpoints"]["slow-api"]["ok"] is False
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "critical"
        assert "超时" in global_v[0]["detail"]

    def test_http_endpoint_curl_not_found(self, monkeypatch):
        """curl not installed triggers critical violation."""
        def raise_file_not_found(*a, **kw):
            raise FileNotFoundError("curl")

        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            raise_file_not_found,
        )
        server = self._make_server_with_http([
            {"url": "http://example.com/health", "name": "api"}
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"]["api"]["status"] == -1
        assert record["http_endpoints"]["api"]["ok"] is False
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "critical"
        assert "连接失败" in global_v[0]["detail"]

    def test_http_endpoint_empty_stdout(self, monkeypatch):
        """Empty stdout from curl triggers critical violation."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            lambda *a, **kw: mock_result,
        )
        server = self._make_server_with_http([
            {"url": "http://example.com/health", "name": "api"}
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"]["api"]["status"] == 0
        assert record["http_endpoints"]["api"]["ok"] is False
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "critical"

    def test_http_endpoint_non_numeric_stdout(self, monkeypatch):
        """Non-numeric stdout triggers critical violation."""
        mock_result = MagicMock()
        mock_result.stdout = "not-a-number"
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            lambda *a, **kw: mock_result,
        )
        server = self._make_server_with_http([
            {"url": "http://example.com/health", "name": "api"}
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"]["api"]["status"] == 0
        assert record["http_endpoints"]["api"]["ok"] is False
        assert len(global_v) == 1

    def test_http_endpoint_status_mismatch(self, monkeypatch):
        """HTTP status code != expected triggers warning violation."""
        mock_result = MagicMock()
        mock_result.stdout = "500"
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            lambda *a, **kw: mock_result,
        )
        server = self._make_server_with_http([
            {"url": "http://example.com/health", "name": "api", "expected_status": 200}
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"]["api"]["status"] == 500
        assert record["http_endpoints"]["api"]["ok"] is False
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "warning"
        assert "500" in global_v[0]["detail"]

    def test_http_endpoint_uses_url_as_name_fallback(self, monkeypatch):
        """When name is missing, URL is used as endpoint name."""
        mock_result = MagicMock()
        mock_result.stdout = "200"
        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            lambda *a, **kw: mock_result,
        )
        server = self._make_server_with_http([
            {"url": "http://example.com/health"}
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        # Name should be the URL when not provided
        assert "http://example.com/health" in record["http_endpoints"]

    def test_http_endpoint_skips_non_dict(self, monkeypatch):
        """Non-dict entries in http_endpoints is skipped."""
        server = self._make_server_with_http(["not-a-dict", 123])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"] == {}
        assert global_v == []

    def test_http_endpoint_skips_missing_url(self, monkeypatch):
        """Endpoint without URL is skipped."""
        server = self._make_server_with_http([{"name": "no-url"}])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"] == {}
        assert global_v == []

    def test_http_endpoint_multiple_endpoints(self, monkeypatch):
        """Multiple HTTP endpoints are checked independently."""
        call_count = [0]

        def mock_subprocess_run(*a, **kw):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.stdout = "200"
            else:
                mock_result.stdout = "404"
            return mock_result

        monkeypatch.setattr(
            "memory_core.tools.daily_kb_audit.subprocess.run",
            mock_subprocess_run,
        )
        server = self._make_server_with_http([
            {"url": "http://api.example.com", "name": "api", "expected_status": 200},
            {"url": "http://web.example.com", "name": "web", "expected_status": 200},
        ])
        global_v: list[dict] = []
        record = check_server(server, global_v)
        assert record["http_endpoints"]["api"]["status"] == 200
        assert record["http_endpoints"]["api"]["ok"] is True
        assert record["http_endpoints"]["web"]["status"] == 404
        assert record["http_endpoints"]["web"]["ok"] is False
        assert len(global_v) == 1
        assert global_v[0]["severity"] == "warning"
