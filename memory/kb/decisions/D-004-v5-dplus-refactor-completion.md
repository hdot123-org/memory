# D-004: v5 D+ 函数全量拆解完成

> Status: accepted
> Date: 2026-07-20
> Source: v5 D+ 函数全量拆解 mission（24 函数 CC>=21 → CC<=20，radon D+ 归零）
> Tags: [decision, refactor, radon, complexity, d-plus, mission, v5]
> Related: [D-003-audit-verification-refactor-basis, audit-verification-methodology]

## 决策

将 24 个 D+ 函数（CC>=21）全部拆解到 C 级（CC<=20），使 `radon cc` 报告的 D+ 计数归零。不改变任何外部 API、返回值、副作用顺序。

## 背景

mission 前 radon 报告 D+ = 24（D=13 / E=7 / F=4），Top CC 值 54/51/45/43。基于 D-003 的 v5 终版数据基线和三核交叉核查结果，制定 3 milestone 渐进式拆解策略。

## 关键决策

### 决策 1: 三种重构模式覆盖全部 24 函数

根据函数结构特征选择三种重构模式，而非一刀切：

| 模式 | 适用场景 | 覆盖函数数 | 代表函数 |
|------|---------|-----------|---------|
| Dispatch Table | if/elif 链（命令分发、字段路由） | 5 | classify_tool_use(CC54) / _extract_path_from_execute(CC30) / _read_a_layer(CC26) / gateway main(CC35) / _enrich_project_info_from_config(CC37) |
| Phase Extraction | 顺序流程（迁移、检查、同步） | 7 | migrate_project_memory(CC51) / _discover_canonical_files(CC45) / check_server(CC43) / migrate_v040_to_v050(CC33) / _maybe_sync_telemetry(CC33) / session_end_logger main(CC26) / daily_kb_audit main(CC21) |
| Validator Extraction | 条件检查集合（验证、配置校验） | 4+ | _truth_basis_errors_for(CC28) / _append_infra_summary(CC36) / CoreConfig.__post_init__(CC23) / build_context_package_core(CC38) |

其余函数用 Extract Method 直接提取 helper（如 plan_residue_migration / cmd_apply_upgrade / batch_capture / _detect_project_type 等）。

**选择理由**：单一模式无法覆盖所有结构。Dispatch Table 消除分支爆炸，Phase Extraction 保持流程可读性，Validator Extraction 保持验证逻辑独立性。

### 决策 2: CC<=20 严格门禁

每个提取的 helper 函数 CC 必须 <=20（radon C 级或更低）。如果提取后某 helper 仍超 CC=20，继续拆分直到达标。

**选择理由**：CC<=20 是业界公认的"可维护"阈值（radon C 级上限）。mission 目标是全部 D+ 归零，不是"尽量降低"。

### 决策 3: 3 Milestone 拆分（F -> E -> D）

按 CC 值从高到低分 3 个 milestone：

| Milestone | 函数数 | CC 范围 | PR 编号 | 合并后 D+ 计数 |
|-----------|--------|---------|---------|---------------|
| M1: F 级 | 4 | CC>=41 | #165, #166 | 24 -> 20 |
| M2: E 级 | 7 | CC 31-40 | #167, #168, #169 | 20 -> 13 |
| M3: D 级 | 13 | CC 21-30 | #171 | 13 -> 0 |

**选择理由**：
- F 级优先：最高 CC 值风险最大，先消除降低后续重构的合并冲突风险
- 每 milestone 独立 PR：便于 review、回滚、CI 验证
- M2 拆 3 个 PR：gateway main 副作用顺序精确保持需单独处理

### 决策 4: radon D+=0 作为 mission 核心可观测目标

整个 mission 的成功标准简化为一个数字：`radon cc memory_core/ scripts/ -n D -s | grep -cE '^\s+[A-F]\s'` 输出 `0`。

**选择理由**：
- 可自动化验证（CI 可跑）
- 无歧义（数字就是数字）
- 与 D-003 的 v5 终版基线对齐

### 决策 5: 测试缺口函数先补测试再拆解

5 个函数现有测试不足，拆解前必须先写单元测试建立行为基线：

| 函数 | 新增测试文件 | 测试 case 数 |
|------|------------|-------------|
| _discover_canonical_files | test_discover_canonical_files.py | 9-case 参数化 |
| _extract_session_info_streaming | test_session_info_helpers.py | 4 helper 测试 |
| _enrich_project_info_from_config | test_enrich_project_info_detectors.py | 4 detector 测试 |
| session_end_logger.main | test_session_end_logger_main.py | path resolution + error path |
| daily_kb_audit.main | test_daily_kb_audit_main.py | infra/no-projects/output |

**选择理由**：纯重构必须证明行为不变。没有测试覆盖的函数拆解后无法确认行为保持。先补测试 = 先建立行为快照。

## 最终结果

| 指标 | 基线 | 最终 | 变化 |
|------|------|------|------|
| radon D+ | 24 | **0** | -24 (归零) |
| pytest passed | 3015 | **3111** | +96 (新增 helper 测试) |
| coverage | 82.37% | **84.52%** | +2.15% |
| mypy errors | 197 | **183** | -14 (重构时顺手修类型注解) |
| vulture | 86 | **86** | 不变 |
| PR 数 | - | **10** | #165-#174 |

## 附带修复

mission 执行过程中发现并修复的基础设施问题：
1. Python 3.11 CI fixture finalizer 泄漏（PR #172）
2. Webhook session_id 路由失效（PR #173）
3. write-pending-ci.sh 全局化到 ~/.factory/webhook/scripts/（PR #174）

## 约束遵守

- 外部函数签名不变（参数名/类型/顺序/默认值）
- 返回值结构不变（dict keys / dataclass fields / 类型）
- 副作用顺序不变（文件写入 / subprocess / stdout / metrics 发射）
- 现有测试只增不删
- 所有 commit 消息中文
- 禁止 `--admin` 合并，所有 PR 通过正常 CI 门禁

## 关联

- 重构基线决策：`memory/kb/decisions/D-003-audit-verification-refactor-basis.md`
- CI fixture leak 教训：`memory/kb/lessons/pytest-fixture-finalizer-leak.md`
- Webhook 路由教训：`memory/kb/lessons/webhook-session-routing.md`
- 详细重构日志：`memory/docs/refactor-logs/v5-dplus-refactor-2026-07-20.md`
- validation-state.json：30/30 assertions passed
