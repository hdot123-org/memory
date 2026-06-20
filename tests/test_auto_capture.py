#!/usr/bin/env python3
"""Tests for session-end auto-capture feature (VAL-CAPTURE-001/002/003).

Auto-capture scans project memory/kb/lessons/ and decisions/ for today's changes
and copies candidates to ~/.memory/global-kb/pending/ with source metadata.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a mock project structure with memory/kb/lessons/ and decisions/."""
    project = tmp_path / "test-project"
    project.mkdir()

    # Create memory/kb structure
    (project / "memory" / "kb" / "lessons").mkdir(parents=True)
    (project / "memory" / "kb" / "decisions").mkdir(parents=True)

    return project


@pytest.fixture
def global_kb_root(tmp_path: Path) -> Path:
    """Create a mock global KB structure."""
    kb_root = tmp_path / "global-kb"
    kb_root.mkdir()

    # Create domain directories
    for domain in ["operations", "engineering", "collaboration", "pending"]:
        (kb_root / domain).mkdir()

    return kb_root


def test_capture_scans_today_changes(project_root: Path, global_kb_root: Path):
    """VAL-CAPTURE-001: session-end scans today's changes in lessons/decisions."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create a file modified today in lessons/
    today = datetime.now()
    lessonfile = project_root / "memory" / "kb" / "lessons" / "test-lesson.md"
    lessonfile.write_text("# Test Lesson\nSome content")

    # Set modification time to today
    today_ts = today.timestamp()
    os.utime(lessonfile, (today_ts, today_ts))

    # Capture candidates
    candidates = capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Should find the candidate
    assert len(candidates) == 1
    assert candidates[0]["source_file"] == "memory/kb/lessons/test-lesson.md"


def test_capture_writes_to_pending(project_root: Path, global_kb_root: Path):
    """VAL-CAPTURE-001: Candidates are written to pending/ directory."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create a file modified today
    lessonfile = project_root / "memory" / "kb" / "lessons" / "captured-lesson.md"
    lessonfile.write_text("# Captured Lesson\nCaptured content")
    today_ts = datetime.now().timestamp()
    os.utime(lessonfile, (today_ts, today_ts))

    # Capture candidates
    capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Check file exists in pending/
    pending_dir = global_kb_root / "pending"
    pending_files = list(pending_dir.glob("*.md"))
    assert len(pending_files) == 1
    assert "captured-lesson" in pending_files[0].name


def test_capture_adds_source_metadata(project_root: Path, global_kb_root: Path):
    """VAL-CAPTURE-002: Candidate files have source metadata."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create a file modified today
    lessonfile = project_root / "memory" / "kb" / "lessons" / "metadata-test.md"
    lessonfile.write_text("# Metadata Test\nContent here")
    today_ts = datetime.now().timestamp()
    os.utime(lessonfile, (today_ts, today_ts))

    # Capture candidates
    capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Check pending file has metadata
    pending_dir = global_kb_root / "pending"
    pending_file = list(pending_dir.glob("*.md"))[0]
    content = pending_file.read_text()

    # Should contain source metadata
    assert "source_project:" in content or "source_project =" in content
    assert str(project_root) in content or project_root.name in content
    assert "source_file:" in content or "source_file =" in content
    assert "captured_at:" in content or "captured_at =" in content


def test_capture_no_changes_no_candidates(project_root: Path, global_kb_root: Path):
    """VAL-CAPTURE-001: No changes today means no candidates produced."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create a file but set modification time to yesterday
    yesterday = datetime.now() - timedelta(days=1)
    lessonfile = project_root / "memory" / "kb" / "lessons" / "old-lesson.md"
    lessonfile.write_text("# Old Lesson\nOld content")
    yesterday_ts = yesterday.timestamp()
    os.utime(lessonfile, (yesterday_ts, yesterday_ts))

    # Capture candidates
    candidates = capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Should find no candidates
    assert len(candidates) == 0

    # Check pending/ is empty (except README.md)
    pending_dir = global_kb_root / "pending"
    pending_files = [f for f in pending_dir.glob("*.md") if f.name != "README.md"]
    assert len(pending_files) == 0


