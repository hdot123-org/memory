# Runbooks

> **环境声明：以下事件响应流程基于 GitHub 为主仓库的开发环境。** 通用维护手册（版本同步、迁移、配置管理）见同目录其他文档。

## Incident Response

### CI pipeline failure on GitHub

1. Check pipeline status: GitHub > Actions > Workflows
2. Identify failing workflow run
3. If `ruff check` fails: run `ruff check . --fix` locally, commit, push
4. If `pytest` fails: run `python -m pytest tests/ -x` locally to reproduce
5. If `check_boundary.py` fails: check for pollution files in protected paths
6. If `ci_health_check.sh` fails on "CI config integrity": check if `.github/workflows/ci.yml` was accidentally emptied or corrupted
    - Verify: `git show origin/main:.github/workflows/ci.yml | wc -l` (should be > 10)
    - Restore from last known good commit
7. Re-push to GitHub after fix

### Release rollback

1. Identify the bad version tag (e.g., v0.5.1)
2. On GitHub: `git revert <commit-sha>` on main
3. Tag a patch release: update pyproject.toml, tag, push to GitHub
4. If PyPI package is broken: `pip install` still works with `--no-deps` pinning

### Repository pollution

If business project files leak into memory-core repo:
1. Run `python scripts/check_boundary.py` to identify pollution
2. Remove the offending files
3. Run `python memory_core/tools/validate_memory_system.py`
4. Commit and push to GitHub

### Agent misbehavior

If Factory/Droid pushes directly to main:
1. Revert the GitHub commit
2. Re-submit the change through feature branch + PR flow
3. Check CONTRIBUTING.md "Violations" section for recovery steps

## Monitoring

- **CI health**: GitHub Actions > Workflows dashboard
- **PyPI package**: https://pypi.org/project/memory-core/
- **Release artifacts**: https://github.com/hdot123/memory/releases
- **CI self-check**: `scripts/ci_health_check.sh` validates CI config integrity (non-empty, valid YAML, required stages), memory system, and pollution detection

## Deployment Observability

After a release is published, verify:

| Check | Location |
|---|---|
| CI pipeline | GitHub Actions > Workflows (filter by tag) |
| Release published | https://github.com/hdot123/memory/releases |
| PyPI available | `pip install memory-core==X.Y.Z` |
| Downstream dispatch | Check dispatch targets for `memory_release_published` event |

## Alerting

- **CI failure**: GitHub sends email on workflow failure
- **Release workflow failure**: https://github.com/hdot123/memory/actions/workflows/release-and-dispatch.yml
