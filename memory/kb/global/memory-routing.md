# 记忆路由规则

Layer 2/3 fallback 与 scope resolution 规则。

## 1. 读取链

Agent 启动时的读取链：

1. `AGENTS.md` — 行为约束、路由方向
2. 三层架构路由 — Layer 3 项目层优先 → Layer 2 全局 fallback
3. `adapter.toml` — 声明 `project_scope`，确定当前项目

## 2. Layer 2/3 Fallback 机制

当 Agent 需要查找知识时，按以下顺序尝试：

1. **Layer 3 项目知识库** — 查找 `<project>/memory/kb/projects/{scope}.md` 及相关文件
2. **Layer 2 全局知识库** — 如果项目层无定义，回退到 `memory/kb/global/` 下的 5 个 canonical 文件
3. **Layer 1 全局治理** — 合法性判定始终由 `project-map/` 子系统负责，不可被项目层覆盖

## 3. Scope Resolution

ScopeResolver 负责将 `project_scope` 解析为具体的 canonical 文件路径：

- `decision_refs_for_scope(scope)` — 返回决策引用路径（过滤仅保留磁盘上存在的路径）
- `lesson_refs_for_scope(scope)` — 返回经验教训引用路径
- `docs_refs_for_scope(scope)` — 返回文档引用路径

所有方法内部调用 `_existing_paths()`，只返回磁盘上实际存在的路径。

## 4. Authority Refs 约束

Authority Refs 必须属于下列白名单之一：

- `project-map/INDEX.md`
- `project-map/legal-core-map.md`
- 5 个全局 canonical 文件（truth-model.md / memory-system.md / memory-routing.md / hook-contract.md / project-map-governance.md）

违反此约束会导致 TruthBasisResolver Phase 6 报错。

## 5. Source Diversity 约束

Source Refs 中至少要包含一条"非 canonical 来源"的路径。
以下类别被视为 canonical 来源，不得全部占据 Source Refs：

- `global-canonical`
- `legal-core`
- `project-map-index`

至少需要一条来自 `docs`、`project-runtime`、`artifact`、`tooling`、`log` 等其它类别的路径。

## 6. Evidence Diversity 约束

Evidence Refs 中至少要包含一条位于 `lower_evidence_roots`（如 `tests/`）下的路径。
`tools/` 目录不被视为 lower evidence root；只有 `tests/` 满足此约束。

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- project-map/INDEX.md
- memory/kb/global/hook-contract.md

### Evidence Refs

- tests/conftest.py

### Conflict Status

- resolved
