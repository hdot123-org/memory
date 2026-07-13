"""Tests for resilient_orchestrator — validation + dispatch + auto-retry."""
from __future__ import annotations

from memory_core.tools.prompt_validator import MAX_PROMPT_CHARS
from memory_core.tools.resilient_orchestrator import ResilientOrchestrator
from memory_core.tools.task_dispatcher import TaskDispatcher


class _MockDispatcher(TaskDispatcher):
    """TaskDispatcher that optionally fails N inline calls before succeeding."""

    def __init__(self, fail_inline_times: int = 0) -> None:
        super().__init__()
        self._fail_remaining = fail_inline_times
        self.total_calls = 0

    def _call_task_tool(self, prompt: str) -> str:
        self.total_calls += 1
        if self._fail_remaining > 0 and "instructions are in" not in prompt:
            self._fail_remaining -= 1
            raise Exception("inline failed")
        return "ok"


class TestResilientOrchestrator:
    def test_dispatch_safe_prompt(self) -> None:
        mock = _MockDispatcher()
        orch = ResilientOrchestrator(dispatcher=mock)
        result = orch.dispatch_task("simple task")
        assert result.success is True
        assert result.method == "inline"
        assert mock.total_calls == 1

    def test_unsafe_prompt_goes_file_based(self) -> None:
        mock = _MockDispatcher()
        orch = ResilientOrchestrator(dispatcher=mock)
        prompt = "x" * (MAX_PROMPT_CHARS + 1)
        result = orch.dispatch_task(prompt, task_name="big")
        assert result.method == "file_based"

    def test_retry_on_failure(self) -> None:
        mock = _MockDispatcher(fail_inline_times=1)
        orch = ResilientOrchestrator(dispatcher=mock)
        result = orch.dispatch_task("task that fails first time")
        assert result.success is True
        # Should have retried via file-based
        assert mock.total_calls >= 2

    def test_max_retries(self) -> None:
        mock = _MockDispatcher(fail_inline_times=99)
        orch = ResilientOrchestrator(dispatcher=mock)
        assert orch.max_retries == 2
        result = orch.dispatch_task("always fails inline")
        # After inline fails, 2 retries via file_based (which succeed in mock)
        assert result.success is True

    def test_cleanup(self) -> None:
        mock = _MockDispatcher()
        orch = ResilientOrchestrator(dispatcher=mock)
        import os
        assert os.path.exists(mock.workspace)
        orch.cleanup()
        assert not os.path.exists(mock.workspace)

    def test_summary(self) -> None:
        mock = _MockDispatcher()
        orch = ResilientOrchestrator(dispatcher=mock)
        orch.dispatch_task("a")
        summary = orch.summary()
        assert "Total tasks" in summary

    def test_default_dispatcher_created(self) -> None:
        orch = ResilientOrchestrator()
        assert orch.dispatcher is not None
        orch.cleanup()
