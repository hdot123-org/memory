#!/usr/bin/env python3
"""Tests for VAL-TEL-001/002/003: missing canonical files severity fix.

Verifies:
- VAL-TEL-001: Missing canonical files (truth-model.md, memory-system.md,
  memory-routing.md) no longer trigger degraded status.
- VAL-TEL-002: Missing canonical files appear in warnings, not errors.
- VAL-TEL-003: Real errors still produce degraded status.
"""


import os
from pathlib import Path

from tests.context_package_helpers import _make_minimal_kwargs

os.environ.setdefault("MEMORY_HOOK_ADAPTER", "default")


class TestMissingCanonicalFilesSeverityFix:
    """VAL-TEL-001/002/003: canonical files missing should be warnings, not errors."""

    def test_missing_canonical_files_status_ok(self, tmp_path: Path) -> None:
        """VAL-TEL-001: When only canonical files are missing, status should be ok."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path, create_project_file=True)
        # Create the project file so it doesn't trigger degraded
        proj_file = kwargs["project_canonical"]["workbot"]
        proj_file.parent.mkdir(parents=True, exist_ok=True)
        proj_file.write_text("# Project\n", encoding="utf-8")

        # Add the three canonical files that are typically missing in consumer projects
        canonical_dir = tmp_path / "memory_core" / "memory" / "kb" / "global"
        kwargs["required_canonical"] = [
            canonical_dir / "truth-model.md",
            canonical_dir / "memory-system.md",
            canonical_dir / "memory-routing.md",
        ]

        result = build_context_package_core(**kwargs)

        assert result["status"] == "ok", (
            f"Expected status 'ok' when only canonical files are missing, "
            f"got '{result['status']}'"
        )

    def test_missing_canonical_files_in_warnings(self, tmp_path: Path) -> None:
        """VAL-TEL-002: Missing canonical files appear in warnings, not in error lists."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path, create_project_file=True)
        canonical_dir = tmp_path / "memory_core" / "memory" / "kb" / "global"
        kwargs["required_canonical"] = [
            canonical_dir / "truth-model.md",
            canonical_dir / "memory-system.md",
        ]

        result = build_context_package_core(**kwargs)

        # Missing canonical files should be in warnings
        assert "warnings" in result, "Result should contain a 'warnings' field"
        assert len(result["warnings"]) > 0, "Warnings should contain missing canonical file entries"

        # Missing canonical files should NOT be in missing_paths (which feeds degraded)
        for path_str in result.get("missing_paths", []):
            assert "truth-model.md" not in path_str, (
                "truth-model.md should not be in missing_paths"
            )
            assert "memory-system.md" not in path_str, (
                "memory-system.md should not be in missing_paths"
            )

        # validation_errors should not contain canonical-file-missing entries
        for err in result.get("validation_errors", []):
            assert "truth-model.md" not in err
            assert "memory-system.md" not in err

    def test_real_errors_still_degraded(self, tmp_path: Path) -> None:
        """VAL-TEL-003: Real errors still produce degraded status."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path, create_project_file=True)
        # Inject a real error via project_map validation
        kwargs["validate_project_map_fn"] = lambda: ["project map validation failed"]

        result = build_context_package_core(**kwargs)

        assert result["status"] == "degraded", (
            f"Expected status 'degraded' when real errors exist, "
            f"got '{result['status']}'"
        )

    def test_non_canonical_missing_still_degraded(self, tmp_path: Path) -> None:
        """Non-canonical missing paths should still trigger degraded status."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path, create_project_file=True)
        # Add a non-canonical missing file
        kwargs["required_canonical"] = [tmp_path / "some" / "other" / "file.md"]

        result = build_context_package_core(**kwargs)

        assert result["status"] == "degraded", (
            f"Expected status 'degraded' when non-canonical file is missing, "
            f"got '{result['status']}'"
        )

    def test_payload_schema_backward_compatible(self, tmp_path: Path) -> None:
        """VAL-CROSS-002: Payload schema retains all existing fields plus new ones."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        kwargs = _make_minimal_kwargs(tmp_path, create_project_file=True)
        result = build_context_package_core(**kwargs)

        # Verify all original fields are present (backward compatibility)
        required_original_fields = [
            "schema_version",
            "generated_at",
            "host",
            "event",
            "repo_root",
            "workspace_root",
            "cwd",
            "project_scope",
            "status",
            "missing_paths",
            "validation_errors",
            "system_context",
        ]
        for field in required_original_fields:
            assert field in result, f"Original field '{field}' must be present in payload"

        # Verify new field is also present
        assert "warnings" in result, "New 'warnings' field must be present in payload"

        # Verify field types are correct
        assert isinstance(result["schema_version"], str)
        assert isinstance(result["host"], str)
        assert isinstance(result["event"], str)
        assert isinstance(result["status"], str)
        assert isinstance(result["missing_paths"], list)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["validation_errors"], list)


class TestMetricsIsolation:
    """VAL-CROSS-003: Coverage tests do not produce stray telemetry events."""

    def test_build_context_package_no_metrics_side_effect(self, tmp_path: Path) -> None:
        """build_context_package_core does not emit metrics (gateway does)."""
        from memory_core.tools.memory_hook_core import build_context_package_core

        # Record metrics file state before
        metrics_path = tmp_path / "test_artifacts" / "memory-hook" / "metrics.jsonl"
        assert not metrics_path.exists()

        kwargs = _make_minimal_kwargs(tmp_path, create_project_file=True)
        build_context_package_core(**kwargs)

        # build_context_package_core should not create any metrics file
        assert not metrics_path.exists(), (
            "build_context_package_core must not emit metrics (gateway does that)"
        )

    def test_metrics_disabled_env_suppresses_output(self, tmp_path: Path, monkeypatch) -> None:
        """VAL-CROSS-005: MEMORY_HOOK_METRICS_DISABLED=1 suppresses metrics."""
        from memory_core.tools.memory_hook_metrics import emit_metrics, is_metrics_disabled

        monkeypatch.setenv("MEMORY_HOOK_METRICS_DISABLED", "1")
        assert is_metrics_disabled() is True

        metrics_path = tmp_path / "memory-hook" / "metrics.jsonl"
        result = emit_metrics(
            artifact_root=tmp_path,
            host="factory",
            event="session-start",
            package={"status": "ok"},
            duration_ms=42,
        )
        assert result is None
        assert not metrics_path.exists()

        # Cleanup env
        monkeypatch.delenv("MEMORY_HOOK_METRICS_DISABLED")
