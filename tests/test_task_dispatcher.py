"""Tests for task_dispatcher — resilient task delivery with long-prompt fallback."""

import os

from memory_core.tools.task_dispatcher import (
    MAX_INLINE_CHARS,
    TaskDispatcher,
    TaskResult,
)


class _MockDispatcher(TaskDispatcher):
    """TaskDispatcher with _call_task_tool mocked out."""

    def __init__(self, fail_inline: bool = False) -> None:
        super().__init__()
        self._fail_inline = fail_inline
        self.call_count = 0

    def _call_task_tool(self, prompt: str) -> str:
        self.call_count += 1
        if self._fail_inline and "instructions are in" not in prompt:
            raise Exception("Prompt truncated by runtime")
        return f"mock output #{self.call_count}"


class TestTaskDispatcher:
    def test_inline_dispatch_for_short_prompt(self) -> None:
        d = _MockDispatcher()
        result = d.dispatch("short task")
        assert result.success is True
        assert result.method == "inline"
        assert result.prompt_chars == 10

    def test_file_based_dispatch_for_long_prompt(self) -> None:
        d = _MockDispatcher()
        prompt = "x" * (MAX_INLINE_CHARS + 1)
        result = d.dispatch(prompt, task_name="big")
        assert result.success is True
        assert result.method == "file_based"

    def test_force_file_based(self) -> None:
        d = _MockDispatcher()
        result = d.dispatch("short", force_file_based=True)
        assert result.method == "file_based"

    def test_inline_failure_triggers_file_fallback(self) -> None:
        d = _MockDispatcher(fail_inline=True)
        result = d.dispatch("medium task")
        assert result.method == "file_based"
        assert result.success is True

    def test_task_counter_increments(self) -> None:
        d = _MockDispatcher()
        d.dispatch("a")
        d.dispatch("b")
        assert d.task_counter == 2
        assert len(d.results) == 2

    def test_results_recorded(self) -> None:
        d = _MockDispatcher()
        d.dispatch("task1")
        assert len(d.results) == 1
        assert isinstance(d.results[0], TaskResult)

    def test_cleanup_removes_workspace(self) -> None:
        d = _MockDispatcher()
        ws = d.workspace
        assert os.path.exists(ws)
        d.cleanup()
        assert not os.path.exists(ws)

    def test_get_summary(self) -> None:
        d = _MockDispatcher()
        d.dispatch("a")
        d.dispatch("b")
        summary = d.get_summary()
        assert "Total tasks: 2" in summary
        assert "Inline: 2" in summary

    def test_file_based_writes_instructions(self) -> None:
        d = _MockDispatcher()
        prompt = "x" * (MAX_INLINE_CHARS + 1)
        d.dispatch(prompt, task_name="filetest")
        # instructions.md should exist somewhere in workspace
        found = False
        for root, _dirs, files in os.walk(d.workspace):
            if "instructions.md" in files:
                found = True
                break
        assert found is True
        d.cleanup()
