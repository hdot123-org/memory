# 文档体系深度分析报告

> 生成日期：2026-05-01
> 分析范围：docs/、analysis/、review/、audit/、memory_core/ 下全部文档 + README.md

---

## 一、逐份文档内容摘要

### 1. README.md — 项目入口文档

**摘要**：定义 memory-core 的定位——为任何项目提供标准化的 `.memory/` 目录结构与版本管理能力。仓库只提供协议、模板、schema 和工具，不存储业务数据。文档覆盖了三个核心 CLI（`memory-init`、`memory-validate`、`memory-migrate`）、`.memory/` 目录结构、`memory.lock` 版本管理、Runtime Capability 声明、Adapter Protocol（`adapter.toml` 结构）、HookEvent 统一事件模型与 Schema 转换链、以及设计三原则（数据隔离、协议优先、污染防护）。

### 2. docs/BOUNDARY.md — 仓库边界定义

**摘要**：定义 memory 仓库的职责范围。属于本仓库的：核心代码、测试、协议与 Schema、模板、审查记录、示例 Fixture、Lessons/Decisions/全局规范。不属于本仓库的：真实业务项目的 PLAN/STATE/CANONICAL/NOW.md 等状态文件必须存放在各自业务项目仓库中。核心原则：单一归属原则、Fixture 与真实数据分离、通用 vs 专用、污染防护（`.gitignore` 禁止清单）、违反边界的处置流程。

### 3. docs/MEMORY_LOCK_SPEC.md — 版本锁定规范

**摘要**：定义 `memory.lock` 文件的 TOML schema（memory_version、schema_version、adapter_version、locked_at、lock_reason），兼容矩阵格式，SemVer 升级分类（patch/minor/major），判断项目是否落后的逻辑（只读 memory.lock，不读正文），升级决策树。核心保证：版本判断完全不读取项目 PLAN/STATE 正文。

### 4. docs/DOT_MEMORY_SPEC.md — .memory 目录规范

**摘要**：定义 `.memory/` 目录下 7 个必备文件的规范：memory.lock（TOML 版本锁定）、adapter.toml（适配器配置）、CANONICAL.md（项目编码规范）、PLAN.md（执行计划）、STATE.md（项目状态）、TASKS.md（任务清单）、migrations.log（迁移日志）。每个文件定义字段说明、必填项、枚举值约束和验证规则。验证器必须检查文件存在性、格式合法性、必填字段和枚举值。

### 5. docs/DISPATCH_TEMPLATE.md — 子代理 Dispatch 模板

**摘要**：定义主线程向子代理分派任务的标准格式。关键约束：子代理模型固定为 `gpt-5.4-mini`，仅在 branch-2 上工作，禁止 merge/push/delete branch。包含 Dispatch Prompt 模板、写入边界配置（allowed_read/allowed_write/deny_write）、回报格式模板、Residue 报告模板（P0-P3 优先级）和完整 Dispatch 示例。

### 6. docs/TASK_CARD_TEMPLATE.md — 任务卡模板

**摘要**：定义主线程通过 Projects URL 接收任务、dispatch 到子代理、验收 closure 的完整流程。包含任务卡字段模板、读卡流程（解析→创建 branch-2→构建 Dispatch→发送→等待回报）、子代理拆分规则（原子性、依赖 DAG、最大 200 行变更）、验收规则（前置条件→通过/不通过→Residue 处理）、状态流转图（pending→dispatched→in_progress→review→accepted/merged/closed 或 rejected→retry）。

### 7. docs/MIGRATION_RULES.md — 项目状态迁移规则

**摘要**：定义从 memory 仓库向业务项目仓库迁移真实项目状态的规则。核心原则：memory 仓库只保留指针或示例，业务项目是真相源，迁移必须在 branch-2 执行，幂等性，可追溯性。包含目标目录规范、迁移步骤模板（Pre-Migration→Execution→Post-Validation）、失败/Residue 处理流程、回滚策略、迁移候选评估。

### 8. docs/MIGRATION_FORMAT_SPEC.md — Migration 格式规范

**摘要**：定义 migration 脚本的命名规范（`<序号>_<描述>.<扩展名>`）、幂等要求（重复执行不破坏项目）、rollback 记录格式、migrations.log 的 NDJSON 格式、执行流程（读取 memory.lock→对比版本→按序号执行→备份→执行→记录→更新 version）。每个 migration 必须满足幂等检查清单。

### 9. docs/MIGRATION_CHECKLIST.md — 迁移执行清单

**摘要**：迁移任务的 checklist 模板，6 个 Phase：迁移前检查→执行迁移→memory 仓库清理→验证→验收与合入→异常处理。每个 Phase 有详细的勾选项。

### 10. docs/MULTI_PROJECT_SCAN_SPEC.md — 多项目升级扫描规范

