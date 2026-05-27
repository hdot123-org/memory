# GitHub Projects 通用制定规范

> 版本：v2.0 / 2026-04-29
> 适用范围：hdot123 下所有仓库、所有任务类型
> 本文档是通用框架，不绑定任何具体项目

---

## 1. 用户触发

用户在任何会话中发送：

```
执行 https://github.com/users/hdot123/projects/<number>
```

主线程收到后，按本规范自动完成从分析到执行到验收的全流程。

用户可选附加指令：

| 指令 | 含义 |
|------|------|
| `执行 <链接>` | 按进度自动继续 |
| `执行 <链接> 只跑 W3` | 只分派指定 Worker |
| `执行 <链接> dry-run` | 只输出计划不执行 |
| `执行 <链接> 验收` | 不分派，只审核已完成的工作 |

---

## 2. 主线程启动流程

收到用户触发后，主线程按以下顺序执行：

```
Step 1: 读取看板
    │  gh project item-list <number> --owner hdot123
    │
Step 2: 检查本地文件
    │  ls <project-root>/<任务>-PLAN.md
    │  ls <project-root>/<任务>-STATE.md
    │
Step 3: 判断状态
    │
    ├── PLAN + STATE 都不存在 → 首次启动，进入「制定流程」（Section 3）
    ├── PLAN 存在 + STATE 不存在 → 首次启动，创建 STATE，进入制定流程收尾
    ├── PLAN + STATE 都存在 → 接力执行，进入「执行流程」（Section 5）
    └── STATE 存在 + PLAN 不存在 → 异常，报告用户
```

---

## 3. 制定流程（首次启动）

当看板存在但本地没有计划文件时，主线程必须先制定完整计划。

### 3.1 分析阶段

主线程需要收集以下信息：

```bash
# 仓库定位（从看板 readme 或卡片中提取）
# 假设仓库路径为 <project-root>/<repo>

cd <project-root>/<repo>

# 分支状态
git branch -a
git fetch --all

# 识别基线和目标
# 对比源分支和目标分支的差异
git log --oneline <base>..<target>
git diff --stat <base>..<target>
```

### 3.2 冲突/依赖分析

分析两端的改动重叠：

```bash
# 重叠文件
comm -12 <(git diff --name-only <base> <source> | sort) \
         <(git diff --name-only <base> <target> | sort)

# 按冲突严重程度分类（行数阈值可调整）
# 重度：双端都 > 50 行
# 中度：一端 > 50 行
# 轻度：双端都 <= 50 行
```

### 3.3 Worker 分组原则

将改动按模块拆分为多个 Worker，遵循以下约束：

**约束 1：写集不重叠**
- 每个 Worker 的文件列表必须互斥
- 共享文件归入冲突最重的 Worker，或单独一个 Worker

**约束 2：模块内聚**
- 同一目录/包下的文件尽量分给同一个 Worker
- 有 import 依赖的文件尽量分给同一个 Worker

**约束 3：独立 Go module 独立 Worker**
- 如有 `llm/` 这样的独立 module，单独一个 Worker

**约束 4：生成代码单独处理**
- `go generate` 产生的文件（ent、gqlgen 等）不手动合并
- 最后由专门的 Worker 统一 `go generate`

**约束 5：测试文件归最后的 Worker**
- 测试文件依赖业务代码的最终形态
- 测试修复放在最后一个 Worker（W_last）

**约束 6：Worker 数量**
- 最少 2 个（业务 + 测试）
- 最多 8 个
- 推荐 4-6 个

**依赖关系：**
- 业务 Worker（W1-Wn）之间并行
- go generate Worker（如有）依赖所有业务 Worker
- 测试 Worker 依赖所有前面的 Worker

```
W1 ──┐
W2 ──┤
W3 ──┼──→ [W_gen] ──→ [W_test] ──→ merge
W4 ──┤
W5 ──┘
```

### 3.4 生成计划文件

创建 `<任务名>-PLAN.md`，必须包含以下 Section：

| Section | 内容 | 读者 |
|---------|------|------|
| 背景与目标 | 为什么做、做什么、基线和目标 | 所有人 |
| 冲突/依赖分析 | 重叠文件、分档、解决策略 | 主线程 + Worker |
| Commit 清单 | 所有待迁移 commit 的 hash 和 message | Worker |
| Worker 分工 | 每个 Worker 的写集、commit、冲突规则、验证命令 | Worker |
| 执行流程图 | ASCII 或 Mermaid | 主线程 |
| 冲突解决原则 | 通用规则 | Worker |
| 已知跳过项 | 哪些 commit/文件不需要处理 | Worker |
| 验收标准 | 最终 checklist | 主线程 |
| 回退方案 | 出问题时怎么办 | 主线程 |
| 主线程接力协议 | 多会话接力规则 | 主线程 |
| 子代理须知 | 子代理简明指令 | Worker |
| 用户触发指令 | 用户如何启动 | 用户 |

