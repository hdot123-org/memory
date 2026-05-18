# ShowDoc↔飞书 主从同步方案

> 版本: 2.0.0 | 创建: 2026-05-16 | 更新: 2026-05-16 | 状态: draft
> 权威源: 本文档为设计文档，权威源为 Git
>
> **v2.0.0 修订说明**: 基于实测数据（24元素 roundtrip + ShowDoc 渲染验证）全面修订。
> - 缩小为 19 项实测确认的安全 Markdown 子集
> - 确认单向同步：ShowDoc → 飞书（飞书为只读镜像）
> - 不需要反向同步，不需要导出
> - 文档从 H2 起头，不使用图片/表格对齐/嵌套引用
> - 公式保留（写入飞书正确渲染）

---

## 1. 三层权威架构

### 1.1 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: Git (SSOT)                                          │
│ 角色: 代码行为/配置/Schema/规范的唯一真相源                      │
│ 存储: 仓库文件系统 (.md, .py, .toml, .json)                   │
│ 变更方式: git commit + PR                                     │
├──────────────────────────────────────────────────────────────┤
│ Layer 2: ShowDoc (Team Hub)                                  │
│ 角色: 团队文档中枢，结构化展示层，API 文档权威源                   │
│ 存储: ShowDoc 平台页面 (item_id per project)                  │
│ 变更方式: MCP API / Web UI                                    │
├──────────────────────────────────────────────────────────────┤
│ Layer 3: 飞书 (Read Mirror)                                  │
│ 角色: 团队只读镜像（不需要反向同步，不需要导出）                  │
│ 存储: 飞书云文档 (docx/wiki)                                   │
│ 变更方式: lark-cli docs +create/+update (v2 API)               │
│ 同步方向: ShowDoc → 飞书（单向）                                │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 各层角色定义

| 层级 | 平台 | 职责 | 可写场景 | 只读场景 |
|------|------|------|---------|---------|
| **L1 Git** | 仓库 | 代码/规范/schema 权威源 | 所有代码驱动的文档 | — |
| **L2 ShowDoc** | ShowDoc 平台 | API 文档权威源 + 团队展示 | API 文档、计划页、Python API 文档 | 从 Git 同步来的规范 |
| **L3 飞书** | 飞书云文档 | 只读镜像 | 无 | 从 ShowDoc 同步来的所有内容（不需要反向同步） |

### 1.3 核心原则

1. **单向数据流**: Git → ShowDoc → 飞书，不需要逆流
2. **飞书不是权威源**: 飞书仅为只读展示镜像
3. **最终一致性**: 三个平台不需要实时一致，但触发同步后必须保证最终一致
4. **安全 Markdown 子集**: 同步必须使用 showdoc-feishu-markdown-compat v2.0 定义的 19 项安全子集
5. **不需要导出**: 不从飞书导出 Markdown，不需要反向同步

---

## 2. 文档分类与权威源映射

### 2.1 文档类型分类

根据 doc-management skill 的 4 层架构，将文档分为以下同步类别：

| 类别编号 | 文档类型 | 示例 | 权威源 | 同步方向 | 飞书行为 |
|---------|---------|------|--------|---------|---------|
| **C1** | 源代码行为/配置/Schema | constants.py 行为、adapter_toml_schema、HookEvent 字段 | **Git (L1)** | Git → ShowDoc → 飞书 | 只读镜像 |
| **C2** | 规范文档 (L2 Spec) | DOT_MEMORY_SPEC.md、MEMORY_LOCK_SPEC.md、API-CONTRACT.md | **Git (L1)** | Git → ShowDoc → 飞书 | 只读镜像 |
| **C3** | API 文档 | 请求URL/参数/返回示例 | **ShowDoc (L2)** | ShowDoc → 飞书 | 只读镜像 |
| **C4** | Python API 文档/用户手册 | hook_event docstring、CoreConfig 说明 | **ShowDoc (L2)** | ShowDoc → Git 摘要 → 飞书 | 只读镜像 |
| **C5** | 计划页 | PLAN-STATUS.md、ShowDoc 计划页 | **双向 (L1↔L2)** | Git ↔ ShowDoc → 飞书 | 只读镜像 |
| **C6** | CLI 命令参考 | memory-init、memory-migrate、memory-validate | **Git (L1)** | Git → ShowDoc → 飞书 | 只读镜像 |
| **C7** | 架构设计文档 | design/01-architecture.md ~ 10-consumer-boundary.md | **Git (L1)** | Git → ShowDoc → 飞书 | 只读镜像 |
| **C8** | CHANGELOG / Release Notes | CHANGELOG.md | **Git (L1)** | Git → ShowDoc → 飞书 | 只读镜像 |
| **C9** | 会议纪要/团队讨论 | 飞书会议记录 | **飞书 (L3)** | 飞书 → ShowDoc 摘要 | 可写 |
| **C10** | 运维手册/操作指南 | APISIX 运维手册、故障排查 | **Git (L1)** | Git → ShowDoc → 飞书 | 只读镜像 |