**摘要**：定义多项目扫描的 registry 格式（TOML 索引）与输出规范。registry 包含项目位置 + 版本指针，全程只读不修改任何项目。扫描输出支持表格/JSON/卡片三种模式，可直接转为主线程任务卡。registry 禁止包含业务项目 PLAN/STATE 正文。

### 11. docs/FIXTURES_VS_REAL.md — Fixture 与真实数据区分

**摘要**：定义 memory 仓库中 example/fixture 数据与真实业务项目状态的区分规则。Fixture 特征：`demo-`/`fixture-` 前缀、虚构数据、最小化规模、不指向真实 URL/路径。真实项目状态特征：标准文件名、真实项目名称、真实路径引用。存放位置对照表和迁移规则。

### 12. docs/RESIDUE_INVENTORY.md — Residue 清单

**摘要**：记录本地 branch-2 有但远程 origin/branch-1 没有的内容。包含 9 个 Residue 项目（R-01 到 R-09），涉及 AxonHub Rebase 真实业务数据（PLAN/STATE/CANONICAL）需迁出、NOW.md 需清理、projects-spec.md 混合内容需剥离、templates 可保留等。分类标签：🔴必须迁出、🟡需清理、🟢可保留、🔵需同步。

### 13. docs/RESIDUE_DISPOSITION_PLAN.md — Residue 处置计划

**摘要**：目标是将 branch-1 恢复为干净稳定线。4 个 Phase：提取可保留内容→迁出真实业务数据→清理 memory 仓库→提交与验收。包含具体清理操作清单、验收标准、风险与注意事项、回滚方案。

### 14. docs/archive/RELEASE_NOTES_v0.2.0.md — 发布说明

**摘要**：memory-core v0.2.0 新增功能：CoreConfig dataclass（37 参数）、build_context_package_simple 简化 API、context-package-v1 schema、PathUtils 接口、PolicyRegistry 扩展、ArtifactWriter + DelegateRouter 分离类、pip 入口点、懒加载公共 API。测试结果 179 passed。向后兼容保证。

### 15. analysis/A1-architecture.md — 架构总览

**摘要**：完整依赖图分析。6 层依赖层级（Level 0-5），核心层 `memory_hook_core.py` 零内部依赖。分层评价（入口层→编排层→核心层→实现层→接口层→适配层）。入口链完整调用链。Public API 表面（4 个懒加载符号 + CLI 入口）。循环依赖检查（无真正循环，有已知反向依赖）。架构评价：优点 5 条、可改进点 5 条（Gateway 文件过大、Impl 文件过大、双重 import、适配器注册硬编码、类型标注不一致）。

### 16. analysis/A2-gateway.md — Gateway 详细分析

**摘要**：`memory_hook_gateway.py`（1028 行，68 个函数）的深度分析。列出 19 个 public 函数 + 52 个 private 函数的职责表。`build_context_package()` 11 步执行流程图。错误处理分析（10 种异常类型与捕获策略）。耦合分析（8 个直接依赖模块 + 标准库依赖）。复杂度热点（Top 5 最长函数、Cyclomatic 复杂度估计）。代码质量评分 7/10，列出优点 6 条、需改进 7 条。

### 17. analysis/A3-core.md — Core 模块分析

**摘要**：`memory_hook_core.py`（383 行）+ `memory_hook_config.py`（227 行）分析。5 个函数清单。Input→Output 完整数据流图。CoreConfig 38 字段分为 5 组，`__post_init__` 校验 14/37 字段。Provider 双模式机制（external-core vs legacy）。错误处理分析（4 种异常 + fallback 策略）。复杂度评估：`build_context_package_core` 207 行建议拆分为 5 个子函数。代码质量 7/10，改进建议 5 条。

### 18. analysis/A4-interfaces.md — 接口分析

**摘要**：`memory_hook_interfaces.py`（335 行）对照 `memory_hook_impls.py`（1251 行）的接口完整性分析。8 个 ABC 接口 + 2 个 TypedDict 清单。契约完整性评估（签名、TypedDict 字段匹配、ISP 分析）。胖接口识别：`PolicyRegistry`（13 方法）和 `GatewayBusinessPolicy`（17 方法）职责混杂。PolicyRegistry 与 GatewayBusinessPolicy 有 8 对方法重叠。实现矩阵（14 个实现类）。5 条改进建议（拆分胖接口、消除重叠、TypedDict 精确化、清理默认实现、统一 write_targets）。

### 19. analysis/A5-impls.md — 实现层分析

