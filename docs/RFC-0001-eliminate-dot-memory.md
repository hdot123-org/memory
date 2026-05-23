# RFC: v0.5.0 — Eliminate Project-Level `.memory/` Directory

> **Status**: draft  
> **Author**: busiji  
> **Date**: 2026-05-23  
> **Version target**: 0.5.0  
> **Breaking change**: Yes

---

## 1. Problem

### Current Three-Layer Architecture

```
~/.memory-core/              ← Layer 1: Global runtime (events, project registry, quarantine)
/Users/busiji/workbot/
  .memory/                   ← Layer 2: Project protocol (adapter.toml, ownership.toml, CANONICAL.md, ...)
  memory/                    ← Layer 3: Project data (docs, kb, decisions, research, system/)
```

### Issues

1. **Cognitive overhead**: Two entry points (`.memory/` hidden + `memory/` visible) per project. Users must understand the relationship between three scattered locations.

2. **Content duplication**: `.memory/CANONICAL.md`, `STATE.md`, `TASKS.md` overlap with `CLAUDE.md`, `AGENTS.md`, and `memory/kb/` content.

3. **Hidden directory anti-pattern**: `.memory/` is invisible in `ls` output, making discovery harder for new users.

4. **Inconsistent dogfooding**: The `memory` repo itself has `.memory/` with only `adapter.toml` and `ownership.toml` — no content files — showing even the author doesn't use the full protocol.

5. **Bloated manifest**: `.memory/manifest.json` (1.2MB in workbot) is regenerated per session and committed alongside code.

6. **No real enforcement**: `ownership.toml` declares directories as "critical" but nothing actually prevents writes — it's purely advisory.

### Evidence

| Project | `.memory/` files | Actually maintained by human? |
|---------|-----------------|-------------------------------|
| workbot | 15 files, 1.2MB manifest | No — AI-generated templates |
| memory (self) | 2 files (adapter + ownership) | Partially — config only |

---

## 2. Proposal: Two-Layer Architecture

### Target Architecture

```
~/.memory-core/              ← Layer 1: Global runtime (unchanged)
  project-lifecycle/
  quarantine/
  keys/

/Users/busiji/workbot/
  memory/                    ← Layer 2: Single project entry point
    system/                  ← Config & state (was .memory/)
      adapter.toml           ← Adapter configuration
      ownership.toml         ← Ownership declaration
      memory.lock            ← Version lock
      migrations.log         ← Migration history
      integrity-audit.jsonl  ← Audit trail
      manifest.json          ← File manifest
    kb/                      ← Knowledge base (unchanged)
    docs/                    ← Documentation (unchanged)
    log/                     ← Logs (unchanged)
```

### Key Changes

| Before (v0.4.x) | After (v0.5.0) | Rationale |
|------------------|-----------------|-----------|
| `.memory/adapter.toml` | `memory/system/adapter.toml` | Single visible entry point |
| `.memory/ownership.toml` | `memory/system/ownership.toml` | Same |
| `.memory/memory.lock` | `memory/system/memory.lock` | Same |
| `.memory/manifest.json` | `memory/system/manifest.json` | Same |
| `.memory/migrations.log` | `memory/system/migrations.log` | Same |
| `.memory/integrity-audit.jsonl` | `memory/system/integrity-audit.jsonl` | Same |
| `.memory/CANONICAL.md` | **Removed** | Redundant with project README/CLAUDE.md |
| `.memory/STATE.md` | **Removed** | Redundant with `memory/system/health-report.json` |
| `.memory/PLAN.md` | **Removed** | Unused template (always empty) |
| `.memory/TASKS.md` | **Removed** | Redundant with Linear/project tools |
| `.memory/NOW.md` | **Removed** | Redundant with project state tracking |
| `.memory/kb/` | **Removed** | Was created but never used (kb lives in `memory/kb/`) |
| `.memory/skills/` | **Removed** | Never used in practice |
| `.memory/backups/` | `memory/system/backups/` | Migration backups |

### What Stays Unchanged

