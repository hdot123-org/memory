#!/usr/bin/env python3
"""Host-neutral gateway business policy layer."""

from __future__ import annotations

from pathlib import Path

try:
    from ..memory_hook_impls import GatewayBusinessPolicyConfig, GatewayBusinessPolicyImpl
except ImportError:  # pragma: no cover - script-mode fallback
    from workspace.tools.memory_hook_impls import GatewayBusinessPolicyConfig, GatewayBusinessPolicyImpl  # type: ignore


class NeutralGatewayBusinessPolicy(GatewayBusinessPolicyImpl):
    """Host-neutral default business policy implementation."""

    def __init__(
        self,
        config: GatewayBusinessPolicyConfig,
        scope_config_path: Path | None = None,
    ):
        super().__init__(config=config, scope_config_path=scope_config_path)
