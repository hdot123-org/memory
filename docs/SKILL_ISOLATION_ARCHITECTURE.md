# Skill Isolation Architecture — 3-Layer Gateway Pattern

> 版本: 1.0.0 | 创建: 2026-05-19 | 状态: design
> 权威源: Git
> 目标: 仅 5 个自定义 ShowDoc↔飞书 skill 为用户-facing 入口，其余文档 skill 降级为内部服务

---

## 1. 问题陈述

当前，`lark-doc`、`lark-wiki`、`lark-drive`、`wiki`、`docx` 等文档类 skill 可被用户直接触发，绕过了：
- ShowDoc↔飞书同步管线
- 19 项安全 Markdown 子集校验
- `sync_registry.yaml` 同步注册表
- 保护标注与审计闭环

**目标**：将这 5 个 skill 降级为"内部服务层"，仅由我们定制的 5 个 gateway skill 调用，禁止用户直接触发。

---

## 2. 3 层架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        用户请求 (User Intent)                            │
│   "同步文档到飞书"  "创建 API 文档"  "检查一致性"  "回写计划页"            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ╔═══════════════════════════════════════════════════════════════════╗  │
│  ║  LAYER 1: GATEWAY (唯一用户入口) — 5 个 Custom Skills              ║  │
│  ║                                                                   ║  │
│  ║  ┌──────────────────────┐  ┌──────────────────────────────┐       ║  │
│  ║  │ showdoc-markdown-    │  │ showdoc-platform-rules       │       ║  │
│  ║  │ compat               │  │ — ShowDoc 操作规则/模板       │       ║  │
│  ║  │ — Markdown 安全子集  │  └──────────────────────────────┘       ║  │
│  ║  │   (19项) 规则        │  ┌──────────────────────────────┐       ║  │
│  ║  └──────────────────────┘  │ feishu-platform-rules        │       ║  │
│  ║  ┌──────────────────────┐  │ — 飞书同步操作规则            │       ║  │
│  ║  │ sync-cross-platform  │  └──────────────────────────────┘       ║  │
│  ║  │ -rules               │  ┌──────────────────────────────┐       ║  │
│  ║  │ — 跨平台同步管线/     │  │ doc-governance               │       ║  │
│  ║  │   冲突解决/回滚策略   │  │ — 文档生命周期/治理/审计规则  │       ║  │
│  ║  └──────────────────────┘  └──────────────────────────────┘       ║  │
│  ║                                                                   ║  │
│  ║  职责: 意图解析 → 规则校验 → 路由决策 → 调用 L2 引擎               ║  │
│  ║  约束: 必须校验 sync_registry, 安全子集, 保护标注, 权威源映射      ║  │
│  ╚═══════════════════════════════════════════════════════════════════╝  │
│                               │                                         │
│                  ┌────────────┼────────────┐                             │
│                  ▼            ▼            ▼                            │
│  ╔═══════════════════════════════════════════════════════════════════╗  │
│  ║  LAYER 2: ENGINE (内部服务) — 禁止用户直接触发                     ║  │
│  ║                                                                   ║  │
│  ║  ┌────────────┐  ┌────────────┐  ┌────────────┐                   ║  │
│  ║  │ lark-doc   │  │ lark-wiki  │  │ lark-drive │                   ║  │
│  ║  │ 云文档 CRUD │  │ 知识库管理  │  │ 云空间管理  │                   ║  │
│  ║  └────────────┘  └────────────┘  └────────────┘                   ║  │
│  ║  ┌────────────┐  ┌────────────┐                                    ║  │
│  ║  │ wiki       │  │ docx       │                                    ║  │
│  ║  │ Wiki 生成  │  │ Word 文档  │                                    ║  │
│  ║  └────────────┘  └────────────┘                                    ║  │
│  ║                                                                   ║  │
│  ║  职责: 执行原始操作 (create/read/update/fetch)                     ║  │
│  ║  约束: 不执行验证/不决策路由/不跳过 sync_registry                   ║  │
│  ║  调用者: 仅接受来自 L1 Gateway 的调用                               ║  │
│  ╚═══════════════════════════════════════════════════════════════════╝  │
│                               │                                         │
│                               ▼                                         │
│  ╔═══════════════════════════════════════════════════════════════════╗  │
│  ║  LAYER 3: TRANSPORT (实际执行) — 底层工具/MCP                       ║  │
│  ║                                                                   ║  │
│  ║  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            ║  │
│  ║  │ lark-cli     │  │ ShowDoc MCP  │  │ git          │            ║  │
│  ║  │ docs+/drive+ │  │ upsert/get   │  │ commit/diff  │            ║  │
│  ║  │ wiki+/sheets+│  │ update/search│  │              │            ║  │
│  ║  └──────────────┘  └──────────────┘  └──────────────┘            ║  │
│  ║                                                                   ║  │
│  ║  职责: 与外部 API 的实际通信                                        ║  │
│  ╚═══════════════════════════════════════════════════════════════════╝  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 层定义

