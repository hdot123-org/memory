# memory-core

为任意项目提供标准化的 `.memory/` 目录结构与版本管理能力。memory-core 只提供协议、模板、schema 和工具，不存储任何业务数据。

## 安装

### 从 GitHub Release 安装

```bash
gh release download v0.2.0 --repo hdot123/memory --pattern "*.whl" && pip install memory_core-0.2.0-py3-none-any.whl
```

### 从源码安装

```bash
pip install git+https://github.com/hdot123/memory.git@v0.2.0
```

### 升级

更换版本号并加 `--upgrade`：

```bash
pip install --upgrade git+https://github.com/hdot123/memory.git@v0.2.0
```

## 快速开始

三个核心 CLI 命令，覆盖项目接入的全生命周期：

### 1. 初始化 — `memory-init`

在目标项目中创建 `.memory/` 标准目录结构：

```bash
memory-init --target /path/to/project
```

**选项：**

| 选项 | 说明 |
|---|---|
| `--target` | （必填）目标项目根目录路径 |
| `--scope` | 显式指定项目 scope 名称；若省略则从 git remote 或目录名自动推导 |
| `--host` | 指定 host 平台（`codex`、`factory` 或 legacy `claude`，默认 `codex`）；正式部署只支持 Codex App / Factory Droid 全局 hook 模式，`claude` 仅保留为兼容值 |
| `--dry-run` | 只输出将要执行的操作，不实际写入文件 |
| `--json` | 以 JSON 格式输出结果，便于脚本集成 |

**使用示例：**

```bash
# 最小可运行命令
memory-init --target /path/to/project

# 显式指定 scope 和 host
memory-init --target /path/to/project --scope my-project --host factory

# 预览（不写入文件）
memory-init --target /path/to/project --dry-run

# JSON 输出
memory-init --target /path/to/project --dry-run --json
```

### 全局部署模式（唯一支持）

memory-core 只支持 **Codex App 全局 hook** 和 **Factory Droid 全局 hook** 两种部署模式。不要再为 Claude 或其他 host 维护项目级 hook 部署；项目级 hook 容易因 cwd、checkout 路径或多项目复用导致记忆漂移。统一使用全局 wrapper 后，host 只负责触发入口，wrapper 再根据原始项目 cwd/`FACTORY_PROJECT_DIR` 把记忆读写回当前项目目录。

全局部署的边界是：

- 全局目录只保存 hook 入口、settings/hooks 配置、lifecycle/path-index 和完整性密钥。
- 项目记忆正文只写入当前项目内的 `.memory/`、`memory/`、`artifacts/memory-hook/`。
- `~/.memory-core` 不是项目记忆池，不能存放业务项目正文记忆。
- 不支持把 Claude 项目级 `.claude/hooks.json` 作为防漂移部署入口；如需使用 Claude，应先通过 Codex App 或 Factory Droid 的全局入口触发 memory gateway。

### Codex App 全局记忆 Hook

Codex App 的全局 hook 只作为触发器，不承担记忆删除、迁移或项目生命周期管理。推荐安装一套稳定入口，让 Codex 的 `SessionStart`、`UserPromptSubmit`、`Stop` 都转发到已安装的 memory gateway：

```bash
memory-codex-hooks install --storage-root ~/.memory-core
```

该命令会写入：

- `~/.codex/bin/memory-hook`：稳定 wrapper，记录原始 `cwd` 后调用 `memory-hook-gateway` 命令，不指向任何项目源码 checkout。
- `~/.codex/hooks.json`：Codex App 全局 hook 配置，合并时保留无关 hook，并替换旧的 memory hook 命令。

运行时边界：Codex App 只触发统一入口；每次会话仍以原始 `cwd` 对应的项目为准。wrapper 会在项目目录存在但尚未接入 memory 时先执行 `memory-init --target <cwd> --host codex`，确保接入 Codex 的项目都有自己的 `.memory/` 项目记忆文件。随后 gateway 的 context 查询、artifact、event log、error log 和 write target 都回到该项目自己的目录，避免项目记忆漂移到全局池。

`--storage-root` 对应的 `~/.memory-core` 只作为 Codex 全局入口的状态根，用于记录 project lifecycle/path-index、missing path 等宿主级索引；它不能替代项目内 `.memory/`/`memory/`。若曾经添加到 Codex 的项目目录被误删，lifecycle 会通过路径索引复用已记录的项目身份并标记为 `missing`，历史项目记忆不会被迁移或删除。目录恢复或重新 clone 后，后续 hook 会继续在项目目录内读写。

