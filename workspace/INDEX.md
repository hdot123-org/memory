# Workbot Workspace - 总控入口

> 简化版索引 | 整合自 MEMORY.md + ROUTER.md  
> 更新：2026-03-24 | OPS v3.0-workbot

---

## 🚀 启动顺序

**标准启动**：
1. `NOW.md` - 当前状态与任务
2. `memory/kb/INDEX.md` - 知识库索引
3. `memory/docs/INDEX.md` - 文档索引

**完整启动**（需要重建上下文时）：
1. `NOW.md`
2. `memory/kb/INDEX.md`
3. `memory/docs/INDEX.md`
4. `memory/log/YYYY-MM-DD.md` - 今日日志

---

## 🎯 核心规则

### 绝对禁止
- ❌ 覆盖任何 `memory/kb/**` 文件
- ❌ 删除 `memory/kb/**` 旧内容（只能标记 `superseded`）
- ❌ 静默覆盖知识库条目
- ❌ 将 `../archive-memory/**` 当作真相层

### 允许操作
- ✅ 只有 `NOW.md` 允许覆写
- ✅ `memory/log/` 只追加，不覆写
- ✅ `memory/kb/` 使用 read-first-CRUD
- ✅ `projects/**` 正常读写

---

## 📍 路由系统

### 写入目标

| 标签 | 目标路径 | 说明 |
|------|---------|------|
| [LOG] | `memory/log/YYYY-MM-DD.md` | 每日日志（append-only） |
| [KB:DECISION] | `memory/kb/decisions/` | 决策记录 |
| [KB:LESSON] | `memory/kb/lessons/` | 经验教训 |
| [KB:PROJECT] | `memory/kb/projects/` | 项目真相 |
| [KB:GLOBAL] | `memory/kb/global/` | 跨项目规则 |
| [KB:LONGTERM] | `memory/kb/longterm/` | 长期记忆 |
| [ACTION] | `memory/actions/inbox.md` | 临时任务（append-only） |
| [ARTIFACT] | `projects/**` | 交付产物 |
| [DOC] | `memory/docs/` | 研究资料 |

### 路由原则

**优先级**：
1. 项目真相 → `memory/kb/projects/`
2. 跨项目规则 → `memory/kb/global/`
3. 长期记忆 → `memory/kb/longterm/`
4. 研究资料 → `memory/docs/`
5. 交付产物 → `projects/`

---

## 🔧 写入协议

### KB 写入流程
1. **读取**目标文件
2. **判断**操作类型：
   - `NOOP` - 无需修改
   - `ADD` - 新增内容
   - `UPDATE` - 更新（只能追加 `superseded` 标记）
   - `CONFLICT` - 冲突（保留两版，等待人工裁决）
3. **执行**写入

### 冲突处理

```md
> ⚠️ CONFLICT (YYYY-MM-DD)
> A: 旧内容 + 来源
> B: 新内容 + 来源
> Needed: 人工裁决
```

---

## 📚 主要区域

### 核心目录
- `memory/kb/` - 知识库（真相层）
- `memory/docs/` - 文档库（资料层）
- `memory/log/` - 日志（时间线）
- `projects/` - 项目产物（交付层）

### 快速参考
- **知识库索引** → `memory/kb/INDEX.md`
- **文档索引** → `memory/docs/INDEX.md`
- **当前状态** → `NOW.md`
- **项目规范** → `memory/kb/global/memory-router-design.md`

---

## 🎯 当前工作空间

**根路径**：`/Users/busiji/workbot/workspace`

**说明**：
- 这是唯一总控工作区
- 所有核心规则、知识库、项目产物都在此统一管理
- 历史项目材料已移至 `history-projects/`（不在本 workspace 内）

---

## 📖 推荐阅读

**新用户**：
1. 本文件（`INDEX.md`）
2. `NOW.md` - 了解当前状态
3. `memory/kb/INDEX.md` - 浏览知识库结构

**深度使用**：
1. `memory/kb/global/` - 学习跨项目规则
2. `memory/kb/projects/` - 了解项目真相
3. `memory/docs/` - 查阅研究资料

---

*最后更新：2026-03-24 | 简化版 v1.0*