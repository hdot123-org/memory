# 混沌测试加固 backlog（后置待办登记）

> 登记日期：2026-08-14
> 状态：open（低优先级，随日常迭代补齐）
> 来源：第一层&第二层补强完成度审计（2026-08-14）

## 背景

2026-08-14 的"第一层&第二层补强完成度审计"发现 **2.2 故障注入测试覆盖不完整**。
经评估为**低优先级后置项**，不阻塞开发与发版节奏。

本登记的目的：把原本只存在于 session 上下文的测试加固路线图落盘，
避免未来 mission 规划再次遗漏（或审计时误报为缺失）。

## 待办项（2 项）

### a) 网络中断注入测试

- **内容**：evolution scanner / adapter 子进程网络超时的 mock 测试
- **现状**：目前无覆盖

### b) 畸形 Unicode 控制符输入测试

- **内容**：含控制字符的输入文件不导致扫描器崩溃
- **现状**：目前无覆盖

## 已有覆盖说明（避免未来审计再误报为缺失）

以下场景**已有测试覆盖**，审计时不应再报告为缺失：

| 场景 | 覆盖测试 |
|------|---------|
| flock 并发 | `tests/test_p2_migrations_log_flock.py` |
| >1MB 超长行 | `tests/test_logger_budget_scan.py` |
| oversized strings 边界 | `tests/test_business_policy_smoke.py` |
| malformed JSON | `tests/test_logger_budget_scan.py` |

## 优先级

低。随日常迭代补齐，不单独立项、不阻塞发版。

## 关联

- 同日（2026-08-14）批准并实施的 **suppress.json expires 过期机制**
  （对应审计缺口 1.2）位于 `feat/suppress-expiry` 分支。

## Truth Basis

### Source Refs

- 2026-08-14 session：第一层&第二层补强完成度审计结论（缺口 2.2）
- 审计缺口 1.2 实施分支：`feat/suppress-expiry`

### Authority Refs

- /Users/busiji/memory/project-map/INDEX.md

### Evidence Refs

- tests/test_p2_migrations_log_flock.py
- tests/test_logger_budget_scan.py
- tests/test_business_policy_smoke.py
- tests/test_suppression_expiry.py（feat/suppress-expiry 分支，已随 commit 680ffdf 提交）

### Conflict Status

- resolved
