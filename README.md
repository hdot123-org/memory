# memory-core

memory-core 提供可复用的 `memory/` 协议、模板、Schema 和 CLI 工具，用于项目级记忆管理。它是一个开源库，负责初始化、校验、迁移和审计记忆布局；本仓库不存储任何业务项目状态。

## 架构 (v0.41.0) <!-- x-release-please-version -->

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

## 遥测架构 (v0.41.0) <!-- x-release-please-version -->

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
pip install git+https://github.com/hdot123-org/memory.git@v0.41.0 <!-- x-release-please-version -->
```

升级到新版本：

```bash
pip install --upgrade git+https://github.com/hdot123-org/memory.git@v0.41.0 <!-- x-release-please-version -->
```

从 release wheel 安装：

```bash
gh release download v0.41.0 --repo hdot123-org/memory --pattern "*.whl" <!-- x-release-please-version -->
pip install memory_core-0.41.0 <!-- x-release-please-version -->
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

##### 自动版本跟随（auto version follow）

自 v0.40.1 起，hook gateway 在 `session-start` 事件自动探测消费者版本：regex 读取项目 `memory/system/memory.lock` 的 `memory_version`，与 `CURRENT_MEMORY_VERSION` 不一致时进程内调用 `sync_single_project`（单项目模式），无需人工触发。

升级门禁 `_gate_version_bump` 规则：

| 场景 | 行为 |
|------|------|
| minor / patch 且 `schema_version` 一致 | 放行，自动同步三文件（`memory.lock`、`adapter.toml`、`ownership.toml`；tmp + `os.replace` 原子写，`.sync.lock` 并发防护） |
| major 跳变 / Schema 变更 | 拦截，仅记警告 |
| 降级（target < current） | 拦截，仅记警告 |

- **失败安全**：探测或同步链路的任何异常均不阻塞 hook 主链（`exit 0` 语义）
- **手动 CLI**：`memory-sync-versions --target <项目>` 仍可用（推荐单项目模式；全局模式的 path-index 以 cwd 为键存在错配，详见 [`path-index` 规范](docs/specs/PATH_INDEX_SPEC.md)）
- **测试**：`tests/test_auto_version_follow.py`，17 用例覆盖六分支

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
- **PR 合并验证（信任链加固）** — 若 Issue body 中包含 `<!-- linear-linkback INFRA-xxx -->` 注释，调用 `_verify_fix_merged_via_linear()` 提取 Linear issue ID，通过 Linear GraphQL API 查询关联的 GitHub PR，再用 `gh pr view` 确认 PR 已合并（`mergedAt` 非空）。仅当 PR 已合并时才关闭 Issue。Linear API 不可用时 fail-open（返回 True，不阻塞关闭）。无 linkback 注释的 Issue 直接关闭（向后兼容）。
- **执行动作** — 通过 `gh issue close` 关闭对应 Issue，并附带中文说明评论（`该 finding 在最近一次扫描中已不再出现，自动关闭此 Issue。`）
- **保留对象** — 仍在当前 findings 中出现的 Issue 保持 open；无法解析出 `rule_id`/`location` 的 Issue 被跳过（不关闭）

### Issue 重开机制

scanner 每次运行时会调用 `_reopen_closed_issue()`（`scripts/evolution_scanner.py`），检查已关闭的 `evolution-found` Issue 是否重新出现：

- **匹配逻辑** — 遍历 closed 状态的 Issue，按 `(rule_id, location)` 匹配当前 findings
- **重开条件** — finding 重新出现且 `reopen_count < 3` 时重开 Issue，并在 history JSON 中递增计数器
- **防抖保护** — `reopen_count >= 3` 的 Issue 不再重开，防止反复开/关（flapping）

### 分支清理

`scripts/branch_cleanup.sh` 从 `.github/workflows/branch-cleanup.yml` 中提取，提供两种模式：

