# Memory Routing — Generic Rules

> Generic template — populated by memory-core default adapter.
> This file defines routing rules for memory requests in any project
> using the generic (non-business-specific) memory-hook adapter.

## Purpose

Memory routing governs request routing, scope resolution, and fallback.

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

## Adapter Resolution

The adapter is resolved: explicit adapter param → MEMORY_HOOK_ADAPTER env → default fallback.

## Project Scope Routing

Each project scope maps to its own knowledge base namespace.
Default scope falls back to `memory/kb/projects/default.md`.

## Version History

- v1.0 — Initial generic template (default adapter)
