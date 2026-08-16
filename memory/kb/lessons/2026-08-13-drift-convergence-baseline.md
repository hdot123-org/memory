> Date: 2026-08-13
> Source: 漂移收敛基线评估（evolution scanner findings + git commit 分析）
> Tags: [lesson, drift-metrics, evolution-scanner, ci-gates, baseline]
> Related: [D-012-evolution-capability-tech-debt, 2026-08-12-ci-cd-automation-fixes]

## 核心判断：漂移收敛需要分层衡量，不能用单一指标

"高频进化后漂移是否变少了"这个问题不能笼统回答。必须拆成两个独立维度：

| 维度 | 状态 | 证据 |
|------|------|------|
| 结构/基础设施层漂移 | **已清零** ✅ | evolution scanner 自 2026-08-09 后连续 0 findings（每小时 2 次扫描，全部 success） |
| 代码逻辑/语义层漂移 | **仍活跃** ⚠️ | 最近 7 天 168 个 commit 中 67 个（40%）是 fix，靠 CI 门禁和 mission 审计发现 |

## 结构层收敛证据

### scanner 硬数据

- `.evolution/heartbeat.json`：`findings_count: 0`，status: ok
- 最近 10 次 Evolution Scan workflow 运行全部 success，耗时 20-38 秒（真正在跑工具，不是秒退）
- `.evolution/suppress.json`：空（没有人为压制任何 finding）
- 08-09 最后一批 findings（~50+ 条）内容验证了收敛真实性：
  - `CONTAINER_DOWN`、`SERVER_UNREACHABLE`：基础设施存活检查 → 已修复
  - `DOCSTRING_HOST_MENTIONS`（7 条）：codex/claude → factory 引用 → 已修复
  - `DOCS_VERSION_REFERENCES`（10+ 条）：wb-hook-v2 残留 → 已清理
  - `ERROR_PATTERN_LLM_API_ERROR`（count=88）：运行时错误 → 已解决

### scanner 的 6 类检查全部归零

| 工具 | 检查什么 | 当前状态 |
|------|---------|---------|
| daily_kb_audit | 容器存活、SSH 可达、HTTP 状态 | 0 findings |
| consistency_check | docstring host、版本号、lock parser | 0 findings |
| error_patterns | 运行时错误日志模式 | 0 findings |
| audit_layout | 文件目录布局 | 0 findings |
| validate_project | project memory 校验 | 0 findings |
| evolution_self_audit | evolution 系统自身审计 | 0 findings |

## 代码层仍活跃的证据

### fix commit 比例

最近 7 天（2026-08-07 ~ 08-13）commit 分类：

| 类型 | 数量 | 占比 |
|------|------|------|
| fix（漂移修正） | 67 | 40% |
| feat（正向建设） | 13 | 8% |
| chore/ci/test/perf/docs | 81 | 48% |

40% 的 fix 比例说明代码层尚未进入稳态。但 fix 的**性质在收敛**：

- 早期（5-7 天前，#324-#412）：结构性缺陷，一次修十几个（"修复 16 个缺陷"、"修复 8 个 P2 审计发现"）
- 近期（1-3 天前，#519-#561）：边缘 case，单个修一两个（"fix-has-test guard 误报"、"Dependabot PR 放行"）

### scanner 覆盖盲区

scanner 的 6 类检查**全部是结构/一致性层**，不做：
- 代码逻辑正确性分析
- 安全漏洞扫描
- 性能问题检测
- 架构合理性评估

代码层漂移的发现渠道是 CI 门禁（mypy/shellcheck/fix-has-test/pytest）和 mission 审计（多模型交叉验证），而非 30 分钟定时扫描。

## 教训

1. **"扫描器查不出问题" ≠ "代码没有问题"** —— scanner 是结构层防线，代码层是 CI 门禁防线，两者职责不同
2. **衡量漂移收敛必须分层** —— 结构层归零是真实进步，但代码层 40% fix 比例说明仍在高频修正
3. **fix commit 的颗粒度变化是收敛信号** —— 从"一次修十几个结构性缺陷"到"一次修一两个边缘 case"，方向正确
4. **稳态判据** —— fix 比例降到 15% 以下 + scanner 持续 0 findings + 无新漂移类别出现，三者同时满足才算进入稳态

## 后续基线对照

本文档作为漂移收敛的基线（Baseline）。后续评估时对比：
- scanner findings 是否仍为 0
- fix commit 比例是否持续下降
- 是否出现新的漂移类别
- scanner 是否需要扩展代码层检查（第 7 个工具）

## Truth Basis

### Source Refs

- `.evolution/heartbeat.json`（2026-08-13T00:43:09，findings_count: 0）
- `.evolution/findings_over_time.json`（08-09 最后一批 findings 明细）
- `.evolution/suppress.json`（空，无人为压制）
- `.evolution/config.yml`（6 类检查工具定义）
- `git log --since="2026-08-07"`（168 commits，67 fix = 40%）
- GitHub Actions: 最近 10 次 Evolution Scan 运行全部 success

### Authority Refs

- project-map/INDEX.md
- memory/kb/global/memory-system.md
- memory/kb/decisions/D-012-evolution-capability-tech-debt.md

### Evidence Refs

- PR #324-#561 的 fix commit 明细
- CI 门禁配置（.github/workflows/ci.yml）

### Conflict Status

- resolved
