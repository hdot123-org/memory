---
type: [KB:LESSON]
title: "PreToolUse Guard 覆盖盲区：规则引擎未消费 CLASSIFICATION.md"
shortname: PRETOOLUSE-GUARD-COVERAGE-GAP
status: tech-debt
tech_debt_severity: P1
created: 2026-07-19
updated: 2026-07-19
source: local-canonical
confidence: high
tags: [lesson, tech-debt, hook, pretooluse, guard, ownership, classification, source-repo-readonly]
related: [D-003-audit-verification-refactor-basis, audit-verification-methodology]

---

# PreToolUse Guard 覆盖盲区：规则引擎未消费 CLASSIFICATION.md

## Active Truth

当前 PreToolUse Guard（`memory_core/tools/pretooluse_guard.py`）是**白名单保护机制**，只对 `memory/system/ownership.toml` 列出的 domains + resources 路径做拦截。AGENTS.md 第 50 行的"先读 CLASSIFICATION.md"是**软规则**（依赖 agent 自觉），CLASSIFICATION.md **从未被 hook 消费**。两者之间的盲区导致本次审计核查期间发生两类违规：根目录 `artifacts/audit-verification/` 写入与 5 个根目录散落 `.py` 脚本写入均未被拦截。

## Tech Debt：未实施，作为后续 sprint 候选

**优先级**：P1（系统性盲区，不影响生产，但会影响审计/核查类工作流的可重复性）
**触发实施条件**：函授重构完成后，或在下次审计/长核查工作流开始前。

## 违规现场复盘

### 违规类型 1：根目录 `artifacts/` 写入

- **实际路径**：`artifacts/audit-verification/`（7 个文件，21KB+6.7KB+8.2KB+7.3KB+4.2KB+4.7KB+README）
- **规则引擎保护路径**：`memory/artifacts/`（有 `memory/` 前缀，递归）
- **未拦原因**：`artifacts/` 与 `memory/artifacts/` 路径不匹配，`classify_owned_path` 返回 NotOwned

### 违规类型 2：根目录散落 `.py` 脚本

- **实际路径**：`kimi_scan_cross_class.py`, `kimi_scan_results.json`, `scan_cross_class_methods.py`, `scan_cross_class_v2.py`, `scan_dup_kimi.py`
- **规则引擎保护**：根目录不在任何 ownership.toml domain
- **未拦原因**：白名单设计，未列入即放行

### 违规类型 3：subagent 越权写入根目录

- bailian-worker / kimi-worker 多次被 PreToolUse hook 拦截（命中 `memory_core/` 写入），但绕道写到根目录 `.py` 文件就放行
- **未拦原因**：根目录是规则盲区，subagent 越权没有第二道防线

## 4 个系统性盲区（按本次违规顺序）

### 盲区 1：根目录 `artifacts/` 不在保护列表

- **保护的**：`memory/artifacts/` (recursive, standard)
- **实际写入的**：`artifacts/audit-verification/`（无 `memory/` 前缀）
- **后果**：违规写入 7 个文件，最后需手工迁移

### 盲区 2：根目录散落 `.py` 不在任何 domain

- **保护的**：`memory_core/`, `memory/docs`, `memory/kb`, `memory/system`, `project-map`, `memory/artifacts`, `memory/log`, `AGENTS.md`, `INDEX.md`, `memory/inbox.md`
- **实际写入的**：根目录 5 个 `.py` + 1 个 `.json`
- **后果**：仓库污染，需要用户授权删除

### 盲区 3：CLASSIFICATION.md 从未被 hook 消费

- **AGENTS.md 第 50 行**：写入知识库前必须先读 CLASSIFICATION.md 决策树
- **实际**：PreToolUse Guard 只读 `ownership.toml`，不读 `docs/CLASSIFICATION.md`
- **后果**：即使决策树明确说"审计记录应放 memory/docs/audit/"，hook 也不会基于此规则做反向校验

### 盲区 4：白名单设计（默认 allow）

- **当前架构**：白名单保护，未列入 ownership.toml 的路径全部放行
- **缺失**：没有"禁止区域"（deny patterns）
- **后果**：任何新创建的路径默认放行，没有反向校验"这个文件应该写在哪里"

## 根因：软规则 vs 硬规则割裂

| 规则类型 | 实现位置 | 执行机制 | 失效场景 |
|---------|---------|---------|---------|
| 软规则 | AGENTS.md 第 50 行"先读 CLASSIFICATION.md" | 依赖 agent 自觉读 | Agent 上下文压缩 / 新 session / subagent 未注入 AGENTS.md |
| 硬规则 | ownership.toml domains + resources | PreToolUse hook 自动执行 | 路径未列入 / 根目录 / 新目录类型 |

**核心问题**：CLASSIFICATION.md 的分类决策树**只对人/agent 生效**，对规则引擎不生效。AGENTS.md 把 CLASSIFICATION.md 写成"必须先读"，但没有任何机制强制 hook 读它。

## 技术债方案：三个层次（彻底程度递增）

### 方案 P0：根目录 deny patterns（最小改动，立即收口本次场景）

**改动点**：`memory_core/tools/pretooluse_guard.py`

