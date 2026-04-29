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
└── migrations.log     # 迁移日志
```

## 文件规范

### 1. memory.lock

**作用**：锁定 `.memory` 目录结构的版本，防止不兼容变更。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| schema_version | int | 是 | 元数据 schema 版本号 |
| structure_version | int | 是 | 目录结构版本号 |
| locked_at | string | 是 | ISO 8601 时间戳，初始化时写入 |

**验证规则**：
- 文件必须存在
- `schema_version` 必须为正整数
- `structure_version` 必须为正整数
- `locked_at` 必须符合 ISO 8601 格式（初始化后可为空字符串）

### 2. adapter.toml

**作用**：声明业务项目使用的适配器类型、策略、读写边界。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| adapter.type | string | 是 | 适配器类型：`workbot` | `neutral` | `custom` |
| adapter.version | string | 是 | 适配器版本号（semver） |
| adapter.policy.read_scope | array | 是 | 允许读取的路径前缀列表 |
| adapter.policy.write_scope | array | 是 | 允许写入的路径前缀列表 |
| adapter.policy.deny_write | array | 否 | 禁止写入的路径列表 |
| adapter.hooks.enabled | array | 否 | 启用的 hook 列表 |
| adapter.runtime.max_context_tokens | int | 否 | 最大上下文 token 数 |
| adapter.runtime.cache_enabled | bool | 否 | 是否启用缓存 |

**验证规则**：
- 文件必须存在且为合法 TOML
- `adapter.type` 必须为枚举值之一
- `adapter.version` 必须符合 semver 格式
- `read_scope` 和 `write_scope` 不能为空

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
