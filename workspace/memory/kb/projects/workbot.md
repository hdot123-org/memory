---
type: [KB:PROJECT]
title: "Workbot Project Canonical"
shortname: WORKBOT-PROJECT
status: active
created: 2026-04-14
updated: 2026-04-14
source: local-canonical
confidence: high
tags: [project, cmux, global-bot, binding, memory]
related: [workbot-memory-system, workbot-truth-model, workbot-hook-contract]
---

# Workbot Project Canonical

> 本文件是 `workbot` 当前 active project canonical。
> 它只记录已经收口并进入 active memory 的 truth，不重复历史草案。

## Global-Bot + Project-Binding Model

- 所有 bot 本体都是全局 bot body，统一定义在 `/Users/busiji/.claude/agents/*.md`。
- `workbot` 通过 `/Users/busiji/workbot/.claude/agents/*.md` 绑定并启用当前正式 bot 集合。
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
- `/Users/busiji/workbot/AGENTS.md`
- `/Users/busiji/workbot/.claude/agents/pm-bot.md`
- `/Users/busiji/workbot/docs/cmux-subagent-runtime-chain.md`
- `/Users/busiji/workbot/docs/cmux-subagent-runtime-truth-table.md`
- `/Users/busiji/workbot/docs/cmux-subagent-minimal-operating-guideline.md`
- `/Users/busiji/workbot/workspace/memory/kb/global/workbot-truth-model.md`
- `/Users/busiji/workbot/workspace/memory/kb/global/workbot-hook-contract.md`
- `/Users/busiji/workbot/workspace/memory/kb/global/workbot-memory-system.md`

### Authority Refs
- `/Users/busiji/workbot/workspace/project-map/legal-core-map.md`
- `/Users/busiji/workbot/workspace/memory/kb/global/workbot-truth-model.md`

### Evidence Refs
- `/Users/busiji/workbot/docs/cmux-subagent-runtime-chain.md`
- `/Users/busiji/workbot/docs/cmux-subagent-runtime-truth-table.md`
- `/Users/busiji/workbot/docs/cmux-subagent-minimal-operating-guideline.md`
- `/Users/busiji/workbot/workspace/tools/memory_hook_gateway.py`

### Conflict Status
- `resolved`
