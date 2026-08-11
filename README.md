# memory-core

memory-core 提供可复用的 `memory/` 协议、模板、Schema 和 CLI 工具，用于项目级记忆管理。它是一个开源库，负责初始化、校验、迁移和审计记忆布局；本仓库不存储任何业务项目状态。

## 架构 (v0.18.5) <!-- x-release-please-version -->

memory-core 采用**三层架构**：

```
~/.memory-core/              ← Layer 1: 全局运行时（永不修改）
~/.memory/global-kb/         ← Layer 2: 全局知识库（v0.8.0 新增）
  operations/                ← 运维知识（服务器、部署、SSH 等）
  engineering/               ← 工程知识（CI/CD、工具链、决策）
  collaboration/             ← 协作知识（Agent 工作流、文档）
  pending/                   ← 自动捕获的待晋升候选
/Users/project/
  memory/                    ← Layer 3: 单项目入口
    system/                  ← 配置与状态文件
      adapter.toml           ← v0.8.0+ 起包含 [global_kb] 段
      ownership.toml
      memory.lock
      migrations.log
      manifest.json
      integrity-audit.jsonl
    kb/                      ← 项目知识库（项目优先路由）
    docs/                    ← 文档
    log/                     ← 日志
```

路由遵循**项目优先、全局兜底**策略：知识查找先命中项目 `memory/kb/`，当某领域条目缺失时再 fallback 到全局 `~/.memory/global-kb/`。全局兜底通过 `memory/system/adapter.toml` 中的 `[global_kb]` 段启用（`memory-init` 自动写入）。

项目级配置位于 `memory/system/`（而非 `.memory/`）。隐藏目录 `.memory/` 在 v0.5.0 中已移除。

## 遥测架构 (v0.18.5) <!-- x-release-please-version -->

memory-core 采用**本地优先遥测**设计，最大限度降低 hook 开销，同时确保数据可靠送达：

**数据流：**
```
hook 事件 (PreToolUse / SessionEnd / gateway)
  │
  ├─ 写入本地 JSONL (metrics.jsonl) — 微秒级，零网络阻塞
  │
  └─ session-start 同步（每小时窗口）：
       1. 检查 .last_sync 时间戳；若 < 3600s 则跳过
       2. 探测 PostHog 连通性（2s 超时）
       3. 通过 .offset 伴车文件批量发送未投递记录
       4. 成功后更新 .offset；从 JSONL 中截断已同步记录
```

**核心设计原则：**
- **Hook 热路径**：仅写入本地 JSONL（微秒级），不导入 PostHog SDK，零网络阻塞
- **session-start 批量同步**：每小时限流，2s 连通性探测，通过 offset 伴车文件增量推进
- **故障安全**：所有遥测逻辑包裹在 try/except 中；分析失败绝不影响 hook 行为
- **数据脱敏**：发送到 PostHog 前，完整文件路径替换为 basename
- **PostHog**：内置公开 API Key（来自 data 文件 default_posthog_key.txt）；设置 `POSTHOG_API_KEY=''` 可禁用

## 守卫与安全架构

memory-core 内置 **PreToolUse 守卫**，位于 Factory 与文件系统之间，决定每次写工具调用是否允许触碰项目记忆。守卫采用故障关闭设计：出现任何异常时，优先保护关键项目状态。

**守卫流程：**

```
工具调用 (Write / Edit / MultiEdit / NotebookEdit / Execute)
  │
  ├─ 从 stdin 读取 JSON 载荷
  ├─ 绝对路径归一化为项目相对路径
  ├─ 按所有权表分类路径
  │     (memory/kb, memory/system, memory/docs, memory/log)
  │
  v
决策: ALLOW (exit 0) | BLOCK (exit 2)
```

**核心设计原则：**

