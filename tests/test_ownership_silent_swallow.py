"""Regression tests for silent exception swallow fix in ownership.py (PR #569).

Bug: Three except blocks in ownership.py used bare `except Exception: pass`,
silently swallowing parse/detection failures with zero observability:
  1. is_memory_core_source_repo — git root detection failure (~L774)
  2. load_memory_ownership — ownership.toml parse failure (~L620)
  3. load_memory_ownership — ownership.json parse failure (~L634)

Fix: Each except block now calls logger.debug(..., exc_info=True) while still
returning its default value (graceful degradation unchanged).

These are code-inspection tests (NOT runtime tests) because the except blocks
live in fallback paths (git binary missing, malformed toml/json) that are hard
to trigger reliably and portably. They follow the TestOsExitRegression pattern
in tests/test_sigint_handling.py: read the source, slice the relevant scope,
and assert the observability call is present.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OWNERSHIP_PATH = REPO_ROOT / "memory_core" / "ownership.py"


def _function_body(content: str, name: str) -> str:
    """Slice a top-level function's source from its `def` to the next top-level `def`.

    Matches top-level defs only: a column-0 `def ` is preceded by a bare
    newline, while a nested def is preceded by newline+indentation, so the
    `\ndef ` search will not stop inside the target function.
    """
    start = content.index(f"def {name}")
    next_def = content.index("\ndef ", start + 1)
    return content[start:next_def]


def _except_positions(body: str) -> list[int]:
    """Return character offsets of every `except Exception:` in body."""
    positions = []
    needle = "except Exception:"
    idx = 0
    while True:
        pos = body.find(needle, idx)
        if pos == -1:
            break
        positions.append(pos)
        idx = pos + len(needle)
    return positions


class TestIsMemoryCoreSourceRepoSilentSwallow:
    """Regression guard: is_memory_core_source_repo except block logs at debug (PR #569).

    Before PR #569 the git-root-detection except was `except Exception: pass`,
    hiding detection failures. The fix preserves graceful degradation
    (return False) but adds debug-level observability with exc_info.
    """

    def test_except_block_logs_with_exc_info(self):
        """The git-root-detection except block must call logger.debug(exc_info=True)."""
        content = OWNERSHIP_PATH.read_text()
        func_body = _function_body(content, "is_memory_core_source_repo")
        positions = _except_positions(func_body)
        assert len(positions) >= 1, (
            "is_memory_core_source_repo must have an except Exception block"
        )
        except_block = func_body[positions[0]:positions[0] + 300]
        assert "logger.debug" in except_block, (
            "is_memory_core_source_repo except block must call logger.debug — "
            "bare pass silently swallows git root detection failures"
        )
        assert "exc_info=True" in except_block, (
            "logger.debug must include exc_info=True so the traceback is captured"
        )

    def test_no_bare_pass_in_function_scope(self):
        """The function must not contain a bare `except Exception: pass` swallow."""
        content = OWNERSHIP_PATH.read_text()
        # is_memory_core_source_repo's except is at 4-space indent, so a bare
        # pass regression would render as 8-space-indented pass.
        assert "except Exception:\n        pass" not in content


class TestLoadMemoryOwnershipSilentSwallow:
    """Regression guard: load_memory_ownership except blocks log at debug (PR #569).

    Before PR #569 both parse-fallback excepts were
    `except Exception: pass`, hiding malformed ownership.toml/ownership.json
    failures. The fix preserves graceful degradation (return defaults) but
    adds debug-level observability with exc_info.
    """

    def test_both_except_blocks_log_with_exc_info(self):
        """Both the toml-parse and json-parse except blocks must call logger.debug(exc_info=True)."""
        content = OWNERSHIP_PATH.read_text()
        func_body = _function_body(content, "load_memory_ownership")
        positions = _except_positions(func_body)
        assert len(positions) >= 2, (
            f"load_memory_ownership must have at least 2 except Exception "
            f"blocks (toml parse + json parse), found {len(positions)}"
        )
        for pos in positions:
            except_block = func_body[pos:pos + 300]
            assert "logger.debug" in except_block, (
                "load_memory_ownership except block must call logger.debug — "
                "bare pass silently swallows ownership parse failures"
            )
            assert "exc_info=True" in except_block, (
                "logger.debug must include exc_info=True so the traceback is captured"
            )

    def test_toml_except_block_present(self):
        """Guard the toml-parse except specifically (distinct from the json one)."""
        content = OWNERSHIP_PATH.read_text()
        func_body = _function_body(content, "load_memory_ownership")
        toml_idx = func_body.index("ownership.toml parse failed")
        # logger.debug( precedes the message; exc_info=True follows it.
        window = func_body[max(0, toml_idx - 80):toml_idx + 200]
        assert "logger.debug" in window
        assert "exc_info=True" in window

    def test_json_except_block_present(self):
        """Guard the json-parse except specifically (distinct from the toml one)."""
        content = OWNERSHIP_PATH.read_text()
        func_body = _function_body(content, "load_memory_ownership")
        json_idx = func_body.index("ownership.json parse failed")
        # logger.debug( precedes the message; exc_info=True follows it.
        window = func_body[max(0, json_idx - 80):json_idx + 200]
        assert "logger.debug" in window
        assert "exc_info=True" in window

    def test_no_bare_pass_in_function_scope(self):
        """The function must not contain a bare `except Exception: pass` swallow."""
        content = OWNERSHIP_PATH.read_text()
        # load_memory_ownership's excepts are at 8-space indent, so a bare
        # pass regression would render as 12-space-indented pass.
        assert "except Exception:\n            pass" not in content


class TestNoSilentSwallowAnywhere:
    """Whole-file guard: no bare `except Exception: pass` swallow remains in ownership.py."""

    def test_no_bare_silent_swallow_pattern(self):
        """No bare `except Exception:` followed only by `pass` at any nesting level.

        Covers both indent levels used in ownership.py:
          - 4-space except (8-space pass): is_memory_core_source_repo
          - 8-space except (12-space pass): load_memory_ownership
        """
        content = OWNERSHIP_PATH.read_text()
        assert "except Exception:\n        pass" not in content, (
            "ownership.py must not contain a 4-space-indented bare "
            "`except Exception: pass` (silent swallow)"
        )
        assert "except Exception:\n            pass" not in content, (
            "ownership.py must not contain an 8-space-indented bare "
            "`except Exception: pass` (silent swallow)"
        )
