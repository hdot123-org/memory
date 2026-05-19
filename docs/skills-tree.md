# 文档治理 Skills 目录树

> 版本: 1.0.0 | 创建: 2026-05-19
> 本文档记录所有文档治理相关 Skills 的层级结构和职责。

---

## Skills 目录树

```
~/.factory/skills/
│
├── 📁 doc-governance/                    # 文档治理核心组
│   ├── SKILL.md                          # 法规宪法（10条铁律 + 4层架构）
│   ├── doc-constitution/                 # 文档治理核心组
│   │   └── SKILL.md                      # 法规参考标准（C1-C10分类、数据流向、安全子集）
│   ├── doc-governance/                   # 文档生命周期管理
│   │   └── SKILL.md                      # 4层架构、状态机、版本号同步、审计闭环
│   └── doc-management/                   # 向后兼容转发文件
│       └── SKILL.md                      # → 转发到 doc-governance + showdoc-platform-rules + sync-cross-platform-rules
│
├── 📁 showdoc-platform/                  # ShowDoc 平台操作组
│   ├── showdoc-markdown-compat/          # Markdown 安全子集
│   │   └── SKILL.md                      # 19项实测确认的安全格式
│   └── showdoc-platform-rules/           # ShowDoc MCP 操作规则
│       └── SKILL.md                      # 路由表、API/数据字典模板、RunApi/看板
│
├── 📁 feishu-platform/                   # 飞书平台操作组
│   └── feishu-platform-rules/            # 飞书 lark-cli 命令集
│       └── SKILL.md                      # docs 命令、wiki 管理、认证检查
│
├── 📁 cross-platform-sync/               # 跨平台同步组
│   └── sync-cross-platform-rules/        # 跨平台同步规则
│       └── SKILL.md                      # 10类权威源映射、冲突解决、sync_registry
│
├── 📁 engine-extensions/                 # L2 Engine 技能附加规则组
│   ├── wiki/                             # Wiki 生成技能
│   │   └── SKILL.md                      # + 文档治理附加规则
│   └── docx/                             # Word 文档处理技能
│       └── SKILL.md                      # + 文档治理附加规则
│
└── 📁 external-services/                 # 外部服务技能（~/.agents/skills/）
    ├── lark-doc/                         # 飞书文档 CRUD
    │   └── SKILL.md                      # + 文档治理附加规则
    ├── lark-wiki/                        # 飞书知识空间
    │   └── SKILL.md                      # + 文档治理附加规则
    └── lark-drive/                       # 飞书云空间
        └── SKILL.md                      # + 文档治理附加规则
```

---

## Skills 职责清单

### L1 Gateway 层（用户直接触发）

| Skill | 职责 | 触发词 |
|-------|------|--------|
| **doc-constitution** | 文档治理最高法规、规则参考源 | 文档法规、文档治理、文档合规 |
| **doc-governance** | 文档生命周期、版本号、审计闭环 | 文档版本、生命周期、审计、一致性 |
| **showdoc-markdown-compat** | 19项安全子集、格式验证 | 文档同步、格式兼容、Markdown规范 |
| **showdoc-platform-rules** | ShowDoc MCP 操作、模板、验证 | ShowDoc操作、创建页面、API文档 |
| **feishu-platform-rules** | 飞书 lark-cli 命令、wiki 管理 | 飞书文档操作、lark-cli docs |
| **sync-cross-platform-rules** | 跨平台同步流程、冲突解决 | 跨平台同步、sync_registry |

### L2 Engine 层（内部服务，照常触发 + 附加规则）

| Skill | 职责 | 附加规则 |
|-------|------|---------|
| **lark-doc** | 飞书文档 CRUD | 安全子集验证、保护标注、注册要求 |
| **lark-wiki** | 飞书知识空间管理 | 目录镜像、H2标题、注册要求 |
| **lark-drive** | 飞书云空间文件管理 | 禁止直推已注册文档、导入走管线 |
| **wiki** | Wiki 生成 | H2标题、C1-C10分类、安全子集 |
| **docx** | Word 文档处理 | 先import、安全子集验证、注册 |

---

## 数据流向总览

```
用户请求
  │
  ├── 同步场景 → L1 Gateway 判断 → L2 Engine 执行 → L3 Transport 调用
  │              (规则验证)         (CRUD操作)        (lark-cli/MCP)
  │              ↓
  │         更新 sync_registry + 审计记录
  │
  └── 非同步场景 → L2 Engine 直接执行，无限制
```

---

## 同步注册表

所有参与同步的文档必须注册到：`docs/sync_registry.yaml`

| 项目 | item_id | 文档数 |
|------|---------|--------|
| APISIX 网关文档 | 664858315 | 17 |
| memory-core 文档 | 664858316 | 37 |
| Factory Droid 功能文档 | 664858317 | 12 |

---

## 文档分类（C1-C10）

| 类别 | 类型 | 权威源 | 同步方向 |
|------|------|--------|---------|
| C1 | 代码/配置/Schema | Git | Git → ShowDoc → 飞书 |
| C2 | 规范文档 | Git | Git → ShowDoc → 飞书 |
| C3 | API 文档 | ShowDoc | ShowDoc → 飞书 |
| C4 | Python API/手册 | ShowDoc | ShowDoc → 飞书 |
| C5 | 计划页 | 双向 | Git ↔ ShowDoc → 飞书 |
| C6 | CLI 命令参考 | Git | Git → ShowDoc → 飞书 |
| C7 | 架构设计文档 | Git | Git → ShowDoc → 飞书 |
| C8 | CHANGELOG | Git | Git → ShowDoc → 飞书 |
| C9 | 会议纪要 | 飞书 | 飞书 → ShowDoc |
| C10 | 运维手册 | Git | Git → ShowDoc → 飞书 |
