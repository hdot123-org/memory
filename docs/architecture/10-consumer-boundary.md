---
type: "[DOC:ARCHITECTURE]"
title: "消费边界与改进建议"
shortname: DES-010
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [consumer-boundary,improvements,suggestions]
related: [DES-001, DES-007, DES-008]
---

> 文档编号：DES-010 | 版本：V1.1 | 日期：2026-09-05 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05（v0.45.6）。如需精确接口签名，请参考源码（`memory_core/tools/`）。

# 消费边界分析与改进建议

> 创建日期：2026-04-26
> 维护人：D10（文档整理员）
> 状态：可评审
> 分析对象：`<memory-repo>`（memory-core 仓库，GitHub 主仓 `hdot123-org/memory`）

> **📌 2026-09-05 校准备注**（相对 2026-05-14 / v0.4.0 Beta 版快照的变更）：
>
> 1. **文件复制消费时代已结束（已移除）**：2026-05 版审计的「workbot 将 memory Python 源码整目录复制进自身仓库」消费模型已废弃。memory-core 现为可复用只读协议库（pip 包），消费项目通过 `memory-init` 在自身仓库初始化独立 `memory/` 结构，互不依赖、无源码复制。
> 2. **三层架构（v0.8.0）**：Layer 1 `~/.memory-core/`（全局运行时：主机级生命周期/path-index/完整性密钥）、Layer 2 `~/.memory/global-kb/`（operations/engineering/collaboration/pending + memory-promote 晋升流）、Layer 3 项目 `memory/`；读取路由项目优先、全局兜底。
> 3. **引擎迁移 infra-core（2026-08，M3/M5）**：version-sync、daily-audit、error-patterns、layout-audit 等执行体迁至 infra-core（`infra-*` CLI）；本仓 CI 维护 workflow 均为 thin caller（tag pin v0.11.1）。
> 4. **旧 §2 的四大边界问题全部出清**：37 参数膨胀已由 `CoreConfig` dataclass 解决；Gateway 过载已由 M3 六模块拆分（门面 + patch-redirect 兼容层）解决；「复制而非引用」已由 pip 分发解决；接口不兼容随 workbot adapter 移除（现仅 `default_runtime_profile` + `neutral_policy`）而消失。
> 5. **仓库托管现状**：GitHub 已成主仓库（AGENTS.md 铁律），GitLab 仅历史备份；`docs/specs/BOUNDARY.md` §8 的「GitLab source of truth」为历史条款，以 AGENTS.md 为准。
> 6. **新增 MCP 消费面**：`memory-mcp-server`（stdio，9 工具）为非 hook 平台提供 load_context / search_memory / save_memory 等消费入口。

---

## 1. 当前消费面审计

### 1.1 消费方式总览

**（历史标注）2026-05 版 §1.1 的「Workbot 文件复制清单」已移除。** 当前的消费模型：

| 消费通道 | 载体 | 说明 |
|----------|------|------|
| pip 安装 | `pip install git+https://github.com/hdot123-org/memory.git@v0.45.6` | 生产消费方式；消费项目安装 memory-core 包并获得全部 CLI 入口（§1.2） |
| 项目初始化 | `memory-init --target <project>` | 在消费项目生成 `memory/system/`、`memory/kb/` 等结构；四模式（create/adopt/update/repair）；同时幂等创建 Layer 2 全局 KB 并写入 `adapter.toml [global_kb]` 段 |
| Hook 接入 | `memory-factory-hooks install --storage-root ~/.memory-core` | 安装 Factory 全局 hook wrapper（`~/.factory/bin/memory-hook`），事件路由回当前项目目录；`render_wrapper()` 经 `shutil.which()` 把裸命令解析为绝对路径（修 daemon PATH 展开问题） |
| MCP 接入 | `memory-mcp-server [--tools a,b]` | stdio MCP server（829 行），9 工具：load_context / search_memory / resolve_doc_path / save_memory / validate_write / record_event / get_health / list_projects / get_daily_summary；`--tools` 可裁剪暴露子集 |
| 只读校验 | `memory-verify-consumer --target <project>` | 非 Factory 平台（Claude Code / Cursor / 自研 agent）自检 `memory/system/` 契约；只读不写；必查文件 `memory/system/adapter.toml` + `ownership.toml` |

