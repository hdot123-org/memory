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
| `--host` | 指定 host 平台（`codex` 或 `claude`，默认 `codex`），影响 `.claude/hooks.json` 和 `AGENTS.md` 中生成的 gateway 命令 |
| `--dry-run` | 只输出将要执行的操作，不实际写入文件 |
| `--json` | 以 JSON 格式输出结果，便于脚本集成 |

**使用示例：**

```bash
# 最小可运行命令
memory-init --target /path/to/project

# 显式指定 scope 和 host
memory-init --target /path/to/project --scope my-project --host claude

# 预览（不写入文件）
memory-init --target /path/to/project --dry-run

# JSON 输出
memory-init --target /path/to/project --dry-run --json
```

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
├── migrations.log     # 迁移日志
└── kb/
    ├── projects/      # 项目知识
    ├── decisions/     # 决策记录
    ├── lessons/       # 经验教训
    └── global/        # 全局规范
```

## 版本管理

### memory.lock

`memory.lock` 是项目 `.memory/` 目录的版本锁定文件，记录当前使用的 schema 版本。每次 `memory-init` 会创建它，`memory-validate` 会校验它，`memory-migrate` 会更新它。

### 升级流程

```
init → validate → migrate
```

1. **初始化**：新项目用 `memory-init` 创建 `.memory/` 结构
2. **校验**：用 `memory-validate` 确认当前结构完整
3. **迁移**：schema 升级时用 `memory-migrate --from <old> --to <new>` 执行迁移，`migrations.log` 会记录每次迁移的详细信息

## Runtime Capabilities

gateway runtime（`memory_hook_gateway.py`、`memory_hook_core.py`）负责以下工作：

- 从 stdin 接收 JSON payload，解析为 `HookEvent`
- 根据 adapter profile 配置发现项目 scope、canonical 路径、policy
- 校验 project-map、legal contract、governance frozen tuple、event contract
- 构建 context package（包含 `system_context`、`project_context`、`task_context`、`allowed_reads`、`allowed_writes`、`evidence_refs`）
- 写入 artifact（snapshot JSON + latest JSON + event log JSONL）
- 通过 `HostDelegate` 将事件转发给 host（Codex/Claude）

**Runtime 不负责：**

- 不管理业务数据读写（由 adapter policy 决定）
- 不直接执行 host 命令（通过 `HostDelegate` 间接调用）
- 不管理 schema 版本迁移（由 `memory-migrate` 负责）

**Capability 声明方式：**

- 通过 adapter runtime profile（如 `workbot_runtime_profile.py`、`default_runtime_profile.py`）声明
- Profile 是一个 dict，包含路径、policy 值、scope 配置等
- Gateway 启动时加载 profile，写入 `_adapter_config` 和 module globals

**与 adapter / host 的关系：**

- Adapter 提供 runtime profile（路径、策略、scope 映射）
- Host 通过 `HostDelegate` 与 runtime 交互
- Gateway 是 adapter profile + host delegate 的协调层

## Adapter Protocol

Adapter 通过 `adapter.toml` 声明项目的 identity、host、policy 配置，并通过 runtime profile 函数构建 gateway 所需的全部路径和策略配置。

### `adapter.toml` 结构（canonical layout）

```toml
[core]
version = "0.1.0"
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

`load_adapter_toml()` 读取 `.memory/adapter.toml`，返回 `AdapterConfig` dataclass：

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_name` | `str` | 项目名称 |
| `project_scope` | `str` | 项目 scope 标识 |
| `host` | `str` | host 平台，默认 `"codex"` |
| `adapter_version` | `str` | adapter 协议版本 |
| `canonical_files` | `list[str]` | canonical 文件列表 |
| `artifact_root` | `str \| None` | artifact 输出根目录（可选） |
| `legality_source_policy` | `str` | legal source 解析策略 |
| `registration_commit_policy` | `str` | 注册提交策略 |
| `registration_commit_phase` | `str` | 注册提交阶段 |

### Runtime Profile

`build_default_runtime_profile(project_root)` 基于 `AdapterConfig` 构建 15 个通用配置 key，供 gateway 使用。

**与 runtime/host 的交互：**

- `load_adapter_toml()` 读取 `.memory/adapter.toml`，返回 `AdapterConfig`
- `build_default_runtime_profile(project_root)` 基于 `AdapterConfig` 构建 runtime profile dict
- Gateway 通过 `MEMORY_HOOK_ADAPTER` 环境变量选择 adapter（默认 `"workbot"`）

**最小 adapter 形态：**

- 一个 `build_*_runtime_profile(repo_root, workspace_root) -> dict[str, Any]` 函数
- 返回包含 `PROJECT_MAP_ROOT`、`TRUTH_MODEL`、`REQUIRED_CANONICAL`、`DEFAULT_PROJECT_SCOPE` 等必要 key 的 dict

## HookEvent & Schema

### HookEvent

`HookEvent` 是统一事件模型，将 Codex 和 Claude 的 hook 输入归一化：

```python
@dataclass
class HookEvent:
    source: str         # "codex" | "claude"
    event_type: str     # "session-start" | "prompt-submit" | "notification" | "stop"
    payload: dict[str, Any]
    cwd: Path
    timestamp: str      # ISO format
    project_scope: str  # default ""
```

**事件类型映射：**

- Codex：通过 `--event` CLI 参数直接传入 canonical name
- Claude：原生事件名映射 — `SessionStart` → `session-start`，`UserPromptSubmit` → `prompt-submit`，`Notification` → `notification`，`Stop` → `stop`

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
