# -*- coding: utf-8 -*-
"""
Unified exception hierarchy for memory-core domain errors.

Replaces ValueError catch-all with specific domain exceptions that
consumer projects can precisely catch.

Part of REF-001 strangler fig scaffold phase.
"""

from typing import Any


class MemoryCoreError(Exception):
    """Base class for all memory-core domain exceptions.

    Consumer projects can catch this base to capture all memory-core
    business exceptions.
    """


# --- Rule domain exceptions ---


class RuleViolationError(MemoryCoreError):
    """Rule validation failure (corresponds to RuleResult.severity='block')."""

    def __init__(self, rule_name: str, message: str, detail: dict[str, Any] | None = None):
        self.rule_name = rule_name
        self.detail: dict[str, Any] = detail or {}
        super().__init__(f"[{rule_name}] {message}")


class OwnershipError(MemoryCoreError):
    """Path ownership violation (protected path write attempt)."""


class GuardBlockError(MemoryCoreError):
    """Tool interception (pretooluse_guard rejected operation)."""

    def __init__(self, tool: str, reason: str, path: str = ""):
        self.tool = tool
        self.reason = reason
        self.path = path
        super().__init__(f"blocked {tool}: {reason}")


class PolicyViolationError(MemoryCoreError):
    """Business policy violation (project-map / frozen-tuple / event-contract validation failure)."""


# --- Configuration domain exceptions ---


class UnsupportedScopeError(MemoryCoreError):
    """Unsupported scope (replaces ValueError)."""


class UnknownHostError(MemoryCoreError):
    """Unknown host (replaces ValueError)."""


class UnknownRouteKindError(MemoryCoreError):
    """Unsupported route kind (replaces ValueError)."""
