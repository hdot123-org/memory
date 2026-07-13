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
| `release.yml` | tag `v*` | release pipeline |

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
- Target Python 3.9+.
- Use concise commit messages: `feat:`, `fix:`, `chore:`, `docs:`.

## Documentation hygiene

Public documentation should be safe for open-source readers.
- Do not include real local absolute paths.
- Do not add internal session records, agent transcripts, or private review notes.
- Redact sensitive information before opening a PR.

## Versioning

- Maintain version only in `pyproject.toml` under `[project].version`.
- Follow SemVer: MAJOR.MINOR.PATCH.
- Release tags must use `vX.Y.Z` and match `pyproject.toml`.

## Release process

1. Update `pyproject.toml` version.
2. Commit and push to GitHub:
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to x.y.z"
   git push origin main
   ```
3. Create and push tag:
   ```bash
   git tag vx.y.z
   git push origin vx.y.z
   ```
4. GitHub Actions CI runs tests and release workflow publishes artifacts.
5. Verify: `pip install memory-core==x.y.z`
