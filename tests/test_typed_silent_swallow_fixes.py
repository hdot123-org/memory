"""Regression tests for typed exception silent-swallow fixes (INFRA-262).

These are static source-inspection tests (NOT runtime tests). They verify that
the 8 typed-exception silent-swallow instances fixed in INFRA-262 now surface
failures with ``logger.warning(...)`` and ``print(..., file=sys.stderr)`` instead
of silently using ``pass``.

Pattern follows ``tests/test_code_hygiene_audit_silent_swallow.py``:
read the source, locate the relevant except block, assert observability calls
are present.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _read_source(rel_path: str) -> str:
    """Read a source file from the repo root."""
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _except_block(content: str, needle: str, window: int = 400) -> str:
    """Extract a window of source around the first occurrence of ``needle``.

    The window is large enough to capture the except header and its body.
    """
    pos = content.find(needle)
    assert pos != -1, f"Expected to find '{needle}' in source"
    return content[pos : pos + window]


def _assert_has_warning_and_stderr(content: str, needle: str, window: int = 400) -> None:
    """Shared assertion: except block contains warning and stderr fallback.

    This helper eliminates duplication across test classes that verify
    the INFRA-262 fixes emit logger.warning and sys.stderr fallback.
    """
    block = _except_block(content, needle, window)
    assert "warning" in block.lower(), (
        "except block must emit a logger.warning"
    )
    assert "sys.stderr" in block, (
        "except block must have stderr fallback"
    )


# ---------------------------------------------------------------------------
# memory_hook_schema.py — audit log write OSError
# ---------------------------------------------------------------------------


class TestMemoryHookSchemaAuditLog:
    """memory_hook_schema.py: audit log write OSError now warns."""

    PATH = "memory_core/tools/memory_hook_schema.py"

    def test_no_silent_pass(self):
        content = _read_source(self.PATH)
        block = _except_block(content, "except OSError as exc")
        assert "pass" not in block.split("\n")[1], (
            "audit log write except must not use bare pass (silent swallow)"
        )

    def test_has_warning(self):
        content = _read_source(self.PATH)
        block = _except_block(content, "except OSError as exc")
        assert "warning" in block.lower(), (
            "audit log write except must emit a logger.warning"
        )

    def test_has_stderr_fallback(self):
        content = _read_source(self.PATH)
        block = _except_block(content, "except OSError as exc")
        assert "sys.stderr" in block, (
            "audit log write except must have stderr fallback"
        )

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except OSError as exc" in content, (
            "audit log write except must bind the exception as exc"
        )


# ---------------------------------------------------------------------------
# memory_hook_gateway.py — sync status file write OSError
# ---------------------------------------------------------------------------


class TestGatewaySyncStatusWrite:
    """memory_hook_gateway.py: sync status write OSError now warns."""

    PATH = "memory_core/tools/memory_hook_gateway.py"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        # The sync status write is identified by its context: write_text + OSError
        pos = content.find('status_file.write_text(json.dumps(status')
        assert pos != -1
        block = content[pos : pos + 300]
        assert "except OSError as exc" in block

    def test_has_warning_and_stderr(self):
        content = _read_source(self.PATH)
        _assert_has_warning_and_stderr(
            content, 'status_file.write_text(json.dumps(status', window=400
        )


# ---------------------------------------------------------------------------
# memory_hook_gateway.py — payload parse (JSONDecodeError, ValueError)
# ---------------------------------------------------------------------------


class TestGatewayPayloadParse:
    """memory_hook_gateway.py: payload parse except now warns."""

    PATH = "memory_core/tools/memory_hook_gateway.py"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        pos = content.find("payload_dict = json.loads(raw_payload)")
        assert pos != -1
        block = content[pos : pos + 300]
        assert "except (json.JSONDecodeError, ValueError) as exc" in block

    def test_has_warning_and_stderr(self):
        content = _read_source(self.PATH)
        _assert_has_warning_and_stderr(
            content, "payload_dict = json.loads(raw_payload)", window=400
        )


# ---------------------------------------------------------------------------
# session_end_logger.py — stdin payload read (JSONDecodeError, OSError)
# ---------------------------------------------------------------------------


class TestSessionEndLoggerStdinPayload:
    """session_end_logger.py: stdin payload read except now warns."""

    PATH = "memory_core/tools/session_end_logger.py"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (json.JSONDecodeError, OSError) as exc" in content

    def test_has_warning_and_stderr(self):
        content = _read_source(self.PATH)
        _assert_has_warning_and_stderr(
            content, "except (json.JSONDecodeError, OSError) as exc", window=200
        )


# ---------------------------------------------------------------------------
# telemetry_bridge.py — path sanitization (OSError, ValueError)
# ---------------------------------------------------------------------------


class TestTelemetryPathSanitization:
    """telemetry_bridge.py: path sanitization except now warns (privacy)."""

    PATH = "memory_core/tools/telemetry_bridge.py"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (OSError, ValueError) as exc" in content

    def test_has_warning_and_stderr(self):
        content = _read_source(self.PATH)
        _assert_has_warning_and_stderr(
            content, "except (OSError, ValueError) as exc", window=250
        )

    def test_mentions_sanitization(self):
        """Warning should mention path sanitization (privacy concern)."""
        content = _read_source(self.PATH)
        pos = content.find("except (OSError, ValueError) as exc")
        block = content[pos : pos + 300]
        assert "sanitiz" in block.lower(), (
            "warning should mention sanitization since raw paths may leak to telemetry"
        )


# ---------------------------------------------------------------------------
# hook_event_stats.py — lifecycle index read (JSONDecodeError, OSError)
# ---------------------------------------------------------------------------


class TestHookEventStatsLifecycleIndex:
    """hook_event_stats.py: lifecycle index read except now warns."""

    PATH = "memory_core/tools/hook_event_stats.py"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (json.JSONDecodeError, OSError) as exc" in content

    def test_has_warning_and_stderr(self):
        content = _read_source(self.PATH)
        _assert_has_warning_and_stderr(
            content, "except (json.JSONDecodeError, OSError) as exc"
        )


# ---------------------------------------------------------------------------
# daily_summary_generator.py — lifecycle index read (JSONDecodeError, OSError)
# ---------------------------------------------------------------------------


class TestDailySummaryLifecycleIndex:
    """daily_summary_generator.py: lifecycle index read except now warns."""

    PATH = "memory_core/tools/daily_summary_generator.py"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (json.JSONDecodeError, OSError) as exc" in content

    def test_has_warning_and_stderr(self):
        content = _read_source(self.PATH)
        _assert_has_warning_and_stderr(
            content, "except (json.JSONDecodeError, OSError) as exc"
        )


# ---------------------------------------------------------------------------
# error_pattern_detector.py — git root detection (SubprocessError, FileNotFoundError)
# ---------------------------------------------------------------------------


class TestErrorPatternDetectorGitRoot:
    """error_pattern_detector.py: git root detection except now warns."""

    PATH = "memory_core/tools/error_pattern_detector.py"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (subprocess.SubprocessError, FileNotFoundError) as exc" in content

    def test_has_warning_and_stderr(self):
        content = _read_source(self.PATH)
        _assert_has_warning_and_stderr(
            content, "except (subprocess.SubprocessError, FileNotFoundError) as exc"
        )


# ---------------------------------------------------------------------------
# Wholesale guards: no typed-exception bare-pass remains at fixed locations
# ---------------------------------------------------------------------------

# NOTE: Only per-location tests above are used. File-wide pattern scans were
# removed because some files contain other typed-exception catches that were
# intentionally left as-is (lower severity, out of INFRA-262 scope).