- **PreToolUse 拦截**：守卫在执行前拦截 `Write`、`Edit`、`MultiEdit`、`NotebookEdit` 和 `Execute`，通过所有权分类决定允许或阻止对 `memory/` 目录的操作。允许操作返回退出码 `0`；阻止操作返回退出码 `2`。
- **故障关闭保护**：当守卫自身失败时（JSON 解析错误、stdin 读取异常、项目根目录探测失败或子进程超时/崩溃），通过 `is_protected_path_target()` 回退到上下文感知的故障关闭逻辑。针对受保护路径（`memory/kb/`、`memory/system/`、`memory/docs/`、`memory/log/`）的操作在守卫失败时**一律拒绝**；非保护路径**允许通过**并记录错误日志。这确保即使守卫崩溃，关键项目状态也绝不会被损坏。
- **双格式 hook 输出**：守卫同时输出旧版和 Factory 官方格式的 JSON，以保持向后兼容：

  ```json
  {
    "decision": "allow",
    "reason": "path not in protected domains",
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "allow",
      "permissionDecisionReason": "path not in protected domains"
    }
  }
  ```

  gateway 透明转发此输出。注意映射关系：旧版 `block` → 官方 `deny`。

- **共享脱敏模块**：`memory_core/tools/_redaction.py` 提供集中的 `redact()` 和 `redact_dict()` 函数，覆盖 API token（`sk-`、`sk-ant-`、`ghp_`、`AKIA`、`lin_api_`、`glpat-`）、JWT 类 token、认证头（`Authorization: Bearer/Basic`、裸 `Bearer`）、密码/密钥参数、私有 IP 地址（`192.168.x.x`、`10.x.x.x`、`172.16-31.x.x`）和用户 home 路径。全部四个日志/指标消费者（`log_utils`、`gateway`、`error_logger`、`telemetry_bridge`）均委托此共享模块，确保任何输出通道都不会泄露密钥。
- **绝对路径归一化**：所有权分类器通过单一共享函数 `_normalize_to_project_relative` 将绝对文件路径归一化为项目根相对路径（单一事实源，遵循与共享脱敏模块相同的整合模式）。该函数位于 `memory_core/ownership.py`，在 `classify_owned_path` 内部仅调用一次，因此每条分类路径（Write/Edit、MultiEdit、NotebookEdit、Execute）都受益于一致的绝对路径处理，无需重复逻辑。这确保无论 Factory 发送相对路径还是绝对路径，四个保护标记都能被正确阻止，杜绝了绝对路径写操作绕过相对路径匹配的分类漏洞。

## 安装

从 GitHub 安装（非可编辑模式，生产用途）：

```bash
pip install git+https://github.com/hdot123/memory.git@v0.18.5 <!-- x-release-please-version -->
```

升级到新版本：

```bash
pip install --upgrade git+https://github.com/hdot123/memory.git@v0.18.5 <!-- x-release-please-version -->
```

从 release wheel 安装：

```bash
gh release download v0.18.5 --repo hdot123/memory --pattern "*.whl" <!-- x-release-please-version -->
pip install memory_core-0.18.5 <!-- x-release-please-version -->
```

仅用于本地开发：

```bash
pip install -e ".[dev]"
```

**注意**：生产部署应使用 `pip install`（非可编辑模式）。可编辑安装（`pip install -e`）仅用于开发。

## 快速开始

初始化目标项目：

```bash
memory-init --target /path/to/project
```

校验生成的记忆布局：

```bash
memory-validate --target /path/to/project
```

在 Schema 版本间迁移：

```bash
memory-migrate --target /path/to/project --from 0.7.0 --to 0.8.0
```

## 核心 CLI 命令

### `memory-init`

在 `memory/system/` 下创建或更新标准项目记忆结构。自动检测项目元数据（语言、框架、工具链、git remote）并填充到项目 scope 文件中。

从 v0.8.0 起，`memory-init` 还会在 `~/.memory/global-kb/` 创建全局知识库结构（幂等操作），并在 `memory/system/adapter.toml` 中写入 `[global_kb]` 段以启用项目优先 / 全局兜底路由。