- `~/.memory-core/` global runtime — no changes
- `memory/kb/`, `memory/docs/`, `memory/log/` — no changes
- `project-map/` — no changes
- All hook adapters (codex, claude, factory) — internal path lookup only
- Public CLI API (`memory-init`, `memory-validate`, etc.) — same interface

---

## 3. Implementation Plan

### Phase 1: Core Path Migration

#### 3.1 Constants (`constants.py`)

```python
# Before
REQUIRED_MEMORY_FILES = [
    "memory.lock", "adapter.toml", "CANONICAL.md", ...
]

# After
SYSTEM_DIR = "memory/system"

REQUIRED_SYSTEM_FILES = [
    "memory.lock", "adapter.toml", "migrations.log",
]

# CANONICAL.md, STATE.md, PLAN.md, TASKS.md, NOW.md: REMOVED
# These were AI-generated templates with no real value.
```

#### 3.2 Init (`init_project_memory.py` — 87KB, ~2184 lines)

**Highest-risk file.** Changes:

1. Replace all `target / ".memory"` with `target / "memory" / "system"`
2. Remove generation of CANONICAL.md, STATE.md, PLAN.md, TASKS.md, NOW.md
3. Remove `.memory/kb/` directory creation (redundant with `memory/kb/`)
4. Remove `.memory/skills/` directory creation
5. Keep adapter.toml, ownership.toml, memory.lock, migrations.log generation
6. Update manifest.json output path

**Affected line ranges** (from grep):
- Lines 88-95: `DOT_MEMORY_DIRS` list
- Lines 199-209: adapter.toml template path
- Lines 315, 390, 597, 648: docstring/comments referencing `.memory/`
- Lines 1242: CANONICAL.md path
- Lines 1637-1677: main init function
- Lines 1767-1807: file conflict checks
- Lines 1920+: template writing
- Lines 2078-2092: skills dir
- Lines 2114-2120: manifest signing

#### 3.3 Migrate (`migrate_project_memory.py` — 32KB)

1. Add `0.4_to_0.5` migration step:
   - Move `.memory/adapter.toml` → `memory/system/adapter.toml`
   - Move `.memory/ownership.toml` → `memory/system/ownership.toml`
   - Move `.memory/memory.lock` → `memory/system/memory.lock`
   - Move `.memory/migrations.log` → `memory/system/migrations.log`
   - Move `.memory/manifest.json` → `memory/system/manifest.json`
   - Move `.memory/integrity-audit.jsonl` → `memory/system/integrity-audit.jsonl`
   - Delete `.memory/CANONICAL.md`, `STATE.md`, `PLAN.md`, `TASKS.md`, `NOW.md`
   - Delete `.memory/kb/`, `.memory/skills/`, `.memory/backups/`
   - Delete empty `.memory/` directory
2. Update `adapter.toml` version from `0.4.0` to `0.5.0`
3. Backup mechanism: copy `.memory/` to `memory/system/backups/` before migration

#### 3.4 Validate (`validate_project_memory.py` — 34KB)

1. Replace `target / ".memory"` with `target / "memory" / "system"`
2. Remove validation of CANONICAL.md, STATE.md, PLAN.md, TASKS.md frontmatter
3. Remove validation of `.memory/kb/` structure
4. Keep adapter.toml and ownership.toml validation

#### 3.5 Ownership (`ownership_cli.py` + `ownership.py`)

1. Line 39: `project_root / ".memory" / "ownership.toml"` → `project_root / "memory" / "system" / "ownership.toml"`
2. Line 517-520: `.memory/` dir creation → `memory/system/`

#### 3.6 Adapter Schema (`adapter_toml_schema.py`)

1. Update path references from `.memory/adapter.toml` to `memory/system/adapter.toml`

#### 3.7 Hook Gateway (`memory_hook_gateway.py` — 61KB)

1. Line 1278: `project_root / ".memory" / "STATE.md"` → `project_root / "memory" / "system"`
2. Line 1407: `.memory/**` exclusion pattern → `memory/system/**`
3. All internal `.memory/` path lookups → `memory/system/`

