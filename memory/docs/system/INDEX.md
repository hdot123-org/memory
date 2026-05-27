# Documentation Index

This index is the public entry point for memory-core documentation. Normal users should start with the README and specification/reference docs; archived audit and residue records are maintainer context only.

## Getting started / CLI reference

- [README](../README.md) — project overview, installation, quickstart, core CLI commands, global hook setup, and layout governance commands.
- [Changelog](../CHANGELOG.md) — release notes and unreleased changes.
- [Contributing](../CONTRIBUTING.md) — contribution workflow and documentation hygiene rules.

## Specification / reference docs

- [`.memory/` directory specification](DOT_MEMORY_SPEC.md) — canonical project memory layout, generated runtime files, validation expectations, and layout governance behavior.
- [`memory.lock` specification](MEMORY_LOCK_SPEC.md) — version lock schema and compatibility rules.
- [Repository boundary](BOUNDARY.md) — what belongs in memory-core versus a consumer project.

## Migration docs

These documents describe migration formats and historical migration processes. Some are archived references and may mention legacy paths or workflows that are not current implementation guidance.

- [Migration format specification](MIGRATION_FORMAT_SPEC.md)
- [Migration rules](MIGRATION_RULES.md)
- [Migration checklist](MIGRATION_CHECKLIST.md)

## Architecture / design docs

Detailed design documents live under [`memory/docs/design/`](../memory/docs/design/):

- `01-architecture.md`
- `02-gateway.md`
- `03-core-assembly.md`
- `04-interfaces.md`
- `05-implementations.md`
- `06-adapters.md`
- `07-policy-governance.md`
- `08-data-pipeline.md`
- `09-provider-fallback.md`
- `10-consumer-boundary.md`
- `API-CONTRACT.md`

## Plans & milestones

- [PLAN-STATUS](PLAN-STATUS.md) — active plan status mirror (synced from ShowDoc).
- [PLAN-0003: 9/9 Hook coverage](PLAN-0003-9-9-HOOK-COVERAGE.md) — Factory hook 100% integration plan.
- [Ownership execution plan](EXECUTION_PLAN_OWNERSHIP_PROTECTION.md) — M1-M6 milestone execution steps.
- [Ownership upgrade plan](UPGRADE_PLAN_OWNERSHIP_PROTECTION.md) — v3 merged upgrade plan (design reference).

## Specifications (extended)

- [Multi-project scan](MULTI_PROJECT_SCAN_SPEC.md) — multi-project upgrade scan registry pointer spec (SPEC-012).

## Engineering notes

- [Prompt truncation solutions](prompt-truncation-engineering-solutions.md) — systematic solutions for Task prompt truncation.

## Bug reports

- `docs/bug-reports/**` — filed bug reports and crash analyses.

## Maintainer / internal records

The following records are useful for maintainers but are not required for normal users and should not be treated as primary documentation:

- `docs/audit/**` — audit notes and session-specific findings.
- `docs/RESIDUE_*.md` — residue inventories and disposition plans.
- `docs/archive/**` and repository `archive/**` — historical or superseded material.
- `.factory/review-index.md` and other local review/session records, when present.