### 3.1 Layer 1: Gateway（5 个自定义 Skill）

| Skill | 职责 | 触发场景 | 调用的 L2 引擎 |
|-------|------|---------|---------------|
| **showdoc-markdown-compat** | 19 项安全 Markdown 子集规则定义与校验 | 任何文档写入/同步前 | lark-doc (写入), showdoc MCP (写入) |
| **showdoc-platform-rules** | ShowDoc 操作模板/API 文档格式/页面分类 | 创建/更新 ShowDoc 文档 | showdoc MCP |
| **feishu-platform-rules** | 飞书同步操作规则/格式转换/保护标注 | ShowDoc→飞书同步 | lark-doc, lark-wiki |
| **sync-cross-platform-rules** | 跨平台同步管线/冲突解决/回滚/一致性 | 全量/增量/一致性扫描 | lark-doc, lark-wiki, showdoc MCP |
| **doc-governance** | 文档生命周期/版本号传播/审计闭环/sync_registry | 版本发布/里程碑更新/审计 | 所有 L2 引擎 |

**Gateway Skill 核心职责**:
1. **意图解析**: 判断用户请求属于哪个文档类别 (C1-C10)
2. **权威源路由**: 根据类别决定写入方向 (Git→ShowDoc→飞书 vs 飞书→ShowDoc)
3. **安全校验**: 强制执行 19 项安全 Markdown 子集
4. **注册表维护**: 读写 `sync_registry.yaml`，确保每次操作都有记录
5. **保护标注**: 在飞书文档顶部注入同步标注
6. **引擎调用**: 将验证通过的操作委托给 L2 引擎执行

### 3.2 Layer 2: Engine（内部服务 Skill）

| Skill | 职责范围 | 约束 |
|-------|---------|------|
| **lark-doc** | 飞书云文档的 create/fetch/update | 禁止用户直接创建/编辑文档；禁止跳过保护标注注入 |
| **lark-wiki** | 飞书知识库节点管理 | 禁止用户直接创建知识空间；必须通过 sync_registry |
| **lark-drive** | 飞书云空间文件管理 (上传/下载/移动) | 禁止绕过内容校验直接上传 |
| **wiki** | Factory Wiki 生成与上传 | 仅限内部调用，不直接面向用户 |
| **docx** | Word 文档创建/读取/编辑 | 仅限内部调用，不直接面向用户 |

**Engine Skill 核心约束**:
```
CONSTRAINTS FOR ALL L2 ENGINE SKILLS:
  1. NO direct user triggering — descriptions must say "INTERNAL SERVICE"
  2. NO document creation/editing APIs exposed to other skills
  3. NO bypass of sync_registry.yaml — every write must be logged
  4. NO skip of protection banners — feishu docs must have sync_info header
  5. NO format outside 19-element safety subset when syncing
  6. NO decision-making — only execute what L1 Gateway instructs
```

### 3.3 Layer 3: Transport（底层工具）

| 工具 | 职责 | 调用者 |
|------|------|--------|
| **lark-cli** | 飞书 API 的 CLI 封装 | L1 Gateway, L2 Engine |
| **ShowDoc MCP** | ShowDoc API 的 MCP 工具集 | L1 Gateway, L2 Engine |
| **git** | 版本控制/内容来源 | L1 Gateway |

---

## 4. 触发控制机制

### 4.1 Skill Description Narrowing（技能描述收窄）

这是最关键的第一道防线。每个 L2 Engine Skill 的描述必须加入以下语言：

**lark-doc / lark-wiki / lark-drive / wiki / docx 的描述改造**:

```
BEFORE (当前):
  "飞书云文档 / Docx / 知识库 Wiki 文档（v2）：创建、打开、读取、获取、
   查看、总结、提取文档内容..."

AFTER (改造后):
  "⚠️ INTERNAL SERVICE — 不应被用户直接触发。
   仅供 showdoc-markdown-compat、feishu-platform-rules、
   sync-cross-platform-rules、doc-governance 等 Gateway Skills
   调用，执行飞书文档/知识库的底层 create/read/update 操作。
   用户如需创建/编辑文档，请使用上述 Gateway Skills。
   
   [原有功能描述保持不变...]"
```

