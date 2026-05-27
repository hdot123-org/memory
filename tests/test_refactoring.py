#!/usr/bin/env python3
"""Tests for CoreConfig, ArtifactWriter, and DelegateRouter.

Covers:
- CoreConfig construction, validation, from_gateway_kwargs, optional defaults
- ArtifactWriter JSON writing and error handling
- DelegateRouter routing and noop dispatch
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


def _dummy_callable():
    """Placeholder callable for CoreConfig callback fields."""
    return None


def _make_minimal_core_config_kwargs(tmp_path: Path) -> dict[str, Any]:
    """Build a minimal-but-complete kwargs dict for CoreConfig."""
    base = tmp_path / "memory_core"
    base.mkdir(parents=True, exist_ok=True)

    def _noop(*_a, **_k):
        return None

    return {
        # Group 1: Environment (7)
        "host": "codex",
        "event": "session-start",
        "payload": {"session_id": "abc"},
        "cwd": base,
        "project_scope": "workbot",
        "workspace_root": base,
        "repo_root": base,
        # Group 2: Paths (7)
        "required_canonical": [],
        "project_canonical": {},
        "project_runtime_root": {},
        "global_canonical": [],
        "project_map_governance": base / "governance.md",
        "event_log": base / "events.jsonl",
        "hook_contract_path": base / "contract.md",
        # Group 3: Policy config (8)
        "legality_source_policy": "map-only",
        "registration_commit_policy": "atomic",
        "registration_commit_phase": "declared-not-enforced",
        "project_map_refs": [],
        "surface_id": "surf-1",
        "workspace_id": "ws-1",
        "governance_blocker_scopes": None,
        "event_contract_blocker_scopes": None,
        "core_evidence_refs": None,
        # Group 4: Callbacks (13)
        "extract_excerpt_fn": _noop,
        "now_iso_fn": _noop,
        "write_targets_fn": _noop,
        "validate_project_map_fn": _noop,
        "validate_unique_legal_system_contract_fn": _noop,
        "policy_validate_fn": _noop,
        "get_policy_pack_fn": _noop,
        "governance_frozen_tuple_errors_fn": _noop,
        "event_contract_blocker_errors_fn": _noop,
        "git_registration_probe_fn": _noop,
        "truth_basis_for_scope_fn": _noop,
        "decision_refs_for_scope_fn": _noop,
        "lesson_refs_for_scope_fn": _noop,
        "docs_refs_for_scope_fn": _noop,
    }


# ---------------------------------------------------------------------------
# CoreConfig tests
# ---------------------------------------------------------------------------


class TestCoreConfig:
    """Validate CoreConfig dataclass construction, validation, and factory."""

    def test_core_config_constructs_with_all_fields(self, tmp_path):
        """CoreConfig can be constructed with all 37 fields."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        cfg = CoreConfig(**kwargs)

        # Verify each group
        # Group 1: Environment
        assert cfg.host == "codex"
        assert cfg.event == "session-start"
        assert cfg.payload == {"session_id": "abc"}
        assert cfg.cwd == tmp_path / "memory_core"
        assert cfg.project_scope == "workbot"
        assert cfg.workspace_root == tmp_path / "memory_core"
        assert cfg.repo_root == tmp_path / "memory_core"

        # Group 2: Paths
        assert cfg.required_canonical == []
        assert cfg.project_canonical == {}
        assert cfg.project_runtime_root == {}
        assert cfg.global_canonical == []
        assert cfg.project_map_governance == tmp_path / "memory_core" / "governance.md"
        assert cfg.event_log == tmp_path / "memory_core" / "events.jsonl"
        assert cfg.hook_contract_path == tmp_path / "memory_core" / "contract.md"

        # Group 3: Policy
        assert cfg.legality_source_policy == "map-only"
        assert cfg.registration_commit_policy == "atomic"
        assert cfg.registration_commit_phase == "declared-not-enforced"
        assert cfg.project_map_refs == []
        assert cfg.surface_id == "surf-1"
        assert cfg.workspace_id == "ws-1"

        # Group 4: Callbacks — just confirm they are the same callables
        assert cfg.extract_excerpt_fn is kwargs["extract_excerpt_fn"]
        assert cfg.now_iso_fn is kwargs["now_iso_fn"]
        assert cfg.write_targets_fn is kwargs["write_targets_fn"]

    def test_core_config_rejects_invalid_host(self, tmp_path):
        """CoreConfig raises on invalid host value."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        kwargs["host"] = "invalid"

        with pytest.raises(ValueError, match="host must be"):
            CoreConfig(**kwargs)

    def test_core_config_rejects_empty_event(self, tmp_path):
        """CoreConfig raises on empty event string."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        kwargs["event"] = ""

        with pytest.raises(ValueError, match="event must be"):
            CoreConfig(**kwargs)

    def test_core_config_rejects_non_path_workspace_root(self, tmp_path):
        """CoreConfig raises when workspace_root is not a Path."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        kwargs["workspace_root"] = "/not/a/path"  # type: ignore

        with pytest.raises(TypeError, match="workspace_root must be a Path"):
            CoreConfig(**kwargs)

    def test_core_config_rejects_non_path_repo_root(self, tmp_path):
        """CoreConfig raises when repo_root is not a Path."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        kwargs["repo_root"] = "/not/a/path"  # type: ignore

        with pytest.raises(TypeError, match="repo_root must be a Path"):
            CoreConfig(**kwargs)

    def test_core_config_from_gateway_kwargs(self, tmp_path):
        """from_gateway_kwargs() correctly maps all 37 kwargs."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        cfg = CoreConfig.from_gateway_kwargs(**kwargs)

        assert cfg.host == "codex"
        assert cfg.event == "session-start"
        assert cfg.payload == {"session_id": "abc"}
        assert cfg.project_scope == "workbot"
        assert cfg.surface_id == "surf-1"
        assert cfg.workspace_id == "ws-1"
        assert cfg.legality_source_policy == "map-only"
        assert cfg.registration_commit_phase == "declared-not-enforced"

    def test_core_config_optional_fields_default_to_none(self, tmp_path):
        """governance_blocker_scopes, event_contract_blocker_scopes, core_evidence_refs default to None."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        # Omit the three optional fields
        kwargs.pop("governance_blocker_scopes")
        kwargs.pop("event_contract_blocker_scopes")
        kwargs.pop("core_evidence_refs")

        cfg = CoreConfig(**kwargs)

        assert cfg.governance_blocker_scopes is None
        assert cfg.event_contract_blocker_scopes is None
        assert cfg.core_evidence_refs is None

    def test_core_config_accepts_claude_host(self, tmp_path):
        """CoreConfig accepts 'claude' as a valid host."""
        from memory_core.tools.memory_hook_config import CoreConfig

        kwargs = _make_minimal_core_config_kwargs(tmp_path)
        kwargs["host"] = "claude"
        cfg = CoreConfig(**kwargs)
        assert cfg.host == "claude"


