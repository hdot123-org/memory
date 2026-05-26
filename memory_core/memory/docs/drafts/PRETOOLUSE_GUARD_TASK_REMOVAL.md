# PreToolUse Guard: Task Matcher Removal — Change Report

**Date**: 2026-05-24
**Project**: memory-core (source-repo-readonly)
**Files Changed**: 3

---

## 1. Problem Statement

Mission workers dispatched via the `Task` tool were silently failing due to `pretooluse_guard.py` blocking Task invocations whose prompts contained path references matching protected patterns.

### Root Cause Chain

```
Orchestrator dispatches Task(prompt references "memory_core/tools/xxx")
  → PreToolUse hook log-task-start.sh records start event ✓
  → PreToolUse hook pretooluse_guard.py scans prompt text with regex
     → r"memory/[\w\-/]+" matches "memory_core/tools/xxx"
     → Returns decision: "block", exit code 2
  → Task invocation silently rejected — worker never starts
  → PostToolUse hook never fires — no end event recorded
  → Mission orchestrator waits indefinitely — appears hung
```

### Impact Data (May 10–24)

| Metric | Value |
|--------|-------|
| Explicit `cancelled_by_guard` workers | 3 |
| Orphan workers (start, no end) | 74 across 62 sessions |
| `stop_block` events (orphan detection) | 116 |
| Estimated guard-caused orphans | ~15–20 |
| Mission stalls requiring manual intervention | 4+ |

---

## 2. Changes Made

### 2.1 `~/.factory/settings.json` — Hook Matcher

**Before**:
```json
{
  "matcher": "Write|Edit|MultiEdit|Execute|Task|NotebookEdit",
  "hooks": [{"type": "command", "command": "python3 /Users/busiji/memory/memory_core/tools/pretooluse_guard.py", "timeout": 30}]
}
```

**After**:
```json
{
  "matcher": "Write|Edit|MultiEdit|Execute|NotebookEdit",
  "hooks": [{"type": "command", "command": "python3 /Users/busiji/memory/memory_core/tools/pretooluse_guard.py", "timeout": 30}]
}
```

**Note**: The separate `log-task-start.sh` hook entry with `matcher: "Task"` remains unchanged and continues recording Task start events normally.

### 2.2 `memory_core/tools/pretooluse_guard.py` — Code Cleanup

Removed:
- 3 helper functions: `_parse_task_paths()`, `_build_ownership_policy_block()`, `_get_project_root_for_task()`
- `elif tool_name == "Task":` branch (~35 lines)
- Total: ~90 lines deleted

When `tool_name == "Task"` now reaches the guard (if invoked without matcher), it falls through to:
```python
# Unknown tool - allow
return {"decision": "allow", "reason": f"Unknown tool: {tool_name}"}
```

### 2.3 `tests/test_pretooluse_guard.py` — Test Cleanup

Removed 10 test functions across 3 test classes:
- `TestPreToolUseGuard`: 2 Task-specific tests
- `TestTaskPayloadInjection`: entire class (5 tests)
- `TestCwdFixed`: entire class (3 tests)

---

## 3. Security Analysis

### What Changed

| Protection Layer | Before | After |
|-----------------|--------|-------|
| Task dispatch-level prompt scanning | Active (regex-based) | **Removed** |
| Task prompt ownership policy injection | Active | **Removed** |
| Write/Edit file path protection | Active | **Unchanged** |
| MultiEdit per-item protection | Active | **Unchanged** |
| Execute command target extraction | Active | **Unchanged** |
| NotebookEdit path protection | Active | **Unchanged** |

### Why Security Is Preserved

The `Task` tool only spawns a sub-agent with a prompt. It has **no direct file-write capability**. A sub-agent must call `Write`, `Edit`, `MultiEdit`, `Execute`, or `NotebookEdit` to modify files — all of which remain in the guard's matcher and are independently checked.

**Protection enforcement flow (unchanged)**:
```
Sub-agent calls Edit on protected path
  → PreToolUse guard fires (Edit is still in matcher)
  → classify_owned_path() checks file_path
  → Returns decision: "block" if path is protected
```

### What Is Lost (Defense-in-Depth Reduction)

1. **Preemptive Task-level blocking**: A Task whose prompt explicitly says "delete memory/kb/foo" is no longer caught at dispatch time. It will be caught later when the sub-agent calls Execute/Edit on the actual path.

2. **Ownership policy injection**: Sub-agents no longer receive a declarative policy block listing what paths are protected. This was informational only — the guard itself was the enforcement mechanism.

3. **Regex false-positive elimination**: The `r"memory/[\w\-/]+"` pattern was overly broad. It matched any prompt containing "memory/" followed by word characters — including read-only references like "check the file at memory_core/tools/init.py".

---

## 4. Impact on Other Hook Systems

| Hook | Matcher | Impact |
|------|---------|--------|
| `log-task-start.sh` (PreToolUse) | `Task` | **None** — independent entry, still logs Task starts |
| `post-task-use.sh` (PostToolUse) | `Task` | **None** — runs after Task completes, unaffected |
| `stop-guard.sh` (Stop) | *(none)* | **Positive** — fewer orphan false positives |
| `memory-hook` (all events) | *(varies)* | **None** — does not depend on guard's Task interception |

---

## 5. Global Scope Consideration

`~/.factory/settings.json` is a user-level configuration affecting all projects on this machine. However:

- The guard script (`pretooluse_guard.py`) only activates for projects with a `.memory/` or `memory/system/` directory
- Projects without memory-core initialization get an immediate `allow` from the guard
- The `Task` removal only affects the guard's behavior; other Task hooks are independent

---

## 6. Verification

```
$ python3 -m py_compile memory_core/tools/pretooluse_guard.py
OK: guard compiles

$ ruff check memory_core/tools/pretooluse_guard.py
All checks passed!

$ python3 -m pytest tests/test_pretooluse_guard.py -q
55 passed in 4.43s
```

---

## 7. Recommendation Requested From Factory

We would like to confirm:

1. Is removing `Task` from the guard's PreToolUse matcher a supported configuration?
2. Are there any Factory platform features that depend on the guard intercepting `Task`?
3. Is the `injected_prompt` field from PreToolUse hook responses consumed by the Factory runtime? Our analysis shows it is not, but we want to confirm.
4. Is there a recommended way to prevent Task-level false positives while keeping the guard active? (e.g., a more precise regex, or a `decision: "allow"` with prompt modification)
