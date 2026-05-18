---
type: "[DOC:DESIGN]"
title: "Memory 模块总体架构"
shortname: DES-001
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-05-14
source: code-analysis
confidence: medium
tags: [architecture,overview]
related: [DES-002, DES-003, DES-004]
---

> 文档编号：DES-001 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-05-14 (v0.4.0 Beta)。如需精确接口签名，请参考源码和 ShowDoc Python API 文档。

# Memory 模块架构设计文档

> 创建日期：2026-04-26
> 维护人：D1（文档整理员）
> 状态：可评审

---

## 1. 仓库概览

`memory` 是一个标准记忆模块（`memory-core`），为多个消费者项目提供统一的 memory core 能力。模块通过 `pyproject.toml` 声明为独立 Python 包（`memory-core==0.4.0`），无第三方依赖，仅依赖 Python ≥3.9 标准库。

核心设计原则：

- **一个正式入口**：统一 gateway（`memory_hook_gateway.py`）
- **一个正式出口合同**：统一 route/write contract
- **项目隔离**：不同项目只做 adapter 适配，不改入口/出口协议
- **模块中立**：模块层禁止内建任何单项目默认真相（M3 已完成去耦）

---

## 2. 仓库目录结构

### 2.1 顶层结构

```
memory/                          # 仓库根
├── .git/
├── .github/                     # CI/CD（release-and-dispatch.yml）
├── .pytest_cache/
├── pyproject.toml               # 包定义（memory-core==0.4.0）
├── README.md                    # 模块说明 + 迁移记录（M1/M2/M3）
├── tests/                       # 13 个测试文件
└── memory_core/                   # 唯一总控工作区
    ├── INDEX.md                 # 工作区入口（路由系统 + 写入协议）
    ├── NOW.md                   # 当前状态
    ├── tools/                   # Python 代码层
    ├── memory/                  # 知识库 + 文档
    ├── project-map/             # 项目地图（legal-core + ingestion-registry）
    ├── projects/                # 项目产物
    └── artifacts/               # 运行时产物（gateway 输出）
```

### 2.2 `memory_core/tools/` — Python 代码层

```
memory_core/tools/
├── memory_hook_interfaces.py          # 242 行 — 接口定义（IF-1 ~ IF-4）
├── memory_hook_impls.py               # 1040 行 — 默认实现
├── memory_hook_core.py                # 271 行 — 核心组装逻辑
├── memory_hook_gateway.py             # 981 行 — 统一入口 / 编排
├── cmux_hook_state.py                 # 225 行 — hook 状态管理
├── memory_hook_provider_rollback.py   # 60 行 — 回滚演练
├── validate_memory_system.py          # 12 行 — 验证桩
└── memory_hook_adapters/              # 适配层
    ├── neutral_policy.py              # 22 行 — 宿主中性基类
    ├── workbot_policy.py              # 82 行 — workbot 业务策略 (已归档至 archive/legacy-workbot/)
    ├── workbot_runtime_profile.py     # 267 行 — workbot 运行时配置 (已归档至 archive/legacy-workbot/)
    └── docs/
        └── workbot-cli-tools.md       # adapter 运行文档 (已归档)
```

### 2.3 `memory_core/memory/` — 知识库 + 文档

```
memory_core/memory/
├── inbox.md                         # 临时任务
├── docs/
│   ├── INDEX.md                     # 文档索引（MEM-DOCS-001）
│   ├── 记忆系统全景文档.md
│   ├── M7-independent-repo-cutover-plan.md
│   └── research/projects/AEdu/INDEX.md
└── kb/
    ├── INDEX.md                     # 知识库索引
    ├── decisions/                   # 决策记录
    ├── lessons/                     # 经验教训
    ├── projects/                    # 项目真相
    │   └── workbot.md
    └── global/                      # 跨项目规则
        ├── INDEX.md
        ├── memory-hook-policy-pack.json
        ├── workbot-hook-contract.md (已归档)
        ├── workbot-memory-routing.md (已归档)
        ├── workbot-memory-system.md (已归档)
        ├── workbot-policy-pack.json (已归档)
        ├── workbot-policy-pack.md (已归档)
        ├── workbot-project-map-governance.md (已归档)
        └── workbot-truth-model.md (已归档)
```

---

## 3. 模块角色说明

### 3.1 接口层（interfaces）

**文件**：`memory_core/tools/memory_hook_interfaces.py` — 242 行