- `--scheduled` — 定时任务模式，扫描所有远程分支，删除无 open PR 且最后 commit 超过 24 小时的孤立分支
- `--immediate <branch>` — 立即删除指定分支（用于 PR 合并后清理）

heartbeat 告警自愈（`resolve_cleared_alerts()`）在本轮 tick 中异常类型全部消失时自动关闭告警 issue 并附中文自愈评论；info 级持续 finding 经 `check_persistent_info_findings()` 连续 ≥10 次快照出现后输出 `suppress.json` 条目提案（只打印不写盘，过期自动解除）。管道全链路（含 GATE A 三条放行路径与单向同步决策）见 [Issue 流转链路文档 §10](docs/architecture/issue-flow.md)。

完整的 GitHub↔Linear Issue 流转链路与职责约定见 [Issue 流转链路文档](docs/architecture/issue-flow.md)。

## webhook-scripts/（CI 通知与治理脚本镜像）

`webhook-scripts/` 是 `~/.factory/webhook/scripts/` 生产脚本的受管镜像。生产侧是 single source of truth；本目录经 PR 回填保持与生产侧 sha256 一致，作为审计与回滚依据。

**同步机制：** `scripts/sync-webhook-scripts.sh` 负责正向同步（repo → 生产），`--check` 模式执行漂移检查。受管文件清单定义在 `webhook-scripts/MANIFEST.sh`（`MANAGED_FILES` + `MANAGED_LIB_FILES`，`lib/` 目录整体纳管，另含跨目录同步映射 `CROSS_DIR_MAPPINGS`）。

**脚本清单：**

| 脚本 | 职责 |
|------|------|
| `trigger-ci-droid.sh` | CI 完成后注入消息；事件时重绑定 session；读取端按 `source` 分流 —— scanner 来源静默清理（gh 不可用走保守路径），session 来源探活 404 时交叉校验 sessions-index，fallback prompt 附带 `gh pr view` 上下文 |
| `write-pending-ci.sh` | PR 注册路由；支持 `--source session\|scanner` 与 `--context <意图>`（旧位置参数兼容，缺省默认 session） |
| `ci-timeout-watchdog.sh` | CI 超时兜底派发；scanner 超期文件 Phase A 跳过，畸形时间戳终态走 Phase B 处理 |
| `reconcile-evolution.sh` | 治理对账：DRY_RUN 守卫 + 127/126 分流 + E4 marker 豁免；红 PR 清道夫（open + CI 红 + 超 507min 阈值 → comment-then-close，双防抖，守则禁止静默关 PR） |
| `trigger-droid.sh` / `trigger-error-droid.sh` | Linear / PostHog 错误触发器 |
| `wiki-refresh.sh` | wiki 刷新（双臂 token 验证） |
| `ci-failed.sh` | CI 失败通知 |
| `webhook-hygiene.sh` | 每日 04:30 TTL 清理 |
| `local_branch_cleanup.sh` | 本地分支清理 |
| `lib/posthog.sh` | 统一 PostHog 上报（`POSTHOG_API_KEY` 走 env），回执写日志不再落 `/dev/null` |
| `lib/op-mcp.sh` | 1Password 凭据链（已入仓纳管） |

**质量门禁：** CI 对全仓 `*.sh` 执行 shellcheck（以 runner 预装工具链为准，不强制最低版本）；`sync-webhook-scripts.sh` 在同步落盘前对每个受管文件执行 `bash -n` + shellcheck（shell）/ `py_compile`（Python）校验，失败即 fail-closed 回滚；`tests/` 下有行为回归测试（`test_write_pending_ci_hardening.py`、`test_m5_rebinding.py`、`test_sync_webhook_scripts.py`、`test_red_pr_sweeper.py` 等，覆盖来源分流 / 红 PR 清道夫 / lib 漂移等场景）。

**关键约束：** `POSTHOG_API_KEY` 仅通过环境变量注入（plist `EnvironmentVariables`），脚本内禁止出现 `phc_` 字面量。

