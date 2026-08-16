> Date: 2026-08-13
> Status: accepted (pending multi-model review)
> Tags: [decision, evolution-scanner, code-hygiene, ast, quota-isolation]
> Related: [D-012-evolution-capability-tech-debt, 2026-08-13-drift-convergence-baseline]

## 背景

Evolution scanner 的 6 类检查全部是结构/基础设施/文档一致性层，代码逻辑层漂移完全不在覆盖范围内。最近 7 天 168 个 commit 中 40%（67 个）是 fix，全部靠 CI 门禁和 mission 审计发现，scanner 从未捕获。

详见基线 lesson：`2026-08-13-drift-convergence-baseline.md`。

## 决策

为 evolution scanner 新增第 7 个审计工具 `code_hygiene_audit`，扩展检测能力到代码逻辑层。采用三步走路线（P0→P1→P2），并引入 4 项工程防护机制。

### 架构改动（3 处）

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `.evolution/config.yml` | audit_tools 加第 7 项 + `max_code_hygiene_issues_per_tick` |
| 2 | `scripts/evolution_adapters.py` | 加 `adapt_code_hygiene()` + 注册 ADAPTER_MAP + TOOL_TO_CATEGORIES |
| 3 | `scripts/evolution_scanner.py` main() | 第 3 个分流池：regular / self_audit / code_hygiene |

### 实施路线图

#### P0：CLI 工具研发与基线验证

新建 `memory_core/tools/code_hygiene_audit.py`，注册 CLI 入口 `memory-code-hygiene-audit`。

检测规则（AST 级）：
- bare except：`except`/`except Exception:` 块内无 log/raise/control-transfer
- 精细判定：仅报告"静默吞没"（pass/空块/无副作用），顶层守护和 graceful degradation 不报
- 豁免机制：支持 `# noqa: bare-except` 行尾注释
- `--dry-run --json` 输出标准 Finding 格式

验收标准：手动运行 `--dry-run` 对 37 处存量逐一验证，剔除误报。

#### P1：接入 Scanner + 独立第三池

- config.yml 加 `max_code_hygiene_issues_per_tick: 1`
- 适配器实现（含按文件聚合 + 抗行号偏移去重）
- scanner main() 三路分流

#### P2：扩展规则

- 整合 `scan_tech_debt.py`（TODO/FIXME 无 issue 引用）
- 整合 `v5_duplicate_scan.py`（AST 重复代码）
- 复用同一 CLI + 同一配额池

### 4 项工程防护

1. **抗行号偏移去重**：location 字段使用函数级锚点（`file::function_name`）而非精确行号，防止代码增删导致 issue flapping
2. **文件级 Issue 聚合**：同一文件多处 bare except 合并为一个 issue，将 37 个压缩到 ~20 个
3. **AST 精细判定 + noqa 豁免**：仅报告静默吞没，支持行尾注释豁免
4. **CLI 健壮性**：单文件解析失败不崩溃，记 warning 跳过

### 排除项（不纳入 scanner）

| 候选 | 排除理由 |
|------|---------|
| check_fix_has_test.py | 强依赖 PR 上下文 |
| mypy --strict memory_core/ | baseline 220 errors，海量 noise |
| pytest / ruff | CI 已做 hard gate |

## 理由

1. bare except 是唯一"CI 不查 + scanner 不查 + 存量 37 处"的盲区
2. scanner 的适配器架构已为扩展设计（开闭原则），改动面可控
3. INFRA-198 独立配额池范式可直接复用，隔离 noise
4. CI（即时阻断）与 Scanner（存量巡检）双轨并行，职责不重叠

## Truth Basis

### Source Refs

- `.evolution/config.yml`（6 类检查工具定义）
- `scripts/evolution_adapters.py`（ADAPTER_MAP + TOOL_TO_CATEGORIES）
- `scripts/evolution_scanner.py:547-557`（现有双池分流逻辑）
- `git log --since="2026-08-07"`（67 fix = 40%）
- bare except grep：37 处 / 20 文件

### Authority Refs

- project-map/INDEX.md
- memory/kb/decisions/D-012-evolution-capability-tech-debt.md
- memory/kb/lessons/2026-08-13-drift-convergence-baseline.md

### Conflict Status

- pending multi-model review