**showdoc-markdown-compat / showdoc-platform-rules / feishu-platform-rules / sync-cross-platform-rules / doc-governance 的描述强化**:

```
AFTER (强化后):
  "🔑 PRIMARY ENTRY POINT — 用户可直接触发的文档同步/管理入口。
   负责 [具体职责]，并通过 Gateway Pattern 调用底层引擎完成操作。
   所有文档写入操作必须经由此 Skill 校验和路由。
   
   [原有功能描述保持不变...]"
```

### 4.2 Conditional Routing Rules（条件路由规则）

在 Gateway Skill 的描述中嵌入路由决策树：

```
ROUTING DECISION TREE (嵌入到 sync-cross-platform-rules):
  用户请求 → 判断类别:
    ├─ "写/创建文档" → 判断文档类型:
    │   ├─ API 文档 (C3) → showdoc-platform-rules → ShowDoc MCP
    │   ├─ 技术规范 (C2) → doc-governance → Git → showdoc-platform-rules
    │   └─ 会议纪要 (C9) → feishu-platform-rules → lark-doc
    ├─ "同步到飞书" → sync-cross-platform-rules → lark-doc/lark-wiki
    ├─ "检查一致性" → sync-cross-platform-rules → 三方对比
    ├─ "版本发布" → doc-governance → 全流程
    └─ "Markdown 兼容" → showdoc-markdown-compat → 规则校验

CALLER IDENTITY CHECK (L1 内部逻辑):
  当 Gateway Skill 调用 L2 Engine 时:
    1. 先校验 sync_registry 存在性
    2. 确认内容符合安全子集
    3. 注入保护标注 header
    4. 然后才调用 L2 引擎
```

### 4.3 Explicit Trigger Precedence（显式触发优先级）

在 `doc-governance` skill 中定义明确的触发优先级矩阵：

```yaml
# trigger_precedence.yaml (嵌入到 doc-governance skill)
trigger_precedence:
  # 优先级 1: Gateway Skills — 允许用户直接触发
  gateway:
    - showdoc-markdown-compat
    - showdoc-platform-rules
    - feishu-platform-rules
    - sync-cross-platform-rules
    - doc-governance

  # 优先级 2: Engine Skills — 仅允许内部调用
  engine_internal_only:
    - lark-doc
    - lark-wiki
    - lark-drive
    - wiki
    - docx

  # 优先级 3: Transport — 无限制 (被 L1/L2 调用)
  transport:
    - lark-cli
    - showdoc MCP
    - git
```

### 4.4 Protection Banner Enforcement（保护标注强制注入）

Gateway 在调用 L2 引擎写入飞书前，必须注入保护标注：

```markdown
<!-- sync_info: managed_by=sync-cross-platform-rules, authority=<权威源>, last_sync=YYYY-MM-DD -->

> 📋 **本文档由同步管线自动管理**
> - 修改请通过 Gateway Skills (showdoc-platform-rules / sync-cross-platform-rules)
> - 权威源: <Git/ShowDoc>
> - 请勿直接编辑
```

如果 L2 引擎尝试写入没有保护标注的飞书文档，Gateway 应拒绝执行并告警。

---

## 5. 调用流时序图

### 5.1 用户创建 API 文档 (Gateway → Engine → Transport)

```
User                    Gateway Skill                 Engine (L2)            Transport (L3)
 │                         │                              │                      │
 │ "创建 API 文档"          │                              │                      │
 │────────────────────────>│                              │                      │
 │                         │ 1. 解析: C3 类别              │                      │
 │                         │    权威源 = ShowDoc           │                      │
 │                         │ 2. 校验: 安全 Markdown 子集   │                      │
 │                         │    (showdoc-markdown-compat)  │                      │
 │                         │ 3. 生成内容                   │                      │
 │                         │                              │                      │
 │                         │ 4. 写入 ShowDoc               │                      │
 │                         │─────────────────────────────>│                      │
 │                         │                              │ MCP upsert_page      │
 │                         │                              │─────────────────────>│
 │                         │<─────────────────────────────│<─────────────────────│
 │                         │    page_id 返回               │                      │
 │                         │                              │                      │
 │                         │ 5. 同步到飞书                 │                      │
 │                         │    注入保护标注                │                      │
 │                         │    内容转换 (移除 [TOC] 等)    │                      │
 │                         │                              │                      │
 │                         │ 6. 调用 lark-doc (L2)         │                      │
 │                         │─────────────────────────────>│                      │
 │                         │                              │ docs +create (v2)    │
 │                         │                              │─────────────────────>│
 │                         │<─────────────────────────────│<─────────────────────│
 │                         │    feishu_doc_id 返回         │                      │
 │                         │                              │                      │
 │                         │ 7. 更新 sync_registry.yaml    │                      │
 │                         │ 8. 创建审计记录                │                      │
 │<────────────────────────│                              │                      │
 │ "文档已创建: ShowDoc    │                              │                      │
 │  page_id=XXX,           │                              │                      │
 │  飞书 doc=YYY"          │                              │                      │
```