定义 4 个核心接口族 + 1 个业务策略接口：

| 接口编号 | 接口名 | 行数 | 职责 |
|----------|--------|------|------|
| IF-1 | `HostDelegate` | L23-L51 | 将 hook 事件委派给宿主运行时（Codex/Claude） |
| IF-2 | `PolicyRegistry` | L58-L99 | 策略查找、验证、冲突解决 |
| IF-3 | `RouteTargetPolicy` / `WriteTargetPolicy` | L106-L129 | 路由目标解析 / 写入目标解析 |
| IF-3.5 | `GatewayBusinessPolicy` | L132-L211 | 宿主/业务策略（项目范围判定、canonical 管理、truth basis 验证） |
| IF-4 | `ArtifactSink` / `ErrorSink` | L218-L242 | 产物输出 / 错误日志 |

关键方法摘要：

- `HostDelegate.can_handle()` — 判断当前环境是否可处理
- `HostDelegate.execute(event, raw_payload, payload)` — 执行委派
- `HostDelegate.noop_response()` — M2 新增：宿主自定义 bypass 输出格式
- `PolicyRegistry.get_policy_pack(scope)` — 获取策略包
- `PolicyRegistry.resolve_conflict(key, values, strategy)` — 冲突解决
- `GatewayBusinessPolicy.determine_project_scope(cwd)` — 从 cwd 解析项目范围
- `GatewayBusinessPolicy.truth_basis_for_scope(scope)` — 返回 truth basis 四要素
- `ArtifactSink.write(package)` — 写入 context package 为 JSON 产物

### 3.2 默认实现层（impls）

**文件**：`memory_core/tools/memory_hook_impls.py` — 1040 行

实现 interfaces 中定义的所有接口：

| 类名 | 行数范围 | 实现接口 | 职责 |
|------|----------|----------|------|
| `CodexDelegate` | L49-L87 | `HostDelegate` | Codex 宿主委派：调用 `cmux codex-hook` |
| `ClaudeDelegate` | L89-L182 | `HostDelegate` | Claude 宿主委派：调用 `cmux claude-hook`，含 state file 注入和 canonicalization |
| `PolicyRegistryImpl` | L188-L357 | `PolicyRegistry` | 策略注册表：支持 policy-pack JSON 动态加载、scope 继承、冲突策略 |
| `RouteTargetPolicyImpl` | L363-L389 | `RouteTargetPolicy` | 路由目标映射（fact/global-rule/source-material/project-runtime 等） |
| `WriteTargetPolicyImpl` | L392-L417 | `WriteTargetPolicy` | 写入目标映射（kb/global/project/decision/lesson/docs 等） |
| `GatewayBusinessPolicyConfig` | L425-L467 | 配置 dataclass | 承载所有 gateway 业务策略配置参数 |
| `GatewayBusinessPolicyImpl` | L468-L977 | `GatewayBusinessPolicy` | 业务策略核心实现：project-map 验证、truth basis 校验、governance frozen tuple 检查、event contract 对齐 |
| `ArtifactSinkImpl` | L984-L1022 | `ArtifactSink` | 产物写入：snapshot + latest + event log |
| `ErrorSinkImpl` | L1025-L1040 | `ErrorSink` | 错误日志写入 |

`GatewayBusinessPolicyImpl` 是该文件最大的类（约 509 行），包含：

- Truth basis 四要素校验（source/authority/evidence/conflict）
- Project-map 合法性验证（active-legal-map-only 合同）
- Governance frozen tuple 检查（AEdu 项目专用）
- Event contract 对齐验证（upstream/formal/downstream 一致性）

### 3.3 核心组装层（core）

**文件**：`memory_core/tools/memory_hook_core.py` — 271 行

提供两个核心函数：

| 函数名 | 行数 | 职责 |
|--------|------|------|
| `registration_phase_from_policy_pack()` | L14-L27 | 从 policy pack 解析 registration phase |
| `evaluate_registration_commit_gate()` | L30-L66 | 评估注册提交门禁（enforced/awaiting/passed/failed） |
| `build_context_package_core()` | L69-L271 | **M5 核心组装**：构建完整的 context package |

`build_context_package_core()` 是 context package 的最终组装函数，输出结构：

```python
{
    "schema_version": "wb-hook-v2",
    "generated_at": "...",
    "host": "...",
    "event": "...",
    "status": "ok" | "degraded",
    "system_context": { ... },
    "project_context": { ... },
    "task_context": { ... },
    "allowed_reads": [...],
    "allowed_writes": { ... },
    "evidence_refs": [...],
}
```

