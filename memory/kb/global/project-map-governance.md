# Project Map Governance — Generic Rules

> Generic template — populated by memory-core default adapter.
> This file defines governance rules for project maps used by any
> project with the generic memory-hook adapter.

## Purpose

Project map governance establishes:

1. What files are part of the legal project map
2. How project map entries are added or removed
3. The validation requirements for a complete project map

## Legal Project Map Files

The project map consists of at minimum:

1. **INDEX.md** — top-level index
2. **legal-core-map.md** — core legal rules
3. **ingestion-registry-map.md** — ingestion registry

## Truth Basis

### Source Refs

- memory/kb/projects/default.md
- memory/kb/global/truth-model.md

### Authority Refs

- memory/kb/global/memory-system.md
- memory/kb/global/hook-contract.md

### Evidence Refs

- memory_core/tools/
- tests/

### Conflict Status

- resolved

## Governance Rules

未经过唯一真相系统清洗的材料，不得被授予合法性。
只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。
未完成同次 `git commit` 的目录登记，不得视为生效。

## Version History

- v1.0 — Initial generic template (default adapter)
