#!/usr/bin/env python3
"""Workbot-specific gateway business policy adapter."""

from __future__ import annotations

from pathlib import Path

try:
    from .neutral_policy import NeutralGatewayBusinessPolicy
    from ..memory_hook_impls import GatewayBusinessPolicyConfig
except ImportError:  # pragma: no cover - script-mode fallback
    from workspace.tools.memory_hook_adapters.neutral_policy import NeutralGatewayBusinessPolicy  # type: ignore
    from workspace.tools.memory_hook_impls import GatewayBusinessPolicyConfig  # type: ignore


class WorkbotGatewayBusinessPolicy(NeutralGatewayBusinessPolicy):
    """Workbot adapter layer over host-neutral business policy."""

    def __init__(
        self,
        config: GatewayBusinessPolicyConfig,
        scope_config_path: Path | None = None,
    ):
        super().__init__(config=config, scope_config_path=scope_config_path)
