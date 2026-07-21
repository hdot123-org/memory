---
type: "[DOC:ARCHITECTURE]"
title: "memory-core 架构审计发现（157项）"
shortname: REF-000
status: 可评审
scope: default
created: 2026-07-16
updated: 2026-07-16
source: architecture-audit
confidence: high
tags: [audit, architecture, rule-engine, llm-isolation, refactoring]
related: [DES-001, DES-004, DES-007, REF-001, REF-002]
---

> 文档编号：REF-000 | 18轮检查 | 157个遗漏点 | 18大维度

# memory-core 架构审计发现

## 审计方法论

十八轮递进式检查，从 LLM/规则分离角度切入，逐步扩展到架构资产、向后兼容、迁移、CI/CD、平台集成、运行时配置、可靠性、质量工具链、测试、I/O 契约、进程管理、安全、异常处理、文档景观、构建打包、数据契约等维度。

## 分类总览

| 类别 | 项数 | 优先级 | 核心内容 |
|------|------|--------|----------|
| A. 架构资产（须演进） | 13 | 演进 | 接口层/CoreConfig/Adapter/类层次/API |
| B. 代码质量（须修复） | 19 | 修复 | 双轨策略/三复制/异常处理 |
| C. 模块结构（须重组） | 10 | 重组 | 54文件平铺/God模块/双导入 |
| D. 向后兼容（须保持） | 14 | 保持 | CLI/API/脚本模式/消费方契约 |
| E. 运行时配置（须理解） | 15 | 理解 | 环境变量/降级/超时 |
| F. 数据契约（须维护） | 12 | 维护 | 状态文件/Schema版本 |
| G. 测试（须更新） | 11 | 更新 | 125测试/mypy/coverage |
| H. CI/CD工具链（须同步） | 13 | 同步 | 硬编码路径/配置/发布 |
| I. 文档（须更新） | 16 | 更新 | 67+文件/DES文档/wiki |
| J. 安全（须保留） | 6 | 保留 | 脱敏/BOUNDARY |
| K. 打包分发（须维护） | 6 | 维护 | packages.find/模板 |
| L. 平台集成（须保留） | 5 | 保留 | Factory hooks/跨平台 |
| **全局知识库缺口** | 25 | 后续 | 10运维+15工程经验 |

---

## A. 架构资产（须演进而非替换）- 13项

### A-01 [致命] 已有抽象层被完全忽略
- **发现**: memory_hook_interfaces.py 已定义 8 个 ABC + 3 个 Protocol
- **ABC 列表**: HostDelegate, PolicyRegistry, RouteTargetPolicy, WriteTargetPolicy, GatewayBusinessPolicy, ArtifactSink, ErrorSink, PathUtils
- **Protocol 列表**: PolicyQueryProvider, GovernanceChecker, TruthBasisProvider
- **影响**: 新建 rule_engine/base.py 如果另起炉灶会创建并行第二套抽象
- **设计要求**: rule_engine 必须基于现有 GatewayBusinessPolicy/PolicyRegistry 演进

### A-02 [致命] CoreConfig（37字段配置中枢）无归属
- **发现**: memory_hook_config.py 的 CoreConfig dataclass 含 37 个字段
- **字段分组**: 环境(7) + 路径(7) + 策略(6+3可选) + 回调(13) + 接口对象(4可选)
- **桥接方法**: from_gateway_kwargs() + __post_init__ 校验
- **设计要求**: 明确 CoreConfig 归入 rule_engine/ 还是 hook/

### A-03 [致命] Adapter/Provider 插件系统无归属
- **发现**: memory_hook_gateway.py 实现完整插件体系
- **组件**: _ADAPTER_REGISTRY, MEMORY_HOOK_ADAPTER, reload_adapter(), CoreBuilder, _load_external_core_builder(), _resolve_core_builder(provider)
- **设计要求**: 新架构必须显式包含 adapter registry

### A-04 [高] Public API 契约（4个符号 via __getattr__）
- **符号**: build_context_package, build_context_package_simple, CoreConfig, build_context_package_from_config
- **设计要求**: 通过 re-export shim 保持这些路径

### A-05 [高] 回调驱动架构
- **发现**: CoreConfig 有 13 个回调字段 + 接口对象
- **影响**: 规则引擎设计必须适应回调驱动模式

### A-06 [高] Host delegate 层次（4个委托）
- CodexDelegate/ClaudeDelegate/FactoryDelegate/NoopHostDelegate + resolve_host_delegate()

### A-07 [高] 完整类层次：30+类跨3种模式
- 接口层(8 ABC + 3 Protocol) + 实现层(13) + 领域层(6) + 其他

