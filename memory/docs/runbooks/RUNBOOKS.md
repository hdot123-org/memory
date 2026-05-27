# Runbooks

## Incident Response

### CI pipeline failure on GitLab

1. Check pipeline status: GitLab > CI/CD > Pipelines
2. Identify failing stage (test / health-check / sync)
3. If `ruff check` fails: run `ruff check . --fix` locally, commit, push
4. If `pytest` fails: run `python -m pytest tests/ -x` locally to reproduce
5. If `check_boundary.py` fails: check for pollution files in protected paths
6. If `sync-to-github` fails: check GITHUB_TOKEN in CI/CD Variables
6.5. If `ci_health_check.sh` fails on "CI config integrity": check if `.gitlab-ci.yml` was accidentally emptied or corrupted
    - Verify: `git show gitlab/main:.gitlab-ci.yml | wc -l` (should be > 10)
    - Restore from last known good commit
7. Re-push to GitLab after fix; do NOT push directly to GitHub

### Release rollback

1. Identify the bad version tag (e.g., v0.5.1)
2. On GitLab: `git revert <commit-sha>` on main
3. Tag a patch release: update pyproject.toml, tag, push to GitLab
4. Verify CI sync restores GitHub mirror
5. If PyPI package is broken: `pip install` still works with `--no-deps` pinning

### Repository pollution

If business project files leak into memory-core repo:
1. Run `python scripts/check_boundary.py` to identify pollution
2. Remove the offending files
3. Run `python memory_core/tools/validate_memory_system.py`
4. Commit and push to GitLab

### Agent misbehavior

If Factory/Droid pushes directly to GitHub:
1. Revert the GitHub commit
2. Re-submit the change through GitLab MR flow
3. Check CONTRIBUTING.md "Violations" section for recovery steps

## Monitoring

- **CI health**: GitLab CI/CD > Pipelines dashboard
- **GitHub mirror sync**: GitHub Actions > ci workflow runs
- **PyPI package**: https://pypi.org/project/memory-core/
- **Release artifacts**: https://github.com/hdot123/memory/releases
- **CI self-check**: `scripts/ci_health_check.sh` validates CI config integrity (non-empty, valid YAML, required stages), memory system, and pollution detection

## Deployment Observability

After a release is published, verify:

| Check | Location |
|---|---|
| CI pipeline | GitLab > CI/CD > Pipelines (filter by tag) |
| GitHub sync | https://github.com/hdot123/memory/actions/workflows/ci.yml |
| Release published | https://github.com/hdot123/memory/releases |
| PyPI available | `pip install memory-core==X.Y.Z` |
| Downstream dispatch | Check dispatch targets for `memory_release_published` event |

## Alerting

- **CI failure**: GitLab sends email on pipeline failure
- **GitHub sync failure**: Check `sync-to-github` job logs in GitLab CI
- **Release workflow failure**: https://github.com/hdot123/memory/actions/workflows/release-and-dispatch.yml
