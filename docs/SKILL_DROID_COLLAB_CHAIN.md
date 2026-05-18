# Skill↔Droid 协作链路设计

> 版本: 1.0.0 | 创建: 2026-05-17 | 状态: design
> 适用范围: ShowDoc↔飞书 文档同步场景

---

## 1. 架构总览

### 1.1 组件分层

```
┌─────────────────────────────────────────────────────────────────┐
│                     主代理 (Orchestrator)                         │
│  职责: 接收用户意图，编排 skill 和 droid，不执行具体操作              │
└──────────┬──────────────────┬──────────────────┬────────────────┘
           │                  │                  │
     ┌─────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
     │ Skill 层   │    │ Droid 层    │    │ 外部工具层   │
     │ (规则/知识) │    │ (执行者)    │    │ (MCP/CLI)   │
     ├───────────┤    ├────────────┤    ├─────────────┤
     │ showdoc-  │    │ showdoc-   │    │ showdoc MCP │
     │ feishu-   │    │ cross-     │    │ lark-cli    │
     │ markdown- │    │ validator  │    │ git         │
     │ compat    │    ├────────────┤    │             │
     ├───────────┤    │ showdoc-   │    │             │
     │ doc-      │    │ plan-sync  │    │             │
     │ management│    └────────────┘    └─────────────┘
     └───────────┘
```

### 1.2 交互原则

| 原则 | 说明 |
|------|------|
| skill 提供规则，不执行操作 | skill 仅输出 Markdown 兼容规则、文档分类规则、版本传播规则 |
| droid 执行操作，引用 skill 规则 | droid 调用 MCP/CLI 工具，在执行前/后引用 skill 规则验证 |
| 主代理编排，不直接执行细节 | 主代理只负责意图解析、流程编排、结果汇总 |
| 每个 droid 只做一件事 | cross-validator 只验证，plan-sync 只同步计划状态 |
| droid 之间不直接调用 | 协作通过主代理编排完成 |

### 1.3 Skill→Droid 规则传递方式

```
主代理调用 skill:
  → skill 输出规则清单（19项安全子集、文档分类表、版本传播矩阵）
  → 主代理将规则作为 context 传给 droid
  → droid 在执行中引用规则做校验

droid 不直接调用 skill:
  → droid 的 system prompt 中内嵌关键规则的摘要
  → 完整规则由主代理在调用时注入
```

---

## 2. 场景1 链路：创建/更新 ShowDoc 文档

**用户输入**: "写个 API 文档"

```
Step 1: [主代理] → 意图解析
  │  输入: "写个 API 文档"
  │  动作: 确定文档类型为 C3 (API 文档)，权威源为 ShowDoc
  │  引用: doc-management skill — 文档分类规则
  │
Step 2: [主代理] → 获取 Markdown 规则
  │  动作: 调用 showdoc-feishu-markdown-compat skill
  │  输出: 19 项安全 Markdown 子集规则
  │  传递: 将规则清单作为 context 保留
  │
Step 3: [主代理] → 生成文档内容
  │  动作: 根据用户需求生成 API 文档 Markdown
  │  约束: 遵循安全 Markdown 子集（H2 起头，无图片，无嵌套引用）
  │  引用: showdoc-feishu-markdown-compat 规则
  │
Step 4: [主代理] → 写入 ShowDoc
  │  工具: showdoc___upsert_page
  │  参数: item_id, page_title, page_content, cat_name
  │  产出: page_id, 写入确认
  │
Step 5: [主代理] → 调用 droid 验证
  │  触发: showdoc-cross-validator droid
  │  输入: page_id, 原始 content, 安全 Markdown 规则
  │  动作:
  │    5a. showdoc___get_page(page_id) 读取已写入内容
  │    5b. 对比原始 content 与实际写入内容
  │    5c. 校验 19 项安全子集合规性
  │    5d. 检查表格无对齐标记、无 [TOC]、无锚点链接
  │  输出: 验证报告 {status: pass/fail, violations: [...]}
  │
Step 6: [主代理] → 结果汇总
  │  如验证通过: 通知用户文档已创建
  │  如验证失败: 展示违规项，询问是否自动修复
  │  引用: doc-management skill — 更新 sync_registry.yaml
```

**流程图**:

