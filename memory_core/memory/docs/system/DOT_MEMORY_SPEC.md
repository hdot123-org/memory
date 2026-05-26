---
type: "[SPEC]"
title: "Memory 目录规范（v0.5.0 两层架构）"
shortname: SPEC-DOT-MEMORY
status: implemented
created: 2026-04-29
updated: 2026-05-23
scope: default
tags: [memory,system,spec,schema]
---

# DOT_MEMORY_SPEC — Memory 目录规范（v0.5.0）

## 概述

自 v0.5.0 起，memory-core 采用两层架构：`~/.memory-core/`（全局运行时）+ `memory/system/`（项目级配置）。
项目级配置文件从隐藏目录 `.memory/` 迁移到 `memory/system/`，同时删除了 5 个 AI 模板文件
（CANONICAL.md, STATE.md, PLAN.md, TASKS.md, NOW.md）及其验证逻辑。

本规范定义了 `memory/system/` 的目录结构、必备文件、字段说明及验证规则。

## 目录结构

```
{project_root}/memory/system/
├── memory.lock        # 版本锁定
├── adapter.toml       # 适配器配置
├── migrations.log     # 迁移日志
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

当使用 `memory-init --sync --sync-showdoc` 时，会额外生成同步相关模板（可选）：

```
{project_root}/
├── .gitlab-ci.yml                           # .pre(CI自检) -> test -> health-check(含CI配置自检) -> sync-to-<mirror> 门禁流水线
├── scripts/
│   └── sync_to_showdoc.py                   # ShowDoc 同步脚本（CI 中执行）
└── memory/
    ├── system/
    │   ├── adapter.toml                     # 含 [sync.showdoc] 配置
    │   └── skills/
    │       └── gitlab_sync_workflow.yaml    # submit_gitlab / merge_after_ci / sync_github / sync_showdoc 编排模板
    └── .showdoc-manifest.json               # SHA256 增量同步 manifest（运行时生成）
```

`sync-to-<mirror>` job 需要镜像凭证变量 `<MIRROR_REMOTE>_TOKEN`
（例如 `GITHUB_TOKEN`），并且必须配置为 GitLab CI 受保护变量（masked + protected）。
ShowDoc 同步需要 `SHOWDOC_API_KEY` 和 `SHOWDOC_API_TOKEN` 变量，同样配置为 CI 受保护变量。

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
| `memory-audit-layout` | 只读审计 `memory/system/`、`memory/`、`project-map/`、workspace legacy 结构和根目录污染 |
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
memory_version = "0.5.0"
schema_version = "context-package-v1"
adapter_version = "builtin"
locked_at = "2026-04-29T00:00:00Z"
lock_reason = "initial"
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| memory_version | SemVer string | 是 | memory-core 的发布版本，如 `0.4.0` |
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
version = "0.5.0"
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
| routing.artifact_root | string | 否 | 产出物根目录 |

**验证规则**：
- 文件必须存在且为合法 TOML
- `core.version` 必须符合 semver 格式
- `routing.project_name` 不能为空
- 详细 schema 定义见 `memory_core/tools/adapter_toml_schema.py`

### 2b. adapter.toml `[sync.showdoc]` 子配置

**作用**：声明 GitLab CI → ShowDoc 文档同步的配置。

当 `[sync]` section 存在且 `showdoc` 子配置启用时，`memory-init` 会生成 ShowDoc 同步所需的脚本和 CI job。

```toml
[sync]
enabled = true
# ... 其他 sync 配置 ...

