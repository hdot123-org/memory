# Prompt Truncation: Engineering Solutions

> **Problem**: Factory Task tool prompts are silently truncated when they exceed an internal token/character limit, causing subagents to receive incomplete instructions.
> **Current workaround**: "Make prompts shorter" — insufficient for complex tasks.
> **Goal**: Fundamental, systematic solutions at system, agent, and process levels.

---

## 1. System-Level Solutions

### S1: Automatic Prompt Chunking (Multi-Call Split)
**Concept**: Factory's Task tool transparently splits long prompts into sequential subagent calls.

**How it works**:
```
Orchestrator → Task("do A, then B, then C, then D...")
                 ↓ (prompt exceeds limit)
             Chunk 1: Task("Part 1: do A, then B")
             Chunk 2: Task("Part 2: given Part 1 result, do C")
             Chunk 3: Task("Part 3: given Part 2 result, do D")
                 ↓ (aggregates results)
             Orchestrator ← combined output
```

**Implementation**:
- Factory backend detects prompt length threshold (e.g., 80% of max context)
- Splits at logical boundaries (section headers, numbered items)
- Chains calls with context passing (previous output → next input)
- Returns aggregated result

**Tradeoff**: High complexity. Requires semantic understanding of where to split. Risk of losing cross-part context.

---

### S2: Pre-Execution Validation with Warning/Rejection
**Concept**: Before dispatching a Task, validate prompt length and warn or reject if it exceeds the safe limit.

**How it works**:
```
Orchestrator → Task(prompt="...")
                 ↓
             Factory validates: len(prompt) > SAFE_LIMIT?
                 ↓ YES
             Return: {"error": "PROMPT_TOO_LONG", "actual_tokens": X, "max_tokens": Y}
             ↓ NO → proceed normally
```

**Implementation**:
- Add a `validate_prompt_length(prompt: str) -> (bool, int, int)` check
- Return structured error: `(is_safe, actual_count, max_limit)`
- Orchestrator can then decide: trim, split, or use file-based approach

**Tradeoff**: Low complexity. Doesn't solve the problem alone — just makes it visible. **This is the most practical immediate solution.**

---

### S3: Streaming Prompt Delivery (Part-by-Part)
**Concept**: Allow Task tool to accept prompts in multiple parts, concatenated on the server side before dispatch.

**How it works**:
```
Orchestrator → Task.start(task_id="T1")
             → Task.append(task_id="T1", part=1, content="...")
             → Task.append(task_id="T1", part=2, content="...")
             → Task.execute(task_id="T1")
                 ↓
             Subagent receives: part1 + part2 + ...
```

**Implementation**:
- New Task lifecycle: `start` → `append` (N times) → `execute`
- Server-side buffer accumulates parts until `execute`
- Each part validated against per-part limit (easier to manage)

**Tradeoff**: Medium complexity. Changes the Task tool API. Requires stateful session management.

---

## 2. Agent-Level Solutions

### A1: Built-in Prompt Length Checker in Orchestrator
**Concept**: The orchestrator agent itself checks prompt length before dispatching any Task call.

**Implementation**:
```python
MAX_SAFE_PROMPT_CHARS = 50_000  # or token count

def dispatch_task(prompt: str, **kwargs):
    char_count = len(prompt)
    if char_count > MAX_SAFE_PROMPT_CHARS:
        # Strategy: fall back to file-based approach
        return dispatch_task_via_file(prompt, **kwargs)
    return tool("Task", prompt=prompt, **kwargs)
```

**Integration**: This should be combined with S2 (system-level validation) as a defense-in-depth strategy.

---

### A2: Standard Task Templates with Size Limits
**Concept**: Define reusable task templates that are pre-sized to fit within safe limits.

**Implementation**:
```yaml
# task_templates.yaml
templates:
  code_review:
    max_chars: 30000
    structure:
      - section: "Context"          # 5000 chars
      - section: "Files to Review"  # 15000 chars
      - section: "Instructions"     # 5000 chars
      - section: "Output Format"    # 5000 chars

  implement_feature:
    max_chars: 40000
    structure:
      - section: "Requirements"     # 5000 chars
      - section: "Architecture"     # 10000 chars
      - section: "Implementation"   # 20000 chars
      - section: "Verification"     # 5000 chars
```

**Tradeoff**: Good for common patterns. Doesn't handle ad-hoc complex prompts.

---

### A3: File-Based Task Instructions (Recommended for Complex Tasks)
**Concept**: Instead of embedding instructions in the prompt, write them to a temp file and have the subagent read it.

**How it works**:
```
Orchestrator:
  1. Write instructions to /tmp/task_T123/instructions.md
  2. Write context files to /tmp/task_T123/context/*
  3. Task("Read /tmp/task_T123/instructions.md and execute. All context is in that directory.")

Subagent:
  1. Read instructions.md
  2. Load context files
  3. Execute
  4. Write results to /tmp/task_T123/results/
```

