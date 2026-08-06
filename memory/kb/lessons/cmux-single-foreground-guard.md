---
type: [KB:LESSON]
title: "CMUX Single Runtime and Foreground Guard"
shortname: CMUX-SINGLE-FOREGROUND-GUARD
status: active
created: 2026-04-15
updated: 2026-08-06
source: local-canonical
confidence: high
tags: [lesson, cmux, runtime, guard, foreground, bootstrap]
---

# CMUX Single Runtime and Foreground Guard

## Active Truth

- `workbot` runtime enforces single cmux workspace at bootstrap time.
- Runtime bootstrap acquires a project lock before bootstrapping and releases it on all exit paths.
- Assignment watcher blocks execution when assignment workspace is not the selected workspace.
- Assignment watcher blocks `auto_continue` when foreground command is not `claude` or `codex`.

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
- AGENTS.md
- memory/docs/记忆系统全景文档.md

### Authority Refs
- memory/kb/global/memory-system.md
- memory/kb/global/hook-contract.md

### Evidence Refs
- memory_core/tools/memory_hook_gateway.py
- tests/test_business_policy_paths.py

### Conflict Status
- resolved