```
用户 "写个 API 文档"
       │
       ▼
  ┌─[主代理]──── 意图解析 ──── 引用 doc-management 分类规则
       │
       ▼
  ┌─[主代理]──── 获取规则 ──── 调用 showdoc-feishu-markdown-compat
       │
       ▼
  ┌─[主代理]──── 生成内容 ──── 遵循安全 Markdown 子集
       │
       ▼
  ┌─[主代理]──── 写入 ShowDoc ── showdoc___upsert_page
       │
       ▼
  ┌─[droid: cross-validator]── 验证写入 ── showdoc___get_page + 规则校验
       │
       ▼
  ┌─[主代理]──── 结果汇总 ──── 通知用户 / 修复违规
```

---

## 3. 场景2 链路：ShowDoc → 飞书同步

**触发**: 用户说"同步到飞书"或版本发布后自动触发

```
Step 1: [主代理] → 确定同步范围
  │  动作: 读取 docs/sync_registry.yaml
  │  确定需要同步的页面（基于 content_hash 对比）
  │  引用: doc-management skill — 文档分类与权威源映射
  │
Step 2: [主代理] → 获取转换规则
  │  动作: 调用 showdoc-feishu-markdown-compat skill
  │  输出: 内容转换管线规则
  │    - 移除 [TOC]
  │    - 移除表格对齐标记 (:---:)
  │    - 确保列表 2 空格缩进
  │    - 验证无锚点链接
  │    - 验证无图片语法 ![...](...)
  │
Step 3: [主代理] → 逐页读取 ShowDoc 内容
  │  工具: showdoc___get_page(page_id)
  │  产出: 每页原始 Markdown 内容
  │
Step 4: [主代理] → 执行内容转换
  │  动作: 按照 showdoc-feishu-markdown-compat 规则转换
  │  约束: 输出必须完全符合 19 项安全子集
  │  引用: showdoc-feishu-markdown-compat — 内容转换管线
  │
Step 5: [主代理] → 写入飞书
  │  新文档: lark-cli docs +create --wiki-space <space_id>
  │  已有文档: lark-cli docs +update --mode overwrite
  │  产出: feishu_doc_id / doc_token
  │
Step 6: [主代理] → 调用 droid 验证
  │  触发: showdoc-cross-validator droid
  │  输入: ShowDoc content, 飞书 doc_token, 安全 Markdown 规则
  │  动作:
  │    6a. lark-cli docs +fetch 读取飞书文档
  │    6b. 对比 ShowDoc 内容与飞书内容（忽略 [TOC] 差异）
  │    6c. 校验结构完整性（标题层级、列表层级、表格列数）
  │    6d. 检查飞书渲染后有无丢失内容
  │  输出: 验证报告 {status: pass/fail, diff_summary, violations}
  │
Step 7: [主代理] → 更新同步注册表
  │  动作: 更新 sync_registry.yaml
  │    - 更新 feishu_doc_id
  │    - 更新 last_feishu_sync 时间戳
  │    - 更新 content_hash
  │  引用: doc-management skill — 同步注册表维护规则
  │
Step 8: [主代理] → 创建审计记录
  │  动作: 写入 docs/audit/showdoc-sync-YYYY-MM-DD.md
  │  引用: doc-management skill — 审计日志格式
```

**流程图**:

```
"同步到飞书" / 版本发布触发
       │
       ▼
  ┌─[主代理]──── 读取 sync_registry ──── 确定同步范围
       │                              引用 doc-management
       ▼
  ┌─[主代理]──── 获取转换规则 ──────── 调用 showdoc-feishu-markdown-compat
       │
       ▼
  ┌─[主代理]──── 读取 ShowDoc ──────── showdoc___get_page (逐页)
       │
       ▼
  ┌─[主代理]──── 内容转换 ──────────── 应用安全 Markdown 子集规则
       │
       ▼
  ┌─[主代理]──── 写入飞书 ──────────── lark-cli docs +create/+update
       │
       ▼
  ┌─[droid: cross-validator]── 验证同步 ── 读取飞书 + 对比 ShowDoc + 校验
       │
       ▼
  ┌─[主代理]──── 更新注册表 + 审计 ──── 引用 doc-management 审计规则
```

---

## 4. 场景3 链路：版本发布文档更新

**触发**: 用户说"发布 v0.4.0"或 constants.py 版本号变更

