# 文档分类规则引擎升级

> Date: 2026-07-22
> Status: COMPLETED
> PRs: #187 (目录治理), #188 (路由引擎), #189 (posthog fix)
> Validation: 18/18 断言通过

## 概述

将 memory-core 的文档分类从"Agent 凭记忆选路径"升级为"硬编码路由表 + PreToolUse guard 拦截 + CI 校验"三层强制执行。两个 milestone，4 个 feature，18 个验证断言全部通过。

## Phase 1: 目录治理（PR #187, da84b81）

整理 memory/docs/ 和 memory/kb/ 下的未注册目录：

| 源目录 | 目标目录 | 文件数 |
|--------|---------|--------|
| memory/docs/decisions/ | memory/kb/decisions/ | 1 + INDEX 合并 |
| memory/docs/research/ | memory/docs/notes/ | 1 目录 |
| memory/docs/residue/ | memory/docs/audit/ | 2 文件 |
| memory/docs/design/ | docs/architecture/ | 17 文件 |
| memory/kb/infra/ | 删除（空目录） | 0 |

## Phase 2: 路由引擎（PR #188, 336c323）

### doc_router.py

```python
DOC_CATEGORIES = {
    "decision":     "memory/kb/decisions/",
    "lesson":       "memory/kb/lessons/",
    "refactor-log": "memory/docs/refactor-logs/",
    "plan":         "memory/docs/plans/",
    "runbook":      "memory/docs/runbooks/",
    "bug-report":   "memory/docs/bug-reports/",
    "audit":        "memory/docs/audit/",
    "rfc":          "memory/docs/rfcs/",
    "note":         "memory/docs/notes/",
    "draft":        "memory/docs/drafts/",   # fallback
}
```

三个函数：resolve_doc_path()、is_registered_doc_dir()、EXCEPTION_DIRS。

### Guard 集成

扩展 _guard_classify.py：Write/Edit/MultiEdit handler 中，当路径匹配 memory/docs/ 或 memory/kb/ 前缀时，调用 is_registered_doc_dir 校验。未注册 → block。

### CI 校验

scripts/check_doc_classification.py：扫描 memory/docs/ 和 memory/kb/ 所有文件，校验在注册目录或例外列表中。ci.yml 新增 step。

### 文档同步

CLASSIFICATION.md 增加 refactor-logs、notes 类别，标注"路由表以 doc_router.py DOC_CATEGORIES 为准"。AGENTS.md 新增铁律。

## Phase 3: 附带修复（PR #189, de36275）

posthog 7.24.0 将 api_key 重命名为 project_api_key。mypy strict 检测到参数名不匹配。scrutiny validator 发现并修复。

## 质量验证

| 门禁 | 结果 |
|------|------|
| mypy | 0 errors (70 source files) |
| pytest | 3102 passed, 3 skipped |
| ruff | All checks passed |
| radon D+ | 0 |
| check_doc_classification | clean (0 findings) |
| validation assertions | 18/18 passed |

## 测试覆盖

| 测试文件 | 用例数 | 覆盖范围 |
|---------|--------|---------|
| tests/test_doc_router.py | 43 | resolve_doc_path + is_registered_doc_dir 全路径 |
| tests/test_guard_doc_routing.py | 13 | guard 拦截 Write/Edit/MultiEdit |

## 遗留 Tech Debt

| 项目 | 严重度 | 说明 |
|------|--------|------|
| is_registered_doc_dir path traversal | non-blocking | 相对路径 '..' 绕过（低风险，guard 接收 Factory API 预规范化路径） |
| is_registered_doc_dir 消费项目兼容 | non-blocking | 绝对路径在消费项目中可能误判（当前部署模式是 in-repo） |
