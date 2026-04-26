---
type: "[DOC:DESIGN]"
title: "Memory API 契约（context-package-v1）"
shortname: DES-011
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: high
tags: [api-contract,context-package,gateway]
related: [DES-001, DES-002, DES-010]
---

> 文档编号：DES-011 | 版本：V1.0 | 日期：2026-04-26 | 维护人：A10（最终合成）

# Memory API 契约（context-package-v1）

> 创建日期：2026-04-26 | 维护人：A10（最终合成）| 状态：可评审

---

## 1. 契约概览

`memory` 模块对外暴露 **一个入口函数 + 一个出口结构**。消费者（CLI、validate、测试、cmux）仅通过此契约交互，不感知内部 34 个参数、adapter 配置、provider 选择等实现细节。

---

## 2. 入口契约

### 2.1 函数签名

```python
def build_context_package(host: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
    ...
```

### 2.2 参数说明

| # | 参数 | 类型 | 必填 | 取值 | 说明 |
|---|------|------|------|------|------|
| 1 | `host` | `str` | 是 | `"codex"` / `"claude"` | 调用方身份，决定 delegate 路由 |
| 2 | `event` | `str` | 是 | `"session-start"` / `"prompt-submit"` / `"stop"` / `"notification"` | 触发事件类型 |
| 3 | `payload` | `dict[str, Any]` | 是 | 任意 JSON 对象 | 事件载荷（cwd、task_ref、session_id 等） |

### 2.3 调用示例

```python
# CLI 入口
package = build_context_package("codex", "session-start", {"cwd": "/path/to/repo"})
# 验证工具
package = build_context_package("codex", "session-start", {})
```

### 2.4 为什么只有 3 个参数

- **A1**：core 的 37 参数中，34 个（路径常量、策略派生、函数引用、环境变量）由 gateway 内部组装。
- **A3**：所有调用方（CLI、validate、9 组测试）都只传 3 个参数。
- **A4**：47 个 adapter 配置 key 在 import-time 注入，是 wiring 参数，不是 API 参数。
- **A6**：LangChain 2 参数、Mem0 1 条消息——薄 API 是行业共识。

---

## 3. 出口契约

### 3.1 返回值结构（context-package-v1）

```python
{
    "schema_version": "context-package-v1",
    "generated_at": "2026-04-26T12:00:00+08:00",
    "host": "codex",
    "event": "session-start",
    "status": "ok",                    # "ok" | "degraded"
    "paths": {
        "repo_root": "<consumer-repo>",
        "workspace_root": "<consumer-repo>/workspace",
        "cwd": "<consumer-repo>",
    },
    "project_scope": "workbot",
    "task": {
        "event": "session-start",
        "task_ref": "workbot:session-start",
        "session_id": "...",
        "surface_id": "dev-bot",
        "workspace_id": "workbot",
    },
    "allowed_reads": ["/path/to/file1"],
    "allowed_writes": {
        "fact": "...",
        "kb_policy": {"mode": "read-first-CRUD", "overwrite_allowed": False, "conflict_strategy": "preserve-and-escalate"},
    },
    "evidence_refs": ["/path/to/evidence1"],
    "validation_errors": [],           # status=degraded 时非空
    "project": {
        "scope": "workbot",
        "truth_status": "truth-ready",  # "truth-ready" | "truth-incomplete"
        "runtime_root": "/path/to/runtime",
        "source_refs": [],
        "authority_refs": [],
        "evidence_refs": [],
    },
}
```

### 3.2 字段说明

| 顶层 key | 类型 | 用途 |
|----------|------|------|
| `schema_version` | `str` | 版本标识 |
| `generated_at` | `str` | ISO-8601 时间戳 |
| `host` / `event` | `str` | 路由标识 + 文件命名 |
| `status` | `str` | `"ok"` / `"degraded"` |
| `paths` | `dict` | 路径上下文（repo_root / workspace_root / cwd） |
| `project_scope` | `str` | 项目作用域 |
| `task` | `dict` | 任务上下文（event / task_ref / session_id / surface_id / workspace_id） |
| `allowed_reads` | `list[str]` | 允许读取的文件路径 |
| `allowed_writes` | `dict` | 写入目标（含 kb_policy） |
| `evidence_refs` | `list[str]` | 证据文件路径 |
| `validation_errors` | `list[str]` | 校验错误汇总 |
| `project` | `dict` | 项目 truth 状态（scope / truth_status / runtime_root / refs） |

### 3.3 移除的字段

| 移除项 | 去向 |
|--------|------|
| `system_context`（整体） | gateway 诊断日志 / stderr |
| `artifact_refs` | gateway 内部产物定位 |
| `missing_paths` | 合并进 `validation_errors` |
| `core_provider*` 系列 | 独立诊断通道 |
| `shadow_run` | 独立 shadow 日志 |

---

## 4. 设计原则

1. **入口最薄**：消费者只传 host + event + payload，其余 34 个参数 gateway 内部组装。
2. **出口精简**：~12 个顶层字段，诊断信息走独立通道（A2/A3/A5）。
3. **provider 透明**：external-core / legacy 切换对消费者透明，`status` 是唯一降级信号（A5）。
4. **adapter 隔离**：47 个配置 key 是 wiring 参数，通过环境变量选择（A4）。
5. **版本化**：`schema_version: "context-package-v1"` 标识契约版本。

---

## 5. 迁移路径

### 阶段 1：诊断通道分离
1. 将 `core_provider*`、`shadow_run` 写入独立日志（stderr 或 shadow log）
2. 从 `system_context` 移除这些字段
3. 更新测试断言，从日志通道验证

### 阶段 2：出口结构精简（breaking change）
1. 扁平字段重组为嵌套分组：`paths` / `task` / `project`
2. 移除 `system_context`、`artifact_refs`、`missing_paths`
3. `missing_paths` 合并进 `validation_errors`
4. 更新 `schema_version` 为 `"context-package-v1"`
5. 更新消费者代码和测试

### 阶段 3：验证与稳定
1. 全量测试无回归
2. 验证 CLI、validate、cmux 三种调用路径
3. `schema_version` 写入 artifact 文件头

---

## 6. 分析来源声明

| 子代理 | 文件 | 核心贡献 |
|--------|------|----------|
| A1（入口分析） | `a1-entry-analysis.md` | 确认 3 参数为最小必要集 |
| A2（出口分析） | `a2-exit-analysis.md` | 设计 context-package-v1 嵌套结构 |
| A3（消费审计） | `a3-consumer-usage.md` | 审计调用方，确认实际消费面 ~10 字段 |
| A4（adapter 配置） | `a4-adapter-config.md` | 确认 47 个 key 是 wiring 非 API |
| A5（provider 透明度） | `a5-provider-transparency.md` | 确认 provider/shadow 移入诊断通道 |
| A6（业界参考） | `a6-industry-reference.md` | 参考 LangChain/Mem0/Zep，确认薄 API 趋势 |
| A7（交叉验证） | `a7-cross-validation.md` | 调和 A2/A3 矛盾，确认 system_context 移除 |
| A8（迁移计划） | 本文档第 5 节 | 三阶段迁移路径（诊断分离 → 出口精简 → 验证稳定），由 A10 基于 A1-A7 推导 |
| A9（API 骨架） | 本文档第 2-3 节 | 入口函数签名（§2.1）+ 出口结构（§3.1）即为完整 API 骨架 |
| A10（最终合成） | 本文档 | 综合 A1-A9，产出唯一设计产出物 |
