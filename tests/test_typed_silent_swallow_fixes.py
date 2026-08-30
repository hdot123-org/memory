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


def _assert_warning_and_stderr(rel_path: str, needle: str, window: int = 400) -> None:
    """Assert the except block at *needle* warns and falls back to stderr.

    Shared checker for the ``test_has_warning_and_stderr`` family
    (CODE_HYGIENE_DUPLICATE_BLOCK fix, INFRA-333).
    """
    block = _except_block(_read_source(rel_path), needle, window)
    assert "warning" in block.lower(), f"{rel_path}: except block at {needle!r} must emit a logger.warning"
    assert "sys.stderr" in block, f"{rel_path}: except block at {needle!r} must have a stderr fallback"


def _assert_binds_exception(rel_path: str, needle: str, expected_except: str, window: int = 300) -> None:
    """Assert the except block near *needle* binds the expected exception type.

    Shared checker for the ``test_binds_exception`` family
    (CODE_HYGIENE_DUPLICATE_BLOCK fix, INFRA-340 follow-up / #719).
    """
    content = _read_source(rel_path)
    block = _except_block(content, needle, window)
    assert expected_except in block, f"{rel_path}: except block near {needle!r} must contain {expected_except!r}"


class _WarnsAndStderrMixin:
    """参数化 mixin：except 分支应记录 warning 且写 stderr。

    消除 7 处结构相同的 test_has_warning_and_stderr 方法定义
    (CODE_HYGIENE_DUPLICATE_BLOCK, INFRA-335)。
    """

    PATH: str
    WARN_NEEDLE: str
    WARN_WINDOW: int = 400

    def test_has_warning_and_stderr(self) -> None:
        _assert_warning_and_stderr(self.PATH, self.WARN_NEEDLE, self.WARN_WINDOW)


# ---------------------------------------------------------------------------
# memory_hook_schema.py — audit log write OSError
# ---------------------------------------------------------------------------


class TestMemoryHookSchemaAuditLog:
    """memory_hook_schema.py: audit log write OSError now warns."""

    PATH = "memory_core/tools/memory_hook_schema.py"

    def test_no_silent_pass(self):
        content = _read_source(self.PATH)
        block = _except_block(content, "except OSError as exc")
        assert "pass" not in block.split("\n")[1], "audit log write except must not use bare pass (silent swallow)"

    def test_has_warning(self):
        content = _read_source(self.PATH)
        block = _except_block(content, "except OSError as exc")
        assert "warning" in block.lower(), "audit log write except must emit a logger.warning"

    def test_has_stderr_fallback(self):
        content = _read_source(self.PATH)
        block = _except_block(content, "except OSError as exc")
        assert "sys.stderr" in block, "audit log write except must have stderr fallback"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except OSError as exc" in content, "audit log write except must bind the exception as exc"


# ---------------------------------------------------------------------------
# memory_hook_gateway.py — sync status file write OSError
# ---------------------------------------------------------------------------


class TestGatewaySyncStatusWrite(_WarnsAndStderrMixin):
    """gateway telemetry: sync status write OSError now warns.

    M3 gateway split: _write_sync_status lives in _gateway_policy? No —
    it lives in _gateway_telemetry.py after the M3 split.
    """

    PATH = "memory_core/tools/_gateway_telemetry.py"
    WARN_NEEDLE = "f.write(json.dumps(status"

    def test_binds_exception(self):
        _assert_binds_exception(
            self.PATH,
            "f.write(json.dumps(status",
            "except OSError as exc",
        )


# ---------------------------------------------------------------------------
# memory_hook_gateway.py — payload parse (JSONDecodeError, ValueError)
# ---------------------------------------------------------------------------


class TestGatewayPayloadParse(_WarnsAndStderrMixin):
    """gateway handlers: payload parse except now warns.

    M3 gateway split: the payload-parse fallback lives in
    _gateway_handlers._handle_pretooluse_guard.
    """

    PATH = "memory_core/tools/_gateway_handlers.py"
    WARN_NEEDLE = "payload_dict = json.loads(raw_payload)"

    def test_binds_exception(self):
        _assert_binds_exception(
            self.PATH,
            "payload_dict = json.loads(raw_payload)",
            "except (json.JSONDecodeError, ValueError) as exc",
        )


# ---------------------------------------------------------------------------
# session_end_logger.py — stdin payload read (JSONDecodeError, OSError)
# ---------------------------------------------------------------------------


class TestSessionEndLoggerStdinPayload(_WarnsAndStderrMixin):
    """session_end_logger.py: stdin payload read except now warns."""

    PATH = "memory_core/tools/session_end_logger.py"
    WARN_NEEDLE = "except (json.JSONDecodeError, OSError) as exc"
    WARN_WINDOW = 200

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (json.JSONDecodeError, OSError) as exc" in content


# ---------------------------------------------------------------------------
# telemetry_bridge.py — path sanitization (OSError, ValueError)
# ---------------------------------------------------------------------------


class TestTelemetryPathSanitization(_WarnsAndStderrMixin):
    """telemetry_bridge.py: path sanitization except now warns (privacy)."""

    PATH = "memory_core/tools/telemetry_bridge.py"
    WARN_NEEDLE = "except (OSError, ValueError) as exc"
    WARN_WINDOW = 250

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (OSError, ValueError) as exc" in content

    def test_mentions_sanitization(self):
        """Warning should mention path sanitization (privacy concern)."""
        content = _read_source(self.PATH)
        pos = content.find("except (OSError, ValueError) as exc")
        block = content[pos : pos + 300]
        assert "sanitiz" in block.lower(), "warning should mention sanitization since raw paths may leak to telemetry"


# ---------------------------------------------------------------------------
# hook_event_stats.py — lifecycle index read (JSONDecodeError, OSError)
# ---------------------------------------------------------------------------


class TestHookEventStatsLifecycleIndex(_WarnsAndStderrMixin):
    """hook_event_stats.py: lifecycle index read except now warns."""

    PATH = "memory_core/tools/hook_event_stats.py"
    WARN_NEEDLE = "except (json.JSONDecodeError, OSError) as exc"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (json.JSONDecodeError, OSError) as exc" in content


# ---------------------------------------------------------------------------
# daily_summary_generator.py — lifecycle index read (JSONDecodeError, OSError)
# ---------------------------------------------------------------------------


class TestDailySummaryLifecycleIndex(_WarnsAndStderrMixin):
    """daily_summary_generator.py: lifecycle index read except now warns."""

    PATH = "memory_core/tools/daily_summary_generator.py"
    WARN_NEEDLE = "except (json.JSONDecodeError, OSError) as exc"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (json.JSONDecodeError, OSError) as exc" in content


# ---------------------------------------------------------------------------
# error_pattern_detector.py — git root detection (SubprocessError, FileNotFoundError)
# ---------------------------------------------------------------------------


class TestErrorPatternDetectorGitRoot(_WarnsAndStderrMixin):
    """error_pattern_detector.py: git root detection except now warns."""

    PATH = "memory_core/tools/error_pattern_detector.py"
    WARN_NEEDLE = "except (subprocess.SubprocessError, FileNotFoundError) as exc"

    def test_binds_exception(self):
        content = _read_source(self.PATH)
        assert "except (subprocess.SubprocessError, FileNotFoundError) as exc" in content


# ---------------------------------------------------------------------------
# Wholesale guards: no typed-exception bare-pass remains at fixed locations
# ---------------------------------------------------------------------------

# NOTE: Only per-location tests above are used. File-wide pattern scans were
# removed because some files contain other typed-exception catches that were
# intentionally left as-is (lower severity, out of INFRA-262 scope).