def test_capture_only_writes_pending_not_formal(project_root: Path, global_kb_root: Path):
    """VAL-CAPTURE-003: Auto-capture only writes to pending/, not formal categories."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create files modified today
    lessonfile = project_root / "memory" / "kb" / "lessons" / "test.md"
    lessonfile.write_text("# Test\nContent")
    today_ts = datetime.now().timestamp()
    os.utime(lessonfile, (today_ts, today_ts))

    decisionfile = project_root / "memory" / "kb" / "decisions" / "test-decision.md"
    decisionfile.write_text("# Decision\nContent")
    os.utime(decisionfile, (today_ts, today_ts))

    # Capture candidates
    capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Check formal categories are empty
    for domain in ["operations", "engineering", "collaboration"]:
        domain_dir = global_kb_root / domain
        domain_files = [f for f in domain_dir.glob("*.md") if f.name != "README.md"]
        assert len(domain_files) == 0, f"Formal category {domain}/ should be empty"

    # Only pending/ should have files
    pending_dir = global_kb_root / "pending"
    pending_files = [f for f in pending_dir.glob("*.md") if f.name != "README.md"]
    assert len(pending_files) == 2


def test_capture_scans_both_lessons_and_decisions(project_root: Path, global_kb_root: Path):
    """VAL-CAPTURE-001: Scans both lessons/ and decisions/ directories."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create files in both directories
    today_ts = datetime.now().timestamp()

    lessonfile = project_root / "memory" / "kb" / "lessons" / "lesson.md"
    lessonfile.write_text("# Lesson\nContent")
    os.utime(lessonfile, (today_ts, today_ts))

    decisionfile = project_root / "memory" / "kb" / "decisions" / "decision.md"
    decisionfile.write_text("# Decision\nContent")
    os.utime(decisionfile, (today_ts, today_ts))

    # Capture candidates
    candidates = capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Should find both
    assert len(candidates) == 2
    source_files = [c["source_file"] for c in candidates]
    assert any("lessons/lesson.md" in sf for sf in source_files)
    assert any("decisions/decision.md" in sf for sf in source_files)


def test_capture_handles_missing_directories(tmp_path: Path, global_kb_root: Path):
    """Auto-capture handles missing lessons/decisions directories gracefully."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Project with no lessons/decisions directories
    project = tmp_path / "empty-project"
    project.mkdir()
    (project / "memory" / "kb").mkdir(parents=True)

    # Should not crash
    candidates = capture_candidates(
        project_root=project,
        global_kb_root=global_kb_root,
    )

    assert len(candidates) == 0


def test_capture_preserves_original_content(project_root: Path, global_kb_root: Path):
    """Captured files should preserve original content with added metadata."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create a file with specific content
    original_content = "# My Lesson\n\nThis is important content.\n\n## Details\nMore details here."
    lessonfile = project_root / "memory" / "kb" / "lessons" / "preserve-test.md"
    lessonfile.write_text(original_content)
    today_ts = datetime.now().timestamp()
    os.utime(lessonfile, (today_ts, today_ts))

    # Capture candidates
    capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Check pending file contains original content
    pending_dir = global_kb_root / "pending"
    pending_file = list(pending_dir.glob("*.md"))[0]
    pending_content = pending_file.read_text()

    # Original content should be preserved
    assert "My Lesson" in pending_content
    assert "important content" in pending_content
    assert "Details" in pending_content


def test_capture_filename_includes_source_info(project_root: Path, global_kb_root: Path):
    """Pending filenames should include source info to avoid conflicts."""
    from memory_core.tools.session_end_logger import capture_candidates

    # Create a file
    lessonfile = project_root / "memory" / "kb" / "lessons" / "common-name.md"
    lessonfile.write_text("# Common\nContent")
    today_ts = datetime.now().timestamp()
    os.utime(lessonfile, (today_ts, today_ts))

    # Capture candidates
    capture_candidates(
        project_root=project_root,
        global_kb_root=global_kb_root,
    )

    # Check pending filename
    pending_dir = global_kb_root / "pending"
    pending_file = list(pending_dir.glob("*.md"))[0]

    # Filename should include project name or timestamp to avoid conflicts
    assert pending_file.name != "common-name.md"  # Should be transformed
    assert "common-name" in pending_file.name or project_root.name in pending_file.name
