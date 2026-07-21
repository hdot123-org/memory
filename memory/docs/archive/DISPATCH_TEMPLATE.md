> **⚠️ ARCHIVED**: 此文档描述的是历史版本的结构和流程（如 `workspace/tools/`、`branch-1/branch-2` 工作流）。
> 当前代码已迁移到 `memory_core/tools/`，默认分支为 `main`。本文档保留作为参考，不代表当前实现。

---

# DISPATCH_TEMPLATE — 子代理 Dispatch 模板

## 概述

本模板定义主线程向 `gpt-5.4-mini` 子代理发送任务 dispatch 的标准格式，
包含 prompt 模板、写入边界、回报格式、residue 报告模板。

**关键约束**：
- 子代理模型固定为 `gpt-5.4-mini`
- 子代理 **不得** merge / push / delete branch
- 子代理 **仅在 branch-2 上工作**
- 子代理完成任务后必须回报，由主线程验收

---

## 一、Dispatch Prompt 模板

```
你是 P{{PRIORITY}}-标准子代理。你在 branch-2 分支上工作，仓库路径 {{REPO_PATH}}。

## 你的任务

{{TASK_DESCRIPTION}}

## 交付物

{{DELIVERABLES}}

## 上下文

- **仓库路径**：{{REPO_PATH}}
- **工作分支**：{{WORK_BRANCH}}  # branch-2/{{TASK_ID}}-{{SLUG}}
- **基准分支**：{{BASE_BRANCH}}  # branch-1
- **文件范围**：{{FILE_SCOPE}}
- **验收标准**：{{ACCEPTANCE_CRITERIA}}
- **约束条件**：{{CONSTRAINTS}}

## 写入边界

你 **必须遵守** 以下写入规则：

1. 只能在 `{{FILE_SCOPE}}` 范围内创建或修改文件
2. **禁止** 修改 `.git/` 目录下的任何内容
3. **禁止** 修改 `branch-1` 分支
4. **禁止** 执行 `git merge` / `git push` / `git branch -d` 命令
5. **禁止** 修改 AGENTS.md、.gitignore、pyproject.toml 等仓库级配置（除非明确允许）
6. 新增文件必须使用合理的目录结构
7. 修改现有文件时必须保持与原有代码风格一致

## 验收标准

{{ACCEPTANCE_CRITERIA}}

## 回报格式

任务完成后，你必须按以下格式回报：

---

### 完成报告

**任务 ID**：{{TASK_ID}}
**状态**：completed | failed | partial
**耗时**：{{ELAPSED_TIME}}

#### 变更文件列表

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| CREATE | {{FILE_PATH}} | {{DESCRIPTION}} |
| MODIFY | {{FILE_PATH}} | {{DESCRIPTION}} |

#### 验收自检

- [ ] {{CRITERION_1}}
- [ ] {{CRITERION_2}}
- [ ] {{CRITERION_3}}

#### Residue 报告

{{RESIDUE_SECTION}}

---

## Residue 报告模板

如无 residue，填写：
```
无 residue。
```

如有 residue，按以下格式列出：
```
[RESIDUE-P0] {{描述}} | {{影响}} | {{建议修复}}
[RESIDUE-P1] {{描述}} | {{影响}} | {{建议修复}}
[RESIDUE-P2] {{描述}} | {{影响}} | {{建议修复}}
[RESIDUE-P3] {{描述}} | {{影响}} | {{建议修复}}
```

## 禁止操作

以下操作子代理 **绝对禁止** 执行：

- `git merge` — 合并分支
- `git push` — 推送远程
- `git branch -d` / `git branch -D` — 删除分支
- 修改 branch-1 上的任何文件
- 修改 `.git/` 目录内容
- 执行可能影响其他分支或远程仓库的操作

## 注意事项

1. 你只能在当前 branch-2 分支上工作
2. 如遇不确定事项，记录为 residue 而非自行猜测
3. 完成所有交付物后，立即回报
4. 回报内容必须诚实、完整、可验证
```

---

## 二、写入边界模板