# ---------------------------------------------------------------------------
# ArtifactWriter tests
# ---------------------------------------------------------------------------


class TestArtifactWriter:
    """Validate ArtifactWriter JSON writing and error handling."""

    def test_artifact_writer_creates_context_file(self, tmp_path):
        """ArtifactWriter writes date-partitioned JSON artifacts."""
        from datetime import datetime as real_datetime

        from memory_core.tools.memory_hook_impls import ArtifactWriter

        class FixedDatetime:
            @staticmethod
            def now():
                return real_datetime(2026, 5, 11, 0, 47, 11, 370980)

        context_root = tmp_path / "memory" / "artifacts"
        error_log = tmp_path / "errors.log"
        writer = ArtifactWriter(
            context_root=context_root,
            error_log=error_log,
            datetime_module=FixedDatetime,
        )

        package = {"schema_version": "wb-hook-v2", "host": "codex", "event": "test"}
        writer.write(host="codex", event="test", package=package)

        snapshot = context_root / "2026-05-11" / "20260511T004711370980-codex-test.json"
        latest = context_root / "latest-codex-test.json"
        event_log = context_root.parent / "events" / "2026-05-11.jsonl"
        legacy_event_log = context_root.parent / "events.jsonl"

        assert snapshot.is_file()
        assert latest.is_file()
        assert event_log.is_file()
        assert legacy_event_log.is_file()

        content = json.loads(snapshot.read_text(encoding="utf-8"))
        assert content["host"] == "codex"
        assert content["event"] == "test"
        assert content["artifact_refs"]["snapshot"] == str(snapshot)
        assert content["artifact_refs"]["latest"] == str(latest)
        assert content["artifact_refs"]["event_log"] == str(event_log)
        assert content["artifact_refs"]["legacy_event_log"] == str(legacy_event_log)

    def test_artifact_writer_handles_write_error_gracefully(self, tmp_path):
        """ArtifactWriter logs errors instead of raising."""
        from datetime import datetime as real_datetime

        from memory_core.tools.memory_hook_impls import ArtifactWriter

        context_root = tmp_path / "memory" / "artifacts"
        error_log = tmp_path / "errors.log"

        # Build a fake datetime that raises only on the first now() call
        # (simulating sink.write failing), then succeeds on the second
        # call (inside _log_error).
        call_count = 0

        class FaultyDatetime:
            @staticmethod
            def now():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise OSError("disk full")
                return real_datetime.now()

        writer = ArtifactWriter(
            context_root=context_root,
            error_log=error_log,
            datetime_module=FaultyDatetime,
        )

        package = {"schema_version": "wb-hook-v2"}
        # Should not raise
        writer.write(host="codex", event="test", package=package)

        # Error should be logged to the dated log and legacy compatibility log.
        dated_error_log = error_log.parent / "errors" / f"{real_datetime.now().date().isoformat()}.log"
        assert dated_error_log.exists()
        assert error_log.exists()
        log_text = dated_error_log.read_text(encoding="utf-8")
        assert "ArtifactWriter" in log_text
        assert "disk full" in log_text

    def test_artifact_writer_uses_sink_internally(self, tmp_path):
        """ArtifactWriter delegates to ArtifactSinkImpl for actual writing."""
        from memory_core.tools.memory_hook_impls import ArtifactWriter

        context_root = tmp_path / "memory" / "artifacts"
        error_log = tmp_path / "errors.log"
        writer = ArtifactWriter(context_root=context_root, error_log=error_log)

        # Internal sink should be present
        assert writer._sink is not None
        assert writer.context_root == context_root
        assert writer.error_log == error_log


