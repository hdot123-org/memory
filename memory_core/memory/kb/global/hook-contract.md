# Hook Contract — Agent↔Memory Handshake Protocol

> Generic template — populated by memory-core default adapter.
> This file defines the handshake protocol between agents and the
> memory system for any project using the generic adapter.

## Purpose

The hook contract specifies request/response formats, error handling,
and schema versioning rules.

## Truth Basis

### Source Refs

- memory_core/memory/kb/projects/default.md
- memory_core/memory/kb/global/truth-model.md

### Authority Refs

- memory_core/memory/kb/global/memory-system.md
- memory_core/memory/kb/global/project-map-governance.md

### Evidence Refs

- memory_core/tools/
- tests/

### Conflict Status

- resolved

## Legal Context Sources

gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。
未完成提交的登记不得生效。

## Request Format

Every agent→memory request must include host, event, payload, and schema fields.

## Response Format

The memory system returns status, validation_errors, missing_paths, and context data.

## Schema Versions

- context-package-v1 (current)
- memory-v1 (legacy)

## Version History

- v1.0 — Initial generic template (default adapter)