### 3.5 生成状态文件

创建 `<任务名>-STATE.md`，模板：

```markdown
# <任务名> 执行状态

> 最后更新：YYYY-MM-DD HH:MM
> 更新者：初始创建

## 总体状态：未开始

## 任务进度

| 任务 | 状态 | 分派会话 | 完成会话 | 结果摘要 |
|------|------|----------|----------|----------|
| P0: 创建任务分支 | Todo | | | |
| W1: <模块1> | Todo | | | |
| ... | | | | |
| Wn: 测试+生成+验收 | Todo | | | |
| P1: merge + push + 清理 | Todo | | | |

## 阻塞记录

（无）

## 决策记录

（无）

## 审核记录

（待 Worker 完成后填写）

## 验收报告

（待全部完成后填写）
```

### 3.6 配置看板

**Step A: 链接到仓库（如果还没链接）**

```bash
# 获取仓库 ID
gh api graphql -f query='query { repository(owner:"<owner>",name:"<repo>") { id } }'

# 链接项目到仓库
gh api graphql -f query='mutation { linkProjectV2ToRepository(input:{projectId:"<project-id>",repositoryId:"<repo-id>"}) { clientMutationId } }'
```

**Step B: 创建 Worker 字段**

```bash
gh project field-create <number> --owner hdot123 \
  --name "Worker" \
  --data-type SINGLE_SELECT \
  --single-select-options "<选项1>,<选项2>,...,main-thread"
```

选项按实际 Worker 编号创建：`W1:模块1,W2:模块2,...,Wn:测试+验收,main-thread`

**Step C: 创建任务卡片**

每张卡片必须按以下模板编写：

```markdown
# 任务指令 <编号>：<标题>

## 分派模板（主线程复制此内容 spawn_agent）

​```
你是 W<N>，负责 <模块名>。

工作分支：git checkout <任务分支>

你的写集（只允许修改这些文件）：
- <文件1>
- <文件2>
- ...

禁止：
- 不碰其他 Worker 文件
- 不执行 go generate（留给 W<N>）
- 不修改 <稳定分支>

Cherry-pick / 改动列表（按顺序）：
1. <hash> — <说明>
2. <hash> — <说明>
...

冲突解决规则：
- <规则1>
- <规则2>

每完成一步跑验证：
<验证命令>

完成后汇报：成功 / 失败 + 详情
​```

## 冲突/依赖上下文
（主线程审核用的补充信息）

## 验证命令
​```
<验证命令>
​```

## 完成后主线程动作
1. 审核改动（Section 6）
2. 更新 STATE 文件
3. 更新看板
```

**卡片类型：**

| 编号 | 类型 | 执行者 | 含义 |
|------|------|--------|------|
| P0 | 主线程任务 | main-thread | 创建任务分支、前置准备 |
| W1-Wn | Worker 任务 | 子代理 | 并行执行的业务任务 |
| P1 | 主线程任务 | main-thread | merge + push + 清理 |

**卡片数量 = 1(P0) + N(Worker) + 1(P1)**

---

## 4. 文件命名规范

| 文件 | 命名 | 位置 |
|------|------|------|
| 计划文件 | `<任务名>-PLAN.md` | `<project-root>/` |
| 状态文件 | `<任务名>-STATE.md` | `<project-root>/` |
| 规范文件 | `PROJECTS-SPEC.md` | `<project-root>/`（本文件） |

任务名从看板标题中提取，大写英文+连字符。示例：
- `<Project> Rebase` → `REBASE`
- `<Project> Audit` → `AUDIT`
- `<Project> Clone` → `<PROJECT>-CLONE`

---

## 5. 执行流程（接力启动）

已有 PLAN + STATE 时，主线程按以下流程执行：

