# v5 D+ 函数全量拆解重构日志

> Date: 2026-07-20
> Mission: v5 D+ 函数全量拆解（24 函数 CC>=21 → CC<=20）
> Status: 完成
> radon D+: 24 → 0（归零）

## Mission 概述

**目标**：拆解 v5 baseline 剩余全部 24 个 D+ 函数（CC>=21）到 C 级（CC<=20），使 radon D+ 计数归零。

**约束**：
- 不改变任何外部 API、返回值、副作用顺序
- 现有测试只增不删
- 每个提取的 helper CC <=20
- 所有 commit 消息中文
- 禁止 `--admin` 合并

**3 种重构模式**：

| 模式 | 适用场景 | 示例 |
|------|---------|------|
| Dispatch Table | if/elif 链替换为字典/表驱动 | classify_tool_use, _extract_path_from_execute, _read_a_layer |
| Phase Extraction | 顺序流程拆分为独立 phase helper | migrate_project_memory, _discover_canonical_files, check_server |
| Validator Extraction | 条件检查集合提取为独立 validator | _truth_basis_errors_for, _append_infra_summary, CoreConfig.__post_init__ |

---

## Milestone 1: F 级函数拆解（CC>=41，4 函数）

**PR**: #165, #166
**拆解后 D+ 计数**: 24 → 20

### F1: classify_tool_use (CC 54 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/_guard_classify.py:336 |
| 策略 | Dispatch Table |
| 提取 helper | 6 tool handler（_classify_write_edit / _classify_multiedit / _classify_notebook / _classify_execute / _classify_task / _classify_unknown）+ 共享 _classify_agents_md helper |
| 测试 | tests/test_guard_classify.py 72 passed |

### F2: migrate_project_memory (CC 51 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/migrate_project_memory.py:974 |
| 策略 | Phase Extraction（8 phase） |
| 提取 helper | _resolve_memory_root / _validate_versions / _check_idempotency_and_downgrade / _perform_backup / _execute_migrations / _run_post_migration_hooks / _handle_migration_exception |
| 测试 | tests/test_cli_migrate.py + 4 个 migrate 测试文件，38 passed |

### F3: _discover_canonical_files (CC 45 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/memory_hook_integrity_manifest.py:190 |
| 策略 | Phase Extraction（5 phase）+ glob/non-glob resource dispatch |
| 提取 helper | _scan_canonical_patterns / _scan_artifact_runtime / _walk_ownership_domains / _walk_ownership_resources / _dedup_and_filter |
| 先补测试 | tests/test_discover_canonical_files.py（9-case 参数化矩阵） |
| 测试 | integrity tests 40 passed |

### F4: check_server (CC 43 → 11)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/daily_kb_audit.py:951 |
| 策略 | Phase Extraction（4 section）+ _append_violation DRY helper |
| 提取 helper | _check_server_ssh / _check_server_docker / _check_server_ports / _check_server_http_endpoints / _append_violation |
| 测试 | audit tests 264 passed |

**M1 门禁**: pytest 3024 passed / radon D+ 20 / vulture 86 / mypy 197 / coverage 83%

---

## Milestone 2: E 级函数拆解（CC 31-40，7 函数）

**PR**: #167, #168, #169, #170
**拆解后 D+ 计数**: 20 → 13

### E1: _extract_session_info_streaming (CC 40 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/session_end_logger.py:92 |
| 策略 | 5 helper extraction |
| 提取 helper | _parse_session_timestamp / _extract_preview_content / _collect_tool_uses / _build_session_dict / _resolve_session_id |
| 测试 | telemetry/synced_lines tests 13 passed |

### E2: build_context_package_core (CC 38 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/memory_hook_core.py:129 |
| 策略 | 5 helper extraction |
| 提取 helper | _check_canonical_missing / _resolve_scope / _get_truth_basis / _build_status / _assemble_context_dict |
| 测试 | test_memory_hook_core.py 7 passed |

### E3: _enrich_project_info_from_config (CC 37 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/init_project_memory.py:1066 |
| 策略 | 4 detector extraction + dispatch |
| 提取 helper | _detect_pyproject_markers / _detect_packagejson_deps / _detect_tsconfig / _detect_cargo + _dispatch_detector |
| 先补测试 | tests/test_enrich_project_info_detectors.py（4 detector 测试） |
| 测试 | init/enrich tests 201 passed |

### E4: _append_infra_summary (CC 36 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/daily_kb_audit.py:1482 |
| 策略 | 8 summarizer helper |
| 提取 helper | _summarize_ssh / _summarize_systemd / _summarize_containers / _summarize_ports / _summarize_http / _summarize_disks / _summarize_database |
| 测试 | audit tests 264 passed |

