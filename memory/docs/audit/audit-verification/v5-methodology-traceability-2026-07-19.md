# v5 终版方法论可追溯性核查报告

**日期**：2026-07-19
**核查人**：explorer subagent (methodology traceability) + Droid orchestrator 落盘
**核查方法**：抽样验证 v5 终版的判定**真的**符合统一 canonical spec

## 总览

- **抽样核查项**：17 项（E: 5, F: 2, G: 5 主项, H: 3）
- **PASS**：17 / 17
- **FAIL**：0
- **结论**：**v5 spec 被严格遵守**，所有抽样项均与统一 canonical spec 一致；`_sample` 的 "born dead" 声明经得起检验。

---

## E. Duplicate Cluster A 抽样（5 方法）

JSON 数据点：

| 方法 | m1 | body_lines | tokens | loc_a | loc_b |
|------|-----|-----------|--------|-------|-------|
| `__init__` | 1.0000 | 11 | 92 | impls.py:718 | checks.py:638 |
| `determine_project_scope` | 1.0000 | 8 | 67 | impls.py:764 | checks.py:681 |
| `get_project_canonical` | 1.0000 | 5 | 66 | impls.py:774 | checks.py:691 |
| `get_project_runtime_root` | 1.0000 | 5 | 66 | impls.py:781 | checks.py:698 |
| `_load_scope_overrides` | 1.0000 | 22 | 201 | impls.py:731 | checks.py:651 |

- **E1 PASS** — 所有 5 方法 m1_similarity = 1.0000 ≥ 0.80
- **E2 PASS** — 所有 5 方法 size 达标（OR 语义）：
  - `__init__` 11 行/92 tokens — 双达标
  - `determine_project_scope` 8 行但 67 tokens — tokens 达标
  - `get_project_canonical` 5 行但 66 tokens — tokens 达标
  - `get_project_runtime_root` 5 行但 66 tokens — tokens 达标
  - `_load_scope_overrides` 22 行/201 tokens — 双达标
- **E3 PASS** — 所有 5 方法 m1_similarity = 1.0000（真正的 copy-paste，spec 严格性的体现）
- **E4 PASS** — 主观比对源文件：
  - `__init__`：两个文件 byte-level 几乎完全相同，唯一差异是 `business_policy_checks.py` 第 648 行多一个 `# type: ignore[assignment]` 注释。AST 标准化后完全一致 → m1=1.0 合理。
  - `_load_scope_overrides`：两个文件 **完全 byte-identical**（22 行 body 一字不差）→ m1=1.0 合理。
- **E5 PASS** — LOC 与 JSON 声明一致：
  - `__init__` body 在 impls.py:719-729 共 11 行；checks.py:639-649 共 11 行
  - `_load_scope_overrides` body 在 impls.py:732-753 共 22 行；checks.py:652-673 共 22 行

## F. Cluster A 失败 size filter 抽样（7 方法）

- **F1 PASS** — 7/7 方法均声明了 lines 和 tokens：
  - `_resolve_override_path` lines=4, tokens=42
  - `get_global_canonical` lines=1, tokens=19
  - `get_required_canonical` lines=1, tokens=19
  - `project_map_refs` lines=1, tokens=25
  - `decision_refs_for_scope` lines=2, tokens=42
  - `lesson_refs_for_scope` lines=2, tokens=42
  - `docs_refs_for_scope` lines=2, tokens=34
- **F2 PASS** — 抽 2 个验证源码：
  - `get_global_canonical` 在 impls.py:780 单行 body：`return list(self._config.global_canonical)` → 1 行/19 tokens 与 JSON 一致
  - `_resolve_override_path` 在 impls.py:755 4 行 body → 4 行/42 tokens 与 JSON 一致

## G. 死代码抽样（5 项）

### G1-G3 `_matches_pattern` (apply_residue_plan.py:194)
- G1 PASS — 文件存在
- G2 PASS — line 194 找到定义 `def _matches_pattern(path: str, pattern: str) -> bool:`
- G3 PASS — 全仓 grep 仅有 1 处非定义命中 `tests/test_p2_migrations_log_flock.py:109: def test_log_line_matches_pattern(...)`，这是 **不同标识符**（test 方法名包含 `matches_pattern` 子串），非实际使用。**真死**

### G1-G3 `_safe_int` (memory_hook_metrics.py:38)
- G1 PASS — 文件存在
- G2 PASS — line 38 找到定义
- G3 PASS — 全仓 grep **仅命中定义本身**，无任何调用。**真死**