```bash
memory-init --target /path/to/project [--scope my-project] [--host factory] [--mode create|adopt|update|repair] [--dry-run] [--force] [--no-clobber] [--no-auto-fill] [--json] [--version]
```

模式说明：

| 模式 | 用途 |
|---|---|
| `create` | 创建新的记忆布局。 |
| `adopt` | 采纳已有项目，保留业务入口文件。 |
| `update` | 更新带标记的记忆管理块，补建缺失文件。 |
| `repair` | 仅补建缺失的必需文件，不覆盖已有文件。 |

`memory-init` 保护已有的 `AGENTS.md`、`INDEX.md`、`project-map/**` 和 `CLAUDE.md`，除非可以安全更新受管块。

### 布局治理

在采纳前后使用以下命令检查遗留布局、运行时残留和根级生成报告：

```bash
memory-audit-layout --target /path/to/project --json
memory-plan-residue --target /path/to/project --output residue-plan.json
memory-apply-residue-plan --target /path/to/project --plan residue-plan.json --dry-run
```

`memory-apply-residue-plan` 仅自动执行低风险操作，例如将已识别的根级生成报告移动到 `artifacts/reports/`。不会覆盖受保护的业务入口文件。

### `memory-validate`

检查 `memory/system/` 是否存在、必需文件是否齐全、frontmatter 和 TOML 是否合法、版本字段是否兼容、污染守卫是否通过。

```bash
memory-validate --target /path/to/project [--dry-run] [--json]
```

### `memory-migrate`

执行版本/Schema 迁移，并将结果记录到 `migrations.log`。

```bash
memory-migrate --target /path/to/project --from 0.7.0 --to 0.8.0 [--dry-run] [--json] [--version]
```

`0.7.0 → 0.8.0` 迁移会向 `adapter.toml` 注入 `[global_kb]` 段（默认 `enabled = true`、`root = "~/.memory/global-kb"`）并更新锁定版本。该操作是幂等的：若 `[global_kb]` 已存在，则仅更新版本。

### `memory-promote`

将全局 KB `pending/` 目录中自动捕获的知识候选提升为正式领域（`operations/`、`engineering/` 或 `collaboration/`）。这是沉淀流的人工确认步骤：`session-end` 自动捕获候选到 `~/.memory/global-kb/pending/`，`memory-promote` 将审核后的文件移入目标领域并更新 `INDEX.md`。

```bash
memory-promote                                          # 列出待处理候选
memory-promote <file> --to operations|engineering|collaboration
memory-promote --version
```

### 全局批量操作

以下命令跨生命周期 path-index（`path-index.json`）中注册的所有项目执行。用于生命周期维护，如无特殊说明不带 `--target`。

#### `memory-sync-versions`

同步项目 scope 文件中锁定的 memory-core 版本。全局模式（不带 `--target`）遍历 `path-index.json` 中的每个项目，在升级门允许时修补三个文件：`ownership.toml`、`memory.lock` 和 `adapter.toml`。带 `--target` 时对单个项目执行相同逻辑。

升级门允许 patch 和 minor 版本升级（要求 `schema_version` 不变），并修补全部三个文件。阻止 major 版本升级或 Schema 变更；此情况下仍修补 `ownership.toml` 以保持向后兼容，并提示用户使用 `memory-migrate`。

```bash
memory-sync-versions                              # 全局：同步所有项目
memory-sync-versions --target /path/to/project    # 单项目
memory-sync-versions --dry-run --json
```

#### `memory-lifecycle-rebuild`

从 `projects/*.json` 生命周期记录重建 `path-index.json`。当索引过期、缺失条目或与磁盘上的 `projects/` 目录不一致时使用。过滤非活跃和缺失记录，按 `local_path` 去重（保留 `observed_at` 最新的记录），原子写入结果。