项目内 hook 产物按日期分区写入，便于后续归档、签名和清理：`artifacts/memory-hook/contexts/YYYY-MM-DD/<timestamp>-<host>-<event>.json` 保存快照，`artifacts/memory-hook/events/YYYY-MM-DD.jsonl` 保存当日事件日志，`memory/system/errors/YYYY-MM-DD.log` 保存当日错误日志；同时保留 `latest-<host>-<event>.json`、`events.jsonl` 和 `errors.log` 作为兼容入口。

#### 生成文件位置规范

默认规则是：项目记忆与运行时产物写入当前项目内；Codex 全局入口、宿主级 lifecycle/path-index 与完整性密钥写入用户级全局目录。`~/.memory-core` 不是项目记忆池，不能替代项目内 `.memory/`/`memory/`。

| 类型 | 默认位置 | 说明 |
|---|---|---|
| 项目初始化文件 | `{project_root}/.memory/`、`{project_root}/memory/`、`{project_root}/project-map/`、`{project_root}/INDEX.md` | `memory-init --target <project>` 生成的项目记忆结构与 runtime required 文件 |
| 项目 host 配置提示 | `{project_root}/AGENTS.md` | 由 `memory-init` 生成/更新，用于项目内 host 集成说明；正式 hook 入口应使用 Codex/Factory 全局部署 |
| Gateway artifact/event | `{project_root}/artifacts/memory-hook/...` | context 快照、latest 快照和 event JSONL，按项目隔离 |
| Gateway error/health | `{project_root}/memory/system/errors.log`、`{project_root}/memory/system/errors/YYYY-MM-DD.log`、`{project_root}/memory/system/health-report.json` | 项目内错误日志和异步健康检查结果 |
| 项目完整性清单 | `{project_root}/.memory/manifest.json` | 每个项目独立维护签名清单 |
| Codex 全局 hook | `~/.codex/bin/memory-hook`、`~/.codex/hooks.json` | `memory-codex-hooks install` 安装的全局入口；可用 `CODEX_HOME` 改变位置 |
| Factory 全局 hook | `~/.factory/bin/memory-hook`、`~/.factory/settings.json` | `memory-factory-hooks install` 安装的 Factory Droid 用户级入口；可用 `FACTORY_HOME` 改变位置 |
| 全局 lifecycle/path-index | `~/.memory-core/project-lifecycle/...` | Codex/Factory wrapper 默认设置的宿主级项目索引；不存放项目正文记忆 |
| 全局 init 错误日志 | `~/.memory-core/memory/system/errors.log` | wrapper 自动初始化项目失败时的兜底日志 |
| 完整性密钥 | `~/.memory-core/keys/project-integrity.key` | 全局共享 HMAC 密钥；manifest 仍按项目隔离 |

以下环境变量会改变默认位置，使用时应避免把多个项目的产物误指向同一个共享文件或目录：

| 环境变量 | 影响 |
|---|---|
| `CODEX_HOME` | 改变 Codex 全局 hook 安装目录，默认 `~/.codex` |
| `FACTORY_HOME` | 改变 Factory Droid 用户级配置目录，默认 `~/.factory` |
| `MEMORY_HOOK_GLOBAL_STATE_ROOT` | 改变全局 lifecycle/path-index 与 wrapper 兜底错误日志根目录，默认 `~/.memory-core` |
| `MEMORY_HOOK_ARTIFACT_ROOT` | 覆盖 gateway artifact/event 根目录，默认 `{project_root}/artifacts/memory-hook` |
| `MEMORY_HOOK_ERROR_LOG` | 覆盖 gateway 主错误日志路径，默认 `{project_root}/memory/system/errors.log` |
| `MEMORY_INTEGRITY_KEY_PATH` | 覆盖完整性签名密钥路径，默认 `~/.memory-core/keys/project-integrity.key` |
| `MEMORY_HOOK_ORIGINAL_CWD` + `MEMORY_HOOK_PREFER_EXTERNAL_CWD` | 影响 gateway 选择当前项目 cwd；Codex wrapper 默认设置，用于保持多项目隔离 |

