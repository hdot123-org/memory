# 死代码清理 + Python 3.14 版本锁死

> Date: 2026-07-22
> Status: COMPLETED
> PRs: #184 (Python 3.14 锁死), #185 (死代码清理)
> Validation: 21/21 断言通过

## 概述

清理 memory-core 中经三模型交叉验证确认的死代码（~655 行），同时完成 Python 3.14 版本锁死。两个 milestone 共 7 个 feature，21 个验证断言全部通过。

## Phase 1: Python 版本锁死（PR #184, e04ceb7）

### 配置锁死

| 配置项 | 旧值 | 新值 |
|--------|------|------|
| requires-python | `>=3.9` | `>=3.14` |
| CI test matrix | 3.9/3.10/3.11/3.12 | 3.14 only |
| mypy python_version | `"3.9"` | `"3.14"` |
| classifiers | 3.9~3.13 | 3.14 only |
| tomli 条件依赖 | `"tomli>=2.0; python_version<'3.11'"` | 删除 |

### 兼容代码清理

| 类别 | 文件数 | 删除行数 |
|------|--------|---------|
| tomli 条件导入 | 12 (memory_core + tests + scripts) | ~35 |
| `from __future__ import annotations` | ~190 | ~190 |
| typing 旧式注解 (Optional/List/Dict) | 6 | ~6 删 + ~15 替换 |
| F821 自引用修复 | 5 | (修复合并到上面) |

### 背景

SessionEnd hook 在 3.14 上的 argparse 报错暴露了 CI 与 runtime 版本脱节。详见 D-006。

## Phase 2: 死代码清理（PR #185, 53ca9b1）

### 删除清单

| 删除项 | 行数 | 类型 |
|--------|------|------|
| observability.py | 283 | 完整文件（5 class，0 生产 import） |
| resilient_orchestrator.py | 67 | 完整文件（依赖不存在，0 生产引用） |
| auto_capture.py | 80 | 完整文件（只有 capture_candidates） |
| CodexDelegate | ~33 | 部分删除（memory_hook_impls.py） |
| ClaudeDelegate | ~93 | 部分删除 |
| PathUtilsImpl | ~31 | 部分删除 |
| 4 个 error class | ~19 | 部分删除（_rule_errors.py） |
| LegalContractChecker | ~12 | 部分删除（business_policy_checks.py） |
| safe_capture | ~35 | 部分删除（telemetry_bridge.py） |
| 关联测试文件 | ~200 | 5 个 test 文件删除 |
| **合计** | **~655 + ~200 测试** | |

### 重构

- `_hmac_sha256`: sign_project/sign_project_incremental 从内联 `_hmac.new()` 改用 helper（从死代码变活代码）
- `vulture_whitelist.py`: 移除 11 个已删 symbol 条目
- scripts/ tomli 残留清理: repo_health_check.sh + test_full_integration.py

### 死代码来源

REF-001 "规则引擎统一与LLM隔离设计"（2026-07-16）规划了 7 阶段 strangler fig 迁移。Phase 1 scaffold 创建了模块/class，但 Phase 7 wiring 从未执行。D-002 决定优先级转向 radon D+/mypy，遗留的 abandoned scaffold 成为死代码。

## 质量验证

| 门禁 | 结果 |
|------|------|
| mypy | 0 errors (69 source files) |
| pytest | 3046 passed, 3 skipped |
| ruff | All checks passed |
| radon D+ | 0 |
| validation assertions | 21/21 passed |

## 遗留 Tech Debt

| 项目 | 严重度 | 说明 |
|------|--------|------|
| os.chdir leak flaky test | non-blocking | test_business_policy_paths.py 的 os.chdir 不恢复导致 pytest-randomly 下版本断言 flaky |
| stale doc references | non-blocking | docs/typing-tech-debt.md 等仍引用已删模块 |
| capture_candidates | deferred | 待 Droid-native API 重建 |
