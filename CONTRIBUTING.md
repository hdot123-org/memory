# Contributing to memory-core

## Branch model

- `main` — stable branch protected by CI.
- `feature/*` — feature branches created from `main` and deleted after merge.

## Workflow

1. Create a feature branch from `main`: `git checkout -b feature/xxx`.
2. Make focused changes and keep generated or local-only artifacts out of the PR.
3. Run local checks before opening a PR.
4. Push the branch and create a PR against `main`.
5. Wait for CI and review to pass before merging.

## CI

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | push/PR to `main` | ruff lint + pytest on Python 3.9/3.10/3.11/3.12 |
| `release-and-dispatch.yml` | tag `v*` | full matrix tests, version validation, build, GitHub Release, PyPI publish |

## Local development

```bash
# Install in editable mode
pip install -e ".[dev]"

# Tests
python -m pytest tests/

# Lint
ruff check .

# Common full local check
ruff check . && python -m pytest tests/
```

## Code style

- Use ruff with the repository configuration.
- Target Python 3.9+.
- Keep line width within the configured project limit.
- Use concise commit messages such as `feat: ...`, `fix: ...`, `chore: ...`, or `docs: ...`.

## Documentation hygiene

Public documentation should be safe for open-source readers and reusable across projects. When editing docs:

- Do not include real local absolute paths; use placeholders such as `/path/to/project` or `<project-root>`.
- Do not add internal session records, agent transcripts, private review notes, or `.factory` session artifacts to public docs.
- Do not quote unredacted audit, residue, customer, infrastructure, token, credential, or private repository details.
- Keep `docs/audit/**`, `docs/RESIDUE_*.md`, archive material, and local review indexes out of primary user navigation unless clearly labeled as maintainer/internal records.
- Prefer small, focused documentation updates that match current CLI behavior.

If a documentation change requires mentioning sensitive or environment-specific information, redact it or replace it with a generic example before opening a PR.

## Versioning

- Maintain the package version only in `pyproject.toml` under `[project].version`.
- Follow SemVer: MAJOR.MINOR.PATCH.
- Release tags must use `vX.Y.Z` and match `pyproject.toml`.

## Release process

1. Update `pyproject.toml` version.
2. Commit and tag:

   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to x.y.z"
   git tag vx.y.z
   git push origin main vx.y.z
   ```

3. The release workflow runs tests, validates the tag/version match, builds artifacts, and publishes.
4. Verify the release, for example: `pip install memory-core==x.y.z`.