### 2.2 现有 ShowDoc 项目文档映射

#### APISIX 网关文档 (item_id=664858315)

| 目录 | 文档类型 | 类别 | 权威源 |
|------|---------|------|--------|
| 架构与概览 | 架构文档 | C7 | Git → ShowDoc → 飞书 |
| 路由配置 | 配置/行为文档 | C1 | Git → ShowDoc → 飞书 |
| 上游服务 | 配置/行为文档 | C1 | Git → ShowDoc → 飞书 |
| 认证与安全 | 规范文档 | C2 | Git → ShowDoc → 飞书 |
| 插件策略 | 配置/行为文档 | C1 | Git → ShowDoc → 飞书 |
| 运维手册 | 操作指南 | C10 | Git → ShowDoc → 飞书 |

#### memory-core 文档 (item_id=664858316)

| 目录 | 文档类型 | 类别 | 权威源 |
|------|---------|------|--------|
| 项目概览 | 架构文档 | C7 | Git → ShowDoc → 飞书 |
| 快速开始与教程 | 用户手册 | C4 | ShowDoc → 飞书 |
| CLI 命令参考 | CLI 文档 | C6 | Git → ShowDoc → 飞书 |
| 配置规范 | 规范文档 | C2 | Git → ShowDoc → 飞书 |
| 架构设计 | 设计文档 | C7 | Git → ShowDoc → 飞书 |
| Python API 文档 | API 文档 | C4 | ShowDoc → 飞书 |
| Schema 与数据格式 | Schema 文档 | C1 | Git → ShowDoc → 飞书 |
| 边界与安全 | 规范文档 | C2 | Git → ShowDoc → 飞书 |
| 测试与CI | 操作指南 | C10 | Git → ShowDoc → 飞书 |

#### Factory Droid 功能文档 (item_id=664858317)

| 目录 | 文档类型 | 类别 | 权威源 |
|------|---------|------|--------|
| 核心配置 | 配置文档 | C1 | Git → ShowDoc → 飞书 |
| 高级功能 | 功能文档 | C4 | ShowDoc → 飞书 |
| 集成与部署 | 操作指南 | C10 | Git → ShowDoc → 飞书 |
| 更新日志 | CHANGELOG | C8 | Git → ShowDoc → 飞书 |

### 2.3 飞书文档结构设计

在飞书侧，按项目建立知识空间（Wiki Space），目录结构镜像 ShowDoc：

```
飞书知识空间: [项目名] 文档镜像
├── 📁 APISIX 网关文档/
│   ├── 架构与概览.md       (mirror of ShowDoc cat 436353036)
│   ├── 路由配置.md         (mirror of ShowDoc cat 436353038)
│   ├── 上游服务.md         (mirror of ShowDoc cat 436353037)
│   ├── 认证与安全.md       (mirror of ShowDoc cat 436353039)
│   ├── 插件策略.md         (mirror of ShowDoc cat 436353041)
│   └── 运维手册.md         (mirror of ShowDoc cat 436353040)
├── 📁 memory-core 文档/
│   ├── 项目概览.md         (mirror of ShowDoc cat 436353042)
│   ├── 快速开始与教程.md    (mirror of ShowDoc cat 436353043)
│   ├── CLI 命令参考.md      (mirror of ShowDoc cat 436353045)
│   ├── 配置规范.md         (mirror of ShowDoc cat 436353044)
│   ├── 架构设计.md         (mirror of ShowDoc cat 436353046)
│   ├── Python API 文档.md  (mirror of ShowDoc cat 436353049)
│   ├── Schema 与数据格式.md (mirror of ShowDoc cat 436353047)
│   ├── 边界与安全.md       (mirror of ShowDoc cat 436353048)
│   └── 测试与CI.md         (mirror of ShowDoc cat 436353050)
├── 📁 Factory Droid 文档/
│   ├── 核心配置.md         (mirror of ShowDoc cat 436353051)
│   ├── 高级功能.md         (mirror of ShowDoc cat 436353054)
│   ├── 集成与部署.md       (mirror of ShowDoc cat 436353053)
│   └── 更新日志.md         (mirror of ShowDoc cat 436353052)
├── 📁 团队协作/             (飞书独有，不同步回 ShowDoc)
│   ├── 会议纪要/
│   ├── 讨论记录/
│   └── 反馈收集/
└── README.md               (同步说明页)
```

