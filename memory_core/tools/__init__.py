"""memory-core public API."""

from typing import Any

# Lazy imports to avoid heavy module loading
__all__ = [
    "build_context_package",
    "build_context_package_simple",
    "CoreConfig",
    "build_context_package_from_config",
]

def __getattr__(name: str) -> Any:
    if name == "build_context_package":
        from memory_core.tools.memory_hook_gateway import build_context_package
        return build_context_package
    if name == "build_context_package_simple":
        from memory_core.tools.memory_hook_gateway import build_context_package_simple
        return build_context_package_simple
    if name == "CoreConfig":
        from memory_core.tools.memory_hook_config import CoreConfig
        return CoreConfig
    if name == "build_context_package_from_config":
        from memory_core.tools.memory_hook_core import build_context_package_from_config
        return build_context_package_from_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
