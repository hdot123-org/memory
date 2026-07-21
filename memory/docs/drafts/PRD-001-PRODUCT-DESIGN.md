---
type: "[DOC:PRD]"
title: "Memory-Core 产品设计文档"
shortname: "PRD-001"
status: "草案"
scope: "product-design"
created: "2026-05-26"
updated: "2026-05-26"
source: "manual"
confidence: "high"
tags: ["product", "design", "prd"]
---

> 文档编号：PRD-001 | 版本：V2.0 | 日期：2026-05-26

# Memory-Core 产品设计文档

## 1. 产品定位

### 1.1 一句话定义

memory-core 是一个开源 Python 库，通过"一个入口一个出口"的核心契约，为 AI Agent 提供标准化的项目上下文注入协议。

### 1.2 核心哲学

**一个入口，一个出口** —— 所有平台、所有事件，统一入口统一出口。

无论用户使用 Codex、Claude 还是 Factory，无论触发的是 session-start、prompt-submit 还是其他 9 个事件，都通过同一个 Gateway 入口进入，获得同一个标准化格式的上下文包输出。调用方只需关注三个信息：谁在调用（host）、什么时候调用（event）、调用上下文（payload），其余 34 个配置参数、47 个 adapter 配置全部由 Gateway 自动组装。

### 1.3 与竞品的根本差异

| 维度 | memory-core | 传统方案 |
|------|-------------|----------|
| **思维模式** | 协议思维 —— 定义 Agent 如何获取项目上下文的协议 | 工具思维 —— 提供 CLI 工具集 |
| **接口设计** | 统一契约 —— 一个入口，一个出口 | 分散接口 —— 每个平台各自实现 |
| **核心抽象** | context-package 标准化输出 | 自由格式输出 |

memory-core 不是一组 CLI 工具的集合，而是一套关于"Agent 如何获取项目上下文"的协议规范。CLI 工具只是协议的实现载体。

---

## 2. 核心契约：一个入口一个出口

### 2.1 入口规范

调用方只需提供三个信息：

| 参数 | 含义 | 示例 |
|------|------|------|
| **host** | 谁在调用（平台身份） | `codex`, `claude`, `factory` |
| **event** | 什么时候调用（事件类型） | `session-start`, `prompt-submit`, `pre-tool-use` 等 9 种 |
| **payload** | 调用上下文 | 平台特定的原始事件数据 |

不管是 Codex、Claude 还是 Factory，不管是 session-start、prompt-submit 等 9 个事件，都走同一个入口 `build_context_package(host, event, payload)`。

内部 34 个配置参数、47 个 adapter 配置，全部由 Gateway 自动组装，调用方完全不需要关心。

### 2.2 出口规范

输出一个标准化的上下文包（context-package-v1），包含以下字段：

```
{
  "scope": "项目唯一标识",
  "truth_status": "ok | degraded",
  "paths": {
    "project_root": "/path/to/project",
    "memory_root": "/path/to/project/memory"
  },
  "allowed_reads": ["允许读取的文件路径列表"],
  "allowed_writes": {
    "targets": ["允许写入的目标"],
    "kb_policy": "知识库写入策略"
  },
  "truth_basis": {
    "source_refs": ["来源引用"],
    "authority_refs": ["权威引用"],
    "evidence_refs": ["证据引用"],
    "conflict_status": "resolved | unresolved"
  },
  "validation_errors": ["验证错误列表（如果有）"]
}
```

只有两个状态：
- **ok** —— 一切正常，Agent 获得完整上下文
- **degraded** —— 降级状态，附带具体错误信息，Agent 获得有限上下文

### 2.3 入口路由规范（读取路由）

定义 Agent 可以从哪些知识来源获取信息：

| 路由名称 | 目标路径 | 内容说明 |
|----------|----------|----------|
| **global-rule** | `memory/kb/global/` | 全局规则（truth-model、hook-contract、policy-pack 等） |
| **project-canonical** | `memory/kb/projects/{scope}/` | 项目知识：CANONICAL、STATE、PLAN、TASKS |
| **decision** | `memory/kb/decisions/` | 决策记录 |
| **lesson** | `memory/kb/lessons/` | 经验教训 |
| **fact** | `memory/log/{date}.md` | 每日事实日志（append-only） |
| **source-material** | `memory/docs/references/` | 参考资料 |
| **system-state** | `memory/system/` | 系统状态（manifest、health-report） |

### 2.4 出口路由规范（写入路由）

定义 Agent 可以向哪些目标写入：

