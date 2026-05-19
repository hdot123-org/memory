# 文档同步标准流程 v1.0

> 版本: 1.0.0 | 创建: 2026-05-19 | 状态: draft
> 权威源: Git (L1) → ShowDoc (L2) → 飞书 (L3 只读镜像)

---

## 1. 同步方向与架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Git (L1)   │────>│ ShowDoc(L2) │────>│  飞书 (L3)  │
│  权威源     │     │  展示层     │     │  只读镜像   │
└─────────────┘     └─────────────┘     └─────────────┘
```

- **L1 Git**: 代码/规范/计划的唯一真相源（`.md`, `.py`, `.json`）
- **L2 ShowDoc**: 团队文档中枢，API 文档权威源（item_id per project）
- **L3 飞书**: 只读展示镜像（不需要反向同步）

---

## 2. 触发时机

| 场景 | 触发条件 |
|------|---------|
| 版本发布 | 新 tag 推送后 |
| 重大功能 | 功能完成 + 测试通过后 |
| 文档变更 | Git 文档更新后 |
| 用户要求 | 用户明确要求同步时 |

---

## 3. ShowDoc 同步步骤

### 3.1 确定目标
- 项目 item_id（memory-core: 664858316）
- 页面分类（计划页/API 文档/规范/教程）

### 3.2 创建/更新页面
```
工具: showdoc___upsert_page 或 showdoc___create_page
参数:
  - item_id: 项目 ID
  - page_title: 页面标题
  - page_content: Markdown 内容（H2 起头，安全子集）
  - cat_id: 目录 ID（可选）
```

### 3.3 验证
- 使用 `showdoc___get_page` 重新读取
- 验证内容完整性
- 验证 Markdown 安全子集合规性

---

## 4. 飞书同步步骤

### 4.1 搜索现有文档
```bash
lark-cli drive +search --query "关键词"
```

### 4.2 创建/更新文档
```bash
# 创建（新文档）
lark-cli docs +create --api-version v2 --title "标题" --content '<XML内容>' --parent-position my_library

# 更新（现有文档）
lark-cli docs +update --api-version v2 --doc "文档URL" --command overwrite --content '<XML内容>'
```

### 4.3 验证
```bash
lark-cli docs +fetch --api-version v2 --doc "文档URL"
```

---

## 5. 格式规范

### ShowDoc (Markdown)
- 标题从 `##` 起头（不用 `#` H1）
- 使用安全子集（19 项）
- 表格用 `|---|`（不用 `:---:` 对齐）
- 代码块标注语言
- 无 `[TOC]`（如需同步飞书）

### 飞书 (XML 默认 / Markdown 可选)
- 默认使用 XML 格式（表达能力更强）
- 用户提供 `.md` 或明确要求时才用 Markdown
- 支持 callout、grid、checkbox 等富 block
- 文档从 H2 起头（`<h2>`）

---

## 6. 配置信息

### ShowDoc
- 项目 item_id:
  - APISIX: 664858315
  - memory-core: 664858316
  - Factory Droid: 664858317

### 飞书
- 个人知识库: my_library
- CLI: lark-cli v1.0.32+
- API: docs v2

---

## 7. 注意事项

- **ShowDoc 在内网** (REDACTED_IP)，需在同一 LAN 或通过隧道访问
- **飞书 API 限流**: 控制 QPS ≤ 2/s
- **同步前验证**: 内容符合安全子集
- **同步后验证**: 读取返回内容确认完整
- **飞书为只读镜像**: 不反向同步，不回传评论