### 3.4 Gateway 编排层（gateway）

**文件**：`memory_core/tools/memory_hook_gateway.py` — 981 行

统一入口，负责：

1. **Adapter 加载**（L79-L91）：通过 `MEMORY_HOOK_ADAPTER` 环境变量选择 adapter，动态加载 runtime profile
2. **Facade 模式**（L96-L270）：IF-5 接口适配，封装所有策略/策略注册表/路由/写入/委托的单例获取
3. **Provider 解析**（L155-L173）：支持 `external-core`（可选）和 `legacy`（默认）两种 core builder
4. **Context 组装**（L739-L822）：`build_context_package()` — 串联 business policy → core builder → compaction
5. **Artifact 写入**（L845-L868）：`write_artifacts()` — 通过 sink 写入，含 fallback
6. **Delegate 执行**（L908-L977）：`main()` — CLI 入口，处理 `--host`、`--event`、`--no-delegate`

关键函数调用链：

```
main()
  → parse_args()
  → read_payload()
  → discover_cwd()
  → should_noop_for_external_context()  # 外部上下文跳过
  → build_context_package()
      → determine_project_scope()
      → _get_gateway_business_policy()
      → _resolve_core_builder()
      → provider_builder(**core_kwargs)  # memory_hook_core.build_context_package_core
      → _apply_artifact_compaction()
  → write_artifacts()
  → delegate_codex() / delegate_claude()
```

### 3.5 适配层（adapters）

**目录**：`memory_core/tools/memory_hook_adapters/`

| 文件 | 行数 | 职责 |
|------|------|------|
| `neutral_policy.py` | 22 | 宿主中性基类，继承 `GatewayBusinessPolicyImpl` |
| `workbot_policy.py` | 82 | Workbot 业务策略：注入 `ADAPTER_POLICIES`（legality_source/registration_commit） |
| `workbot_runtime_profile.py` | 267 | Workbot 运行时配置：返回 30+ 配置项（project-map 路径、canonical、scope hints 等） |

`build_workbot_runtime_profile()` 返回的配置包括：

- `PROJECT_MAP_ROOT`、`PROJECT_MAP_FILES`、`PROJECT_MAP_GOVERNANCE`
- `TRUTH_MODEL`、`GLOBAL_CANONICAL`、`REQUIRED_CANONICAL`
- `PROJECT_CANONICAL`（workbot/AEdu/platform-capabilities 三项目）
- `PROJECT_RUNTIME_ROOT`、`PROJECT_DOC_REFS`、`PROJECT_LESSON_REFS`
- `GOVERNANCE_FROZEN_TUPLE_FILES`、`EVENT_CONTRACT_FILES`
- `SCOPE_MATCH_HINTS`（项目范围匹配提示路径）
- `ARTIFACT_COMPACTION`（artifact 裁剪策略）
- `POLICY_ALLOWED_SCOPES`、`POLICY_SCOPE_INHERITS`

### 3.6 辅助模块

| 文件 | 行数 | 职责 |
|------|------|------|
| `cmux_hook_state.py` | 225 | Hook 状态文件管理：lock、load、write、record_hook_event |
| `memory_hook_provider_rollback.py` | 60 | 回滚演练：验证 legacy provider 可用性 |
| `validate_memory_system.py` | 12 | 验证桩（当前为空操作） |

---

## 4. 模块依赖关系图

```
                    ┌─────────────────────────┐
                    │  memory_hook_gateway.py │  ← 统一入口（981 行）
                    │      (gateway 编排层)    │
                    └────────┬────────────────┘
                             │
              ┌──────────────┼──────────────────┐
              │              │                   │
              ▼              ▼                   ▼
    ┌─────────────────┐ ┌──────────────┐ ┌──────────────────┐
    │memory_hook_core │ │memory_hook_  │ │memory_hook_      │
    │    .py          │ │  impls.py    │ │  interfaces.py   │
    │  (核心组装 271行) │ │ (默认实现1040行)│ │ (接口定义 242行) │
    └─────────────────┘ └──────┬───────┘ └────────▲─────────┘
                               │                   │
                               │ implements        │ defines
                               │                   │
                               ▼                   │
                     ┌─────────────────┐           │
                     │ memory_hook_    │───────────┘
                     │  adapters/      │
                     │  (适配层)        │
                     │                 │
                     │ neutral_policy  │──继承──→ GatewayBusinessPolicyImpl
                     │ workbot_policy  │──继承──→ NeutralGatewayBusinessPolicy
                     │ workbot_runtime │──返回──→ 配置字典（注入 gateway globals）
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │cmux_hook_state  │ ← hook 状态文件管理
                     │  .py (225 行)   │
                     └─────────────────┘
```