[sync.showdoc]
enabled = true
item_id = 664858316
api_url = ""
core_files = ["docs/**/*.md", "CHANGELOG.md"]
extra_patterns = []
cat_name_mapping = {}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | bool | 是 | `false` | 是否启用 ShowDoc 同步 |
| `item_id` | int | 是 | `0` | ShowDoc 目标项目 ID |
| `api_url` | string | 否 | `""` | ShowDoc 实例地址（留空则从 mcp.json 读取） |
| `core_files` | array[string] | 否 | `["docs/**/*.md", "CHANGELOG.md"]` | 默认同步的 glob patterns |
| `extra_patterns` | array[string] | 否 | `[]` | 用户自定义扩展 glob patterns |
| `cat_name_mapping` | object | 否 | `{}` | 文件路径→ShowDoc 目录名映射（如 `"docs/design/" = "设计文档"`） |

**验证规则**：
- `enabled = true` 时 `item_id` 必须大于 0
- `core_files` 和 `extra_patterns` 必须是合法的 glob pattern 列表
- `cat_name_mapping` 的 key 必须是文件路径前缀，value 为非空字符串
- 详细 schema 定义见 `memory_core/tools/adapter_toml_schema.py` 中的 `ShowdocSyncConfig`

**同步机制**：
- CI job 在合并到 main 后执行，与 `sync-to-github` 并行
- 通过 ShowDoc Open API `updateByApi` 进行 upsert（按 page_title 幂等）
- 使用 SHA256 manifest（`.showdoc-manifest.json`）实现增量同步
- 单文件失败不阻断，API 调用自动重试 3 次（指数退避）
- Markdown 内容需符合 showdoc-markdown-compat 安全子集

**CLI 参数**（`memory-init`）：
- `--sync-showdoc` — 启用 ShowDoc 同步
- `--sync-showdoc-item-id` — 目标项目 ID
- `--sync-showdoc-url` — ShowDoc 实例地址（可选）

### 3. migrations.log

**作用**：记录 `memory/system/` 结构变更、适配器升级、数据迁移历史。

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

### 4. inbox.md

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

### 5. manifest.json（L2 自动生成）

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
      "path": "/abs/path/to/project/memory/system/adapter.toml",
      "rel_path": "memory/system/adapter.toml",
      "sha256": "<hex>",
      "hmac_sha256": "<hex>",
      "size_bytes": 1234,
      "signed_at": "2026-05-11T12:00:00+08:00"
    }
  ]
}
```

**签名的文件范围**：
- `memory/system/adapter.toml`、`memory/system/ownership.toml`
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

### 6. memory-hook-policy-pack.json（runtime required）

**作用**：默认策略包，位于 `memory/kb/global/`。

Runtime required：被 `memory_hook_impls.py` 作为 `DEFAULT_POLICY_PACK_PATH` 加载。

默认内容为空策略：

```json
{
  "policies": [],
  "version": "1.0"
}
```

### 7. {scope}.md（项目 scope 知识文件）

**作用**：每个项目 scope 的知识文件，位于 `memory/kb/projects/{scope}.md`。

Runtime required：被 `memory_hook_core.py` 在构建 context package 时作为 project canonical 读取。

包含项目概述、技术栈、关键模块、决策记录和经验教训的引用。

## 验证器要求

当 `memory/system/` 目录下存在任意文件时，验证器必须检查以下完整性：

1. **必备文件检查**：4 个文件全部存在（memory.lock、adapter.toml、ownership.toml、migrations.log）
2. **格式检查**：各文件格式合法（TOML/JSON）
3. **必填字段检查**：各文件必填字段不为空
4. **枚举值检查**：状态、类型等字段为合法枚举值
5. **Runtime required 文件检查**：`memory/kb/INDEX.md`、`memory/kb/global/memory-hook-policy-pack.json`、`memory/kb/projects/{scope}.md`、`memory/inbox.md` 存在
6. **L2 完整性检查**（可选）：`manifest.json` 存在且签名验证通过

缺少任一必备文件时，验证器必须报告失败。

## 占位符替换规则

模板文件中的 `{{FIELD_NAME}}` 格式占位符在初始化项目时必须被替换为实际值。
未被替换的占位符在验证时应报告警告（不阻塞）。
