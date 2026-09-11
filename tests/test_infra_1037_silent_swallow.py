"""Regression tests for INFRA-1037: SILENT_SWALLOW fixes (batch 3).

Bug: Eight `except Exception: pass/continue/return` clauses silently swallowed
exceptions with zero observability. The fixes bind the exception and emit a
DEBUG-level log record with exc_info=True, preserving graceful-degradation
semantics while adding an audit trail.

Coverage follows the established INFRA-242 dual pattern:
  - Code-inspection tests: read source, slice function body, assert the
    observability call replaced the bare pass/continue/return.
"""

from pathlib import Path

from tests.silent_swallow_helpers import (
    bare_except_positions,
    except_positions,
    function_body,
)

BASE = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. evolution/extractor.py — MCP secret resolution (line ~106)
# ---------------------------------------------------------------------------


class TestExtractorMcpSecretSilentSwallow:
    """Regression guard: MCP secret resolution must log, not silently pass."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "evolution" / "extractor.py").read_text(encoding="utf-8")

    def test_mcp_secret_except_not_bare(self):
        """The MCP secret resolver except must not be a bare swallow."""
        content = self._read_source()
        # Find the resolve_api_key function body
        func_body = function_body(content, "resolve_api_key")
        assert not bare_except_positions(func_body), (
            "resolve_api_key must not contain a bare `except Exception:` clause — "
            "the MCP secret resolution path needs an audit trail (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_mcp_secret_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        func_body = function_body(content, "resolve_api_key")
        positions = except_positions(func_body)
        # Find the MCP secret resolution except (contains McpSecretResolver)
        mcp_except_idx = None
        for pos in positions:
            context = func_body[max(0, pos - 200) : pos + 200]
            if "McpSecretResolver" in context or "mcp" in context.lower():
                mcp_except_idx = pos
                break
        assert mcp_except_idx is not None, "could not find MCP secret resolution except block"
        except_block = func_body[mcp_except_idx : mcp_except_idx + 300]
        assert "as exc" in except_block, (
            "except clause must bind the exception (`as exc`) for the log record"
        )
        assert "logging.getLogger" in except_block or ".debug(" in except_block, (
            "except block must emit a logging record at DEBUG level"
        )


# ---------------------------------------------------------------------------
# 2. tools/_gateway_config.py — config parsing during conflict detection
# ---------------------------------------------------------------------------


class TestGatewayConfigParsingSilentSwallow:
    """Regression guard: config parsing during conflict detection must log."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "tools" / "_gateway_config.py").read_text(encoding="utf-8")

    def test_config_parsing_except_not_bare(self):
        """The config parsing except must not be a bare swallow."""
        content = self._read_source()
        # The except is inside _resolve_repo_root_with_config (a nested try within a larger function)
        # Check the whole file for bare except patterns with "pass  # Don't crash"
        assert "except Exception:\n                    pass" not in content, (
            "_gateway_config.py: config parsing must not use bare `except Exception: pass` — "
            "bind exception and log at DEBUG (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_config_parsing_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        assert "except Exception as exc:" in content, (
            "config parsing except must bind the exception"
        )
        # Verify the debug log is near the except block
        idx = content.find("except Exception as exc:\n                    _logger.debug")
        assert idx >= 0, (
            "config parsing except must log at DEBUG level with _logger.debug"
        )


# ---------------------------------------------------------------------------
# 3. tools/mcp_server.py — source_refs merge in pending duplicates
# ---------------------------------------------------------------------------


