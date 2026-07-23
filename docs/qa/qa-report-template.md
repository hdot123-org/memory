# QA Report - memory-core

> **日期**: YYYY-MM-DD
> **版本**: v0.9.0
> **触发**: PR #XXX / Nightly / Manual
> **运行环境**: ubuntu-latest, Python 3.14

---

## 1. 执行摘要

| 指标 | 值 | 目标 | 状态 |
|------|----|------|------|
| 总测试数 | XXX | - | - |
| 通过 | XXX | - | PASS/FAIL |
| 失败 | XXX | 0 | PASS/FAIL |
| 跳过 | XXX | - | - |
| 覆盖率 | XX.X% | 80% | PASS/FAIL |
| 执行时间 | XXXs | - | - |

**总体评估**: PASS / FAIL / 有条件通过

---

## 2. CLI 端到端测试

### Layer 1: 冒烟测试

| CLI 命令 | --help | 无参数 | 状态 |
|----------|--------|--------|------|
| memory-init | PASS | PASS | - |
| memory-migrate | PASS | PASS | - |
| memory-validate | PASS | PASS | - |
| memory-hook-gateway | PASS | PASS | - |
| memory-factory-hooks | PASS | PASS | - |
| memory-consistency-check | PASS | PASS | - |
| memory-audit-layout | PASS | PASS | - |
| memory-plan-residue | PASS | PASS | - |
| memory-apply-residue-plan | PASS | PASS | - |
| memory-ownership | PASS | PASS | - |
| memory-verify-consumer | PASS | PASS | - |
| memory-integrity-resign | PASS | PASS | - |
| memory-sync-versions | PASS | PASS | - |
| memory-audit-daily | PASS | PASS | - |
| memory-promote | PASS | PASS | - |

### Layer 2: 功能测试

| 测试场景 | 结果 | 备注 |
|----------|------|------|
| memory-init 全新创建 | PASS | 结构完整 |
| memory-init --dry-run | PASS | 无写入 |
| memory-init --mode update | PASS | managed blocks 更新 |
| memory-init --mode repair | PASS | 缺失文件重建 |
| memory-validate 合法布局 | PASS | 退出码 0 |
| memory-validate 缺失文件 | PASS | 正确报错 |
| memory-validate --json | PASS | JSON 结构正确 |
| memory-migrate 0.7.0->0.8.0 | PASS | [global_kb] 注入 |
| memory-migrate 幂等性 | PASS | 不重复注入 |
| memory-audit-layout --json | PASS | - |
| memory-ownership --json | PASS | - |

### Layer 3: 健壮性测试

| 测试场景 | 结果 |
|----------|------|
| 不存在的目标目录 | PASS |
| 权限不足 | PASS |
| 并发执行 | PASS |
| 特殊字符路径 | PASS |

---

## 3. 覆盖率分析

### 总体覆盖率

| 指标 | 值 |
|------|----|
| 行覆盖率 | XX.X% |
| 分支覆盖率 | XX.X% |
| 总行数 | XXXX |
| 覆盖行数 | XXXX |
| 未覆盖行数 | XXXX |
| 达到 80% 目标还需 | XXX 行 |

### 优先级分布

| 优先级 | 描述 | 模块数 |
|--------|------|--------|
| P0 | 核心模块 < 50% | X |
| P1 | 核心模块 < 70% | X |
| P2 | 任意模块 < 40% | X |
| P3 | 任意模块 < 30% | X |

### Top-10 未覆盖模块

| 模块 | 覆盖率 | 未覆盖行 | 核心 | 优先级 |
|------|--------|----------|------|--------|
| xxx | XX.X% | XXX | YES | P0 |
| ... | ... | ... | ... | ... |

### 零覆盖模块

| 模块 | 总行数 |
|------|--------|
| xxx | XXX |

---

## 4. Hook 生命周期测试

