# D-003: 基于三核交叉核查的重构决策基线

> Status: accepted (v5 终版，0 差异)
> Date: 2026-07-19
> Source: 代码质量审计核查（4 轮 10 次核查：bailian + kimi + GLM 三核 + 15 次深度核查 + 统一 spec 收敛）

## 决策

重构蓝图基于 **v5 终版数据基线**（统一 canonical spec 严格判定，0 差异）。

## v5 终版核心数字

| 数据项 | v5 终版值 |
|--------|----------|
| 27 D+ 函数 | 27 (D=14/E=8/F=5) |
| Top 5 CC | 118/54/51/45/43 |
| 19 nested | 19（全 CC≤11） |
| **真死代码** | **44**（function 20 + method 3 + class 4 + attribute 5 + variable 12） |
| **真重复对** | **10**（Cluster A=5, B=1, C=3, D=0, E=0, F=1） |
| P0-4 引用 | 13（audit 30 虚高 2.3 倍）|

## v5 关键方法论（不可协商）

### AST 相似度标准化
- **唯一标准**：`ast.dump(annotate_fields=False)` + `difflib.SequenceMatcher.ratio()`
- **禁用**：`annotate_fields=True`（Python 调试格式，非相似度方法）
- **阈值**：≥0.80（严格，无容差）
- **Minimum-size 过滤**：≥10 行 OR ≥50 tokens（SonarQube/jscpd 行业惯例）

### 死代码判定
- 生产代码无实际使用（import/注释/docstring 不算）
- 测试代码无实际使用（import-only 不算）
- 删除后无测试失败

## v1-v4 演进历史（参考，不用于重构决策）

| 阶段 | 真重复对 | 真死代码 | 方法论缺陷 |
|------|---------|---------|----------|
| v1 | 3 | 23 | 仅 function/method/class |
| v2 | 39-66 | 44 | 用 annotate_fields=True（虚高）|
| v3 | 65-66 | 44 | 同上 |
| v4 | 47 candidate | 44 | 同上 |
| **v5** | **10** | **44** | 统一 spec 收敛，0 差异 |

## audit 报告评估

### audit 报告准确项（10/10 核心数字 100% 准确）
- CC 分布 B=165 / C=77 / D=14 / E=8 / F=5 = 27 D+ 函数
- Top 5 P0 CC 值：118 / 54 / 51 / 45 / 43（严格降序）
- MI<50 文件数：31
- 死代码 vulture 条目：129
- Lint violations：0 / deptry violations：0
- 健康度评分：35/100（算法自洽）

### audit 报告失准项（v5 终版）
| 项目 | audit 声称 | v5 终版 | 严重程度 |
|------|-----------|---------|---------|
| 重复代码对识别 | 3 对 | **10 对** | 漏报 70%（v1-v4 的 39-66 是 annotate_fields=True 虚高）|
| 死代码真死分类 | 129 条（未分类）| **44 真死** | 129 中 85 条是 vulture 误报 |
| P0-4 测试引用数 | 30 次 | **13 次** | 虚高 2.3 倍 |
| P2/P3 问题清单 | 5+5=10 个 | 实际候选 110-140 个 | 抽样率仅 5-10% |

## 关键修正项（v5 vs audit 原报告）

### 修正 1: Cluster A v5 终版 5 个 method

`GatewayBusinessPolicyImpl`（memory_hook_impls.py:718-841）复制粘贴了 `ScopeResolver`（business_policy_checks.py:638-722）的 12 个 method，但只有 5 个通过 v5 spec 的 minimum-size 过滤：

- `__init__` (11 行/92 tokens)
- `determine_project_scope` (8 行/67 tokens)
- `get_project_canonical` (5 行/66 tokens)
- `get_project_runtime_root` (5 行/66 tokens)
- `_load_scope_overrides` (22 行/201 tokens)

被剔除的 7 个 trivial method（1-2 行/stub）不算 duplicate。

**重构收益**：抽取 `ScopeResolverBase` 基类。预计减 75 LOC。

### 修正 2: `_extract_session_info` (CC=35) 是 D+ 函数同时是死代码

`session_end_logger.py:289` 经核查确认零调用。**立即删除可让 27 D+ 降到 26 D+**。

### 修正 3: 真死代码 v5 终版 44 个

- function: 20（v5 加 `_sample`）
- method: 3
- class: 4
- attribute: 5（v5 加 `_section`）
- variable: 12（v5 删 DOMAIN/RESOURCE 判活）

**DOMAIN/RESOURCE v5 判活**：`tests/test_ownership_model.py:56` 通过 `OwnershipKind.DOMAIN != OwnershipKind.RESOURCE` 实际属性访问，删除会导致 AttributeError 测试失败。按统一 spec 判活。

### 修正 4: 6 个真重复 Cluster（v5 终版）

- **Cluster A**: GatewayBusinessPolicyImpl ↔ ScopeResolver（**5** method，全 1.0）
- **Cluster B**: gateway ↔ TruthBasisResolver（**1** method：`_truth_basis_errors_for`，M1=0.9341）
- **Cluster C**: business_policy_checks 内部 5 Validator（**3** 对 evaluate，M1=0.92-0.93）
- **Cluster D**: memory_hook_impls Delegate 类（**0** 对，全被 size 过滤剔除）
- **Cluster E**: PolicyRegistry ↔ GatewayBusinessPolicy（**0** 对，全 abstract method declaration）
- **Cluster F**: 独立跨文件（**1** 对：`_sha256_file`，M1=0.8573）

## 约束

所有 v5 数字都经过：
- bailian + kimi + GLM 三方独立交叉验证
- 5 次反向/正向/横向核查
- AST 标准化方法学深度研究（行业惯例 + Python 官方文档）
- 统一 canonical spec 严格应用（0 差异）

## 关联

- 详细核查数据：`memory/docs/audit/audit-verification/`（7 个文件，v5 终版）
- 方法论教训（含 AST 标准化盲区）：`memory/kb/lessons/audit-verification-methodology.md`
- AST 标准化陷阱（v5 揭示的最严重盲区）：`memory/docs/audit/audit-verification/05-METHODOLOGY-LESSONS.md` 第 5 盲区
- 原始 audit 报告（已清理）：worker transcript 在 mission `e688ce4d-286b-48e7-80ef-9c16b9017aa8`