具体 import 关系：

- `memory_hook_gateway.py` import → `memory_hook_interfaces`（IF-1~IF-4）、`memory_hook_impls`（实现类）、`memory_hook_core`（core builder）、`cmux_hook_state`（状态管理）、`memory_hook_adapters.*`（adapter 配置）
- `memory_hook_impls.py` import → `memory_hook_interfaces`（接口基类）
- `memory_hook_core.py` import → 无模块依赖（纯函数，通过参数注入所有依赖）
- `neutral_policy.py` import → `memory_hook_impls`（GatewayBusinessPolicyConfig/GatewayBusinessPolicyImpl）
- `workbot_policy.py` import → `neutral_policy`（NeutralGatewayBusinessPolicy）、`memory_hook_impls`（GatewayBusinessPolicyConfig）
- `workbot_runtime_profile.py` import → `workbot_policy`（WorkbotGatewayBusinessPolicy）
- `memory_hook_provider_rollback.py` import → `memory_hook_gateway`（调用 gateway 内部函数）

---

## 5. 数据流概览

### 5.1 完整调用路径

```
消费者（Codex/Claude）
    │
    │  1. 触发 hook（session-start / prompt-submit / stop / notification）
    │     通过 stdin 传入 raw_payload (JSON)
    ▼
┌─────────────────────────────────────────────────┐
│  memory_hook_gateway.py: main()                  │
│  ┌─────────────────────────────────────────────┐│
│  │ 1. parse_args()      -- 解析 --host --event ││
│  │ 2. read_payload()    -- 解析 stdin JSON     ││
│  │ 3. discover_cwd()    -- 确定工作目录        ││
│  └──────────────┬──────────────────────────────┘│
│                 ▼                                │
│  ┌─────────────────────────────────────────────┐│
│  │ 4. should_noop_for_external_context()       ││
│  │    → 外部上下文返回 noop_response()         ││
│  └──────────────┬──────────────────────────────┘│
│                 ▼                                │
│  ┌─────────────────────────────────────────────┐│
│  │ 5. build_context_package(host, event,       ││
│  │         payload)                            ││
│  │   ├─ determine_project_scope(cwd)           ││
│  │   ├─ _get_gateway_business_policy()         ││
│  │   │   └─ GatewayBusinessPolicyConfig        ││
│  │   │       + WorkbotGatewayBusinessPolicy    ││
│  │   ├─ _resolve_core_builder(provider)        ││
│  │   │   └─ external-core 或 legacy            ││
│  │   ├─ provider_builder(**kwargs)             ││
│  │   │   └─ build_context_package_core()       ││
│  │   │       (memory_hook_core.py)             ││
│  │   └─ _apply_artifact_compaction()           ││
│  └──────────────┬──────────────────────────────┘│
│                 ▼                                │
│  ┌─────────────────────────────────────────────┐│
│  │ 6. write_artifacts(package)                 ││
│  │   └─ ArtifactSinkImpl.write()               ││
│  │       ├─ snapshot JSON                      ││
│  │       ├─ latest JSON                        ││
│  │       └─ events.jsonl (append)              ││
│  └──────────────┬──────────────────────────────┘│
│                 ▼                                │
│  ┌─────────────────────────────────────────────┐│
│  │ 7. delegate_codex() / delegate_claude()     ││
│  │   ├─ HostDelegate.execute()                 ││
│  │   │   └─ cmux codex-hook / claude-hook      ││
│  │   └─ noop_response() (fallback)             ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
    │
    ▼
产物输出：
  - memory_core/artifacts/memory-hook/contexts/latest-{host}-{event}.json
  - memory_core/artifacts/memory-hook/events.jsonl
  - memory_core/memory/system/errors.log (错误时)
```

### 5.2 Context Package 结构

