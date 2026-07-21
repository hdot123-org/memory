#!/usr/bin/env python3
"""Extended tests for memory_hook_provider_rollback.

Covers: healthy-system full structure, each probe independently toggled,
gateway exceptions, env-var behavior, and return-type validation.
Does not duplicate test_validate_memory_system.py or the M6 batch-3 rollback tests.
"""


import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import memory_hook_gateway as gateway
from memory_core.tools import memory_hook_provider_rollback as rollback

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = frozenset(
    [
        "status",
        "requested_provider",
        "external_probe_provider",
        "external_probe_errors",
        "external_probe_ok",
        "legacy_probe_provider",
        "legacy_probe_errors",
        "legacy_probe_ok",
        "rollback_target",
    ]
)


def _fake_resolve_map(answer_map: dict[str, tuple[str, Any, list[str]]]):
    """Return a _resolve_core_builder shim that looks up by the exact provider string."""
    def shim(provider: str, *, allow_fallback: bool = True):
        hit = answer_map.get(provider)
        if hit is not None:
            return hit
        return "legacy", gateway.build_context_package_core, []
    return shim


def _fake_resolve_raises(exception_map: dict[str, Exception]):
    """Return a shim that raises on specified provider strings, delegates otherwise."""
    def shim(provider: str, *, allow_fallback: bool = True):
        exc = exception_map.get(provider)
        if exc is not None:
            raise exc
        return "legacy", gateway.build_context_package_core, []
    return shim


# ---------------------------------------------------------------------------
# 1. Healthy system — both probes pass
# ---------------------------------------------------------------------------

def test_healthy_system_both_probes_pass(monkeypatch):
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    monkeypatch.setenv("MEMORY_HOOK_CORE_PROVIDER", "legacy")

    result = rollback.run_rollback_drill()

    assert result["status"] == "passed"
    assert result["external_probe_ok"] is True
    assert result["legacy_probe_ok"] is True
    assert result["rollback_target"] == "legacy"
    assert result["requested_provider"] == "legacy"


def test_healthy_system_returns_all_keys(monkeypatch):
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    result = rollback.run_rollback_drill()
    assert set(result.keys()) == _EXPECTED_KEYS


def test_healthy_system_return_types(monkeypatch):
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    result = rollback.run_rollback_drill()
    assert isinstance(result["status"], str)
    assert isinstance(result["requested_provider"], str)
    assert isinstance(result["external_probe_provider"], str)
    assert isinstance(result["external_probe_errors"], list)
    assert isinstance(result["external_probe_ok"], bool)
    assert isinstance(result["legacy_probe_provider"], str)
    assert isinstance(result["legacy_probe_errors"], list)
    assert isinstance(result["legacy_probe_ok"], bool)
    assert isinstance(result["rollback_target"], str)


# ---------------------------------------------------------------------------
# 2. Individual probe tests — external-core pass / fail
# ---------------------------------------------------------------------------

def test_external_core_probe_pass(monkeypatch):
    """external-core available: returns 'external-core' with no errors."""
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    result = rollback.run_rollback_drill()
    assert result["external_probe_provider"] == "external-core"
    assert result["external_probe_errors"] == []
    assert result["external_probe_ok"] is True


def test_external_core_probe_missing(monkeypatch):
    """external-core unavailable: falls back to legacy with error message."""
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("legacy", gateway.build_context_package_core, ["external-core load failed, fallback to legacy"]),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    result = rollback.run_rollback_drill()
    assert result["external_probe_provider"] == "legacy"
    assert result["external_probe_errors"]
    assert result["external_probe_ok"] is False


# ---------------------------------------------------------------------------
# 3. Individual probe tests — legacy pass / fail
# ---------------------------------------------------------------------------

def test_legacy_probe_pass(monkeypatch):
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    result = rollback.run_rollback_drill()
    assert result["legacy_probe_provider"] == "legacy"
    assert result["legacy_probe_errors"] == []
    assert result["legacy_probe_ok"] is True


def test_legacy_probe_fails_status_failed(monkeypatch):
    """Legacy unavailable => overall status is 'failed' (legacy_probe_ok gates passed)."""
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("external-core", gateway.build_context_package_core, ["legacy broken"]),
        }),
    )
    result = rollback.run_rollback_drill()
    assert result["status"] == "failed"
    assert result["legacy_probe_ok"] is False
    assert result["legacy_probe_provider"] == "external-core"


def test_legacy_probe_returns_wrong_name(monkeypatch):
    """Legacy probe returns a wrong provider name => legacy_probe_ok is False."""
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("some-other", gateway.build_context_package_core, []),
        }),
    )
    result = rollback.run_rollback_drill()
    assert result["legacy_probe_ok"] is False
    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# 4. Boundary: gateway raises exception during resolution
# ---------------------------------------------------------------------------

def test_external_core_resolve_raises(monkeypatch):
    """If _resolve_core_builder raises on external-core, the except path sets
    external_provider='external-core' and captures the error."""
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_raises({"external-core": ImportError("no module")}),
    )
    result = rollback.run_rollback_drill()
    assert result["external_probe_provider"] == "external-core"
    assert result["external_probe_errors"]
    assert "no module" in result["external_probe_errors"][0]
    assert result["external_probe_ok"] is False


def test_legacy_resolve_raises(monkeypatch):
    """If _resolve_core_builder raises on legacy, the except path captures it."""
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_raises({"legacy": RuntimeError("legacy crashed")}),
    )
    result = rollback.run_rollback_drill()
    assert result["legacy_probe_provider"] == "legacy"
    assert result["legacy_probe_errors"]
    assert "legacy crashed" in result["legacy_probe_errors"][0]
    assert result["legacy_probe_ok"] is False
    # Both probes fail => status failed
    assert result["status"] == "failed"


def test_both_resolve_raises(monkeypatch):
    """Both probes raise => status failed, both error lists non-empty."""
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_raises({
            "external-core": ImportError("ext missing"),
            "legacy": RuntimeError("legacy broken"),
        }),
    )
    result = rollback.run_rollback_drill()
    assert result["status"] == "failed"
    assert result["external_probe_ok"] is False
    assert result["legacy_probe_ok"] is False
    assert result["external_probe_errors"]
    assert result["legacy_probe_errors"]


# ---------------------------------------------------------------------------
# 5. Environment variable behavior
# ---------------------------------------------------------------------------

def test_requested_provider_from_env(monkeypatch):
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    monkeypatch.setenv("MEMORY_HOOK_CORE_PROVIDER", "external-core")
    result = rollback.run_rollback_drill()
    assert result["requested_provider"] == "external-core"


def test_requested_provider_default(monkeypatch):
    """No env var set => defaults to 'legacy'."""
    monkeypatch.delenv("MEMORY_HOOK_CORE_PROVIDER", raising=False)
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    result = rollback.run_rollback_drill()
    assert result["requested_provider"] == "legacy"


# ---------------------------------------------------------------------------
# 6. main() exit codes
# ---------------------------------------------------------------------------

def test_main_returns_zero_on_passed(monkeypatch):
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("legacy", gateway.build_context_package_core, []),
        }),
    )
    assert rollback.main() == 0


def test_main_returns_nonzero_on_failed(monkeypatch):
    monkeypatch.setattr(
        rollback.gateway, "_resolve_core_builder",
        _fake_resolve_map({
            "external-core": ("external-core", gateway.build_context_package_core, []),
            "legacy": ("external-core", gateway.build_context_package_core, ["no legacy"]),
        }),
    )
    assert rollback.main() != 0