class TestMcpServerMergeSilentSwallow:
    """Regression guard: source_refs merge must log, not silently pass."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "tools" / "mcp_server.py").read_text(encoding="utf-8")

    def test_merge_except_not_bare(self):
        """The source_refs merge except must not be a bare swallow."""
        content = self._read_source()
        assert "except Exception:\n                        pass" not in content, (
            "mcp_server.py: source_refs merge must not use bare `except Exception: pass` — "
            "bind exception and log at DEBUG (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_merge_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        assert "except Exception as exc:" in content
        # Verify debug logging is present near the merge code
        assert "logging.getLogger(__name__).debug" in content or "_logger.debug" in content, (
            "source_refs merge except must emit a DEBUG log record"
        )


# ---------------------------------------------------------------------------
# 4. tools/session_end_logger.py — gateway root resolution fallback
# ---------------------------------------------------------------------------


class TestSessionEndLoggerRootResolveSilentSwallow:
    """Regression guard: gateway root resolution fallback must log."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "tools" / "session_end_logger.py").read_text(encoding="utf-8")

    def test_root_resolve_except_not_bare(self):
        """The gateway root resolution except must not be a bare swallow."""
        content = self._read_source()
        func_body = function_body(content, "_resolve_project_root")
        assert not bare_except_positions(func_body), (
            "_resolve_project_root must not contain a bare `except Exception:` clause — "
            "the gateway root resolution fallback needs an audit trail (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_root_resolve_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        func_body = function_body(content, "_resolve_project_root")
        positions = except_positions(func_body)
        assert positions, "_resolve_project_root must have an except Exception block"
        except_block = func_body[positions[0] : positions[0] + 400]
        assert "as exc" in except_block, "except clause must bind the exception"
        assert "logger.debug(" in except_block or ".debug(" in except_block, (
            "except block must emit a DEBUG-level log record"
        )


# ---------------------------------------------------------------------------
# 5. tools/evidence_ref_validator.py — KB file read
# ---------------------------------------------------------------------------


class TestEvidenceRefValidatorSilentSwallow:
    """Regression guard: KB file read must log, not silently continue."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "tools" / "evidence_ref_validator.py").read_text(encoding="utf-8")

    def test_kb_read_except_not_bare(self):
        """The KB file read except must not be a bare swallow."""
        content = self._read_source()
        func_body = function_body(content, "validate_evidence_refs")
        assert not bare_except_positions(func_body), (
            "validate_evidence_refs must not contain a bare `except Exception:` clause — "
            "KB file read failures need an audit trail (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_kb_read_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        func_body = function_body(content, "validate_evidence_refs")
        positions = except_positions(func_body)
        assert positions, "validate_evidence_refs must have an except Exception block"
        except_block = func_body[positions[0] : positions[0] + 400]
        assert "as exc" in except_block, "except clause must bind the exception"
        assert "logging.getLogger" in except_block or ".debug(" in except_block, (
            "except block must emit a DEBUG-level log record"
        )


# ---------------------------------------------------------------------------
# 6. tools/validate_project_memory.py — pollution check file read
# ---------------------------------------------------------------------------


class TestValidateProjectMemorySilentSwallow:
    """Regression guard: pollution check file read must log, not silently continue."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "tools" / "validate_project_memory.py").read_text(encoding="utf-8")

    def test_pollution_check_except_not_bare(self):
        """The pollution check file read except must not be a bare swallow."""
        content = self._read_source()
        func_body = function_body(content, "_check_pollution")
        assert not bare_except_positions(func_body), (
            "_check_pollution must not contain a bare `except Exception:` clause — "
            "file read failures need an audit trail (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_pollution_check_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        func_body = function_body(content, "_check_pollution")
        positions = except_positions(func_body)
        assert positions, "_check_pollution must have an except Exception block"
        except_block = func_body[positions[0] : positions[0] + 400]
        assert "as exc" in except_block, "except clause must bind the exception"
        assert "logging.getLogger" in except_block or ".debug(" in except_block, (
            "except block must emit a DEBUG-level log record"
        )


# ---------------------------------------------------------------------------
# 7. tools/daily_summary_generator.py — is_true_project_root
# ---------------------------------------------------------------------------


class TestDailySummaryGeneratorSilentSwallow:
    """Regression guard: _is_true_project_root must log, not silently return False."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "tools" / "daily_summary_generator.py").read_text(encoding="utf-8")

    def test_is_true_project_root_except_not_bare(self):
        """The _is_true_project_root except must not be a bare swallow."""
        content = self._read_source()
        func_body = function_body(content, "_is_true_project_root")
        assert not bare_except_positions(func_body), (
            "_is_true_project_root must not contain a bare `except Exception:` clause — "
            "root detection failures need an audit trail (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_is_true_project_root_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        func_body = function_body(content, "_is_true_project_root")
        positions = except_positions(func_body)
        assert positions, "_is_true_project_root must have an except Exception block"
        except_block = func_body[positions[0] : positions[0] + 400]
        assert "as exc" in except_block, "except clause must bind the exception"
        assert "logger.debug(" in except_block or ".debug(" in except_block, (
            "except block must emit a DEBUG-level log record"
        )


# ---------------------------------------------------------------------------
# 8. tools/error_logger.py — write_error_log
# ---------------------------------------------------------------------------


class TestErrorLoggerSilentSwallow:
    """Regression guard: write_error_log must log, not silently return False."""

    def _read_source(self) -> str:
        return (BASE / "memory_core" / "tools" / "error_logger.py").read_text(encoding="utf-8")

    def test_write_error_log_except_not_bare(self):
        """The write_error_log outer except must not be a bare swallow."""
        content = self._read_source()
        func_body = function_body(content, "write_error_log")
        assert not bare_except_positions(func_body), (
            "write_error_log must not contain a bare `except Exception:` clause — "
            "internal errors need an audit trail (SILENT_SWALLOW, INFRA-1037)"
        )

    def test_write_error_log_except_logs_debug(self):
        """The except block must bind the exception and log at DEBUG level."""
        content = self._read_source()
        func_body = function_body(content, "write_error_log")
        positions = except_positions(func_body)
        # Find the last except block (the outer catch-all)
        assert positions, "write_error_log must have an except Exception block"
        except_block = func_body[positions[-1] : positions[-1] + 400]
        assert "as exc" in except_block, "except clause must bind the exception"
        assert "logging.getLogger" in except_block or ".debug(" in except_block, (
            "except block must emit a DEBUG-level log record"
        )