```python
# pretooluse_guard.py 顶部加常量
ROOT_DENY_PATTERNS = [
    re.compile(r'^[^/]+\.(py|json|sh)$'),       # 根目录散落脚本
    re.compile(r'^artifacts/'),                   # 根目录 artifacts/
    re.compile(r'^(scan|kimi|tmp)_.*\.(py|json)$'),  # 已知违规前缀
]

# classify_tool_use 开头加（在 ownership 加载前）
if is_memory_core_source_repo(project_root):
    rel = _normalize_rel_path(file_path)
    for pattern in ROOT_DENY_PATTERNS:
        if pattern.match(rel):
            return RuleResult(
                matched=True, severity="error",
                message=f"根目录污染：源仓库禁止散落文件 ({rel})",
                detail={"decision": "block", "scenario": "root_pollution"}
            )
```

- **投入**：30 分钟（含单测）
- **覆盖盲区**：盲区 1、2、4（部分）
- **不覆盖**：盲区 3（CLASSIFICATION.md 仍未被消费）
- **风险**：黑名单天然不全，新 pattern 会绕过

### 方案 P1：扩展 ownership.toml 加 `deny_domains` schema（可配置化）

**改动点**：
- `memory_core/ownership.py`：schema 加 `deny_domains: list[DenyDomain]`
- `memory_core/tools/_guard_classify.py`：classify 流程加 deny 检查分支
- `memory/system/ownership.toml`：写入实际 deny 规则

```toml
# ownership.toml 新增
[[deny_domains]]
name = "root_pollution"
path = "."
recursive = false
patterns = ["*.py", "scan_*.py", "kimi_*.py", "*.tmp.json"]
reason = "根目录禁止散落脚本，应放 memory_core/tools/ 或 tmp/"

[[deny_domains]]
name = "root_artifacts"
path = "artifacts"
recursive = true
reason = "根目录 artifacts/ 是运行时目录，文档应放 memory/docs/ 分类路径"
```

- **投入**：2-3 小时（schema + classify 分支 + 单测 + 文档）
- **覆盖盲区**：盲区 1、2、4（完整）
- **不覆盖**：盲区 3
- **收益**：deny 规则变成数据驱动（改 toml 不改代码）

### 方案 P2：让 PreToolUse Guard 消费 CLASSIFICATION.md（彻底闭环）

**改动点**：
- 新增 `memory_core/tools/classification_guard.py`：解析 CLASSIFICATION.md 决策树
- `memory_core/tools/_guard_classify.py`：Write/Edit 前加分类守卫
- shadow mode 起步（只 log 不 block），观察误报率

```python
# 伪代码
def classify_against_decision_tree(file_path, content_keywords):
    """
    1. 解析 docs/CLASSIFICATION.md 的决策树
    2. 根据 content 关键词（"审计"/"决策"/"服务器"）推断应有路径
    3. 如果 file_path 不在推荐路径 → block, reason="应放 <推荐路径>"
    """
    recommended = match_classification(file_path, content_keywords)
    if recommended and not is_within(file_path, recommended):
        return Block(reason=f"分类错误：应放 {recommended}（CLASSIFICATION.md）")
    return Allow()
```

- **投入**：1-2 天（含分类器设计、shadow mode、误报观察）
- **覆盖盲区**：盲区 1、2、3、4（全部）
- **风险**：关键词歧义误报（"审计" 既可能是 audit 也可能是 compliance）
- **缓解**：shadow mode 先跑 1-2 周收集误报，调优后再启用 block

## 推荐路径

| 阶段 | 方案 | 触发条件 | 优先级 |
|------|------|---------|--------|
| 立即（P0） | 根目录 deny patterns | 本次违规刚清理完，趁记忆新鲜 | P0 |
| 短期（P1） | ownership.toml deny_domains schema | 下次 sprint 规划时 | P1 |
| 中期（P2） | CLASSIFICATION.md 分类守卫 | shadow mode 数据足够，或下次大改 hook 时 | P2 |

## 实施约束

- 本仓库 `AGENTS.md` 第 17 行明确 **"不要建议改进本项目结构"** + **source-repo-readonly**
- 实施任一方案需走 **feature 分支 + PR 流程**（铁律：GitHub 主仓库）
- commit 消息中文
- PR 合并前必须 ci-ok + droid-review 通过
- 改 `ownership.toml` schema 需要兼容旧版本（schema_version 不变，加可选字段）

## 触发实施的条件

任一条件满足时，把本技术债转成 sprint 任务：

1. **函授重构完成**（当前用户优先级）
2. **下次审计/长核查工作流开始前**（避免重复违规）
3. **subagent 写入根目录事件再次发生**（说明盲区已变成实际负担）
4. **ownership.toml 需要新增第 3 个 domain 时**（趁机加 deny_domains schema）

## 关联文档

- 决策记录：`memory/kb/decisions/D-003-audit-verification-refactor-basis.md`
- 姊妹教训：`memory/kb/lessons/audit-verification-methodology.md`（核查方法论的 4 盲区）
- 详细核查数据：`memory/docs/audit/audit-verification/`（7 个文件）
- 分类规则源：`docs/CLASSIFICATION.md`
- 规则引擎源码：`memory_core/tools/pretooluse_guard.py`, `memory_core/tools/_guard_classify.py`, `memory_core/tools/_guard_patterns.py`
- ownership 配置：`memory/system/ownership.toml`
- hook 入口：`~/.factory/hooks.json`, `~/.factory/bin/memory-hook`
