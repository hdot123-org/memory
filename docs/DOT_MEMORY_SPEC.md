---
type: "[SPEC]"
title: ".memory 目录规范"
shortname: SPEC-DOT-MEMORY
status: implemented
created: 2026-04-29
updated: 2026-05-12
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
├── NOW.md             # 当前状态快照
├── migrations.log     # 迁移日志
├── inbox.md           # 临时任务捕获区
├── manifest.json      # L2 完整性签名清单（自动生成）
└── kb/
    ├── projects/      # 项目知识
    ├── decisions/     # 决策记录
    ├── lessons/       # 经验教训
    └── global/        # 全局规范
```

此外，`memory-init` 还会在项目根目录下生成 runtime required 文件：

```
{project_root}/
├── memory/
│   ├── kb/
│   │   ├── INDEX.md                         # 知识库索引
│   │   ├── global/
│   │   │   ├── truth-model.md               # 真相模型
│   │   │   ├── memory-system.md             # 记忆系统规则
│   │   │   ├── memory-routing.md            # 记忆路由规则
│   │   │   ├── hook-contract.md             # Hook 契约
│   │   │   ├── project-map-governance.md    # 项目地图治理
│   │   │   ├── INDEX.md                     # 全局知识索引
│   │   │   └── memory-hook-policy-pack.json # 策略包（默认空策略）
│   │   └── projects/
│   │       └── {scope}.md                   # 项目 scope 知识文件
│   ├── docs/
│   │   └── INDEX.md                         # 文档索引
│   └── system/
│       ├── errors.log                       # 错误日志
│       └── health-report.json              # 健康检查报告（自动生成）
├── project-map/
│   ├── INDEX.md                             # 合法目录地图索引
│   ├── legal-core-map.md                   # 合法核心地图
│   └── ingestion-registry-map.md           # 摄入登记地图
└── INDEX.md                                 # 工作区索引
```

## 初始化与布局治理

`memory-init` 支持四种模式：

| 模式 | 说明 |
|------|------|
| `create` | 新项目初始化默认模式；创建缺失结构，已有文件默认跳过 |
| `adopt` | 接管已有项目；保留业务入口，不向未标记 `AGENTS.md` 追加 hook block |
| `update` | 更新已有 memory 结构；只替换已标记 block 或创建缺失文件 |
| `repair` | 修复模式；只补齐缺失必需文件，不覆盖已有文件 |

布局治理命令：

| 命令 | 说明 |
|------|------|
| `memory-audit-layout` | 只读审计 `.memory/`、`memory/`、`project-map/`、workspace legacy 结构和根目录污染 |
| `memory-plan-residue` | 基于审计结果生成残留处理计划与 rollback/backup 信息 |
| `memory-apply-residue-plan` | 安全应用低风险计划；默认仅允许根目录污染移动和 runtime artifact 忽略 |

自动流程禁止覆盖以下业务入口路径：`AGENTS.md`、`INDEX.md`、`project-map/**`、`CLAUDE.md`。根目录污染自动移动目的地为 `artifacts/reports/`；需要人工判断的项目会留在计划的 `needs_human_decision` bucket。

健康报告会写入 `layout_audit` 摘要字段（total/P0/P1/P2、root_pollution_count、multi_generation_conflict、recommended_mode）。布局审计异常或严重发现只会把健康状态降级为 `degraded`，不阻断报告生成。

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

### 8. NOW.md

**作用**：记录项目当前状态的实时快照，gateway 每次构建 context package 时读取。

Runtime required：被 `memory_hook_core.py` 在构建 context package 时作为 `state_entry` 读取。

| 字段/章节 | 类型 | 必填 | 说明 |
|-----------|------|------|------|
| frontmatter.type | string | 是 | 固定为 `KB:STATE` |
| frontmatter.status | string | 是 | `active` |
| 当前任务 | section | 是 | 当前正在执行的主要任务 |
| 下一步行动 | section | 是 | 下一步行动列表 |
| 阻塞项 | section | 否 | 当前阻塞项 |
| 上下文摘要 | section | 否 | 当前上下文简要描述 |

**验证规则**：
- 文件必须存在且为合法 Markdown
- 必须包含 frontmatter（`type`、`status`）

### 9. inbox.md

**作用**：临时任务捕获区，用于快速记录待处理事项。

Runtime required：被 `memory_hook_impls.py` workbot adapter 在任务操作时引用。

```markdown
# 收件箱

临时任务捕获区。用于快速记录待处理事项，后续应整理到正式任务管理系统。

## 待处理事项

- [ ] （待填写）

## 已归档

（已处理并归档的项）
```

**验证规则**：
- 文件必须存在
- 必须包含「待处理事项」章节

### 10. manifest.json（L2 自动生成）

**作用**：L2 Integrity Layer 的签名清单，记录项目 canonical 文件的 SHA-256 和 HMAC-SHA256 签名。

此文件由 `memory_hook_integrity_manifest.py` 自动生成和维护，不应手动编辑。

```json
{
  "schema_version": "integrity-manifest-v1",
  "project_root": "/abs/path/to/project",
  "generated_at": "2026-05-11T12:00:00+08:00",
  "key_fingerprint": "sha256:<first-8-hex>",
  "entry_count": 5,
  "entries": [
    {
      "path": "/abs/path/to/project/.memory/CANONICAL.md",
      "rel_path": ".memory/CANONICAL.md",
      "sha256": "<hex>",
      "hmac_sha256": "<hex>",
      "size_bytes": 1234,
      "signed_at": "2026-05-11T12:00:00+08:00"
    }
  ]
}
```

**签名的文件范围**：
- `.memory/CANONICAL.md`、`.memory/STATE.md`、`.memory/PLAN.md`、`.memory/TASKS.md`、`.memory/adapter.toml`
- `memory/system/errors.log`
- `artifacts/memory-hook/contexts/` 和 `artifacts/memory-hook/events/` 下的日期分区文件

**触发时机**：
- `memory-init` 初始化后自动签名（best-effort）
- gateway 成功写入 artifact 后自动重新签名
- `session-start` 时自动验证完整性

**验证规则**：
- `schema_version` 必须为 `integrity-manifest-v1`
- `key_fingerprint` 必须与当前密钥匹配
- 每个条目的 `sha256` 和 `hmac_sha256` 必须与当前文件内容一致
- 不在 manifest 中的 canonical 文件报告为 `new_unsigned` 警告

### 11. memory-hook-policy-pack.json（runtime required）

**作用**：默认策略包，位于 `memory/kb/global/`。

Runtime required：被 `memory_hook_impls.py` 作为 `DEFAULT_POLICY_PACK_PATH` 加载。

默认内容为空策略：

```json
{
  "policies": [],
  "version": "1.0"
}
```

### 12. {scope}.md（项目 scope 知识文件）

**作用**：每个项目 scope 的知识文件，位于 `memory/kb/projects/{scope}.md`。

Runtime required：被 `memory_hook_core.py` 在构建 context package 时作为 project canonical 读取。

包含项目概述、技术栈、关键模块、决策记录和经验教训的引用。

## 验证器要求

当 `.memory/` 目录下存在任意文件时，验证器必须检查以下完整性：

1. **必备文件检查**：9 个文件全部存在（memory.lock、adapter.toml、CANONICAL.md、PLAN.md、STATE.md、TASKS.md、NOW.md、migrations.log、inbox.md）
2. **格式检查**：各文件格式合法（TOML/Markdown/JSON）
3. **必填字段检查**：各文件必填字段不为空
4. **枚举值检查**：状态、类型等字段为合法枚举值
5. **Runtime required 文件检查**：`memory/kb/INDEX.md`、`memory/kb/global/memory-hook-policy-pack.json`、`memory/kb/projects/{scope}.md` 存在
6. **L2 完整性检查**（可选）：`manifest.json` 存在且签名验证通过

缺少任一必备文件时，验证器必须报告失败。

## 占位符替换规则

模板文件中的 `{{FIELD_NAME}}` 格式占位符在初始化项目时必须被替换为实际值。
未被替换的占位符在验证时应报告警告（不阻塞）。
