# M5 收缩处置记录（shrink-webhook-and-delete）

> 日期：2026-08-30 / 分支：`mission-ic-m5-shrink-core`
> 本文件是 VAL-SHRINK-012 要求的窗口关闭处置记录：记载 M5 收缩 PR 中
> 每一类已迁文件的处置方式、保留窗口与关闭条件。

## 1. 删除面（本 PR 删除）

| 类别 | 文件 | 处置依据 |
|------|------|----------|
| webhook manifest/sync 所有权 | `webhook-scripts/`（全目录含 MANIFEST.sh）、`scripts/sync-webhook-scripts.sh` | 单一所有权源迁 infra-core 仓（PR infra-core#81）；两 manifest 不双 claim（VAL-SHRINK-002） |
| 分支清理三件套 | `scripts/branch_cleanup.sh`、`scripts/branch_cleanup_issue.sh`、`scripts/branch_cleanup_retired.txt` | infra-core composite `actions/branch-cleanup` 自包含（含独立 retired list）；memory 侧 thin caller 已切换 |
| 死代码（R2 追加） | `scripts/branch_cleanup_issue.sh` 残余副本 | 无 Linear 同步块、无 workflow 引用；infra-core composite 是唯一执行路径 |
| auto-merge 分诊 | `scripts/auto_merge_triage.sh` | auto-merge pipeline 执行体在 infra-core reusable |
| droid-review 分片执行体 | `scripts/droid_review/`（plan_shards / publish_findings / run_shard） | droid-review thin caller 委托 infra-core reusable（M4 切换） |
| 锚点助手副本 | `scripts/extract_anchor.py`、`scripts/anchor_gate.py` | 生产字节由 infra-core `webhook-scripts/cross-dir/` 托管（sha256 同源），memory 副本零独立价值 |
| 引擎工具六件 | `memory_core/tools/{version_sync,daily_kb_audit,error_pattern_detector,evolution_self_audit,code_hygiene_audit,audit_project_layout}.py` | 执行体与 `infra-*` CLI 入口在 infra-core（M3/M4 已切换）；pyproject 六入口同步修剪 |
| 审计拆分族 | `memory_core/tools/_audit_{project,checks,cli,infra,patch_redirect,report,server}.py` | 随 `daily_kb_audit` 死亡；`_gateway_*` / `_migrate_*` / `_patch_redirect_shared` 保留（存活 importer） |
| 孤儿测试族 | 50 个测试文件（drift-watch / tick-budget / suppression / webhook 副本 / daily-audit / version-sync / hygiene / error-patterns / droid-sharding / branch-cleanup 等） | 被测对象已删除；webhook 生产行为测试族随所有权迁 infra-core（manifest/sync 两文件已随 infra-core#81 移植，其余行为测试移植为后续项） |

## 2. 保留窗口（一个 release window 的回滚副本）

| 文件 | 保留理由 | 关闭条件 |
|------|----------|----------|
| `scripts/evolution_scanner.py` | M4 scan 切换（#1071）的回滚副本：若 infra-core reusable 出现不可修复回归，可快速恢复本仓执行体 | 下一个 release（≥1 个完整扫描周期绿）后删除；删除方式：独立 revert-able PR |
| `scripts/evolution_heartbeat.py` | M4 heartbeat 切换（#1069/#1071）回滚副本 | 同上 |
| `scripts/evolution_utils.py` | scanner/heartbeat 的同目录依赖链（生产 cross-dir 同步源为 infra-core，本副本仅供回滚） | 同上 |
| `scripts/evolution_adapters.py` | 同上 | 同上 |
| `scripts/check_droid_review.sh` | **不设窗口——长期保留**：ci-ok 聚合 job 依赖（VAL-HARD-107） | 无（永久保留，直至 ci-ok 面重构） |

## 3. 改名/重指向面

