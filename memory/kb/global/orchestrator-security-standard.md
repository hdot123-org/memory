# 编排器安全前置标准

> 本文件是全局操作标准，所有编排器 session（droid 作为 orchestrator）启动时必须读取。

## 核心原则

**安全是规划阶段的工作，不是审计阶段的工作。**

编排器在规划任何 Mission 时，必须将安全要求嵌入任务定义的三个层面。

## 三层安全嵌入（D-013）

### 第一层：validation-contract.md — 安全断言

每个 feature 必须有安全断言。涉及攻击面的 feature 写 `VAL-SEC-xxx`，不涉及的写显式安全适用性声明。

攻击面清单（必须断言）：
- 用户输入 → 注入路径
- 认证/授权 → 权限绕过
- 数据存储 → 明文泄露
- 外部调用 → SSRF/重定向
- 文件操作 → 路径遍历
- 并发操作 → 竞态/死锁

### 第二层：features.json — 安全行为

涉及安全面的 feature，expectedBehavior 必须包含至少一条安全行为描述，fulfills 必须引用对应的 VAL-SEC-xxx。

### 第三层：AGENTS.md — 安全约束

Mission 的 AGENTS.md 必须声明 worker 的安全义务：
- 对所有外部输入执行校验
- 实现完成后自检注入/越权/泄露路径
- 无法确认安全断言通过时，handoff 中标记 discoveredIssue

## 验证闭环

```
规划阶段：编排器写入 VAL-SEC + expectedBehavior 安全要求
    ↓
实现阶段：worker 遵守 AGENTS.md 安全约束
    ↓
验证阶段：user-testing-validator 验证 VAL-SEC 断言
    ↓
审计阶段（可选）：opus-auditor 只应发现已知权衡，不应发现全新漏洞
```

如果 auditor 发现了全新问题，说明编排器规划时漏了攻击面 → 更新本文件的攻击面清单。

## 参考文件

- D-013 决策记录：`memory/kb/decisions/D-013-security-in-mission-planning.md`
- 教训：`memory/kb/lessons/security-must-be-in-mission-planning.md`
