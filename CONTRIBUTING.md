# Contributing to memory-core

## 分支模型

本项目使用 `branch-1 / branch-2` 任务隔离流：

- `branch-1` — 稳定分支，与 GitHub 同步，累计已验收结果
- `branch-2` — 每次任务从 `branch-1` 创建，任务完成后合回并删除

### 工作流程

1. 从 `branch-1` 创建新的任务分支
2. 在任务分支上完成开发、测试
3. 确保所有测试通过
4. 合回 `branch-1` 并删除任务分支

## 测试

```bash
python3 -m pytest
```

## 代码风格

```bash
ruff check .
```

## 提交信息

格式: `Task X.Y: 简短描述`