| 事件链路 | 测试数 | 通过 | 失败 |
|----------|--------|------|------|
| session-start | X | X | 0 |
| prompt-submit | X | X | 0 |
| PreToolUse guard | X | X | 0 |
| session-end | X | X | 0 |
| 遥测管道 | X | X | 0 |

### 关键发现

- (无 / 描述发现的任何问题)

---

## 5. 业务策略测试

| 规则组 | 测试数 | 通过 | 失败 |
|--------|--------|------|------|
| 路径分类 | X | X | 0 |
| 规则执行 | X | X | 0 |
| Scope 解析 | X | X | 0 |
| PreToolUse 集成 | X | X | 0 |

### Marker 常量覆盖

- 已覆盖: XX/20 MKR_* 常量
- 未覆盖: (列出未覆盖的 marker)

---

## 6. 遥测与完整性测试

| 测试组 | 测试数 | 通过 | 失败 |
|--------|--------|------|------|
| 本地 JSONL | X | X | 0 |
| PostHog 同步 | X | X | 0 |
| Manifest 签名 | X | X | 0 |
| Manifest 验证 | X | X | 0 |
| 重签名 | X | X | 0 |

---

## 7. Schema 迁移测试

| 测试组 | 测试数 | 通过 | 失败 |
|--------|--------|------|------|
| 版本迁移 | X | X | 0 |
| 回滚安全 | X | X | 0 |
| Schema 验证 | X | X | 0 |
| 版本同步 | X | X | 0 |
| Hook 升级 | X | X | 0 |

---

## 8. 边界与安全测试

| 测试组 | 测试数 | 通过 | 失败 |
|--------|--------|------|------|
| Source-repo-readonly | X | X | 0 |
| Denylist | X | X | 0 |
| Pollution guard | X | X | 0 |
| 文件安全 | X | X | 0 |
| 证据引用 | X | X | 0 |

### 安全扫描结果

| 扫描项 | 结果 |
|--------|------|
| check_boundary.py | PASS |
| repo_health_check.sh | PASS |
| pip-audit | PASS (0 vulnerabilities) |
| gitleaks | PASS |
| 硬编码路径检查 | PASS |

---

## 9. 回归矩阵

### 按模块组汇总

| 模块组 | 总测试 | 通过 | 失败 | 跳过 | 覆盖率 |
|--------|--------|------|------|------|--------|
| 核心引擎 | XX | XX | 0 | X | XX% |
| CLI 工具 | XX | XX | 0 | X | XX% |
| 业务策略 | XX | XX | 0 | X | XX% |
| 审计与布局 | XX | XX | 0 | X | XX% |
| 遥测与完整性 | XX | XX | 0 | X | XX% |
| 配置与 Schema | XX | XX | 0 | X | XX% |
| 工具与辅助 | XX | XX | 0 | X | XX% |

---

## 10. 风险评级

### 发现的问题

| 编号 | 严重程度 | 模块 | 描述 | 建议 |
|------|----------|------|------|------|
| 1 | Critical | xxx | xxx | xxx |
| 2 | High | xxx | xxx | xxx |
| 3 | Medium | xxx | xxx | xxx |
| 4 | Low | xxx | xxx | xxx |

### 覆盖率风险

| 模块 | 当前覆盖率 | 目标 | 风险 | 计划 |
|------|-----------|------|------|------|
| memory_hook_gateway | XX% | 80% | High | 补充 X 个测试 |
| business_policy_checks | XX% | 80% | High | 补充 X 个测试 |
| ... | ... | ... | ... | ... |

---

## 附录

### 环境信息

- Python: 3.14.x
- pytest: 8.x
- ruff: 0.11.x
- mypy: 1.10+
- OS: Ubuntu 22.04 (GitHub Actions)

### 工件

- CLI E2E 结果: qa-cli-e2e-results.json
- 覆盖率 XML: coverage.xml
- 覆盖率缺口: qa-coverage-results.json
