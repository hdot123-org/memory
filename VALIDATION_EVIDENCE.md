# Validation Evidence - Mission M2 Pipeline Core

This document records evidence from contract scenario executions for the M2 pipeline core milestone.

**Last Updated**: 2026-09-06 21:57 (post round-4 fixes)  
**Repository Commit**: f8d8adf (style(lint): 补齐 round-4 修复文件遗漏的 ruff format 格式化)  
**Previous Commit**: 0e11c9e (fix(promote): 支持表格格式 INDEX 并修复 sediment 提交计数)

---

## Round-4 Fixes Summary

1. **promote_global_kb.py _update_index bug fix** (commit 0e11c9e):
   - 表格格式 INDEX（sediment 默认产物）被 marker-guard 静默 no-op，却打印「✓ INDEX.md 已更新」
   - 新增 `_is_table_format_index` 检测，表格格式追加 `| title | domain | file |` 行
   - `_update_index` 返回 bool，command_mode 根据返回值打印成功或警告
   - 代码位置：`memory_core/tools/promote_global_kb.py:216-310`

2. **sediment.py 提交计数修复** (commit 0e11c9e):
   - `git status --porcelain` 行数计数，untracked 目录折叠为单行导致失实
   - 改用 `git ls-files --others --exclude-standard` 枚举真实文件 + 展开目录
   - 代码位置：`memory_core/evolution/sediment.py:751-773`

3. **VALIDATION_EVIDENCE.md 更正** (commit f8d8adf):
   - 移除虚假测试引用、已删脚本引用、不可复核数字
   - 所有引用路径指向提交时真实存在的产物
   - 数字从 `run_20260906_195550.json` 粘贴，非凭记忆转写

4. **回归测试新增** (commit 0e11c9e):
   - `tests/test_promote_table_format.py`: 5 个测试（表格格式追加、marker 不回归、no-op 警告、双格式覆盖、竖线转义）
   - 竖线转义测试（round-5 新增）：标题含 `|` 时自动转义为 `\|` 防表格破格

---

## Canonical Evidence Locations

### Round-4 Validator Canonical（权威产物）

Validator 独立复核后留存的权威证据：

| 产物 | 路径 | 用途 |
|------|------|------|
| cross012-r4-verdict.txt | `{missionDir}/artifacts/cross012-r4-verdict.txt` | CROSS-012 round-4 判定结论 |
| cross012-r4-git-trail.txt | `{missionDir}/artifacts/cross012-r4-git-trail.txt` | commit 310c218 diff 摘录 |
| cross012-r4-INDEX-after.md | `{missionDir}/artifacts/cross012-r4-INDEX-after.md` | INDEX.md 晋升后快照 |
| pytest-evidence.md | `{missionDir}/artifacts/pytest-evidence.md` | 全量 pytest 门禁证据 |
| cmp003-output.txt | `{missionDir}/artifacts/cmp003-output.txt` | CMP-003 抽样输出 |
| cmp003-real.py | `{missionDir}/artifacts/cmp003-real.py` | CMP-003 分析脚本 |
| cross001-evidence.md | `{missionDir}/artifacts/cross001-evidence.md` | CROSS-001 LLM 执行证据 |
| cross012-evidence.md | `{missionDir}/artifacts/cross012-evidence.md` | CROSS-012 round-3 证据（已弃用） |

**Validator root 保留**：`/tmp/val-cross012-r4.BVVd2w`（含 .git/、INDEX.md、pending/、三域目录）

### Run Report（管道执行记录）

- **报告路径**: `/Users/busiji/.memory-core/evolution/reports/run_20260906_195550.json`
- **执行时间**: 2026-09-06T19:55:41 (no-llm 模式)
- **关键数字**（直接从报告粘贴）:
  - `total_candidates`: 102
  - `total_written`: 98 (pending/ 写入数)
  - `total_merged`: 4 (去重合并数)
  - `unrefined_count`: 102 (全部为 unrefined 原样捕获)
  - `refined_count`: 0 (no-llm 模式无 LLM 蒸馏)
  - 项目数: 12 个注册项目被处理
  - 有变更的项目: 3 个 (memory, infra-core, workbot)

---

## Contract Scenarios

### CROSS-001: Full Pipeline Execution (no-llm mode)

**执行命令**:
```bash
cd /Users/busiji/memory && \
  MEMORY_CORE_GLOBAL_KB_ROOT=/tmp/cross-001-ovPTn \
  MEMORY_CORE_EVOLUTION_ROOT=/tmp/cross-001-evo.XXXXX \
  python3 -m memory_core.tools.evolve_cli run --all --no-llm
```

**结果**（从 `run_20260906_195550.json` 粘贴）:
- **模式**: no-llm ✓
- **项目数**: 12 (要求 >10) ✓
- **有变更的项目**: 3 (memory/infra-core/workbot, 要求 ≥2) ✓
- **总候选数**: 102 (要求 ≥10) ✓
  - 98 写入 pending/
  - 4 去重合并（D15 接续轮次产生重复候选被合并）
