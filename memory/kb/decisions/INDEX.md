# Decision Records Index

> Decision records document architectural and operational decisions
> made during the project lifecycle.

## Files

| File | Summary |
|------|---------|
| `2026-08-17-mission-async-merge-decoupling.md` | mission 会话与 CI/合并流程解耦（异步合并纪律，门禁零削弱） |
| `D-002-gateway-adapter-overengineering.md` | gateway adapter 注入模式属于过度工程 |
| `d-002-ci-pytest-strategy.md` | pytest 版本策略与 CI 缓存治理 |
| `D-003-audit-verification-refactor-basis.md` | 基于三核交叉核查的重构决策基线 |
| `D-004-v5-dplus-refactor-completion.md` | v5 D+ 函数全量拆解完成（24 函数 CC>=21 → CC<=20，radon D+ 归零） |
| `D-005-mypy-type-safety-completion.md` | mypy 183→0 类型安全加固完成（strict 模式全量通过） |
| `D-006-python-version-pin-314.md` | Python 版本锁死到 3.14 单版本（superseded by D-008） |
| `D-007-doc-routing-engine.md` | 文档分类规则引擎升级（路由表 + guard 拦截 + CI 校验三层强制执行） |
| `D-008-python-version-rollback-312.md` | Python 版本从 3.14 回滚到 3.12（稳定性问题 + 平台标准化） |
| `D-009-lifecycle-event-sharding.md` | 生命周期事件按项目分片存储（events.jsonl → projects/{id}/events/{date}.jsonl） |
| `D-010-lifecycle-robustness-fixes.md` | 生命周期工具健壮性修复策略（防御性编程 + 可观测性 + 优雅降级） |
| `D-011-bounded-everything-architecture.md` | Bounded Everything 作为架构哲学（运行时边界常量层 + 共享 redaction + fail-closed） |
| `D-012-evolution-capability-tech-debt.md` | 工程进化能力——技术债跟踪（四层进化基础设施，待 D-011 完成后讨论） |

## Process

1. New decisions are added as individual markdown files
2. Each decision file follows the standard template
3. Decisions are indexed here with their current status