**Implementation**:
```python
import tempfile
import os
import shutil

class FileBasedTask:
    def __init__(self, workspace=None):
        self.workspace = workspace or tempfile.mkdtemp(prefix="factory_task_")

    def prepare(self, instructions: str, context_files: dict[str, str] = None):
        with open(os.path.join(self.workspace, "instructions.md"), "w") as f:
            f.write(instructions)
        if context_files:
            ctx_dir = os.path.join(self.workspace, "context")
            os.makedirs(ctx_dir, exist_ok=True)
            for name, content in context_files.items():
                with open(os.path.join(ctx_dir, name), "w") as f:
                    f.write(content)
        return self.workspace

    def dispatch(self, prompt_template: str = None):
        prompt = prompt_template or (
            f"Read instructions from {self.workspace}/instructions.md\n"
            f"All context files are in {self.workspace}/context/\n"
            f"Write results to {self.workspace}/results/\n"
            f"Execute the instructions completely."
        )
        return tool("Task", prompt=prompt)

    def cleanup(self):
        shutil.rmtree(self.workspace, ignore_errors=True)
```

**Tradeoff**: **Highly effective**. Works with any prompt size. Subagent has full context. Requires subagent to support file reading (which it does).

---

## 3. Process-Level Solutions

### P1: Prompt Budget per Subagent
**Concept**: Allocate a character/token budget per subagent call. Track usage and alert when approaching limits.

**Implementation**:
```python
class PromptBudget:
    BUDGET_PER_TASK = 40_000  # chars
    TOTAL_BUDGET = 200_000    # chars for entire orchestration
    
    def __init__(self):
        self.used = 0
    
    def allocate(self, prompt: str) -> bool:
        cost = len(prompt)
        if cost > self.BUDGET_PER_TASK:
            raise BudgetError(f"Single task exceeds budget: {cost} > {self.BUDGET_PER_TASK}")
        if self.used + cost > self.TOTAL_BUDGET:
            raise BudgetError(f"Total budget exceeded: {self.used + cost} > {self.TOTAL_BUDGET}")
        self.used += cost
        return True
```

**Tradeoff**: Good governance tool. Doesn't solve truncation, just prevents it by constraining input.

---

### P2: Subagent Failure Fallback Mechanism
**Concept**: When a subagent fails (due to truncation or other reasons), automatically retry with a smaller/alternative prompt.

**Implementation**:
```python
def resilient_dispatch(prompt: str, max_retries=2):
    """Dispatch with automatic fallback on failure."""
    for attempt in range(max_retries + 1):
        result = tool("Task", prompt=prompt)
        if result.get("error") == "PROMPT_TRUNCATED":
            # Fallback strategy:
            if attempt == 0:
                # Try 1: Compress prompt (remove verbose sections)
                prompt = compress_prompt(prompt)
            elif attempt == 1:
                # Try 2: Switch to file-based approach
                task = FileBasedTask()
                task.prepare(prompt)
                result = task.dispatch()
                task.cleanup()
                return result
        else:
            return result
    raise RuntimeError("All dispatch attempts failed")
```

**Tradeoff**: Good safety net. Adds latency on retry. Requires reliable failure detection.

---

## 4. Tradeoff Comparison