**关键事实**：消费项目之间互不依赖——每个项目拥有自己的 `memory/`、`project-map/`、`memory/artifacts/memory-hook/`；共享的只有 Layer 2 全局 KB（读取兜底 + pending 晋升）与 Layer 1 主机级运行时（`~/.memory-core/`，生命周期/path-index/完整性密钥，不是项目记忆池）。

### 1.2 CLI 契约面（pyproject [project.scripts]，15 入口实测）

| # | 入口 | 模块:函数 |
|---|------|-----------|
| 1 | `memory-init` | `memory_core.tools.init_project_memory:main` |
| 2 | `memory-migrate` | `memory_core.tools.migrate_project_memory:main` |
| 3 | `memory-validate` | `memory_core.tools.validate_project_memory:main` |
| 4 | `memory-promote` | `memory_core.tools.promote_global_kb:main` |
| 5 | `memory-hook-gateway` | `memory_core.tools.hook_runtime_guard:gateway_main` |
| 6 | `memory-factory-hooks` | `memory_core.tools.factory_global_hooks:main` |
| 7 | `memory-consistency-check` | `memory_core.tools.consistency_check:main` |
| 8 | `memory-plan-residue` | `infra_core.packs.memory.layout_audit:plan_main`（执行体在 infra-core） |
| 9 | `memory-apply-residue-plan` | `memory_core.tools.apply_residue_plan:main` |
| 10 | `memory-ownership` | `memory_core.tools.ownership_cli:main` |
| 11 | `memory-verify-consumer` | `memory_core.tools.verify_consumer:main` |
| 12 | `memory-integrity-resign` | `memory_core.tools.memory_integrity_resign:main` |
| 13 | `memory-lifecycle-rebuild` | `memory_core.tools.project_lifecycle:rebuild_main` |
| 14 | `memory-lifecycle-migrate` | `memory_core.tools.project_lifecycle:migrate_main` |
| 15 | `memory-mcp-server` | `memory_core.tools.mcp_server:main_sync` |

> M5 收缩注记：evolution 引擎面六入口（audit-layout / sync-versions / audit-daily / error-patterns / evolution-audit / code-hygiene-audit）已迁 infra-core 对应 `infra-*` CLI，本仓 pyproject 不再持有。

### 1.3 memory-init 四模式与生成布局

```bash
memory-init --target /path/to/project [--scope my-project] [--host factory|zcode] \
    [--mode create|adopt|update|repair] [--dry-run] [--force] [--no-clobber] \
    [--no-auto-fill] [--json] [--version]
```

| 模式 | 用途 |
|---|---|
| `create` | 创建新的记忆布局 |
| `adopt` | 采纳已有项目，保留业务入口文件 |
| `update` | 更新带标记的记忆管理块，补建缺失文件 |
| `repair` | 仅补建缺失的必需文件，不覆盖已有文件 |

行为要点：
- 自动检测项目元数据（语言、框架、工具链、git remote）填充项目 scope 文件
- 保护已有 `AGENTS.md`、`INDEX.md`、`project-map/**`、`CLAUDE.md`（除非可安全更新受管块）
- 幂等创建 `~/.memory/global-kb/`（四域：operations / engineering / collaboration / pending，各带 README，INDEX.md 存在不覆盖）并在 `memory/system/adapter.toml` 写入 `[global_kb]` 段启用项目优先 / 全局兜底
- 必需文件（`memory_core/constants.py`）：`memory.lock`、`adapter.toml`、`migrations.log`；必需目录：`kb/projects`、`kb/decisions`、`kb/lessons`、`kb/global`

配套生命周期工具：
- `memory-validate`：校验布局完整性、frontmatter/TOML 合法性、版本兼容、污染守卫
- `memory-migrate`：版本/Schema 迁移并记 `migrations.log`；`0.7.0 → 0.8.0` 注入 `[global_kb]` 段（幂等）
- `memory-promote`：将 `~/.memory/global-kb/pending/` 自动捕获候选人工晋升到正式域并更新 INDEX.md
- `memory-lifecycle-rebuild` / `memory-lifecycle-migrate`：维护 Layer 1 path-index（`~/.memory-core/`）

### 1.4 调用链路全景

