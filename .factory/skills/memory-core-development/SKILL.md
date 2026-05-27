---
name: memory-core-development
description: Guidelines for developing on the memory-core library. Covers CLI tools, hook gateway, ownership model, and project memory lifecycle.
---

# memory-core Development

## Project Overview
memory-core is a read-only protocol repository providing the `memory/` protocol, templates, schemas, and CLI tools. It is a reusable library that does not store business project state.

## Key Commands
- Install: `pip install -e ".[dev]"`
- Lint: `ruff check .`
- Test: `python -m pytest tests/`
- Boundary check: `python scripts/check_boundary.py`
- Full check: `ruff check . && python -m pytest tests/`

## Architecture (v0.5.0)
Two-layer architecture:
- Layer 1: `~/.memory-core/` — Global runtime (never modified by agents)
- Layer 2: `memory/system/` — Single project entry point (adapter.toml, ownership.toml, etc.)

## Key Directories
- `memory_core/tools/` — CLI tools (memory-init, memory-validate, memory-migrate, etc.)
- `memory_core/ownership.py` — Ownership data model and classify API
- `tests/` — 1826+ unit tests
- `memory/docs/` — Design documents, specs, RFCs

## Development Rules
- This is a source-repo-readonly repository: only explore, never modify protected paths
- Follow GitLab-first workflow: push to GitLab, never directly to GitHub
- Use conventional commits: feat:, fix:, chore:, docs:
- Target Python 3.9+
- Boundary defined in `memory/docs/system/BOUNDARY.md`