| Solution | Implementation Effort | Effectiveness | Side Effects | Complexity |
|----------|----------------------|---------------|--------------|------------|
| **S2: Pre-execution validation** | Low | Medium (detects, doesn't fix) | None | Low |
| **A3: File-based instructions** | Low | High | Temp file management | Low |
| **A1: Orchestrator length checker** | Low | High (when combined with A3) | None | Low |
| **P2: Fallback mechanism** | Medium | High | Retry latency | Medium |
| **P1: Prompt budget** | Low | Low (prevents, doesn't solve) | Restricts flexibility | Low |
| **A2: Task templates** | Medium | Medium | Inflexible for ad-hoc | Medium |
| **S3: Streaming delivery** | High | High | API change, stateful | High |
| **S1: Auto chunking** | Very High | Very High | Context loss risk | Very High |

---

## 5. Ranked Solutions (Most Practical to Most Comprehensive)

### Rank 1: S2 + A3 + A1 — "Detect → Redirect → File" (Recommended)
**Immediate, zero-risk, high-effectiveness.**

1. Orchestrator checks prompt length before dispatch (A1)
2. If too long, writes to temp file and dispatches a short prompt referencing the file (A3)
3. System-level validation as safety net catches any orchestrator mistakes (S2)

**Why top rank**: 
- Can be implemented entirely at the orchestrator level — no Factory platform changes needed
- Works with any existing Task tool
- No API changes required
- Handles arbitrarily large prompts

---

### Rank 2: P2 + S2 — "Detect → Retry → Fallback"
**Defensive layering for reliability.**

1. System validates before dispatch (S2)
2. If failure occurs, automatic retry with compression or file-based approach (P2)

**Why second**: Adds resilience on top of Rank 1. Slightly more complex but worth it for production reliability.

---

### Rank 3: S3 — "Streaming Prompt Delivery"
**Platform-level solution for the long term.**

**Why third**: Requires Factory platform changes. Not something the orchestrator can implement alone. But if Factory adds this, it becomes the ideal solution.

---

## 6. Implementation Details for Top 3

### Implementation 1: File-Based Task Dispatcher

**File**: `memory_core/tools/task_dispatcher.py`

```python
"""
Resilient task dispatcher that automatically handles long prompts
by falling back to file-based instruction delivery.
"""

import os
import tempfile
import shutil
from typing import Optional
from dataclasses import dataclass, field

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
    error: Optional[str] = None


class TaskDispatcher:
    """Dispatches tasks to subagents with automatic fallback for long prompts."""

    def __init__(self, workspace: Optional[str] = None):
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

    def cleanup(self):
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
```

---

### Implementation 2: Prompt Validator (Pre-Execution Check)

**File**: `memory_core/tools/prompt_validator.py`

```python
"""
Pre-execution prompt validator.
Checks prompts before Task dispatch to prevent silent truncation.
"""

from dataclasses import dataclass
from typing import Optional

# Configuration — adjust based on actual Factory limits
MAX_PROMPT_CHARS = 50_000
MAX_PROMPT_TOKENS = 12_000  # approximate: ~4 chars per token
WARNING_THRESHOLD_CHARS = 40_000


@dataclass
class ValidationResult:
    is_safe: bool
    char_count: int
    estimated_tokens: int
    warning: Optional[str] = None
    recommendation: Optional[str] = None


def validate_prompt(prompt: str, *, 
                    max_chars: int = MAX_PROMPT_CHARS,
                    warn_at: int = WARNING_THRESHOLD_CHARS) -> ValidationResult:
    """
    Validate a prompt before dispatching to a subagent.
    
    Returns a ValidationResult indicating whether the prompt is safe to use inline.
    """
    char_count = len(prompt)
    estimated_tokens = char_count // 4  # rough estimate
    
    if char_count > max_chars:
        return ValidationResult(
            is_safe=False,
            char_count=char_count,
            estimated_tokens=estimated_tokens,
            warning=f"Prompt exceeds maximum: {char_count} > {max_chars} chars",
            recommendation="Use file-based task dispatch or split into smaller tasks",
        )
    elif char_count > warn_at:
        return ValidationResult(
            is_safe=True,
            char_count=char_count,
            estimated_tokens=estimated_tokens,
            warning=f"Prompt near limit: {char_count}/{max_chars} chars "
                    f"(~{estimated_tokens} tokens)",
            recommendation="Consider file-based dispatch for safety",
        )
    
    return ValidationResult(
        is_safe=True,
        char_count=char_count,
        estimated_tokens=estimated_tokens,
    )


def check_prompt_or_raise(prompt: str, *, mode: str = "warn") -> None:
    """
    Validate and optionally raise an error.
    
    mode: "warn" = print warning but allow
          "error" = raise PromptTooLongError
          "auto" = return validation result for caller to decide
    """
    result = validate_prompt(prompt)
    
    if not result.is_safe:
        if mode == "error":
            raise PromptTooLongError(
                f"Prompt too long: {result.char_count} chars "
                f"(max: {MAX_PROMPT_CHARS}). {result.recommendation}"
            )
        elif mode == "warn":
            print(f"[PROMPT WARNING] {result.warning}. {result.recommendation}")
    
    return result


class PromptTooLongError(ValueError):
    """Raised when a prompt exceeds the safe character limit."""
    pass
```

---

### Implementation 3: Resilient Orchestrator Wrapper

**File**: `memory_core/tools/resilient_orchestrator.py`

```python
"""
Resilient orchestrator wrapper that combines validation, 
dispatch, and automatic fallback.
"""

from typing import Optional
from .task_dispatcher import TaskDispatcher, TaskResult
from .prompt_validator import validate_prompt, ValidationResult


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
```

---

## 7. Decision Matrix

```
                    Quick Win    Production    Platform-Level
                    (Now)        Ready         (Future)
                    ─────────    ─────────     ──────────────
Detection           ✅ S2        ✅ S2+A1      ✅ S2+Auto-warn
Resolution          ✅ A3        ✅ A3+P2      ✅ S3 (Streaming)
Prevention          ✅ P1        ✅ P1+A2      ✅ S1 (Auto-chunk)
Resilience                       ✅ P2         ✅ S1+S3
```

## 8. Recommended Action Plan

### Phase 1: Immediate (This Week)
1. **Deploy S2**: Add prompt validation before every Task call
2. **Deploy A3**: Implement file-based task dispatcher
3. **Deploy A1**: Wire validation + dispatcher together

### Phase 2: Short-term (This Month)
1. **Deploy P2**: Add retry fallback for failed dispatches
2. **Deploy P1**: Add prompt budget tracking for governance
3. **Monitor**: Collect data on prompt sizes and truncation frequency

### Phase 3: Long-term (Push to Factory Platform)
1. **Propose S3**: Request streaming prompt delivery from Factory team
2. **Propose S1**: Request automatic prompt chunking from Factory team
3. **Propose built-in validation**: Request S2 as a Factory platform feature

---

*Generated: 2026-05-16*
*Analysis scope: Factory agent orchestration system — prompt truncation prevention*
