# 项目状态迁移规则

> 版本：v1.0 | 创建日期：2026-04-29
> 适用范围：memory 仓库 → 业务项目仓库的真实项目状态迁移

---

## 一、迁移规则总则

### 1.1 核心原则

- **memory 仓库只保留指针或示例**：迁移完成后，memory 仓库中不得保留项目的完整状态、代码、文档或任何可独立运行的内容。
- **业务项目是真相源**：迁移后的项目状态以业务项目仓库的 `.memory/` 目录为准。
- **迁移必须在业务项目 branch-2 执行**：所有迁移操作必须在目标业务项目仓库的 `branch-2` 分支上进行，严禁在 `branch-1` 或 `main` 上直接操作。
- **幂等性**：重复执行迁移流程不得破坏项目已有状态。
- **可追溯性**：每次迁移必须留下可追踪的 residue 记录，失败时可恢复。

### 1.2 角色分工

| 角色 | 职责 |
|------|------|
| main-thread（主线程） | 分配任务、验收结果、关闭 cycle，100% 不允许修改代码 |
| P1-迁移子代理 | 在 branch-2 上执行迁移文档、规则制定、状态检查 |
| 业务项目子代理 | 在业务项目 branch-2 上执行实际迁移操作 |

### 1.3 迁移触发条件

满足以下任一条件时触发迁移：
1. `workspace/projects/{ProjectName}/` 下存在非占位内容（非纯占位 INDEX.md）
2. 项目已从 memory 仓库独立，拥有自己的业务仓库
3. 主线程下达迁移指令

---

## 二、目标目录规范

### 2.1 业务项目 `.memory/` 标准结构

迁移后，业务项目仓库根目录下必须存在 `.memory/` 目录，结构如下：

```
{业务项目仓库}/
├── .memory/                        # 项目记忆层（迁移目标）
│   ├── kb/                         # 知识库（真相层）
│   │   ├── project/                # 项目真相
│   │   │   ├── context.md          # 项目上下文
│   │   │   ├── decisions/          # 决策记录
│   │   │   └── architecture.md     # 架构说明（如有）
│   │   ├── global/                 # 跨项目规则（引用或本地副本）
│   │   └── lessons/                # 经验教训
│   ├── docs/                       # 文档库（资料层）
│   │   ├── INDEX.md                # 文档索引
│   │   └── research/               # 研究资料
│   ├── log/                        # 日志（append-only）
│   │   └── YYYY-MM-DD.md           # 每日日志
│   ├── actions/                    # 临时任务
│   └── MIGRATION_RECORD.md         # 迁移记录（必填）
├── .memory-pointer.md              # memory 仓库指针文件（可选，见 2.2）
└── ...                             # 项目原有文件不变
```

### 2.2 memory 仓库保留指针规范

迁移完成后，memory 仓库中对应项目位置只保留以下之一：

**选项 A：指针文件（推荐）**
```markdown
# {ProjectName} — 已迁移

> 该项目已迁移至独立业务仓库。
> 
> - **目标仓库**：{业务仓库 URL 或路径}
> - **迁移日期**：YYYY-MM-DD
> - **迁移 commit**：{业务仓库 commit hash}
> - **迁移分支**：branch-2 → branch-1 (已合入)
> 
> 项目当前状态请以业务仓库 `.memory/` 为准。
```

**选项 B：示例快照（仅用于教学/参考）**
```markdown
# {ProjectName} — 示例快照

> 以下为迁移前的快照示例，仅供参考，不代表当前状态。
> 当前状态见：{业务仓库 URL}
> 
> [快照内容已标记为 superseded，不可作为真相源使用]
```

---

## 三、迁移步骤模板

### 3.1 迁移前检查（Pre-Migration）