#### 3.8 Hook Files (`*_global_hooks.py` × 3)

1. `claude_global_hooks.py`: update `.memory/` path lookups
2. `codex_global_hooks.py`: same
3. `factory_global_hooks.py`: same

#### 3.9 Other Tools

| File | Change |
|------|--------|
| `audit_project_layout.py` | Layout audit paths |
| `consistency_check.py` | Consistency check paths |
| `memory_health_report.py` | Health report output path |
| `memory_hook_integrity_manifest.py` | Manifest path |
| `memory_hook_impls.py` | Implementation paths |
| `pretooluse_guard.py` | Guard paths |
| `project_probe.py` | Probe paths |
| `template_sync.py` | Template paths |
| `verify_consumer.py` | Consumer verification paths |
| `hook_upgrade.py` | Upgrade paths |
| `memory_hook_config.py` | Config paths |
| `validate_memory_system.py` | System validation paths |

### Phase 2: Template & Spec Updates

- `workspace/templates/.memory/adapter.toml` → `workspace/templates/memory/system/adapter.toml`
- `docs/DOT_MEMORY_SPEC.md` — update spec to reflect new layout
- `docs/BOUNDARY.md` — update boundary docs
- `docs/MEMORY_LOCK_SPEC.md` — update lock spec

### Phase 3: Test Updates (90 test files)

All test files with `.memory` fixtures need path updates. Key files:

- `test_cli_init.py` — init creates `memory/system/` not `.memory/`
- `test_cli_migrate.py` — migration moves `.memory/` to `memory/system/`
- `test_init_*.py` (6 files) — init fixtures
- `test_validate_project_memory_direct.py` — validation paths
- `test_ownership_cli.py` — ownership paths
- `test_adapter_toml_strict.py` — adapter paths
- `test_*_global_hooks.py` (3 files) — hook paths
- `test_memory_hook_gateway_*.py` (4 files) — gateway paths
- All other test files referencing `.memory`

### Phase 4: Consumer Projects Migration

After v0.5.0 release:

1. `workbot` — run `memory-migrate --from 0.4.0 --to 0.5.0`, delete `.memory/`
2. `memory` (self) — same
3. Any other projects registered in `~/.memory-core/project-lifecycle/projects/`

---

## 4. Migration Safety

### Backup Strategy

The `0.4_to_0.5` migration:
1. Creates `memory/system/backups/pre-0.5/` with all `.memory/` contents
2. Moves config files to `memory/system/`
3. Deletes redundant content files
4. Removes empty `.memory/` directory
5. Updates `adapter.toml` version to `0.5.0`
6. Appends migration log entry

### Rollback

If migration fails:
1. `memory-migrate --rollback` restores from `memory/system/backups/pre-0.5/`
2. Re-creates `.memory/` with original contents

### Idempotency

Running `memory-migrate` on an already-migrated project is a no-op.

---

## 5. Version Strategy

- **v0.4.0** — current stable, last version with `.memory/`
- **v0.5.0** — breaking change, new `memory/system/` layout
- Migration path: `0.4.0 → 0.5.0` (no intermediate versions needed)

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Init rewrite breaks (87KB file) | Medium | High | Incremental refactoring, test-first |
| Test suite regression | Medium | Medium | 90 test files, automated CI |
| Consumer projects stuck on 0.4 | Low | Medium | Migration script + rollback |
| `.memory/` still referenced in docs/specs | Low | Low | Grep for `.memory` before release |

---

## 7. Success Criteria

- [ ] `memory-init` creates `memory/system/` instead of `.memory/`
- [ ] `memory-migrate --from 0.4.0 --to 0.5.0` successfully migrates workbot
- [ ] `memory-validate` passes on migrated project
- [ ] All 90+ test files pass
- [ ] No `.memory` references remain in source code
- [ ] `DOT_MEMORY_SPEC.md` updated to reflect new layout
- [ ] workbot and memory repos both migrated successfully