### 5.2 用户同步到飞书

```
User                    Gateway Skill                 Engine (L2)            Transport (L3)
 │                         │                              │                      │
 │ "同步 memory-core       │                              │                      │
 │  文档到飞书"             │                              │                      │
 │────────────────────────>│                              │                      │
 │                         │ 1. 读取 sync_registry.yaml    │                      │
 │                         │ 2. 确定同步范围               │                      │
 │                         │ 3. 逐页读取 ShowDoc            │                      │
 │                         │    (MCP get_page)             │                      │
 │                         │ 4. 内容转换 + 安全子集校验     │                      │
 │                         │ 5. 注入保护标注                │                      │
 │                         │                              │                      │
 │                         │ 6. 调用 lark-doc/lark-wiki    │                      │
 │                         │─────────────────────────────>│                      │
 │                         │                              │ docs +update/        │
 │                         │                              │ create               │
 │                         │                              │─────────────────────>│
 │                         │<─────────────────────────────│<─────────────────────│
 │                         │    逐页确认                   │                      │
 │                         │                              │                      │
 │                         │ 7. 批量验证 (读取飞书对比)     │                      │
 │                         │ 8. 更新 sync_registry          │                      │
 │                         │ 9. 创建审计记录                │                      │
 │<────────────────────────│                              │                      │
 │ "已同步 N 页, M 页失败   │                              │                      │
 │  (详见审计报告)"         │                              │                      │
```

---

## 6. 实施 Checklist

### Phase 1: Skill 描述改造 (P0 — 立即执行)

- [ ] **1.1** 修改 `lark-doc` skill 描述：添加 `⚠️ INTERNAL SERVICE` 前缀
  - 添加"仅供 Gateway Skills 调用"说明
  - 添加"用户请使用 Gateway Skills"引导
- [ ] **1.2** 修改 `lark-wiki` skill 描述：同上
- [ ] **1.3** 修改 `lark-drive` skill 描述：同上
- [ ] **1.4** 修改 `wiki` skill 描述：添加 `⚠️ INTERNAL SERVICE` 前缀
- [ ] **1.5** 修改 `docx` skill 描述：添加 `⚠️ INTERNAL SERVICE` 前缀
- [ ] **1.6** 修改 `showdoc-markdown-compat` skill 描述：添加 `🔑 PRIMARY ENTRY POINT` 标记
- [ ] **1.7** 修改 `showdoc-platform-rules` skill 描述：同上
- [ ] **1.8** 修改 `feishu-platform-rules` skill 描述：同上
- [ ] **1.9** 修改 `sync-cross-platform-rules` skill 描述：同上
- [ ] **1.10** 修改 `doc-governance` skill 描述：同上 + 嵌入 trigger_precedence 矩阵

### Phase 2: Gateway 规则增强 (P0 — 与 Phase 1 并行)

- [ ] **2.1** 在 `sync-cross-platform-rules` 中嵌入路由决策树 (见 §4.2)
- [ ] **2.2** 在 `doc-governance` 中定义 trigger_precedence 矩阵 (见 §4.3)
- [ ] **2.3** 在 `showdoc-markdown-compat` 中强化安全子集校验规则
  - 写入前校验
  - 写入后验证
  - 违规拒绝策略
- [ ] **2.4** 在 `feishu-platform-rules` 中定义保护标注模板 (见 §4.4)
  - 标注格式标准化
  - 强制注入检查点
  - 缺失标注的拒绝策略

### Phase 3: sync_registry 强化 (P1)

- [ ] **3.1** 在 `sync_registry.yaml` 中增加 `last_gateway_call` 字段
- [ ] **3.2** 在 `sync_registry.yaml` 中增加 `protection_banner_injected` 布尔字段
- [ ] **3.3** 在 `sync_registry.yaml` 中增加 `safety_subset_verified` 布尔字段
- [ ] **3.4** 编写 sync_registry 校验脚本 (Python)，在 CI 中检查合规性