### Factory Droid 全局记忆 Hook

Factory Droid 的全局 hook 配置位于 `~/.factory/settings.json` 的 `hooks` 字段。可安装一套用户级稳定入口，让 Droid 的 `SessionStart`、`UserPromptSubmit`、`Stop`、`Notification` 都转发到 memory gateway：

```bash
memory-factory-hooks install --storage-root ~/.memory-core
```

该命令会写入：

- `~/.factory/bin/memory-hook`：稳定 wrapper，优先使用 Factory 提供的 `FACTORY_PROJECT_DIR` 识别项目根，并调用 `memory-hook-gateway`。
- `~/.factory/settings.json`：Factory Droid 用户级 hook 配置；合并时保留无关设置和无关 hooks，并替换旧的 memory hook 命令。

运行时边界与 Codex 一致：Factory 全局 hook 只作为触发器；项目记忆仍写入当前项目自己的 `.memory/`、`memory/`、`artifacts/memory-hook/`。当项目尚未初始化时，wrapper 会先执行 `memory-init --target <project> --host factory`。

### 2. 校验 — `memory-validate`

检查项目 `.memory/` 目录是否完整、schema 是否合规：

```bash
memory-validate --target /path/to/project
```

校验内容包括：
- 必需文件是否存在（`memory.lock`、`adapter.toml`、`CANONICAL.md`、`PLAN.md`、`STATE.md`、`TASKS.md`、`migrations.log`）
- Markdown 文件的 frontmatter 字段是否完整
- `memory.lock` 与 `adapter.toml` 版本是否兼容
- **污染防护**：检测 memory 仓库是否被写入了业务数据

**选项：**

| 选项 | 说明 |
|---|---|
| `--dry-run` | 只执行检查，不修改任何文件 |
| `--json` | 以 JSON 格式输出校验结果 |

### 3. 版本迁移 — `memory-migrate`

在 schema 版本之间迁移：

```bash
memory-migrate --target /path/to/project --from 0.1.0 --to 0.2.0
```

**选项：**

| 选项 | 说明 |
|---|---|
| `--from <version>` | 当前版本号 |
| `--to <version>` | 目标版本号 |
| `--dry-run` | 预览迁移步骤，不实际执行 |
| `--json` | 以 JSON 格式输出迁移结果 |

## `.memory/` 目录结构

`memory-init` 后在项目根目录下生成：

```
.memory/
├── memory.lock        # 版本锁定文件，记录当前 schema 版本
├── adapter.toml       # 项目适配器配置
├── CANONICAL.md       # 项目规范
├── PLAN.md            # 执行计划
├── STATE.md           # 项目状态
├── TASKS.md           # 任务清单
├── NOW.md             # 当前状态快照（runtime required）
├── migrations.log     # 迁移日志
├── manifest.json      # L2 完整性签名清单（自动生成）
├── inbox.md           # 临时任务捕获区（runtime required）
└── kb/
    ├── projects/      # 项目知识
    ├── decisions/     # 决策记录
    ├── lessons/       # 经验教训
    └── global/        # 全局规范
```

此外，项目根目录下还会生成以下 runtime required 文件：

```
{project_root}/
├── memory/
│   ├── kb/
│   │   ├── INDEX.md                    # 知识库索引
│   │   ├── global/
│   │   │   ├── truth-model.md          # 真相模型
│   │   │   ├── memory-system.md        # 记忆系统规则
│   │   │   ├── memory-routing.md       # 记忆路由规则
│   │   │   ├── hook-contract.md        # Hook 契约
│   │   │   ├── project-map-governance.md # 项目地图治理
│   │   │   ├── INDEX.md               # 全局知识索引
│   │   │   └── memory-hook-policy-pack.json  # 策略包
│   │   └── projects/
│   │       └── {scope}.md             # 项目 scope 知识文件
│   ├── docs/
│   │   └── INDEX.md                    # 文档索引
│   ├── system/
│   │   ├── errors.log                  # 错误日志
│   │   └── health-report.json         # 健康检查报告（自动生成）
│   └── inbox.md                        # 临时任务捕获
├── project-map/
│   ├── INDEX.md                        # 合法目录地图索引
│   ├── legal-core-map.md              # 合法核心地图
│   └── ingestion-registry-map.md     # 摄入登记地图
├── artifacts/
│   └── memory-hook/
│       ├── contexts/YYYY-MM-DD/        # 日期分区快照
│       └── events/YYYY-MM-DD.jsonl     # 日期分区事件日志
└── INDEX.md                            # 工作区索引
```