| 路由名称 | 目标路径 | 用途 |
|----------|----------|------|
| **project-canonical** | `memory/kb/projects/{scope}/` | 项目知识写入 |
| **global-canonical** | `memory/kb/global/` | 全局规则写入 |
| **decision** | `memory/kb/decisions/` | 决策记录 |
| **lesson** | `memory/kb/lessons/` | 经验教训 |
| **fact** | `memory/log/{date}.md` | 每日事实 |
| **docs** | `memory/docs/` | 文档 |
| **action** | `memory/inbox.md` | 临时任务 |
| **artifacts** | `artifacts/` | 运行时产物 |
| **system-error** | `memory/system/errors.log` | 系统错误日志 |

**写入策略（kb_policy）：**
- **read-first-CRUD**：先读后写，确保读取最新状态后再修改
- **overwrite_allowed = false**：禁止覆盖已有文件
- **conflict_strategy = preserve-and-escalate**：冲突时保留原文件并升级处理

---

## 3. 入口流程（完整链路）

```
平台 Hook 触发（Codex/Claude/Factory）
  │
  ├── HOME 目录反污染检查
  │     └── cwd = HOME → 输出空 JSON 退出
  ├── Source Repo Readonly 检测
  │     └── 项目是 memory-core 自身 → 只读模式
  └── Auto-init（项目缺少 memory/system/）
        └── 自动执行 memory-init
  │
  ▼
Gateway 入口：build_context_package(host, event, payload)
  │
  ├── 1. 发现项目根
  │     └── 从 cwd 向上查找 memory/system/
  ├── 2. 确定项目 scope
  │     └── 通过 adapter.toml 或路径匹配
  ├── 3. 加载 adapter 配置
  │     └── 47 个配置 key，注入 37 个参数到核心组装
  ├── 4. Provider 双轨机制
  │     ├── external-core 可选（高级配置）
  │     └── legacy 默认（失败自动 fallback）
  ├── 5. 读取知识来源
  │     └── 7 种读取路由（见 2.3）
  ├── 6. 验证完整性
  │     ├── canonical 文件存在性
  │     ├── truth basis 四要素检查
  │     ├── ownership 域完整性
  │     ├── project-map 合法性（active-legal-map-only）
  │     └── governance frozen tuple 检查
  │     全部通过 → status = "ok"
  │     有错误   → status = "degraded" + validation_errors
  ├── 7. Artifact Compaction
  │     └── 根据 adapter 配置裁剪输出字段
  ├── 8. 构建标准化输出
  │     └── context-package-v1
  ├── 9. 上下文持久化（三写）
  │     ├── snapshot：带时间戳的完整快照
  │     ├── latest：最新一份覆盖写入
  │     └── events.jsonl：append-only 事件日志
  ├── 10. 健康报告
  │     └── 异步启动，下次 session-start 注入结果
  ├── 11. Delegate 分派
  │     └── Codex/Claude/Factory + Noop Fallback
  ├── 12. Hook 状态管理
  │     └── lock/load/write/record
  └── 13. 输出给 Agent
```

---

## 4. 出口流程（完整链路）

```
Agent 写入请求
  │
  ▼
PreToolUse Guard 拦截
  │
  ├── 6 种工具拦截：Write/Edit/MultiEdit/Execute/Task/工厂子代理
  └── classify_owned_path() 分类 API
        ├── critical 域 → 阻止写入
        ├── high 域 → 警告
        └── readonly 模式 → 完全阻止
  │
  ▼
allowed_writes 定义写入目标和策略
  │
  ├── 12 种写入路由（见 2.4）
  └── kb_policy 三策略
        ├── read-first-CRUD（先读后写）
        ├── overwrite_allowed = false（禁止覆盖）
        └── conflict_strategy = preserve-and-escalate（冲突保留并升级）
  │
  ▼
写入执行
  │
  └── Integrity re-sign
        ├── 更新 manifest.json（SHA-256 + HMAC-SHA256）
        └── 追加 integrity-audit.jsonl（审计轨迹）
```

---

## 5. Droid 编排会话

memory-core 深度集成 Factory Droid 的编排体系，覆盖了 Droid 的 9 个 Hook 事件和完整的子代理保护链。

### 5.1 Hook 事件覆盖

memory-core 通过全局 Hook 覆盖 Factory Droid 的全部 9 个生命周期事件：

| 事件 | 触发时机 | memory-core 的作用 |
|------|----------|-------------------|
| SessionStart | 会话开始或恢复 | 自动构建并注入项目上下文（context-package）|
| UserPromptSubmit | 用户提交 prompt | 校验项目状态、注入健康报告 |
| PreToolUse | Agent 调用工具前 | 拦截写入操作、保护 ownership 域、注入子代理保护策略 |
| PostToolUse | Agent 调用工具后 | 记录工具使用事件 |
| SubagentStop | 子代理任务完成 | 记录子代理执行结果 |
| PreCompact | Agent 压缩上下文前 | 可用于上下文提炼触发（v0.6+ 规划）|
| Stop | Agent 完成响应 | 记录会话结束事件 |
| Notification | Agent 发送通知 | 记录通知事件 |
| SessionEnd | 会话结束 | 记录会话生命周期 |