---

## 3. 同步流程

### 3.1 Git → ShowDoc → 飞书（技术文档流）

**适用类别**: C1, C2, C6, C7, C8, C10

```
Step 1: Git 变更触发
  ├── 开发者 git push
  ├── 或 Agent 完成代码修改
  └── 触发条件: 版本号变更 / L2 Spec 变更 / CLI 行为变更

Step 2: Git → ShowDoc 同步
  ├── 读取 Git 文件内容
  ├── 转换为 ShowDoc 格式 (加 [TOC]、调整标题层级)
  ├── showdoc___upsert_page 写入/更新
  ├── 记录同步到 docs/audit/showdoc-sync-YYYY-MM-DD.md
  └── 等待 ShowDoc 写入确认

Step 3: ShowDoc → 飞书同步
  ├── 从 ShowDoc 读取已写入的页面 (showdoc___get_page)
  ├── 执行飞书兼容转换:
  │   ├── 移除 [TOC] 标记
  │   ├── 确保使用安全 Markdown 子集
  │   ├── 表格移除对齐标记 (:---:)
  │   └── 验证无飞书不支持元素
  ├── lark-cli docs +update --mode overwrite 写入飞书
  │   (首次使用 lark-cli docs +create 创建文档)
  └── 记录飞书文档 token 映射关系

Step 4: 验证闭环
  ├── lark-cli docs +fetch 读取飞书文档
  ├── 对比 ShowDoc 内容 (忽略 [TOC] 差异)
  ├── 确认结构完整性
  └── 更新同步记录状态
```

**数据流示意**:
```
Git file.md
  → [showdoc___upsert_page] → ShowDoc page
  → [content transform] → Safe Markdown
  → [lark-cli docs +update] → 飞书 doc
```

### 3.2 ShowDoc → 飞书（计划/操作文档流）

**适用类别**: C3, C4, C5 (ShowDoc→飞书方向)

```
Step 1: ShowDoc 内容变更
  ├── 团队成员在 ShowDoc 编辑
  ├── Agent 更新计划页状态
  └── 触发条件: 计划状态变更 / API 文档更新 / 里程碑完成

Step 2: ShowDoc 内容读取
  ├── showdoc___get_page 获取最新内容
  ├── 记录 page_id、last_update_time、content_hash
  └── 与上次同步记录比对，判断是否有变更

Step 3: 飞书兼容转换
  ├── 移除 [TOC]
  ├── 移除 ShowDoc API 模板格式 (转为标准表格+代码块)
  ├── 验证安全 Markdown 子集合规性
  └── 执行验证清单 (见 §3.4)

Step 4: 飞书写入
  ├── 已有文档: lark-cli docs +update --mode overwrite
  ├── 新文档: lark-cli docs +create --wiki-space <space_id>
  └── 记录/更新飞书 token 映射

Step 5: 同步记录更新
  ├── 更新 sync_registry.yaml (见 §3.3)
  ├── 记录同步时间戳
  └── 写入审计记录
```

### 3.3 飞书 → ShowDoc（团队协作反馈流）

**适用类别**: C9 (会议纪要/讨论), C5 (计划页飞书侧修改)