```bash
# 1. 确认当前在业务项目仓库的 branch-2
cd {业务项目仓库路径}
git branch --show-current
# 预期输出：branch-2

# 2. 确认 branch-1 已对齐远程
git fetch origin branch-1
git log --oneline branch-1..origin/branch-1 | wc -l
# 预期输出：0

# 3. 确认 .memory/ 目录不存在或为空
ls -la .memory/ 2>/dev/null || echo "目录不存在，可安全创建"

# 4. 检查 memory 仓库中项目内容
cd {memory 仓库路径}
find workspace/projects/{ProjectName}/ -type f | grep -v '.gitkeep'
# 记录所有待迁移文件
```

### 3.2 执行迁移（Migration Execution）

**Step 1：在业务项目 branch-2 上创建 .memory/ 骨架**
```bash
mkdir -p .memory/{kb/{project/decisions,global,lessons},docs/research,log,actions}
touch .memory/docs/INDEX.md
```

**Step 2：从 memory 仓库复制项目状态文件**
```bash
# 从 memory 仓库 workspace/projects/{ProjectName}/ 复制内容
# 从 memory 仓库 workspace/memory/kb/projects/{ProjectName}/ 复制（如有）
# 从 memory 仓库 workspace/memory/docs/ 复制项目相关文档（如有）

cp -r {memory}/workspace/projects/{ProjectName}/* {业务项目}/.memory/kb/project/
```

**Step 3：生成迁移记录**
```bash
cat > .memory/MIGRATION_RECORD.md << 'EOF'
# 迁移记录

| 项目 | 值 |
|------|-----|
| 源仓库 | memory ({memory 仓库 URL}) |
| 源 commit | {commit hash} |
| 目标仓库 | {业务项目仓库 URL} |
| 目标分支 | branch-2 |
| 迁移日期 | YYYY-MM-DD |
| 执行人 | {子代理名称} |
| 迁移范围 | workspace/projects/{ProjectName}/ → .memory/ |

## 迁移内容清单

- [ ] kb/project/ 已迁移
- [ ] kb/global/ 引用已建立
- [ ] docs/ 已迁移
- [ ] log/ 已迁移
- [ ] actions/ 已迁移

## 验证状态

- [ ] validator 核验通过（引用 validator 概念）
- [ ] 重复执行幂等性测试通过
- [ ] memory 仓库已替换为指针文件
EOF
```

**Step 4：提交迁移结果**
```bash
git add .memory/
git commit -m "migrate: import project state from memory repo → .memory/"
```

**Step 5：在 memory 仓库中替换为指针**
```bash
# 在 memory 仓库 branch-2 上操作
cd {memory 仓库路径}
# 将 workspace/projects/{ProjectName}/ 内容替换为指针文件（见 2.2）
git add workspace/projects/{ProjectName}/
git commit -m "migrate: replace {ProjectName} with migration pointer"
```

### 3.3 迁移后验证（Post-Migration Validation）

```bash
# 1. validator 核验（引用 validator 概念）
# 运行业务项目的 validator 脚本（如有）
# 验证 .memory/ 结构完整性
test -f .memory/MIGRATION_RECORD.md && echo "迁移记录存在" || echo "FAIL: 迁移记录缺失"
test -d .memory/kb/project/ && echo "知识库存在" || echo "FAIL: 知识库缺失"

# 2. 幂等性测试：再次执行迁移步骤，确认不破坏已有状态

# 3. 确认 memory 仓库只保留指针
cat workspace/projects/{ProjectName}/INDEX.md
# 预期：包含"已迁移"或"示例快照"标记
```

---

## 四、失败/中断/Residue 处理流程

### 4.1 失败分类

| 级别 | 场景 | 处理方式 |
|------|------|----------|
| P0-致命 | 数据丢失、文件覆盖 | 立即回滚（见 5.1），通知主线程 |
| P1-严重 | 迁移不完整、结构错误 | 标记 residue，记录失败原因，保留 branch-2 供后续处理 |
| P2-一般 | 部分文件未迁移、格式问题 | 记录 residue，可在下次迁移 cycle 中补全 |
| P3-轻微 | 文档格式、命名不一致 | 记录为技术债，不影响迁移完成 |