```
Factory/ZCode Hook 事件
    │
    ▼
~/.factory/bin/memory-hook（wrapper，绝对路径）
    │
    ▼
memory-hook-gateway = hook_runtime_guard:gateway_main()
    ├── install_guard()（SIGALRM 8s / SIGINT → exit 0）
    └── memory_hook_gateway.main()（_gateway_handlers，薄门面 + 六拆分模块）
        ├── _parse_args() → host(factory|zcode) / event(9 种) / no-delegate
        ├── pre-tool-use → PreToolUse 守卫（allow exit 0 / block exit 2）
        ├── session-start 旁路：健康检查 / STATE.md 刷新 / 遥测同步 / 版本跟随探测
        ├── 非注入事件 → 快速路径（生命周期 + 指标 + 最小 event log）
        └── 注入事件 → build_context_package()（CoreConfig 组装）
                          → ArtifactWriter 落盘（contexts/{day}/ + events/{day}.jsonl 双写）
                          → _build_factory_hook_output()（additionalContext 注入）
```

自动版本跟随（v0.40.1+，M1/M3）：session-start 时 gateway regex 读取项目 `memory/system/memory.lock` 的 `memory_version`，与 `CURRENT_MEMORY_VERSION` 不一致时进程内调用 infra-core 的 `sync_single_project`；升级门禁 `_gate_version_bump`：minor/patch 且 schema_version 一致 → 放行（原子修补 memory.lock / adapter.toml / ownership.toml 三文件 + `.sync.lock` 并发防护 + 同步后增量重签）；major 跳变 / Schema 变更 / 降级 → 拦截仅警告。任何异常不阻塞 hook 主链。

---

## 2. 边界规则

### 2.1 仓库定位（BOUNDARY.md 现行条款）

memory-core 是**通用记忆层模块仓库 / 可复用只读协议库**，承载协议定义、模板、Schema、Validator、Migration 工具与 demo fixture，**不存储任何业务项目状态**。核心原则：

| 原则 | 内容 |
|------|------|
| 单一归属 | 每个业务项目的 adapter.toml / ownership.toml / memory.lock 只能存在于该业务项目自身的 `memory/system/` |
| Fixture 与真实数据分离 | 仓内示例只能是 demo fixture（`demo-` / `fixture-` 前缀）；真实业务 PLAN/STATE/CANONICAL 必须在业务项目仓库 |
| 通用 vs 专用 | 只存放跨项目通用的协议、模板、Schema、Validator、Lesson；绑定具体业务上下文的内容属于业务项目 |
| 污染防护 | `.gitignore` 禁止清单拦截 `workspace/projects/*/` 等业务状态路径；违规 PR 在 review 中拒绝 |
| 引擎边界 | evolution/审计引擎执行体在 infra-core 仓；本仓仅保留协议面与 `.evolution/config.yml` 消费配置（rule_packs 引用） |

memory-core 源码仓自身受 source-repo-readonly 保护：hook 检测到自身时走只读规则包（`allowed_writes: {}`），develop 模式跳过消费者校验。

### 2.2 仓库托管现状（以 AGENTS.md 为准）

| 维度 | 现状 |
|------|------|
| 主仓库 | **GitHub**（`hdot123-org/memory`）——所有代码变更直接 push GitHub，走 feature 分支 + PR |
| 历史备份 | GitLab remote 保留用于历史备份，不再作为主开发流程 |
| 历史条款 | `docs/specs/BOUNDARY.md` §8 仍写「GitLab source of truth / Local→GitLab→GitHub 单向同步」，这是旧状态的历史条款；现行方向以 AGENTS.md 铁律（GitHub 主仓）为准 |

### 2.3 CI / 发布消费面

| 机制 | 现状 |
|------|------|
| 版本发布 | release-please 自动化（conventional commits 驱动；禁止手动 tag / 手动改版本号） |
| CI 门禁 | `ci-ok` 聚合门禁，**包含 droid-review**（AI review 失败即 ci-ok 失败）；分支保护 enforce_admins，任何情况禁止 `--admin` 绕过 |
| 合并 | auto-merge workflow（全绿后自动 squash）；session 创建 PR 后注册 webhook 路由即离开关键路径，不阻塞等 CI |
| 分支清理 | branch-cleanup 每日自动删除孤立分支（thin caller：`hdot123-org/infra-core/actions/branch-cleanup`，pin v0.11.1） |
| 维护 workflow | evolution-scan / evolution-heartbeat / evolution-governance / droid-review / auto-merge / branch-cleanup 均为 thin caller，执行体由 infra-core reusable workflows / composite actions 承载 |
| 质量门禁 | pytest `--cov-fail-under=80`、ruff（含 C901，零豁免）、mypy --strict 双域（scripts/ + memory_core/）、vulture、deptry、fix-has-test（修 bug 必加测试） |
| Issue 流转 | Linear 是唯一任务管理面板；GitHub Issue 是 evolution scanner 自动产物（label: evolution-found，自动创建 / 自愈关闭 / 带 flapping 防抖重开）；PR body `Fixes INFRA-xxx` 双路径自动闭环 |

