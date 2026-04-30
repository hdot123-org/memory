#!/usr/bin/env python3
"""Workbot-specific gateway business policy adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from ..memory_hook_impls import GatewayBusinessPolicyConfig
    from .neutral_policy import NeutralGatewayBusinessPolicy
except ImportError:  # pragma: no cover - script-mode fallback
    from memory_core.tools.memory_hook_adapters.neutral_policy import NeutralGatewayBusinessPolicy  # type: ignore
    from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig  # type: ignore


# Workbot-specific policy overrides injected into the gateway strategy chain.
ADAPTER_POLICIES: dict[str, str] = {
    "legality_source": "active-legal-map-only",
    "registration_commit": "required-after-absorption-complete",
}


class WorkbotGatewayBusinessPolicy(NeutralGatewayBusinessPolicy):
    """Workbot adapter layer over host-neutral business policy."""

    POLICY_PACK_ENV = "MEMORY_HOOK_POLICY_PACK_PATH"
    DEFAULT_POLICY_PACK_PATH = (
        Path(__file__).resolve().parents[2] / "memory" / "kb" / "global" / "memory-hook-policy-pack.json"
    )

    def __init__(
        self,
        config: GatewayBusinessPolicyConfig,
        scope_config_path: Path | None = None,
        policy_pack_path: Path | None = None,
    ):
        # Resolve policy-pack path: explicit param > env var > default file > None
        if policy_pack_path is not None:
            resolved = policy_pack_path
        else:
            env_path = os.environ.get(self.POLICY_PACK_ENV)
            if env_path:
                resolved = Path(env_path).expanduser()
            elif self.DEFAULT_POLICY_PACK_PATH.exists():
                resolved = self.DEFAULT_POLICY_PACK_PATH
            else:
                resolved = None
        self._policy_pack_path: Path | None = resolved
        super().__init__(config=config, scope_config_path=scope_config_path)

    def inject_policy_pack_config(self) -> dict[str, Any]:
        """Return adapter policy values merged with any policy-pack file content."""
        pack_content: dict[str, Any] = {}
        if self._policy_pack_path is not None and self._policy_pack_path.exists():
            try:
                raw = json.loads(self._policy_pack_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    pack_content = raw
            except (OSError, json.JSONDecodeError):
                pass
        # Merge: ADAPTER_POLICIES override pack-level policies when both exist
        merged_policies: dict[str, str] = {}
        if isinstance(pack_content.get("policies"), dict):
            merged_policies.update(pack_content["policies"])
        merged_policies.update(ADAPTER_POLICIES)
        return {
            "schema_version": pack_content.get("schema_version", "m3-policy-pack-v1"),
            "scope": pack_content.get("scope", "workbot"),
            "policies": merged_policies,
            "conflict_strategies": pack_content.get("conflict_strategies", {}),
            "adapter_scope": pack_content.get("adapter_scope", True),
        }

    def resolve_policies(self) -> dict[str, str]:
        """Merge ADAPTER_POLICIES with base gateway policies from the parent class."""
        from memory_core.tools.memory_hook_impls import PolicyRegistryImpl
        base = dict(PolicyRegistryImpl.DEFAULT_POLICIES)
        base.update(ADAPTER_POLICIES)
        return base