### 4.2 Residue 记录格式

每次失败或中断必须在 `.memory/RESIDUE.md` 中记录：

```markdown
# Residue 记录

## Cycle ID: {YYYYMMDD-HHMM}

| 项目 | 值 |
|------|-----|
| 阶段 | {失败阶段} |
| 错误 | {错误描述} |
| 影响 | {影响范围} |
| 状态 | open / in-progress / resolved |
| 下次处理 | {计划处理时间或条件} |

## 未迁移文件清单
- `path/to/file.md` — 原因：{原因}

## 恢复步骤
1. {步骤}
2. {步骤}
```

### 4.3 中断恢复流程

1. 检查 `.memory/RESIDUE.md` 是否存在，确认上次中断点
2. 从最近的完成步骤继续执行
3. 补全遗漏文件
4. 更新 residue 状态为 `resolved`
5. 重新执行验证

### 4.4 失败禁止合入规则

**迁移未通过、被停止、被拒绝或 residue 未清时，不得将 branch-2 合回 branch-1。**

---

## 五、回滚策略

### 5.1 回滚触发条件

- 迁移后 validator 核验失败且无法修复
- 发现数据丢失或覆盖
- 主线程要求回滚

### 5.2 回滚步骤

```bash
# Step 1：在业务项目 branch-2 上删除 .memory/
rm -rf .memory/

# Step 2：恢复 memory 仓库中的项目内容
# 从上一次 commit 恢复
cd {memory 仓库路径}
git checkout HEAD~1 -- workspace/projects/{ProjectName}/

# Step 3：记录回滚
echo "回滚记录见 .memory/RESIDUE.md" 

# Step 4：在 branch-2 提交回滚
git add .
git commit -m "rollback: revert migration of {ProjectName}"
```

### 5.3 回滚后验证

- 确认 memory 仓库中项目内容已恢复
- 确认业务项目仓库中无残留 `.memory/` 文件
- 确认 residue 记录已更新

---

## 六、迁移候选示例

### 6.1 当前仓库中的真实项目状态

经检查，`workspace/projects/` 目录下存在以下项目：

| 项目名 | 路径 | 状态 | 迁移就绪度 |
|--------|------|------|-----------|
| **AEdu** | `workspace/projects/AEdu/` | 占位索引 | ⏳ 待确认 |

**AEdu 详细状态：**
- 文件：`workspace/projects/AEdu/INDEX.md`
- 内容：占位文本（"迁移阶段占位索引"）
- 评估：当前为占位状态，不含真实项目数据。迁移就绪度取决于外部业务仓库是否存在。
- 动作：确认 AEdu 业务仓库路径后，可执行迁移。

### 6.2 迁移候选评估标准

| 条件 | 状态 |
|------|------|
| 存在非占位内容 | ❌ 当前仅为占位 |
| 有独立业务仓库 | ⏳ 待确认 |
| 有业务仓库 branch-2 | ⏳ 待确认 |
| 主线程下达迁移指令 | ⏳ 待确认 |

**结论**：AEdu 当前为占位状态。当满足迁移触发条件（见 1.3）时，按本规则执行迁移。

---

## 七、附录

### 7.1 术语表

| 术语 | 定义 |
|------|------|
| branch-1 | 本地稳定分支，与 GitHub 对齐，累计已验收结果 |
| branch-2 | 任务分支，所有任务执行必须在该分支上进行 |
| main-thread | 主线程，负责任务分配和验收，不修改代码 |
| validator | 迁移验证工具/脚本，用于核验迁移完整性 |
| residue | 迁移过程中遗留的未处理事项 |
| .memory/ | 业务项目仓库中的记忆层目录，迁移目标 |

### 7.2 相关文档

- `MIGRATION_CHECKLIST.md` — 迁移执行清单模板
- `workspace/memory/kb/global/workbot-truth-model.md` — 真相模型
- `workspace/project-map/INDEX.md` — 项目地图

---

*文档版本：v1.0 | 最后更新：2026-04-29*
