# Policy Pack — Generic Documentation

> Generic template — populated by memory-core default adapter.
> This file documents the policy pack structure for any project using
> the generic (non-business-specific) memory-hook adapter.

## Purpose

The policy pack defines gateway business policies, validation rules,
artifact compaction, and scope-based access control.

## Truth Basis

### Source Refs

- memory/kb/projects/default.md
- memory/kb/global/memory-system.md

### Authority Refs

- memory/kb/global/truth-model.md
- memory/kb/global/hook-contract.md

### Evidence Refs

- memory_core/tools/
- tests/

### Conflict Status

- resolved

## Policy Architecture

The default adapter uses NeutralGatewayBusinessPolicy from the
neutral_policy module, providing generic business rules without
project-specific bindings.

## Version History

- v1.0 — Initial generic template (default adapter)
