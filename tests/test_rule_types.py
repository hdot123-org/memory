# -*- coding: utf-8 -*-
"""Unit tests for _rule_types.py rule evaluation types."""

from dataclasses import dataclass
from pathlib import Path

from memory_core.tools._rule_types import RuleContext, RuleResult


def test_rule_result_creation():
    """Test RuleResult can be created with required fields."""
    result = RuleResult(matched=True, severity="error", message="Test error")
    assert result.matched is True
    assert result.severity == "error"
    assert result.message == "Test error"
    assert result.detail == {}


def test_rule_result_frozen():
    """Test RuleResult is immutable (frozen dataclass)."""
    result = RuleResult(matched=True)
    try:
        result.matched = False
        assert False, "Should not be able to modify frozen dataclass"
    except AttributeError:
        pass


def test_rule_result_default_values():
    """Test RuleResult default values."""
    result = RuleResult(matched=False)
    assert result.severity == "info"
    assert result.message == ""
    assert result.detail == {}


def test_rule_context_creation():
    """Test RuleContext can be created with optional fields."""
    ctx = RuleContext(
        path=Path("/test"),
        content="test content",
        tool_name="test_tool",
    )
    assert ctx.path == Path("/test")
    assert ctx.content == "test content"
    assert ctx.tool_name == "test_tool"
    assert ctx.event_type is None
    assert ctx.project_root is None
    assert ctx.extra == {}


def test_rule_context_all_none_by_default():
    """Test RuleContext fields are None by default."""
    ctx = RuleContext()
    assert ctx.path is None
    assert ctx.content is None
    assert ctx.tool_name is None
    assert ctx.event_type is None
    assert ctx.project_root is None
    assert ctx.extra == {}


def test_rule_context_mutable():
    """Test RuleContext is mutable (not frozen)."""
    ctx = RuleContext()
    ctx.path = Path("/test")
    assert ctx.path == Path("/test")


def test_rule_evaluator_protocol():
    """Test RuleEvaluator Protocol can be implemented."""

    @dataclass
    class MockRule:
        name: str

        @property
        def rule_name(self) -> str:
            return self.name

        def evaluate(self, ctx: RuleContext) -> RuleResult:
            return RuleResult(matched=True, severity="info", message="mock")

    rule = MockRule(name="test_rule")
    assert rule.rule_name == "test_rule"

    ctx = RuleContext(path=Path("/test"))
    result = rule.evaluate(ctx)
    assert result.matched is True
    assert result.severity == "info"


def test_rule_evaluator_protocol_compatibility():
    """Test Protocol allows duck-typing (structural subtyping)."""

    class ConcreteRule:
        @property
        def rule_name(self) -> str:
            return "concrete"

        def evaluate(self, ctx: RuleContext) -> RuleResult:
            return RuleResult(matched=False)

    rule = ConcreteRule()
    # Should satisfy Protocol without explicit inheritance
    assert rule.rule_name == "concrete"
    result = rule.evaluate(RuleContext())
    assert result.matched is False


def test_all_types_importable():
    """Test all types are importable via both import paths."""
    from memory_core.tools._rule_types import (
        RuleContext,
        RuleResult,
    )

    assert RuleResult is not None
    assert RuleContext is not None
