---
type: "[SPEC]"
title: ".memory 目录规范"
shortname: SPEC-DOT-MEMORY
status: implemented
created: 2026-04-29
updated: 2026-04-30
scope: default
tags: [dot-memory,spec,schema]
---

# DOT_MEMORY_SPEC — .memory 目录规范

## 概述

`.memory/` 是每个业务项目的标准元数据目录，用于维护项目上下文、状态、任务和配置。
本规范定义了 `.memory/` 的目录结构、必备文件、字段说明及验证规则。

## 目录结构

```
{project_root}/.memory/
├── memory.lock        # 版本锁定
├── adapter.toml       # 适配器配置
├── CANONICAL.md       # 项目规范
├── PLAN.md            # 执行计划
├── STATE.md           # 项目状态
├── TASKS.md           # 任务清单
├── migrations.log     # 迁移日志
└── kb/
    ├── projects/      # 项目知识
    ├── decisions/     # 决策记录
    ├── lessons/       # 经验教训
    └── global/        # 全局规范
```

## 文件规范

### 1. memory.lock

**作用**：锁定项目与 memory-core 的版本绑定，防止不兼容变更。

文件为 TOML 格式，包含 `[memory]` section：

```toml
[memory]
memory_version = "0.2.0"
schema_version = "context-package-v1"
adapter_version = "builtin"
locked_at = "2026-04-29T00:00:00Z"
lock_reason = "initial"
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| memory_version | SemVer string | 是 | memory-core 的发布版本，如 `0.2.0` |
| schema_version | string | 是 | hook/schema 版本标识，如 `context-package-v1` |
| adapter_version | string | 否 | adapter 版本，默认 `builtin` |
| locked_at | ISO-8601 | 否 | 最后锁定/升级时间 |
| lock_reason | string | 否 | 锁定原因：`initial` / `upgrade` / `downgrade` |

**验证规则**：
- 文件必须存在且为合法 TOML
- 必须包含 `[memory]` section
- `memory_version` 必须严格遵循 SemVer：MAJOR.MINOR.PATCH
- `schema_version` 必须是 memory-core 已发布的合法 schema 标识
- 完整 schema 定义见 [MEMORY_LOCK_SPEC.md](MEMORY_LOCK_SPEC.md)

### 2. adapter.toml

**作用**：声明业务项目使用的适配器版本、策略规则、路由配置。

文件为 TOML 格式，canonical layout 使用 `[core]`、`[policy]`、`[routing]` 三节：

```toml
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "default"
# host: codex | claude | factory
host = "codex"
canonical_files = ["CANONICAL.md", "STATE.md"]
# artifact_root = "artifacts/"
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| core.version | string | 是 | 适配器版本号（semver） |
| core.adapter | string | 是 | 适配器名称 |
| policy.legality_source_policy | string | 否 | 合法性来源策略，默认 `map-only` |
| policy.registration_commit_policy | string | 否 | 注册提交策略，默认 `same-commit` |
| policy.registration_commit_phase | string | 否 | 注册提交阶段，默认 `post` |
| routing.project_name | string | 是 | 项目名称 |
| routing.project_scope | string | 是 | 项目作用域 |
| routing.host | string | 否 | 宿主平台：`codex` \| `claude` \| `factory`，默认 `codex` |
| routing.canonical_files | array | 否 | 规范文件列表 |
| routing.artifact_root | string | 否 | 产出物根目录 |

**验证规则**：
- 文件必须存在且为合法 TOML
- `core.version` 必须符合 semver 格式
- `routing.project_name` 不能为空
- 详细 schema 定义见 `workspace/tools/adapter_toml_schema.py`

### 3. CANONICAL.md

**作用**：定义业务项目的编码规范、架构约束、命名约定。

