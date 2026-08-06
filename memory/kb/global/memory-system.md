# 记忆系统规则

三层架构与 scope 路由规则。

## 1. 三层知识库架构

记忆系统采用三层架构，从全局到项目逐层细化：

| 层级 | 名称 | 职责 | 典型路径 |
|------|------|------|----------|
| Layer 1 | 全局治理 | 跨项目通用规则、合法性判定 | `project-map/`、`AGENTS.md` |
| Layer 2 | 全局知识库 | 跨项目通用知识、全局 fallback | `memory/kb/global/` |
| Layer 3 | 项目知识库 | 项目专属知识 | `<project>/memory/kb/` |

## 2. Scope 路由机制

Agent 启动时通过 `adapter.toml` 中的 `project_scope` 字段确定当前项目 scope。
ScopeResolver 根据 scope 名称定位到 `memory/kb/projects/{scope}.md` 项目 canonical 文件，
然后 TruthBasisResolver 对该文件及所有全局 canonical 文件执行 8 阶段校验。

路由优先级：
1. Layer 3 项目层优先 — 项目专属规则覆盖全局规则
2. Layer 2 全局 fallback — 项目层无定义时回退到全局知识库
3. Layer 1 全局治理 — 合法性判定由 project-map 子系统统一负责

## 3. 全局 Canonical 文件

Layer 2 全局知识库包含 5 个 canonical 文件，每个文件承担特定职责：

| 文件 | 职责 |
|------|------|
| `truth-model.md` | 唯一真相模型：Truth Basis 概念、Ref 分类规则 |
| `memory-system.md` | 记忆系统规则：三层架构、scope 路由 |
| `memory-routing.md` | 路由规则：Layer 2/3 fallback、scope resolution |
| `hook-contract.md` | Hook 契约：session-start/prompt-submit 生命周期 |
| `project-map-governance.md` | 项目地图治理：project-map 结构、合法性校验 |

## 4. Context Package 构建

`memory_hook_gateway` 在 session-start 和 prompt-submit 事件时动态构建 context package，
包含下列必需 key：

| Key | 必需子 key |
|-----|-----------|
| `status` | — |
| `host` | — |
| `event` | — |
| `schema_version` | — |
| `system_context` | `boot_entry`, `state_entry` |
| `task_context` | `session_id`, `event` |

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- memory/kb/global/truth-model.md
- memory/kb/global/memory-routing.md

### Evidence Refs

- tests/conftest.py

### Conflict Status

- resolved
