# 迁移执行清单模板

> 版本：v1.0 | 创建日期：2026-04-29
> 使用说明：每次迁移任务复制本文件至业务项目仓库 `.memory/CHECKLIST.md`，逐项执行并勾选

---

## 任务基本信息

| 字段 | 值 |
|------|-----|
| 项目名称 | {ProjectName} |
| 源仓库 | memory ({路径/URL}) |
| 目标仓库 | {业务项目仓库路径/URL} |
| 目标分支 | branch-2 |
| 迁移日期 | YYYY-MM-DD |
| 执行人 | {子代理名称} |
| Cycle ID | {YYYYMMDD-HHMM} |

---

## Phase 1：迁移前检查

- [ ] 1.1 确认在业务项目仓库 `branch-2` 分支上工作
- [ ] 1.2 确认 `branch-1` 已对齐远程 `origin/branch-1`
- [ ] 1.3 确认 `.memory/` 目录不存在或为空（无残留）
- [ ] 1.4 确认 memory 仓库中项目内容完整可访问
- [ ] 1.5 记录待迁移文件清单（见下方表格）
- [ ] 1.6 主线程已下达迁移指令

### 待迁移文件清单

| 源路径 | 目标路径 | 大小 | 迁移状态 |
|--------|----------|------|----------|
| `memory/workspace/projects/{ProjectName}/` | `.memory/kb/project/` | | ⏳ |
| `memory/workspace/memory/kb/projects/{ProjectName}/` (如有) | `.memory/kb/project/` | | ⏳ |
| `memory/workspace/memory/docs/` 项目相关 (如有) | `.memory/docs/` | | ⏳ |
| `memory/workspace/memory/log/` 项目相关 (如有) | `.memory/log/` | | ⏳ |
| `memory/workspace/memory/actions/` 项目相关 (如有) | `.memory/actions/` | | ⏳ |

---

## Phase 2：执行迁移

- [ ] 2.1 在业务项目 branch-2 上创建 `.memory/` 骨架
  ```
  .memory/
  ├── kb/{project/{decisions,},global,lessons}
  ├── docs/{research,}
  ├── log/
  └── actions/
  ```
- [ ] 2.2 从 memory 仓库复制项目知识库文件
- [ ] 2.3 从 memory 仓库复制项目文档（如有）
- [ ] 2.4 从 memory 仓库复制项目日志（如有）
- [ ] 2.5 从 memory 仓库复制项目 action（如有）
- [ ] 2.6 生成 `MIGRATION_RECORD.md`
- [ ] 2.7 生成 `CHECKLIST.md`（本文件）
- [ ] 2.8 `git add .memory/` + `git commit`

---

## Phase 3：memory 仓库清理

- [ ] 3.1 在 memory 仓库 branch-2 上操作
- [ ] 3.2 将 `workspace/projects/{ProjectName}/` 替换为指针文件
  - [ ] 指针包含：目标仓库 URL、迁移日期、commit hash
- [ ] 3.3 删除或标记 `superseded` 旧内容（不直接删除，先标记）
- [ ] 3.4 `git add` + `git commit`

---

## Phase 4：验证

- [ ] 4.1 结构验证
  - [ ] `.memory/` 目录存在且结构正确
  - [ ] `MIGRATION_RECORD.md` 存在且信息完整
  - [ ] 所有源文件已迁移（对比 Phase 1 清单）
- [ ] 4.2 Validator 核验
  - [ ] 运行 validator 脚本/工具（如有）
  - [ ] 核验通过 / 失败原因：{记录}
- [ ] 4.3 幂等性测试
  - [ ] 重复执行迁移步骤，确认不破坏已有状态
- [ ] 4.4 指针验证
  - [ ] memory 仓库中项目位置为指针文件（非完整内容）
  - [ ] 指针指向正确的业务仓库 URL

---

## Phase 5：验收与合入

- [ ] 5.1 主线程验收通过
- [ ] 5.2 业务项目 branch-2 合入 branch-1
- [ ] 5.3 推送 branch-1 至远程
- [ ] 5.4 删除业务项目 branch-2
- [ ] 5.5 记忆层迁移 branch-2 合入 branch-1（指针更新）
- [ ] 5.6 推送 memory 仓库 branch-1 至远程
- [ ] 5.7 删除 memory 仓库 branch-2

---

## Phase 6：异常处理（如适用）

### Residue 记录

- [ ] 6.1 发现异常，记录至 `.memory/RESIDUE.md`
- [ ] 6.2 标记未完成项及原因
- [ ] 6.3 通知主线程

### 回滚（如适用）

- [ ] 6.4 触发回滚条件
- [ ] 6.5 执回滚步骤
- [ ] 6.6 确认回滚成功
- [ ] 6.7 记录回滚原因

---

## 完成状态

| 字段 | 值 |
|------|-----|
| 完成日期 | YYYY-MM-DD |
| 最终状态 | ✅ 成功 / ❌ 失败 / ⏸️ 暂停 |
| Residue | 无 / {描述} |
| 下次处理计划 | {如适用} |

---

*模板版本：v1.0 | 最后更新：2026-04-29*
