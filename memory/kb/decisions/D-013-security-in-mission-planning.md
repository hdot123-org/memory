# D-013: 编排器必须将安全要求前置到任务定义阶段

> **状态**：生效中
> **日期**：2026-08-09
> **来源**：两个反复出现的 session 问题（a1ad229d 攻击者 vs 实现者分歧；1396a48a mission 编排中安全缺位）

## 背景

### 反复出现的问题模式

在使用 Factory Mission 编排时，反复出现同一类问题：

1. 编排器（droid）规划任务，定义 expectedBehavior 和 validation-contract
2. Worker 完美执行，功能正确，通过 scrutiny + user-testing 验证
3. Mission 标记"完成"
4. 事后手动跑 opus-auditor（攻击者视角），发现安全问题
5. 实现者视角说"没问题"，攻击者视角说"有问题" → 争论循环

### Factory 平台的结构性缺失

经 Factory 官方文档（88 页，1.34MB）完整检索确认：

- Mission 验证系统只有 scrutiny（代码质量）+ user-testing（功能正确性），**没有安全验证**
- "security" 一词在整个 Missions 文档中零出现
- 不存在 security gate / security milestone 概念
- `/security-review` 是独立的可选 skill，与 Mission 编排无原生集成

**这意味着：Factory 的 Mission 系统在设计上，安全不在"完成"的定义里。**

### 根因

不是工具不够强，不是 droid 没有上下文，不是 Factory 有 bug。

**根因是编排器（我）在规划任务时，没有把安全要求写进任务定义。**

## 决策

### 编排器铁律：安全前置

**从本决策生效起，编排器在规划任何 Mission 时，必须执行以下安全前置步骤：**

#### 1. validation-contract.md 必须包含安全断言

每个涉及以下攻击面的 feature，必须有对应的 `VAL-SEC-xxx` 断言：

| 攻击面 | 必须断言的内容 |
|--------|---------------|
| 用户输入 | 所有外部输入经过校验/转义，无注入路径 |
| 认证/授权 | 权限检查不可绕过，session 不可伪造 |
| 数据存储 | 敏感数据加密存储，无明文泄露 |
| 外部调用 | 外部 API 响应经过校验，无 SSRF/重定向风险 |
| 文件操作 | 路径不可遍历，文件类型/大小有限制 |
| 并发操作 | 无竞态条件，锁不可死锁 |

**对于不涉及上述攻击面的纯内部 feature**，validation-contract.md 必须显式标注：

```
### VAL-SEC-XXX: 安全适用性声明
本 feature 不涉及外部输入/认证/数据存储/外部调用。
攻击面评估：无。
```

#### 2. features.json 的 expectedBehavior 必须包含安全要求

涉及安全面的 feature，expectedBehavior 必须包含至少一条安全行为：

```json
"expectedBehavior": [
  "...功能行为...",
  "所有外部输入经过 [校验方式]，不存在注入/越权/信息泄露路径"
]
```

#### 3. AGENTS.md 必须包含安全约束

Mission 的 AGENTS.md 必须在 Mission Directives 中声明：

```markdown
## Mission Directives

**安全要求:**
- Worker 必须对所有外部输入执行校验（不可信任任何输入）
- Worker 必须在实现完成后自检：是否存在注入/越权/信息泄露路径
- 如果 Worker 无法确认某个安全断言通过，必须在 handoff 中标记为 discoveredIssue
```

#### 4. fulfills 必须引用安全断言

涉及安全面的 feature，其 `fulfills` 数组必须包含对应的 `VAL-SEC-xxx` ID。

这样 user-testing-validator 会验证这些安全断言。

## 适用范围

本决策适用于**所有未来的 Mission 规划**，不限项目。

编排器 session（包括其他 droid 作为编排器）启动时必须读取本决策。

## 与 Factory 平台限制的关系

本决策是在 Factory 平台**没有内置安全验证**的前提下，由编排器层手动补齐的方案。

- 不修改 Factory 平台代码
- 不依赖 Factory 新功能
- 利用现有机制（validation-contract + features.json + AGENTS.md）将安全嵌入任务定义
- 如果 Factory 未来内置 security validation，本决策可以简化或废弃

## 验证

本决策是否有效，取决于编排器是否严格执行。验证方式：

1. Mission 完成后，手动跑 opus-auditor，检查是否发现全新安全问题（非已知权衡）
2. 如果 auditor 发现的问题是 expectedBehavior 和 VAL-SEC 已覆盖的 → 说明 worker 违反了要求，需要加强 AGENTS.md 约束
3. 如果 auditor 发现的问题是 VAL-SEC 未覆盖的 → 说明编排器在规划时漏了攻击面，需要更新本决策的攻击面清单
4. 如果 auditor 没有发现新问题 → 决策生效

## 四层防御架构（2026-08-09 补充）

经 Opus 5 / GLM-5.2 / Qwen 3.7 三模型交叉验证，确认仅靠规划前置不够，需要四层纵深防御：

### 第 0 层：规划前置（本决策的核心）
- 编排器在 validation-contract.md 写 VAL-SEC-xxx 安全断言
- features.json 的 expectedBehavior 写安全行为
- AGENTS.md 写 worker 安全约束
- 模板文件：`docs/templates/validation-contract-security-template.md` 等

### 第 1 层：本地快检（PreToolUse hook，确定性，<2s）
- `~/.factory/hooks/security-gate.sh`
- gitleaks 式正则（密钥）+ 危险模式（eval/exec/shell=True）+ 敏感文件检测
- fail-CLOSED（超时 deny）
- 已实施

### 第 2 层：服务端强审计（CI，不可绕过）
- `droid-review.yml` 改用 `pull_request_target`（PR 无法关闭自己的审查）
- `check_droid_review.sh` 白名单化：仅 `success` 放行
- `enforce_admins: true`（堵死 --admin 旁路）
- 安全审查模型升级为 claude-opus（强于 worker 模型）
- 已实施

### 第 3 层：检测与跟进（PostToolUse，不阻断）
- `~/.factory/hooks/security-detect.sh`
- 异步扫描 + additionalContext 注入
- 安全 TODO/FIXME 提醒 + debug 代码检测
- 已实施

### 已修复的现有漏洞
1. `enforce_admins: true` + 删除 AGENTS.md 中的 --admin 例外
2. `droid-review.yml` 改用 `pull_request_target`
3. `auto-merge.yml` 按 SHA 固定
4. `check_droid_review.sh` 白名单化

### 验证结果
三模型评分：Opus 3/10 → 重构后预期 7-8/10。核心发现：
- hook 内跑 LLM 物理上不可行（5s 预算 vs 60-1200s 扫描）
- 正确的第一道门禁是确定性快速静态扫描
- 深度审计必须在 CI 端（异步、不可绕过）