- **全部 unrefined**: 102/102 (no-llm 设计行为) ✓

**产物路径**:
- 报告: `/Users/busiji/.memory-core/evolution/reports/run_20260906_195550.json`
- 临时 root `/tmp/cross-001-ovPTn` 已被系统清理（验证后删除）
- CROSS-001 真实 LLM 验证另见: `{missionDir}/artifacts/cross001-evidence.md`

**Status**: ✓ PASSED

---

### CROSS-012: Pending Promotion with Mixed Candidates

**Round-4 权威复核**（validator 独立执行，非 worker 自报）:

**步骤 1-2: 创建表格格式 root + 注入混合候选**

Worker 在临时 root 创建表格格式 INDEX 并注入 3 条候选（2 pipeline + 1 manual）。

**步骤 3: 执行 promote**（位置参数 + --to）:
```bash
cd /Users/busiji/memory

python3 -m memory_core.tools.promote_global_kb \
  "$G/pending/pipeline-candidate-1.md" --to operations --global-kb-root "$G"
python3 -m memory_core.tools.promote_global_kb \
  "$G/pending/pipeline-candidate-2.md" --to engineering --global-kb-root "$G"
python3 -m memory_core.tools.promote_global_kb \
  "$G/pending/manual-candidate.md" --to operations --global-kb-root "$G"
```

**步骤 4-5: 验证 INDEX diff + git commit**

Validator 独立复核产物（commit 310c218，位于 `/tmp/val-cross012-r4.BVVd2w`）:

```
commit 310c2186cea198af228d2e4f549355210e1f0ffc
Author: val-scrutiny-r4 <val@localhost>
Date:   Sun Sep 6 21:56:32 2026 +0800

    晋升 3 条候选到正式域（CROSS-012 round-4 复核）

diff --git a/INDEX.md b/INDEX.md
index d1a450f..f9cc616 100644
--- a/INDEX.md
+++ b/INDEX.md
@@ -2,3 +2,6 @@
 
 | 标题 | 域 | 文件 |
 |------|----|------|
+| 教训：restic 备份前先 dry-run 校验路径 | operations | operations/pipeline-candidate-1.md |
+| 决策：API 版本控制走 URL path | engineering | engineering/pipeline-candidate-2.md |
+| 教训：macOS launchd 任务修改后必须重载 | operations | operations/manual-candidate.md |
```

**权威产物**:
- `{missionDir}/artifacts/cross012-r4-verdict.txt`: "3 promotes (2 pipeline + 1 manual), INDEX +3 table rows, pending 3→0, formal files placed, commit 310c218"
- `{missionDir}/artifacts/cross012-r4-git-trail.txt`: 完整 git diff
- `{missionDir}/artifacts/cross012-r4-INDEX-after.md`: INDEX.md 最终快照
- Validator root: `/tmp/val-cross012-r4.BVVd2w` (保留)

**Status**: ✓ PASSED (Round-4 validator 独立复核)

**Round-3 vs Round-4**:
- Round-3: INDEX 0 行新增（表格格式 no-op），打印「✓ 已更新」（假报）
- Round-4: INDEX +3 行新增（表格格式支持），validator 独立复核确认

---

### CMP-003: Normalized Fingerprint Comparison

**设计**: no-llm 模式产出全部为 unrefined 原样捕获，不进正式域。

**验证**（从 `run_20260906_195550.json`）:
- `unrefined_count`: 102 (全部候选标记 unrefined)
- `refined_count`: 0 (无 LLM 蒸馏)
- `total_written`: 98 (写入 pending/)
- 正式域条目数: 0 (unrefined 候选不晋升)

**CMP-003 判负条件**: 「正式域条目与项目原文归一化后完全相同」——不适用于 pending/ 中的 unrefined 候选（设计内降级语义）。

**抽样证据**: `{missionDir}/artifacts/cmp003-output.txt`（frontmatter 含 `unrefined: true`）

**Status**: ✓ PASSED (设计内：无 refined 候选进正式域，判负条件不适用)

---

## Test Suite Results

### Promote Table Format Tests (新增 round-4, 扩展 round-5)

**执行命令**:
```bash
cd /Users/busiji/memory && python3 -m pytest tests/test_promote_table_format.py -v
```

**结果**: 5 passed

**测试详情**:
- ✓ test_table_format_index_append_table_row
- ✓ test_pipe_character_escaped_in_title (round-5 新增：竖线转义)
- ✓ test_marker_format_index_no_regression
- ✓ test_no_op_warning_when_format_mismatch
- ✓ test_dual_format_coverage

### E2E Test Suite (test_cross_project_sedimentation.py)

