> **⚠️ ARCHIVED**: 此文档描述的是历史版本的结构和流程（如 `workspace/tools/`、`branch-1/branch-2` 工作流）。
> 当前代码已迁移到 `memory_core/tools/`，默认分支为 `main`。本文档保留作为参考，不代表当前实现。

---

# TASK_CARD_TEMPLATE — 主线程任务卡模板

## 概述

本模板定义主线程如何通过 Projects URL 接收任务、dispatch 到子代理、并最终验收 closure 的完整流程。

---

## 一、用户输入模板

用户通过 Projects URL 提交任务时，任务卡应包含以下字段：

```markdown
## 任务卡

- **任务 ID**：T-{{ID}}
- **标题**：{{TITLE}}
- **描述**：{{DESCRIPTION}}
- **优先级**：{{PRIORITY}}  # P0 (紧急) | P1 (高) | P2 (标准) | P3 (低)
- **标签**：{{TAGS}}  # dev | fix | refactor | test | review | ops
- **Projects URL**：{{PROJECTS_URL}}
- **关联 Issue**：{{ISSUE_IDS}}
- **期望交付物**：{{DELIVERABLES}}
- **验收标准**：{{ACCEPTANCE_CRITERIA}}
- **约束条件**：{{CONSTRAINTS}}
```

---

## 二、主线程读卡流程

主线程收到任务卡后，按以下步骤处理：

### 步骤 1：解析任务卡

1. 从 Projects URL 或 Issue 中提取任务卡字段
2. 验证必填字段完整（ID、标题、描述、优先级、验收标准）
3. 确定任务类型（dev/fix/refactor/test/review/ops）

### 步骤 2：创建 branch-2

```bash
# 从 branch-1 创建新任务分支
git checkout branch-1
git pull origin branch-1
git checkout -b branch-2/{{TASK_ID}}-{{SLUG}}
```

### 步骤 3：构建 Dispatch Prompt

使用 [DISPATCH_TEMPLATE.md](./DISPATCH_TEMPLATE.md) 构建子代理 dispatch prompt，包含：
- 仓库路径
- 工作分支（branch-2）
- 文件范围
- 验收标准
- 写入边界

### 步骤 4：Dispatch 到子代理

- 子代理模型固定为 `gpt-5.4-mini`
- 发送 dispatch prompt + 任务卡上下文
- 记录 dispatch 时间戳

### 步骤 5：等待子代理回报

子代理完成后返回：
- 完成报告
- 变更文件列表
- residue 报告（如有）
- 测试/验证结果

---

## 三、子代理任务拆分规则

子代理收到任务后，如需进一步拆分：

1. **原子性原则**：每个子任务应能独立验证
2. **依赖顺序**：有依赖的子任务按 DAG 排序
3. **最大粒度**：单个子任务不超过 200 行代码变更
4. **拆分记录**：在 `.memory/TASKS.md` 中记录子任务清单

拆分后，子代理按顺序执行每个子任务，并在完成报告中列出所有子任务状态。

---

## 四、Acceptance / Closure 规则

### 验收前置条件

子代理回报后，主线程必须验证：

- [ ] 所有变更在 branch-2 上，未触碰 branch-1
- [ ] 变更文件在允许的文件范围内
- [ ] 验收标准全部满足
- [ ] 测试通过（如适用）
- [ ] 无未解决的 residue 或 residue 已记录
- [ ] 代码符合 CANONICAL.md 规范

### 验收通过 → Closure

1. 主线程在 branch-2 上执行最终审查
2. 合并 branch-2 → branch-1
3. Push branch-1 到 remote
4. 删除 branch-2
5. 更新任务状态为 `completed`
6. 记录 closure 时间戳

### 验收不通过 → Rejection

1. 主线程记录不通过原因
2. 将 residue 反馈给子代理
3. 子代理在 branch-2 上修复
4. 重新回报，进入验收循环

### Residue 处理

- **P0/P1 residue**：必须在当前 cycle 内修复
- **P2 residue**：可记录为 follow-up task
- **P3 residue**：可记录为技术债

Residue 格式：
```
[RESIDUE] {优先级} | {描述} | {建议修复方案} | {是否阻塞验收}
```

---

## 五、状态流转

```
pending → dispatched → in_progress → review → accepted → merged → closed
                                       ↓
                                   rejected → in_progress (retry)
```

| 状态 | 说明 |
|------|------|
| pending | 任务卡已创建，等待 dispatch |
| dispatched | 已发送给子代理 |
| in_progress | 子代理正在执行 |
| review | 子代理已回报，等待验收 |
| accepted | 验收通过，准备合并 |
| rejected | 验收不通过，需修复 |
| merged | 已合入 branch-1 |
| closed | 已完成并清理 |
