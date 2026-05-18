"""
Resilient orchestrator wrapper that combines validation,
dispatch, and automatic fallback.
"""

from typing import Optional

from .prompt_validator import validate_prompt
from .task_dispatcher import TaskDispatcher, TaskResult


class ResilientOrchestrator:
    """
    Orchestrator wrapper that ensures no prompt is ever silently truncated.

    Flow:
    1. Validate prompt length
    2. If safe → dispatch inline
    3. If unsafe → dispatch via file-based approach
    4. On failure → retry with fallback strategy
    """

    def __init__(self, dispatcher: Optional[TaskDispatcher] = None):
        self.dispatcher = dispatcher or TaskDispatcher()
        self.max_retries = 2

    def dispatch_task(
        self,
        prompt: str,
        *,
        task_name: str = "unnamed",
    ) -> TaskResult:
        """Dispatch with full validation and automatic fallback."""
        # Step 1: Validate
        validation = validate_prompt(prompt)

        if not validation.is_safe:
            # Direct to file-based
            return self.dispatcher.dispatch(
                prompt, task_name=task_name, force_file_based=True
            )

        if validation.warning:
            print(f"[{task_name}] {validation.warning}")

        # Step 2: Try inline first
        result = self.dispatcher.dispatch(prompt, task_name=task_name)

        # Step 3: Retry on failure
        if not result.success and self.max_retries > 0:
            for attempt in range(self.max_retries):
                print(f"[{task_name}] Retry {attempt + 1} via file-based...")
                result = self.dispatcher.dispatch(
                    prompt, task_name=task_name, force_file_based=True
                )
                if result.success:
                    break

        return result

    def cleanup(self):
        self.dispatcher.cleanup()

    def summary(self) -> str:
        return self.dispatcher.get_summary()
