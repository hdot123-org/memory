# Plan Status Mirror

> This file mirrors external ShowDoc plan pages so repository-local scans can detect stale plan state.
> Source of external truth: ShowDoc project 664858316
> Local mirror owner: main orchestration agent
> Last sync: 2026-05-14

## Status Enum

- `planning` — proposed, not started
- `in_progress` — executing
- `completed` — done and verified
- `blocked` — blocked, requires action

## Plans

<!-- PLAN_STATUS_START -->

### PLAN-0001: v0.4.0 Beta Quality Hardening

```yaml
plan_id: PLAN-0001
title: "Alpha → Beta/Stable 质量加固计划"
status: completed
version: v0.4.0-beta
showdoc:
  item_id: 664858316
  page_id: 269622139
  page_title: "Alpha → Beta/Stable 质量加固计划"
owner: main-agent
last_sync: 2026-05-14
last_verified: 2026-05-14
```

#### Checklist

| id | item | status | owner | evidence | last_updated |
|---|---|---|---|---|---|
| P0001-C001 | Test coverage ≥ 90% | completed | subagent | 7 new test files, 246 tests, 1351 total passed | 2026-05-14 |
| P0001-C002 | Lint ignore ≤ 5 | completed | subagent | F821/F401/F841/E741 all zero, only E501/E402 global | 2026-05-14 |
| P0001-C003 | CLI API frozen | completed | subagent | 11 CLI signatures frozen, ShowDoc page 269622140 | 2026-05-14 |
| P0001-C004 | Python API documented | completed | subagent | 9 pages written to ShowDoc Python API 目录 | 2026-05-14 |
| P0001-C005 | CI gate ready | completed | subagent | .github/workflows/ci.yml exists, pytest + ruff | 2026-05-14 |
| P0001-C006 | Development Status → Beta | completed | main-agent | pyproject.toml updated to "4 - Beta" | 2026-05-14 |
| P0001-C007 | Version bump to 0.4.0 | completed | main-agent | constants.py + pyproject.toml + CHANGELOG | 2026-05-14 |
| P0001-C008 | Doc audit and fix | completed | subagent | 2C+8H+6M = 16 items fixed | 2026-05-14 |
| P0001-C009 | ShowDoc plan page synced | completed | main-agent | page 269622139 updated with results | 2026-05-14 |

#### Blockers

None.

#### Sync Notes

- 2026-05-14: Plan created, all milestones completed, ShowDoc page synced.

### PLAN-0002: Ownership 保护升级

```yaml
plan_id: PLAN-0002
title: "Ownership 保护升级 (M1-M6)"
status: completed
version: v0.4.0
showdoc:
  item_id: 664858316
owner: main-agent
last_sync: 2026-05-18
last_verified: 2026-05-18
```

#### Checklist

| id | item | status | owner | evidence | last_updated |
|---|---|---|---|---|---|
| P0002-C001 | M1: Ownership 数据模型 + classify API | completed | subagent | ownership.py 641行, 37测试通过 | 2026-05-18 |
| P0002-C002 | M5a: PreToolUse P0 拦截 | completed | subagent | pretooluse_guard.py 620行, 40测试通过 | 2026-05-18 |
| P0002-C003 | M2: init/validate/audit ownership-aware | completed | subagent | 21测试通过, force限制+4类检查 | 2026-05-18 |
| P0002-C004 | M3: Source repo readonly context-package | completed | subagent | 16测试通过, git status/mtime不变 | 2026-05-18 |
| P0002-C005 | M4: Integrity v2 + 禁止 auto re-sign | completed | subagent | 18测试通过, re-sign CLI | 2026-05-18 |
| P0002-C006 | M5b: 子代理 policy 注入 | completed | subagent | 含在 pretooluse_guard 中 | 2026-05-18 |
| P0002-C007 | M6: 管辖域变更 CLI + hook 升级 | completed | subagent | ownership_cli 588行, hook_upgrade 455行 | 2026-05-18 |
| P0002-C008 | 全量测试通过 | completed | subagent | 1612 passed, 0 failed | 2026-05-18 |

#### Blockers: None

<!-- PLAN_STATUS_END -->