```json
{
  "schema_version": "wb-hook-v2",
  "generated_at": "2026-04-26T...",
  "host": "codex" | "claude",
  "event": "session-start" | "prompt-submit" | "stop" | "notification",
  "repo_root": "...",
  "workspace_root": "...",
  "cwd": "...",
  "project_scope": "...",
  "status": "ok" | "degraded",
  "missing_paths": ["..."],
  "validation_errors": ["..."],
  "system_context": {
    "boot_entry": "memory_core/INDEX.md",
    "state_entry": "memory_core/NOW.md",
    "state_summary": ["..."],
    "project_map_validation": "pass" | "fail",
    "legality_contract_validation": "pass" | "fail",
    "truth_basis_validation": "pass" | "fail",
    "registration_commit_gate": { ... },
    "core_provider": "external-core" | "legacy",
    "policy_pack": { ... }
  },
  "project_context": {
    "scope": "workbot" | "AEdu" | "platform-capabilities",
    "canonical": "...",
    "truth_status": "truth-ready" | "truth-incomplete",
    "runtime_root": "...",
    "source_refs": [...],
    "authority_refs": [...],
    "evidence_refs": [...]
  },
  "task_context": {
    "event": "...",
    "task_ref": "...",
    "session_id": "...",
    "surface_id": "...",
    "workspace_id": "...",
    "payload_keys": ["..."]
  },
  "allowed_reads": ["..."],
  "allowed_writes": { "fact": "...", "decision": "...", ... },
  "evidence_refs": ["..."],
  "artifact_refs": {
    "snapshot": "...",
    "latest": "...",
    "event_log": "..."
  }
}
```

### 5.3 Provider 双轨机制

Gateway 支持两种 core builder provider：

| Provider | 说明 | 触发方式 |
|----------|------|----------|
| `external-core` | 可选 provider，通过环境变量动态加载模块 | `MEMORY_HOOK_CORE_PROVIDER=external-core` |
| `legacy` | 默认 provider，直接调用 `memory_hook_core.build_context_package_core` | 默认值 / fallback |

Provider 切换逻辑（`_resolve_core_builder`）：

1. 请求 `external-core` → 尝试动态导入 `MEMORY_HOOK_EXTERNAL_CORE_MODULE`
2. 导入失败 → 自动 fallback 到 `legacy`，记录错误
3. `MEMORY_HOOK_SHADOW_RUN` 开启时，同时运行对端 provider 做对比验证

---

## 6. 模块分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     消费者层 (Consumers)                     │
│              Codex / Claude / cmux runtime                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ stdin (raw_payload JSON)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Gateway 层 (gateway)                      │
│                                                             │
│  memory_hook_gateway.py (981 行)                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ CLI 入口: main() → parse_args → build → write → exec │  │
│  │ Facade: _get_* 系列函数 (IF-5)                        │  │
│  │ Provider: _resolve_core_builder (双轨机制)             │  │
│  │ Adapter: 动态加载 runtime profile → globals.update()  │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌──────────────────┐ ┌──────────────┐ ┌────────────────────┐
│   Core 层        │ │  Impl 层     │ │  Adapter 层        │
│   (core)         │ │  (impls)     │ │  (adapters)        │
│                  │ │              │ │                    │
│ memory_hook_core │ │memory_hook_  │ │ neutral_policy     │
│ .py (271 行)     │ │impls.py      │ │ workbot_policy     │
│                  │ │(1040 行)     │ │ workbot_runtime_   │
│ 纯函数，无模块   │ │              │ │ profile            │
│ 依赖，通过参数   │ │ 实现所有     │ │ (371 行 合计)      │
│ 注入所有依赖     │ │ IF-1~IF-4    │ │                    │
│                  │ │ 接口         │ │ 项目特化配置       │
└──────────────────┘ └──────────────┘ └────────────────────┘
              ▲            ▲
              │            │
              └────────────┘
                   │
              ┌────┴─────┐
              │ Interfaces│
              │ (interfaces)│
              │           │
              │memory_hook│
              │_interfaces│
              │.py (242行)│
              │           │
              │ IF-1~IF-4 │
              └───────────┘