### 5.2 子代理保护链

当主 Agent 通过 Task 工具分派子代理（Custom Droid）时，memory-core 自动执行三层保护：

**第一层：PreToolUse Guard 拦截**
- 拦截 Task 工具调用
- 解析子代理 prompt 中引用的受保护路径
- 如果 prompt 引用了 critical 域路径 → 阻止整个 Task 分派

**第二层：Ownership Policy 自动注入**
- 读取 ownership.toml 的保护域和资源列表
- 自动生成 policy block（保护域 + 禁止指令）
- 插入到子代理 prompt 开头（幂等，不重复注入）
- 子代理在执行中遵守注入的保护策略

**第三层：弹性任务分派**
- Resilient Orchestrator 处理不同长度的子代理 prompt
- 短 prompt（< 40K 字符）→ 内联分派（直接传递）
- 长 prompt（> 40K 字符）→ 文件分派（写 instructions.md，子代理读文件执行）
- 失败自动重试（最多 2 次），重试自动切换为文件分派
- cwd 固定为 project_root，防止子代理工作目录漂移导致保护失效

### 5.3 Missions 集成

memory-core 的 Hook、Ownership 保护、AGENTS.md 规范在 Factory Missions 中自动生效：
- Mission worker 和 validator 继承项目的 memory-core 配置
- 每个 worker session 通过 SessionStart 自动获取项目上下文
- PreToolUse Guard 保护 worker 不修改受保护文件
- 子代理保护链在 worker 分派子任务时自动激活

### 5.4 上下文压缩与持久化状态追踪

Factory Droid 提供了结构化上下文压缩方案（PreCompact + anchored iterative summarization），在 Agent 长会话中自动提炼上下文。根据 Factory Research 的评估（36000+ 条消息、三种方案对比），结构化摘要的整体评分最高（3.70/5），但所有方案在**文件追踪（Artifact tracking）**这一维度上都是最弱项（最高仅 2.45/5）。

这意味着：上下文压缩可以保留推理意图和决策，但无法精确追踪哪些文件被创建/修改/检查过，也无法持久化结构化的项目知识。

**memory-core 的定位：补 Factory 上下文压缩的最弱项。**

memory-core 不做上下文压缩（这是 Factory 自身 PreCompact 机制的事），而是通过结构化的持久化记忆层，精确追踪 Factory 压缩后无法保留的状态：

- **文件状态追踪** — context-package 记录了项目所有知识来源的精确路径和状态，每次 session-start 自动刷新
- **决策记录** — memory/kb/decisions/ 以结构化方式持久化每个架构决策及其推理
- **项目知识** — memory/kb/projects/{scope}/ 的五文件（CANONICAL/STATE/PLAN/TASKS/NOW）精确记录项目真相
- **经验教训** — memory/kb/lessons/ 持久化跨会话的经验，不随上下文压缩丢失
- **变更历史** — integrity-audit.jsonl 和 events.jsonl 提供完整的审计轨迹
- **Artifact 快照** — 按 session/event 保存完整的 context-package 快照，可精确回溯任意历史时刻的项目状态

这种互补关系意味着：
- Factory 负责 Agent 会话内的上下文连续性（通过压缩保持推理链）
- memory-core 负责跨会话的状态持久化（通过结构化记忆保留精确数据）
- 两者结合，Agent 既不会丢失推理能力，也不会丢失事实状态

---

## 6. 上下文持久化策略

### 6.1 保存机制（三写）

每次 Gateway 构建完 context-package 后，持久化为三种形式：

| 形式 | 路径格式 | 说明 |
|------|----------|------|
| **snapshot** | `artifacts/memory-hook/contexts/{date}/{timestamp}-{host}-{event}.json` | 带时间戳的完整快照，保留完整历史 |
| **latest** | `artifacts/memory-hook/contexts/latest-{host}-{event}.json` | 最新一份，覆盖写入 |
| **events.jsonl** | `artifacts/memory-hook/events/{date}.jsonl` | append-only 事件日志 |

### 6.2 时间策略

- 按天分区，不删除历史
- 全局 latest 永远是最近一次（供下次 session-start 快速加载）
- 每日 latest 保留当天最后一次
- 同一时间戳冲突时自动加后缀

### 6.3 已知问题：上下文无限累积

当前按天分区但无 TTL、无自动清理、无提炼机制，长时间使用后 artifact 目录持续增长。

### 6.4 路线图规划（v0.6+）

- PreCompact 事件集成（Factory 已支持此事件，可作为提炼触发点）
- daily_session_summary 自动化（从分析工具升级为提炼流程）
- 上下文 TTL 策略（snapshot 保留天数配置）
- 历史上下文压缩（多天合并为摘要存入 kb）

---

## 7. 每日日志自动化系统（A+B+C 三层架构）

