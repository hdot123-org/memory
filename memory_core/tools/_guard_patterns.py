#!/usr/bin/env python3.12
"""Guard pattern definitions extracted from pretooluse_guard.py.

Contains FORBIDDEN_SUFFIXES, FORBIDDEN_DIRS, and pre-compiled
regex patterns for command parsing in the tool-use guard.

Part of REF-001 strangler fig scaffold phase.
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# 文件类型黑名单常量
# ---------------------------------------------------------------------------

FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".sql",
    ".bak",
    ".sqlite",
    ".db",
    ".dump",
    ".sql.gz",
)

FORBIDDEN_DIRS: frozenset[str] = frozenset({"backups"})

# ---------------------------------------------------------------------------
# Pre-compiled regex patterns for command parsing
# ---------------------------------------------------------------------------

# mv / git mv
RE_MV = re.compile(r"^(?:git\s+)?mv\s+(.+)$", re.IGNORECASE)

# rm
RE_RM = re.compile(r"^rm\s+(?:-[a-zA-Z]+\s+)?(.+)$", re.IGNORECASE)

# cp — do NOT strip flags (needed for -t/--target-directory detection)
RE_CP = re.compile(r"^cp\s+(.+)$", re.IGNORECASE)

# rsync
RE_RSYNC = re.compile(r"^rsync\s+(?:-[a-zA-Z]+\s+)*(.+)$", re.IGNORECASE)

# mkdir
RE_MKDIR = re.compile(r"^mkdir\s+(?:-[a-zA-Z]+\s+)?(.+)$", re.IGNORECASE)

# touch
RE_TOUCH = re.compile(r"^touch\s+(?:-[a-zA-Z]+\s+)?(.+)$", re.IGNORECASE)

# python -c
RE_PYTHON_C = re.compile(
    r"^python\d*\s+(?:-[a-zA-Z]+\s+)*-c\s+['\"]?(.+)$",
    re.IGNORECASE | re.DOTALL,
)

# node -e
RE_NODE_E = re.compile(
    r"^node\s+(?:-[a-zA-Z]+\s+)*-e\s+['\"]?(.+)$",
    re.IGNORECASE | re.DOTALL,
)

# shell redirect (> >>) — used with findall() for multi-redirect coverage
RE_REDIRECT = re.compile(r"[12]?>[>]?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")

# tee
RE_TEE = re.compile(r".*tee\s+(?:-[a-zA-Z]+\s+)?([^|&;]+)", re.IGNORECASE)

# heredoc (cat << EOF)
RE_HEREDOC = re.compile(r".*cat\s+.*<<\s*\w+\s*>?\s*([^|&;]+)", re.IGNORECASE)

# dd (of=)
RE_DD = re.compile(r"^dd\s+.*of=['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE)

# install
RE_INSTALL = re.compile(r"^install\s+(?:-[a-zA-Z]+\s+)*(.+)$", re.IGNORECASE)

# ln / symlink
RE_LN = re.compile(r"^ln\s+(?:-[a-zA-Z]+\s+)*(.+)$", re.IGNORECASE)

# open() calls in python -c code
RE_PYTHON_OPEN = re.compile(r"open\s*\(\s*['\"]([^'\"]+)['\"]")

# pathlib Path() calls in python -c code
RE_PYTHON_PATH = re.compile(r"Path\s*\(\s*['\"]([^'\"]+)['\"]\)")

# fs.writeFileSync / writeFile / appendFileSync / appendFile in node -e
RE_NODE_FS_WRITE = re.compile(r"(?:writeFileSync|writeFile|appendFileSync|appendFile)\s*\(\s*['\"]([^'\"]+)['\"]")

# require('fs').writeFileSync patterns in node -e
RE_NODE_REQUIRE_FS = re.compile(
    r"require\s*\(\s*['\"]fs['\"]\s*\)\s*\.\s*(?:writeFileSync|writeFile)\s*\(\s*['\"]([^'\"]+)['\"]"
)

# ---------------------------------------------------------------------------
# Uncertain path patterns (wildcards, variables, etc.)
# ---------------------------------------------------------------------------

UNCERTAIN_PATH_PATTERNS: list[str] = [
    r"\*",  # wildcards
    r"\?",
    r"\$",  # variables
    r"`",  # command substitution
    r"\$\(",
    r"\{",  # brace expansion
    r"\[",  # bracket expansion
]

# ---------------------------------------------------------------------------
# Protected path markers for fail-closed guard logic
# ---------------------------------------------------------------------------

PROTECTED_PATH_MARKERS: tuple[str, ...] = (
    "memory/kb/",
    "memory/system/",
    "memory/docs/",
    "memory/log/",
)


def is_protected_path_target(payload: dict[str, Any]) -> bool:
    """Check if payload targets a protected path.

    Fast path check for fail-closed logic. Does NOT call the full classifier.
    Checks tool_input path fields (file_path, path, command) against
    PROTECTED_PATH_MARKERS.

    Args:
        payload: Dict containing tool_input or direct path fields.

    Returns:
        True if any path field contains a protected marker, False otherwise.
    """
    # Defensive check: non-dict payloads cannot have protected paths
    if not isinstance(payload, dict):
        return False

    # Normalize: check tool_input first, then top-level
    tool_input = payload.get("tool_input", payload)

    # Check each path field
    for key in ("file_path", "path", "command"):
        val = tool_input.get(key, "")
        if isinstance(val, str):
            for marker in PROTECTED_PATH_MARKERS:
                if marker in val:
                    return True
    return False
