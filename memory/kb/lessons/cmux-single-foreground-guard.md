---
type: [KB:LESSON]
title: "CMUX Single Runtime and Foreground Guard"
shortname: CMUX-SINGLE-FOREGROUND-GUARD
status: active
created: 2026-04-15
updated: 2026-04-15
source: local-canonical
confidence: high
tags: [lesson, cmux, runtime, guard, foreground, bootstrap]
related: [hook-contract, truth-model, memory-routing]
---

# CMUX Single Runtime and Foreground Guard

## Active Truth

- `workbot` runtime enforces single cmux workspace at bootstrap time.
- `bootstrap_claude_runtime.py` acquires a project lock before bootstrapping and releases it on all exit paths.
- `watch_cmux_assignments.py` blocks execution when assignment workspace is not the selected workspace.
- `watch_cmux_assignments.py` blocks `auto_continue` when foreground command is not `claude` or `codex`.

## Fix Summary

- Added workspace-count hard guard (`>1` fails fast with workspace list).
- Added bootstrap lock at:
  - `memory_core/artifacts/cmux-runtime/bootstrap.lock`
- Added stale-lock recovery and live-lock refusal.
- Added watcher guards:
  - workspace mismatch -> `task_blocked`
  - non-agent foreground command -> `task_blocked` and no continue dispatch

## Truth Basis

### Source Refs
- `AGENTS.md`
- `memory/kb/global/hook-contract.md`

### Authority Refs
- `memory/kb/global/memory-system.md`

### Evidence Refs
- `tests/test_cmux_hook_state.py`

### Conflict Status
- `resolved`