```
Step 1: 飞书内容变更检测
  ├── 团队成员在飞书添加评论或修改协作区文档
  ├── 定期扫描飞书文档更新时间 (手动触发)
  └── 仅对 C9 类别和 C5 计划页允许飞书→ShowDoc

Step 2: 飞书内容读取
  ├── lark-cli docs +fetch --doc <token>
  ├── 获取 Markdown 内容
  └── 记录变更部分

Step 3: 反向兼容转换
  ├── 过滤飞书独有标签 (<callout>, <grid>, <lark-table>)
  ├── <callout emoji="💡"> → > 💡 引用块
  ├── <grid cols="2"> → 并列表格
  ├── <lark-table> → 标准 Markdown 表格
  └── 确保使用安全 Markdown 子集

Step 4: ShowDoc 写入
  ├── showdoc___update_page 写入
  ├── 添加变更标记: <!-- synced from feishu YYYY-MM-DD -->
  └── 如为 C5 类别，同步更新 PLAN-STATUS.md

Step 5: 验证与记录
  ├── showdoc___get_page 验证写入
  ├── 更新同步记录
  └── 通知团队成员
```

### 3.4 同步注册表（sync_registry.yaml）

维护一份同步状态注册表，记录每个文档在三个平台间的映射关系：

```yaml
# sync_registry.yaml — 文档同步注册表
# 位置: docs/sync_registry.yaml

version: "1.0"
last_updated: "2026-05-16"

projects:
  - showdoc_item_id: 664858315
    showdoc_item_name: "APISIX 网关文档"
    feishu_wiki_space: null  # 待创建
    sync_enabled: true
    pages:
      - showdoc_page_id: null
        showdoc_page_title: "APISIX 架构概览"
        showdoc_cat_id: 436353036
        git_source: "docs/apisix/architecture.md"
        feishu_doc_id: null
        doc_category: C7
        authority: git
        sync_direction: "git→showdoc→feishu"
        last_showdoc_sync: null
        last_feishu_sync: null
        content_hash: null

  - showdoc_item_id: 664858316
    showdoc_item_name: "memory-core 文档"
    feishu_wiki_space: null  # 待创建
    sync_enabled: true
    pages:
      - showdoc_page_id: 269622139
        showdoc_page_title: "Alpha → Beta/Stable 质量加固计划"
        showdoc_cat_id: null
        git_source: "docs/PLAN-STATUS.md"
        feishu_doc_id: null
        doc_category: C5
        authority: bidirectional
        sync_direction: "git↔showdoc→feishu"
        last_showdoc_sync: "2026-05-14"
        last_feishu_sync: null
        content_hash: null

  - showdoc_item_id: 664858317
    showdoc_item_name: "Factory Droid 功能文档"
    feishu_wiki_space: null  # 待创建
    sync_enabled: true
    pages: []  # 待注册
```

### 3.5 内容转换管线

```
┌─────────────────────────────────────────────────────────────┐
│                    内容转换管线                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Git Markdown ──→ ShowDoc 格式                              │
│  │  ├── 检查是否需要 [TOC]                                   │
│  │  ├── 确保 ShowDoc API 文档模板格式 (C3/C4)                │
│  │  └── 验证代码块标注语言                                    │
│  │                                                          │
│  ShowDoc 内容 ──→ 飞书安全 Markdown                          │
│  │  ├── 移除 [TOC]                                          │
│  │  ├── 转换 ShowDoc API 模板 → 标准表格+代码块               │
│  │  ├── 移除表格对齐标记 (:---:/:---/---:)                    │
│  │  ├── 确保列表 2 空格缩进                                   │
│  │  └── 验证无锚点链接                                       │
│  │                                                          │
│  飞书内容 ──→ ShowDoc 格式                                   │
│     ├── <callout> → > 引用块                                 │
│     ├── <grid> → 并列表格                                    │
│     ├── <lark-table> → 标准 Markdown 表格                    │
│     ├── 移除 <text color="">                                 │
│     ├── 移除 {color=""} {align=""} 属性                      │
│     └── 确保标题 ≤ H6                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 触发机制

### 4.1 触发方式总览

| 触发方式 | 方向 | 适用场景 | 自动化程度 | 实现方式 |
|---------|------|---------|-----------|---------|
| **版本发布触发** | Git→ShowDoc→飞书 | 版本号变更/发布 | 半自动 | Agent 检测 + 手动确认 |
| **Agent 闭环触发** | Git↔ShowDoc→飞书 | 子代理完成任务后 | 自动 | doc-management skill 自动检测 |
| **定时同步** | ShowDoc→飞书 | 定期全量同步 | 手动触发 | Agent 执行同步命令 |
| **手动单页同步** | 任意方向 | 单篇文档更新 | 手动 | 用户指定文档 ID |
| **飞书反馈触发** | 飞书→ShowDoc | 评论/协作修改 | 手动 | 用户或 Agent 检测 |

### 4.2 自动触发详细规则

#### 版本发布触发 (Git → ShowDoc → 飞书)

```
触发条件:
  - constants.py 版本号变更
  - pyproject.toml 版本号变更
  - 用户说 "commit" / "push" / "发布" / "release"

