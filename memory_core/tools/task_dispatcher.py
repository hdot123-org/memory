"""
Resilient task dispatcher that automatically handles long prompts
by falling back to file-based instruction delivery.
"""

import os
import shutil
import tempfile
from dataclasses import dataclass

# Safe character limit for inline prompts (adjust based on actual limit)
MAX_INLINE_CHARS = 40_000
# Warning threshold (80% of max)
WARNING_THRESHOLD = 32_000


@dataclass
class TaskResult:
    success: bool
    output: str
    method: str  # "inline" or "file_based"
    prompt_chars: int
    error: str | None = None


class TaskDispatcher:
    """Dispatches tasks to subagents with automatic fallback for long prompts."""

    def __init__(self, workspace: str | None = None):
        self.workspace = workspace or tempfile.mkdtemp(prefix="factory_tasks_")
        self.task_counter = 0
        self.results: list[TaskResult] = []

    def dispatch(
        self,
        prompt: str,
        *,
        task_name: str = "unnamed",
        force_file_based: bool = False,
    ) -> TaskResult:
        """Dispatch a task, automatically choosing inline or file-based delivery."""
        self.task_counter += 1
        char_count = len(prompt)
        task_id = f"{task_name}_{self.task_counter}"

        # Check if inline is safe
        if force_file_based or char_count > MAX_INLINE_CHARS:
            return self._dispatch_file_based(prompt, task_id, char_count)
        elif char_count > WARNING_THRESHOLD:
            # Log warning but still try inline
            print(f"[WARN] Task '{task_id}' prompt is {char_count} chars "
                  f"(near limit of {MAX_INLINE_CHARS})")
            return self._dispatch_inline(prompt, task_id, char_count)
        else:
            return self._dispatch_inline(prompt, task_id, char_count)

    def _dispatch_inline(self, prompt: str, task_id: str, char_count: int) -> TaskResult:
        """Dispatch prompt directly via Task tool."""
        try:
            result = self._call_task_tool(prompt)
            task_result = TaskResult(
                success=True,
                output=result,
                method="inline",
                prompt_chars=char_count,
            )
        except Exception as e:
            # If inline fails, try file-based as fallback
            if "truncat" in str(e).lower():
                return self._dispatch_file_based(prompt, task_id, char_count)
            task_result = TaskResult(
                success=False,
                output="",
                method="inline",
                prompt_chars=char_count,
                error=str(e),
            )
        self.results.append(task_result)
        return task_result

    def _dispatch_file_based(self, prompt: str, task_id: str, char_count: int) -> TaskResult:
        """Dispatch via file-based instruction delivery."""
        task_dir = os.path.join(self.workspace, task_id)
        os.makedirs(task_dir, exist_ok=True)

        instructions_path = os.path.join(task_dir, "instructions.md")
        results_dir = os.path.join(task_dir, "results")
        os.makedirs(results_dir, exist_ok=True)

        # Write instructions
        with open(instructions_path, "w", encoding="utf-8") as f:
            f.write(prompt)

        # Construct a short prompt that references the file
        short_prompt = (
            f"Task: {task_id}\n\n"
            f"Your complete instructions are in: {instructions_path}\n\n"
            f"Steps:\n"
            f"1. Read the full instructions from the file above\n"
            f"2. Execute all instructions completely\n"
            f"3. Write your output and any result files to: {results_dir}\n"
            f"4. Summarize what you did and return the summary\n\n"
            f"IMPORTANT: Read the entire instructions file before starting any work. "
            f"Do not skip sections or assume content."
        )

        try:
            result = self._call_task_tool(short_prompt)
            task_result = TaskResult(
                success=True,
                output=result,
                method="file_based",
                prompt_chars=char_count,  # Original prompt size
            )
        except Exception as e:
            task_result = TaskResult(
                success=False,
                output="",
                method="file_based",
                prompt_chars=char_count,
                error=str(e),
            )

        self.results.append(task_result)
        return task_result

    def _call_task_tool(self, prompt: str) -> str:
        """Call the actual Task tool. Override or adapt as needed."""
        # This is the actual tool call — implementation depends on the environment
        # In Factory: tool("Task", prompt=prompt)
        raise NotImplementedError("Subclass and implement _call_task_tool")

    def cleanup(self) -> None:
        """Remove all temporary files."""
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace, ignore_errors=True)

    def get_summary(self) -> str:
        """Get a summary of all dispatched tasks."""
        total_chars = sum(r.prompt_chars for r in self.results)
        inline_count = sum(1 for r in self.results if r.method == "inline")
        file_count = sum(1 for r in self.results if r.method == "file_based")
        failed = [r for r in self.results if not r.success]

        return (
            f"Task Dispatch Summary:\n"
            f"  Total tasks: {len(self.results)}\n"
            f"  Inline: {inline_count}, File-based: {file_count}\n"
            f"  Total prompt chars dispatched: {total_chars}\n"
            f"  Failed: {len(failed)}\n"
            + (f"  Errors: {[r.error for r in failed]}" if failed else "")
        )
