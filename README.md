# memory-core

<!-- API MR test marker - automated verification -->
memory-core provides a reusable `memory/` protocol, templates, schemas, and CLI tools for project-scoped memory management. It is an open-source library for initializing, validating, migrating, and auditing memory layouts; it does not store business project state in this repository.

## Architecture (v0.8.0)

memory-core uses a **three-layer architecture**:

```
~/.memory-core/              ← Layer 1: Global runtime (never modified)
~/.memory/global-kb/         ← Layer 2: Global knowledge base (NEW in v0.8.0)
  operations/                ← Operations knowledge (servers, deployment, SSH, ...)
  engineering/               ← Engineering knowledge (CI/CD, toolchain, decisions)
  collaboration/             ← Collaboration knowledge (agent workflows, docs)
  pending/                   ← Auto-captured candidates awaiting promotion
/Users/project/
  memory/                    ← Layer 3: Single project entry point
    system/                  ← Config & state files
      adapter.toml           ← Now includes [global_kb] section (v0.8.0+)
      ownership.toml
      memory.lock
      migrations.log
      manifest.json
      integrity-audit.jsonl
    kb/                      ← Project knowledge base (project-first routing)
    docs/                    ← Documentation
    log/                     ← Logs
```

Routing follows a **project-first, global-fallback** policy: knowledge lookups hit the project `memory/kb/` first, then fall back to the global `~/.memory/global-kb/` when a domain entry is missing. The global fallback is enabled via the `[global_kb]` section in `memory/system/adapter.toml` (`memory-init` writes it automatically).

The project-level configuration lives in `memory/system/` (not `.memory/`). The hidden `.memory/` directory was removed in v0.5.0.

## Install

Install from a GitHub release wheel:

```bash
gh release download v0.8.0 --repo hdot123/memory --pattern "*.whl"
pip install memory_core-0.8.0-py3-none-any.whl
```

Install from source:

```bash
pip install git+https://github.com/hdot123/memory.git@v0.8.0
```

Upgrade by changing the version and adding `--upgrade`:

```bash
pip install --upgrade git+https://github.com/hdot123/memory.git@v0.8.0
```

For local development:

```bash
pip install -e ".[dev]"
```

## Quickstart

Initialize a target project:

```bash
memory-init --target /path/to/project
```

Validate the generated memory layout:

```bash
memory-validate --target /path/to/project
```

Migrate between schema versions:

```bash
memory-migrate --target /path/to/project --from 0.7.0 --to 0.8.0
```

## Core CLI commands

### `memory-init`

Creates or updates the standard project memory structure under `memory/system/`. Auto-fills detected project metadata (language, framework, toolchain, git remote) into project scope files.

Starting with v0.8.0, `memory-init` also creates the global knowledge base structure at `~/.memory/global-kb/` (idempotent) and writes the `[global_kb]` section into `memory/system/adapter.toml` to enable project-first / global-fallback routing.

```bash
memory-init --target /path/to/project [--scope my-project] [--host factory] [--mode create|adopt|update|repair] [--dry-run] [--force] [--no-clobber] [--no-auto-fill] [--json] [--version]
```

Modes:

| Mode | Purpose |
|---|---|
| `create` | Create a new memory layout. |
| `adopt` | Adopt an existing project while preserving business entry files. |
| `update` | Update marked memory-managed blocks and create missing files. |
| `repair` | Recreate missing required files without overwriting existing files. |

`memory-init` protects existing `AGENTS.md`, `INDEX.md`, `project-map/**`, and `CLAUDE.md` unless a managed block can be safely updated.

### Layout governance

Use these commands before or after adoption to inspect legacy layouts, runtime residue, and root-level generated reports:

```bash
memory-audit-layout --target /path/to/project --json
memory-plan-residue --target /path/to/project --output residue-plan.json
memory-apply-residue-plan --target /path/to/project --plan residue-plan.json --dry-run
```

`memory-apply-residue-plan` only applies low-risk actions automatically, such as moving recognized generated root reports to `artifacts/reports/`. It does not overwrite protected business entry points.

### `memory-validate`

Checks that `memory/system/` exists, required files are present, frontmatter and TOML are valid, version fields are compatible, and pollution guards pass.

```bash
memory-validate --target /path/to/project [--dry-run] [--json]
```

### `memory-migrate`

Runs version/schema migrations and records the result in `migrations.log`.

```bash
memory-migrate --target /path/to/project --from 0.7.0 --to 0.8.0 [--dry-run] [--json] [--version]
```

The `0.7.0 → 0.8.0` migration injects the `[global_kb]` section into `adapter.toml` (with defaults `enabled = true`, `root = "~/.memory/global-kb"`) and bumps the pinned version. It is idempotent: if `[global_kb]` already exists, it only updates the version.

### `memory-promote`

Promotes auto-captured knowledge candidates from the global KB `pending/` directory into a formal domain (`operations/`, `engineering/`, or `collaboration/`). This is the human confirmation step of the sedimentation flow: `session-end` auto-captures candidates into `~/.memory/global-kb/pending/`, and `memory-promote` moves a reviewed file into its target domain and updates `INDEX.md`.

```bash
memory-promote                                          # List pending candidates
memory-promote <file> --to operations|engineering|collaboration
memory-promote --version
```

## Generated project layout

A target project initialized by `memory-init` receives a project-local memory layout, and `memory-init` also ensures the shared global knowledge base exists:

```text
~/.memory/global-kb/                  ← Layer 2: shared global KB (created once, idempotent)
├── INDEX.md
├── operations/
│   └── README.md
├── engineering/
│   └── README.md
├── collaboration/
│   └── README.md
└── pending/                          ← Auto-captured candidates (promote via memory-promote)
    └── README.md

<project>/
├── memory/
│   ├── system/
│   │   ├── memory.lock
│   │   ├── adapter.toml              ← Includes [global_kb] section (v0.8.0+)
│   │   ├── migrations.log
│   │   ├── manifest.json
│   │   ├── integrity-audit.jsonl
│   │   └── kb/
│   ├── kb/
│   │   └── INDEX.md
│   ├── docs/
│   └── log/
├── project-map/
├── artifacts/memory-hook/
└── INDEX.md
```

The global KB (`~/.memory/global-kb/`) is shared across every project that enables global routing; each project still owns its own `memory/`, `project-map/`, and `artifacts/memory-hook/`. Project memory and runtime artifacts belong to the target project. The memory-core repository contains the reusable protocol, code, templates, schemas, fixtures, and documentation.

## Global hook setup

memory-core supports Factory Droid global hook entry points. Global hooks act as stable wrappers and route each event back to the current project directory.

Factory Droid:

```bash
memory-factory-hooks install --storage-root ~/.memory-core
```

Global state under `~/.memory-core` stores host-level lifecycle/path-index data and integrity keys; it is not a project memory pool. Project memory lives under the target project’s `memory/system/`, `memory/`, and `artifacts/memory-hook/` paths.

## Documentation

- [Documentation index](memory/docs/system/INDEX.md)
- [`memory/` specification](memory/docs/system/DOT_MEMORY_SPEC.md)
- [`memory.lock` specification](memory/docs/system/MEMORY_LOCK_SPEC.md)
- [Repository boundary](memory/docs/system/BOUNDARY.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Development and verification

```bash
ruff check .
python -m pytest tests/
python3 scripts/check_boundary.py
```

## Version and license

- Current documented release: v0.8.0
- Python: >= 3.9
- License: MIT. See [LICENSE](LICENSE).