```
读取 STATE.md
    │
    ├── P0 = Todo → 执行 P0（创建任务分支）
    │   └── go build 验证上游代码可编译
    │
    ├── W1-W(n-1) 有 Todo → 并行 spawn_agent
    │   ├── 从看板卡片的「分派模板」复制 spawn message
    │   ├── 子代理模型：gpt-5.4-mini
    │   └── 每个 Worker 的写集不重叠，可同时跑
    │
    ├── W1-W(n-1) 全部 Done，W_test = Todo → 分派 W_test
    │   └── 串行，等前面全部完成
    │
    ├── W_test Done，P1 = Todo → 执行 P1（merge + push）
    │
    └── 全部 Done → 汇报完成
```

### 5.1 Worker 返回后主线程必须做的事

```
子代理汇报完成
    │
    ├── 审核改动（Section 6）
    │   ├── 审核通过 → 继续
    │   └── 审核不通过 → 退回（最多 2 次）
    │
    ├── 更新 STATE.md（状态 + 时间戳）
    ├── 更新看板卡片状态
    └── 汇报进度给用户
```

### 5.2 子代理模型

- 默认：`gpt-5.4-mini`
- 主线程可根据任务复杂度提升模型，但需在 STATE.md 中记录原因

---

## 6. 审核规范

### 6.1 审核时机

- 子代理汇报完成后，主线程必须先审核
- 未经审核不得标记为 Done

### 6.2 审核维度

| 维度 | 检查内容 | 方法 |
|------|----------|------|
| 写集合规 | 只改了自己负责的文件 | `git diff --name-only` 对比写集白名单 |
| 编译通过 | 代码可编译 | `go build ./...`（注意独立 module） |
| 静态检查 | 无明显问题 | `go vet ./...` |
| 冲突正确性 | 按规则解决，无遗漏 | 逐文件 `git diff` 审阅 |
| 功能完整性 | 分配的任务全部完成 | `git log --oneline` 对比清单 |
| 无副作用 | 未引入无关改动 | `git diff --stat` |

### 6.3 审核流程

```
1. 写集合规 → 越界则退回
2. 编译     → 失败则退回
3. 冲突正确性（重度冲突逐行审阅，中度抽查，轻度跳过）
4. 功能完整性 → 有遗漏则退回
5. 通过 → 更新状态
```

### 6.4 审核记录

每次审核必须记录到 STATE.md：

```markdown
### W<N> 审核 — YYYY-MM-DD
- 结果：通过 / 退回
- 写集合规：是/否
- 编译：通过/失败
- 冲突解决：正确/有问题（文件：xxx）
- 功能完整性：完整/缺失
- 备注：xxx
```

### 6.5 退回规则

- 退回时必须给出**具体修改要求**
- 同一 Worker 最多退回 **2 次**，第 3 次标记 Blocked 等人工介入

---

## 7. 验收规范

### 7.1 三级验收

| 层级 | 时机 | 执行者 | 内容 |
|------|------|--------|------|
| L1 | 每个 Worker 完成后 | 主线程 | 写集 + 编译 + vet |
| L2 | 所有 Worker 完成后 | 主线程 | 全量编译 + generate + 分模块测试 + 全量测试 |
| L3 | merge 之前 | 主线程 | race detector + 最终 checklist |

**L1 不通过不进 L2，L2 不通过不进 L3，L3 不通过不 merge。**

### 7.2 L1: Worker 验收

```bash
git diff --name-only <base>..<branch> -- <Worker写集路径>
go build ./对应模块/...
go vet ./对应模块/...
```

通过标准：
- [ ] 改动在写集范围内
- [ ] 编译零错误
- [ ] vet 零警告
- [ ] 分配的任务全部完成
- [ ] 冲突按规则解决

### 7.3 L2: 集成验收

```bash
# 1. 全量编译
go build ./...

# 2. 代码生成（如适用）
go generate ./...

# 3. 再次编译（generate 后）
go build ./...

# 4. 分模块测试
go test ./模块1/... -count=1 -timeout 120s
go test ./模块2/... -count=1 -timeout 120s
# ...（按项目实际模块列出）

# 5. 全量测试
go test ./... -count=1 -timeout 300s
```

通过标准：
- [ ] 全量编译零错误
- [ ] go generate 无报错
- [ ] 所有模块测试全绿
- [ ] 全量测试全绿
- [ ] 所有任务可追溯

### 7.4 L3: 最终验收

```bash
go test -race ./... -count=1 -timeout 300s
git log --oneline <base>..<branch>
git diff --stat
```

通过标准：
- [ ] race detector 全绿
- [ ] 所有任务可追溯
- [ ] 无意外改动
- [ ] vet 零警告

### 7.5 验收报告

L2/L3 完成后在 STATE.md 中生成：