执行流程:
  1. 检测版本号变更
  2. 扫描所有 C1/C2/C6/C7/C8 类别文档
  3. 对比 Git 文件与 ShowDoc 页面的 content_hash
  4. 仅同步有变更的文档
  5. 同步到飞书
  6. 创建审计记录

触发频率: 按需 (通常每次发布一次)
预估时间: 15-30 分钟 (视文档数量)
```

#### Agent 闭环触发 (Git ↔ ShowDoc → 飞书)

```
触发条件:
  - 子代理 todo 从 in_progress 变为 completed
  - 会话中创建了 ShowDoc 页面或更新了内容

执行流程:
  1. 回写 ShowDoc 计划页 (showdoc___update_page)
  2. 更新 PLAN-STATUS.md
  3. 检查是否需要飞书同步
  4. 如需要，执行 ShowDoc→飞书同步
  5. 输出闭环报告

触发频率: 每次子代理任务完成
预估时间: 5-10 分钟
```

### 4.3 手动触发命令

```bash
# 全量同步 (ShowDoc → 飞书)
# Agent 执行: 读取 sync_registry.yaml → 遍历所有 pages → 逐一同步
# 用户说: "同步所有文档到飞书"

# 单项目同步
# Agent 执行: 读取指定 item_id 的所有页面 → 同步
# 用户说: "同步 memory-core 文档到飞书"

# 单页同步
# Agent 执行: 读取指定 page_id → 转换 → 写入飞书
# 用户说: "同步这个页面到飞书" + 提供 page_id

# 反向同步 (飞书 → ShowDoc)
# Agent 执行: 读取飞书文档 → 转换 → 写入 ShowDoc
# 用户说: "把飞书的会议纪要同步回 ShowDoc"
```

### 4.4 不采用实时自动同步的原因

1. **API 限制**: 飞书文档 API 有 QPS 限制，批量同步可能触发限流
2. **变更频率**: 技术文档变更不频繁，无需实时同步
3. **一致性风险**: 实时同步增加冲突概率，手动触发可控性更高
4. **审批需求**: 文档发布通常需要人工确认

---

## 5. 冲突解决策略

### 5.1 冲突检测

```yaml
# 冲突检测规则
conflict_detection:
  method: content_hash_comparison
  hash_algorithm: sha256
  
  # 在同步前，比较目标平台的 content_hash 与上次同步记录的 hash
  # 如果两者不一致，且源端也发生了变更，则判定为冲突
  
  detection_flow:
    - step: 1
      action: "读取源端内容，计算 hash"
    - step: 2
      action: "读取目标端内容，计算 hash"
    - step: 3
      action: "比较两者与 sync_registry 中的 last_hash"
    - step: 4
      action: "仅源端变更 → 正常同步"
    - step: 5
      action: "仅目标端变更 → 提醒但不覆盖 (飞书侧)"
    - step: 6
      action: "两端都变更 → 冲突，进入解决流程"
