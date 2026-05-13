# memory-core

memory-core provides a reusable `.memory/` protocol, templates, schemas, and CLI tools for project-scoped memory management. It is an open-source library for initializing, validating, migrating, and auditing memory layouts; it does not store business project state in this repository.

## Install

Install from a GitHub release wheel:

```bash
gh release download v0.3.0 --repo hdot123/memory --pattern "*.whl"
pip install memory_core-0.3.0-py3-none-any.whl
```

Install from source:

```bash
pip install git+https://github.com/hdot123/memory.git@v0.3.0
```

Upgrade by changing the version and adding `--upgrade`:

```bash
pip install --upgrade git+https://github.com/hdot123/memory.git@v0.3.0
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
memory-migrate --target /path/to/project --from 0.2.0 --to 0.3.0
```

## Core CLI commands

### `memory-init`

Creates or updates the standard project memory structure.

```bash
memory-init --target /path/to/project [--scope my-project] [--host codex|factory|claude] [--mode create|adopt|update|repair] [--dry-run] [--json]
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

Checks that `.memory/` exists, required files are present, frontmatter and TOML are valid, version fields are compatible, and pollution guards pass.

```bash
memory-validate --target /path/to/project [--dry-run] [--json]
```

### `memory-migrate`

Runs version/schema migrations and records the result in `migrations.log`.

```bash
memory-migrate --target /path/to/project --from 0.2.0 --to 0.3.0 [--dry-run] [--json]
```

## Generated project layout

A target project initialized by `memory-init` receives a project-local memory layout:

```text
.memory/
├── memory.lock
├── adapter.toml
├── CANONICAL.md
├── PLAN.md
├── STATE.md
├── TASKS.md
├── NOW.md
├── inbox.md
├── migrations.log
├── manifest.json
└── kb/

memory/
├── kb/
├── docs/
└── system/

project-map/
artifacts/memory-hook/
INDEX.md
```

Project memory and runtime artifacts belong to the target project. The memory-core repository contains the reusable protocol, code, templates, schemas, fixtures, and documentation.

## Global hook setup

memory-core supports Codex App and Factory Droid global hook entry points. Global hooks act as stable wrappers and route each event back to the current project directory.

Codex App:

```bash
memory-codex-hooks install --storage-root ~/.memory-core
```

Factory Droid:

```bash
memory-factory-hooks install --storage-root ~/.memory-core
```

Global state under `~/.memory-core` stores host-level lifecycle/path-index data and integrity keys; it is not a project memory pool. Project memory remains under the target project’s `.memory/`, `memory/`, and `artifacts/memory-hook/` paths.

## Documentation

- [Documentation index](docs/INDEX.md)
- [`.memory/` specification](docs/DOT_MEMORY_SPEC.md)
- [`memory.lock` specification](docs/MEMORY_LOCK_SPEC.md)
- [Repository boundary](docs/BOUNDARY.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Development and verification

```bash
ruff check .
python -m pytest tests/
python3 scripts/check_boundary.py
```

## Version and license

- Current documented release: v0.3.0
- Python: >= 3.9
- License: MIT. See [LICENSE](LICENSE).