```bash
memory-lifecycle-rebuild                          # 原地重建索引
memory-lifecycle-rebuild --dry-run --json
memory-lifecycle-rebuild --lifecycle-root /custom/lifecycle/root
```

#### `memory-audit-daily`

全局每日完整性审计。遍历 `path-index.json` 中注册的每个项目，检查 manifest 完整性、未签名文件和版本一致性。无 `--target` 选项，始终为全局操作。

```bash
memory-audit-daily --json
memory-audit-daily --dry-run
```

#### `memory-error-patterns`

全局错误模式检测器（Layer D）。跨项目扫描 `memory/log/*-errors.jsonl` 文件，通过智能归一化（路径、时间戳、UUID、hex、数字全部抽象化）对重复错误进行指纹识别，将机器可读的模式注册表写入 `memory/kb/patterns/registry.jsonl`。满足阈值（>=2 个不同天数 或 >=5 次总计数）的模式标记为 `threshold_met`。仅检测，不修改 KB，不自动生成 lesson。

```bash
memory-error-patterns                                    # 从 cwd 自动检测项目
memory-error-patterns --project /path/to/project         # 单项目
memory-error-patterns --all-projects                     # 所有项目（launchd 每日 23:55）
memory-error-patterns --dry-run --verbose                # 预览不写入注册表
```

## 生成的项目布局

由 `memory-init` 初始化的目标项目获得项目级记忆布局，同时 `memory-init` 确保共享全局知识库存在：

```text
~/.memory/global-kb/                  ← Layer 2: 共享全局 KB（创建一次，幂等）
├── INDEX.md
├── operations/
│   └── README.md
├── engineering/
│   └── README.md
├── collaboration/
│   └── README.md
└── pending/                          ← 自动捕获的候选（通过 memory-promote 晋升）
    └── README.md

<project>/
├── memory/
│   ├── system/
│   │   ├── memory.lock
│   │   ├── adapter.toml              ← v0.8.0+ 起包含 [global_kb] 段
│   │   ├── migrations.log
│   │   ├── manifest.json
│   │   ├── integrity-audit.jsonl
│   │   └── kb/
│   ├── kb/
│   │   └── INDEX.md
│   ├── docs/
│   └── log/
├── project-map/
├── artifacts/memory-hook/
└── INDEX.md
```

全局 KB（`~/.memory/global-kb/`）在所有启用全局路由的项目间共享；每个项目仍拥有自己的 `memory/`、`project-map/` 和 `artifacts/memory-hook/`。项目记忆和运行时 artifacts 属于目标项目。memory-core 仓库包含可复用的协议、代码、模板、Schema、fixture 和文档。

## 全局 Hook 设置

memory-core 支持 Factory Droid 全局 hook 入口点。全局 hook 作为稳定封装层，将每个事件路由回当前项目目录。

Factory Droid：

```bash
memory-factory-hooks install --storage-root ~/.memory-core
```

`~/.memory-core` 下的全局状态存储主机级生命周期/path-index 数据和完整性密钥，不是项目记忆池。项目记忆位于目标项目的 `memory/system/`、`memory/` 和 `artifacts/memory-hook/` 路径下。

## SessionEnd Hook 安全架构

SessionEnd hook 运行在 Factory 会话关闭的最后时刻，必须在严格超时窗口内干净退出。早期实现在导入阶段或巨型日志扫描时收到 SIGINT 会抛出 traceback 并以非零码退出，导致 Factory 误判为崩溃。本节记录 v0.15.6 引入的四层防护。

**1. 引导守卫（hook_runtime_guard.py）**

`memory-hook-gateway` 的 console-script 入口点从 `memory_hook_gateway:main` 改为 `hook_runtime_guard:gateway_main`。新入口在导入 gateway 模块**之前**先安装信号处理器，确保即使 import 阶段耗时也能干净退出：

