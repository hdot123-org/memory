# Memory Docs Index

> 文档编号：MEM-DOCS-001
> 版本：V3.0
> 创建日期：2026-04-15
> 维护人：memory system

This file catalogs every document under `memory_core/memory/docs/`.
Only files that exist on disk are listed; phantom entries have been removed.

---

Docs 子树默认归入 `incoming-raw`，未被地图明确吸收前不授予合法性。

## Document Catalog

| ID      | Name                                    | Path                                          | Status  |
|---------|-----------------------------------------|-----------------------------------------------|---------|
| M7-001  | 独立仓迁出执行计划（POR）                | `M7-independent-repo-cutover-plan.md`          | 可执行  |
| DES-001 | Memory 模块总体架构                      | `design/01-architecture.md`                    | 可评审  |
| DES-002 | Gateway 门控设计                         | `design/02-gateway.md`                         | 可评审  |
| DES-003 | Core Assembly 核心装配                   | `design/03-core-assembly.md`                   | 可评审  |
| DES-004 | 接口契约层                               | `design/04-interfaces.md`                      | 可评审  |
| DES-005 | 实现层                                   | `design/05-implementations.md`                 | 可评审  |
| DES-006 | Adapter 层                               | `design/06-adapters.md`                        | 可评审  |
| DES-007 | Policy Pack 与治理                       | `design/07-policy-governance.md`               | 可评审  |
| DES-008 | 数据管道与 Sink                          | `design/08-data-pipeline.md`                   | 可评审  |
| DES-009 | Provider 与回退机制                      | `design/09-provider-fallback.md`               | 可评审  |
| DES-010 | 消费边界与改进建议                       | `design/10-consumer-boundary.md`               | 可评审  |
| DES-011 | Memory API 契约                          | `design/API-CONTRACT.md`                       | 可评审  |

### Other files

| File                                  | Notes                        |
|---------------------------------------|------------------------------|
| `记忆系统全景文档.md`                 | 记忆系统全景概览              |
| `research/projects/AEdu/INDEX.md`     | AEdu 项目研究索引             |

### Referenced from kb (not under docs/)

| ID     | Name                         | Path                                                  |
|--------|------------------------------|-------------------------------------------------------|
| M3-000 | Memory Policy Pack           | `../kb/global/memory-hook-policy-pack.md`              |

---

## Removed entries (files do not exist on disk)

The following IDs appeared in previous versions but have no corresponding files:
M3-001, M3-002, M3-003, M6-001, M6-002.
If these documents are needed, they should be recreated before being re-listed here.

---

## Changelog

| Version | Date       | Author | Change                                       |
|---------|------------|--------|----------------------------------------------|
| V3.0    | 2026-04-27 | codex  | Cleaned up: removed phantom entries (M3-001~003, M6-001~002), audit checklists, duplicate Section 5, and cross-reference tables. Kept only files that exist on disk. |
| V2.0    | 2026-04-27 | codex  | Added M8 API completion record               |
| V1.9    | 2026-04-26 | codex  | DES-001~DES-011 marked as 可评审              |
| V1.8    | 2026-04-26 | codex  | Added DES design document series index        |