| 字段/章节 | 类型 | 必填 | 说明 |
|-----------|------|------|------|
| 项目信息 | section | 是 | 项目名称、类型、主语言、创建日期 |
| 编码规范 | section | 是 | 项目编码标准描述 |
| 架构约束 | section | 是 | 架构层面的约束条件 |
| 命名约定 | section | 是 | 变量、函数、文件命名规则 |
| 工具链 | section | 否 | 使用的工具和版本 |
| 变更日志 | section | 是 | 规范变更记录表 |

**验证规则**：
- 文件必须存在且为合法 Markdown
- 必须包含「项目信息」和「编码规范」章节

### 4. PLAN.md

**作用**：记录当前迭代/任务的执行计划、里程碑、验收标准。

| 字段/章节 | 类型 | 必填 | 说明 |
|-----------|------|------|------|
| 任务概述 | section | 是 | 任务 ID、名称、优先级、创建日期 |
| 目标 | section | 是 | 任务目标描述 |
| 执行计划 | section | 是 | 步骤表格（步骤、描述、状态、完成日期） |
| 验收标准 | section | 是 | 验收条件列表 |
| 风险与依赖 | section | 否 | 风险和外部依赖 |
| 状态 | section | 是 | 当前状态、上次更新 |

**验证规则**：
- 文件必须存在且为合法 Markdown
- 必须包含「任务概述」、「目标」、「执行计划」、「验收标准」章节
- 状态值必须为：`planning` | `in_progress` | `review` | `completed` | `blocked`

### 5. STATE.md

**作用**：记录业务项目的当前状态、上下文摘要、关键决策。

| 字段/章节 | 类型 | 必填 | 说明 |
|-----------|------|------|------|
| 项目状态 | section | 是 | 状态、最后更新、健康度 |
| 上下文摘要 | section | 是 | 项目上下文概要 |
| 关键决策 | section | 是 | 决策记录表 |
| 当前工作区 | section | 否 | 当前工作区描述 |
| 待处理事项 | section | 是 | 待处理事项列表 |
| 已完成的里程碑 | section | 否 | 里程碑记录 |

**验证规则**：
- 文件必须存在且为合法 Markdown
- 状态值必须为：`active` | `paused` | `completed` | `archived`
- 健康度值必须为：`green` | `yellow` | `red`

### 6. TASKS.md

**作用**：跟踪当前项目下的所有任务、子任务、状态。

| 字段/章节 | 类型 | 必填 | 说明 |
|-----------|------|------|------|
| 活跃任务 | section | 是 | 活跃任务表格 |
| 已完成任务 | section | 是 | 已完成任务表格 |
| 已取消任务 | section | 是 | 已取消任务表格 |
| 阻塞项 | section | 否 | 当前阻塞项列表 |

**验证规则**：
- 文件必须存在且为合法 Markdown
- 必须包含三个任务章节（活跃、已完成、已取消）
- 任务 ID 格式必须为 `T-XXX`

### 7. migrations.log

**作用**：记录 `.memory` 结构变更、适配器升级、数据迁移历史。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| TIMESTAMP | string | 是 | ISO 8601 时间戳 |
| VERSION_FROM | string | 是 | 迁移前版本 |
| VERSION_TO | string | 是 | 迁移后版本 |
| DESCRIPTION | string | 是 | 迁移描述 |
| STATUS | string | 是 | 迁移状态：`completed` | `failed` | `pending` |

**验证规则**：
- 文件必须存在
- 非注释行必须符合管道符分隔格式
- 必须有至少一条初始化记录

## 验证器要求

当 `.memory/` 目录下存在任意文件时，验证器必须检查以下完整性：

1. **必备文件检查**：7 个文件全部存在
2. **格式检查**：各文件格式合法（TOML/Markdown/YAML）
3. **必填字段检查**：各文件必填字段不为空
4. **枚举值检查**：状态、类型等字段为合法枚举值

缺少任一必备文件时，验证器必须报告失败。

## 占位符替换规则

模板文件中的 `{{FIELD_NAME}}` 格式占位符在初始化项目时必须被替换为实际值。
未被替换的占位符在验证时应报告警告（不阻塞）。
