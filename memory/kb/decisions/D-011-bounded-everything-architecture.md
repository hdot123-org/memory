---
title: "Bounded Everything 作为架构哲学"
status: accepted
date: 2026-08-03
source: oh-my-cli vs memory-core 工程对比分析（维度 07：有限操作设计 vs 隐式边界）
tags: [decision, architecture, bounded, reliability, security, fail-closed]
related: [D-009-lifecycle-event-sharding, D-010-lifecycle-robustness-fixes]

---

# D-011: Bounded Everything 作为架构哲学

## 决策

将 "bounded everything" 确立为 memory-core 的架构级设计哲学。每个模块的入口应定义显式的运行时边界（timeout、size-limit、output-cap），所有边界违规 fail-closed（返回安全结果，不抛异常），redaction 作为共享基础设施贯穿全链路。

## 背景

oh-my-cli vs memory-core 对比分析（维度 07）揭示了两者的根本架构差距：

**oh-my-cli 的做法**（架构级哲学）：
- `tool-invocation.ts` 定义硬编码边界：`DEFAULT_INVOKE_TIMEOUT_MS=30000`，`MAX_INVOKE_TIMEOUT_MS=300000`，`DEFAULT_MAX_OUTPUT_BYTES=65536`
- `clampInvokeTimeout()` 将任意输入钳位到合法区间，不可绕过
- `permission-impact.ts` 的 `redactSecrets()` 覆盖 6 种 secret 模式，被 10+ 模块复用
- `compaction.ts` 的每个字段都有精确数字上限（`MAX_FIELD=500`，`MAX_REFERENCE=160`，`MAX_DECISIONS=50`）
- `fatal-boundary.ts` 连崩溃信息都要 `redactHomePath(redactSecrets(...))` 后再截断
- 所有边界违规 fail-closed：超时返回 `timedOut` 标记，输出超限返回 `outputCapped` 标记，永不抛异常

**memory-core 的现状**（局部边界）：
- `_validation_constants.py` 定义的是业务规则常量（中文标记字符串），非运行时边界
- `error_logger.py` 有 `_redact_api_keys()` 但只覆盖 `sk-` 格式
- `pretooluse_guard.py` JSON 解析失败时 exit 0（fail-open 放行）
- 各模块各自定义超时和大小限制，无统一常量层
- 没有共享的 redaction 基础设施

## 理由

1. **可靠性**：没有统一的 timeout 和 output-cap，hook 执行可能无限挂起或 OOM。这是生产环境的基础保障。
2. **安全性**：redaction 不贯穿全链路意味着 secret 可能通过 error log、guard reason、prompt warning 等通道泄漏。
3. **可维护性**：边界常量散落在各模块中，修改一个全局限制需要搜索多个文件。集中定义降低维护成本。
4. **一致性**：fail-closed 不是系统性原则（guard 解析失败时 fail-open），导致安全行为不可预测。

## 四个一致特征（从 oh-my-cli 提炼）

oh-my-cli 的 bounded everything 有四个一致特征，应作为 memory-core 的架构指导原则：

| 特征 | oh-my-cli 示例 | memory-core 现状 |
|------|---------------|-----------------|
| 每个模块有显式常量定义上界 | `DEFAULT_INVOKE_TIMEOUT_MS`, `MAX_OUTPUT_BYTES` 等集中在 `tool-invocation.ts` | 常量散落，`_validation_constants.py` 是业务常量非运行时边界 |
| 所有边界违规 fail-closed | 超时返回 `timedOut`，输出超限返回 `outputCapped`，永不抛异常 | guard 解析失败 exit 0（fail-open），行为不一致 |
| Redaction 是共享基础设施 | `redactSecrets()` 在 `permission-impact.ts`，被 10+ 模块复用 | `_redact_api_keys()` 在 `error_logger.py`，只覆盖 sk- 格式 |
| Schema + Version 标记有界数据结构 | `IDEMPOTENCY_GUARD_SCHEMA`, `MCP_CONTRACT_VERSION` 等 | 无系统性 schema 版本化 |

## 影响

| 变更 | 预估工作量 | 优先级 |
|------|-----------|--------|
| 建立 `_runtime_bounds.py` 中央常量层（`HOOK_TIMEOUT_S=30`, `MAX_OUTPUT_BYTES=65536`, `MAX_ERROR_MSG=500`） | 2-3 天 | 高 |
| 统一 redaction 基础设施（`_redaction.py` 共享模块，覆盖 6 种 secret 模式） | 3-4 天 | 高 |
| PreToolUse guard 改为 fail-closed（JSON 解析失败返回 block） | 0.5 天 | 高 |
| 各模块统一导入中央常量层 | 1-2 天 | 中 |

## 快速赢取

以下改进可在 2-2.5 周内完成，直接解决最紧迫的 bounded 差距：

1. **`_runtime_bounds.py`**：定义 `HOOK_TIMEOUT_S`, `MAX_OUTPUT_BYTES`, `MAX_ERROR_MSG`, `MAX_EVENT_PAYLOAD` 等常量
2. **`_redaction.py`**：将 `_redact_api_keys()` 升级为覆盖 URL 凭证、Bearer token、env secret、known token formats 的共享模块
3. **Guard fail-closed**：`pretooluse_guard.py` 解析失败时返回 `{"decision":"block","reason":"invalid input: fail-closed"}`

## 关联

- 对比文档：oh-my-cli 有限性设计分析文档（bounded-design.md）
- 差距总结：oh-my-cli 工程对比分析文档（gap-priorities.md）→ G-07-1, G-07-2, G-07-3, G-07-4
- 跨维度交叉差距：系统性边界 vs 局部边界（01:Gap4, 03:Gap5, 07:Gap1, 07:Gap4）
- 相关决策：D-010（健壮性修复策略，与本决策互补）

## Truth Basis

### Source Refs
- memory/docs/plans/PLAN-STATUS.md

### Authority Refs
- memory/kb/global/truth-model.md

### Evidence Refs
- tests/test_guard_fail_closed.py
- memory_core/tools/_guard_classify.py

### Conflict Status
- resolved
