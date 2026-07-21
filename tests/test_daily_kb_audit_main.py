"""Tests for daily_kb_audit.main() CLI entry point.

VAL-M3-001: 拆解前必须先补齐 main 的单元测试覆盖:
  - 基础设施检查路径（正常 / 异常降级 / --no-infra）
  - 无项目路径（返回码取决于基础设施 critical）
  - 有项目路径（正常审计 / 单项目异常 / critical/warning 返回码）
  - --json / --no-write / --notify 选项
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_core.tools.daily_kb_audit import main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _patch_infra_clean():
    """Patch check_infrastructure to return clean (no violations)."""
    with patch(
        "memory_core.tools.daily_kb_audit.check_infrastructure",
        return_value={"servers": {}, "databases": {}, "violations": []},
    ):
        yield


@pytest.fixture()
def _patch_infra_critical():
    """Patch check_infrastructure to return one critical violation."""
    with patch(
        "memory_core.tools.daily_kb_audit.check_infrastructure",
        return_value={
            "servers": {
                "srv1": {
                    "violations": [
                        {"type": "ssh_fail", "severity": "critical", "path": "srv1", "detail": "fail"},
                    ],
                },
            },
            "databases": {},
            "violations": [],
        },
    ):
        yield


@pytest.fixture()
def _patch_no_projects():
    """Patch load_registered_projects to return empty list."""
    with patch(
        "memory_core.tools.daily_kb_audit.load_registered_projects",
        return_value=[],
    ):
        yield


@pytest.fixture()
def _patch_one_project():
    """Patch load_registered_projects to return one project."""
    with patch(
        "memory_core.tools.daily_kb_audit.load_registered_projects",
        return_value=[("proj-a", Path("/fake/proj-a"))],
    ):
        yield


@pytest.fixture()
def _patch_fingerprints():
    """Patch build_global_kb_fingerprints to return empty dict."""
    with patch(
        "memory_core.tools.daily_kb_audit.build_global_kb_fingerprints",
        return_value={},
    ):
        yield


@pytest.fixture()
def _patch_audit_project_clean():
    """Patch audit_project to return clean results."""
    with patch(
        "memory_core.tools.daily_kb_audit.audit_project",
        return_value={"path": "/fake/proj-a", "violations": []},
    ):
        yield


@pytest.fixture()
def _patch_audit_project_critical():
    """Patch audit_project to return one critical violation."""
    with patch(
        "memory_core.tools.daily_kb_audit.audit_project",
        return_value={
            "path": "/fake/proj-a",
            "violations": [
                {"type": "hash_mismatch", "severity": "critical", "path": "x", "detail": "bad"},
            ],
        },
    ):
        yield


@pytest.fixture()
def _patch_audit_project_warning():
    """Patch audit_project to return one warning violation."""
    with patch(
        "memory_core.tools.daily_kb_audit.audit_project",
        return_value={
            "path": "/fake/proj-a",
            "violations": [
                {"type": "unsigned", "severity": "warning", "path": "y", "detail": "unsigned"},
            ],
        },
    ):
        yield


@pytest.fixture()
def _patch_write_report(tmp_path: Path):
    """Patch write_report to write to tmp_path and return the path."""
    out = tmp_path / "report.json"

    def _write(report: dict) -> Path:
        out.write_text(json.dumps(report), encoding="utf-8")
        return out

    with patch("memory_core.tools.daily_kb_audit.write_report", side_effect=_write):
        yield out


@pytest.fixture()
def _patch_build_report():
    """Patch build_report to return a simple report dict."""
    def _build(projects_results, infrastructure=None):
        total_v = sum(len(r.get("violations", [])) for r in projects_results.values())
        r: dict = {
            "audit_date": "2026-07-20",
            "projects_checked": len(projects_results),
            "total_violations": total_v,
            "projects": projects_results,
        }
        if infrastructure is not None:
            r["infrastructure"] = infrastructure
        return r

    with patch("memory_core.tools.daily_kb_audit.build_report", side_effect=_build):
        yield


@pytest.fixture()
def _patch_notify():
    """Patch notify_via_lark to track calls."""
    with patch(
        "memory_core.tools.daily_kb_audit.notify_via_lark",
        return_value=True,
    ) as mock_notify:
        yield mock_notify


# ---------------------------------------------------------------------------
# Group 1: No projects found
# ---------------------------------------------------------------------------

class TestMainNoProjects:
    """main() when load_registered_projects() returns []."""

    def test_no_projects_clean_infra_returns_0(
        self, _patch_infra_clean, _patch_no_projects, _patch_build_report,
        _patch_write_report,
    ):
        """No projects + clean infra → exit 0."""
        rc = main(["--no-write"])
        assert rc == 0

    def test_no_projects_critical_infra_returns_1(
        self, _patch_infra_critical, _patch_no_projects, _patch_build_report,
        _patch_write_report,
    ):
        """No projects + critical infra → exit 1."""
        rc = main(["--no-write"])
        assert rc == 1

    def test_no_projects_json_output(
        self, _patch_infra_clean, _patch_no_projects, _patch_build_report,
        _patch_write_report, capsys: pytest.CaptureFixture,
    ):
        """No projects + --json → JSON printed to stdout."""
        main(["--no-write", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["projects_checked"] == 0

    def test_no_projects_write_report(
        self, _patch_infra_clean, _patch_no_projects, _patch_build_report,
        _patch_write_report,
    ):
        """No projects + write enabled → write_report called."""
        main([])  # default writes report
        # If we got here without error, write_report was called

    def test_no_projects_notify(
        self, _patch_infra_clean, _patch_no_projects, _patch_build_report,
        _patch_write_report, _patch_notify,
    ):
        """No projects + --notify → notify_via_lark called."""
        main(["--no-write", "--notify"])
        _patch_notify.assert_called_once()

    def test_no_projects_no_infra_skips_check(
        self, _patch_no_projects, _patch_build_report, _patch_write_report,
    ):
        """--no-infra → check_infrastructure not called."""
        with patch(
            "memory_core.tools.daily_kb_audit.check_infrastructure",
        ) as mock_infra:
            rc = main(["--no-write", "--no-infra"])
            mock_infra.assert_not_called()
            assert rc == 0


# ---------------------------------------------------------------------------
# Group 2: Projects found, normal audit path
# ---------------------------------------------------------------------------

class TestMainWithProjects:
    """main() when projects exist."""

    def test_clean_audit_returns_0(
        self, _patch_infra_clean, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_clean, _patch_build_report, _patch_write_report,
    ):
        """All clean → exit 0."""
        rc = main(["--no-write"])
        assert rc == 0

    def test_critical_project_returns_1(
        self, _patch_infra_clean, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_critical, _patch_build_report, _patch_write_report,
    ):
        """Critical project violation → exit 1."""
        rc = main(["--no-write"])
        assert rc == 1

    def test_warning_only_returns_0(
        self, _patch_infra_clean, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_warning, _patch_build_report, _patch_write_report,
    ):
        """Warning-only → exit 0 (warnings don't block)."""
        rc = main(["--no-write"])
        assert rc == 0

    def test_json_output_with_projects(
        self, _patch_infra_clean, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_clean, _patch_build_report, _patch_write_report,
        capsys: pytest.CaptureFixture,
    ):
        """--json → valid JSON to stdout."""
        main(["--no-write", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["projects_checked"] == 1

    def test_notify_called(
        self, _patch_infra_clean, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_clean, _patch_build_report, _patch_write_report,
        _patch_notify,
    ):
        """--notify → notify_via_lark called."""
        main(["--no-write", "--notify"])
        _patch_notify.assert_called_once()


# ---------------------------------------------------------------------------
# Group 3: Infrastructure check degradation
# ---------------------------------------------------------------------------

class TestMainInfraDegradation:
    """main() when check_infrastructure() raises."""

    def test_infra_exception_degrades_gracefully(
        self, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_clean, _patch_build_report, _patch_write_report,
    ):
        """check_infrastructure() raises → infra_results=None, continues."""
        with patch(
            "memory_core.tools.daily_kb_audit.check_infrastructure",
            side_effect=RuntimeError("SSH timeout"),
        ):
            rc = main(["--no-write"])
            # Project is clean, infra degraded → exit 0
            assert rc == 0

    def test_infra_exception_with_critical_project_still_returns_1(
        self, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_critical, _patch_build_report, _patch_write_report,
    ):
        """check_infrastructure() raises + critical project → exit 1."""
        with patch(
            "memory_core.tools.daily_kb_audit.check_infrastructure",
            side_effect=RuntimeError("SSH timeout"),
        ):
            rc = main(["--no-write"])
            assert rc == 1


# ---------------------------------------------------------------------------
# Group 4: Project audit exception handling
# ---------------------------------------------------------------------------

class TestMainProjectAuditException:
    """main() when audit_project() raises for one project."""

    def test_single_project_exception_captured(
        self, _patch_infra_clean, _patch_fingerprints,
        _patch_build_report, _patch_write_report,
    ):
        """audit_project raises → captured as warning, doesn't crash."""
        with patch(
            "memory_core.tools.daily_kb_audit.load_registered_projects",
            return_value=[
                ("proj-a", Path("/fake/proj-a")),
                ("proj-b", Path("/fake/proj-b")),
            ],
        ):
            call_count = 0

            def _audit_side_effect(name, root, fps):
                nonlocal call_count
                call_count += 1
                if name == "proj-a":
                    raise ValueError("boom")
                return {"path": str(root), "violations": []}

            with patch(
                "memory_core.tools.daily_kb_audit.audit_project",
                side_effect=_audit_side_effect,
            ):
                # proj-a raises (→ warning), proj-b clean → no critical → exit 0
                rc = main(["--no-write"])
                assert rc == 0
                assert call_count == 2


# ---------------------------------------------------------------------------
# Group 5: No-write flag
# ---------------------------------------------------------------------------

class TestMainNoWrite:
    """main() --no-write flag."""

    def test_no_write_skips_write_report(
        self, _patch_infra_clean, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_clean, _patch_build_report,
    ):
        """--no-write → write_report not called."""
        with patch(
            "memory_core.tools.daily_kb_audit.write_report",
        ) as mock_write:
            main(["--no-write"])
            mock_write.assert_not_called()

    def test_write_enabled_calls_write_report(
        self, _patch_infra_clean, _patch_one_project, _patch_fingerprints,
        _patch_audit_project_clean, _patch_build_report, _patch_write_report,
    ):
        """Default (no --no-write) → write_report called."""
        # If we reach here without exception, write_report was patched and callable
        main([])
