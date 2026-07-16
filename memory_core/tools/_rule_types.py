# -*- coding: utf-8 -*-
"""
Unified rule evaluation types and protocols.

Defines RuleResult, RuleContext, and RuleEvaluator Protocol for consistent
rule evaluation across all rule implementations.

Part of REF-001 strangler fig scaffold phase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RuleResult:
    """Unified return type for all rule evaluations.

    Attributes:
        matched: Whether the rule matched/triggered
        severity: Severity level (info | warning | error | block)
        message: Human-readable description
        detail: Machine-readable supplementary data
    """
    matched: bool
    severity: str = "info"
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleContext:
    """Unified input context for rule evaluation.

    Callers populate fields as needed; rules only read what they require.

    Attributes:
        path: Path for path-based rules (ownership/denylist/guard)
        content: Content for content-based rules (business_policy/consistency)
        tool_name: Tool name for tool interception rules (pretooluse_guard)
        event_type: Event type for event mapping rules (hook_event)
        project_root: Project root context
        extra: Extension slot for additional context
    """
    path: Path | None = None
    content: str | None = None
    tool_name: str | None = None
    event_type: str | None = None
    project_root: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class RuleEvaluator(Protocol):
    """Protocol for rule evaluation - unified interface for all rule implementations.

    Evolved from PolicyRegistry.validate(context) - but validate is a monolithic method
    containing all validation logic. RuleEvaluator splits it into independent composable units.
    """

    @property
    def rule_name(self) -> str:
        """Stable identifier for metrics/logging."""
        ...

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        """Evaluate the rule against given context, return result.

        Pure function - does not perform I/O.
        """
        ...
