# Code Quality Metrics (v0.9.0)

This page documents the code quality metrics tracked by the memory-core
project, the tools that produce them, and how to access the results.

## Tracked Metrics

### Coverage

- **What:** Percentage of source lines / branches exercised by the test
  suite, measured by `pytest --cov=memory_core`.
- **Target:** a coverage floor of **15%** is enforced via
  `--cov-fail-under=15` in `pyproject.toml`. The long-term goal is to
  raise the floor incrementally as more tests are added.
- **Current:** ~16% (see the latest CI run / Codecov badge).
- **Where to view:**
  - Pull-request coverage diff on GitHub.
  - Project dashboard on **Codecov** at
    `https://app.codecov.io/gh/hdot123/memory` (requires read access).

### Duplicate Code

- **What:** Percentage of duplicated code (clones) across the package,
  measured by `pylint --disable=all --enable=R0801 memory_core/`.
- **Target:** below 10% duplicated lines; clones longer than 10 lines
  are flagged for refactoring.
- **Where to view:** run locally (`pylint ...`) or check the
  `advisory-telemetry-audit` / health-check CI output which surfaces
  high-confidence duplicates.

### Type Errors

- **What:** Count of `mypy --strict` errors against `memory_core/`.
- **Baseline (v0.9.0):** 220 errors across 36/63 files.
- **Target:** strict-mode errors trend to zero over successive releases;
  fixed modules are opted into strict mode via
  `[[tool.mypy.overrides]]` in `pyproject.toml`.
- **Where to view:**
  - Locally: `python -m mypy --strict memory_core/`.
  - CI: the `advisory-typing` job in `.github/workflows/ci.yml`
    (non-blocking / advisory until the baseline drops further).

### Cyclomatic Complexity

- **What:** Per-function cyclomatic complexity, measured by ruff's
  `C901` rule.
- **Threshold:** `max-complexity = 20` in `ruff.toml`; functions above
  this are flagged and must be refactored before merge.
- **Where to view:** `ruff check . --select C901` locally, or the
  lint step in CI.

## Accessing Metrics

| Metric            | Local command                                              | CI / online                                  |
|-------------------|------------------------------------------------------------|----------------------------------------------|
| Coverage          | `pytest --cov=memory_core --cov-report=term-missing`       | **Codecov** dashboard, PR diff               |
| Duplicate code    | `pylint --disable=all --enable=R0801 memory_core/`         | CI advisory jobs / health check              |
| Type errors       | `python -m mypy --strict memory_core/`                     | `advisory-typing` CI job (advisory)          |
| Complexity        | `ruff check . --select C901`                               | `ruff` lint step in CI (blocking)            |
| Dead code         | `vulture memory_core/ --min-confidence 80`                 | pre-commit hook (local)                      |
| Dependency usage  | `deptry .`                                                 | `deptry` step in CI (blocking)               |

### Codecov

Coverage reports are uploaded from CI via `codecov-action`. The project
dashboard lives at:

    https://app.codecov.io/gh/hdot123/memory

Use the dashboard to inspect per-file coverage, diff coverage on PRs,
and historical trends. The `CODECOV_TOKEN` secret is configured on the
repository; no token is needed to view public reports.

### pylint

`pylint` is used primarily for duplicate-code detection (`R0801`). To
run it locally with the same focus:

    pylint --disable=all --enable=R0801 memory_core/

For a broader lint pass (informational only; ruff remains the primary
linter):

    pylint memory_core/

## Adding a New Metric

When proposing a new metric:

1. Add the definition to this page (what, target, where).
2. Wire the tool into CI (preferably as advisory first).
3. Update `docs/typing-tech-debt.md` or equivalent if it produces a
   debt backlog.
4. Reference the metric in PR templates so reviewers see the delta.

## References

- `pyproject.toml` - pytest, mypy, deptry configuration.
- `ruff.toml` - ruff rule selection and complexity threshold.
- `.github/workflows/ci.yml` - CI pipeline definition.
- `.pre-commit-config.yaml` - local pre-commit hooks.
- `docs/typing-tech-debt.md` - mypy strict migration backlog.
