"""INDEX.md schema versioning (T2.5).

Provides an open contract for INDEX.md consumers (e.g., Factory DCE).
The schema header is platform-agnostic and intentionally simple:

    <!-- memory-core: <project_version> -->
    <!-- index-schema: 1.0 -->

The first comment records which release of memory-core generated the
file (debug-friendly). The second comment is the schema contract version
and is updated independently of project version when the INDEX.md shape
changes.

Backward compatibility: INDEX.md files without these headers are still
considered valid; consumers should treat a missing index-schema header
as "schema 1.0" or "legacy".
"""

import re
from pathlib import Path
from typing import NamedTuple

INDEX_SCHEMA_VERSION = "1.0"
"""Current INDEX.md schema contract version. Bump on contract change."""

PROJECT_VERSION_MARKER = "memory-core"
SCHEMA_VERSION_MARKER = "index-schema"

_HEADER_RE = re.compile(
    r"<!--\s*(?P<key>[a-zA-Z][\w-]*)\s*:\s*(?P<value>[^>]*?)\s*-->"
)


class IndexSchemaHeaders(NamedTuple):
    project_version: str
    schema_version: str

    def render(self) -> str:
        return (
            f"<!-- {PROJECT_VERSION_MARKER}: {self.project_version} -->\n"
            f"<!-- {SCHEMA_VERSION_MARKER}: {self.schema_version} -->\n"
        )


def build_headers(project_version: str, schema_version: str = INDEX_SCHEMA_VERSION) -> IndexSchemaHeaders:
    return IndexSchemaHeaders(project_version=project_version, schema_version=schema_version)


def inject_headers(content: str, headers: IndexSchemaHeaders) -> str:
    """Prepend headers to INDEX.md content. Idempotent: replaces if present."""
    stripped = strip_headers(content)
    return headers.render() + stripped


def strip_headers(content: str) -> str:
    """Remove any existing memory-core/index-schema header lines from the top."""
    lines = content.splitlines(keepends=True)
    skipped = 0
    for line in lines:
        match = _HEADER_RE.match(line.strip())
        if match and match.group("key") in {PROJECT_VERSION_MARKER, SCHEMA_VERSION_MARKER}:
            skipped += 1
            continue
        break
    return "".join(lines[skipped:])


def parse_headers(content: str) -> dict[str, str]:
    """Extract header values from the top of INDEX.md.

    Returns an empty dict if no headers found. Only scans the leading
    comment block, so headers buried in the body are ignored.
    """
    result: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _HEADER_RE.match(stripped)
        if not match:
            break
        key = match.group("key")
        if key in {PROJECT_VERSION_MARKER, SCHEMA_VERSION_MARKER}:
            result[key] = match.group("value").strip()
    return result


def get_schema_version(content: str) -> str:
    """Return declared schema version, defaulting to '1.0' for legacy files."""
    return parse_headers(content).get(SCHEMA_VERSION_MARKER, INDEX_SCHEMA_VERSION)


def is_schema_compatible(content: str, expected: str = INDEX_SCHEMA_VERSION) -> bool:
    """Major version compatibility: 1.x consumers accept any 1.y INDEX.md."""
    declared = get_schema_version(content)
    return declared.split(".")[0] == expected.split(".")[0]


def read_project_version() -> str:
    """Read project version from pyproject.toml, falling back to 'unknown'."""
    # Project root is two levels up from memory_core/tools/index_schema.py
    root = Path(__file__).resolve().parent.parent.parent
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("version") and "=" in stripped:
            value = stripped.split("=", 1)[1].strip()
            return value.strip('"').strip("'")
    return "unknown"
