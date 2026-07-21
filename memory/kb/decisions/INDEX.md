# Decision Records Index

> Generic template — populated by memory-core default adapter.
> This file tracks decision records for the default adapter.

## Purpose

Decision records document architectural and operational decisions
made during the project lifecycle.

## Decision Catalog

| ID | Title | Status | Date |
|----|-------|--------|------|
| D-001 | Default adapter initialization | accepted | 2026-05-10 |
| D-002 | gateway adapter 注入模式属于过度工程 | accepted（暂不清理） | 2026-07-18 |
| D-002b | pytest 版本策略与 CI 缓存治理 | accepted | 2026-06-02 |
| D-003 | 基于三核交叉核查的重构决策基线 | accepted | 2026-07-19 |
| D-004 | v5 D+ 函数全量拆解完成（24 函数 CC>=21 → CC<=20，radon D+ 归零） | accepted | 2026-07-20 |
| D-005 | mypy 183→0 类型安全加固完成（strict 模式全量通过） | accepted | 2026-07-21 |
| D-006 | Python 版本锁死到 3.14 单版本（CI 矩阵缩减 75%，删除 ~225 行兼容代码） | accepted | 2026-07-22 |

## Process

1. New decisions are added as individual markdown files
2. Each decision file follows the standard template
3. Decisions are indexed here with their current status
