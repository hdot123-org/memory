---
name: memory-core-development
description: Guidelines for developing on the memory-core library. Covers CLI tools, hook gateway, ownership model, and project memory lifecycle.
---

# memory-core Development

## Project Overview
memory-core is a read-only protocol repository providing the `memory/` protocol, templates, schemas, and CLI tools. It is a reusable library that does not store business project state. The project uses a v0.9.0 three-layer architecture with Layer 2 global knowledge base support.

## Key Commands
- Install: `pip install -e ".[dev]"`
- Lint: `ruff check .`
- Test: `python -m pytest tests/`
- Boundary check: `python scripts/check_boundary.py`
- Full check: `ruff check . && python -m pytest tests/`

## Architecture (v0.9.0)
Three-layer architecture:
- Layer 1: `~/.memory-core/` — Global runtime (never modified by agents)
- Layer 2: `~/.memory/global-kb/` — Global knowledge base (cross-project shared knowledge, global fallback; NEW in v0.8.0)
- Layer 3: `memory/system/` — Single project entry point (adapter.toml, ownership.toml, etc.)

Routing follows a **project-first, global-fallback** policy: knowledge lookups hit the project `memory/kb/` first, then fall back to the global `~/.memory/global-kb/` when a domain entry is missing.

## Key Directories
- `memory_core/tools/` — CLI tools (memory-init, memory-validate, memory-migrate, etc.)
- `memory_core/ownership.py` — Ownership data model and classify API
- `tests/` — 3037+ unit tests
- `docs/architecture/` — Architecture design documents (v0.9.0 three-layer architecture, data pipeline, telemetry)
- `docs/specs/` — Protocol specifications and boundary definitions (BOUNDARY.md, schema specs)

## Development Rules
- This is a source-repo-readonly repository: only explore, never modify protected paths
- Follow GitHub PR workflow: push to feature branch, open PR, pass dual-gate (ci-ok + droid-review), squash merge
- Use conventional commits: feat:, fix:, chore:, docs:
- Target Python 3.9+
- Boundary defined in `docs/specs/BOUNDARY.md`