## 版本管理

### memory.lock

`memory.lock` 是项目 `.memory/` 目录的版本锁定文件，记录当前使用的 schema 版本。每次 `memory-init` 会创建它，`memory-validate` 会校验它，`memory-migrate` 会更新它。

TOML 格式示例：
```toml
[memory]
memory_version = "0.2.0"
schema_version = "context-package-v1"
adapter_version = "builtin"
locked_at = "2026-04-29T00:00:00Z"
lock_reason = "initial"
```

### 升级流程

```
init → validate → migrate
```

1. **初始化**：新项目用 `memory-init` 创建 `.memory/` 结构
2. **校验**：用 `memory-validate` 确认当前结构完整
3. **迁移**：schema 升级时用 `memory-migrate --from <old> --to <new>` 执行迁移，`migrations.log` 会记录每次迁移的详细信息

## Runtime Capabilities

### L1 — Canonical & Policy Layer

gateway runtime（`memory_hook_gateway.py`、`memory_hook_core.py`）负责以下工作：

- 从 stdin 接收 JSON payload，解析为 `HookEvent`
- 根据 adapter profile 配置发现项目 scope、canonical 路径、policy
- 校验 project-map、legal contract、governance frozen tuple、event contract
- 构建 context package（包含 `system_context`、`project_context`、`task_context`、`allowed_reads`、`allowed_writes`、`evidence_refs`）
- 写入 artifact（snapshot JSON + latest JSON + event log JSONL）
- 通过 `HostDelegate` 将事件转发给 host（Codex/Factory；legacy Claude 仅保留兼容）

**Runtime 不负责：**

- 不管理业务数据读写（由 adapter policy 决定）
- 不直接执行 host 命令（通过 `HostDelegate` 间接调用）
- 不管理 schema 版本迁移（由 `memory-migrate` 负责）

### L2 — Integrity Layer

L2 完整性层为项目的 canonical 文件提供 SHA-256 + HMAC-SHA256 签名和验证，由三个模块组成：

| 模块 | 职责 |
|---|---|
| `memory_hook_integrity_keys.py` | HMAC-SHA256 密钥管理（生成、存储、加载），密钥位于 `~/.memory-core/keys/project-integrity.key` |
| `memory_hook_integrity_manifest.py` | 扫描项目 canonical 文件并生成 `manifest.json`（每个文件计算 SHA-256 和 HMAC 签名） |
| `memory_hook_integrity_verify.py` | 读取 `manifest.json` 验证当前文件完整性，报告篡改、缺失和新增未签名文件 |

**生命周期触发：**

- **`session-start`**：gateway 自动调用 `_integrity_verify(cwd)` 验证项目完整性，失败时降级但不阻塞
- **artifact 写入后**：gateway 自动调用 `_integrity_sign(cwd)` 重新签名 manifest
- **`memory-init`**：初始化时签名首个 manifest（best-effort，失败不阻塞）

**多项目隔离：** 每个项目在 `{project_root}/.memory/manifest.json` 维护独立的签名清单。HMAC 密钥全局共享，manifest 按项目隔离。

### Health Report

`memory_health_report.py` 提供异步健康检查能力：

- 在 `session-start` 时由 gateway 以后台进程方式启动（`_launch_async_health_check`）
- 检查结果写入 `{project_root}/memory/system/health-report.json`
- 下次 `session-start` 时注入上次检查结果到 context package（作为 alert）
- CLI 也可独立运行：`python memory_health_report.py --target /path/to/project`

### Project Lifecycle

`project_lifecycle.py` 追踪多项目的生命周期状态：

- 每个项目生成唯一 `project_id`（`{name}-{sha256[:12]}`），基于 git remote 或本地路径
- 独立项目记录写入 `PROJECT_LIFECYCLE_ROOT/projects/{project_id}.json`
- 维护 `path-index.json` 路径索引，支持路径到项目身份的映射
- 当项目路径被删除时标记为 `missing`，但**永不删除**记忆 artifact（`retention_policy: preserve-memory-on-missing-path`）

### Memory Root Discovery