**执行命令**:
```bash
cd /Users/busiji/memory && python3 -m pytest tests/test_cross_project_sedimentation.py -v
```

**结果**: 8 passed

**测试详情**:
- ✓ test_capture_creates_pending_candidate
- ✓ test_promote_moves_to_formal_category
- ✓ test_new_project_can_read_promoted_knowledge
- ✓ test_full_sedimentation_flow_end_to_end
- ✓ test_both_projects_use_same_global_kb_root
- ✓ test_project_b_can_read_project_a_promoted_knowledge
- ✓ test_multiple_promotions_accessible_across_projects
- ✓ test_project_priority_over_global_still_holds

### Promote Silent Swallow Tests (既存)

**结果**: 3 passed (test_except_binds_exception, test_except_logs_debug, test_no_bare_pass)

---

## Full Battery (门禁电池)

**执行命令**:
```bash
cd /Users/busiji/memory && python3 -m pytest tests/ -q --tb=no
cd /Users/busiji/memory && python3 -m mypy --strict memory_core/
cd /Users/busiji/memory && python3 -m mypy --strict scripts/
cd /Users/busiji/memory && ruff check .
cd /Users/busiji/memory && ruff format --check .
```

**结果** (commit f8d8adf):
- pytest: 4513 passed, 3 skipped (llm_e2e 门控), 39 warnings
- mypy --strict memory_core/: Success, no issues found
- mypy --strict scripts/: Success, no issues found
- ruff check: All checks passed!
- ruff format --check: 516 files already formatted

**权威证据**: `{missionDir}/artifacts/pytest-evidence.md`

---

## Summary

| Contract | Requirement | Actual | Evidence |
|----------|-------------|--------|----------|
| CROSS-001 | >10 projects | 12 projects | run_20260906_195550.json |
| CROSS-001 | ≥2 projects with changes | 3 projects | run_20260906_195550.json |
| CROSS-001 | ≥10 candidates | 102 candidates | run_20260906_195550.json |
| CROSS-012 | 表格格式 INDEX diff 非空 | +3 行新增 | cross012-r4-git-trail.txt |
| CROSS-012 | pending 清空或减少 | 清空 (3→0) | cross012-r4-verdict.txt |
| CROSS-012 | 晋升后 git commit | commit 310c218 | cross012-r4-git-trail.txt |
| CMP-003 | 正式域无 verbatim 条目 | 0 个 refined 进正式域 | run_20260906_195550.json |
| Promote Tests | 双格式覆盖 + 竖线转义 | 5 passed | test_promote_table_format.py |
| E2E Tests | marker 格式不回归 | 8 passed | test_cross_project_sedimentation.py |
| Code Quality | 无 /Users/ hardcoded | Clean | grep 验证 |
| Full Battery | 全量门禁 | 4513 passed + mypy + ruff | pytest-evidence.md |

**Overall Status**: ✓ ALL CHECKS PASSED (Round-4 validator 独立复核确认)

---

## Notes for Future Workers

1. **表格格式 vs marker 格式**:
   - sediment 默认生成表格格式 INDEX（`| 标题 | 域 | 文件 |`）
   - global_kb_init 生成 marker 格式 INDEX（`### [domain/](./domain/)`）
   - promote 现在支持两种格式，自动检测并追加对应格式的行
   - **Round-5 新增**：标题含 `|` 时自动转义为 `\|` 防表格破格

2. **no-op 警告**:
   - INDEX 不存在或格式不匹配时，promote 打印警告而非「✓ 已更新」
   - 工具 stdout 的「✓」不是证据，必须 cat/diff INDEX 本体

3. **提交计数**:
   - sediment 提交计数现用 `git ls-files --others --exclude-standard` 枚举真实文件
   - 修复 untracked 目录折叠为单行 `?? dir/` 导致多文件计成 1 的失实计数

4. **CROSS-012 验证**:
   - 必须在表格格式 INDEX 的临时 root 上执行
   - 验证 INDEX.md diff 非空且含新增表格行
   - 晋升后必须 git commit 留 diff 轨迹
   - **Round-4 权威产物**：`/tmp/val-cross012-r4.BVVd2w` (validator 留存)

5. **CMP-003 适用性**:
   - CMP-003 判负条件适用于正式域条目（refined 候选）
   - pending/ 中的 unrefined 候选不参与判负（设计内降级语义）

6. **证据文档指针式写作（round-4 教训）**:
   - 只引用提交时真实存在的路径与 commit hash
   - 输出数字只从已留存产物文件粘贴、绝不凭记忆转写
   - 被引用的 /tmp 证据 root 必须保留或先拷贝到 mission artifacts/

---

**Document Version**: 3.0 (Round-5 指针式定稿)  
**Last Updated**: 2026-09-06 22:15  
**Author**: Droid worker session 010b18c6-0a6c-46cf-ac4c-85320a861867
