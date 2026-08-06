---
type: [KB:LESSON]
title: "CMUX Project Virtualenv Is Mandatory"
shortname: CMUX-PROJECT-VENV-MANDATORY
status: active
created: 2026-04-15
updated: 2026-04-15
source: local-canonical
confidence: high
tags: [lesson, cmux, runtime, python, venv, guard]
related: [hook-contract, truth-model, memory-routing]
---

# CMUX Project Virtualenv Is Mandatory

## Active Truth

- `cmux` 打开任意项目时，项目级虚拟环境是硬前置条件。
- 正式运行链必须要求 `<project_dir>/.venv` 可用。
- 至少需要通过以下存在性校验：
  - `<project_dir>/.venv/bin/python`
  - `<project_dir>/.venv/bin/activate`
- 若虚拟环境缺失或损坏，`bootstrap` 必须 `fail-fast`，不得回退系统 Python。

## Runtime Enforcement

- `bootstrap_claude_runtime.py` 在 runtime 启动前执行虚拟环境 preflight。
- agent 启动环境显式注入：
  - `VIRTUAL_ENV=<project_dir>/.venv`
  - `PATH=<project_dir>/.venv/bin:$PATH`
- assignment 生成、hook bridge、watcher 进程统一使用项目虚拟环境解释器运行。

## Truth Basis

### Source Refs
- `AGENTS.md`
- `memory/kb/global/hook-contract.md`

### Authority Refs
- `memory/kb/global/memory-system.md`

### Evidence Refs
- `tests/test_cmux_hook_state_unit.py`

### Conflict Status
- `resolved`
