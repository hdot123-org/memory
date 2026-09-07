"""
Tests for memory_core.evolution.extractor - content extraction
"""

import tempfile
from pathlib import Path

from memory_core.evolution.extractor import NoLlmExtractor


def test_extractor_basic():
    """Test extractor processes file changes"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup project structure
        project_dir = Path(tmpdir) / "project"
        kb_dir = project_dir / "memory" / "kb" / "lessons"
        kb_dir.mkdir(parents=True)

        lesson_file = kb_dir / "test.md"
        lesson_file.write_text("# Test Lesson\n\nThis is test content.")

        # Create changed_files in the format expected by extractor
        changed_files = [
            {
                "abs_path": lesson_file,
                "rel_path": "memory/kb/lessons/test.md",
                "sha256": "abc123",
                "project_root": project_dir,
            }
        ]

        # Extract candidates
        extractor = NoLlmExtractor()
        candidates = extractor.extract_from_files(changed_files)

        assert len(candidates) == 1
        assert candidates[0].title == "Test Lesson"
        assert candidates[0].domain == "engineering"  # default domain
        assert "This is test content." in candidates[0].content
        assert candidates[0].source_refs[0]["path"] == "memory/kb/lessons/test.md"
        assert candidates[0].source_refs[0]["project"] == str(project_dir)
        assert candidates[0].unrefined is True


def test_extractor_multiple_files():
    """Test extractor processes multiple files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "project"
        lessons_dir = project_dir / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)

        # Create multiple files
        file1 = lessons_dir / "lesson1.md"
        file1.write_text("# Lesson One\n\nContent 1")

        file2 = lessons_dir / "lesson2.md"
        file2.write_text("# Lesson Two\n\nContent 2")

        changed_files = [
            {
                "abs_path": file1,
                "rel_path": "memory/kb/lessons/lesson1.md",
                "sha256": "hash1",
                "project_root": project_dir,
            },
            {
                "abs_path": file2,
                "rel_path": "memory/kb/lessons/lesson2.md",
                "sha256": "hash2",
                "project_root": project_dir,
            },
        ]

        extractor = NoLlmExtractor()
        candidates = extractor.extract_from_files(changed_files)

        assert len(candidates) == 2
        titles = {c.title for c in candidates}
        assert titles == {"Lesson One", "Lesson Two"}


def test_extractor_empty_list():
    """Test extractor handles empty file list"""
    changed_files = []
    extractor = NoLlmExtractor()
    candidates = extractor.extract_from_files(changed_files)
    assert len(candidates) == 0


def test_extractor_missing_file():
    """Test extractor handles missing files gracefully"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "project"

        # Create file change pointing to non-existent file
        missing_file = project_dir / "memory" / "kb" / "lessons" / "missing.md"
        changed_files = [
            {
                "abs_path": missing_file,
                "rel_path": "memory/kb/lessons/missing.md",
                "sha256": "hash",
                "project_root": project_dir,
            }
        ]

        extractor = NoLlmExtractor()
        candidates = extractor.extract_from_files(changed_files)
        assert len(candidates) == 0


def test_extractor_no_title():
    """Test extractor handles files without clear title"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "project"
        lessons_dir = project_dir / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)

        # File without markdown heading
        lesson_file = lessons_dir / "no_title.md"
        lesson_file.write_text("Just some content without a title")

        changed_files = [
            {
                "abs_path": lesson_file,
                "rel_path": "memory/kb/lessons/no_title.md",
                "sha256": "hash",
                "project_root": project_dir,
            }
        ]

        extractor = NoLlmExtractor()
        candidates = extractor.extract_from_files(changed_files)
        assert len(candidates) == 1
        # Should use first line as fallback title
        assert candidates[0].title == "Just some content without a title"


def test_parse_llm_response_think_tag_stripping():
    """
    Test that _parse_llm_response correctly strips <think> tags from reasoning models (glm-5.3).

    Reasoning models like glm-5.3 wrap their reasoning process in <think>...</think> tags
    before the actual JSON response. The parser must strip these tags and parse the JSON
    that follows.
    """
    from memory_core.evolution.extractor import _parse_llm_response

    # Simulate glm-5.3 response with think block followed by JSON
    content_with_think = '<think>\nThis is the model\'s reasoning process.\nIt can contain multiple lines and various text.\n</think>\n\n[\n  {\n    "title": "测试经验",\n    "domain": "engineering",\n    "content": "这是一个测试经验条目",\n    "confidence": 0.85,\n    "source_refs": [{"project": "test-project", "path": "memory/kb/lessons/test.md"}]\n  }\n]'

    candidates = _parse_llm_response(content_with_think)

    # Should successfully parse the JSON after stripping think tags
    assert len(candidates) == 1
    assert candidates[0]["title"] == "测试经验"
    assert candidates[0]["domain"] == "engineering"
    assert candidates[0]["confidence"] == 0.85
    assert len(candidates[0]["source_refs"]) == 1