| 信号 | 行为 | 超时 |
|---|---|---|
| `SIGALRM` | `_exit0_handler` → `sys.exit(0)` | 8 秒（早于 Factory 的 10s 硬超时） |
| `SIGINT` | 同上，`exit 0`，无 traceback | — |

`_BOOT_SECONDS = 8` 仅在 `__main__` 上下文安装，pytest import 时不触发定时器，避免测试被误杀。

**2. 日志确定性预算扫描（session_end_logger.py）**

`_extract_session_info_streaming` 重写为确定性双预算扫描，防止超大 JSONL 文件挂起进程：

| 参数 | 值 | 含义 |
|---|---|---|
| `TIME_BUDGET` | 1.8s | 单次扫描时间上限 |
| `BYTE_BUDGET` | 8 MB | 单次扫描字节上限 |
| `CHUNK_SIZE` | 64 KB | 每次读取块大小 |
| `MAX_LINE` | 1 MB | 超过此长度的行直接跳过 |

达到任一预算时立即停止并写入 `truncated: true` 标记，保留已采集的有效片段。

**3. Git 子进程超时与 CWD 复用（ownership.py）**

`discover_project_root` 的 `git rev-parse` 子进程增加 `timeout=2`，防止损坏的 git 仓库无限阻塞。同时优先复用 shell wrapper 注入的 `MEMORY_HOOK_PROJECT_CWD` 环境变量，减少冗余子进程探测。

**4. Wrapper 绝对路径解析（factory_global_hooks.py）**

`render_wrapper()` 在安装时通过 `shutil.which()` 将裸 `memory-hook-gateway` 解析为绝对路径，写入 wrapper 脚本。这解决了 Factory daemon 执行上下文中 PATH 未正确展开导致命令找不到的问题。

## Evolution Scanner 与 Issue 自动维护

memory-core 仓库自身通过 evolution scanner（`scripts/evolution_scanner.py`，GitHub Actions cron 每 30 分钟触发）进行自动化维护。scanner 会在审计发现问题时自动创建带 `evolution-found` 标签的 GitHub Issue，并在问题自愈后自动关闭，避免 Issue 无限堆积。

### 已解决 Issues 自动关闭机制

scanner 每次运行末尾会调用 `auto_close_resolved()`（`scripts/evolution_utils.py`）作为补偿机制，关闭已经不再出现的 finding 对应的 open Issue：

- **触发时机** — 在本次扫描创建新 Issue **之后**执行，避免误关闭刚创建的 Issue
- **判定标准** — 以 `(rule_id, location)` 为键，构建当前扫描的 findings 集合；对所有 open 的 `evolution-found` Issue 解析 body 中的 `rule_id` 与 `location`，若该键**不在**当前 findings 集合中，则视为「已解决」
- **执行动作** — 通过 `gh issue close` 关闭对应 Issue，并附带中文说明评论（`该 finding 在最近一次扫描中已不再出现，自动关闭此 Issue。`）
- **保留对象** — 仍在当前 findings 中出现的 Issue 保持 open；无法解析出 `rule_id`/`location` 的 Issue 被跳过（不关闭）

完整的 GitHub↔Linear Issue 流转链路与职责约定见 [Issue 流转链路文档](docs/architecture/issue-flow.md)。

## 文档

- [文档索引](docs/INDEX.md)
- [`.memory/` 规范](docs/specs/DOT_MEMORY_SPEC.md)
- [`memory.lock` 规范](docs/specs/MEMORY_LOCK_SPEC.md)
- [仓库边界](docs/specs/BOUNDARY.md)
- [架构设计文档](docs/architecture/INDEX.md)
- [更新日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)

## 开发与验证

```bash
ruff check .
deptry .
python -m pytest tests/
python3 scripts/check_boundary.py
```

## 版本与许可

- 当前文档版本：v0.18.5 <!-- x-release-please-version -->
- Python: >= 3.9
- 许可证：MIT，详见 [LICENSE](LICENSE)。