### 7.1 架构概述

> **全自动运行**：系统部署完成后完全自动运行，无需人工干预。A 层由 Factory SessionEnd Hook 自动触发，B 层由 macOS launchd 每日 23:55 定时触发，C 层由 A/B 层异常时被动触发。唯一需要手动操作的是初始部署（已完成）。

A+B+C 三层每日日志自动化系统为 memory-core 提供从 session 级实时统计到每日 LLM 总结再到全局错误捕获的完整日志链路。

| 层级 | 触发时机 | 功能 | 性能要求 | 输出文件 |
|------|----------|------|----------|----------|
| **A层** | Session 结束（Factory SessionEnd Hook） | 追加 session 统计 | <2s | `{project}/memory/log/{date}-sessions.md` |
| **B层** | 每日 23:55 定时（launchd） | LLM 分类总结 | <120s | `{project}/memory/log/{date}.md` |
| **C层** | A/B 层异常时调用 | 错误日志记录 | <100ms | `{project}/memory/log/{date}-errors.jsonl` |

### 7.2 A层：Session 实时统计

**触发机制**：Factory `SessionEnd` hook → `session_end_logger.py`

**输入**：从 Factory hook stdin payload 提取 session_id、cwd（项目根目录）、transcript_path

**输出内容**：每条记录包含 session_id 前缀、标题、模型、时长、Token 用量（input/output）、工具调用统计、用户意图（首条 user message 前 200 字符）、助手摘要（末条 assistant message 片段）

**降级策略**：
- transcript 不存在 → 记录 `transcript_missing` 到 C 层，静默退出
- 超时 2s → 记录 `hook_timeout` 到 C 层，静默退出
- 任何异常 → 记录对应错误类型到 C 层，不阻塞 hook 链

**实现**：`memory_core/tools/session_end_logger.py`

### 7.3 B层：每日 LLM 总结

**触发机制**：launchd 每日 23:55 → `daily_summary_generator.py --today --all-projects`

**输入**：A层 sessions.md 的 session 列表 + 对应 transcript jsonl

**输出内容**：统计概览、按主题分类的工作总结（LLM 生成）、经验教训（3-5 条）

**降级策略**：
- LLM 调用失败 → 降级为纯统计报告（无分类）
- API key 缺失 / 请求超时 → 重试或降级
- 无 session 数据 → 跳过该项目
- 降级失败 → 记录错误到 C 层

**兜底策略**：自动补前 3 天缺失日志（应对关机/断网场景）

**实现**：`memory_core/tools/daily_summary_generator.py`

### 7.4 C层：全局错误日志

**设计约束**：
- **静默原则**：C 层写入失败不触发二次异常，函数返回 False
- **轻量原则**：错误写入 <100ms，不阻塞主流程
- **隔离原则**：按项目独立记录，互不污染
- **不改变现有行为**：A/B 层正常流程不受影响

**JSON Lines 格式**：每行一个 JSON 对象

```json
{"ts":"2026-05-28T14:30:00+08:00","type":"transcript_missing","script":"session_end_logger","project":"/path/to/project","ctx":{"session_id":"abc12345"},"msg":"transcript not found"}
```

**字段规范**：
- `ts`：ISO 8601 时间戳
- `type`：错误类型枚举（8 种）
- `script`：来源脚本名
- `project`：项目根路径
- `ctx`：上下文键值对
- `msg`：错误消息（截断 500 字符，API key 自动脱敏为 `sk-...****`）

**错误类型枚举**：

| type | 来源 | 严重度 |
|------|------|--------|
| transcript_missing | A层 | low |
| hook_timeout | A层 | medium |
| json_parse_error | A层 | low |
| directory_creation_failed | A/B/C | medium |
| file_write_failed | A/B | medium |
| llm_api_error | B层 | high |
| llm_timeout | B层 | high |
| settings_read_failed | B层 | low |

**实现**：`memory_core/tools/error_logger.py`

### 7.5 文件布局

```
{project}/memory/log/
├── 2026-05-28-sessions.md       # A层输出
├── 2026-05-28.md                # B层输出
└── 2026-05-28-errors.jsonl      # C层输出（新）
```

### 7.6 配置与部署

| 组件 | 路径 | 说明 |
|------|------|------|
| A层脚本 | `memory_core/tools/session_end_logger.py` | Hook 入口 |
| B层脚本 | `memory_core/tools/daily_summary_generator.py` | 定时入口 |
| C层模块 | `memory_core/tools/error_logger.py` | 错误日志模块 |
| SessionEnd hook | `~/.factory/settings.json` | Factory 启动快照 |
| Hook 备份 | `~/.factory/settings.local.json` | Factory UI 不覆盖 |
| 定时任务 | `~/Library/LaunchAgents/com.memory.daily-summary.plist` | 23:55 执行 |