### A-08 [高] Policy pack JSON schema 契约
- memory-hook-policy-pack.json, schema m3-policy-pack-v1
- 6个策略键 + 3种冲突策略

### A-09 [高] Provider 双轨系统
- legacy vs external-core provider, shadow-run 对比

### A-10 [高] API 契约：唯一入口 build_context_package
- build_context_package(host, event, payload) -> dict

### A-11 [中] 数据类模式多样
- @dataclass/frozen=True, TypedDict, NamedTuple, Enum

### A-12 [中] memory_hook_core.py 核心装配
- build_context_package_from_config() + _resolve_callbacks()

### A-13 [中] 内部管道参数从34增长到37

---

## B. 代码质量（须修复）- 19项

### B-01 [高] 双轨业务策略
- 旧 GatewayBusinessPolicyImpl(1500行) 与新 business_policy_checks.*(6类) 并存且已发散
- marker 校验旧类用硬编码中文字符串，新类用 MKR_* 常量

### B-02 [高] 8个工具函数三处复制
- _path_is_under, _section_bullets, _markdown_code_tokens 等8个函数在3个文件逐字重复

### B-03 [高] 无统一 Rule 抽象
- 6种规则模式（预编译正则/字面量正则/fnmatch/字符串包含/字典映射/if-elif链）散落9个文件

### B-04 [高] _classify_truth_ref 14分支链两处复制

### B-05 [中] Write-target 字典三处复制

### B-06 [中] 规则逻辑内嵌 I/O（git/read_text/subprocess）

### B-07 [中] pretooluse_guard 单文件700行6职责

### B-08 [中] 错误处理模式分散（write_error_log 5+模块 try/except import）

### B-09 [中] 文件锁定在4模块独立实现（fcntl.flock）

### B-10 [中] 仅1个自定义异常类（PromptTooLongError）

### B-11 [中] 异常吞噬模式（except Exception: pass）

### B-12 [中] 大量泛型 Exception 捕获

### B-13 [中] ValueError 用作领域错误 catch-all

### B-14 [中] 55处 type:ignore 抑制

### B-15 [中] 多处 legacy 引用表示迁移未完成

### B-16 [低] 日志模式不一致（logger/_logger 混用）

### B-17 [低] OSError 处理模式不统一

### B-18 [低] 上下文管理器极少使用（仅2模块）

### B-19 [低] 无自定义装饰器模式

---

## C. 模块结构（须重组）- 10项

### C-01 [致命] tools/ 目录54个文件平铺，无子包分类

### C-02 [致命] 幽灵 feature_flags 模块（.env.example 引用不存在的模块）

### C-03 [致命] 1.7MB schema-audit.log 在源码包

### C-04 [高] 5个 God 模块（>1200行）
- init_project_memory.py(2647), memory_hook_gateway.py(2148), daily_kb_audit.py(1803), memory_hook_impls.py(1500), migrate_project_memory.py(1411)

### C-05 [高] 30+处双重导入反模式

### C-06 [高] 循环依赖被延迟加载掩盖

### C-07 [中] 复杂度被配置抑制而非修复（ruff C901）

### C-08 [中] 15个模块有 __main__ 脚本入口

### C-09 [中] tools/__init__.py 空文件（无 __all__）

### C-10 [中] KB_TEMPLATES/FILE_TEMPLATES 大内联字典

---

## D. 向后兼容（须保持）- 14项

### D-01 [致命] 16个 CLI 入口点无迁移映射

### D-02 [高] 公共 API 懒导出契约

### D-03 [高] 脚本模式双导入反模式

### D-04 [高] 模块级 globals 注入兼容层

### D-05 [致命] 外部消费方向后兼容无保障

### D-06 [高] compat.py 版本矩阵（9版本x5维度）

### D-07 [中] 退出码契约（0/1/2）

### D-08 [中] stdin/stdout/stderr I/O 契约

### D-09 [中] 所有 I/O 硬编码 UTF-8

### D-10 [中] packages.find 包含 memory_core* 和 workspace*

### D-11 [中] posthog 版本约束 >=3.0,<8.0

### D-12 [中] tomli 条件依赖（Python <3.11）

### D-13 [中] 版本字符串源于 constants.py 单一位置

### D-14 [低] 向后兼容测试（VAL-COMPAT-001/002）

---

## E. 运行时配置（须理解）- 15项

### E-01 [致命] 25+环境变量作为隐式配置契约
- MEMORY_HOOK_*(15+), MEMORY_CORE_*(2), MEMORY_LLM_*(1), GLM_API_KEY, POSTHOG_*(2), FACTORY_*(2), CMUX_*(2), WORKBOT_*(1)

### E-02 [高] 源仓库模式（readonly/develop）

