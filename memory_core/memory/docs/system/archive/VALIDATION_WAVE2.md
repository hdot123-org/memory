# Wave 2 Cross-Validation Report

**Date:** 2026-04-26
**Branch:** `codex/v0.2.0-version-bump` (task branch — `codex/api-refactor-batch` not found)
**Validator:** codex (cross-validation agent)
**Pre-wait:** 120 seconds elapsed before validation began

---

## 1. `workspace/tools/memory_hook_config.py` (Wave 1)

| Check | Status | Detail |
|---|---|---|
| 37 fields match core signature | ✅ PASS | 7 (Environment) + 7 (Paths) + 9 (Policy) + 14 (Callbacks) = 37 fields. All parameter names match `build_context_package_core()` kwargs. |
| `from_gateway_kwargs()` works | ✅ PASS | Accepts all 37 kwargs with correct types and defaults (`governance_blocker_scopes`, `event_contract_blocker_scopes`, `core_evidence_refs` default to `None`). Returns a `CoreConfig` instance. |
| `to_gateway_kwargs()` works | ✅ PASS | Uses `dataclasses.asdict(self)` — returns all 37 fields as a dict suitable for `**kwargs` unpacking. |
| `__post_init__` validation | ✅ PASS | Validates `host` ∈ {"codex", "claude"}, `event` is non-empty string, `workspace_root` and `repo_root` are `Path` instances. |

## 2. `workspace/tools/memory_hook_impls.py` (Wave 1)

| Check | Status | Detail |
|---|---|---|
| `ArtifactWriter` defined | ✅ PASS | Class defined at ~line 950. Wraps `ArtifactSinkImpl` with filename generation and non-blocking error handling. |
| `DelegateRouter` defined | ✅ PASS | Class defined at ~line 1000. Routes to `CodexDelegate` / `ClaudeDelegate` by host name, provides `noop` fallback. |
| Reuse existing classes | ✅ PASS | `ArtifactWriter` internally instantiates `ArtifactSinkImpl`; `DelegateRouter` stores and dispatches to `CodexDelegate` / `ClaudeDelegate`. No duplicated logic. |

## 3. `workspace/tools/memory_hook_core.py` (Wave 1 fix)

| Check | Status | Detail |
|---|---|---|
| `build_context_package_from_config(config)` exists | ✅ PASS | Function defined at bottom of module (~line 320). |
| Identical behavior to old function | ✅ PASS | Unpacks all 37 fields from `CoreConfig` and passes them as kwargs to `build_context_package_core()`. Parameter-by-parameter mapping is correct — no missing or extra fields. |

## 4. `workspace/tools/memory_hook_gateway.py` (Waves 1+2)

| Check | Status | Detail |
|---|---|---|
| `CoreConfig` construction correct | ✅ PASS | `build_context_package()` constructs `CoreConfig` with all 37 fields populated from adapter policy, environment, and gateway constants. |
| `build_context_package_from_config` used | ⚠️ PARTIAL | `build_context_package_from_config` is imported but **not called** in the primary path. The gateway uses `config.to_gateway_kwargs()` → `provider_builder(**kwargs)` instead of `build_context_package_from_config(config)`. The shadow-run path also calls `build_context_package_from_config(config)` directly — but this is a **bug** (see Findings section). |
| `build_context_package_simple` defined | ✅ PASS | Defined at ~line 833. Takes `(host, event, payload)` with optional `adapter`. Delegates to `build_context_package()`. |
| `__all__` export list present | ✅ PASS | `__all__ = ['build_context_package', 'build_context_package_simple']` at ~line 96. |

## 5. `pyproject.toml`

| Check | Status | Detail |
|---|---|---|
| Version bumped to 0.2.0 | ✅ PASS | `version = "0.2.0"` confirmed. |

## 6. `workspace/tools/validate_memory_system.py`

| Check | Status | Detail |
|---|---|---|
| `core_config_path` check added | ⚠️ FAIL (runtime bug) | `check_core_config_path()` is defined **after** `if __name__ == "__main__": raise SystemExit(main())`. The function is called from `main()` (line 207) but not yet defined at module-load time. Causes `NameError: name 'check_core_config_path' is not defined` at runtime. The function body itself is correct — it just needs to be moved before `main()`. |

## 7. Test Results

| Test File | Total | Passed | Failed | Status |
|---|---|---|---|---|
| `tests/test_refactoring.py` | 17 | 17 | 0 | ✅ All pass |
| `tests/test_core_config_path.py` | 11 | 11 | 0 | ✅ All pass |
| `tests/test_validate_memory_system.py` | 3 | 0 | 3 | ❌ All fail |
| `tests/test_memory_hook_gateway_m6_batch3_provider_switch.py` | 1 | 0 | 1 | ❌ Fail |

**Overall: 155 passed, 4 failed out of 159 tests.**

### Failed test details:

1. **`test_build_context_package_records_provider_and_shadow_run`** — The shadow-run code in `build_context_package()` calls `build_context_package_from_config(config)` instead of `shadow_builder(config)`. The test mocks `_resolve_core_builder` to return an `external_builder` that produces `status="degraded"`, but the actual shadow path re-runs the config-based builder (which returns `status="ok"`). **This is a genuine bug in the gateway.**

2. **`test_validate_returns_zero_on_healthy_system`** — `NameError` as described in item 6 above.

3. **`test_validate_prints_summary`** — Same root cause: validator crashes before printing.

4. **`test_validate_reports_all_checks_passed`** — Same root cause.

---

## Script Execution Results

| Script | Exit Code | Result |
|---|---|---|
| `python3 -m pytest -q tests` | 1 | 4 failures (see above) |
| `python3 workspace/tools/validate_memory_system.py` | 1 | `NameError: check_core_config_path not defined` |
| `python3 workspace/tools/memory_hook_provider_rollback.py` | 0 | ✅ Passed — both external-core and legacy probes OK |

---

## Summary

| Area | Verdict |
|---|---|
| CoreConfig dataclass | ✅ Healthy — 37 fields, factory, validation all correct |
| ArtifactWriter / DelegateRouter | ✅ Healthy — properly reuse existing classes |
| build_context_package_from_config | ✅ Healthy — identical behavior to kwargs path |
| Gateway CoreConfig construction | ✅ Healthy — all fields wired correctly |
| Gateway `__all__` / build_context_package_simple | ✅ Healthy |
| pyproject.toml version 0.2.0 | ✅ Healthy |
| validate_memory_system.py | ❌ Bug — function ordering causes NameError |
| Gateway shadow_run path | ❌ Bug — calls wrong builder function |
| Test suite | ⚠️ 155/159 pass — 4 failures from 2 bugs above |

## Required Fixes Before Merge

1. **`validate_memory_system.py`**: Move `check_core_config_path()` function definition before `main()` (or at least before the `if __name__` block).
2. **`memory_hook_gateway.py` shadow_run**: Change `shadow_package = build_context_package_from_config(config)` to `shadow_package = shadow_builder(**config.to_gateway_kwargs())` so the shadow actually uses the alternate provider.
3. **`memory_hook_gateway.py` primary path**: Consider using `build_context_package_from_config(config)` instead of `provider_builder(**config.to_gateway_kwargs())` for consistency with the refactoring intent.