### 7.7 与 PRD 其他部分的衔接

- 与 **第 2.3 节入口路由** 衔接：日志文件 `memory/log/{date}.md` 作为 `fact` 路由的知识来源
- 与 **第 5 节 Droid 编排** 衔接：SessionEnd 事件触发 A 层日志统计
- 与 **第 6 节上下文持久化** 衔接：每日日志是对会话级快照的跨天总结

---

## 8. 接入模型

### 8.1 全局接入（一次性）

用户安装 memory-core 并注册全局 Hook：

**步骤 1：安装**
```bash
pip install memory-core
```

**步骤 2：注册全局 Hook（选择一个平台）**

| 平台 | 命令 | 生成文件 |
|------|------|----------|
| Factory | `memory-factory-hooks install --storage-root ~/.memory-core` | `~/.factory/settings.json` + `~/.factory/bin/memory-hook` |
| Claude | `memory-claude-hooks install --storage-root ~/.memory-core` | `~/.claude/hooks.json` + wrapper 脚本 |
| Codex | `memory-codex-hooks install --storage-root ~/.memory-core` | Codex 配置 + wrapper 脚本 |

**步骤 3：全局运行时目录自动创建**
```
~/.memory-core/
├── keys/                          # HMAC 密钥
├── project-lifecycle/             # 项目注册、path-index、events.jsonl
└── quarantine/                    # 隔离区
```

**事件支持：**
- Factory：9 种事件（含 PreToolUse、PostToolUse、SubagentStop、PreCompact、SessionEnd）
- Codex/Claude：4 种事件

**全局 Hook 的 auto-init 机制：**
当检测到项目缺少 `memory/system/` 时，自动执行 `memory-init --target <project>`。

### 7.2 单项目接入（每个项目一次）

在每个项目根目录执行 `memory-init --target /path/to/project`，生成以下目录结构：

**system/（配置与状态）**
```
memory/system/
├── adapter.toml           # 适配器配置（版本、策略、路由）
├── ownership.toml         # 所有权声明（保护域定义）
├── memory.lock            # 版本锁定
├── migrations.log         # 迁移日志
├── manifest.json          # 完整性签名（自动生成）
├── integrity-audit.jsonl  # 审计轨迹
├── errors.log             # 错误日志
└── health-report.json     # 健康报告（自动生成）
```

**kb/（知识库）**
```
memory/kb/
├── INDEX.md                       # 知识库索引
├── global/                        # 全局规范
│   ├── truth-model.md
│   ├── hook-contract.md
│   ├── policy-pack.md
│   └── projects-spec.md
├── projects/{scope}/              # 项目知识
│   ├── CANONICAL.md               # 项目真相
│   ├── STATE.md                   # 执行状态
│   ├── PLAN.md                    # 计划
│   ├── TASKS.md                   # 任务清单
│   └── {scope}.md                 # 项目主文件
├── decisions/                     # 决策记录
└── lessons/                       # 经验教训
```

**docs/（文档）** / **log/（日志，append-only）**

**project-map/（合法性地图）**
```
memory/project-map/
├── INDEX.md
├── legal-core-map.md
├── ingestion-registry-map.md
└── ...  # 只有 active-legal 的条目才被 Gateway 承认
```

**其他**
- `INDEX.md` —— 工作区入口路由
- `NOW.md` —— 当前状态（项目根，唯一允许覆写的入口文件）
- `artifacts/memory-hook/` —— 运行时产物（Gateway 自动生成）

### 7.3 多项目运行时

每次 Agent 会话，Gateway 自动识别当前项目：

```
~/.memory-core/
├── project-lifecycle/
│   ├── path-index.json           # 路径索引，记录所有接入项目
│   ├── projects/
│   │   └── {project_id}.json     # 每个项目的生命周期记录
│   └── events.jsonl              # 全局事件日志
```

- project_id 通过 git_remote 或 local_path 唯一标识
- 项目路径消失时保留记忆（`preserve-memory-on-missing-path` 策略）

---

## 9. 协议支撑层

### 9.1 Adapter 多平台适配

- **新平台接入 = 写 adapter，不改核心**
- adapter 通过 `MEMORY_HOOK_ADAPTER` 环境变量选择
- 运行时通过 `globals().update()` 注入 47 个配置 key

### 9.2 Knowledge Base 分层

| 层级 | 路径 | 特性 |
|------|------|------|
| **Canonical 层** | `memory/kb/global/` + `memory/kb/projects/{scope}/` | 只读，项目真相 |
| **KB 层** | `memory/kb/decisions/`, `memory/kb/lessons/` | 追加优先 |
| **Artifacts 层** | `artifacts/` | 可写，运行时产物 |

### 9.3 五文件协议

每个项目 scope 下生成的五个声明式真相文件：

