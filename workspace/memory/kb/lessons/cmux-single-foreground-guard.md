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
related: [workbot-hook-contract, workbot-truth-model, workbot-memory-routing]
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
  - `/Users/busiji/memory/workspace/artifacts/cmux-runtime/bootstrap.lock`
- Added stale-lock recovery and live-lock refusal.
- Added watcher guards:
  - workspace mismatch -> `task_blocked`
  - non-agent foreground command -> `task_blocked` and no continue dispatch

## Evidence Refs

- `/Users/busiji/.agents/skills/cmux/scripts/bootstrap_claude_runtime.py`
- `/Users/busiji/.agents/skills/cmux/scripts/watch_cmux_assignments.py`
- `/Users/busiji/.agents/skills/cmux/references/workbot/cmux-multi-pane-agent-runtime-requirements.md`

## Verification Refs

- `python3 -m py_compile /Users/busiji/.agents/skills/cmux/scripts/bootstrap_claude_runtime.py`
- `python3 -m py_compile /Users/busiji/.agents/skills/cmux/scripts/watch_cmux_assignments.py`
- `python3 /Users/busiji/.agents/skills/cmux/scripts/watch_cmux_assignments.py --assignment-file /Users/busiji/memory/workspace/artifacts/cmux-runtime/cmux-assignment.json --hook-state-file /Users/busiji/memory/workspace/artifacts/cmux-runtime/hook-state.json --once`
