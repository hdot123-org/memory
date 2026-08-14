"""Shared source-slicing helpers for silent-swallow code-inspection tests (INFRA-283).

Historically every ``tests/test_*_silent_swallow.py`` module carried its own
copy of these helpers, and the near-identical same-name copies repeatedly
triggered the CODE_HYGIENE_DUPLICATE_BLOCK finding (90-100% AST similarity
across files). The copies are consolidated into this module; test modules
import them under their historical local names via aliased imports, so
existing call sites stay unchanged.

Semantics:
- ``function_body`` stops at the next top-level ``def`` OR ``class``.
- ``top_level_function_body`` stops at the next column-0 ``def`` only.
- ``except_positions`` matches every ``except Exception`` clause (bare and
  binding forms alike).
- ``bare_except_positions`` matches only the bare ``except Exception:`` form.
"""


def function_body(content: str, name: str) -> str:
    """Slice a top-level function's source from its ``def`` to the next top-level def/class."""
    start = content.index(f"def {name}")
    next_def = content.find("\ndef ", start + 1)
    next_class = content.find("\nclass ", start + 1)
    candidates = [p for p in (next_def, next_class) if p != -1]
    end = min(candidates) if candidates else len(content)
    return content[start:end]


def top_level_function_body(content: str, name: str) -> str:
    """Slice a top-level function's source from its ``def`` to the next top-level ``def``.

    Matches top-level defs only: a column-0 ``def`` is preceded by a bare
    newline, while a nested def is preceded by newline+indentation, so the
    ``\\ndef`` search will not stop inside the target function.
    """
    start = content.index(f"def {name}")
    next_def = content.index("\ndef ", start + 1)
    return content[start:next_def]


def except_positions(body: str) -> list[int]:
    """Return character offsets of every ``except Exception`` clause in body.

    Matches the bare form (``except Exception:``) and the binding form
    (``except Exception as e:``) alike.
    """
    return _find_all(body, "except Exception")


def bare_except_positions(body: str) -> list[int]:
    """Return character offsets of every bare ``except Exception:`` in body."""
    return _find_all(body, "except Exception:")


def _find_all(body: str, needle: str) -> list[int]:
    """Return character offsets of every occurrence of needle in body."""
    positions = []
    idx = 0
    while True:
        pos = body.find(needle, idx)
        if pos == -1:
            break
        positions.append(pos)
        idx = pos + len(needle)
    return positions