| 文件 | 用途 | 可覆写 |
|------|------|--------|
| **CANONICAL.md** | 项目真相（架构、技术栈、关键模块） | 否 |
| **STATE.md** | 执行状态 | 否 |
| **PLAN.md** | 计划 | 否 |
| **TASKS.md** | 任务清单 | 否 |
| **NOW.md** | 当前状态（项目根目录） | **是（唯一允许）** |

### 9.4 Ownership 保护体系

**ProtectionLevel 枚举：**
- `critical` —— 禁止写入
- `high` —— 警告
- `medium` —— 记录
- `low` —— 放行

**classify_owned_path() 分类 API：** 自动识别路径属于哪个 ownership 域

**DEFAULT_OWNERSHIP_DOMAINS：**
- `memory_docs` —— 受保护文档域
- `memory_kb` —— 受保护知识库域
- `memory_system` —— 受保护系统状态域
- `project_map` —— 受保护项目地图域
- `source_repo_docs` —— 源仓库文档域（只读）
- `source_repo_factory` —— 源仓库 Factory 配置域（只读）

**ownership_cli 四命令：**
- `memory-ownership show` —— 显示所有权配置
- `memory-ownership validate` —— 验证配置有效性
- `memory-ownership plan-update` —— 规划更新
- `memory-ownership apply-update` —— 应用更新

### 9.5 Integrity 保护体系

- **HMAC-SHA256 签名**：`manifest.json` 包含所有受保护文件的 SHA-256 + HMAC-SHA256
- **审计轨迹**：`integrity-audit.jsonl` 记录所有变更历史
- **re-sign CLI**：`memory-integrity-resign --reason "xxx" --token xxx`（需 reason + token/force）
- **key 管理**：存储在 `~/.memory-core/keys/`
- **key 丢失**：warning + 结构化字典返回，引导重新生成

### 9.6 Policy Pack

六策略 + 三种冲突解决策略：

| 策略 | 值 | 说明 |
|------|-----|------|
| `legality_source` | `active-legal-map-only` | 只承认 active-legal 的 project-map 条目 |
| `registration_commit` | `required-after-absorption-complete` | 吸收完成后必须提交注册 |
| `truth_basis_policy` | `source-authority-evidence-conflict` | 真相四要素策略 |
| `kb_write_mode` | `read-first-CRUD` | 知识库写入模式 |
| `kb_overwrite_allowed` | `false` | 禁止覆盖 |
| `conflict_strategy` | `preserve-and-escalate` | 冲突策略 |

**冲突策略选项：**
- `fail-fast` —— 快速失败
- `preserve-and-escalate` —— 保留并升级
- `prefer-strict` —— 优先严格模式

### 9.7 Truth Basis 四要素

每个正式真相条目必须同时具备：

| 要素 | 说明 |
|------|------|
| **source_refs** | 来源引用 —— 信息最初来自哪里 |
| **authority_refs** | 权威引用 —— 谁确认了这条信息 |
| **evidence_refs** | 证据引用 —— 支持这条信息的证据 |
| **conflict_status** | 冲突状态 —— `resolved` 或 `unresolved` |

---

## 10. 同步管道

**单向同步铁律：代码只推 GitLab，GitHub 和 ShowDoc 由 CI 同步**

```
GitLab（主仓库，唯一写入源）
  │
  ├── CI Pipeline
  │     ├── test + health-check 门禁
  │     └── 合并到 main 后触发 sync
  │
  ├──→ GitHub（只读镜像）
  │     └── GitLab CI 的 sync-to-github job 推送
  │
  └──→ ShowDoc（文档镜像）
        ├── 增量同步（SHA256 manifest）
        ├── 幂等 upsert（按 page_title）
        ├── 安全子集验证（19 项 Markdown 兼容）
        ├── 单文件失败容忍
        └── CI 凭证管理
```

**禁止直推 GitHub**：任何 `git push origin main` 到 GitHub 都是违规，会破坏单源真相。

---

## 11. 用户画像与用例

### 11.1 四类用户

| 用户画像 | 核心需求 | 主要场景 |
|----------|----------|----------|
| **独立开发者** | 零配置获得 Agent 跨会话记忆 | 个人项目，自动记忆 |
| **技术团队 Lead** | 统一协议 + 保护机制 + CI 门禁 | 团队规范，知识管理 |
| **平台集成者** | Adapter SDK + 稳定 API | 自建平台接入 memory 协议 |
| **开源维护者** | 自动上下文注入 | 开源项目贡献者 onboarding |

### 11.2 核心用例

**用例 1：独立开发者首次使用**
```
安装 → memory-init → 开启 Agent 对话 → 自动获得上下文
```
- 目标：5 分钟内完成
- 体验：零额外操作

**用例 2：技术团队统一规范**
```
评估 → 试点项目 → 定义 ownership → CI 集成 → 推广
```
- 目标：团队所有 Agent 使用同一套上下文
- 体验：新成员 onboarding 自动获得项目知识

