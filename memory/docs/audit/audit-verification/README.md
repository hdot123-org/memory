# 核查文件索引

**核查日期**：2026-07-19
**核查对象**：代码质量审计报告（已被清理，原始内容从 worker transcript 提取）
**核查方法**：**4 轮 10 次核查收敛**（10 次元验证 + 10 次双核交叉 + 5 次 GLM 三核仲裁 + 15 次深度核查 + 统一 spec 收敛）
**v5 终版状态**：**0 差异**，所有 borderline 已用统一 canonical spec 严格判定
**三核 subagent**：bailian-worker + kimi-worker + glm52-worker

---

## 文件清单

| # | 文件 | 内容 | 大小 |
|---|------|------|------|
| 00 | `00-EXECUTIVE-SUMMARY.md` | 执行摘要 + 40 次核查完整记录 + 三核仲裁 + v5 终版数据基线 | ~25KB |
| 01 | `01-D-PLUS-FUNCTIONS.json` | 27 个 D+ 函数完整清单（含死活、重复标记） | ~6KB |
| 02 | `02-DUPLICATE-PAIRS.json` | v5 终版 10 对真重复代码（按 6 个 cluster 分组，统一 spec） | ~9KB |
| 03 | `03-DEAD-CODE.json` | v5 终版 44 个真死代码（function 20 + method 3 + class 4 + attribute 5 + variable 12） | ~8KB |
| 04 | `04-NESTED-FUNCTIONS.json` | 19 个 nested function 完整清单（radon 漏报） | ~4KB |
| 05 | `05-METHODOLOGY-LESSONS.md` | 方法论反思 + 5 个系统性盲区 + 工具盲区速查表 + AST 标准化陷阱 | ~6KB |

---

## v5 终版核心结论（0 差异）

### v5 终版数字（权威）

| 数据项 | v5 值 | v1-v4 演进 |
|--------|-------|-----------|
| 27 D+ 函数 | 27 (D=14/E=8/F=5) | 始终稳定 |
| **真重复对** | **10**（Cluster A=5, B=1, C=3, D=0, E=0, F=1） | v1: 3 → v2-v4: 39-66（虚高）→ v5: 10 |
| **真死代码** | **44**（function 20 + method 3 + class 4 + attribute 5 + variable 12） | v1: 23 → v2: 44 → v5: 44（组成变） |
| 19 nested | 19 | 始终稳定 |

### v5 关键方法论修正

**AST 标准化陷阱**（v1-v4 都踩了）：`ast.dump(annotate_fields=True)` 是 Python 调试格式，非相似度方法。
- Python 官方文档：annotate_fields=True "makes the code impossible to evaluate"
- 行业工具（PMD CPD / SonarQube / jscpd）全部用 token-based 或 `annotate_fields=False`
- v5 统一切换到 `annotate_fields=False` + minimum-size 过滤（≥10 行 OR ≥50 tokens）→ 47 candidate → 10 真 duplicate（-80%）

### 三核仲裁历史结论（已被 v5 spec 取代）

| 核查项 | bailian | kimi | GLM | 三核共识 | **v5 终版** |
|--------|---------|------|-----|---------|----------|
| D+ 分布 | 14/8/5 ✅ | 21/3/3 ❌ | 14/8/5 ✅ | **14/8/5**（bailian+GLM） | 14/8/5 ✅ |
| 真重复对（raw） | 39 ❌ | 65 ✅ | 66 ✅ | **65-66**（kimi+GLM） | **10**（统一 spec）|
| 真死代码 | 43 | 42 ✅ | 42 ✅ | **42**（kimi+GLM） | **44**（DOMAIN/RESOURCE 移活 + _sample/_section 补漏）|
| P0-4 引用 | 12 | 13-19 ✅ | 13 ✅ | **13**（kimi+GLM） | 13 ✅ |
| scripts/ vulture | - | 7 ✅ | 7 ✅ | **7**（kimi+GLM） | 7 ✅ |

### GLM 独有发现（双核未识别）
1. **Cluster A 实际 12 method**（不是之前说的 13）—— `_read_text_if_exists` 是跨类误配（实际属 `ProjectMapValidator`，非 `ScopeResolver`），源代码核查确认
2. **Cluster B 实际 4 对**（漏了 `_lower_evidence_ref`，AST 0.849）
3. **新增真死 variable 2 条**：
   - `FORBIDDEN_OVERWRITE_PATTERNS`（apply_residue_plan.py:60）—— 3 grep 命中全是定义+注释
   - `observability.metrics`（observability.py:288）—— 17 grep 命中全是误报（文件名/类名/函数名）
   - 源代码核查：`observability.py:288 metrics` 和 `:289 error_tracker` **都是真死**（相邻两行的不同变量）
4. **radon 阈值源码级证据**：F≥41（GLM 直读源码证实）

---

## 核查结论速览

### audit 报告准确项（10/10 核心数字）
CC 分布、Top 5 P0、MI<50、死代码 129 条、Lint 0、Deps 0、健康度 35/100、8 维度结构、25 问题清单、4 重构机会——**核心原始数据 100% 准确**。

### audit 报告问题项（v5 终版）
1. **重复代码识别不足**：3 对 vs v5 终版 10 对（漏报 70%；v1-v4 的 39-66 对是 annotate_fields=True 虚高）
2. **死代码未做真死/误报分类**：129 条中只有 v5 终版 44 条是真死
3. **P2/P3 抽样率仅 5-10%**：5+5 个 vs 实际候选 110-140 个
4. **P0-4 测试引用数虚高 2.3 倍**：30 次 vs 实际 13 次（三核一致）
5. **4 个重构机会偏保守**：实际有 5-7 个三重命中文件

### 时间漂移（3 项，非 audit 错误）
mypy 198→200、gateway LLOC 1148→1154、MI mid/high 微调——全部源于 audit 后的 PR #159。

---

## 使用建议

### 用于重构决策
直接参考 `01-D-PLUS-FUNCTIONS.json`、`02-DUPLICATE-PAIRS.json` (v5)、`03-DEAD-CODE.json` (v5) 的修正版数据。**不要直接使用 audit 报告的重复代码/死代码清单**。

### v5 数据基线 vs v1-v4
- v5 用统一 spec：`annotate_fields=False` + minimum-size 过滤（≥10 行 OR ≥50 tokens）+ 显式死代码决策树
- v1-v4 用混合方法（含 annotate_fields=True 调试格式）→ 系统性虚高重复对数

### 用于质量评估
audit 报告的 CC 分布、Top 5 P0、MI<50、健康度评分仍然准确，可作为代码质量基准。

### 用于未来审计
参考 `05-METHODOLOGY-LESSONS.md` 的工具盲区速查表，避免重复踩坑。
