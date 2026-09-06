"""
Tests for memory_core.evolution.registry - lifecycle registry enumeration
"""
import json
import tempfile
from pathlib import Path
import pytest

from memory_core.evolution.registry import EvolutionRegistry


@pytest.fixture
def temp_lifecycle_root():
    """Create temporary lifecycle registry structure"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create path-index.json
        path_index = {
            "paths": {
                "/tmp/proj1": {
                    "git_root": "/tmp/proj1",
                    "project_name": "proj1"
                },
                "/tmp/proj2": {
                    "git_root": "/tmp/proj2",
                    "project_name": "proj2"
                },
                "/tmp/proj1": {  # duplicate, should be deduped
                    "git_root": "/tmp/proj1",
                    "project_name": "proj1-dup"
                }
            },
            "schema_version": "project-lifecycle-path-index-v1"
        }
        
        lifecycle_dir = root / "project-lifecycle"
        lifecycle_dir.mkdir()
        
        with open(lifecycle_dir / "path-index.json", "w") as f:
            json.dump(path_index, f)
        
        # Create projects directory
        projects_dir = lifecycle_dir / "projects"
        projects_dir.mkdir()
        
        # Add some project JSONs
        proj3 = {
            "git_root": "/tmp/proj3",
            "project_name": "proj3",
            "status": "active"
        }
        with open(projects_dir / "proj3.json", "w") as f:
            json.dump(proj3, f)
        
        proj4 = {
            "git_root": "/tmp/proj4",  # missing project
            "project_name": "proj4",
            "status": "active"
        }
        with open(projects_dir / "proj4.json", "w") as f:
            json.dump(proj4, f)
        
        proj5 = {
            "git_root": None,  # None git_root should be filtered
            "project_name": "proj5"
        }
        with open(projects_dir / "proj5.json", "w") as f:
            json.dump(proj5, f)
        
        yield root, lifecycle_dir


@pytest.fixture
def temp_project_dirs():
    """Create temporary project directories with various health states"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # proj1: active_kb (has memory/kb with content)
        proj1 = root / "proj1"
        (proj1 / "memory" / "kb" / "lessons").mkdir(parents=True)
        (proj1 / "memory" / "kb" / "lessons" / "lesson1.md").write_text("# Lesson 1")
        
        # proj2: no_kb (has memory but no kb or empty kb)
        proj2 = root / "proj2"
        (proj2 / "memory").mkdir(parents=True)
        
        # proj3: active_kb
        proj3 = root / "proj3"
        (proj3 / "memory" / "kb" / "decisions").mkdir(parents=True)
        (proj3 / "memory" / "kb" / "decisions" / "decision1.md").write_text("# Decision 1")
        
        # proj4: missing (doesn't exist)
        # Don't create it
        
        yield root, [proj1, proj2, proj3, root / "proj4"]


def test_registry_dedup_by_git_root(temp_lifecycle_root, temp_project_dirs):
    """Test that registry deduplicates by git_root and filters None"""
    lifecycle_root, lifecycle_dir = temp_lifecycle_root
    project_root, projects = temp_project_dirs
    
    registry = EvolutionRegistry(lifecycle_dir)
    entries = registry.get_all_entries()
    
    # Should have deduped proj1 and filtered None git_root
    git_roots = [e.git_root for e in entries]
    
    # Count unique git_roots
    assert len(git_roots) == len(set(git_roots)), "git_root should be unique after dedup"
    
    # Should not contain None
    assert None not in git_roots, "None git_root should be filtered"
    
    # Should have at least 3 unique projects (proj1 deduped, proj5 filtered)
    assert len(entries) >= 3


def test_missing_root_tolerated(temp_lifecycle_root, temp_project_dirs):
    """Test that missing paths are classified as 'missing' without error"""
    lifecycle_root, lifecycle_dir = temp_lifecycle_root
    project_root, projects = temp_project_dirs
    
    registry = EvolutionRegistry(lifecycle_dir)
    entries = registry.get_all_entries()
    
    # Find the missing project (proj4)
    missing_entries = [e for e in entries if e.health == "missing"]
    
    # Should have at least one missing entry
    assert len(missing_entries) >= 1, "Should have at least one missing project"
    
    # Should not raise exception
    for entry in missing_entries:
        assert not entry.git_root.exists()


def test_health_classification_active_kb(temp_lifecycle_root, temp_project_dirs):
    """Test that projects with memory/kb content are classified as active_kb"""
    lifecycle_root, lifecycle_dir = temp_lifecycle_root
    project_root, projects = temp_project_dirs
    
    # Create lifecycle registry pointing to our temp projects
    path_index = {
        "paths": {
            str(projects[0]): {"git_root": str(projects[0])},
            str(projects[1]): {"git_root": str(projects[1])},
            str(projects[2]): {"git_root": str(projects[2])},
            str(projects[3]): {"git_root": str(projects[3])}
        }
    }
    
    lifecycle_dir2 = lifecycle_root / "project-lifecycle2"
    lifecycle_dir2.mkdir()
    
    with open(lifecycle_dir2 / "path-index.json", "w") as f:
        json.dump(path_index, f)
    
    projects_dir2 = lifecycle_dir2 / "projects"
    projects_dir2.mkdir()
    
    registry = EvolutionRegistry(lifecycle_dir2)
    entries = registry.get_all_entries()
    
    # proj1 should be active_kb (has memory/kb/lessons with content)
    proj1_entries = [e for e in entries if e.git_root == projects[0]]
    assert len(proj1_entries) == 1
    assert proj1_entries[0].health == "active_kb"
    
    # proj2 should be no_kb (has memory but no kb content)
    proj2_entries = [e for e in entries if e.git_root == projects[1]]
    assert len(proj2_entries) == 1
    assert proj2_entries[0].health == "no_kb"
    
    # proj3 should be active_kb (has memory/kb/decisions with content)
    proj3_entries = [e for e in entries if e.git_root == projects[2]]
    assert len(proj3_entries) == 1
    assert proj3_entries[0].health == "active_kb"


def test_backup_paths_filters_missing(temp_lifecycle_root, temp_project_dirs):
    """Test that backup_paths only returns existing memory directories"""
    lifecycle_root, lifecycle_dir = temp_lifecycle_root
    project_root, projects = temp_project_dirs
    
    # Create lifecycle registry pointing to our temp projects
    path_index = {
        "paths": {
            str(projects[0]): {"git_root": str(projects[0])},
            str(projects[1]): {"git_root": str(projects[1])},
            str(projects[2]): {"git_root": str(projects[2])},
            str(projects[3]): {"git_root": str(projects[3])}  # missing
        }
    }
    
    lifecycle_dir2 = lifecycle_root / "project-lifecycle3"
    lifecycle_dir2.mkdir()
    
    with open(lifecycle_dir2 / "path-index.json", "w") as f:
        json.dump(path_index, f)
    
    projects_dir2 = lifecycle_dir2 / "projects"
    projects_dir2.mkdir()
    
    registry = EvolutionRegistry(lifecycle_dir2)
    backup_paths = registry.get_backup_paths()
    
    # Should not include missing project
    assert len(backup_paths) == 3, "Should only include 3 existing projects"
    
    # All paths should end with /memory
    for path in backup_paths:
        assert path.endswith("/memory") or path.endswith("\\memory")
        
    # All paths should exist on disk
    for path in backup_paths:
        assert Path(path).exists()
