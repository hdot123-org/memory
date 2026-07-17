"""Feature flag framework for memory-core.

Provides environment-variable-driven feature flags with a registry
for defaults and documentation.

Priority order:
    env var (MEMORY_FEATURE_<NAME>) > register_flag default > is_enabled default > False

Truthy values (case-insensitive): 1, true, yes, on
Falsy values (case-insensitive): 0, false, no, off
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Valid flag name pattern: uppercase letters, digits, underscores
_FLAG_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _parse_value(raw: str | None) -> bool | None:
    """Parse an env var string into a boolean.

    Returns:
        True for truthy values (1/true/yes/on, case-insensitive)
        False for falsy values (0/false/no/off, case-insensitive)
        None if raw is None or empty
        False for unknown values (logged at debug level)
    """
    if raw is None or raw.strip() == "":
        return None

    normalized = raw.strip().lower()

    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False

    logger.debug("feature_flags: unknown value %r, treating as falsy", raw)
    return False


@dataclass(frozen=True)
class FeatureFlag:
    """A registered feature flag definition."""
    name: str
    default: bool = False
    description: str = ""


class FeatureFlagRegistry:
    """Central registry for feature flags.

    Stores flag definitions with defaults and descriptions.
    Thread-safe for reads; registration should happen at module import time.
    """

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}

    def register(
        self,
        name: str,
        default: bool = False,
        description: str = "",
    ) -> FeatureFlag:
        """Register a feature flag.

        Args:
            name: Flag name (uppercase, e.g. "NEW_UI")
            default: Default value when env var is not set
            description: Human-readable description

        Returns:
            The registered FeatureFlag

        Raises:
            ValueError: If name is not a valid flag name
        """
        upper = name.upper()
        if not _FLAG_NAME_RE.match(upper):
            raise ValueError(
                f"Invalid flag name {name!r}: must match {_FLAG_NAME_RE.pattern}"
            )
        if upper in self._flags:
            logger.debug("feature_flags: overriding existing flag %s", upper)
        flag = FeatureFlag(name=upper, default=default, description=description)
        self._flags[upper] = flag
        return flag

    def get(self, name: str) -> FeatureFlag | None:
        """Get a registered flag by name (case-insensitive)."""
        return self._flags.get(name.upper())

    def list_flags(self) -> list[FeatureFlag]:
        """Return all registered flags sorted by name."""
        return sorted(self._flags.values(), key=lambda f: f.name)

    def clear(self) -> None:
        """Clear all registered flags (for testing)."""
        self._flags.clear()

    def __len__(self) -> int:
        return len(self._flags)

    def __contains__(self, name: str) -> bool:
        return name.upper() in self._flags


# Global registry instance
_global_registry = FeatureFlagRegistry()


def register_flag(
    name: str,
    default: bool = False,
    description: str = "",
) -> FeatureFlag:
    """Register a feature flag in the global registry.

    Args:
        name: Flag name (e.g. "NEW_UI" -> env var MEMORY_FEATURE_NEW_UI)
        default: Default value when env var is not set
        description: Human-readable description

    Returns:
        The registered FeatureFlag
    """
    return _global_registry.register(name, default=default, description=description)


def list_flags() -> list[FeatureFlag]:
    """List all registered feature flags, sorted by name."""
    return _global_registry.list_flags()


def reset_flags() -> None:
    """Reset the global feature flag registry (for testing)."""
    _global_registry.clear()


def is_enabled(name: str, default: bool | None = None) -> bool:
    """Check if a feature flag is enabled.

    Priority order:
        1. MEMORY_FEATURE_<NAME> env var (highest)
        2. register_flag default (if registered)
        3. is_enabled default arg
        4. False (lowest)

    Args:
        name: Flag name (case-insensitive, e.g. "NEW_UI" or "new_ui")
        default: Fallback default when env var not set and flag not registered

    Returns:
        True if the flag is enabled, False otherwise
    """
    upper = name.upper()
    env_key = f"MEMORY_FEATURE_{upper}"

    # 1. Check env var (highest priority)
    env_val = _parse_value(os.environ.get(env_key))
    if env_val is not None:
        return env_val

    # 2. Check registry default
    registered = _global_registry.get(upper)
    if registered is not None:
        return registered.default

    # 3. Use caller-provided default
    if default is not None:
        return default

    # 4. Ultimate fallback
    return False