# ---------------------------------------------------------------------------
# DelegateRouter tests
# ---------------------------------------------------------------------------


class TestDelegateRouter:
    """Validate DelegateRouter routing and noop dispatch."""

    def _make_fake_delegate(self):
        """Create a mock delegate that records calls."""
        delegate = MagicMock()
        delegate.execute.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok\n", stderr=""
        )
        delegate.noop_response.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="noop\n", stderr=""
        )
        return delegate

    def test_delegate_router_routes_to_codex(self):
        """DelegateRouter calls codex_delegate.execute for host='codex'."""
        from memory_core.tools.memory_hook_impls import DelegateRouter

        codex = self._make_fake_delegate()
        claude = self._make_fake_delegate()
        router = DelegateRouter(codex_delegate=codex, claude_delegate=claude)

        result = router.route(
            host="codex",
            event="session-start",
            raw_payload='{"key": "val"}',
            payload={"key": "val"},
        )

        codex.execute.assert_called_once_with(
            "session-start", '{"key": "val"}', {"key": "val"}
        )
        claude.execute.assert_not_called()
        assert result.returncode == 0

    def test_delegate_router_routes_to_claude(self):
        """DelegateRouter calls claude_delegate.execute for host='claude'."""
        from memory_core.tools.memory_hook_impls import DelegateRouter

        codex = self._make_fake_delegate()
        claude = self._make_fake_delegate()
        router = DelegateRouter(codex_delegate=codex, claude_delegate=claude)

        result = router.route(
            host="claude",
            event="file-change",
            raw_payload="{}",
            payload={},
        )

        claude.execute.assert_called_once_with("file-change", "{}", {})
        codex.execute.assert_not_called()
        assert result.returncode == 0

    def test_delegate_router_rejects_unknown_host(self):
        """DelegateRouter raises ValueError for unknown host."""
        from memory_core.tools.memory_hook_impls import DelegateRouter

        codex = self._make_fake_delegate()
        claude = self._make_fake_delegate()
        router = DelegateRouter(codex_delegate=codex, claude_delegate=claude)

        with pytest.raises(ValueError, match="unknown host"):
            router.route(host="unknown", event="x", raw_payload="", payload={})

    def test_delegate_router_noop_codex(self):
        """DelegateRouter calls codex_delegate.noop_response for host='codex'."""
        from memory_core.tools.memory_hook_impls import DelegateRouter

        codex = self._make_fake_delegate()
        claude = self._make_fake_delegate()
        router = DelegateRouter(codex_delegate=codex, claude_delegate=claude)

        result = router.noop(host="codex")

        codex.noop_response.assert_called_once()
        claude.noop_response.assert_not_called()
        assert result.stdout == "noop\n"

    def test_delegate_router_noop_claude(self):
        """DelegateRouter calls claude_delegate.noop_response for host='claude'."""
        from memory_core.tools.memory_hook_impls import DelegateRouter

        codex = self._make_fake_delegate()
        claude = self._make_fake_delegate()
        router = DelegateRouter(codex_delegate=codex, claude_delegate=claude)

        result = router.noop(host="claude")

        claude.noop_response.assert_called_once()
        codex.noop_response.assert_not_called()
        assert result.stdout == "noop\n"

    def test_delegate_router_noop_rejects_unknown_host(self):
        """DelegateRouter raises ValueError for unknown host in noop()."""
        from memory_core.tools.memory_hook_impls import DelegateRouter

        codex = self._make_fake_delegate()
        claude = self._make_fake_delegate()
        router = DelegateRouter(codex_delegate=codex, claude_delegate=claude)

        with pytest.raises(ValueError, match="unknown host"):
            router.noop(host="unknown")

    def test_delegate_router_stores_delegates(self):
        """DelegateRouter stores references to both delegates."""
        from memory_core.tools.memory_hook_impls import DelegateRouter

        codex = self._make_fake_delegate()
        claude = self._make_fake_delegate()
        router = DelegateRouter(codex_delegate=codex, claude_delegate=claude)

        assert router.codex_delegate is codex
        assert router.claude_delegate is claude