**用例 3：平台集成**
```
阅读 adapter 文档 → 实现 hook 归一化 → 配置 adapter.toml → 部署
```
- 目标：自有平台接入 memory 协议
- 体验：稳定接口，不随内部实现变更

---

## 12. 产品体验

### 12.1 首次体验

**目标：5 分钟内从安装到 Agent 获得上下文**

| 步骤 | 操作 | 耗时 |
|------|------|------|
| 1 | `pip install memory-core` | < 1 分钟 |
| 2 | `memory-init --target /path/to/project` | < 5 秒 |
| 3 | `memory-validate` 确认 | < 2 秒 |
| 4 | `memory-factory-hooks install`（可选） | < 10 秒 |
| 5 | 开启 Agent 对话 | 自动 |

### 12.2 日常使用

**目标：零感知，Agent 通过 hook 自动获取上下文**

- 用户不需要手动操作 memory
- Agent 自动获得完整项目上下文
- 受保护文件自动拦截

### 12.3 错误体验

| 错误场景 | 诊断 | 修复指引 |
|----------|------|----------|
| Manifest 过期 | `⚠️ Integrity degraded` | `memory-integrity-resign --reason "xxx"` |
| 所有权冲突 | `🚫 Blocked: xxx belongs to critical domain` | 该文件属于只读域，不可修改 |
| 版本不兼容 | `❌ Schema mismatch` | `memory-migrate --from x --to y` |
| HMAC key 缺失 | `⚠️ Warning: HMAC key not configured` | 配置 key 或使用 `--force` |

### 12.4 升级体验

**目标：自动备份 + 可回滚 + 零停机**

```
pip install --upgrade → 自动检测版本差异 → memory-migrate
                              ↓
                    自动备份到 backups/
                              ↓
                    memory-validate 确认 → 失败则 --rollback
```

---

## 13. 内置工具全景（41 个）

所有工具位于 `memory_core/tools/` 目录。

### 平台 Hook 安装（3 个）

| 脚本 | 用途 |
|------|------|
| `factory_global_hooks.py` | Factory/Droid 全局 hook 安装 |
| `claude_global_hooks.py` | Claude Code 全局 hook 安装 |
| `codex_global_hooks.py` | Codex 全局 hook 安装 |

### 项目初始化/迁移/验证（6 个）

| 脚本 | 用途 |
|------|------|
| `init_project_memory.py` | 项目记忆初始化（create/adopt/update/repair） |
| `migrate_project_memory.py` | 旧版记忆迁移 |
| `verify_consumer.py` | 消费者项目自检 |
| `validate_project_memory.py` | 项目完整性校验 |
| `validate_memory_system.py` | 记忆系统校验 |
| `project_probe.py` | 项目元数据自动检测（语言/框架/数据库） |

### Hook 运行时/网关（7 个）

| 脚本 | 用途 |
|------|------|
| `memory_hook_gateway.py` | Hook 事件网关（核心调度） |
| `memory_hook_core.py` | Hook 核心逻辑 |
| `memory_hook_impls.py` | Hook 事件处理实现 |
| `memory_hook_config.py` | Hook 配置管理 |
| `memory_hook_interfaces.py` | Hook 接口定义 |
| `memory_hook_schema.py` | Hook Schema 定义 |
| `pretooluse_guard.py` | PreToolUse 安全守卫 |

### 完整性/安全（6 个）

| 脚本 | 用途 |
|------|------|
| `memory_integrity_resign.py` | 完整性重签名 |
| `memory_integrity_verify.py` | 完整性校验 |
| `memory_hook_integrity_manifest.py` | 完整性清单 |
| `memory_hook_integrity_keys.py` | 完整性密钥 |
| `ownership_cli.py` | 所有权管理 CLI |
| `ownership.py` | 所有权模型（核心） |

### 运维/诊断（11 个）

| 脚本 | 用途 |
|------|------|
| `daily_session_summary.py` | 每日会话汇总报告 |
| `session_end_logger.py` | A 层 Session 实时统计（Factory SessionEnd Hook 自动触发） |
| `daily_summary_generator.py` | B 层 每日 LLM 总结（launchd 23:55 定时触发） |
| `error_logger.py` | C 层全局错误日志（A/B 层异常时被动调用，JSON Lines 格式） |
| `memory_health_report.py` | 记忆健康报告 |
| `consistency_check.py` | 一致性检查 |
| `audit_project_layout.py` | 项目布局审计 |
| `business_policy_checks.py` | 业务策略检查 |
| `version_sync.py` | 版本同步（跨项目） |
| `project_lifecycle.py` | 项目生命周期跟踪 |
| `denied_project_roots.py` | 禁止初始化的根目录 |

### 辅助工具（8 个）

