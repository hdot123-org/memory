---
type: [KB:PROJECT]
title: "Workbot Project Canonical"
shortname: WORKBOT-PROJECT
status: active
created: 2026-04-14
updated: 2026-04-26
scope: adapter
source: local-canonical
confidence: high
tags: [project, cmux, global-bot, binding, memory]
related: [workbot-memory-system, workbot-truth-model, workbot-hook-contract]
---

# Workbot Project Canonical

> 本文件是 workbot consumer adapter 的项目描述符，不是模块默认身份真相。
> 其他 consumer adapter 可以有自己的 project canonical 和运行时选择。
> cmux 运行时是 workbot adapter 的运行时选择，不代表模块默认。
> 它只记录已经收口并进入 active memory 的 truth，不重复历史草案。

## Global-Bot + Project-Binding Model

- 所有 bot 本体都是全局 bot body，统一定义在 `<global>/.claude/agents/*.md`。
- `workbot` 通过 `.claude/agents/*.md` 绑定并启用当前正式 bot 集合。
- 当前 `workbot` 绑定并启用的 bot 是：
  - `pm-bot`
  - `dev-bot`
  - `qa-bot`
  - `doc-bot`
  - `rea-bot`
- 外部 `main-thread` 仍在 `OpenCode/Codex` 外部，不进入项目内 bot 集合。
- `cmux-browser` 只是 board surface，不是 bot，也不属于正式身份层。

## `pm-bot` Role Contract

- `pm-bot` 的 role body 是：
  - 产品分析
  - 模仿产品
  - requirement organization
  - website content collection
  - benchmarking
  - imitation analysis
- 如果保留 `clarification`，也只能理解为产品侧需求梳理，不是主线程级任务裁定。
- `pm-bot` 不负责 task breakdown、scope convergence、acceptance framing、dispatch、closure、adjudication。
- role body 和 tools boundary 分开写。
- Crawl4AI 不是 `pm-bot` 的 current canonical owner truth。
- legacy collector variant 只保留为 historical residue / quarantine evidence，不进入 active canonical。

## `pm-bot` Control-Chain Truth

- `dispatch_owner = codex`
- 当前 `pm-bot` 控制链 truth 是 `shared core + pm-specific special cases`
- shared core 包括：
  - shared assignment flow
  - shared watcher flow
  - shared reminder delivery
  - shared state / artifact paths
- pm-specific special cases 包括：
  - `pm-bot-watch.json`
  - single-bot bootstrap support
  - pm-specific continue / correction branches
- 旧 `CODEX_THREAD_ID` / doorbell / monitor-thread 提醒链只属于 historical residue。

## Active / Quarantine Boundary

- active canonical 只写当前已经定稿的 truth。
- legacy collector / crawl4ai owner / long-running checkpoint 叙事只留在 quarantine 或 historical evidence。
- 不要把 legacy residue 偷平成 active truth。
- 不要把 project binding 层写成 project-local ontology。

## Truth Basis

### Source Refs
- `workspace/INDEX.md`
- `workspace/memory/docs/INDEX.md`
- `workspace/memory/kb/global/workbot-truth-model.md`
- `workspace/memory/kb/global/workbot-hook-contract.md`
- `workspace/memory/kb/global/workbot-memory-system.md`

### Authority Refs
- `workspace/project-map/legal-core-map.md`
- `workspace/project-map/INDEX.md`

### Evidence Refs
- `workspace/tools/memory_hook_gateway.py`
- `workspace/tools/memory_hook_core.py`
- `workspace/tools/memory_hook_impls.py`

### Conflict Status
- `resolved`
