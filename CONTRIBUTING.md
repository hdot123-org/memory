# Contributing to memory-core

## Branch model

- `main` — stable branch protected by CI.
- `feature/*` — feature branches created from `main` and deleted after merge.

## Workflow

**This project follows a GitHub PR workflow with dual-gate approval.**

### Dual-Gate Approval Process

1. **All code changes flow through feature branches and pull requests.**
   - Create feature branch from `main` on GitHub.
   - Push to GitHub, create Pull Request.
   - CI pipeline (ruff + pytest) must pass (ci-ok gate).
   - Code review by droid must pass (droid-review gate).
   - Squash merge to `main` after both gates green.

2. **No direct pushes to `main`.**
   - All changes require PR approval.
   - Violating this rule bypasses the dual-gate protection.

3. **Agents (Factory/Droid) must follow this flow.**
   - Use `git push origin <branch>` to push feature branches.
   - Create PR via GitHub UI or `gh pr create`.
   - Wait for both ci-ok and droid-review gates to pass.
   - Squash merge PR via GitHub.

### Step-by-step

1. Create a feature branch from `main`: `git checkout -b feature/xxx`
2. Make focused changes and keep generated or local-only artifacts out.
3. Run local checks: `ruff check . && python -m pytest tests/`
4. Push to GitHub: `git push -u origin feature/xxx`
5. Create PR: `gh pr create --title "..." --body "..."`
6. Wait for dual-gate approval (ci-ok + droid-review).
7. Squash merge PR after both gates green.

## CI

### GitHub Actions (primary)

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | push/PR to `main` | ruff lint + pytest (ci-ok gate) |
| `release-please.yml` | push to `main` | 自动版本管理，创建 Release PR |
| `release-and-dispatch.yml` | tag `v*` / workflow_dispatch | release pipeline + 下游通知 |

The `ci.yml` workflow validates:
- Ruff lint passes
- pytest suite passes
- Memory system integrity
- Boundary guard checks

**Dual-gate approval:** PRs require both ci-ok (CI passes) and droid-review (code review passes) before squash merge.

## Local development

```bash
pip install -e ".[dev]"
python -m pytest tests/
ruff check .
ruff check . && python -m pytest tests/
```

## Code style

- Use ruff with the repository configuration.
- Target Python 3.12.
- Use concise commit messages: `feat:`, `fix:`, `chore:`, `docs:`.

## Test naming convention

All test files must follow the `test_*.py` naming pattern so pytest auto-discovers them. Test functions must use the `test_*` prefix and descriptive names that indicate what behavior is verified.

**File naming:**
- Test files: `test_<module_name>.py` (e.g. `test_feature_flags.py` for `feature_flags.py`)
- Place tests under `tests/` mirroring the source tree structure

**Function naming:**
- Test functions: `test_<what_is_being_tested>` (e.g. `test_is_enabled_returns_true_for_1`)
- Use descriptive names that explain the expected behavior
- Avoid generic names like `test_basic` or `test_it_works`

**Class naming:**
- Test classes: `Test<ClassUnderTest>` (e.g. `TestPostHogAnalytics`)
- Group related tests in classes when they share setup/teardown

## Documentation hygiene

Public documentation should be safe for open-source readers.
- Do not include real local absolute paths.
- Do not add internal session records, agent transcripts, or private review notes.
- Redact sensitive information before opening a PR.

## Release Process

本项目使用 [release-please](https://github.com/googleapis/release-please-action) 自动化版本管理。

### 自动发版流程

1. **提交代码** — 使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：
   - `feat:` → minor 版本（0.9.5 → 0.10.0）
   - `fix:` → patch 版本（0.9.5 → 0.9.6）
   - `feat!:` 或 `fix!:` → major 版本（0.9.5 → 1.0.0）
   - `chore:`, `docs:`, `test:`, `refactor:` → 不触发新版本
2. **合并 PR 到 main** — release-please 自动创建 Release PR
3. **合并 Release PR** — 自动创建 tag + GitHub Release + 构建 wheel

### 版本号维护

release-please 自动更新以下文件：
- `pyproject.toml`
- `memory_core/constants.py`
- `README.md`
- `CHANGELOG.md`

测试文件通过 `CURRENT_MEMORY_VERSION` 动态读取版本号，无需手动更新。

### 手动发版（备用）

通过 GitHub Actions 的 `workflow_dispatch` 手动触发 `release-and-dispatch.yml`：
```bash
gh workflow run release-and-dispatch.yml \
  -f release_tag=v0.9.6 \
  -f dispatch_targets="owner/repo1,owner/repo2"
```

### 回滚

使用 `scripts/release_rollback.sh` 回滚 release（需在 GitHub Release 页面手动删除对应 release）。

> **完整操作手册**：详见 [`RELEASE.md`](RELEASE.md)，包含故障排查、下游通知、hotfix 流程等。

## Versioning

遵循 [Semantic Versioning](https://semver.org/)：`MAJOR.MINOR.PATCH`

- **MAJOR** — 不兼容的 API 变更
- **MINOR** — 向后兼容的新功能
- **PATCH** — 向后兼容的 bug 修复

Python 版本：CI 固定 3.12（见决策 D-008）。

<!-- INFRA-23 review-mapping test marker 1785737789 -->

<!-- INFRA-24 e2e-mission-verify test marker 1785620671 -->

<!-- INFRA-27 valt-chain-b test marker 1785738372 -->

<!-- INFRA-28 valt-chain-c test marker 1785691961 -->

<!-- INFRA-1 linear-gateway-fullchain test marker 1785733640 -->

<!-- INFRA-28 valt-chain-c test marker 1785738011 -->

<!-- INFRA-26 valt-chain-a test marker 1785738928 -->

<!-- INFRA-29 valt-chain-nodeleg test marker 1785747578 -->

<!-- INFRA-6 sole-executor-full-flow test marker 1785719500 -->