| 脚本 | 用途 |
|------|------|
| `adapter_toml_schema.py` | adapter.toml Schema 定义 |
| `template_sync.py` | 模板同步 |
| `hook_upgrade.py` | Hook 版本升级 |
| `cmux_hook_state.py` | cmux hook 状态管理 |
| `codex_session_analyzer.py` | Codex 会话分析 |
| `apply_residue_plan.py` | 残留计划清理 |
| `evidence_ref_validator.py` | 证据引用校验 |
| `index_schema.py` | 索引 Schema 定义 |

---

## 14. 差异化分析

| 维度 | memory-core | CLAUDE.md 手写 | Cursor Memory | Copilot Workspace |
|------|-------------|----------------|---------------|-------------------|
| **协议标准化** | ✅ 标准 `memory/` 协议 | ❌ 自由格式 | ⚠️ 部分结构化 | ⚠️ 部分结构化 |
| **一个入口一个出口** | ✅ 统一契约设计 | ❌ 无统一接口 | ❌ 无 | ❌ 无 |
| **开源自主** | ✅ MIT 许可 | N/A | ❌ 闭源 | ❌ 闭源 |
| **跨平台** | ✅ Codex/Claude/Factory | ❌ 仅 Claude | ❌ 仅 Cursor | ❌ 仅 GitHub |
| **完整性保护** | ✅ HMAC + Ownership | ❌ 无 | ❌ 无 | ❌ 无 |
| **41 个内置工具全生命周期** | ✅ 完整工具链 | ❌ 无 | ❌ 无 | ❌ 无 |

**核心差异化：**
1. **协议思维 vs 工具思维** —— memory-core 是协议，不是工具集
2. **契约设计** —— 一个入口一个出口的标准化契约
3. **完整性保护** —— HMAC + Ownership 业内独有
4. **开源自主** —— MIT 许可，完全本地
5. **跨平台** —— 三平台适配
6. **全生命周期** —— 41 个内置工具覆盖完整生命周期

---

## 15. 成功指标

| 指标 | 目标 | 衡量方式 |
|------|------|----------|
| 安装到首次使用转化率 | > 80% | `memory-init` 后 `memory-validate` 通过比例 |
| 日常使用零感知率 | > 95% | hook 日志中无用户干预记录的比例 |
| 保护机制生效率 | 100% | integrity verify 通过率；Guard 拦截成功率 |
| 升级成功率 | > 99% | capability-check 通过率 |
| 首次初始化时间 | < 5 秒 | `time memory-init` 实测 |

---

## 16. 路线图

| 版本 | 里程碑 | 关键特性 |
|------|--------|----------|
| **v0.5.0** | 当前 | 两层架构 + 五文件恢复 + 三平台支持 |
| **v0.6.0** | 能力注册表 | CAPABILITY_REGISTRY + 上下文生命周期管理（TTL/提炼/压缩）+ Hook 协议版本化 + **A+B+C 每日日志系统（已实现）** |
| **v0.7.0** | 代码质量 | 死代码清理 + god module 拆分 + 文档补全 + API 稳定化 |
| **v1.0** | 稳定生态 | 稳定 API + 插件化 adapter 市场 + 多语言 SDK（TypeScript） |

---

## 17. 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| AI 平台变更 hook 协议 | 中 | 高 | adapter 层隔离；平台变更只需更新 adapter |
| HMAC key 管理复杂性 | 中 | 中 | 简化流程 + rotation 指南 |
| 上下文无限累积 | 高 | 中 | v0.6+ 规划生命周期管理 |
| 多 Agent 并发写入 | 低 | 中 | ownership 域保护 |
| 竞品推出类似方案 | 低 | 中 | 先发优势 + 开源社区 + 1612 个测试用例质量壁垒 |

---

## 18. 开放问题

| # | 问题 | 状态 | 影响版本 |
|---|------|------|----------|
| 1 | 上下文 TTL 和提炼的具体策略 | 规划中 | v0.6 |
| 2 | 多 Agent 并发写入是否需要更精细的锁机制 | 待定 | v1.0+ |
| 3 | 是否提供 Web UI | 待定 | v1.0+ |
| 4 | 多语言 SDK（TypeScript）优先级 | 待定 | v1.0 |
| 5 | CAPABILITY_REGISTRY 的具体设计 | 规划中 | v0.6 |
| 6 | **Droid 编排会话产出物持久化**：当前 memory-core 在编排任务执行时缺少自动捕获和持久化每次 worker session 产出物的机制。需要设计：SubagentStop 事件触发时自动提取子代理产出物（代码变更、变更文件清单、commit diff 摘要、知识更新），并持久化到 memory/ 结构中。这是 v0.6+ 需要解决的核心问题，涉及 Factory Hook 的 `transcript_path` 利用、产出物自动提炼、跨 session 状态追踪。 | 规划中 | v0.6+ |

---

*文档结束*