```

### 5.2 冲突场景与解决策略

| 场景 | 冲突类型 | 解决策略 | 具体操作 |
|------|---------|---------|---------|
| **S1** | Git 和 ShowDoc 同时修改同一文档 | 权威源优先 | Git 为权威源 → Git 内容覆盖 ShowDoc → 通知 ShowDoc 编辑者 |
| **S2** | ShowDoc 和飞书同时修改同一文档 | 权威源优先 | ShowDoc 为权威源 → ShowDoc 内容覆盖飞书 → 通知飞书编辑者 |
| **S3** | 飞书侧修改了 C1-C8 类别文档 | 权威源优先 | **忽略飞书变更**，下次同步覆盖。提前在飞书文档顶部标注: "本文档为自动同步镜像，请勿直接编辑。修改请前往 ShowDoc: <link>" |
| **S4** | 飞书侧修改了 C9 类别文档 | 飞书优先 | 正常回传 ShowDoc |
| **S5** | 飞书侧修改了 C5 计划页 | 合并 | 手动合并，标记冲突段落，通知双方编辑者 |
| **S6** | 同步过程中网络中断 | 一致性 | 回滚到同步前状态，记录失败，等待重试 |

### 5.3 冲突解决流程

```
冲突检测
  │
  ├── 判定文档类别 (C1-C10)
  │
  ├── 类别为 C1-C8 (飞书只读)
  │   ├── 权威源 (Git/ShowDoc) 内容覆盖
  │   ├── 通知飞书编辑者变更被覆盖
  │   └── 记录冲突到审计日志
  │
  ├── 类别为 C9 (飞书可写)
  │   ├── 飞书内容优先
  │   ├── 同步到 ShowDoc
  │   └── 记录同步
  │
  └── 类别为 C5 (双向)
      ├── 提取两端变更差异
      ├── 生成冲突报告 (diff 格式)
      ├── 通知用户手动解决
      ├── 等待用户确认后执行
      └── 记录解决过程
```

### 5.4 飞书文档保护标注

每篇同步到飞书的文档顶部必须添加:

```markdown
<!-- sync_info: source=showdoc, item_id=XXX, page_id=XXX, last_sync=YYYY-MM-DD -->

> 📋 **本文档为自动同步镜像**
> - 来源: ShowDoc [项目名] → [页面标题]
> - 最后同步: YYYY-MM-DD
> - **请勿直接编辑此文档**，修改请前往 [ShowDoc](<url>)
> - 如需协作讨论，请使用评论区或联系文档管理员
```

---

## 6. 失败回滚机制

### 6.1 同步失败分类

| 失败类型 | 严重程度 | 示例 | 处理方式 |
|---------|---------|------|---------|
| **F1 网络超时** | 低 | ShowDoc API 超时 | 自动重试 3 次，间隔 5s/15s/30s |
| **F2 API 限流** | 低 | 飞书 API QPS 超限 | 指数退避重试，最长等待 5 分钟 |
| **F3 格式转换失败** | 中 | Markdown 含不兼容元素 | 跳过当前页面，记录错误，继续其余页面 |
| **F4 权限不足** | 高 | 飞书文档无写入权限 | 终止同步，通知管理员 |
| **F5 内容校验失败** | 高 | 同步后读取内容不一致 | 回滚到同步前版本 |
| **F6 部分同步失败** | 中 | 10 页中 3 页失败 | 记录失败页面，成功的不回滚 |

### 6.2 回滚策略

```
同步开始前:
  1. 读取目标端当前内容 → 保存为 pre_sync_backup
  2. 记录 sync_registry 中的当前 hash

同步执行中:
  3. 逐页同步，每页记录结果
  4. 遇到 F1/F2 → 自动重试
  5. 遇到 F3 → 跳过并记录
  6. 遇到 F4/F5 → 触发回滚

回滚执行:
  7. 使用 pre_sync_backup 恢复目标端内容
  8. 对恢复后的内容进行校验
  9. 记录回滚操作到审计日志
  10. 通知同步失败并附带错误详情
```

### 6.3 审计日志格式

每次同步操作（成功或失败）都记录到 `docs/audit/` 目录:

```markdown
# 同步审计记录 - YYYY-MM-DD

## 同步信息

| 字段 | 值 |
|------|------|
| 同步方向 | ShowDoc → 飞书 |
| 触发方式 | 手动/自动 |
| 操作者 | Agent/User |
| 开始时间 | YYYY-MM-DD HH:MM:SS |
| 结束时间 | YYYY-MM-DD HH:MM:SS |
| 总耗时 | Xm Ys |

## 同步结果

| 页面 | 方向 | 状态 | 耗时 | 备注 |
|------|------|------|------|------|
| APISIX 架构概览 | ShowDoc→飞书 | ✅ success | 2s | |
| 路由配置 | ShowDoc→飞书 | ❌ failure | 5s | 格式转换失败: 含嵌套表格 |
| 认证与安全 | ShowDoc→飞书 | ✅ success | 1s | |