```markdown
## 验收报告

### L1 Worker 验收
| Worker | 结果 | 编译 | 写集 | 冲突 | 备注 |
|--------|------|------|------|------|------|
| W1 | PASS/FAIL | | | | |
| ... | | | | | |

### L2 集成验收
- 全量编译：✅/❌
- go generate：✅/❌
- 分模块测试：逐项 ✅/❌
- 全量测试：✅/❌

### L3 最终验收
- race detector：✅/❌
- 任务可追溯性：✅/❌
- 无意外改动：✅/❌
- 最终结论：PASS / FAIL
```

### 7.6 验收失败处理

| 层级 | 处理 |
|------|------|
| L1 | 退回 Worker（最多 2 次） |
| L2 | 定位失败模块，重新分派，重跑 L2 |
| L3 | 定位问题，修复后重跑 L3 |

---

## 8. 看板管理规范

### 8.1 项目字段

| 字段 | 类型 | 必选 | 用途 |
|------|------|------|------|
| Title | 内置 | 是 | 任务标题 |
| Status | 内置 | 是 | Todo / In Progress / Done |
| Worker | 单选 | 是 | 执行者标识 |
| Assignees | 内置 | 否 | 负责人 |

### 8.2 看板同步时机

- 任务开始：Todo → In Progress
- 任务审核通过：In Progress → Done
- 任务退回：In Progress → Todo
- 看板与 STATE 不一致时以 STATE 为准，同步看板

### 8.3 看板命令速查

```bash
# 列出项目
gh project list --owner hdot123

# 查看卡片
gh project item-list <number> --owner hdot123

# 创建卡片（draft issue）
gh api graphql -f query='mutation {
  addProjectV2DraftIssue(input:{
    projectId:"<project-id>",
    title:"<标题>",
    body:"<body>"
  }) { projectItem { id } }
}'

# 更新状态
gh project item-edit --id <item-id> --project-id <project-id> \
  --field-id <status-field-id> --single-select-option-id <option-id>

# 链接到仓库
gh api graphql -f query='mutation {
  linkProjectV2ToRepository(input:{
    projectId:"<project-id>",
    repositoryId:"<repo-id>"
  }) { clientMutationId }
}'
```

---

## 9. 完整工作流总览

```
用户发送：执行 <项目链接>
    │
    ├── 看板存在？
    │   ├── 否 → 报错，要求用户先创建 GitHub Project
    │   └── 是 → 继续
    │
    ├── STATE 存在？
    │   ├── 否 → 制定流程（Section 3）
    │   │   ├── 分析仓库状态
    │   │   ├── 冲突/依赖分析
    │   │   ├── Worker 分组
    │   │   ├── 生成 PLAN.md
    │   │   ├── 生成 STATE.md
    │   │   ├── 配置看板（字段 + 卡片）
    │   │   └── 汇报计划给用户，等待确认或直接执行
    │   │
    │   └── 是 → 执行流程（Section 5）
    │       ├── P0 Todo → 执行 P0
    │       ├── W1-W(n-1) Todo → 并行分派
    │       ├── W_test Todo → 串行分派
    │       ├── P1 Todo → 执行 P1
    │       └── 全部 Done → 完成
    │
    ├── 每个 Worker 完成后 → 审核（Section 6）
    │
    ├── 所有 Worker 完成 → 验收（Section 7）
    │
    └── 验收通过 → merge + push + 清理 + 归档
```

---

## 10. 跨项目通用约束

1. **主线程不写代码**，只读状态、分派任务、验收结果
2. **子代理模型统一 gpt-5.4-mini**，除非主线程判断需要更强模型并在 STATE 中记录
3. **子代理不读看板**，只读 PLAN.md
4. **STATE.md 是唯一真源**，看板是可视化层
5. **写集不重叠**，Worker 之间不得碰对方的文件
6. **独立 Go module 独立 Worker**，go 命令在对应目录下执行
7. **生成代码不手动合并**，由专门 Worker 统一 go generate
8. **审核不通过不进 Done**，退回最多 2 次
9. **L1 不过不进 L2，L2 不过不进 L3，L3 不过不 merge**
10. **任何会话可接力**，读 STATE.md 即可恢复上下文

---



---

*第 11 节 "CE-01 自动化部署" 已从本通用规范中剥离（属于 AxonHub 项目专属运维信息），完整内容归档于 `archive/legacy-workbot/projects-spec-axonhub-section.md`。如需恢复，请将该文件追加回此 spec 末尾。*