`memory_root_discovery.py` 从 cwd 向上查找 `.memory/` 目录定位项目根：

- 找到 `.memory/` → 该目录即为项目根（project root）
- 找到 `.git/` 但没有 `.memory/` → monorepo sentinel，fallback
- 超过 8 层或到达文件系统根 → fallback 到 memory 仓库根
- 同时发现 workspace root：`{project_root}/memory_core/` 存在则使用，否则等于 project root

### Thread Safety

Gateway 配置层通过 `get_config(key)` + `_config_lock`（`threading.Lock`）提供线程安全访问。`reload_adapter()` 可安全切换 adapter 配置。同进程多项目并发推荐使用 `get_config()`；进程级隔离仍为推荐方案。

### Capability 声明方式

- 通过 adapter runtime profile（如 `workbot_runtime_profile.py`、`default_runtime_profile.py`）声明
- Profile 是一个 dict，包含路径、policy 值、scope 配置等
- Gateway 启动时加载 profile，写入 `_adapter_config` 和 module globals

### 与 adapter / host 的关系

- Adapter 提供 runtime profile（路径、策略、scope 映射）
- Host 通过 `HostDelegate` 与 runtime 交互
- Gateway 是 adapter profile + host delegate 的协调层

## 多项目架构

memory-core 支持在同一套安装下为多个业务项目提供独立的记忆管理。每个项目拥有自己的 `.memory/` 目录和完整的隔离上下文。

### 项目接入

每个业务项目通过 `memory-init --target /path/to/project` 初始化独立的 `.memory/` 结构。Gateway 运行时从目标项目的 `adapter.toml` 动态读取配置（project_scope、host、policy 等），无需在 memory 仓库中硬编码任何项目信息。

### 默认 Adapter（`default_runtime_profile`）

`default_runtime_profile.py` 是通用适配器，为任意项目自动构建 runtime profile：

- 从目标项目的 `.memory/adapter.toml` 读取 `routing.project_scope`
- 按动态 scope 构建 `project_canonical`、`project_runtime_root`、`project_doc_refs` 等映射
- 所有路径相对于目标项目根，不依赖 memory 仓库内部结构
- 通过 `MEMORY_HOOK_ADAPTER=default`（默认）选择此 adapter

### 项目隔离

| 维度 | 隔离方式 |
|---|---|
| Canonical 文件 | 每个项目 `{project_root}/.memory/` 下独立维护 |
| Artifact 输出 | 按项目路径写入各自的 `artifacts/memory-hook/` |
| L2 Manifest | 每个项目 `{project_root}/.memory/manifest.json` 独立签名 |
| Lifecycle 记录 | `PROJECT_LIFECYCLE_ROOT/projects/{project_id}.json` 按项目 ID 隔离 |
| Scope 路由 | `project_scope` 从各项目 `adapter.toml` 动态解析 |

### 项目发现

`memory_root_discovery.py` 从 cwd 向上查找 `.memory/` 目录定位项目根，支持：
- 单 git 仓库单项目
- Monorepo（多个子目录各有 `.memory/`）
- 未初始化项目通过 Codex 全局 hook 自动触发 `memory-init`

## Adapter Protocol

Adapter 通过 `adapter.toml` 声明项目的 identity、host、policy 配置，并通过 runtime profile 函数构建 gateway 所需的全部路径和策略配置。

### `adapter.toml` 结构（canonical layout）

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
project_scope = "my-project"
host = "codex"
canonical_files = []
# artifact_root = (optional)
```

### AdapterConfig

`load_adapter_toml()` 读取 `.memory/adapter.toml`，使用 `adapter_toml_schema.py` 进行结构化校验，返回 `AdapterConfig` dataclass：

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_name` | `str` | 项目名称 |
| `project_scope` | `str` | 项目 scope 标识 |
| `host` | `str` | host 平台（`codex`、`factory` 或 legacy `claude`），默认 `"codex"`；正式部署只支持 Codex App / Factory Droid 全局 hook 模式 |
| `adapter_version` | `str` | adapter 协议版本 |
| `canonical_files` | `list[str]` | canonical 文件列表 |
| `artifact_root` | `str \| None` | artifact 输出根目录（可选） |
| `legality_source_policy` | `str` | legal source 解析策略 |
| `registration_commit_policy` | `str` | 注册提交策略 |
| `registration_commit_phase` | `str` | 注册提交阶段 |