### Phase 4: 审计闭环 (P1)

- [ ] **4.1** 定义 Gateway 调用审计日志格式
  - 调用者 identity
  - 调用时间
  - 调用目标 (L2 引擎 + L3 工具)
  - 校验结果 (安全子集/注册表/保护标注)
  - 执行结果
- [ ] **4.2** 每次 Gateway 调用自动写入审计日志
- [ ] **4.3** 编写审计日志汇总脚本

### Phase 5: 验证与测试 (P2)

- [ ] **5.1** 测试场景：用户直接请求 lark-doc 创建文档
  - 预期：被 L2 的 INTERNAL SERVICE 描述阻止，引导至 Gateway
- [ ] **5.2** 测试场景：用户通过 Gateway 创建文档
  - 预期：完整管线执行 (校验→注入→写入→验证→审计)
- [ ] **5.3** 测试场景：无保护标注的飞书文档尝试同步
  - 预期：Gateway 拒绝执行，要求先注入标注
- [ ] **5.4** 测试场景：不符合安全子集的内容尝试写入
  - 预期：Gateway 拒绝，返回违规项列表
- [ ] **5.5** 测试场景：sync_registry 中不存在的文档尝试同步
  - 预期：Gateway 拒绝，要求先注册

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **Skill 描述修改不影响已有触发行为** | 中 | 高 | Agent 的 skill 匹配主要依赖描述文本，收窄描述是最有效的控制手段 |
| **其他 Agent/用户绕过 Gateway 直接调用 CLI** | 低 | 中 | sync_registry 校验 + 审计日志监控可检测异常调用 |
| **保护标注被意外覆盖** | 中 | 中 | Gateway 在每次写入前检查并重新注入 |
| **性能开销** | 低 | 低 | 校验步骤在文档同步场景下耗时可忽略 (<1s) |

---

## 8. 迁移路径

```
当前状态 (所有 skill 平等)
  │
  ▼
Step 1: 修改 Skill 描述 (Phase 1)
  │  → 5 个 Engine Skill 标记为 INTERNAL
  │  → 5 个 Gateway Skill 标记为 PRIMARY
  │
  ▼
Step 2: 增强 Gateway 规则 (Phase 2)
  │  → 路由决策树
  │  → 触发优先级
  │  → 安全校验
  │  → 保护标注
  │
  ▼
Step 3: 强化注册表 (Phase 3)
  │  → 校验字段
  │  → CI 检查
  │
  ▼
Step 4: 审计闭环 (Phase 4)
  │  → 审计日志
  │  → 异常检测
  │
  ▼
Step 5: 验证测试 (Phase 5)
  │  → 5 个测试场景
  │  → 修复发现的问题
  │
  ▼
目标状态 (3 层隔离架构上线)
```

---

## 附录 A: 关键文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `~/.factory/skills/lark-doc/SKILL.md` | Skill 定义 | 需改造 (加 INTERNAL SERVICE) |
| `~/.factory/skills/lark-wiki/SKILL.md` | Skill 定义 | 需改造 |
| `~/.factory/skills/lark-drive/SKILL.md` | Skill 定义 | 需改造 |
| `~/.factory/skills/wiki/SKILL.md` | Skill 定义 | 需改造 |
| `~/.factory/skills/docx/SKILL.md` | Skill 定义 | 需改造 |
| `~/.factory/skills/showdoc-markdown-compat/SKILL.md` | Skill 定义 | 需强化 (加 PRIMARY ENTRY POINT) |
| `~/.factory/skills/showdoc-platform-rules/SKILL.md` | Skill 定义 | 需强化 |
| `~/.factory/skills/feishu-platform-rules/SKILL.md` | Skill 定义 | 需强化 |
| `~/.factory/skills/sync-cross-platform-rules/SKILL.md` | Skill 定义 | 需强化 + 嵌入路由树 |
| `~/.factory/skills/doc-governance/SKILL.md` | Skill 定义 | 需强化 + 嵌入优先级矩阵 |
| `docs/sync_registry.yaml` | 配置 | 需增加校验字段 |
| `docs/audit/` | 审计 | 新增审计日志目录 |

## 附录 B: Skill 位置说明

当前 `.factory/skills/` 目录为空。所有 skill 定义存在于全局位置 (`~/.factory/skills/`)。改造需要修改全局 skill 定义文件，或在项目本地 `.factory/skills/` 中创建覆盖版本。