```

分层职责：

| 层 | 文件 | 职责 | 可修改性 |
|----|------|------|----------|
| **interfaces** | `memory_hook_interfaces.py` | 定义抽象接口，不依赖任何实现 | 稳定，变更需全层同步 |
| **core** | `memory_hook_core.py` | 纯函数组装逻辑，无模块级 import | 稳定，通过参数注入扩展 |
| **impls** | `memory_hook_impls.py` | 接口的默认实现（宿主中性） | 新增实现需对应新接口 |
| **adapters** | `memory_hook_adapters/*.py` | 项目特化配置和策略覆盖 | 新增项目只需新增 adapter |
| **gateway** | `memory_hook_gateway.py` | 编排层：加载 adapter → 组装 core → 写入 artifact → 委派 delegate | 稳定，通过 adapter 扩展 |

---

## 7. 关键设计决策

### 7.1 Adapter 动态加载机制

Gateway 通过 `MEMORY_HOOK_ADAPTER` 环境变量选择 adapter（默认 `workbot`），使用 `importlib.import_module` 动态加载 runtime profile 函数，将返回的配置字典注入 `globals()`。这使 gateway 代码本身不硬编码任何项目路径。

### 7.2 Provider 双轨 + Shadow Run

- 默认使用 `legacy` provider（内置 `memory_hook_core.build_context_package_core`）
- 通过 `MEMORY_HOOK_CORE_PROVIDER=external-core` 切换到 external provider

- `MEMORY_HOOK_SHADOW_RUN=1` 时同时运行对端 provider，对比结果用于验证

### 7.3 Artifact Compaction

M2 引入的 `ARTIFACT_COMPACTION` 策略字典控制 context package 裁剪，adapter 可配置哪些 section 包含在最终产物中。

### 7.4 Truth Basis 四要素

所有项目 canonical 文件必须包含 Truth Basis 四要素：

- **Source Refs**：信息来源（不能全是 canonical）
- **Authority Refs**：权威引用（必须是 formal canonical）
- **Evidence Refs**：证据引用（必须包含 lower-layer 支持）
- **Conflict Status**：冲突状态（必须为 `resolved`）

Gateway 在 `build_context_package` 阶段自动校验。

---

## 8. 测试覆盖

**目录**：`tests/` — 13 个测试文件

| 测试文件 | 对应阶段 | 覆盖内容 |
|----------|----------|----------|
| `test_m2_adapter_extraction.py` | M2 | Adapter 剥离：delegate gate、state file strictness、compaction policy |
| `test_m3_consumer_truth_cleanup.py` | M3 | Consumer truth 清理验证 |
| `test_m3_policy_pack_wiring.py` | M3 | Policy-pack 注入接线 |
| `test_m3_doc_scope_coverage.py` | M3 | 文档 scope 覆盖 |
| `test_memory_hook_core_m5_adapter_slimming.py` | M5 | Core 瘦身 |
| `test_memory_hook_gateway_m6_batch2_adapter_policy.py` | M6 | Adapter 策略 |
| `test_memory_hook_gateway_m6_batch3_provider_switch.py` | M6 | Provider 切换 |
| `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` | M6 | 结构和回滚 |
| `test_m7_independent_repo_baseline.py` | M7 | 独立仓基线 |
| `test_m7_p2_gateway_decoupling.py` | M7 | Gateway 解耦 |
| `test_m7_p3_smoke.py` | M7 | 冒烟测试 |
| `test_m7_p4_gateway_integration.py` | M7 | Gateway 集成 |
| `test_m7_p4_policy_pack_edge_cases.py` | M7 | Policy-pack 边界 |

运行方式：`python3 -m pytest -q tests`

---

## 9. 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MEMORY_HOOK_ADAPTER` | `workbot` | 选择 adapter profile |
| `MEMORY_HOOK_CORE_PROVIDER` | `legacy` | Core builder provider（`external-core` 或 `legacy`） |
| `MEMORY_HOOK_EXTERNAL_CORE_MODULE` | `workspace.tools.memory_hook_core` | External core 模块路径 |
| `MEMORY_HOOK_EXTERNAL_CORE_FUNC` | `build_context_package_core` | External core 函数名 |
| `MEMORY_HOOK_POLICY_PACK_PATH` | — | Policy-pack JSON 路径 |
| `MEMORY_HOOK_FORCE` | — | 强制 hook 执行（跳过外部上下文检查） |
| `MEMORY_HOOK_SHADOW_RUN` | — | 开启 shadow run 对比 |
| `CMUX_SURFACE_ID` | — | 当前 surface ID |
| `CMUX_WORKSPACE_ID` | — | 当前 workspace ID |
| `CMUX_HOOK_STATE_FILE` | — | Hook state 文件路径（adapter 注入） |

---

*文档基于代码实际阅读整理，所有行号引用对应 2026-04-26 的仓库快照。*