**修改纪律：** 先改生产侧（原子落盘：install + mv）→ 回填本目录 → 提 PR。

## 文档

- [文档索引](docs/INDEX.md)
- [`.memory/` 规范](docs/specs/DOT_MEMORY_SPEC.md)
- [`memory.lock` 规范](docs/specs/MEMORY_LOCK_SPEC.md)
- [`path-index` cwd 键局限规范](docs/specs/PATH_INDEX_SPEC.md)
- [仓库边界](docs/specs/BOUNDARY.md)
- [架构设计文档](docs/architecture/INDEX.md)
- [更新日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)

## 开发与验证

```bash
pip install -e ".[dev]"          # 首次安装开发依赖
ruff check .                     # Lint（含 C901 复杂度，max-complexity=15）
ruff format --check .            # 格式检查（CI 硬门禁）
python -m pytest tests/          # 测试 + 覆盖率（addopts 已含 --cov=memory_core --cov-fail-under=80）
python -m mypy --strict scripts/ # 类型检查（CI 硬门禁：scripts/ + memory_core/ 双域）
python -m mypy --strict memory_core/  # 类型检查（CI 硬门禁；与 scripts/ 同等强制）
deptry .                         # 依赖使用检查
vulture memory_core/ --min-confidence 80  # 死代码检查
python3 scripts/check_boundary.py
shellcheck scripts/*.sh
actionlint .github/workflows/*.yml
```

**质量门禁：** CI（ci-ok 聚合门禁）与 pre-commit 强制执行以下标准：

| 门禁 | 标准 |
|------|------|
| 覆盖率 | `--cov-fail-under=80`（pytest addopts；当前分支基线约 84%） |
| Lint | ruff（E,F,W,I,C901,UP,B,SIM,PTH），零 C901 豁免；ruff format --check |
| 类型 | mypy `--strict` 于 `scripts/` 与 `memory_core/`（双域硬门禁） |
| 死代码 | vulture `--min-confidence 80` 于 `memory_core/`，零发现 |
| 依赖 | deptry 零发现 |
| 工具版本 | ruff 0.16.1 / mypy 2.3.0，本地 / pre-commit / CI 三方对齐 |

CI pytest 在自建 runner 上以串行模式（`-n 0`）运行以保证覆盖率统计准确（并行分片会丢失覆盖数据）；本地并行（如 `-n 6`）验证标准不变。

**模块拆分与门面架构：** 最大的四个工具模块已按单一职责拆分为 `_gateway_*`、`_init_*`、`_audit_*`、`_migrate_*` 前缀的子模块（均 ≤500 行），原文件保留为薄门面（facade）：`memory_hook_gateway.py`、`init_project_memory.py`、`daily_kb_audit.py`、`migrate_project_memory.py`。patch-redirect 兼容层保证 `monkeypatch` 打在门面上的既有测试语义不变。

**CI 安全门禁：** `.github/workflows/droid-review.yml` 中 `security_block_on_high: "false"`（Advisory 模式），AI 安全审查仅留 Comment 不阻断合并。确定性工具（shellcheck、actionlint、pytest、fix-has-test guard）作为 CI 硬门禁负责实际阻断。

**Fix-has-test 门禁：** `scripts/check_fix_has_test.py` 强制执行"修一个 Bug 必加一个测试"原则。PR 中含 `fix:`/`hotfix:`/`bugfix:` commit 但未修改 `tests/` 下任何文件时，CI 直接失败。豁免 Dependabot PR、release-please PR、纯文档变更，以及非代码变更 PR（全部改动均不在 `memory_core/`、`scripts/`、`tests/` 下，如仅改 shell/workflow/文档的基础设施回填，由 bash -n/shellcheck/mission 验证覆盖）。

## 版本与许可

- 当前文档版本：v0.41.0 <!-- x-release-please-version -->
- Python: >= 3.9
- 许可证：MIT，详见 [LICENSE](LICENSE)。