**摘要**：`memory_hook_impls.py`（1251 行，12 个类，83 个方法）分析。12 个类清单及职责。方法统计 Top 5。SRP 分析：`GatewayBusinessPolicyImpl` 承担 6 种责任（510 行，严重违反 SRP）。硬编码问题：大量 `"memory"` 路径段在 3 个类中重复 3 次，18+ 条中文字符串硬编码作为文档断言。错误处理模式评估（总体可接受但不一致）。复杂度热点（7 个超长方法，`event_contract_blocker_errors()` 100 行最复杂）。代码质量 6/10，5 条重构建议。

### 20. analysis/A6-config-schema.md — 配置与 Schema 分析

**摘要**：CoreConfig 37 字段清单（5 组），`__post_init__` 验证 14/37 字段，23 个未覆盖。工厂方法分析（`from_gateway_kwargs` 未使用，`to_gateway_kwargs` Path 不转 str）。Schema 模块只做 v2→v1 单向转换，两个已知信息丢弃（system_context、missing_paths）。字段冗余分析（project_canonical/runtime_root/global_canonical 语义重叠，event_log/project_map_governance 未消费）。5 条改进建议。

### 21. analysis/A7-adapters.md — 适配器分析

**摘要**：适配器三层继承链（Impl → Neutral → Workbot）。neutral vs workbot 区别对比。Policy Pack 内容（ADAPTER_POLICIES 硬编码覆盖，策略合并逻辑）。Runtime Profile 配置（~50 个键，分路径、策略、AEdu 专用、证据等类别）。扩展性评估（中等偏高，profile dict 键重是主要痛点）。与 core/gateway 集成点（`globals().update()` 注入、GATEWAY_POLICY_CLASS 动态引用）。5 条改进建议。

### 22. analysis/A8-tests.md — 测试质量分析

**摘要**：19 个测试文件，216 用例，3751 行测试代码。测试矩阵表（每文件用例数、行数、覆盖模块）。源模块覆盖率评估（良好/中等/偏弱分层）。测试分层金字塔（unit 65%、integration 23%、e2e 9%、property 7%）。测试质量评价（强测试 vs 弱测试）。命名规范评价。缺失场景（边界条件、异常路径、并发、性能、Windows 兼容、adapter 扩展、migration 向后兼容）。5 条改进建议。测试/源码比 0.88:1。

### 23. analysis/A9-ops-tooling.md — 运维工具分析

**摘要**：3 个运维模块分析。Provider Rollback（60 行）：实际是探测诊断工具而非回退工具，名字误导。Validate System（270 行）：6 个检查项，短路策略合理但部分检查注入 stub 绕过实际校验，`assert` 在 `-O` 下失效。Cmux Hook State（225 行）：状态文件 JSON 结构，4 种事件类型，并发安全良好但时间戳格式非标准 ISO 8601、自我验证是 destructive 的。综合评估与 5 条改进建议。

### 24. analysis/A10-dataflow-and-side-effects.md — 数据流与副作用

**摘要**：完整数据流图（事件→环境变量收集→git 查询→context 组装→provider 分发→写入）。8 个文件系统写入点清单（W1-W8），原子性保障评估。6 个 subprocess 调用清单（S1-S6）。13 个环境变量依赖清单。零第三方依赖。副作用隔离评估（文件 I/O 集中度 4/5、subprocess 3/5、环境变量 2/5、全局状态 2/5、可测试性 4/5）。5 条改进建议。

### 25. review/R1-impls-bugs.md — 实现层 Bug

**摘要**：6 个 Bug。Bug #1-2：`_conflict_strategies` 缺少 "default" 时 KeyError 崩溃（P2）。Bug #3-4：project_map_files 少于 3 个元素时 IndexError 越界（P2）。Bug #5：event_contract_files 缺失键时 KeyError（P2）。Bug #6：ArtifactSink 写入 event_log 时父目录不存在导致部分写入（P1）。

### 26. review/R2-gateway-bugs.md — Gateway Bug

**摘要**：5 个 Bug。Bug #1：external-core provider 被忽略，固定调用 legacy builder（P1）。Bug #2：shadow run 比较同一个 builder 而非 alternate provider（P2）。Bug #3：adapter config fallback 顺序让旧 global 值覆盖新 adapter 配置（P1）。Bug #4：未知 adapter 在 import 时崩溃（P2）。Bug #5：delegate subprocess OS 错误未被 main() 捕获（P2）。

### 27. review/R3-core-config-schema-bugs.md — Core/Config/Schema Bug

**摘要**：2 个 Finding。Finding #1：interface 对象部分提供时 `_resolve_callbacks()` 直接 getattr 抛 AttributeError 而非 fallback（P1）。Finding #2：v2 missing-path 失败信息在 convert_to_v1 时被丢弃，v1 degraded 状态但无缺失路径详情（P2）。3 个 Non-findings 验证。

### 28. review/R4-interfaces-business-policy-bugs.md — 接口/业务策略 Bug