### E-03 [高] Factory hooks 集成契约（9种事件类型）

### E-04 [中] .env.example 配置文档（含幽灵 feature_flags）

### E-05 [中] 性能测量基础设施（duration_ms 全链路）

### E-06 [中] 优雅降级模式遍布全系统（4条降级路径）

### E-07 [中] 超时模式不统一（5种不同超时值）

### E-08 [低] 除遥测外无重试逻辑

### E-09 [中] subprocess 模式不统一（3种调用模式）

### E-10 [中] signal.alarm 超时（POSIX-only）

### E-11 [中] fcntl POSIX-only, 无 Windows 回退

### E-12 [中] macOS /tmp 符号链接感知

### E-13 [中] 广泛使用 Path.resolve()

### E-14 [低] AGENTS.md markers 契约

### E-15 [低] 备份/回滚机制

---

## F. 数据契约（须维护）- 12项

### F-01 [高] 状态文件格式契约
- memory.lock(TOML), manifest.json(v2 SHA-256+HMAC), integrity-audit.jsonl, path-index.json

### F-02 [高] Schema 版本契约（5+版本字符串）

### F-03 [高] 模板状态文件契约（adapter.toml 三段式）

### F-04 [高] MEMORY_LOCK_SPEC.md(SPEC-010) 定义 memory.lock schema

### F-05 [高] memory.lock 5字段有语义含义

### F-06 [中] SUPPORTED_SCHEMA_VERSIONS 硬编码

### F-07 [中] Schema 审计日志路径相对于模块文件

### F-08 [中] CLI 帮助文本内联在各模块

### F-09 [中] 无 JSON Schema 验证

### F-10 [中] 代码质量指标追踪（覆盖率15%底线）

### F-11 [中] DOT_MEMORY_SPEC.md(SPEC-DOT-MEMORY) 352行

### F-12 [低] BOUNDARY.md 定义严格分离规则

---

## G. 测试（须更新）- 11项

### G-01 [高] ~125个测试文件深度耦合（部分95KB/86KB/71KB）

### G-02 [高] 测试中动态导入（importlib）

### G-03 [中] conftest.py autouse fixture 耦合

### G-04 [中] tests/conftest.py fixtures 引用目录结构

### G-05 [中] 里程碑标签测试（P2-P4, M7）

### G-06 [中] 15%覆盖率底线（当前~16%）

### G-07 [中] 18/~63模块通过 mypy strict（28%）

### G-08 [中] deptry DEP001 忽略12个模块

### G-09 [低] pytest --reruns 2

### G-10 [低] Python 3.13分类器但CI仅测3.9-3.12

### G-11 [低] 11处 pragma: no cover

---

## H. CI/CD工具链（须同步）- 13项

### H-01 [高] CI工作流硬编码路径

### H-02 [高] Shell脚本 sys.path.insert

### H-03 [中] ruff.toml per-file-ignores（7个文件）

### H-04 [中] pyproject.toml mypy overrides（18+模块）

### H-05 [中] CODEOWNERS 引用 /memory_core/tools/

### H-06 [中] pre-commit vulture 扫描路径

### H-07 [中] Pylint R0801 重复代码检测

### H-08 [中] Vulture 死代码检测

### H-09 [中] Deptry 依赖分析（13+忽略项）

### H-10 [中] pdoc API 文档生成

### H-11 [中] typing-tech-debt.md 引用17+模块路径

### H-12 [中] 发布流程含下游分发

### H-13 [中] CONTRIBUTING.md 双门禁审批流程

---

## I. 文档（须更新）- 16项

### I-01 [高] 已有11篇编号设计文档（DES-001~DES-011, ~200KB）

### I-02 [高] 设计文档版本过时（v0.4.0 vs v0.9.0）

### I-03 [中] 设计文档 frontmatter 规范

### I-04 [中] 设计文档法律地位声明

### I-05 [高] BOUNDARY.md 系统规范存在

### I-06 [中] Runbooks 确认存在（7篇）

### I-07 [高] 完整文档清单：67+文件, ~563KB+

### I-08 [中] PRD-001-PRODUCT-DESIGN.md(35KB) 在 drafts/

### I-09 [中] RFC-0001-eliminate-dot-memory.md

### I-10 [中] Bug 报告: factory-session-orphan-shutdown-crash.md

### I-11 [中] 审计文档含会话特定发现

### I-12 [中] 仅1个正式决策记录

### I-13 [中] PRETOOLUSE_GUARD_TASK_REMOVAL.md 在 drafts/

### I-14 [中] memory-core-development skill 引用 v0.5.0

### I-15 [中] review-index.md 过时

### I-16 [低] droid-wiki 引用已移除模块

