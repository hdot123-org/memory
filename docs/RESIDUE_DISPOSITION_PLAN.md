# Residue 处置计划 — 回到远程稳定线

> 生成时间：2026-04-29
> 目标：branch-1 恢复为干净稳定线，所有真实业务数据正确归属

---

## 0. 原则

1. **不直接 push 未验收 commit**：当前 2 个本地 commit 未经验收，不得 push 到 origin/branch-1
2. **真实项目数据必须迁出**：AxonHub Rebase 相关文件迁移到 axonhub 业务项目
3. **通用内容可保留**：模板、通用规范框架保留在 memory 仓库
4. **branch-1 保持稳定线职责**：处置完成后，branch-1 应与 origin/branch-1 对齐

---

## 1. 处置步骤

### Phase 1: 提取可保留内容

**操作**：将 2 个 commit 中的通用内容提取出来

| 文件 | 操作 | 目标 |
|------|------|------|
| `templates/analyze-for-review.py` | 保留 | memory 仓库通用模板 |
| `templates/code-review-template.md` | 保留 | memory 仓库通用模板 |
| `workspace/memory/kb/global/projects-spec.md` | 保留并清理 | 保留通用框架，剥离 AxonHub CI 命令（约末尾 30-50 行） |
| `workspace/memory/kb/global/INDEX.md` | 保留 | 索引指向保留的 projects-spec |

### Phase 2: 迁出真实业务数据

**操作**：将业务数据迁移到 axonhub 仓库

| 文件 | 操作 | 目标位置 |
|------|------|----------|
| `workspace/memory/kb/projects/axonhub-rebase/PLAN.md` | 迁出 | `axonhub` 仓库 `.memory/kb/projects/axonhub-rebase/PLAN.md` |
| `workspace/memory/kb/projects/axonhub-rebase/STATE.md` | 迁出 | `axonhub` 仓库 `.memory/kb/projects/axonhub-rebase/STATE.md` |
| `workspace/memory/kb/projects/axonhub-rebase/CANONICAL.md` | 迁出 | `axonhub` 仓库 `.memory/kb/projects/axonhub-rebase/CANONICAL.md` |
| `workspace/NOW.md` | 清理 | 移除 AxonHub Rebase 业务任务行，或整体迁出到业务项目 |

### Phase 3: 清理 memory 仓库

**操作**：在当前 branch-2 上执行

1. 删除 `workspace/memory/kb/projects/axonhub-rebase/` 整个目录
2. 更新 `workspace/memory/kb/projects/INDEX.md` — 移除 axonhub-rebase 条目
3. 清理 `workspace/memory/kb/global/projects-spec.md` — 移除末尾 AxonHub 特定 CI 命令部分
4. 更新或清理 `workspace/NOW.md` — 移除具体业务任务引用

### Phase 4: 提交与验收

**操作**：创建干净的 commit

1. 在 branch-2 上提交上述清理操作
2. 验证：`git diff --stat origin/branch-1..branch-2` 只包含通用的、符合边界的变更
3. 提交主线程验收
4. 验收通过后，merge branch-2 → branch-1
5. push branch-1 → origin/branch-1
6. 删除 branch-2

---

## 2. 具体清理操作清单

### 2.1 删除真实项目状态目录

```bash
# 删除 axonhub-rebase 项目状态（迁移到 axonhub 仓库后）
rm -rf workspace/memory/kb/projects/axonhub-rebase/
```

### 2.2 更新 projects INDEX

```bash
# 移除 axonhub-rebase 条目，只保留 .keep 标记
# 或者如果还有其他项目索引，只移除对应行
```

### 2.3 清理 projects-spec.md

```bash
# 移除末尾的 AxonHub 特定运维命令（ssh ce-01 相关代码块）
# 保留前部的通用制定规范框架
```

### 2.4 处理 NOW.md

```bash
# 方案 A：将 NOW.md 整体迁出到业务项目
# 方案 B：保留 NOW.md 但仅保留 memory 仓库级 mission，移除业务任务引用
# 推荐方案 B（因为 NOW.md 可以作为 memory 模块的状态跟踪）
```

---

## 3. 验收标准

| 检查项 | 标准 |
|--------|------|
| 无真实项目状态 | `workspace/memory/kb/projects/` 下无 PLAN/STATE/CANONICAL 真实业务文件 |
| 无业务任务引用 | NOW.md 不引用具体业务项目的执行任务 |
| 通用内容完整 | templates/ 和 global/ 目录保留通用模板和框架 |
| 边界合规 | 所有文件符合 docs/BOUNDARY.md 定义的范围 |
| 远程对齐 | branch-1 push 后与 origin/branch-1 一致 |

---

## 4. 风险与注意事项

| 风险 | 缓解措施 |
|------|----------|
| 迁移数据丢失 | 在迁出前备份到临时目录或 axonhub 仓库的临时分支 |
| projects-spec.md 过度清理 | 只移除明确的 AxonHub CI 命令块，保留通用框架 |
| NOW.md 清理过度 | 保留 memory 仓库级 mission 和通用状态信息 |
| 索引不一致 | 清理后验证 INDEX.md 与实际文件一致 |

---

## 5. 回滚方案

如果处置过程中出现问题：

1. branch-2 上的所有操作都是可逆的
2. 可以通过 `git reset --hard branch-1` 回到当前状态
3. 原始 2 个 commit 的数据仍然存在于 branch-2 的 git history 中
4. 可以随时从 branch-2 的 git history 中恢复被删除的文件

---

## 6. 后续建议

1. **立即执行**：在下一个 branch-2 任务中完成 residue 清理
2. **启用防护**：`.gitignore` 已更新，未来类似污染文件将被 git 忽略
3. **定期审计**：每次 task 开始前运行 `git diff --stat origin/branch-1..branch-1` 检查 residue
4. **业务项目规范**：推动各业务项目建立 `.memory/` 目录结构，确保状态有正确归属