**摘要**：2 个 Finding。Finding #1：拆分后的 `TruthBasisResolver` 忽略了 scope override config，`get_project_canonical()` 只返回静态配置映射而非合并后的覆盖值（Medium）。Finding #2：`business_policy_checks.py` 从 `memory_hook_impls.py` 导入 config dataclass，创建反向依赖导致潜在循环导入（Medium）。3 个 Non-findings 验证。

### 29. review/R5-ops-adapters-bugs.md — 运维/适配器 Bug

**摘要**：1 个 Finding。`validate_memory_system.py` 的 `check_context_package()` 无条件记录为通过，即使 package status 为 "degraded"（Medium）。5 个 Non-findings 验证。

### 30. review/2026-04-27-10-reviewer-bug-report-v2.md — 综合 Bug 报告

**摘要**：10 个审查员的综合报告。总计 37 个 Bug：P0（3 个：adapter 注册崩溃、adapter profile 非 dict 崩溃、函数缺失崩溃）、P1（9 个：非原子写入、subprocess 无 timeout、globals() 污染、profile 函数调用两次、任意模块加载、fallback KeyError、policy registry default 缺失）、P2（18 个：TOCTOU 竞态、验证回读破坏、noop 不一致、硬编码导入、git 无 timeout、死代码、CoreConfig 校验不完整、schema 版本不校验、TypedDict 全可选、payload 无 schema 验证、路径逃逸、event log 无锁、路径遍历、越界访问等）、P3（7 个：缺少 fsync、policy-pack TOCTOU、模块加载固化、双写不一致、空字符串允许、死代码）。覆盖矩阵、Non-findings 总结（40+ 项安全验证通过）。

### 31. audit/SUMMARY.md — 审计总结

**摘要**：三轮审计结果汇总。第一轮（AUDIT_01-09）：5 个维度 PASS。第二轮独立审查（INDEPENDENT_03-09）：6 个维度 FAIL（错误处理、文档、API 表面、性能、类型安全、Git 卫生）。第三轮复审（REAUDIT_01-07）：3 个维度 PASS，3 个维度 Improved。最终 verdict：PASS，216 tests passed。关键修复 5 项，剩余非阻塞建议 5 条。

### 32. memory_core/INDEX.md — 工作区总控入口

