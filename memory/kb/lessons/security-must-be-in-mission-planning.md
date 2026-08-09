# Mission 编排中安全必须前置到任务定义阶段

**日期**: 2026-08-09
**严重性**: P1（问题反复出现，根因为系统性缺失）
**状态**: 已确认根因，D-013 决策已记录

## 问题描述

使用 Factory Mission 编排时，安全审查始终在 mission "完成"之后才进行（手动跑 opus-auditor）。导致：

1. Worker 实现代码功能正确但存在安全漏洞
2. Mission 验证通过（scrutiny + user-testing 都不检查安全）
3. 事后 auditor 发现问题
4. 实现者视角和攻击者视角产生分歧，无仲裁标准

## 根因

**Factory Mission 系统在设计上不包含安全验证维度。**

经官方文档完整检索确认：
- Mission 验证只有 scrutiny（代码质量）+ user-testing（功能正确性）
- "security" 一词在整个 Missions 文档中零出现
- `/security-review` 是独立可选 skill，与 Mission 编排无原生集成

**但编排器（droid）可以在任务定义阶段手动将安全嵌入：**
- validation-contract.md 写 VAL-SEC-xxx 安全断言
- features.json 的 expectedBehavior 写安全行为要求
- AGENTS.md 写安全约束让 worker 遵守
- fulfills 引用 VAL-SEC 让 user-testing-validator 验证

## 教训

**安全不是审计阶段的工作，是规划阶段的工作。**

如果安全要求在任务定义时就不存在，worker 不会主动考虑安全，验证器不会检查安全，auditor 必然在事后发现问题。

**编排器的职责是在规划阶段就把安全要求写进每一个任务定义。**

## 解决方案

见 D-013 决策记录：编排器必须将安全要求前置到任务定义阶段。