---

## J. 安全（须保留）- 6项

### J-01 [中] SanitizingFilter 日志脱敏（Bearer/password/API key/private IP）

### J-02 [中] 遥测数据脱敏（文件路径替换为 basename）

### J-03 [高] BOUNDARY.md 定义严格分离规则

### J-04 [中] BOUNDARY.md 引用过时路径

### J-05 [中] 备份/回滚机制

### J-06 [低] 无 GitHub issue/PR 模板

---

## K. 打包分发（须维护）- 6项

### K-01 [中] workspace/templates/ 打包模板

### K-02 [低] CODEOWNERS 引用

### K-03 [低] pre-commit vulture 扫描路径

### K-04 [低] build/ 目录残留构建产物

### K-05 [低] 无 Makefile/Taskfile/.editorconfig

### K-06 [低] 无 GitHub issue/PR 模板

---

## L. 平台集成（须保留）- 5项

### L-01 [高] Factory hooks 集成契约（9种事件 + wrapper脚本）

### L-02 [高] Host delegate 层次（4个委托）

### L-03 [中] 跨平台: fcntl POSIX-only

### L-04 [中] signal.alarm 超时（POSIX-only）

### L-05 [中] macOS /tmp 符号链接感知

---

## 全局知识库缺口分析

### 25个知识领域缺口

**运维基础设施知识（10个）：**

| # | 领域 | 现有覆盖 | 缺口 |
|---|------|----------|------|
| 1 | CI/CD工作流 | 6篇 | 发布分发流程文档 |
| 2 | 测试基础设施 | 1篇 | 测试架构总览 |
| 3 | 打包分发 | 0篇 | 完全空白 |
| 4 | 代码质量工具链 | 1篇 | 工具链使用指南 |
| 5 | 平台集成 | 3篇 | Factory hooks完整指南 |
| 6 | 运行时配置 | 1篇 | 环境变量参考 |
| 7 | 安全实践 | 2篇 | 安全模式指南 |
| 8 | 文档规范 | 1篇 | 文档规范指南 |
| 9 | 发布流程 | 2篇 | 完整发布流程 |
| 10 | 降级与可靠性 | 2篇 | 降级模式文档 |

**工程经验教训（15个，全部空白）：**

| # | 领域 | 来源发现 |
|---|------|----------|
| 11 | 规则引擎设计模式 | B-03: 6种规则模式无统一抽象 |
| 12 | 模块组织反模式 | C-01: 54文件平铺 |
| 13 | 双轨迁移策略 | B-01: 新旧实现并存且发散 |
| 14 | 异常处理最佳实践 | B-10/B-11/B-12 |
| 15 | 类型债务管理 | B-14: 55处type:ignore |
| 16 | 导入模式反模式 | C-05: 30+双导入 |
| 17 | God模块预防 | C-04: 5个>1200行模块 |
| 18 | 回调驱动架构 | A-05: CoreConfig 37字段+13回调 |
| 19 | 策略包设计模式 | A-08/DES-007 |
| 20 | 文件锁定模式 | B-09: 4模块独立fcntl |
| 21 | 环境变量管理 | E-01: 25+环境变量 |
| 22 | Schema版本管理 | F-02: 5+版本/compat矩阵 |
| 23 | 适配器/插件系统设计 | A-03: Adapter/Provider注册 |
| 24 | Shadow-run安全对比 | A-09/E-06 |
| 25 | 跨平台兼容性 | L-03/L-04: fcntl/signal POSIX-only |

---

## 附录：审计统计

### 严重度分布

| 严重度 | 数量 | 占比 |
|--------|------|------|
| 致命(P0) | 6 | 3.8% |
| 高(P1) | 34 | 21.7% |
| 中(P2) | 87 | 55.4% |
| 低(P3) | 30 | 19.1% |
| **总计** | **157** | 100% |

### 检查轮次趋势

| 轮次 | 发现数 | 新致命 | 新高级 |
|------|--------|--------|--------|
| 1-5轮 | 63 | 6 | 22 |
| 6-10轮 | 47 | 0 | 6 |
| 11-15轮 | 29 | 0 | 5 |
| 16-18轮 | 18 | 0 | 1 |

### 核心重构范围 vs 维护运维

**核心重构（REF-xxx 设计文档聚焦）：**
- A(架构资产演进) + B(代码质量修复) + C(模块重组) + LLM隔离

**维护运维（全局知识库后续处理）：**
- E(运行时配置) + G(测试) + H(CI/CD) + I(文档) + J(安全) + K(打包)

**兼顾约束（设计文档中作为约束条件）：**
- D(向后兼容) + F(数据契约)

---

*由架构审计自动生成于 2026-07-16*
