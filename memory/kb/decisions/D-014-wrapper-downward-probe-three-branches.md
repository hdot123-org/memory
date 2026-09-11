# D-014: Wrapper 向下探测三分支语义决策记录

## 决策背景

在处理非 git 目录包含嵌套 git 仓库的布局时，memory-core 的 wrapper 需要实施智能向下探测逻辑，以正确路由到适当的 git 仓库。这解决了 mencbo 事故的根本问题，其中会话在非 git 父目录启动，导致错误的记忆树创建。

## 决策内容

### 探测触发条件
向下探测仅在满足以下所有条件时激活：
1. `GIT_ROOT` 为空（向上归一化未命中）
2. `PROJECT_CWD` 目录无 `.git` 存在（dataless/不可读 .git 的真仓库不探测）
3. 无 consent 标记（外层 `memory/system` 内 `allow_non_git=true` → passthrough）
4. 非 `$HOME` 精确命中
5. 未设逃生口 env（`MEMORY_HOOK_DISABLE_DOWNWARD_PROBE` 未设置）

### 候选判定机制
1. **stat 门控**：检查子目录是否存在 `.git` 文件或目录（兼容 worktree/submodule）
2. **唯一候选时 rev-parse 确认**：仅在唯一有效候选时进行 `git -C rev-parse` 确认，避免悬空/损坏 .git 目录
3. **限制深度**：仅检查直接子目录，深度为 1

### 三分支语义
- **恰好 1 个有效仓库** → `PROJECT_CWD` 指向该子仓库；成功路由不记日志无 stderr
- **0 个候选** → noop（`{}` + exit 0 + session-start 记日志）
- **≥2 个候选** → noop + stderr 恰一行诊断（含全部候选 + 出路提示）+ session-start 记 errors.log

### 用户裁决 1：歧义处理
对于歧义形态（≥2 仓库），采取 noop + stderr 一行诊断的方式，而不是尝试猜测或选择。用户可以通过以下方式解决问题：
1. 进入具体仓库目录
2. 在项目根放置 `memory-project.toml` 进行消歧

## 影响与后果

1. **安全性增强**：避免在非预期位置创建记忆树
2. **确定性行为**：在歧义情况下不会猜测，而是明确报告问题
3. **用户可控**：通过 `MEMORY_HOOK_DISABLE_DOWNWARD_PROBE` 环境变量提供逃生口
4. **与现有系统兼容**：不影响已经在 git 仓库内的会话行为

## 与相关决策的关联

- 与此决策相关的单一性硬规则决策：无标记的非 git 树被视为事故残留
- 与此决策相关的 consent 过渡语义：允许已同意的非 git 项目正常工作

## 实施状态

**已实施**：在 `memory_core/tools/factory_global_hooks.py` 的 render_wrapper 模板中实现

## 参考文献

- `factory_global_hooks.py` render_wrapper 模板
- `memory/artifacts/2026-09-10-nested-repo-root-resolution-solution-qwen.md`
- 用户裁决 2026-09-10