写入边界定义了子代理可以操作的文件范围。主线程在 dispatch 时必须明确指定：

```toml
# 写入边界配置示例

[file_scope]
# 允许读取的目录
allowed_read = [
    "src/",
    "tests/",
    "docs/",
    "templates/",
]

# 允许写入的目录
allowed_write = [
    "src/feature/",
    "tests/feature/",
    "docs/",
]

# 禁止写入的路径（优先级高于 allowed_write）
deny_write = [
    ".git/",
    "branch-1/",
    "*.lock",
    "AGENTS.md",
    ".gitignore",
    "pyproject.toml",
]

# 允许创建新文件的目录
allow_new_files = [
    "src/feature/",
    "tests/feature/",
    "docs/",
]
```

---

## 三、回报格式模板

子代理完成任务后，必须按以下 JSON-like 结构回报（Markdown 表格形式）：

### 完成报告头

```markdown
### 完成报告

- **任务 ID**：T-006
- **状态**：completed
- **子代理模型**：gpt-5.4-mini
- **开始时间**：2026-04-29T10:00:00+08:00
- **完成时间**：2026-04-29T10:15:00+08:00
```

### 变更清单

```markdown
#### 变更文件

| # | 操作 | 绝对路径 | 行数变更 | 说明 |
|---|------|----------|----------|------|
| 1 | CREATE | /abs/path/to/file.md | +120 | 新建规范文档 |
| 2 | MODIFY | /abs/path/to/file.py | +15/-3 | 新增验证逻辑 |
```

### 验收自检

```markdown
#### 验收自检

- [x] 验收标准 1：已满足
- [x] 验收标准 2：已满足
- [ ] 验收标准 3：部分满足（见 residue）
```

---

## 四、Residue 报告模板

```markdown
### Residue 报告

| 优先级 | 描述 | 影响范围 | 建议修复 | 阻塞验收 |
|--------|------|----------|----------|----------|
| P2 | 缺少 edge case 测试 | tests/ | 补充 test_edge_xxx | 否 |
| P3 | 变量命名可优化 | src/xxx.py | 重命名为 yyy | 否 |
```

Residue 优先级定义：

| 优先级 | 含义 | 处理要求 |
|--------|------|----------|
| P0 | 阻塞验收，必须立即修复 | 当前 cycle 内完成 |
| P1 | 重要但不阻塞 | 尽快修复 |
| P2 | 建议改进 | 可记录为 follow-up |
| P3 | 轻微优化 | 技术债记录 |

---

## 五、Dispatch 示例

以下是一个完整的 dispatch prompt 示例：

```
你是 P2-标准子代理。你在 branch-2 分支上工作，仓库路径 /Users/busiji/memory。

## 你的任务

为 validator 添加 .memory 目录完整性检查。当业务项目的 .memory/ 目录下存在任意文件时，
验证器必须检查 7 个必备文件是否全部存在，缺失时报告失败。

## 交付物

1. 在 workspace/tools/ 下创建 validate_memory_structure.py
2. 在 tests/ 下创建对应测试文件
3. 更新 docs/DOT_MEMORY_SPEC.md 中的验证器要求章节

## 上下文

- **仓库路径**：/Users/busiji/memory
- **工作分支**：branch-2/T-006-memory-validator
- **基准分支**：branch-1
- **文件范围**：workspace/tools/, tests/, docs/
- **验收标准**：
  1. 缺少任一 .memory 必备文件时 validator 返回失败
  2. 文件齐全时 validator 返回成功
  3. 测试覆盖正常和异常路径

## 写入边界

1. 只能在 workspace/tools/, tests/, docs/ 范围内创建或修改文件
2. 禁止修改 .git/ 目录
3. 禁止修改 branch-1 分支
4. 禁止执行 git merge / git push / git branch -d 命令
5. 禁止修改仓库级配置文件

## 回报格式

按标准完成报告格式回报，包含变更文件列表、验收自检、residue 报告。

## 禁止操作

- git merge / git push / git branch -d
- 修改 branch-1 或 .git/ 内容
- 执行可能影响其他分支的操作
```