**Schema 校验：** `adapter_toml_schema.py` 提供完整的 TOML 结构校验，包括字段类型检查、必填字段验证、枚举值约束。支持从文件路径或 dict 加载。

### Runtime Profile

`build_default_runtime_profile(project_root)` 基于 `AdapterConfig` 构建 15 个通用配置 key，供 gateway 使用。

**与 runtime/host 的交互：**

- `load_adapter_toml()` 读取 `.memory/adapter.toml`，返回 `AdapterConfig`
- `build_default_runtime_profile(project_root)` 基于 `AdapterConfig` 构建 runtime profile dict
- Gateway 通过 `MEMORY_HOOK_ADAPTER` 环境变量选择 adapter（默认 `"default"`）

**最小 adapter 形态：**

- 一个 `build_*_runtime_profile(repo_root, workspace_root) -> dict[str, Any]` 函数
- 返回包含 `PROJECT_MAP_ROOT`、`TRUTH_MODEL`、`REQUIRED_CANONICAL`、`DEFAULT_PROJECT_SCOPE` 等必要 key 的 dict

## HookEvent & Schema

### HookEvent

`HookEvent` 是统一事件模型，将 Codex App、Factory Droid 和 legacy Claude 的 hook 输入归一化：

```python
@dataclass
class HookEvent:
    source: str         # "codex" | "factory" | "claude"
    event_type: str     # "session-start" | "prompt-submit" | "notification" | "stop"
    payload: dict[str, Any]
    cwd: Path
    timestamp: str      # ISO format
    project_scope: str  # default ""
```

**事件类型映射：**

- Codex：通过 `--event` CLI 参数直接传入 canonical name
- Factory：通过 `~/.factory/settings.json` 全局 hook 调用 wrapper，再以 `--host factory --event <canonical>` 传入
- Claude：legacy 兼容解析，原生事件名映射 — `SessionStart` → `session-start`，`UserPromptSubmit` → `prompt-submit`，`Notification` → `notification`，`Stop` → `stop`

**解析入口：** `parse_hook_event(host, event, raw_payload) -> HookEvent`

### Schema 转换链

系统内部维护三层 schema 格式：

| Schema | 用途 |
|---|---|
| `wb-hook-v2` | 内部 context package 格式（`build_context_package` 的输出） |
| `context-package-v1` | 公开格式：重命名 `project_context` → `project`、`task_context` → `task`，移除 `system_context` |
| `memory-v1` | 面向 `.memory/*` canonical 文件的格式，project section 只引用 `.memory/CANONICAL.md` 等 |

**转换函数：**

| 函数 | 说明 |
|---|---|
| `convert_to_v1(package)` | `wb-hook-v2` → `context-package-v1` |
| `convert_to_memory_v1(package)` | `wb-hook-v2` → `memory-v1` |
| `convert_legacy_to_memory_v1(package)` | 任意版本 → `memory-v1` |
| `build_context_package_simple(host, event, payload, adapter, schema)` | 简化入口，支持 `schema="context-package-v1"` 或 `schema="memory-v1"` |
| `is_lossless(input_obj, output_obj, direction)` | 检查转换是否有数据丢失，返回 `(bool, list[str])` |

**已知有损转换：**
- `wb-hook-v2` → `context-package-v1`：静默丢弃 `system_context`、`missing_paths`
- `context-package-v1` → `memory-v1`：project 只保留 scope，name/description/tech_stack 丢失
- `is_lossless()` 可在运行时检测这些丢弃，审计日志写入 `schema-audit.log`

## 设计原则

- **数据隔离**：所有业务数据只存在于业务项目自己的 `.memory/` 下，memory 仓库不存储任何业务数据。`memory-init` 包含安全守卫，拒绝在 memory 仓库内初始化业务目录。
- **协议优先**：仓库提供协议定义、schema 和工具；适配器通过 `adapter.toml` 和 runtime profile 按项目配置行为，不内建任何单项目默认绑定。
- **污染防护**：`memory-validate` 内置 pollution guard，防止 memory 仓库被写入业务状态。

## 开发与测试

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python -m pytest tests/
```

## 版本

- **当前版本**：v0.2.0
- **Python 要求**：>= 3.9

## License

MIT License. See [LICENSE](LICENSE) for details.

## Links
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [License](LICENSE)