```
Step 1: [主代理] → 检测版本变更
  │  动作: 读取 constants.py / pyproject.toml 版本号
  │  对比上次发布记录
  │  引用: doc-management skill — 版本号传播矩阵
  │
Step 2: [主代理] → 确定文档变更范围
  │  动作: git diff 扫描自上次发布以来的文档变更
  │  分类: 按 doc-management 的 C1-C10 类别过滤
  │  排除: 无变更的文档
  │  引用: doc-management skill — 文档分类表
  │
Step 3: [主代理] → 获取 Markdown 规则
  │  动作: 调用 showdoc-feishu-markdown-compat skill
  │  产出: 安全 Markdown 子集 + 内容转换管线规则
  │
Step 4: [主代理] → Git → ShowDoc 批量同步
  │  工具: showdoc___upsert_page (逐页)
  │  动作:
  │    4a. 读取变更的 Git 文件
  │    4b. 转换为 ShowDoc 格式（加 [TOC]、调整标题层级）
  │    4c. 写入 ShowDoc
  │    4d. 记录写入结果
  │
Step 5: [主代理] → 调用 droid 验证 ShowDoc 写入
  │  触发: showdoc-cross-validator droid
  │  输入: 所有变更页面的 page_id 列表 + 安全 Markdown 规则
  │  动作:
  │    5a. 逐页 showdoc___get_page 读取
  │    5b. 对比 Git 源文件内容与 ShowDoc 实际内容
  │    5c. 校验安全 Markdown 子集合规性
  │    5d. 检查版本号是否正确传播到所有文档
  │  输出: 批量验证报告 {total, passed, failed, details}
  │
Step 6: [主代理] → ShowDoc → 飞书批量同步
  │  动作:
  │    6a. 对已验证通过的页面执行飞书转换
  │    6b. 移除 [TOC]、表格对齐标记等
  │    6c. 写入飞书 lark-cli docs +update
  │
Step 7: [主代理] → 调用 droid 验证飞书同步
  │  触发: showdoc-cross-validator droid
  │  输入: 变更页面的 feishu_doc_id 列表
  │  动作: 逐页读取飞书 + 对比 ShowDoc + 校验
  │  输出: 飞书同步验证报告
  │
Step 8: [主代理] → 更新 PLAN-STATUS 和里程碑
  │  触发: showdoc-plan-sync droid
  │  动作:
  │    8a. 读取 docs/PLAN-STATUS.md 获取活跃计划
  │    8b. 更新版本号字段
  │    8c. showdoc___update_page 回写 ShowDoc 计划页
  │    8d. 更新 last_sync 时间戳
  │  输出: PLAN-STATUS 更新报告
  │
Step 9: [主代理] → 创建发布审计记录
  │  动作: 写入 docs/audit/showdoc-sync-YYYY-MM-DD.md
  │  内容: 版本号、变更文档列表、同步结果、验证结果
  │  引用: doc-management skill — 审计日志格式
```

**流程图**:

```
"发布 v0.4.0" / 版本号变更检测
       │
       ▼
  ┌─[主代理]──── 检测版本变更 ──────── 引用 doc-management 版本传播矩阵
       │
       ▼
  ┌─[主代理]──── 扫描文档变更 ──────── git diff + 文档分类
       │                              引用 doc-management 分类规则
       ▼
  ┌─[主代理]──── 获取规则 ──────────── 调用 showdoc-feishu-markdown-compat
       │
       ▼
  ┌─[主代理]──── Git→ShowDoc 同步 ──── showdoc___upsert_page (批量)
       │
       ▼
  ┌─[droid: cross-validator]── 验证 ShowDoc ── 读取+对比+校验
       │
       ▼
  ┌─[主代理]──── ShowDoc→飞书 同步 ─── lark-cli docs +update (批量)
       │
       ▼
  ┌─[droid: cross-validator]── 验证飞书 ────── 读取+对比+校验
       │
       ▼
  ┌─[droid: plan-sync]─────── 更新计划状态 ─── PLAN-STATUS + ShowDoc 计划页
       │
       ▼
  ┌─[主代理]──── 创建审计记录 ──────── 引用 doc-management 审计规则
```

---

## 5. 场景4 链路：定期一致性扫描

**触发**: 用户说"检查一致性"或定期手动触发

