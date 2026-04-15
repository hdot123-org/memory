---
type: [KB:GLOBAL]
title: "Workbot Hook Gateway Contract"
shortname: WB-HOOK
status: active
created: 2026-04-11
updated: 2026-04-11
source: local-canonical
confidence: high
tags: [hook, gateway, codex, claude, memory]
related: [workbot-memory-system, workbot-memory-routing]
---

# Workbot Hook Gateway Contract

> 本文件定义 `Codex` 与 `Claude` 进入总记忆系统时必须共享的 hook 合同。
> 它定义统一入口、统一上下文裁决和统一写入分流。
> 截至 2026-04-11，两个宿主的正式 hook 入口都已切到仓内 gateway。

## 1. 目标

不管宿主是 `Codex` 还是 `Claude`，官方上下文入口都必须先经过同一套 memory gateway，再进入项目执行或上下文注入。

这份合同只定义宿主共享的规则，不定义宿主专属的 UI 或配置格式。

## 2. Gateway Phases

### 2.1 preflight
- 识别宿主、仓库根目录、当前工作区、事件类型和项目范围。
- 如果工作区不合法、关键入口缺失或总记忆系统损坏，应 fail-fast，而不是静默绕过。

### 2.2 context-resolve
- 读取总记忆系统需要注入的 canonical。
- gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。
- 仅出现在 `ingestion-registry-map.md` 中，不构成合法上下文资格。
- gateway 不只检查合法性，还必须检查当前上下文的 truth basis 是否完整。
- 最小上下文包应包含：
  - 全局规则
  - 当前项目 canonical
  - 必要 decision / lesson
  - `workspace/NOW.md` 摘要
  - 必要 source docs 引用

### 2.3 context-package
- 将上一步的裁决结果组装成统一结构。
- 不允许宿主各自定义一套不同的读取顺序。

### 2.4 write-route
- 当宿主或执行面要落内容时，由 gateway 判定它属于 `log / kb / docs / projects / artifacts / system / archive` 哪一层。
- 不允许宿主绕过路由规则直接写入 canonical。

### 2.4.1 truth-basis gate
- 进入正式 canonical 的上下文，必须同时具备：
  - `source_refs`
  - `authority_refs`
  - `evidence_refs`
  - `conflict_status = resolved`
- gateway 不能只检查 truth basis 的段落形状，还必须检查 ref 的角色语义：
  - `authority_refs` 只能指向 formal canonical 或 legal core
  - `source_refs` 不能全部退化为 canonical 自指
  - `evidence_refs` 必须包含至少一条 lower-layer support
- 如果 truth basis 不完整，宿主可以继续看到辅助证据，但不得把该对象当作正式真相注入。
- `docs_refs`、`decision_refs`、`lesson_refs` 属于辅助证据，不直接等于 truth basis。

### 2.5 post-write-sync
- 更新健康状态、兼容索引、必要的追踪记录和验收证据。
- 等吞噬清洗完成后，目录登记或目录状态迁移还必须附带同次 `git commit` 的提交门禁；未完成提交的登记不得生效。

## 3. Shared Contract Surface

统一合同至少应回答以下问题：

1. 当前宿主是谁。
2. 当前项目域是谁。
3. 当前允许读取哪些 canonical。
4. 当前允许引用哪些资料层文档。
5. 当前允许写入哪些层级。
6. 当前错误应落到哪里。

如果宿主不能回答这些问题，就说明它没有真正经过总记忆系统。

宿主还必须能回答：

7. 当前正式真相的 truth basis 是什么。
8. 当前对象只是合法存在，还是已经达到正式真相标准。

## 4. Host Adapter Rule

- `Codex` 与 `Claude` 可以使用不同的 hook 配置格式。
- 但两者必须调用同一个 gateway 入口，或调用共享同一合同的适配器。
- 宿主适配器只能翻译配置格式，不能重写总记忆系统规则。

## 5. Rollout Rule

- 先完成记忆总系统的 canonical、路由、索引和项目层收正。
- 再补 hook 物理接线。
- 任何影响 `Codex` 全局配置的改动都必须放到最后执行。

## 6. Acceptance Gate

只有同时满足以下条件，hook cutover 才算成功：

- `Codex` 官方入口先过 gateway。
- `Claude` 官方入口先过 gateway。
- 同一任务输入下，两边拿到的是同结构上下文包。
- gateway 失效时，宿主 fail-fast 或明确降级，不允许静默绕过。
- gateway 只认 `active-legal` 地图条目为合法目录来源，不认“仅登记未吸收”的对象。
- gateway 只允许 truth basis 完整且冲突已裁决的对象进入正式真相上下文。

## 6.1 Truth Basis

### Source Refs
- `/Users/busiji/workbot/workspace/INDEX.md`
- `/Users/busiji/workbot/workspace/memory/docs/INDEX.md`

### Authority Refs
- `/Users/busiji/workbot/workspace/memory/kb/global/workbot-truth-model.md`
- `/Users/busiji/workbot/workspace/memory/kb/global/workbot-memory-system.md`

### Evidence Refs
- `/Users/busiji/workbot/workspace/tools/memory_hook_gateway.py`
- `/Users/busiji/workbot/workspace/tools/validate_memory_system.py`

### Conflict Status
- `resolved`

## 7. 当前状态

截至 2026-04-11：

- `Codex` 正式 hook 入口已切到 `/Users/busiji/workbot/workspace/tools/memory_hook_gateway.py`
- `Claude` 正式 hook 入口已切到 `/Users/busiji/workbot/workspace/tools/memory_hook_gateway.py`
- gateway 会先产出 context package 与事件证据，再转发到底层 `cmux` hook
- 验收报告已生成到 `/Users/busiji/workbot/workspace/artifacts/memory-hook/validation/latest.json`
