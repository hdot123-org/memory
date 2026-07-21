# v5 终版数据一致性核查报告

**日期**：2026-07-19
**核查人**：Droid orchestrator (data consistency audit)
**核查方法**：交叉验证 7 个 v5 文件之间的数字自洽性 + 文档叙述与 JSON 数据一致性

## 总览

- **总核查项**：25
- **PASS**：20
- **FAIL**：5（全部为同一类数学错误：false_positive count）
- **结论**：v5 数据基线**几乎完全一致**，但发现 1 类系统性数学错误（`false_positive_count = 129-44` 应为 85，实际有 3 处写 83、2 处写 86）。已在本核查中修复。

---

## 详细核查

### A. Duplicate 数字一致性（8/8 PASS）

- **A1 PASS** — `02-DUPLICATE-PAIRS.json` 的 `v5_total_summary.total_duplicate_pairs` = 10
- **A2 PASS** — `by_cluster` = {A:5, B:1, C:3, D:0, E:0, F:1}
- **A3 PASS** — 各 cluster `v5_method_count` 累加 = 5+1+3+0+0+1 = 10
- **A4 PASS** — `00-EXECUTIVE-SUMMARY.md` 重复对总数 = 10
- **A5 PASS** — `00-EXECUTIVE-SUMMARY.md` 各 cluster method 数与 02 JSON 一致
- **A6 PASS** — `README.md` 重复对总数 = 10
- **A7 PASS** — `D-003` 重复对总数 = 10
- **A8 PASS** — v1-v4 残留旧值（39/65/66/47）均明确标注为"虚高"或"演进历史"，无作为当前权威值使用

### B. Dead Code 数字一致性（9/9 PASS）

- **B1 PASS** — `03-DEAD-CODE.json` 的 `truly_dead_code_summary.total_truly_dead` = 44
- **B2 PASS** — `by_type` = {function:20, method:3, class:4, attribute:5, variable:12}
- **B3 PASS** — 各 detail 数组实际元素数与 by_type 一致（functions=20, methods=3, classes=4, attributes=5, variables=12）
- **B4 PASS** — `00-EXECUTIVE-SUMMARY.md` 死代码总数 = 44
- **B5 PASS** — `00-EXECUTIVE-SUMMARY.md` by_type 与 03 JSON 一致
- **B6 PASS** — `README.md` 死代码总数 = 44
- **B7 PASS** — `D-003` 死代码总数 = 44
- **B8 PASS** — `03-DEAD-CODE.json` 含 `_sample`（scripts/profiling_helper.py:115）+ `_section`（scripts/profiling_helper.py:98）
- **B9 PASS** — `03-DEAD-CODE.json` 含 `v5_removed_alive_symbols` 字段且包含 DOMAIN + RESOURCE

### C. 方法论一致性（5/5 PASS）

- **C1 PASS** — `02-DUPLICATE-PAIRS.json` 的 `scan_metadata.method` 声明 `annotate_fields=False`
- **C2 PASS** — `02-DUPLICATE-PAIRS.json` 的 `excluded_normalization_methods` 解释了为何排除 `annotate_fields=True`
- **C3 PASS** — `05-METHODOLOGY-LESSONS.md` 含第 5 盲区（AST 标准化方法错误）
- **C4 PASS** — `audit-verification-methodology.md` 含盲区 5（同上）
- **C5 PASS** — 所有文件中 `annotate_fields=True` 仅作为"禁用方法"提及，无作为当前推荐

### D. 其他一致性（3/3 PASS）

- **D1 PASS** — 27 D+ 函数（00/README/D-003 全部一致）
- **D2 PASS** — 19 nested function（00/README/D-003 全部一致）
- **D3 PASS** — P0-4 引用 13（00/README/D-003 全部一致）

---

## E. 发现的不一致（5 FAIL，同一类数学错误）

**false_positive_count 数学错误**：129 - 44 = **85**（正确值）

| 文件 | 行号 | 当前值 | 正确值 | 状态 |
|------|------|--------|--------|------|
| `03-DEAD-CODE.json` | 22 | `false_positive_count: 83` | 85 | FAIL |
| `03-DEAD-CODE.json` | 23 | `"64.3% (83 of 129...)"` | `"65.9% (85 of 129...)"` | FAIL |
| `03-DEAD-CODE.json` | 115 | `"...83 of 129 entries..."` | `"...85 of 129 entries..."` | FAIL |
| `audit-verification-methodology.md` | 55 | `"129 条中 86 条是误报"` | `"129 条中 85 条是误报"` | FAIL |
| `audit-verification-methodology.md` | 96 | `"129 条中 86 条是误报"` | `"129 条中 85 条是误报"` | FAIL |

**正确的文件**（4 处）：
- `05-METHODOLOGY-LESSONS.md:83` — "85 条是误报" ✅
- `05-METHODOLOGY-LESSONS.md:104` — "85 条是误报" ✅
- `D-003:59` — "129 中 85 条是 vulture 误报" ✅
- `00-EXECUTIVE-SUMMARY.md`（未直接提及 false_positive count）✅

**百分比计算验证**：
- 83/129 = 64.3%（JSON 中错误值对应的错误百分比）
- **85/129 = 65.9%（正确百分比）**
- 86/129 = 66.7%

---

## F. 修复操作

本次核查中已修复全部 5 处错误（纯数学错误，无歧义）：

1. `03-DEAD-CODE.json:22` — `false_positive_count: 83` → `85`
2. `03-DEAD-CODE.json:23` — `"64.3% (83 of 129...)"` → `"65.9% (85 of 129...)"`
3. `03-DEAD-CODE.json:115` — `"...83 of 129 entries..."` → `"...85 of 129 entries..."`
4. `audit-verification-methodology.md:55` — `"86 条是误报"` → `"85 条是误报"`
5. `audit-verification-methodology.md:96` — 同上

---

## G. 修复后状态

修复后 v5 终版**全部 25 项核查通过，0 不一致**。所有文件中 `false_positive_count` 统一为 **85**，百分比统一为 **65.9%**。

## H. 核查元教训

这个错误揭示了一个新盲区：**多个 subagent 独立扫描时，如果都从 vulture 的 129 条出发做减法，容易在"真死 - 总数 = 误报"的算术上出错**（v4 阶段死代码数字多次摇摆，可能影响了 false_positive 的计算）。修复方法：所有 false_positive count 必须显式标注 `129 - truly_dead = false_positive` 的计算式，避免直接写一个"看起来对"的数字。