### G1-G3 `write_metrics` (memory_hook_metrics.py:94)
- G1 PASS — 文件存在
- G2 PASS — line 94 找到定义
- G3 PASS — 其他 grep 命中均为不同标识符或测试方法名（`_write_metrics_jsonl` 是不同函数；`test_write_metrics_failure_is_non_blocking` 方法名含子串但 body 实际调用 `metrics.emit_metrics`，**不调用 write_metrics**）。**真死**

### G1-G3 `_is_path_under` (ownership.py:325)
- G1 PASS — 文件存在
- G2 PASS — line 325 找到定义
- G3 PASS — 全仓 grep **仅命中定义本身**。**真死**

### G1-G4 `_sample` (scripts/profiling_helper.py:115) — v5 新增
- G1 PASS — 文件存在（位于 `/Users/busiji/memory/scripts/profiling_helper.py`，注意路径是仓库根的 scripts/，与 scan_scope `"memory_core/ + scripts/"` 一致）
- G2 PASS — line 115 找到定义 `def _sample() -> None:`
- G3 PASS — 全仓其他 `_sample` 命中均为不同标识符（`_sample_package`、`_sample_v1_package`、`_sample_v2_package`、`upstream_samples`、`downstream_samples`）
- **G4 PASS — "born dead in commit 709fe58" 声明经得起检验**：
  - `main()`（line 137 起）在 `with profile(args.section, ...)` 块内 **直接内联** 工作负载 `total = sum(range(100_000))`
  - `_sample()` body 也做 `sum(range(100_000))` 但使用 `profile("sample")` 而非 main 的 `profile(args.section)`，且其结果格式与 main 不同
  - 即 `_sample` 是一个独立的 demo/sample 函数，从未被 main 或任何代码路径调用 → **born dead 成立**

## H. v5 vs v4 变化抽样

- **H1 PASS** — `03-DEAD-CODE.json` scan_metadata 含字段 `v5_changes_from_v4`: `"DOMAIN/RESOURCE removed (alive per spec); _sample and _section added (previously missed)."`
- **H2 PASS** — DOMAIN/RESOURCE 确实判活：
  - `memory_core/ownership.py` 第 36-37 行确实定义 `DOMAIN = auto()` 和 `RESOURCE = auto()`
  - Grep 命中 `tests/test_ownership_model.py:56: assert OwnershipKind.DOMAIN != OwnershipKind.RESOURCE` — 这是 **实际属性访问**（既非 import-only，也非注释/docstring/异常字符串/类型注解）
  - 按 v5 spec condition 2（测试实际访问）+ condition 3（删除导致 AttributeError 测试失败）→ 判活正确
- **H3 PASS** — profiling_helper.py 第 98 行和第 115 行均存在目标符号且均未被使用：
  - line 98: `self._section = section`（write-only attribute，后续 `__init__` 使用局部参数 `section` 而非 `self._section`）
  - line 115: `def _sample() -> None:`（如 G4 所述，未被调用）
  - 全仓 `_section` grep 其他命中均为不同标识符（`_section_body`、`_truth_basis_sections_for` 等），无 `self._section` 的读访问

## 发现的偏离

**无**。所有 17 个抽样项均 PASS。

## 备注（非偏离，但值得记录）

1. **路径语义说明**：03-DEAD-CODE.json 中 `scripts/profiling_helper.py` 是相对于 **仓库根** 的路径，与 `scan_scope: "memory_core/ + scripts/"` 一致。最初尝试读 `/Users/busiji/memory/memory_core/scripts/profiling_helper.py` 失败，正确路径是 `/Users/busiji/memory/scripts/profiling_helper.py`。
2. **`# type: ignore` 注释差异**：Cluster A 的 `__init__` 在 `business_policy_checks.py` 比 `memory_hook_impls.py` 多一个类型忽略注释。这种差异在 `ast.dump(annotate_fields=False)` 下完全不可见（注释被 AST 丢弃），所以 m1=1.0 是正确的。

---

## 总结

v5 终版的方法论选型（`annotate_fields=False` + minimum-size 过滤 + 显式死代码决策树）在抽样核查中得到完整验证。spec 严格性（m1=1.0000 体现真 copy-paste，最小 size 阈值无 tolerance，死代码决策树无例外）得到实证。`_sample` 的 born-dead 声明、DOMAIN/RESOURCE 的判活理由均经得起源码核查。