## 统计

- 成功: 2/3
- 失败: 1/3
- 跳过: 0/3

## 回滚操作

- 无需回滚 / 已回滚 [页面列表]

## 后续操作

- [ ] 修复路由配置页面格式
- [ ] 重新同步失败页面
```

---

## 7. 实施路线图

### Phase 1: 基础设施搭建 (1-2 天)

```
任务 1.1: 创建飞书知识空间
  - 为每个 ShowDoc 项目创建对应飞书知识空间
  - 或在一个知识空间下创建项目文件夹
  - 记录 wiki_space_id / folder_token
  
任务 1.2: 创建 sync_registry.yaml
  - 初始化同步注册表
  - 注册所有现有 ShowDoc 页面
  - 填入 showdoc_page_id 和 content_hash
  
任务 1.3: 更新 doc-management skill
  - 在现有 skill 中加入飞书维度
  - 定义飞书同步路由规则
  - 加入 sync_registry 维护规则
```

### Phase 2: 首次全量同步 (1 天)

```
任务 2.1: ShowDoc → 飞书首次同步
  - 按项目分批同步 (每批 5-10 页)
  - 每批完成后验证
  - 记录所有飞书文档 token
  
任务 2.2: 添加保护标注
  - 在每篇飞书文档顶部添加同步标注
  - 确保标注使用安全 Markdown 子集
  
任务 2.3: 建立审计基线
  - 创建首次同步审计记录
  - 记录所有页面的 content_hash
  - 更新 sync_registry.yaml
```

### Phase 3: 增量同步自动化 (2-3 天)

```
任务 3.1: 实现增量同步逻辑
  - 基于 content_hash 的变更检测
  - 仅同步有变更的页面
  
任务 3.2: 集成到 doc-management skill
  - 在版本发布触发中加入飞书同步步骤
  - 在 Agent 闭环触发中加入飞书同步步骤
  
任务 3.3: 实现 C9 反向同步
  - 飞书会议纪要 → ShowDoc
  - 格式转换逻辑
```

### Phase 4: 监控与优化 (持续)

```
任务 4.1: 同步健康检查
  - 定期检查三方一致性
  - 检测 stale 文档
  
任务 4.2: 性能优化
  - 批量同步优化
  - 增量检测优化
  
任务 4.3: 文档完善
  - 更新 doc-management skill 文档
  - 编写操作手册
