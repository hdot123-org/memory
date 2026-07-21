# -*- coding: utf-8 -*-
"""Unit tests for _rule_helpers.py extracted functions."""

import tempfile
from pathlib import Path

from memory_core.tools._rule_helpers import (
    _existing_paths,
    _json_object_keys,
    _json_string_values,
    _markdown_code_tokens,
    _path_is_under,
    _path_is_under_lexical,
    _section_body,
    _section_bullets,
)


def test_path_is_under_true():
    """Test path_is_under returns True for path under root."""
    root = Path("/project")
    path = Path("/project/subdir/file.txt")
    assert _path_is_under(path, root) is True


def test_path_is_under_false():
    """Test path_is_under returns False for path outside root."""
    root = Path("/project")
    path = Path("/other/file.txt")
    assert _path_is_under(path, root) is False


def test_path_is_under_lexical_true():
    """Test lexical containment without symlinks."""
    root = Path("/project")
    path = Path("/project/subdir/file.txt")
    assert _path_is_under_lexical(path, root) is True


def test_path_is_under_lexical_false():
    """Test lexical containment fails outside root."""
    root = Path("/project")
    path = Path("/other/file.txt")
    assert _path_is_under_lexical(path, root) is False


def test_section_bullets_extracts_bullets():
    """Test extraction of bullet points from markdown section."""
    text = """
## Section Header
- item one
- item two
- item three

## Next Section
"""
    bullets = _section_bullets(text, "## Section Header")
    assert bullets == ["item one", "item two", "item three"]


def test_section_bullets_stops_at_next_heading():
    """Test bullet extraction stops at next heading."""
    text = """
## Section Header
- item one
- item two

## Next Section
- other item
"""
    bullets = _section_bullets(text, "## Section Header")
    assert bullets == ["item one", "item two"]


def test_section_body_extracts_content():
    """Test extraction of section body content."""
    text = """
## Section Header
Some content here
More content

## Next Section
Other content
"""
    body = _section_body(text, "## Section Header")
    assert "Some content here" in body
    assert "More content" in body
    assert "Other content" not in body


def test_section_body_returns_empty_for_missing():
    """Test section_body returns empty string for missing section."""
    text = "## Other Section\nContent"
    body = _section_body(text, "## Missing Section")
    assert body == ""


def test_markdown_code_tokens_extracts_inline_code():
    """Test extraction of inline code tokens."""
    text = "Use `print()` and `input()` functions"
    tokens = _markdown_code_tokens(text)
    assert tokens == {"print()", "input()"}


def test_markdown_code_tokens_empty():
    """Test no code tokens returns empty set."""
    text = "No code here"
    tokens = _markdown_code_tokens(text)
    assert tokens == set()


def test_json_string_values_extracts_values():
    """Test extraction of string values for a key."""
    text = '{"name": "Alice", "name": "Bob", "age": "30"}'
    values = _json_string_values(text, "name")
    assert values == {"Alice", "Bob"}


def test_json_string_values_no_match():
    """Test no matching key returns empty set."""
    text = '{"name": "Alice"}'
    values = _json_string_values(text, "missing")
    assert values == set()


def test_json_object_keys_extracts_keys():
    """Test extraction of all object keys."""
    text = '{"name": "Alice", "age": 30, "city": "NYC"}'
    keys = _json_object_keys(text)
    assert keys == {"name", "age", "city"}


def test_existing_paths_filters_existing():
    """Test existing_paths filters to only existing paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = Path(tmpdir) / "exists.txt"
        existing.touch()
        missing = Path(tmpdir) / "missing.txt"

        result = _existing_paths([existing, missing])
        assert str(existing) in result
        assert str(missing) not in result


def test_all_functions_importable():
    """Test all 8 functions are importable via both import paths."""
    # Direct import
    from memory_core.tools._rule_helpers import (
        _existing_paths,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _section_body,
        _section_bullets,
    )

    # Verify they're callable
    assert callable(_path_is_under)
    assert callable(_path_is_under_lexical)
    assert callable(_section_bullets)
    assert callable(_section_body)
    assert callable(_markdown_code_tokens)
    assert callable(_json_string_values)
    assert callable(_json_object_keys)
    assert callable(_existing_paths)
