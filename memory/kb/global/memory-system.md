# Memory System — Generic Configuration

> Generic template — populated by memory-core default adapter.
> This file defines the memory system configuration for any project
> using the generic (non-business-specific) memory-hook adapter.

## Purpose

The memory system configuration governs:

1. How memory entries are stored and retrieved
2. The compaction and retention policies
3. The artifact lifecycle management

## Storage Model

Memory entries are organized into three tiers:

### Tier 1: Canonical (Read-Only)

These files are immutable during a session.

### Tier 2: Knowledge Base (Append-Only)

- `memory/kb/global/` — global knowledge
- `memory/kb/projects/` — per-project knowledge
- `memory/kb/decisions/` — decision records
- `memory/kb/lessons/` — lessons learned

### Tier 3: Artifacts (Write-Allowed)

- Runtime artifacts and project-specific directories.

## Truth Basis

### Source Refs

- memory/kb/projects/default.md
- memory/kb/decisions/INDEX.md

### Authority Refs

- memory/kb/global/truth-model.md
- memory/kb/global/hook-contract.md

### Evidence Refs

- memory_core/tools/
- tests/

### Conflict Status

- resolved

## Compaction Policy

Artifact compaction is controlled by the ARTIFACT_COMPACTION profile field.

## Memory System Rules

1. Canonical files must exist before a session can start in ok status
2. Missing canonical files trigger degraded mode with validation errors
3. State transitions must reference the truth model for validation
4. All writes go through the gateway policy for authorization

## Version History

- v1.0 — Initial generic template (default adapter)
