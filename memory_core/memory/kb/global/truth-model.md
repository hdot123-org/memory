# Truth Model — Generic Canonical Reference

> Generic template — populated by memory-core default adapter.
> This file defines how truth state is modeled and resolved for any
> project using the generic (non-business-specific) memory-hook adapter.

## Purpose

The truth model is the single source of truth for canonical state
decisions. It tells agents and memory subsystems:

1. Which sources are authoritative.
2. How conflicts between sources are resolved.
3. What canonical fields must be present for a state to be considered valid.

## Canonical Fields

Every truth entry must include at minimum:

- `source` — the originating system or agent
- `event_type` — the event classification
- `timestamp` — ISO-8601 timestamp of the event
- `project_scope` — the project scope this truth applies to
- `state` — the canonical state

## Truth Basis

### Source Refs

- memory_core/memory/kb/projects/default.md

### Authority Refs

- memory_core/memory/kb/global/memory-system.md
- memory_core/memory/kb/global/hook-contract.md

### Evidence Refs

- memory_core/tools/
- tests/

### Conflict Status

- resolved

## Usage

Agents consult this truth model before making state-dependent decisions.
The memory subsystem uses it to validate incoming state transitions.

## Version History

- v1.0 — Initial generic template (default adapter)
