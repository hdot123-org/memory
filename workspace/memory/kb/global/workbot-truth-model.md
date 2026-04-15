---
type: [KB:GLOBAL]
title: "Workbot 真相判定模型"
shortname: WB-TRUTH
status: active
created: 2026-04-11
updated: 2026-04-11
source: local-canonical
confidence: high
tags: [truth, proof, canonical, memory]
related: [workbot-memory-system, workbot-memory-routing, workbot-hook-contract, workbot-project-map-governance]
---

# Workbot 真相判定模型

> 本文件定义 `workbot` 中“什么才配叫真相”。
> 它不替代合法性地图，而是在合法性之上再回答：什么内容可以被正式相信并进入 canonical。

## 1. 第一性原则

一条内容要成为正式真相，必须同时满足四个条件：

1. 有来源。
2. 有上位许可。
3. 有落地支撑。
4. 冲突已裁决。

缺任何一项，都不能进入正式真相层。

## 2. 四要素

### `source_refs`

用于回答：这条内容从哪里来。

- 可以指向研究资料、参考资料、历史正文、来源文档或原始材料。
- `source_refs` 可以来自 `memory/docs/**`，也可以来自受管执行材料。
- 有来源不等于来源本身就是合法真相。

### `authority_refs`

用于回答：谁允许这条内容成立。

- 必须指向更高一层的 canonical、治理规则、路由规则或总系统边界。
- 项目级结论必须受 global canonical 约束。
- 运行层、资料层和产物层不能充当 authority。
- `memory/docs/**`、`workspace/projects/**`、`workspace/artifacts/**` 和根级实现目录不得冒充 authority。

### `evidence_refs`

用于回答：什么证明这条内容不是空话。

- 可以指向运行材料、产物、日志、验证脚本、执行清单、任务真源或实现文件。
- `evidence_refs` 必须能在更具体层级上支撑这条结论。
- 如果没有落地支撑，只能算候选说法，不能算正式真相。
- `evidence_refs` 不能只是资料层复述，必须至少包含一条更下级的实现、执行或运行支撑。

### `conflict_status`

用于回答：是否仍存在未裁决冲突。

允许值：

- `resolved`
- `open`
- `rejected`

规则：

- `resolved`：允许继续参与正式真相判定。
- `open`：不得进入正式真相。
- `rejected`：转入失效或归档，不得进入正式真相。

## 3. 真相与合法性的关系

合法性与真相性不是一回事。

### 合法性

由 `project-map` 裁决，回答：

- 这个对象是否允许存在于正式系统中。
- 它当前属于 `active-legal`、`incoming-raw`、`compatibility-only`、`absorbed` 还是 `retired`。

### 真相性

由本模型裁决，回答：

- 这个对象有没有资格被正式相信并进入 canonical。
- 它是否拥有完整的 `source / authority / evidence / conflict` 四要素。

结论：

- 一个对象可以合法存在，但还不配叫真相。
- 只有同时满足合法性和真相性，才能作为正式 canonical 被读取和注入。

## 4. 最小真相判定规则

一条内容要进入正式真相层，必须同时满足：

- `source_refs` 非空
- `authority_refs` 非空
- `evidence_refs` 非空
- `conflict_status = resolved`
- `source_refs`、`authority_refs`、`evidence_refs` 不得互相偷换或完全重合

用公式表示：

`truth = source_refs + authority_refs + evidence_refs + resolved_conflict`

## 5. 层级约束

### Global Canonical

进入 `workspace/memory/kb/global/` 的内容必须：

- 有来源材料或既有控制面来源
- 受总系统或更上位治理边界约束
- 有运行或实现层支撑
- 冲突已裁决

### Project Canonical

进入 `workspace/memory/kb/projects/` 的内容必须：

- 有项目来源材料
- 受 global canonical 约束
- 有项目执行面或运行证据支撑
- 冲突已裁决

### Decision / Lesson

- `decisions/` 记录裁决过程，本身可以承接冲突，但未裁决前不能晋升为 canonical。
- `lessons/` 可以记录经验，但若要晋升为稳定真相，仍要满足四要素。

## 6. Hook 与 Validator 要求

正式 gateway 和 validator 必须至少检查：

1. 当前 truth basis 是否完整。
2. 当前 project canonical 是否与 project scope 匹配。
3. `source_refs`、`authority_refs`、`evidence_refs` 是否被正确区分。
4. `memory/docs/**` 不能直接冒充 authority。
5. `conflict_status != resolved` 的对象不得进入正式上下文。
6. `source_refs` 不得全部退化为 canonical 自指。
7. `evidence_refs` 至少包含一条 lower-layer support。

## 7. 真相基与辅助证据的区别

当前 formal gate 至少要区分两层：

- `truth_basis_refs`
  - 当前正式上下文真正依赖的 canonical 真相基
- `evidence_refs`
  - 支撑、解释、证明或追溯用的辅助证据

规则：

- `truth_basis_refs` 只能由 global canonical 与当前 project canonical 组成。
- `docs_refs`、`decision_refs`、`lesson_refs`、运行证据都属于辅助证据，不直接等于 truth basis。

## 8. 结论

`workbot` 的记忆系统以后不只要回答“这个东西是否合法存在”，还要回答“这个东西凭什么能被相信”。

正式真相的最低标准是：

> 有来源，有上位许可，有落地支撑，且冲突已裁决。

## 9. Truth Basis

### Source Refs
- `/Users/busiji/workbot/workspace/INDEX.md`
- `/Users/busiji/workbot/workspace/memory/kb/global/workbot-memory-system.md`

### Authority Refs
- `/Users/busiji/workbot/workspace/project-map/legal-core-map.md`

### Evidence Refs
- `/Users/busiji/workbot/workspace/tools/memory_hook_gateway.py`
- `/Users/busiji/workbot/workspace/tools/validate_memory_system.py`

### Conflict Status
- `resolved`