---

## 3. 理想设计「一个入口一个出口」落地核对

**（历史标注）2026-05 版 §3 提出的四项目标已全部或大部落地**，逐项核对：

| 2026-05 目标 | 落地状态 | 现状实现 |
|--------------|----------|----------|
| Gateway 是唯一入口 | ✅ 已实现 | CLI console-script 唯一（`hook_runtime_guard:gateway_main`）；Python 侧 `build_context_package()` 为唯一公开编排入口，core 不可绕过 adapter/policy 接线 |
| Context Package 是唯一出口 | ✅ 已实现 | 出口结构三层 schema：内部 `wb-hook-v2` → 消费 `context-package-v1`（→ 可选 `memory-v1`），转换集中于 `memory_hook_schema.py`（详见 API-CONTRACT.md） |
| Core 是纯函数 | ✅ 已实现 | `build_context_package_core()` 纯组装，依赖全注入；`build_context_package_from_config(config: CoreConfig)` 提供结构化入口 |
| Adapter 是配置边界 | ✅ 已实现 | `memory_hook_adapters/` 现仅 `default_runtime_profile.py`（默认 profile，含 ARTIFACT_COMPACTION / GLOBAL_KB_* 等约 40 配置键）+ `neutral_policy.py`；workbot 专用 adapter 已移除 |

**37 参数问题的解决**（2026-05 版 §3.2.3 建议的 `CoreConfig`）已按建议实现，`memory_hook_config.py`：
- 5 组字段：环境（7）/ 路径（7）/ 策略（6）/ 回调（14）/ 接口对象与可选策略（5，`policy_registry: PolicyRegistry | None` + `path_utils: PathUtils | None` 可整体替代扁平回调）
- `__post_init__` 分组校验（host 必须在 SUPPORTED_HOSTS 内、路径类型、回调可调用性）
- `from_gateway_kwargs()` 桥接旧 37 kwargs；`to_gateway_kwargs()` 反向导出
- `memory_hook_core._resolve_callbacks()` 优先从接口对象取绑定方法，回退扁平回调字段——13 个 callback 可经 2 个接口对象（PolicyRegistry + PathUtils）注入

**Gateway 职责精简**（2026-05 版 §4.4 建议）已通过 M3 拆分实现：

| 模块 | 行数 | 职责 |
|------|------|------|
| `memory_hook_gateway.py` | 494 | 薄门面：re-export 全部符号 + `__all__` + excepthook 安装 + `__main__` 引导 |
| `_gateway_config.py` | 467 | 路径常量、适配器存储、IF-5 门面、完整性、生命周期 |
| `_gateway_artifacts.py` | 301 | artifact/error 写入、只读 source-repo package、健康检查 |
| `_gateway_policy.py` | 487 | core builder 解析、业务策略委托、build_context_package |
| `_gateway_telemetry.py` | 483 | PostHog 遥测同步、prompt 日志 |
| `_gateway_dispatch.py` | 444 | CWD 发现、delegate 执行、输出格式化 |
| `_gateway_handlers.py` | 495 | 事件处理器、main 入口、excepthook |

兼容性保障：`_gateway_patch_redirect.install_redirect()` 把对门面符号的 monkeypatch/patch.object 写入重定向到实际查找该符号的子模块，保持旧测试打桩语义不变（patch-redirect 兼容层）。

**「引用替代复制」**（2026-05 版 §4.3 阶段 3）已实现：memory-core 以 pip 包分发（`pip install git+https://github.com/hdot123-org/memory.git@v0.45.6`），消费项目 `pyproject.toml` 声明依赖即可；升级经自动版本跟随机制在 session-start 无感完成。

---

## 4. 剩余边界关注点

旧四大问题出清后，当前仍需关注的边界：

