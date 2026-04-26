"""memory-core public API."""
from __future__ import annotations

# Lazy imports to avoid heavy module loading
__all__ = [
    "build_context_package",
    "build_context_package_simple",
    "CoreConfig",
    "build_context_package_from_config",
]

def __getattr__(name: str):
    if name == "build_context_package":
        from workspace.tools.memory_hook_gateway import build_context_package
        return build_context_package
    if name == "build_context_package_simple":
        from workspace.tools.memory_hook_gateway import build_context_package_simple
        return build_context_package_simple
    if name == "CoreConfig":
        from workspace.tools.memory_hook_config import CoreConfig
        return CoreConfig
    if name == "build_context_package_from_config":
        from workspace.tools.memory_hook_core import build_context_package_from_config
        return build_context_package_from_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