| 面 | 变更 |
|----|------|
| `pyproject.toml` | 修剪 6 入口（audit-layout / sync-versions / audit-daily / error-patterns / evolution-audit / code-hygiene-audit）；`memory-plan-residue` 重指向 `infra_core.packs.memory.layout_audit:plan_main` |
| `.evolution/config.yml` | 五引擎 inline 条目删除，改 `rule_packs: [{pack: memory}]` 引用（inline-wins 语义保留给原生工具 consistency_check / validate_project） |
| `scripts/qa/run_cli_e2e.py` | CLI_ALL / CLI_NO_ARGS_OK 修剪 3 个已删入口 |
| `scripts/qa/coverage_gap_finder.py` | CORE_MODULES 修剪 3 个已删模块 |
| README.md / AGENTS.md / BOUNDARY.md / CLASSIFICATION.md / docs/architecture/* | 陈旧指针更新为 infra-core 指向（VAL-SHRINK-006） |

## 4. error_patterns registry 写入评估（pack-seam (b) 结论）

pack 定义为 `infra-error-patterns --repo-root {repo_root} --json`（stdout JSONL 供
adapter 逐行解析）。该 CLI 运行时会将 registry 写入目标仓
`memory/kb/patterns/registry.jsonl`——与 memory-core 原版一致的**仓内写**：
- 写入发生在 scanner 的 ephemeral checkout（Actions job 结束即丢弃），不回推远端；
- **不加 `--dry-run`**：dry-run 会清空 stdout JSONL，scanner adapter 将得到零
  finding，破坏检测连续性（VAL-SHRINK-009）；
- scanner 本 run 不读 registry 落盘文件（消费 stdout），落盘仅为幂等副产品。

**补充实测（v0.5.1 生产真源）**：引擎 `run_audit_tool` 仅支持 `registry_jsonl`
文件模式，不支持 pack spec 的 `jsonl` stdout 模板（`json.loads` 直接失败 → 工具
None）。故 config 保留 `error_patterns` inline override（registry 文件模式，
inline wins），待引擎支持 jsonl stdout 后移除。

## 4.1 已知残留 gap（infra-core 后续项，非本仓可修）

- `layout_audit`（pack 名）在 memory `evolution_adapters.ADAPTER_MAP` 中无对应
  adapter（键为 `audit_layout`，且其输入 schema `{violations:[…]}` 与 infra
  输出 list-of-{kind,…} 不同）→ raw 透传 finding 缺 `rule_id`。实测 7/7 工具
  executed、无 crash，仅该域 finding 的 dedup 键退化。需 infra-core 侧注册
  pack 名 adapter 或对齐 ToolSpec 命名。

## 5. 验证快照

- 全量 pytest（fresh venv，见 PR CI）；ruff / actionlint 全绿
- VAL-SHRINK-009：五 infra 工具 + 两原生工具对本仓执行 `--json` 全 executed 且 rule_id 非空
- VAL-HARD-107：`scripts/check_droid_review.sh` 保留，ci-ok 契约测试绿

## 6. 窗口关闭记录（2026-09-02，close-rollback-release-window）

**权威口径（编排器裁定 2026-08-30）**：本窗口的关闭条件以 close-rollback-release-window
feature 契约为准——release v0.45.0（含 M5 收缩）发版后 **≥3 天稳定周期**（无回滚事件、
scan/heartbeat tick 正常）。§2 表中「下一个 release + ≥1 个完整扫描周期绿」系 shrink
worker 自录的弱口径，无权放宽计划，特此注明。

**时间锚点**：release v0.45.0 = 2026-08-30T09:44:45Z，门成熟 = 2026-09-02T09:44Z
（两锚点取严：M4 scan/heartbeat 切换 #1071 = 2026-08-29T21:32Z，+3 天 = 09-01T21:32Z；
release 锚更严）。

**实际关闭载体**：四件套 `scripts/evolution_{scanner,heartbeat,utils,adapters}.py`
由并行清理流的 **PR #1097**（merged 2026-08-31T04:49:30Z）删除——早于门成熟约 29.5
小时。发布后至本记录时刻零 revert/回滚事件（`git log` 逐 commit 核验），窗口实质
稳定期已满（发版至门成熟 3 天 + 门后 1 天），提前删除未造成回滚敞口损失。
close-rollback-release-window 派发（2026-09-02T23:33Z，门后）按验证优先流程核对既成
状态而非重复执行。

**处置偏差（#1097 相对本 feature 原配方）**：
- `tests/test_pr_merged_verification.py` 未删除，改为 import
  `infra_core.engine.evolution_utils`（importer 重指向在役引擎模块，测试保留为覆盖）；
- `tests/test_governance_rename.py` fixture 已适配；`pyproject.toml` coverage source
  三条目与 deptry ignore 已移除；
- `evolution-governance.yml` 的 `scripts/evolution_*.py` protected-patterns glob 与
  `.github/CODEOWNERS` 对应保护行由 #1097 一并移除（原 grep 白名单项随之失效）。

**本 PR 收尾**：`check_boundary.py` / `check_doc_classification.py` /
`check_pr_ref_consistency.py` 三处陈旧注释重指向 `infra_core.engine.*` 路径。全仓
grep `evolution_(scanner|heartbeat|utils|adapters)` 零本地文件 importer 残留（白名单：
`infra_core.engine.*` 模块路径引用与 README/.evolution 文档表述）。

**error_patterns override 复评**：inline override 已随 #1079 移除（引擎 jsonl stdout
支持落地后），本子项确认无遗留动作。

**VAL-CROSS-005 fresh window 证据**（供 m7 user-testing 复验，全文见 mission
evidence/m7-close-window/）：窗口 2026-09-01T23:33Z..09-02T23:33Z 内 scheduled scan
success ×5（06:26Z 起）、scheduled heartbeat success ×4（05:07Z 起）、零新
evolution-heartbeat issue；09-01T21:24Z..09-02T01:25Z 有 4 次 scheduled 启动失败
（run 零 job，引擎未执行，infra-core 同窗零投递，属 INFRA-578 平台投递家族，非
#1092/#1094 修复面回归）。watch item #1090：08-30T22:07Z tick 的
`auto_close_resolved` 按 self_audit 保护显式 skip（日志：「Skip auto-close #1090:
self-audit finding … requires manual/Droid resolution」），22:46:36Z 的关闭为人工
带外操作，此后 3 天无振荡。