| 关注点 | 现状 | 缓解机制 |
|--------|------|----------|
| 引擎双仓耦合 | 执行体在 infra-core（pin v0.11.1 硬依赖），本仓仅 thin caller + 消费配置 | tag pin 固定版本；infra-core 消费仓接入指南文档化 |
| path-index 以 cwd 为键 | 全局模式 path-index 存在键错配（见 PATH_INDEX_SPEC.md） | 单项目模式为推荐路径（自动版本跟随即单项目模式） |
| 全局 KB 共享写 | Layer 2 全局 KB 跨项目共享，pending 自动捕获依赖 session-end | memory-promote 人工确认晋升；kb_policy read-first-CRUD |
| 遥测丢失容忍 | metrics.jsonl 锁竞争丢弃（设计决策） | 本地 JSONL 持久 + offset 断点续传 + 每小时窗口重试 |

---

## 5. 风险矩阵（更新）

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| infra-core pin 版本与 thin caller 漂移 | 低 | 中 | pyproject 依赖与 workflow pin 同版本（当前 v0.11.1）；升级同批提交 |
| 消费项目 schema_version 落后于库版本 | 中 | 低 | 自动版本跟随（minor/patch 自动同步；major/Schema 变更显式拦截） |
| 升级门误放行不兼容变更 | 低 | 高 | `_gate_version_bump` 阻止 major 跳变与 Schema 变更；`.sync.lock` 并发防护；同步后增量重签可校验 |
| 全局 KB pending 候选积压 | 中 | 低 | memory-promote 交互模式列出候选；域 README 说明晋升语义 |
| 遥测端点慢导致 hook 超时 | 低 | 中 | 直连 batch API 3s 超时 0 重试；2s 连通探测前置；全链 try/except 不传播 |

---

## 6. 附录

### 6.1 文件路径索引（现行模块）

| 职责 | 路径 |
|------|------|
| Gateway 门面 | `memory_core/tools/memory_hook_gateway.py` |
| Gateway 拆分模块 | `memory_core/tools/_gateway_{config,artifacts,policy,telemetry,dispatch,handlers}.py` |
| 引导守卫 | `memory_core/tools/hook_runtime_guard.py` |
| Core 组装 | `memory_core/tools/memory_hook_core.py` |
| 结构化配置 | `memory_core/tools/memory_hook_config.py`（CoreConfig） |
| 接口定义 | `memory_core/tools/memory_hook_interfaces.py`（HostDelegate / PolicyRegistry / GatewayBusinessPolicy / PathUtils / ArtifactSink / ErrorSink） |
| Schema 转换 | `memory_core/tools/memory_hook_schema.py`（wb-hook-v2 → context-package-v1 → memory-v1） |
| Adapter | `memory_core/tools/memory_hook_adapters/{default_runtime_profile,neutral_policy}.py` |
| 遥测 | `memory_core/tools/{memory_hook_metrics,telemetry_bridge,posthog_client,_gateway_telemetry}.py` |
| SessionEnd | `memory_core/tools/{session_end_logger,daily_summary_generator,error_logger}.py` |
| MCP server | `memory_core/tools/mcp_server.py` |
| 初始化 | `memory_core/tools/init_project_memory.py` + `_init_*.py` 子模块 |
| 消费者自检 | `memory_core/tools/verify_consumer.py` |
| 版本常量 | `memory_core/constants.py`（`CURRENT_MEMORY_VERSION` / `SUPPORTED_HOSTS` / `CANONICAL_MEMORY_LOCK_SCHEMA` 等） |

**（历史标注）2026-05 版 §1.1 表列出的 workbot 复制文件（workbot_runtime_profile.py / workbot_policy.py 等双仓副本）已移除**；消费侧不再持有 memory 源码副本。

### 6.2 相关文档

- [01-architecture.md](./01-architecture.md) — Memory 模块架构设计
- [08-data-pipeline.md](./08-data-pipeline.md) — 数据管道与 Sink（含遥测管道）
- [API-CONTRACT.md](./API-CONTRACT.md) — API 契约（context-package-v1）
- [issue-flow.md](./issue-flow.md) — GitHub↔Linear Issue 流转链路
- [../specs/BOUNDARY.md](../specs/BOUNDARY.md) — 仓库边界（§8 为历史条款）
- [../specs/M5-SHRINK-DISPOSITION.md](../specs/M5-SHRINK-DISPOSITION.md) — M5 引擎收缩处置记录