```
Step 1: [主代理] → 发起一致性扫描
  │  动作: 读取 docs/sync_registry.yaml 获取所有注册页面
  │  引用: doc-management skill — 同步注册表维护规则
  │
Step 2: [主代理] → 获取校验规则
  │  动作: 调用 showdoc-feishu-markdown-compat skill
  │  产出: 安全 Markdown 子集校验清单
  │
Step 3: [主代理] → 调用 droid 执行一致性检查
  │  触发: showdoc-cross-validator droid
  │  输入: sync_registry 全部页面 + 安全 Markdown 规则
  │  动作:
  │    3a. 逐页 showdoc___get_page 读取 ShowDoc 内容
  │    3b. 逐页 lark-cli docs +fetch 读取飞书内容
  │    3c. 对比三方内容（Git → ShowDoc → 飞书）
  │    3d. 计算每页的 content_hash 差异
  │    3e. 校验安全 Markdown 子集合规性
  │    3f. 生成三方一致性矩阵
  │  输出: 一致性报告 {
  │    consistent: [...],      // 三方一致
  │    showdoc_stale: [...],   // ShowDoc 落后于 Git
  │    feishu_stale: [...],    // 飞书落后于 ShowDoc
  │    violations: [...],      // 安全子集违规
  │    missing: [...]          // 注册表有记录但实际不存在
  │  }
  │
Step 4: [主代理] → 调用 droid 修复 stale 状态
  │  触发: showdoc-plan-sync droid
  │  动作:
  │    4a. 读取 docs/PLAN-STATUS.md
  │    4b. 对比 ShowDoc 计划页与本地实际状态
  │    4c. 对 showdoc_stale 页面执行 showdoc___update_page 修复
  │    4d. 更新 PLAN-STATUS.md 的 last_verified 时间戳
  │  输出: 修复报告 {fixed: [...], needs_manual: [...]}
  │
Step 5: [主代理] → 对 feishu_stale 页面执行增量同步
  │  动作:
  │    5a. 对一致性报告中 feishu_stale 的页面
  │    5b. 重新执行 ShowDoc → 飞书同步（场景2的 Step 4-6）
  │
Step 6: [主代理] → 输出汇总报告
  │  内容: 一致性扫描结果 + 修复动作 + 仍需手动处理的项
  │  引用: doc-management skill — 审计日志格式
```

**流程图**:

```
"检查一致性" / 定期触发
       │
       ▼
  ┌─[主代理]──── 读取 sync_registry ──── 引用 doc-management
       │
       ▼
  ┌─[主代理]──── 获取规则 ──────────── 调用 showdoc-feishu-markdown-compat
       │
       ▼
  ┌─[droid: cross-validator]── 三方一致性检查 ── Git+ShowDoc+飞书 对比
       │
       ▼
  ┌─[droid: plan-sync]─────── 修复 stale 状态 ── PLAN-STATUS + ShowDoc 计划页
       │
       ▼
  ┌─[主代理]──── 增量同步飞书 ──────── 对 feishu_stale 页面重新同步
       │
       ▼
  ┌─[主代理]──── 输出汇总报告 ──────── 引用 doc-management 审计规则
```

---

## 6. 场景5 链路：计划页里程碑更新

**触发**: 子代理完成任务后，主代理检测到 todo 状态变更

```
Step 1: [主代理] → 检测子代理完成信号
  │  触发: 子代理 todo 从 in_progress 变为 completed
  │  动作: 识别已完成的里程碑/任务
  │  引用: doc-management skill — 文档分层与生命周期状态机
  │
Step 2: [主代理] → 获取回写规则
  │  动作: 调用 doc-management skill
  │  输出: 计划页状态传播规则、里程碑验收标准
  │
Step 3: [主代理] → 调用 droid 执行计划页回写
  │  触发: showdoc-plan-sync droid
  │  输入: 已完成的任务 ID、新状态、证据（test results / commit hash）
  │  动作:
  │    3a. 读取 docs/PLAN-STATUS.md
  │    3b. 定位对应里程碑条目
  │    3c. 更新状态为 completed
  │    3d. 填写证据（commit hash, test pass rate, date）
  │    3e. showdoc___update_page 回写 ShowDoc 计划页
  │    3f. 更新 last_sync 时间戳
  │  输出: 回写报告 {plan_status: updated, showdoc_page: updated}
  │
Step 4: [主代理] → 获取 Markdown 规则
  │  动作: 调用 showdoc-feishu-markdown-compat skill
  │  产出: 安全 Markdown 子集 + 内容转换规则
  │
Step 5: [主代理] → 同步到飞书
  │  动作:
  │    5a. 从 ShowDoc 读取更新后的计划页
  │    5b. 执行飞书兼容转换
  │    5c. lark-cli docs +update 写入飞书
  │
Step 6: [主代理] → 调用 droid 验证同步
  │  触发: showdoc-cross-validator droid
  │  输入: ShowDoc page_id, 飞书 doc_token
  │  动作: 对比 ShowDoc 和飞书计划页内容
  │  输出: 验证报告
  │
Step 7: [主代理] → 输出闭环报告
  │  内容: 里程碑完成确认 + 三方同步状态 + 后续待办
  │  引用: doc-management skill — 审计闭环规则
```

**流程图**:

```
子代理 todo: in_progress → completed
       │
       ▼
  ┌─[主代理]──── 检测完成信号 ──────── 引用 doc-management 生命周期状态机
       │
       ▼
  ┌─[主代理]──── 获取回写规则 ──────── 调用 doc-management
       │
       ▼
  ┌─[droid: plan-sync]─────── 回写计划页 ──── PLAN-STATUS.md + ShowDoc 计划页
       │
       ▼
  ┌─[主代理]──── 获取 Markdown 规则 ── 调用 showdoc-feishu-markdown-compat
       │
       ▼
  ┌─[主代理]──── 同步到飞书 ────────── lark-cli docs +update
       │
       ▼
  ┌─[droid: cross-validator]── 验证同步 ───── 对比 ShowDoc + 飞书
       │
       ▼
  ┌─[主代理]──── 输出闭环报告 ──────── 引用 doc-management 审计闭环
```

---

## 7. 发现的协作缺口

### 7.1 缺失组件

| 缺口 | 严重程度 | 说明 |
|------|---------|------|
| **showdoc-cross-validator droid 未创建** | 🔴 高 | 场景 1-6 均依赖此 droid 做写入后验证，但当前仓库中不存在该 droid 定义文件。需创建 `.factory/droids/showdoc-cross-validator.md` |
| **skill 本地定义文件缺失** | 🟡 中 | `showdoc-feishu-markdown-compat` 和 `doc-management` 两个 skill 在 `~/.factory/skills/` 中可能存在全局定义，但项目本地 `.factory/skills/` 目录为空。建议在项目级创建引用或符号链接 |
| **sync_registry.yaml 未创建** | 🟡 中 | 同步注册表 `docs/sync_registry.yaml` 在 SHOWDOC_FEISHU_SYNC_PLAN 中设计完善但尚未创建，是一致性扫描和增量同步的前置依赖 |
| **飞书知识空间未创建** | 🟢 低 | 飞书侧的 Wiki Space 尚未创建，首次同步前需完成 |

### 7.2 链路断点

| 断点位置 | 影响 | 修复方案 |
|---------|------|---------|
| **场景1 Step 5**: cross-validator droid 不存在 | 写入 ShowDoc 后无验证环节，可能写入不合规内容 | 创建 showdoc-cross-validator droid |
| **场景2 Step 6**: 同上，飞书同步后无验证 | 飞书可能渲染丢失内容但不被发现 | 创建 showdoc-cross-validator droid |
| **场景3 Step 5/7**: 发布流程双验证均依赖 cross-validator | 发布后文档质量无保障 | 创建 showdoc-cross-validator droid |
| **场景4 Step 3**: 一致性扫描依赖 cross-validator | 无法自动化三方一致性检查 | 创建 showdoc-cross-validator droid |
| **场景5 Step 6**: 里程碑验证依赖 cross-validator | 闭环报告可能不准确 | 创建 showdoc-cross-validator droid |

### 7.3 建议新增组件

| 组件 | 类型 | 职责 | 优先级 |
|------|------|------|--------|
| **showdoc-cross-validator** | droid | ShowDoc/飞书写入后验证，安全 Markdown 子集校验，三方一致性对比 | P0 |
| **showdoc-sync-registry** | 配置文件 | `docs/sync_registry.yaml` — 文档同步状态注册表 | P1 |
| **showdoc-content-transformer** | skill 或 droid 辅助 | 专责 Git→ShowDoc 和 ShowDoc→飞书的内容格式转换，解耦主代理的转换逻辑 | P2（可选，当前可由主代理内联处理） |

### 7.4 当前架构能力矩阵

| 场景 | 主代理 | showdoc-plan-sync | showdoc-cross-validator | showdoc-feishu-markdown-compat | doc-management |
|------|--------|--------------------|-------------------------|-------------------------------|----------------|
| 场景1: 创建文档 | ✅ 编排 | ❌ 不参与 | ❌ 缺失 | ✅ 提供规则 | ✅ 提供规则 |
| 场景2: 同步飞书 | ✅ 编排 | ❌ 不参与 | ❌ 缺失 | ✅ 提供规则 | ✅ 提供规则 |
| 场景3: 版本发布 | ✅ 编排 | ✅ 更新计划 | ❌ 缺失 | ✅ 提供规则 | ✅ 提供规则 |
| 场景4: 一致性扫描 | ✅ 编排 | ✅ 修复 stale | ❌ 缺失 | ✅ 提供规则 | ✅ 提供规则 |
| 场景5: 里程碑回写 | ✅ 编排 | ✅ 回写计划 | ❌ 缺失 | ✅ 提供规则 | ✅ 提供规则 |

**结论**: 5 个场景中有 5 个场景受 cross-validator 缺失影响。创建此 droid 是解除所有链路断点的唯一前置条件。