### E5: gateway main (CC 35 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/memory_hook_gateway.py:1782 |
| 策略 | Event dispatch table + 8 handler |
| 提取 helper | _handle_source_repo / _handle_pretooluse / _handle_session_start / _handle_session_end / _handle_prompt_submit / _handle_post_tool_use / _handle_tool_result / _handle_unknown_event |
| 测试 | gateway tests 347 passed |

### E6: migrate_v040_to_v050 (CC 33 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/migrate_project_memory.py:401 |
| 策略 | 8 step extraction |
| 提取 helper | _check_v040_idempotency / _move_config_files / _move_kb_files / _move_templates / _update_references / _cleanup_old_layout / _validate_migration / _build_v050_result |
| 测试 | migrate tests 38 passed |

### E7: _maybe_sync_telemetry (CC 33 → <=20)

| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/memory_hook_gateway.py:1562 |
| 策略 | 8 helper extraction |
| 提取 helper | _check_backoff / _probe_endpoint / _read_pending_records / _build_batch / _send_batch / _compact_sent / _record_outcome / _update_backoff |
| 测试 | telemetry/gateway tests 217 passed |

**附带修复**: mypy 类型注解回归修复 (PR #170)，197 → 189 errors

**M2 门禁**: pytest 3082 passed / radon D+ 13 / vulture 86 / mypy 189 / coverage 83%

---

## Milestone 3: D 级函数拆解（CC 21-30，13 函数）

**PR**: #171
**拆解后 D+ 计数**: 13 → 0（MISSION OBJECTIVE ACHIEVED）

### D1: daily_kb_audit.py 三函数

**main** (CC 21 → <=20)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/daily_kb_audit.py:1680 |
| 策略 | 4 helper extraction |
| 提取 helper | _run_infra_check / _handle_no_projects / _audit_all_projects / _print_console_summary |
| 先补测试 | tests/test_daily_kb_audit_main.py |

**check_large_or_db_files** (CC 21 → 11)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/daily_kb_audit.py:417 |
| 策略 | 3 helper extraction |
| 提取 helper | _is_excludable_file / _check_single_file / _check_backups_dir |

**_summarize_report** (CC 21 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/daily_kb_audit.py:1413 |
| 策略 | 1 helper（消除 project/infra 重复） |
| 提取 helper | _summarize_violation_block |

### D2: _extract_path_from_execute + _truth_basis_errors_for + CoreConfig.__post_init__

**_extract_path_from_execute** (CC 30 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/_guard_classify.py:113 |
| 策略 | Dispatch Table（14 命令分支） |
| 提取 helper | _HANDLERS 表（14 regex + handler 对） |
| 测试 | test_guard_classify.py 72 passed |

**_truth_basis_errors_for** (CC 28 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/business_policy_checks.py:510 |
| 策略 | 7 validator extraction |
| 提取 helper | _check_section_presence / _check_ref_existence / _check_ref_overlaps / _check_canonical_refs / _check_classify_refs / _check_lower_bound / _check_path_resolution（消除 3 处重复） |
| 测试 | business_policy/truth_basis tests 288 passed |

**CoreConfig.__post_init__** (CC 23 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/memory_hook_config.py:91 |
| 策略 | 4 grouped validator |
| 提取 helper | _validate_environment / _validate_paths / _validate_policy / _validate_callbacks |
| 测试 | config_validation tests 61 passed |

### D3: migrate main + _read_a_layer + plan_residue_migration + _detect_project_type

**migrate main** (CC 26 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/migrate_project_memory.py:1262 |
| 策略 | 4 helper extraction |
| 提取 helper | _build_parser / _handle_rollback / _format_output / _emit_result |
| 测试 | migrate CLI tests 38 passed |

**_read_a_layer** (CC 26 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/daily_summary_generator.py:70 |
| 策略 | Dispatch Table（7 字段分支） |
| 提取 helper | _FIELD_HANDLERS 表（7 字段 dispatch） |
| 测试 | daily_summary_generator tests 55 passed |

**plan_residue_migration** (CC 25 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/audit_project_layout.py:972 |
| 策略 | 2 helper extraction |
| 提取 helper | _scan_root_pollution / _populate_forbidden_overwrites |
| 测试 | audit_project_layout tests 61 passed |

**_detect_project_type** (CC 24 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/project_probe.py:300 |
| 策略 | 1 helper + marker config |
| 提取 helper | _count_markers |
| 测试 | project_probe tests 18 passed |

### D4: session_end_logger main + cmd_apply_upgrade + batch_capture

**session_end_logger main** (CC 26 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/session_end_logger.py:349 |
| 策略 | 2 helper extraction |
| 提取 helper | _resolve_session_paths / _safe_run_session_end |
| 先补测试 | tests/test_session_end_logger_main.py |
| 测试 | session tests 26 passed |

**cmd_apply_upgrade** (CC 21 → 11)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/hook_upgrade.py:293 |
| 策略 | 3 helper extraction |
| 提取 helper | _prompt_approval / _backup_files / _format_result |
| 测试 | hook_upgrade tests 27 passed |

**batch_capture** (CC 21 → <=10)
| 项目 | 值 |
|------|---|
| 文件 | memory_core/tools/telemetry_bridge.py:239 |
| 策略 | 2 helper extraction |
| 提取 helper | _build_batch_items / _post_with_retries |
| 测试 | telemetry_error_capture tests 24 passed |

**M3 门禁**: pytest 3111 passed / radon D+ **0** / vulture 86 / mypy 183 / coverage 84.52%

---

## 新增测试文件清单

| 测试文件 | 覆盖函数 | Case 数 |
|---------|---------|--------|
| tests/test_discover_canonical_files.py | _discover_canonical_files | 9-case 参数化 |
| tests/test_session_info_helpers.py | _extract_session_info_streaming helpers | 4 |
| tests/test_enrich_project_info_detectors.py | _enrich_project_info_from_config detectors | 4 |
| tests/test_daily_kb_audit_main.py | daily_kb_audit.main | 3+ |
| tests/test_session_end_logger_main.py | session_end_logger.main | 3+ |

总新增测试：96 个（从 3015 → 3111）

---

## 附带修复

### CI fixture finalizer 泄漏（PR #172）

**问题**：Python 3.11 CI 中 pytest-rerunfailures + pytest 8.x + telemetry singleton 状态泄漏导致 `assert not self._finalizers` 间歇性失败。

**解决**：
- 移除全局 `--reruns 2`，改为精确标记特定 flaky 测试
- 新增 autouse singleton cleanup fixture
- Pin CI 依赖版本

**教训**：全局 --reruns 掩盖真实测试问题，应精确标记。详见 `memory/kb/lessons/pytest-fixture-finalizer-leak.md`。

### Webhook session 路由失效（PR #173）

**问题**：`write-pending-ci.sh` 用 mtime scan 猜 session_id，worker session 永远比 orchestrator 新，导致 CI 完成事件路由到已死 worker session。

**解决**：用 sessions-index.json 精确查找 `role:orchestrator` + `status:active` 的 session。

**教训**：不要用 mtime 猜测 session 归属，用 sessions-index.json 的结构化 metadata。详见 `memory/kb/lessons/webhook-session-routing.md`。

### write-pending-ci.sh 全局化（PR #174）

**改进**：核心逻辑从项目级脚本提取到全局 `~/.factory/webhook/scripts/write-pending-ci.sh`，消除每个消费项目维护 wrapper 脚本的冗余。

---

## PR 链

| PR | 标题 | 状态 |
|----|------|------|
| #165 | refactor: 拆解 F 级函数 classify_tool_use + migrate_project_memory | merged |
| #166 | refactor: 拆解 F 级函数 _discover_canonical_files + check_server | merged |
| #167 | refactor: 拆解 E 级函数 session_info_streaming + build_context_package_core | merged |
| #168 | refactor: 拆解 E 级函数 enrich_project_info + append_infra_summary | merged |
| #169 | refactor: 拆解 E 级函数 gateway main + migrate_v040_to_v050 | merged |
| #170 | fix: 修复 M2 重构引入的 mypy 类型注解回归 | merged |
| #171 | refactor: 拆解 D 级函数（全部 13 个 CC 21-30 函数） | merged |
| #172 | fix: 修复 Python 3.11 CI fixture finalizer 泄漏 | merged |
| #173 | fix: 修复 webhook session 路由失效问题 | merged |
| #174 | refactor: write-pending-ci.sh 核心逻辑提取到全局路径 | merged |

---

## 最终质量指标

| 指标 | 基线 | M1 后 | M2 后 | M3 后（最终） |
|------|------|-------|-------|-------------|
| radon D+ | 24 | 20 | 13 | **0** |
| pytest passed | 3015 | 3024 | 3082 | **3111** |
| vulture | 86 | 86 | 86 | **86** |
| mypy errors | 197 | 197 | 189 | **183** |
| coverage | 82.37% | 83% | 83% | **84.52%** |
| 提取 helper 数 | - | 20+ | 40+ | **60+** |
| 新增测试 | - | +9 | +67 | **+96** |

## 结论

mission 核心目标达成：radon D+ 从 24 归零到 0。24 个 D+ 函数全部拆解到 CC<=20，60+ 个 helper 函数全部 C 级及以下。测试从 3015 增长到 3111（+96），覆盖率从 82.37% 提升到 84.52%。mypy 错误从 197 降低到 183（重构过程中顺手修复类型注解）。vulture 维持 86 不变（无新增死代码）。

所有外部 API 签名、返回值结构、副作用顺序完全保持不变。30/30 validation assertions passed。
