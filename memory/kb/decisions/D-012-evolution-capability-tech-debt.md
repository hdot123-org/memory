# D-012: 工程进化能力——技术债跟踪

> **状态**：技术债（待后续讨论）
> **日期**：2026-08-03
> **来源**：oh-my-cli 对比分析 + 多模型验证（Qwen/GLM/Kimi 三模型共识）

## 背景

oh-my-cli 通过四个互锁系统实现自主进化：

1. **Contract-Driven Extension**——新能力通过声明式契约加入，不改核心代码
2. **Bounded Everything**——每个操作继承 timeout/size/fail-closed
3. **Confidence Infrastructure**——三层测试 + 确定性 fake provider
4. **Evolution Evidence**——交付证据链产出 ship/hold/no-ship

memory-core 当前是反应式进化：发现问题 → 手动打补丁。没有系统让进化变得主动和安全。

## 已确认的行动（D-011 覆盖）

以下已作为 D-011 的实施项启动，属于第二层"安全地板"：

- [ ] Guard fail-closed 改造（3 处 fail-open 修复）
- [ ] 共享 `_redaction.py` 统一脱敏模块
- [ ] Hook 返回格式迁移到 Factory 官方 `hookSpecificOutput.permissionDecision`

## 未启动的技术债（本决策跟踪）

### 第一层：协议进化能力

- 将 `_COMPAT_MATRIX` 从 14 行硬编码改为版本范围声明（`>=0.4.0` → `factory-hooks-v1`）
- 增加 Factory hook 能力探测：运行时检查 Factory 支持哪些 hook 事件和返回格式
- 目标：Factory 发布新 hook 能力时，memory-core 只需更新版本范围声明

### 第三层：信心基础设施

- 测试分层：unit（纯函数秒级）/ integration（hook 管线模拟 Factory payload）/ smoke（构建验证）
- Fake Factory 环境：模拟 Factory hook 调用（payload 格式、环境变量、退出码语义）
- Hook 事件 replay：录制真实 hook 事件序列，回放做回归测试

### 第四层：进化审计

- 变更证据日志：每次代码变更记录"改了什么、为什么、什么测试验证"
- Hook 健康信号：组合 test 结果 + hook 超时率 + guard block/allow 比例
- 摘要完整性校验：对关键输出做 SHA-256 校验

## 讨论前提

在讨论本技术债之前，需完成 D-011 的三个实施项。实施结果将作为评估第一层和第三层投入产出比的依据。

## 多模型验证支撑

三模型独立验证（Qwen 3.7 Plus / GLM-5.2 / Kimi K2.5）确认：
- 原分析列的 10 个"高优"差距中，只有 P3（运行时边界）和 P4（redaction）经受住了三模型审查
- G-07-4（fail-closed）被原分析排在 P25（中优），但三模型一致认为应提升到 Top 3
- 自治循环、session 压缩、delivery brief 等 agent 能力不适用于 hook 库

详见 oh-my-cli 工程对比分析文档（gap-priorities.md）。

## Truth Basis

### Source Refs
- memory/docs/plans/PLAN-STATUS.md

### Authority Refs
- memory/kb/global/memory-system.md

### Evidence Refs
- tests/test_validate_memory_system.py
- memory_core/tools/validate_memory_system.py

### Conflict Status
- resolved
