# Hook 安全架构：PreToolUse 快检 + CI 深审

**日期**: 2026-08-09
**严重性**: P1
**状态**: 已实施四层防御

## 问题描述

Mission 编排中安全问题在事后才发现，实现者视角和攻击者视角反复冲突。

## 根因

1. Factory Mission 系统没有内置安全验证
2. 编排器规划任务时未将安全写入验收标准
3. CI 安全审查可被 PR 自身关闭（pull_request 事件）
4. enforce_admins: false 允许 --admin 绕过

## 关键教训

### 1. hook 内不能跑 LLM
PreToolUse hook 预算 10s（Factory 外层）/ 5s（guard 内层）。LLM 安全扫描需要 60-1200s。差距 2-3 个数量级。正确做法：hook 只做确定性快速静态扫描（<2s）。

### 2. 门禁不能被被约束方修改
PR 使用 `pull_request` 事件时，workflow 定义来自 PR head。PR 可以把 `automatic_security_review: true` 改为 `false`。必须用 `pull_request_target` 或 org 级 required workflow。

### 3. fail-open 是最危险的失败模式
现有 guard 超时后对非保护路径 fail-open（allow）。安全门禁必须 fail-closed。但 fail-closed + 超时 = 每次都阻断 → 死锁。解决方案：用确定性检查（不会超时）而非 LLM。

### 4. 三层验证比单层强审计更有效
- 第 0 层（规划前置）：消除根因
- 第 1 层（本地快检）：挡住低垂果实
- 第 2 层（CI 深审）：不可绕过的深度审计
- 第 3 层（异步检测）：检测漏网之鱼

### 5. 审查模型必须强于实现者
用同级模型审查自己产出的代码 = 自审偏差。安全审查固定使用 claude-opus，worker 用 qwen3.7-plus。

## 解决方案

见 D-013 决策记录。
