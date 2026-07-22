
> Status: accepted
> Date: 2026-07-22
> Source: 文档分类规则引擎升级 mission（3 PRs 合并，18/18 断言通过）
> Tags: [decision, doc-routing, guard, ci, classification, governance]
> Related: [D-006-python-version-pin-314]

## 决策

将文档分类从"Agent 凭记忆选路径"升级为"硬编码路由表 + PreToolUse guard 拦截 + CI 校验"三层强制执行。杜绝文档放在未注册目录的问题。

## 背景

CLASSIFICATION.md 是纯文本 spec，没有任何程序消费它。Agent 凭记忆选路径导致：
- 重构日志放错 plans/（应为 refactor-logs/）
- refactor-logs/ 目录创建后未回写 CLASSIFICATION.md
- 7 个历史未注册目录散落在 memory/docs/ 下
- 2 组重复目录（memory/docs/decisions/ vs memory/kb/decisions/）

根因：规则文档是静态文本，靠 Agent 手动维护，没有自动校验。

## 关键决策

### 决策 1: 硬编码路由表作为 single source of truth

DOC_CATEGORIES 字典写死在 `memory_core/tools/doc_router.py` 中，包含 10 个分类标签。CLASSIFICATION.md 从"唯一分类指引"降级为"人类参考文档"。

### 决策 2: 三层强制执行

| Layer | 机制 | 拦截时机 |
|-------|------|---------|
| resolve_doc_path() | Agent 调 API 拿路径 | 写入前 |
| PreToolUse guard | _guard_classify.py 校验注册目录 | 写入时 block |
| CI check | check_doc_classification.py 扫描全量文件 | PR 合并前 fail |

### 决策 3: 路由表只管 memory/ 下

`docs/architecture/`、`docs/specs/` 等仓库自身文档不进路由表。路由表边界就是 `memory/` 目录。

### 决策 4: 目录治理先于路由引擎

先整理 7 个未注册目录（合并重复、删除空目录），再建路由引擎。否则路由表跟实际目录仍然脱节。

### 决策 5: 例外列表

允许存在但不进路由表的目录：archive/（只读历史）、system/（系统 spec）、projects/（消费项目知识）。

## 影响

| 变更 | PR |
|------|-----|
| 目录治理：合并 4 个未注册目录 + 删除空目录 | #187 (da84b81) |
| 路由引擎：doc_router.py + guard 集成 + CI check + 文档同步 | #188 (336c323) |
| posthog 7.24.0 参数名修复 | #189 (de36275) |

## 教训

"声明 ≠ 执行"——CLASSIFICATION.md 声明了分类规则但无人执行，跟 CI 版本脱节是同一个模式。根治方法是代码强制执行，不是靠 Agent 自觉。
