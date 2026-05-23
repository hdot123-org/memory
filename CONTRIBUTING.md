# Contributing to memory-core

## Branch model

- `main` — stable branch protected by CI.
- `feature/*` — feature branches created from `main` and deleted after merge.

## Workflow

**This project follows a GitLab-first development flow. All projects managed via Factory/Droid must comply.**

### Iron Rule: GitLab → GitHub (one-way mirror)

1. **All code changes flow through GitLab first.**
   - Create feature branch from `main` on GitLab.
   - Push to GitLab, create Merge Request.
   - CI pipeline (lint + test + health-check) must pass before merge.
   - Only merge to `main` after CI green.

2. **GitHub is a read-only mirror.**
   - Only GitLab CI can push to GitHub (sync-to-github job).
   - **Never push directly to GitHub from any machine, agent, or CI runner.**
   - Violating this rule breaks the single-source-of-truth guarantee.

3. **Agents (Factory/Droid) must not bypass this flow.**
   - Use `git push gitlab <branch>` only.
   - Create MR via GitLab API or push options.
   - Wait for CI pipeline to pass.
   - Merge MR via GitLab API.

### Step-by-step

1. Create a feature branch from `main`: `git checkout -b feature/xxx`
2. Make focused changes and keep generated or local-only artifacts out.
3. Run local checks: `ruff check . && python -m pytest tests/`
4. Push to GitLab: `git push -u gitlab feature/xxx`
5. Create MR (via push options or GitLab UI/API).
6. Wait for CI pipeline to pass (test + health-check).
7. Merge MR. CI will auto-sync to GitHub.

### memory-init sync bootstrap

For consumer projects initialized by memory-core, run `memory-init --sync` to generate:
- `.gitlab-ci.yml` with `test` -> `health-check` -> `sync-to-<mirror>` hard gate flow.
- `.memory/skills/gitlab_sync_workflow.yaml` with `submit_gitlab`, `merge_after_ci`, `sync_github` skill workflow.

Mirror sync requires CI secret variable `<MIRROR_REMOTE>_TOKEN` (example: `GITHUB_TOKEN`).
This variable must be stored in GitLab CI/CD Variables as masked + protected.

### ShowDoc sync (optional)

When ShowDoc document sync is needed, initialize with `memory-init --sync --sync-showdoc`:

**What gets generated:**
- `scripts/sync_to_showdoc.py` — sync script that runs in CI
- `[sync.showdoc]` section in `.memory/adapter.toml` with `item_id`, `core_files`, etc.
- `sync-to-showdoc` job in `.gitlab-ci.yml` (runs in parallel with `sync-to-github`)

**CI flow:**
```
push to main -> test -> health-check -> merge
                                      ├── sync-to-github (GitHub mirror)
                                      └── sync-to-showdoc (ShowDoc pages, upsert by title)
```

**Required CI variables** (GitLab CI/CD Variables, masked + protected):

| Variable | Description |
|----------|-------------|
| `SHOWDOC_API_KEY` | ShowDoc API key for authentication |
| `SHOWDOC_API_TOKEN` | ShowDoc API token for authentication |
| `SHOWDOC_URL` | ShowDoc instance URL (e.g., `http://REDACTED_IP`) |

**How it works:**
1. The sync script reads `[sync.showdoc]` config from `adapter.toml`
2. Scans files matching `core_files` and `extra_patterns` glob patterns
3. Compares SHA256 hashes against `.showdoc-manifest.json` for incremental sync
4. Changed files are uploaded via ShowDoc Open API (`updateByApi`, upsert by `page_title`)
5. `cat_name` is derived from file path (e.g., `docs/design/01-arch.md` → "设计文档")
6. Markdown content is validated against showdoc-markdown-compat safe subset
7. Manifest is updated on successful sync

**Idempotency guarantee:** Multiple runs with the same files produce no duplicate pages (upsert by `page_title`).

**Failure tolerance:** Single file failure does not block other files. API calls retry 3 times with exponential backoff (5s/15s/30s).

### Violations

If code is accidentally pushed directly to GitHub:
1. Do NOT attempt to fix by pushing more code.
2. Revert the GitHub commit.
3. Re-submit the change through GitLab MR flow.
4. Verify CI sync restores consistency.

## CI

### GitLab CI (primary)

| Stage | Job | Trigger | Purpose |
|-------|-----|---------|---------|
| test | `test` | push | ruff lint + pytest |
| health-check | `health-check` | push | boundary + structure validation |
| sync | `sync-to-github` | merge to main | push to GitHub mirror |

The `sync-to-github` job only runs after test + health-check both pass.

### GitHub Actions (mirror-only)

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | push/PR to `main` | ruff lint + pytest (mirror validation) |
| `release-and-dispatch.yml` | tag `v*` | release pipeline |

GitHub Actions run for validation only; all merges happen on GitLab.

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
2. Commit and tag on GitLab:
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to x.y.z"
   git tag vx.y.z
   git push gitlab main vx.y.z
   ```
3. GitLab CI runs tests and syncs to GitHub.
4. GitHub release workflow publishes artifacts.
5. Verify: `pip install memory-core==x.y.z`
