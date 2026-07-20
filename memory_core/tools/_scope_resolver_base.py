"""Shared scope resolution base class."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from ._rule_helpers import _path_is_under_lexical
except ImportError:
    from _rule_helpers import _path_is_under_lexical  # type: ignore

if TYPE_CHECKING:
    from .memory_hook_impls import GatewayBusinessPolicyConfig


class ScopeResolverBase:
    """Resolves project scope from cwd and manages scope overrides."""

    SCOPE_CONFIG_PATH_ENV = "MEMORY_HOOK_SCOPE_CONFIG_PATH"

    def __init__(
        self,
        config: GatewayBusinessPolicyConfig,
        scope_config_path: Path | None = None,
    ):
        self._config = config
        self._scope_config_path: Path | None = scope_config_path
        if scope_config_path is None:
            env_path = os.environ.get(self.SCOPE_CONFIG_PATH_ENV)
            self._scope_config_path = Path(env_path).expanduser() if env_path else None
        self._scope_overrides: dict[str, dict[str, str]] = self._load_scope_overrides()

    def _load_scope_overrides(self) -> dict[str, dict[str, str]]:
        path = self._scope_config_path
        if path is None or not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}

        result: dict[str, dict[str, str]] = {}
        for key in ("project_canonical", "project_runtime_root"):
            raw = payload.get(key)
            if not isinstance(raw, dict):
                continue
            scoped: dict[str, str] = {}
            for scope, value in raw.items():
                if isinstance(scope, str) and isinstance(value, str):
                    scoped[scope] = value
            if scoped:
                result[key] = scoped
        return result

    def _resolve_override_path(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        if path.is_absolute():
            return path
        return (self._config.repo_root / path).resolve()

    def determine_project_scope(self, cwd: Path) -> str:
        cfg = self._config
        if not _path_is_under_lexical(cwd, cfg.repo_root):
            return cfg.default_project_scope
        for scope, roots in cfg.scope_match_hints.items():
            for root in roots:
                if _path_is_under_lexical(cwd, root):
                    return scope
        return cfg.default_project_scope

    def get_project_canonical(self) -> dict[str, Path]:
        merged = dict(self._config.project_canonical)
        overrides = self._scope_overrides.get("project_canonical", {})
        for scope, raw in overrides.items():
            merged[scope] = self._resolve_override_path(raw)
        return merged

    def get_project_runtime_root(self) -> dict[str, Path]:
        merged = dict(self._config.project_runtime_root)
        overrides = self._scope_overrides.get("project_runtime_root", {})
        for scope, raw in overrides.items():
            merged[scope] = self._resolve_override_path(raw)
        return merged

    def get_required_canonical(self) -> list[Path]:
        return list(self._config.required_canonical)

    def get_global_canonical(self) -> list[Path]:
        return list(self._config.global_canonical)

    def project_map_refs(self) -> list[str]:
        return [str(path) for path in self._config.project_map_files]