**摘要**：memory module workspace 的总控索引。快速入口（NOW.md、kb/INDEX.md、docs/INDEX.md）。核心目录结构树。project-map 合同口径（INDEX.md 是唯一合法入口，只有 active-legal 标记才是合法资料）。核心规则（NOW.md 唯一可覆写、kb/** read-first CRUD、log/ 只追加）。

### 33. memory_core/NOW.md — 当前状态

**摘要**：当前 Mission：将 memory module 发布为独立 PyPI 包 memory-core v0.2.0。已完成：Phase 1 版本统一、gitignore、LICENSE 元数据，命名空间迁移 workspace → memory_core，761 tests passed。Next 3 Actions：合入已验收分支到 branch-1、GitHub Release v0.2.0、验证 pip install 干净环境。无 Blockers。

### 34. memory_core/project-map/INDEX.md — 项目地图索引

**摘要**：规则文件索引。Status: active-legal。唯一合法入口规则：只有出现在合法目录地图中并被标为 `active-legal` 的条目才是合法资料，目录登记同次 git commit 提交后才生效。引用 2 个 rule files。

### 35. memory_core/project-map/legal-core-map.md — 合法资料地图

**摘要**：adapter 级别的合法资料地图。Status: active-legal。Rule：只有本图列出的 active-legal 条目才是当前合法资料。Legal Core Markers（active-legal、project-map/INDEX.md、workbot-truth-model.md、workbot-memory-system.md）。Active Legal Scopes（2 个文件路径）。

### 36. memory_core/project-map/ingestion-registry-map.md — 摄入登记册

**摘要**：adapter 级别的摄入登记册。Status: rule-only。Rule：Registry tracks incoming-raw 和 compatibility-only 材料，登记不授予合法性。4 个 Lifecycle Status。Required Registry Scopes（8 个 glob 模式覆盖整个项目代码和文档树）。

---

## 二、文档关系图

### 引用关系矩阵

```
                    ┌─────────────────────────────────────────┐
                    │            README.md (入口)              │
                    │  引用: BOUNDARY, DOT_MEMORY_SPEC,        │
                    │        MEMORY_LOCK_SPEC                  │
                    └───────────────┬─────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
    │  docs/BOUNDARY.md │  │docs/DOT_MEMORY_  │  │docs/MEMORY_LOCK_ │
    │  (边界定义)        │  │    SPEC.md       │  │  SPEC.md         │
    │  引用: RESIDUE_   │  │  引用: MEMORY_   │  │  引用:           │
    │  INVENTORY,       │  │  LOCK_SPEC       │  │  MIGRATION_      │
    │  RESIDUE_DISPO-   │  │                  │  │  FORMAT_SPEC     │
    │  SITION_PLAN      │  │                  │  │                  │
    └───────┬──────────┘  └────────┬─────────┘  └────────┬─────────┘
            │                      │                     │
            ▼                      │                     │
    ┌──────────────────┐           │                     │
    │RESIDUE_          │           │                     │
    │INVENTORY.md      │◄──────────┘                     │
    │(残留清单)         │                                 │
    └───────┬──────────┘                                 │
            │                                            │
            ▼                                            ▼
    ┌──────────────────┐                        ┌──────────────────┐
    │RESIDUE_DISPO-    │                        │MIGRATION_        │
    │SITION_PLAN.md    │                        │FORMAT_SPEC.md    │
    │(处置计划)         │                        │(迁移格式)         │
    └───────┬──────────┘                        └────────┬─────────┘
            │                                           │
            ▼                                           ▼
    ┌──────────────────┐                        ┌──────────────────┐
    │MIGRATION_        │                        │MULTI_PROJECT_    │
    │RULES.md          │                        │SCAN_SPEC.md      │
    │(迁移规则)         │                        │(多项目扫描)       │
    └───────┬──────────┘                        └──────────────────┘
            │
            ▼
    ┌──────────────────┐
    │MIGRATION_        │
    │CHECKLIST.md      │
    │(执行清单)         │
    └──────────────────┘

    ┌─────────────────────────────────────────┐
    │  docs/DISPATCH_TEMPLATE.md              │
    │    引用: TASK_CARD_TEMPLATE.md           │
    └───────────────┬─────────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────────────┐
    │  docs/TASK_CARD_TEMPLATE.md             │
    │    引用: DISPATCH_TEMPLATE.md            │
    └─────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │  docs/FIXTURES_VS_REAL.md               │
    │    互补: BOUNDARY.md                    │
    └─────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │  memory_core/INDEX.md                   │
    │    引用: project-map/INDEX.md           │
    └───────────────┬─────────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────────────┐
    │  project-map/INDEX.md                   │
    │    引用: legal-core-map.md,             │
    │           ingestion-registry-map.md      │
    └─────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │  memory_core/NOW.md                     │
    │    独立: 当前任务状态                     │
    └─────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │  audit/SUMMARY.md                       │
    │    独立: 审计结果汇总                      │
    └─────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │  analysis/A1-A10 (10 篇)                │
    │    互相关联: 架构→Gateway→Core→Interfaces │
    │    →Impls→Config→Adapters→Tests→Ops→Data │
    └───────────────┬─────────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────────────┐
    │  review/R1-R5 + bug-report-v2 (6 篇)     │
    │    引用: analysis 各篇的发现               │
    │    互补: audit/SUMMARY.md                 │
    └─────────────────────────────────────────┘
```

### 互补关系说明

| 文档对 | 关系 |
|--------|------|
| BOUNDARY.md ↔ FIXTURES_VS_REAL.md | BOUNDARY 定义"什么不属于"，FIXTURES 定义"如何区分" |
| MEMORY_LOCK_SPEC.md ↔ DOT_MEMORY_SPEC.md | MEMORY_LOCK 定义版本锁定的 schema，DOT_MEMORY 定义整个 .memory 目录，引用前者 |
| MIGRATION_RULES.md ↔ MIGRATION_FORMAT_SPEC.md ↔ MIGRATION_CHECKLIST.md | 规则定义→格式规范→执行清单，三层递进 |
| DISPATCH_TEMPLATE.md ↔ TASK_CARD_TEMPLATE.md | 互相引用，前者侧重子代理约束，后者侧重主线程流程 |
| analysis/ (A1-A10) ↔ review/ (R1-R5 + bug-report) | 分析发现架构/代码问题，审查发现具体 Bug |
| audit/SUMMARY.md ↔ review/bug-report-v2.md | 审计是整体 verdict，Bug 报告是详细 finding 清单 |
| project-map/INDEX.md ↔ legal-core-map.md ↔ ingestion-registry-map.md | 索引→合法地图→摄入登记，三层治理 |

---

## 三、核心规范要点汇总

### 3.1 BOUNDARY（仓库边界规范）

| 规则 | 内容 | 强制级别 |
|------|------|----------|
| 单一归属原则 | 每个业务项目的状态只能存在于该项目自己的 `.memory/` 下 | **强制** |
| Fixture 分离 | memory 仓库中示例必须带 `demo-` 或 `fixture-` 前缀 | **强制** |
| 通用 vs 专用 | memory 仓库只存跨项目通用的协议/模板/Schema | **强制** |
| 污染防护 | `.gitignore` 禁止提交 STATE.md/PLAN.md/CANONICAL.md/NOW.md | **强制** |
| 违反处置 | 发现违规必须记录到 RESIDUE_INVENTORY.md 并跟踪处置 | **强制** |

### 3.2 MEMORY_LOCK（版本锁定规范）

| 规则 | 内容 | 强制级别 |
|------|------|----------|
| 文件位置 | 每个消费者项目根目录或 .memory/ 下必须有 memory.lock | **强制** |
| SemVer | memory_version 必须遵循 MAJOR.MINOR.PATCH | **强制** |
| Schema 标识 | schema_version 必须是 memory-core 已发布的合法标识 | **强制** |
| 只读判断 | 判断项目是否落后时只读 memory.lock，不读项目正文 | **强制** |
| 升级分类 | patch/minor/major 分类决定迁移行为 | **推荐** |

### 3.3 DOT_MEMORY_SPEC（.memory 目录规范）

| 规则 | 内容 | 强制级别 |
|------|------|----------|
| 7 必备文件 | memory.lock, adapter.toml, CANONICAL.md, PLAN.md, STATE.md, TASKS.md, migrations.log | **强制** |
| 文件校验 | 验证器必须检查存在性、格式、必填字段、枚举值 | **强制** |
| 占位符替换 | 初始化时 `{{FIELD_NAME}}` 必须被替换 | **推荐** |
| TOML 格式 | memory.lock 和 adapter.toml 必须为合法 TOML | **强制** |

### 3.4 Adapter Protocol（适配器协议）

| 规则 | 内容 | 强制级别 |
|------|------|----------|
| adapter.toml 三节 | [core]、[policy]、[routing] | **强制** |
| Runtime Profile | 必须提供 `build_*_runtime_profile(repo_root, workspace_root) -> dict` | **强制** |
| 环境变量选择 | 通过 `MEMORY_HOOK_ADAPTER` 环境变量选择适配器 | **强制** |
| Profile ~50 键 | 新项目适配器需提供所有 gateway 期望的键 | **推荐** |

### 3.5 Migration（迁移规范）

| 规则 | 内容 | 强制级别 |
|------|------|----------|
| 幂等性 | 重复执行 migration 不破坏项目 | **强制** |
| 命名规范 | `<序号>_<描述>.<扩展名>` 格式 | **强制** |
| 备份规则 | 每个 migration 执行前必须备份到 .memory/backups/ | **强制** |
| NDJSON 日志 | migrations.log 必须为 NDJSON 格式 | **强制** |
| 回滚不自动 | 失败时不自动回滚，由人工/主线程决定 | **强制** |

### 3.6 项目治理规则（Project Map）

| 规则 | 内容 | 强制级别 |
|------|------|----------|
| 唯一合法入口 | project-map/INDEX.md 是唯一合法入口 | **强制** |
| active-legal 标记 | 只有被标记为 active-legal 的条目才是合法资料 | **强制** |
| 同次提交生效 | 目录登记必须与相关文件同次 git commit 提交才生效 | **强制** |
| 登记不授予合法性 | 仅进入登记册不授予合法性 | **强制** |

### 3.7 子代理操作约束

| 规则 | 内容 | 强制级别 |
|------|------|----------|
| branch-2 工作 | 子代理仅在 branch-2 上工作 | **强制** |
| 禁止 git 操作 | 禁止 merge/push/delete branch | **强制** |
| 写入边界 | 只能在 allowed_write 范围内操作 | **强制** |
| Residue 报告 | 必须按 P0-P3 优先级报告 residue | **强制** |

---

## 四、已知 Bug 清单

> 来源：review/ 下 6 份文档 + 综合 bug report

### P0 — 崩溃级（3 个）

| # | 描述 | 文件 | 严重度 | 状态 |
|---|------|------|--------|------|
| P0-01 | `_ADAPTER_REGISTRY` 无 key 校验，未知 adapter 导致模块 import 崩溃 | gateway.py:92 | P0 | 待修复 |
| P0-02 | adapter profile 返回非 dict 导致 `globals().update()` TypeError 崩溃 | gateway.py:110,113 | P0 | 待修复 |
| P0-03 | adapter 模块缺失预期函数导致 getattr AttributeError 崩溃 | gateway.py:98 | P0 | 待修复 |

### P1 — 错误结果级（9 个）

| # | 描述 | 文件 | 严重度 | 状态 |
|---|------|------|--------|------|
| P1-01 | ArtifactSinkImpl 非原子写入导致并发/崩溃时文件不一致 | impls.py:1133-1134 | P1 | 待修复 |
| P1-02 | subprocess.run 全量缺少 timeout — cmux delegate 挂起 | impls.py:150,245 | P1 | 待修复 |
| P1-03 | `_canonicalize_cmux_refs` subprocess 无 timeout | gateway.py:938 | P1 | 待修复 |
| P1-04 | `globals().update(profile)` 模块级命名空间污染 | gateway.py:113,119 | P1 | 待修复 |
| P1-05 | adapter profile 函数被调用两次，可能导致配置不一致 | gateway.py:117-119 | P1 | 待修复 |
| P1-06 | `_load_external_core_builder()` 任意模块加载（安全） | gateway.py:194 | P1 | 待修复 |
| P1-07 | `write_artifacts()` fallback 中 KeyError | gateway.py:911,916 | P1 | 待修复 |
| P1-08 | ArtifactSinkImpl.write 未防御 package key | impls.py:1120 | P1 | 待修复 |
| P1-09 | PolicyRegistryImpl 缺失 "default" conflict strategy 导致 KeyError | impls.py:379 | P1 | 待修复 |

### P2 — Edge Case（18 个）

| # | 描述 | 文件 | 严重度 |
|---|------|------|--------|
| P2-01 | 文件名生成 TOCTOU 竞争窗口 | impls.py:1122-1124 | P2 |
| P2-02 | `_write_hook_state_unlocked` 验证回读在写入成功后抛异常 | cmux_hook_state.py:141 | P2 |
| P2-03 | ClaudeDelegate noop_response stdout 为空（与 Codex 不一致） | impls.py:254-255 | P2 |
| P2-04 | resolve_policies 硬编码绝对导入路径 | workbot_policy.py:79 | P2 |
| P2-05 | git subprocess 调用无 timeout | gateway.py:604,624,631 | P2 |
| P2-06 | inject_policy_pack_config / resolve_policies 死代码 | workbot_policy.py:54-82 | P2 |
| P2-07 | AEdu 硬编码路径无加载时校验 | workbot_runtime_profile.py:111-124 | P2 |
| P2-08 | CoreConfig 缺少 project_map_governance / event_log 的 Path 类型校验 | config.py:90 | P2 |
| P2-09 | convert_to_v1 不校验输入 schema_version | schema.py:30 | P2 |
| P2-10 | TypedDict total=False 导致所有 key 可选 | interfaces.py:23,37 | P2 |
| P2-11 | `_read_payload()` 无 schema 验证 | gateway.py:331-338 | P2 |
| P2-12 | `_path_is_under_lexical()` 不 resolve symlinks（路径逃逸） | business_policy_checks.py:82-88 | P2 |
| P2-13 | event log 并发追加写无锁 | impls.py:1136 | P2 |
| P2-14 | `_registration_payload_paths()` 从 payload 直接取值无 repo 内校验 | gateway.py:540-544 | P2 |
| P2-15 | validate_project_map_files 越界访问 | impls.py:840 | P2 |
| P2-16 | `write_artifacts()` 仅捕获 RuntimeError，漏捕获 OSError/KeyError | gateway.py:904-927 | P2 |
| P2-17 | `append_error_log()` 同样仅捕获 RuntimeError | gateway.py:893-901 | P2 |
| P2-18 | `main()` 直接索引 package["status"] 和 package["missing_paths"] | gateway.py:987,994 | P2 |

### P3 — 代码异味（7 个）

| # | 描述 | 文件 | 严重度 |
|---|------|------|--------|
| P3-01 | `_write_hook_state_unlocked` 缺少目录 fsync | cmux_hook_state.py:135-136 | P3 |
| P3-02 | policy-pack TOCTOU (exists → read_text) | workbot_policy.py:47-48 | P3 |
| P3-03 | `CLAUDE_HOOK_STATE_FILE` 模块加载时固化 | workbot_runtime_profile.py:253 | P3 |
| P3-04 | `_adapter_config` 与 `globals()` 双写/双读不一致 | gateway.py:109-113 | P3 |
| P3-05 | CoreConfig surface_id / workspace_id 允许空字符串 | config.py:144 | P3 |
| P3-06 | `from_gateway_kwargs` 死代码 | config.py:189 | P3 |
| P3-07 | `_resolve_callbacks()` interface 对象路径为死代码 | core.py:22-46 | P3 |

---

## 五、架构分析结论汇总

### 5.1 整体架构评价

memory hook 系统采用 **端口-适配器（Hexagonal）架构**，核心思想正确：
- 核心层（`memory_hook_core.py`）零内部依赖，纯函数逻辑
- 接口层（`memory_hook_interfaces.py`）定义 8 个 ABC + 2 个 TypedDict
- 实现层（`memory_hook_impls.py`）提供对应实现
- 适配层（`memory_hook_adapters/`）通过三层继承链实现可扩展性
- 入口层（`memory_hook_gateway.py`）作为 Facade 协调各层

### 5.2 关键架构问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| Gateway 文件过大（1028 行） | 中 | 承担 CLI、policy、artifact、adapter、delegate 多重职责 |
| Impl 文件过大（1251 行） | 中 | `GatewayBusinessPolicyImpl` 510 行，承担 6 种责任 |
| `globals().update()` 污染 | 高 | ~50 个 adapter key 直接注入模块全局命名空间 |
| 硬编码路径重复 | 中 | `"memory"` 路径在 3 个类中重复出现 |
| Provider 机制未生效 | 高 | external-core provider 被忽略，固定调用 legacy |
| Shadow run 失效 | 中 | 比较同一个 builder 而非 alternate provider |

### 5.3 数据流与副作用

- **零第三方依赖**：整个 tools/ 仅使用 Python 标准库
- **8 个文件系统写入点**：主要集中在 ArtifactSink/ErrorSink，但 EVENT_LOG 无锁
- **13 个环境变量**：分散在 4+ 个模块，无统一配置层
- **6 个 subprocess 调用**：部分缺少 timeout 保护
- **原子性保障不一致**：cmux_hook_state 有 flock + atomic write，但 ArtifactSink 没有

### 5.4 测试覆盖

- 216 个测试，3751 行代码，测试/源码比 0.88:1（偏低）
- Unit 占 65%，integration 占 23%，e2e 占 9%
- 缺失：interfaces 契约验证、provider rollback 直接测试、schema 完整测试、并发测试
- 弱测试：smoke 测试只检查"不报错"，未验证结构正确性

### 5.5 审计结果

- 三轮审计后最终 verdict：**PASS**
- 216 tests passed，100% 稳定性
- 剩余 5 条非阻塞建议

---

## 六、文档体系完整性评估

### 6.1 覆盖矩阵

| 领域 | 是否有文档 | 文档质量 | 缺口 |
|------|-----------|---------|------|
| 仓库边界 | ✅ BOUNDARY.md | 优秀 | 无 |
| .memory 目录规范 | ✅ DOT_MEMORY_SPEC.md | 优秀 | 无 |
| 版本锁定 | ✅ MEMORY_LOCK_SPEC.md | 优秀 | 无 |
| 适配器协议 | ✅ README + A7 | 良好 | 缺少独立 Adapter Protocol 文档 |
| 迁移规范 | ✅ MIGRATION_* 系列（3 篇） | 优秀 | 无 |
| 多项目扫描 | ✅ MULTI_PROJECT_SCAN_SPEC.md | 良好 | 无 |
| 任务分发 | ✅ DISPATCH_TEMPLATE + TASK_CARD_TEMPLATE | 优秀 | 无 |
| Fixture vs Real | ✅ FIXTURES_VS_REAL.md | 优秀 | 无 |
| 架构分析 | ✅ A1-A10（10 篇） | 优秀 | 无 |
| Bug 审查 | ✅ R1-R5 + v2 report | 优秀 | R2 和 R7 报告缺失（已部分覆盖） |
| 审计总结 | ✅ audit/SUMMARY.md | 良好 | 无 |
| 项目治理 | ✅ project-map/*（3 篇） | 良好 | 无 |
| 当前状态 | ✅ NOW.md | 良好 | 无 |
| 发布说明 | ✅ archive/RELEASE_NOTES_v0.2.0.md | 良好 | 缺少 v0.1.0 说明 |
| 兼容性矩阵 | ❌ | **缺失** | MEMORY_LOCK_SPEC.md 中提及但文件不存在 |
| 类型安全报告 | ⚠️ | **部分** | audit 提及但无独立文档 |
| API 文档 | ⚠️ | **部分** | README 有部分，但缺少完整 API reference |
| 部署/运维指南 | ❌ | **缺失** | 无独立 CI/CD 部署文档 |

### 6.2 完整性评分：8/10

**得分项（+）**：
- 核心规范（边界、目录、版本、迁移）覆盖完整且质量高
- 架构分析深度优秀（10 篇覆盖所有模块）
- Bug 审查系统化（37 个 finding + 40+ non-findings）
- 审计三轮验证，结论可信
- 文档之间有明确的引用和互补关系

**扣分项（-）**：
- 兼容性矩阵（COMPATIBILITY_MATRIX.md）被 MEMORY_LOCK_SPEC.md 引用但实际不存在（-1）
- 缺少独立的 Adapter Protocol 规范文档，相关内容散落在 README 和 A7 中（-0.5）
- 缺少完整的 API Reference 文档（-0.5）
- R2 和 R7 审查员报告缺失（-0.5）
- 缺少 CI/CD 部署和运维指南（-0.5）

### 6.3 文档健康度总结

文档体系整体 **健康且自洽**。核心规范文档（BOUNDARY、MEMORY_LOCK、DOT_MEMORY）形成稳固的三角关系，迁移文档（RULES→FORMAT→CHECKLIST）层次递进，分析文档（A1-A10）与审查文档（R1-R5）形成发现问题→定位问题的闭环。主要缺口在于兼容性矩阵的缺失和 API 文档的不完整，建议在下一个版本中补齐。
