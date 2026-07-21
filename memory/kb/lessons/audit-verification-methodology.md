---
type: [KB:LESSON]
title: "代码审计核查的 5 个系统性盲区（v5 终版）"
shortname: AUDIT-VERIFICATION-METHODOLOGY
status: active
created: 2026-07-19
updated: 2026-07-19
source: local-canonical
confidence: high
tags: [lesson, audit, verification, ast, radon, vulture, methodology, ast-normalization, annotate-fields]
related: [D-003-audit-verification-refactor-basis, pretooluse-guard-coverage-gap]

---

# 代码审计核查的 5 个系统性盲区（v5 终版）

## Active Truth

代码审计核查（反查）的盲区有 5 类，**最严重的是第 5 类（AST 标准化方法错误）**。前 4 类是数据/范围层面的问题（可由多核交叉发现），第 5 类是**方法论层面的问题**（多核都用同样的错误方法时，三核交叉也无法发现，必须研究行业惯例）。

v5 终版结论：4 轮 10 次核查收敛，0 差异。27 D+ / 19 nested / 真死 44 / 真重复对 **10**（不是 v1-v4 报告的 39-66）。

## 4 个系统性盲区

### 盲区 1: 范围锚定偏差

**症状**：把"audit 重点 5 个 py"误解为"Top5 P0 所在文件"。

**后果**：Top5 第 4 名 `_discover_canonical_files`（CC=45 F 级）所在的 `memory_hook_integrity_manifest.py` **完全在前 30 轮反查范围外**。

**修正方法**：全仓 `radon cc -n D` 一次扫完，不要预先锁定文件范围。

### 盲区 2: 命令参数漂移

**症状**：audit 用 `radon cc -a -nb -s -j memory_core/ scripts/ memory/ workspace/`，反查时变体多（去 -a、去 -nb、缩路径），导致每次数字都对不上。

**后果**：漏掉的 5 个函数全在 `workspace/templates/analyze-for-review.py`。

**修正方法**：复制 audit 原命令原路径跑，不要自由发挥。

### 盲区 3: AST 扫描方法 bug

**症状**：用 `ast.iter_child_nodes(tree)` 只看直接子节点。

**后果**：漏 `if dry_run:` 块内、`for` 循环内、`with` 语句内的 `def`（共 8 个 nested function 被漏）。

**修正方法**：用 `ast.walk(tree)` 全树递归扫描。

### 盲区 4: 工具信任偏差

**症状**：信任 radon cc 报告所有函数。

**后果**：
- radon **不报告 nested function**（19 个完全没出现）
- vulture **不做"真死/误报"分类**（129 条中 85 条是误报（129 - 44 truly_dead = 85））
- AST dump 相似度对 **method vs function 有差异**（self 参数导致 AST 结构不同）
- 我之前说"184 函数"实际是 194（漏 10 个 nested）
- 我之前说"15 真重复对"实际是 v5 终版 10 对（v1-v4 的 39-66 是 annotate_fields=True 虚高）
- 我之前说"23 真死代码"实际是 v5 终版 44（漏 variable/attribute + GLM 独有 2 条 + DOMAIN/RESOURCE 判活）

**修正方法**：多工具交叉验证（radon + AST + vulture + grep），单工具结论不可信。

### 盲区 5: AST 相似度标准化方法错误（v5 揭示的最严重盲区）

**症状**：v1-v4 全部用 `ast.dump(annotate_fields=True)` 计算相似度
**后果**：
- Python 官方文档明确 annotate_fields=True 是调试格式（"makes the code impossible to evaluate"）
- 字段名字符串（`name=`, `args=`, `id=`, `ctx=` 等）在所有 AST 节点都出现
- SequenceMatcher 把重复字段名当成"相似内容"，**任何两个 AST 都会得高分**
- 47/47 pair 全部通过 ≥0.80 阈值，**无判别力**
- v5 切换到 `annotate_fields=False` + minimum-size 过滤后：47 candidate → **10 真 duplicate**（-80%）

**行业惯例**（v5 研究确认）：
- PMD CPD：token-based Rabin-Karp，min 100 tokens
- SonarQube：token-based，min 10 lines / 100 tokens
- jscpd：token-based，min 50 tokens
- 学术 Type-3 clone：0.5-0.8 阈值
- **没有任何主流工具用 annotate_fields=True**

**修正方法**：用 `ast.dump(annotate_fields=False)`（M1 唯一标准）+ minimum-size 过滤（≥10 行 OR ≥50 tokens）+ 接口镜像（同名不同实现）按 spec 不算 duplicate

## 元教训

1. **反查的盲区来自范围假设而非数据本身**：前 30 轮都在确认细节，从没质疑范围本身
2. **双核交叉验证是发现遗漏的唯一可靠方法**：bailian 和 kimi 独立扫描，互相印证，互相纠错
3. **三核可仲裁双核分歧**：kimi 和 bailian 在真重复对数上有分歧（39 vs 65），GLM 独立扫得 66 才确认 kimi 准确
4. **数字"看起来对"不等于"完整"**：27 D+ 数字 100% 准确，但 audit 漏报 95% 的重复代码
5. **subagent 也会出错**：kimi 第一轮用了错误阈值（F≥50 而非 F≥41），GLM 第一版脚本 bug 得 95 对虚高。subagent 结论也需 orchestrator 把关

## 工具盲区速查表

| 工具 | 盲区 | 影响 | 交叉验证方法 |
|------|------|------|-------------|
| radon cc | 不报告 nested function | 漏 19 个函数（全 B 级以下，不影响 D+） | ast.walk 全树扫描 |
| radon cc | comprehension if 计数 | CC 值比手算高 1-5 | mccabe 库或手算 decision points |
| vulture | 不做真死/误报分类 | 129 条中 85 条是误报（129 - 44 truly_dead = 85） | grep 全仓引用数 |
| AST dump 相似度 | method vs function 差异 | `_classify_truth_ref` AST=0.57 但文本=0.87 | 双算法（AST + 文本）对比 |
| grep -w | 边界情况 | 标准库同名符号干扰 | 加路径过滤 |
| ast.iter_child_nodes | 不递归 | 漏 if/for/with 块内 def | 改用 ast.walk |
| radon 阈值 | 网络文档误传 F≥50 | 实际 F≥41（直读源码 cc_rank） | 实验验证 + 源码核查 |

## Verification Refs

- 详细核查数据：`memory/docs/audit/audit-verification/`（7 个文件，25 次核查完整记录）
- 决策记录：`memory/kb/decisions/D-003-audit-verification-refactor-basis.md`
