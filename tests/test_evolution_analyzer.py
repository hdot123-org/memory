"""
Tests for memory_core.evolution.analyzer - incremental analysis
"""

import tempfile
from pathlib import Path

from memory_core.evolution.analyzer import IncrementalAnalyzer


def test_analyzer_initial_state():
    """Test analyzer starts with empty state"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        config = {"analyze": {"max_files_per_project": 50}}

        analyzer = IncrementalAnalyzer(state_file, config)
        assert analyzer.max_files_per_project == 50
        assert analyzer.include_docs is True
        assert analyzer.include_daily_logs is True


def test_analyzer_config_flags():
    """Test analyzer respects config flags"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        config = {
            "analyze": {
                "include_docs": False,
                "include_daily_logs": False,
                "max_files_per_project": 10,
            }
        }

        analyzer = IncrementalAnalyzer(state_file, config)
        assert analyzer.max_files_per_project == 10
        assert analyzer.include_docs is False
        assert analyzer.include_daily_logs is False


def test_analyzer_detects_changes():
    """Test analyzer detects file changes"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup project structure
        project_dir = Path(tmpdir) / "project"
        kb_dir = project_dir / "memory" / "kb" / "lessons"
        kb_dir.mkdir(parents=True)

        lesson_file = kb_dir / "test.md"
        lesson_file.write_text("# Test Lesson\n\nContent")

        # Setup analyzer
        state_file = Path(tmpdir) / "state.json"
        config = {"analyze": {"max_files_per_project": 50}}
        analyzer = IncrementalAnalyzer(state_file, config)

        # First analysis should detect the file
        result = analyzer.analyze_project(project_dir)
        assert len(result.changed_files) == 1
        assert result.changed_files[0].rel_path == "memory/kb/lessons/test.md"

        # Update cursor
        analyzer.update_cursors(project_dir, result.changed_files)

        # Second analysis should detect no changes
        result2 = analyzer.analyze_project(project_dir)
        assert len(result2.changed_files) == 0


def test_analyzer_content_change_detection():
    """Test analyzer detects content changes even with same mtime"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup project structure
        project_dir = Path(tmpdir) / "project"
        kb_dir = project_dir / "memory" / "kb" / "lessons"
        kb_dir.mkdir(parents=True)

        lesson_file = kb_dir / "test.md"
        lesson_file.write_text("# Test Lesson\n\nContent v1")

        # Setup analyzer
        state_file = Path(tmpdir) / "state.json"
        config = {"analyze": {"max_files_per_project": 50}}
        analyzer = IncrementalAnalyzer(state_file, config)

        # First analysis
        result1 = analyzer.analyze_project(project_dir)
        assert len(result1.changed_files) == 1
        analyzer.update_cursors(project_dir, result1.changed_files)

        # Modify file
        lesson_file.write_text("# Test Lesson\n\nContent v2 - modified")

        # Second analysis should detect the change
        result2 = analyzer.analyze_project(project_dir)
        assert len(result2.changed_files) == 1
        assert result2.changed_files[0].sha256 != result1.changed_files[0].sha256


def test_analyzer_excludes_global():
    """Test analyzer excludes memory/kb/global/"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup project structure
        project_dir = Path(tmpdir) / "project"

        # Regular lesson (should be included)
        lessons_dir = project_dir / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)
        (lessons_dir / "test.md").write_text("# Test")

        # Global file (should be excluded)
        global_dir = project_dir / "memory" / "kb" / "global"
        global_dir.mkdir(parents=True)
        (global_dir / "global.md").write_text("# Global")

        # Setup analyzer
        state_file = Path(tmpdir) / "state.json"
        config = {"analyze": {"max_files_per_project": 50}}
        analyzer = IncrementalAnalyzer(state_file, config)

        # Analyze
        result = analyzer.analyze_project(project_dir)

        # Should only include the regular lesson
        assert len(result.changed_files) == 1
        assert result.changed_files[0].rel_path == "memory/kb/lessons/test.md"


def test_analyzer_file_cap():
    """Test analyzer respects max_files_per_project limit"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup project with many files
        project_dir = Path(tmpdir) / "project"
        lessons_dir = project_dir / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)

        # Create 10 files
        for i in range(10):
            (lessons_dir / f"lesson{i}.md").write_text(f"# Lesson {i}")

        # Setup analyzer with cap of 5
        state_file = Path(tmpdir) / "state.json"
        config = {"analyze": {"max_files_per_project": 5}}
        analyzer = IncrementalAnalyzer(state_file, config)

        # Analyze
        result = analyzer.analyze_project(project_dir)

        # Should only process 5 files
        assert len(result.changed_files) == 5


def test_analyzer_state_persistence():
    """Test analyzer state persists across instances"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup project structure
        project_dir = Path(tmpdir) / "project"
        kb_dir = project_dir / "memory" / "kb" / "lessons"
        kb_dir.mkdir(parents=True)

        lesson_file = kb_dir / "test.md"
        lesson_file.write_text("# Test Lesson")

        # Setup analyzer
        state_file = Path(tmpdir) / "state.json"
        config = {"analyze": {"max_files_per_project": 50}}

        # First analyzer instance
        analyzer1 = IncrementalAnalyzer(state_file, config)
        result1 = analyzer1.analyze_project(project_dir)
        analyzer1.update_cursors(project_dir, result1.changed_files)

        # Verify state file exists
        assert state_file.exists()

        # Second analyzer instance (should load state)
        analyzer2 = IncrementalAnalyzer(state_file, config)
        result2 = analyzer2.analyze_project(project_dir)

        # Should detect no changes (cursor persisted)
        assert len(result2.changed_files) == 0


def test_analyzer_include_docs_flag():
    """Test analyzer respects include_docs flag"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup project structure
        project_dir = Path(tmpdir) / "project"

        # Lesson file
        lessons_dir = project_dir / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)
        (lessons_dir / "lesson.md").write_text("# Lesson")

        # Doc file
        docs_dir = project_dir / "memory" / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "doc.md").write_text("# Doc")

        # Analyzer with docs enabled
        state_file = Path(tmpdir) / "state.json"
        config_enabled = {"analyze": {"include_docs": True, "max_files_per_project": 50}}
        analyzer_enabled = IncrementalAnalyzer(state_file, config_enabled)
        result_enabled = analyzer_enabled.analyze_project(project_dir)
        assert len(result_enabled.changed_files) == 2

        # Analyzer with docs disabled
        state_file2 = Path(tmpdir) / "state2.json"
        config_disabled = {"analyze": {"include_docs": False, "max_files_per_project": 50}}
        analyzer_disabled = IncrementalAnalyzer(state_file2, config_disabled)
        result_disabled = analyzer_disabled.analyze_project(project_dir)
        assert len(result_disabled.changed_files) == 1
        assert result_disabled.changed_files[0].rel_path == "memory/kb/lessons/lesson.md"
