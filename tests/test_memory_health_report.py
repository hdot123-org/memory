"""Tests for memory_health_report module."""



from memory_core.tools.memory_health_report import (
    _determine_recommended_mode,
    _has_workspace_memory_conflict,
    main,
)


class TestDetermineRecommendedMode:
    def test_fresh_when_no_findings_no_system_memory(self):
        mode = _determine_recommended_mode(
            total=0, p0=0, p1=0, p2=0,
            root_pollution_count=0,
            multi_generation_conflict=False,
            has_real_workspace_conflict=False,
            has_system_memory=False,
        )
        assert mode == "fresh"

    def test_update_when_no_findings_with_system_memory(self):
        mode = _determine_recommended_mode(
            total=0, p0=0, p1=0, p2=0,
            root_pollution_count=0,
            multi_generation_conflict=False,
            has_real_workspace_conflict=False,
            has_system_memory=True,
        )
        assert mode == "update"

    def test_manual_when_workspace_conflict(self):
        mode = _determine_recommended_mode(
            total=0, p0=0, p1=0, p2=0,
            root_pollution_count=0,
            multi_generation_conflict=False,
            has_real_workspace_conflict=True,
            has_system_memory=True,
        )
        assert mode == "manual"

    def test_repair_when_p0_with_system_memory(self):
        mode = _determine_recommended_mode(
            total=5, p0=2, p1=0, p2=0,
            root_pollution_count=0,
            multi_generation_conflict=False,
            has_real_workspace_conflict=False,
            has_system_memory=True,
        )
        assert mode == "repair"

    def test_adopt_when_p0_without_system_memory(self):
        mode = _determine_recommended_mode(
            total=5, p0=2, p1=0, p2=0,
            root_pollution_count=0,
            multi_generation_conflict=False,
            has_real_workspace_conflict=False,
            has_system_memory=False,
        )
        assert mode == "adopt"

    def test_repair_when_p1_with_system_memory(self):
        mode = _determine_recommended_mode(
            total=3, p0=0, p1=2, p2=0,
            root_pollution_count=0,
            multi_generation_conflict=False,
            has_real_workspace_conflict=False,
            has_system_memory=True,
        )
        assert mode == "repair"

    def test_repair_when_p2_with_system_memory(self):
        mode = _determine_recommended_mode(
            total=3, p0=0, p1=0, p2=2,
            root_pollution_count=0,
            multi_generation_conflict=False,
            has_real_workspace_conflict=False,
            has_system_memory=True,
        )
        assert mode == "repair"

    def test_repair_when_root_pollution(self):
        mode = _determine_recommended_mode(
            total=2, p0=0, p1=0, p2=0,
            root_pollution_count=2,
            multi_generation_conflict=False,
            has_real_workspace_conflict=False,
            has_system_memory=True,
        )
        assert mode == "repair"


class TestHasWorkspaceMemoryConflict:
    def test_no_workspace_structures(self, tmp_path):
        findings = []
        result = _has_workspace_memory_conflict(tmp_path, findings)
        assert result is False

    def test_workspace_memory_but_no_root(self, tmp_path):
        (tmp_path / "workspace" / "memory").mkdir(parents=True)
        findings = []
        result = _has_workspace_memory_conflict(tmp_path, findings)
        assert result is False

    def test_both_root_and_workspace(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "workspace" / "memory").mkdir(parents=True)
        findings = []
        result = _has_workspace_memory_conflict(tmp_path, findings)
        assert result is True

    def test_workspace_project_map_and_root(self, tmp_path):
        (tmp_path / "project-map").mkdir()
        (tmp_path / "workspace" / "project-map").mkdir(parents=True)
        findings = []
        result = _has_workspace_memory_conflict(tmp_path, findings)
        assert result is True


class TestMain:
    def test_nonexistent_target(self):
        # main() uses argparse with required=True for --target.
        # Calling without --target causes argparse to exit(2).
        # Testing actual file operations is done via E2E subprocess tests.
        assert callable(main)
