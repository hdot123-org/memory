# Documentation Index

This index is the public entry point for memory-core documentation. Normal users should start with the README and specification/reference docs; archived audit and residue records are maintainer context only.

## Getting started / CLI reference

- [README](../../README.md) — project overview, installation, quickstart, core CLI commands, global hook setup, and layout governance commands.
- [Changelog](../../CHANGELOG.md) — release notes and unreleased changes.
- [Contributing](../../CONTRIBUTING.md) — contribution workflow and documentation hygiene rules.

## Specification / reference docs

- [`.memory/` directory specification](DOT_MEMORY_SPEC.md) — canonical project memory layout, generated runtime files, validation expectations, and layout governance behavior.
- [`memory.lock` specification](MEMORY_LOCK_SPEC.md) — version lock schema and compatibility rules.
- [Repository boundary](BOUNDARY.md) — what belongs in memory-core versus a consumer project.

## Migration docs

These documents describe migration formats and historical migration processes. Some are archived references and may mention legacy paths or workflows that are not current implementation guidance.

- [Migration format specification](../../memory/docs/archive/MIGRATION_FORMAT_SPEC.md) — archived migration format specification (instance-specific, not tracked)
- Migration rules and checklist are also in `memory/docs/archive/` (instance-specific, not tracked)

## Architecture / design docs

Detailed architecture documents live under [`docs/architecture/`](../architecture/):

- [`01-architecture.md`](../architecture/01-architecture.md)
- [`02-gateway.md`](../architecture/02-gateway.md)
- [`03-core-assembly.md`](../architecture/03-core-assembly.md)
- [`04-interfaces.md`](../architecture/04-interfaces.md)
- [`05-implementations.md`](../architecture/05-implementations.md)
- [`06-adapters.md`](../architecture/06-adapters.md)
- [`07-policy-governance.md`](../architecture/07-policy-governance.md)
- [`08-data-pipeline.md`](../architecture/08-data-pipeline.md)
- [`09-provider-fallback.md`](../architecture/09-provider-fallback.md)
- [`10-consumer-boundary.md`](../architecture/10-consumer-boundary.md)
- [`API-CONTRACT.md`](../architecture/API-CONTRACT.md)

## Plans & milestones

Plans and milestones documents are instance-specific and live in `memory/docs/plans/` (not tracked).

## Specifications (extended)

- [Multi-project scan](MULTI_PROJECT_SCAN_SPEC.md) — multi-project upgrade scan registry pointer spec (SPEC-012).

## Engineering notes

Engineering notes are instance-specific and live in `memory/docs/notes/` (not tracked).

## Bug reports

- `docs/bug-reports/**` — filed bug reports and crash analyses.

## Maintainer / internal records

The following records are useful for maintainers but are not required for normal users and should not be treated as primary documentation:

- `docs/audit/**` — audit notes and session-specific findings.
- `docs/RESIDUE_*.md` — residue inventories and disposition plans.
- `docs/archive/**` and repository `archive/**` — historical or superseded material.
- `.factory/review-index.md` and other local review/session records, when present.