```

---

## 8. 风险评估

### 8.1 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **飞书 API 限流** | 高 | 中 | 批量同步时控制 QPS ≤ 2/s，使用指数退避 |
| **格式转换丢失** | 中 | 高 | 同步前验证安全子集合规性；同步后读取验证 |
| **飞书文档 token 泄露** | 低 | 中 | token 存储在 sync_registry.yaml，不公开提交 |
| **大文档同步超时** | 中 | 低 | 分段同步，使用 docs +update --mode append 分段写入 |
| **飞书 overwrite 丢失评论** | 高 | 中 | 飞书文档标注为只读镜像，减少直接编辑；优先使用 append/replace |
| **飞书 API 不可用** | 低 | 高 | 降级为仅 ShowDoc 同步，飞书同步排队等待恢复 |

### 8.2 流程风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **团队成员直接编辑飞书文档** | 高 | 中 | 明确标注为只读镜像；同步时覆盖并通知 |
| **同步注册表不一致** | 中 | 高 | 每次同步前验证 sync_registry 完整性 |
| **三人协作冲突** | 低 | 中 | 权威源优先策略；冲突时通知用户 |
| **忘记触发同步** | 中 | 低 | 集成到 doc-management skill 自动检测 |

### 8.3 飞书特殊限制

| 限制 | 影响 | 应对策略 |
|------|------|---------|
| **飞书文档 API 不支持读取评论** | 无法自动同步评论回 ShowDoc | 评论仅在飞书查看，不回传 |
| **飞书 overwrite 模式清空文档** | 可能丢失图片、评论等 | 首次用 create，后续用 update replace_range/append |
| **飞书文档标题 800 字符限制** | 超长标题截断 | 标题保持在 100 字符内 |
| **飞书不支持锚点链接** | 目录内链接失效 | 飞书自动生成目录，无需手动锚点 |
| **飞书图片需单独处理** | 图片 token 无法直接迁移 | 同步时图片使用 URL 引用，不依赖 token |
| **lark-cli 认证需定期刷新** | 长时间不用可能过期 | 同步前检查认证状态，必要时重新登录 |

---

## 附录 A: 同步操作 Checklist

### A.1 首次同步 Checklist

- [ ] 飞书知识空间已创建，记录 wiki_space_id
- [ ] sync_registry.yaml 已初始化
- [ ] ShowDoc 所有页面已注册到 sync_registry
- [ ] lark-cli 认证已配置且有效
- [ ] 首次同步按项目分批执行
- [ ] 每批同步后执行飞书读取验证
- [ ] 飞书文档顶部已添加保护标注
- [ ] sync_registry.yaml 已更新所有 feishu_doc_id
- [ ] 审计记录已创建
- [ ] 首次同步报告已输出

### A.2 增量同步 Checklist

- [ ] 读取 sync_registry.yaml 获取当前状态
- [ ] 对比 ShowDoc 页面 content_hash 与注册表
- [ ] 仅同步有变更的页面
- [ ] 执行飞书兼容转换
- [ ] 写入飞书并验证
- [ ] 更新 sync_registry.yaml
- [ ] 创建审计记录

### A.3 反向同步 Checklist (飞书 → ShowDoc)

- [ ] 确认文档类别为 C9 或 C5
- [ ] 确认飞书文档有实际变更
- [ ] 执行反向格式转换
- [ ] 写入 ShowDoc 并验证
- [ ] 更新 sync_registry.yaml
- [ ] 通知相关团队成员

---

## 附录 B: 安全 Markdown 子集速查（v2.0，实测确认）

> 详见 showdoc-feishu-markdown-compat skill v2.0
> 实测依据: 2026-05-16, 24 元素 roundtrip + ShowDoc 渲染验证

```
✅ 安全子集（19项，双边100%）:
   ## ~ ###### 标题（H2起头，不用H1）
   **粗体** *斜体* ~~删除线~~ `代码` <u>下划线</u>
   - 列表 / 1. 列表 / - [ ] 待办（2空格缩进）
   > 引用（单层）
   | 表格 | 标准格式 |（无对齐标记）
   [链接](url)
   ```代码块```（标注语言）
   $公式$ / $$公式$$
   --- 分割线
   <!-- 注释 -->

❌ 禁止/不兼容:
   # H1 标题               → 飞书变为文档title
   [TOC]                   → 同步时过滤
   :---: 表格对齐           → 飞书丢弃对齐信息
   > > 嵌套引用             → 飞书扁平化
   ![图片](url)            → 飞书完全丢失
   <grid>                  → 两边不兼容
   <callout>               → 仅飞书渲染
   <text color>            → 仅飞书
   [链接](#anchor)         → 飞书不支持
```

---

## 附录 C: 相关工具与命令参考

### ShowDoc MCP 工具

| 工具 | 用途 |
|------|------|
| `showdoc___list_pages` | 获取项目页面列表 |
| `showdoc___get_page` | 读取页面内容 |
| `showdoc___update_page` | 更新页面 |
| `showdoc___upsert_page` | 按标题创建或更新 |
| `showdoc___search_pages` | 搜索页面 |

### 飞书 lark-cli 命令

| 命令 | 用途 |
|------|------|
| `lark-cli docs +create` | 创建飞书文档 |
| `lark-cli docs +fetch` | 获取飞书文档内容 |
| `lark-cli docs +update --mode overwrite` | 全文覆盖 (首次同步后慎用) |
| `lark-cli docs +update --mode replace_range` | 局部替换 (增量同步推荐) |
| `lark-cli docs +update --mode append` | 追加内容 |

### 关键配置文件

| 文件 | 用途 |
|------|------|
| `docs/sync_registry.yaml` | 同步状态注册表 (待创建) |
| `docs/audit/showdoc-sync-*.md` | 同步审计记录 |
| `docs/PLAN-STATUS.md` | 计划页本地镜像 |
| `~/.factory/skills/doc-management/SKILL.md` | 文档管理 skill 定义 |
| `~/.factory/skills/showdoc-feishu-markdown-compat/SKILL.md` | Markdown 兼容规则 |
