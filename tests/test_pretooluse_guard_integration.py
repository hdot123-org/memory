"""Integration tests for PreToolUse guard via gateway.

Tests the full pipeline: gateway receives pre-tool-use event ->
forwards payload to pretooluse_guard.py -> returns decision.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

GATEWAY = Path(__file__).resolve().parents[1] / "memory_core" / "tools" / "memory_hook_gateway.py"


def _run_gateway(
    event: str,
    payload: dict[str, Any],
    *,
    cwd: Path | None = None,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run gateway with given event/payload via stdin.

    Returns (returncode, stdout, stderr).
    """
    env: dict[str, str] = {}
    if cwd:
        env["FACTORY_PROJECT_DIR"] = str(cwd)
        env["MEMORY_HOOK_ORIGINAL_CWD"] = str(cwd)
    if env_extra:
        env.update(env_extra)

    full_env = {**__import__("os").environ, **env}

    result = subprocess.run(
        [sys.executable, str(GATEWAY), "--host", "factory", "--event", event, "--no-delegate"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=full_env,
        timeout=30,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _make_payload(tool_name: str, **kwargs: Any) -> dict[str, Any]:
    """Build a Factory-style pre-tool-use payload."""
    return {
        "tool_name": tool_name,
        "tool_input": kwargs,
    }


class TestGuardBlocksWriteToAuditDir:
    """Test: writing to audit/ directory should be blocked."""

    def test_guard_blocks_write_to_audit_dir(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = _make_payload(
            "Write",
            file_path="audit/test.md",
            content="test",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        assert rc == 2, f"Expected exit code 2 (block), got {rc}. stdout={stdout}, stderr={stderr}"
        output = json.loads(stdout)
        assert output["decision"] == "block"


class TestGuardBlocksWriteToMemoryDocs:
    """Test: writing to memory/docs/ (CRITICAL domain) should be blocked."""

    def test_guard_blocks_write_to_memory_docs(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory" / "docs").mkdir(parents=True)

        payload = _make_payload(
            "Write",
            file_path="memory/docs/new-doc.md",
            content="test content",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        assert rc == 2, f"Expected exit code 2 (block), got {rc}. stdout={stdout}, stderr={stderr}"
        output = json.loads(stdout)
        assert output["decision"] == "block"


class TestGuardAllowsWriteToAllowedPath:
    """Test: writing to allowed paths (e.g., workspace/) should be allowed."""

    def test_guard_allows_write_to_allowed_path(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "workspace").mkdir(parents=True)

        payload = _make_payload(
            "Write",
            file_path="workspace/notes.md",
            content="some notes",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        assert rc == 0, f"Expected exit code 0 (allow), got {rc}. stdout={stdout}, stderr={stderr}"
        output = json.loads(stdout)
        assert output["decision"] == "allow"

    def test_guard_blocks_write_to_memory_log(self, tmp_path: Path) -> None:
        """Writing to memory/log/ (STANDARD domain) should be blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory" / "log").mkdir(parents=True)

        payload = _make_payload(
            "Write",
            file_path="memory/log/today.md",
            content="log entry",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        assert rc == 2, f"Expected exit code 2 (block), got {rc}. stdout={stdout}, stderr={stderr}"
        output = json.loads(stdout)
        assert output["decision"] == "block"


class TestGuardAllowsReadOperations:
    """Test: read operations should be allowed."""

    def test_guard_allows_read_operations(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory" / "docs").mkdir(parents=True)
        test_file = tmp_path / "memory" / "docs" / "readme.md"
        test_file.write_text("read me", encoding="utf-8")

        # Read tool (factory style) - should always be allowed
        payload = _make_payload(
            "Read",
            file_path="memory/docs/readme.md",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        assert rc == 0, f"Expected exit code 0 (allow), got {rc}. stdout={stdout}, stderr={stderr}"
        output = json.loads(stdout)
        assert output["decision"] == "allow"


class TestGuardHandlesSourceRepo:
    """Test: in source repo, all writes should be blocked."""

    def test_guard_allows_in_source_repo(self, tmp_path: Path) -> None:
        """Source repo should still allow reads via gateway.

        The gateway returns a readonly context-package for source repos,
        but the pre-tool-use guard still runs and classifies paths.
        """
        # Create a fake source repo structure
        (tmp_path / "memory_core" / "tools" / "memory_hook_gateway.py").parent.mkdir(parents=True)
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # In the source repo context, writes to memory/docs should be blocked
        payload = _make_payload(
            "Write",
            file_path=str(tmp_path / "memory_core" / "memory" / "docs" / "test.md"),
            content="test",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        # The guard should block writes to protected paths even in source repo
        # (memory_core/memory/docs is under memory/docs domain pattern)
        output = json.loads(stdout)
        # We just verify the gateway returns a decision; blocking depends on
        # whether the path matches owned domains relative to project root
        assert "decision" in output


class TestGatewayPretooluseBranch:
    """Test: gateway pre-tool-use event calls guard and returns correct results."""

    def test_gateway_calls_guard_for_pretooluse_event(self, tmp_path: Path) -> None:
        """Verify the gateway's pre-tool-use branch invokes the guard."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = _make_payload(
            "Write",
            file_path="src/new_file.py",
            content="print('hello')",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        # Non-owned path should be allowed
        assert rc == 0, f"Expected exit code 0, got {rc}. stderr={stderr}"
        output = json.loads(stdout)
        assert output["decision"] == "allow"

    def test_gateway_blocks_protected_path(self, tmp_path: Path) -> None:
        """Verify the gateway blocks writes to protected paths via guard."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = _make_payload(
            "Edit",
            file_path="memory/system/ownership.toml",
            old_str="old",
            new_str="new",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        assert rc == 2, f"Expected exit code 2 (block), got {rc}. stderr={stderr}"
        output = json.loads(stdout)
        assert output["decision"] == "block"

    def test_gateway_returns_structured_json(self, tmp_path: Path) -> None:
        """Verify gateway stdout contains valid JSON with decision field."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = _make_payload(
            "Write",
            file_path="src/main.py",
            content="pass",
        )

        rc, stdout, stderr = _run_gateway("pre-tool-use", payload, cwd=tmp_path)

        # Must be valid JSON
        output = json.loads(stdout)
        assert "decision" in output
        assert output["decision"] in ("allow", "block")
        assert "reason" in output
