#!/usr/bin/env python3
"""Tests for index_schema (T2.5)."""
from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.index_schema import (
    INDEX_SCHEMA_VERSION,
    PROJECT_VERSION_MARKER,
    SCHEMA_VERSION_MARKER,
    build_headers,
    get_schema_version,
    inject_headers,
    is_schema_compatible,
    parse_headers,
    read_project_version,
    strip_headers,
)


def test_build_headers_default_schema_version():
    h = build_headers("0.4.0")
    assert h.project_version == "0.4.0"
    assert h.schema_version == INDEX_SCHEMA_VERSION


def test_build_headers_custom_schema_version():
    h = build_headers("0.4.0", schema_version="2.0")
    assert h.schema_version == "2.0"


def test_render_emits_two_lines():
    h = build_headers("0.4.0")
    out = h.render()
    assert f"<!-- {PROJECT_VERSION_MARKER}: 0.4.0 -->" in out
    assert f"<!-- {SCHEMA_VERSION_MARKER}: {INDEX_SCHEMA_VERSION} -->" in out
    assert out.endswith("\n")


def test_inject_headers_prepends_block():
    h = build_headers("0.4.0")
    body = "# Title\n\n- item\n"
    out = inject_headers(body, h)
    assert out.startswith(f"<!-- {PROJECT_VERSION_MARKER}: 0.4.0 -->")
    assert out.endswith(body)


def test_inject_headers_is_idempotent():
    h = build_headers("0.4.0")
    body = "# Title\n"
    once = inject_headers(body, h)
    twice = inject_headers(once, h)
    assert once == twice


def test_inject_headers_replaces_old_version():
    h_old = build_headers("0.3.0")
    h_new = build_headers("0.4.0")
    body = "# Title\n"
    out_old = inject_headers(body, h_old)
    out_new = inject_headers(out_old, h_new)
    assert "0.3.0" not in out_new
    assert "0.4.0" in out_new


def test_strip_headers_removes_known_markers():
    body = "# Title\n"
    out = inject_headers(body, build_headers("0.4.0"))
    assert strip_headers(out) == body


def test_strip_headers_preserves_other_comments():
    raw = "<!-- some-other: keep -->\n# Title\n"
    assert strip_headers(raw) == raw


def test_parse_headers_extracts_known_fields():
    raw = (
        f"<!-- {PROJECT_VERSION_MARKER}: 1.2.3 -->\n"
        f"<!-- {SCHEMA_VERSION_MARKER}: 1.0 -->\n"
        "# body\n"
    )
    parsed = parse_headers(raw)
    assert parsed[PROJECT_VERSION_MARKER] == "1.2.3"
    assert parsed[SCHEMA_VERSION_MARKER] == "1.0"


def test_parse_headers_stops_at_first_body_line():
    raw = (
        f"<!-- {PROJECT_VERSION_MARKER}: 1.2.3 -->\n"
        "# body\n"
        f"<!-- {SCHEMA_VERSION_MARKER}: 99.0 -->\n"
    )
    parsed = parse_headers(raw)
    assert parsed[PROJECT_VERSION_MARKER] == "1.2.3"
    # schema header buried in body must not be picked up
    assert SCHEMA_VERSION_MARKER not in parsed


def test_get_schema_version_defaults_to_current_when_absent():
    assert get_schema_version("# legacy\n") == INDEX_SCHEMA_VERSION


def test_get_schema_version_returns_declared_value():
    raw = f"<!-- {SCHEMA_VERSION_MARKER}: 2.5 -->\n# body\n"
    assert get_schema_version(raw) == "2.5"


def test_is_schema_compatible_major_version_only():
    assert is_schema_compatible(f"<!-- {SCHEMA_VERSION_MARKER}: 1.0 -->\n") is True
    assert is_schema_compatible(f"<!-- {SCHEMA_VERSION_MARKER}: 1.9 -->\n") is True
    assert is_schema_compatible(f"<!-- {SCHEMA_VERSION_MARKER}: 2.0 -->\n") is False


def test_is_schema_compatible_legacy_treated_as_default():
    assert is_schema_compatible("# legacy file\n") is True


def test_read_project_version_returns_string():
    version = read_project_version()
    assert isinstance(version, str)
    assert version != ""
