# 测试体系 Part1 深度分析报告

> 覆盖范围：`tests/test_business_policy_*.py` + `tests/conftest.py`
> 业务域：`workspace.tools.business_policy_checks`（唯一合法性系统策略校验）

---

## 1. 每个测试文件的测试类/函数数量统计

| 文件 | 测试类数 | 测试函数数 | 辅助函数 | 备注 |
|---|---|---|---|---|
| `conftest.py` | 0 | 0 | 3 (fixtures) | 全局共享 fixtures |
| `test_business_policy_smoke.py` | 11 | 36 | 2 | 冒烟/基础通路 |
| `test_business_policy_errors.py` | 8 | 30 | 2 | 错误信息校验 |
| `test_business_policy_integration.py` | 5 | 29 | 4 | 集成/回归场景 |
| `test_business_policy_paths.py` | 12 | 54 | 2 | 路径/权限/边界 |
| `test_business_policy_schema.py` | 10 | 62 | 6 | Schema/解析/全量覆盖 |
| **合计** | **46** | **211** | **19** | **最大的测试子体系** |

---

## 2. 每个测试函数的测试意图摘要

### 2.1 `conftest.py`

| Fixture | 意图 |
|---|---|
| `repo_root` | 返回仓库根目录路径 |
| `workspace_root` | 返回 memory_core 包根目录 |
| `tmp_memory_root` | 返回临时 `.memory` 目录（基于 pytest tmp_path） |

### 2.2 `test_business_policy_smoke.py` — 冒烟测试

| 类 | 函数 | 意图 |
|---|---|---|
| `TestModuleImport` | `test_import_module` | 验证模块可导入 |
| | `test_import_classes` | 验证 6 个公共类均可导入 |
| | `test_import_helpers` | 验证 8 个公共辅助函数均可导入且 callable |
| `TestProjectMapValidator` | `test_instantiation` | 验证类可实例化且持有 config 引用 |
| | `test_validate_project_map_files_missing` | 空文件时返回非空错误列表 |
| | `test_validate_unique_legal_system_contract_missing` | 空文件时 legal contract 返回错误 |
| `TestLegalContractChecker` | `test_instantiation` | 验证实例化 |
| | `test_validate_delegates` | 验证 delegate 方法返回 list |
| `TestFrozenTupleChecker` | `test_instantiation` | 验证实例化 |
| | `test_governance_empty_files_list` | 空 governance 文件列表时返回空错误 |
| | `test_governance_missing_files` | 不存在的 governance 文件返回错误（含 "missing"） |
| `TestEventContractChecker` | `test_instantiation` | 验证实例化 |
| | `test_event_contract_missing_files` | 缺失文件时返回错误（含 "missing"） |
| | `test_event_contract_complete_matching` | 完整匹配的事件合约文件应返回零错误 |
| `TestTruthBasisResolver` | `test_instantiation` | 验证实例化 |
| | `test_get_project_canonical` | 返回 dict 且包含 test-scope |
| | `test_truth_basis_unknown_scope` | 未知 scope 返回 validation=fail 且 errors 非空 |
| | `test_path_classification` | 验证 _classify_truth_ref 对多种路径返回非空字符串类别 |
| `TestScopeResolver` | `test_instantiation` | 验证实例化 |
| | `test_instantiation_with_override_path` | 带 override 文件实例化 |
| | `test_determine_project_scope_default` | 未知目录返回默认 scope |
| | `test_determine_project_scope_outside_repo` | repo 外目录返回默认 scope |
| | `test_get_project_canonical` | 返回 dict |
| | `test_get_project_runtime_root` | 返回 dict |
| | `test_get_required_canonical` | 返回 list |
| | `test_get_global_canonical` | 返回 list |
| | `test_project_map_refs` | 返回 list |
| | `test_refs_for_scope` | 三类 refs 均返回 list |
| | `test_scope_override_valid_json` | 有效 JSON override 合并到 canonical 和 runtime_root |
| | `test_scope_override_invalid_json` | 无效 JSON 返回空 overrides |
| | `test_scope_override_env_var` | 环境变量 SCOPE_CONFIG_PATH 可覆盖配置文件路径 |
| `TestHelperPathIsUnder` | 4 个测试 | 验证 `_path_is_under` 和 `_path_is_under_lexical` 的基本正/反用例 |
| `TestHelperSectionParsing` | 4 个测试 | 验证 `_section_bullets` 和 `_section_body` 的正/反用例 |
| `TestHelperJsonParsing` | 4 个测试 | 验证 `_markdown_code_tokens`、`_json_string_values`、`_json_object_keys` |
| `TestHelperExistingPaths` | 2 个测试 | 验证 `_existing_paths` 过滤不存在文件 |
| `TestFailurePaths` | 7 个测试 | 空输入/特殊字符输入的容错性 |
| `TestBoundaryInputs` | 5 个测试 | 超长文本、超长路径、空 formal sets 等边界输入 |

### 2.3 `test_business_policy_errors.py` — 错误消息校验

| 类 | 函数 | 意图 |
|---|---|---|
| `TestProjectMapValidatorErrors` | `test_validate_project_map_files_empty_content_produces_errors` | 空文件产生多个错误 |
| | `test_validate_project_map_files_no_round_references` | 含 round/wave 引用产生错误 |
| | `test_validate_project_map_files_all_markers_present_no_errors` | 所有标记齐全时零错误 |
| | `test_validate_unique_legal_system_contract_empty_files_produce_errors` | 空文件产生关于缺失声明的错误 |
| | `test_validate_unique_legal_system_contract_complete_no_errors` | 所有文件标记正确时零错误 |
| `TestFrozenTupleCheckerErrors` | `test_missing_governance_files_error` | 缺失 governance 文件报错 |
| | `test_missing_expected_tuple_markers_error` | 缺少预期标记报错 |
| | `test_legacy_markers_still_present_error` | 遗留标记仍存在时报错 |
| | `test_no_errors_when_all_correct` | 正确时零错误 |
| | `test_multiple_missing_files_aggregated` | 多个缺失文件聚合到一条错误 |
| `TestEventContractCheckerErrors` | `test_missing_event_contract_files_error` | 缺失事件合约文件报错 |
| | `test_formal_set_mismatch_error` | 匹配的 formal sets 应零错误 |
| | `test_formal_set_mismatch_detects_missing_source` | formal contract 缺少 source_type 产生 mismatch |
| | `test_out_of_contract_source_type_error` | 样本 JSON 中未知 source_type 产生 out-of-contract 错误 |
| | `test_legacy_field_keys_error` | 遗留字段键产生错误 |
| | `test_missing_formal_field_keys_error` | 缺少正式字段键产生错误 |
| `TestTruthBasisResolverReport` | `test_report_structure_for_unknown_scope` | 未知 scope 返回完整 dict 结构（10 个 key）|
| | `test_report_structure_for_known_scope` | 已知 scope 返回 dict 含 project_ref |
| | `test_report_errors_list_is_list_of_strings` | errors 字段始终是字符串列表 |
| `TestTruthBasisResolverErrors` | `test_missing_truth_canonical_error` | 不存在的 truth canonical 文件报错 |
| | `test_truth_basis_section_missing_error` | 缺少 Truth Basis section 报错 |
| | `test_missing_source_refs_error` | 空 Source Refs 报错 |
| | `test_unresolved_conflict_status_error` | 非 resolved 冲突状态报错 |
| | `test_identical_source_and_evidence_refs_error` | Source 和 Evidence refs 相同报错 |
| `TestScopeResolverScopeDetermination` | `test_default_scope_outside_repo` | repo 外目录返回默认 scope |
| | `test_scope_match_hints_inside_repo` | 匹配 hint 返回对应 scope |
| `TestErrorAggregation` | `test_project_map_multiple_errors` | 空文件产生 ≥3 个不同错误 |
| | `test_frozen_tuple_multiple_missing_markers_aggregated` | 多个缺失标记聚合到单条错误 |
| | `test_truth_basis_aggregates_all_file_errors` | global + project 文件的错误都收集 |
| `TestNoErrorBoundary` | `test_project_map_no_errors_with_correct_content` | 正确内容零错误 |
| | `test_frozen_tuple_no_errors` | 正确标记零错误 |
| `TestErrorMessageFormatConsistency` | `test_project_map_errors_are_lowercase_descriptions` | 错误是描述性句子，非原始常量名 |
| | `test_error_messages_do_not_contain_raw_paths_unless_missing` | 内容错误不泄露路径，缺失文件错误包含路径 |
| | `test_truth_basis_errors_include_file_reference` | 错误包含文件路径供上下文 |

### 2.4 `test_business_policy_integration.py` — 集成回归测试

| 类 | 函数 | 意图 |
|---|---|---|
| `TestCompleteFlow` | `test_project_map_validator_returns_empty_errors_for_valid_markers` | 有效标记时零错误 |
| | `test_project_map_validator_detects_missing_markers` | 检测缺失标记 |
| | `test_project_map_validator_detects_transition_refs` | 检测 round-1 过渡引用 |
| | `test_truth_basis_resolver_returns_fail_for_unknown_scope` | 未知 scope 返回 fail |
| | `test_scope_resolver_determines_default_scope` | 无 hints 时返回默认 |
| | `test_scope_resolver_matches_hint` | 匹配 hint 返回对应 scope |
| | `test_scope_resolver_handles_scope_overrides` | JSON override 文件可合并 canonical |
| `TestGatewayIntegration` | `test_gateway_style_project_map_check_flow` | 模拟 gateway 调用 project map 校验 |
| | `test_gateway_style_truth_basis_flow` | 模拟 gateway truth basis 流程 |
| | `test_gateway_style_scope_resolution_flow` | 模拟 gateway scope 解析 |
| | `test_gateway_style_event_contract_check` | 完整事件合约 gateway 校验（使用验证常量）|
| | `test_gateway_style_missing_contract_files` | 缺失合约文件的 gateway 错误 |
| `TestAdapterConfigIntegration` | `test_workbot_adapter_config_triggers_project_map_checks` | workbot adapter 触发完整检查 |
| | `test_neutral_adapter_config_minimal_markers` | 最小标记配置应产生错误 |
| | `test_adapter_with_custom_scope_match_hints` | 自定义 hint 多 scope 匹配 |
| | `test_adapter_scope_override_env_var` | 环境变量覆盖 scope 配置 |
| `TestMultiPolicyInteraction` | `test_project_map_and_legal_contract_combined` | ProjectMap + LegalContract 联合校验 |
| | `test_frozen_tuple_checker_with_expected_markers` | 正确 frozen tuple 零错误 |
| | `test_frozen_tuple_checker_detects_legacy_markers` | 遗留标记检测 |
| | `test_event_contract_checker_detects_mismatch` | 事件合约不匹配检测 |
| | `test_combined_all_checkers_pass` | 所有 checker 联合运行全部通过 |
| `TestRegressionScenarios` | `test_read_text_if_exists_fn_is_used` | 验证 read_text_if_exists_fn 被调用（记录调用次数）|
| | `test_truth_basis_ref_classification` | 验证 _classify_truth_ref 对 4 种路径分类 |
| | `test_scope_resolver_handles_outside_repo` | 处理 repo 外的路径 |
| | `test_scope_resolver_loads_invalid_json_gracefully` | 无效 JSON 优雅降级 |
| | `test_scope_resolver_handles_non_dict_json` | 非 dict JSON 优雅降级 |
| | `test_path_is_under_helper` | 验证 _path_is_under |
| | `test_path_is_under_lexical_helper` | 验证 _path_is_under_lexical |
| | `test_section_bullets_extracts_list_items` | 验证 _section_bullets |
| | `test_section_body_extracts_text_between_headings` | 验证 _section_body |
| | `test_markdown_code_tokens_extracts_backtick_values` | 验证 _markdown_code_tokens |
| | `test_json_string_values_extracts_values_by_key` | 验证 _json_string_values |
| | `test_existing_paths_filters_nonexistent` | 验证 _existing_paths |
| | `test_truth_basis_for_scope_returns_global_refs` | 验证 global_refs 包含在 refs 中 |
| | `test_scope_resolver_project_runtime_root_merge` | runtime root 与 override 合并 |
| | `test_scope_resolver_get_required_canonical` | 验证 get_required_canonical |
| | `test_scope_resolver_get_global_canonical` | 验证 get_global_canonical |
| | `test_scope_resolver_project_map_refs` | 验证 project_map_refs |
| | `test_scope_resolver_refs_for_scope_combine_defaults_and_project` | 默认 + 项目 refs 合并 |
| | `test_scope_resolver_lesson_refs_for_scope` | lesson refs 合并 |
| | `test_scope_resolver_docs_refs_for_scope` | docs refs 返回 |

### 2.5 `test_business_policy_paths.py` — 路径/权限/边界测试

| 类 | 函数 | 意图 |
|---|---|---|
| `TestPathIsUnder` | 9 个测试 | 直接子目录、深层嵌套、兄弟路径、root 自身、root 父级、symlink 逃逸、symlink 内部、不存在路径、不存在外部 |
| `TestPathIsUnderLexical` | 5 个测试 | 直接子目录、symlink 词法通过、兄弟路径、~ 展开、相对 vs 绝对路径 |
| `TestTruthBasisResolverPathIsUnder` | 3 个测试 | 静态方法 _path_is_under 正/反/与模块级一致性 |
| `TestTruthBasisResolverClassify` | 18 个测试 | 对 16 种不同路径进行分类（legal-core、project-map-index、global-canonical、compatibility-only、project-canonical、docs、project-runtime、artifact、tooling、log、system、app、agents、gpt-web-to、repo-policy、workspace-entry）+ unknown 返回 "other" + 优先级测试 |
| `TestTruthBasisResolverAuthorityAllowed` | 4 个测试 | authority_allowed_paths 集合内、global_canonical 内、都不在、空配置 |
| `TestTruthBasisResolverLowerEvidence` | 5 个测试 | 第一个/第二个 evidence root 下、深层嵌套、都不在、空 roots |
| `TestScopeResolverDetermineScope` | 7 个测试 | repo 外默认、kb scope、tools scope、projects scope、workspace root 默认、repo root 默认、repo 内非 hint 默认 |
| `TestScopeResolverOverrides` | 6 个测试 | 有效 JSON、损坏 JSON、缺失文件、非 dict JSON、绝对路径覆盖、环境变量 |
| `TestPathEdgeCases` | 11 个测试 | 空路径、点路径、点点路径、Unicode 内部/外部、200 段超长路径内部/外部、遍历点名称、symlink 链保持内部、symlink 链逃逸 |
| `TestScopeResolverHelpers` | 8 个测试 | get_project_canonical 合并、get_project_runtime_root、get_required_canonical、get_global_canonical、project_map_refs 返回字符串列表、decision/lesson/docs refs |
| `TestBoundaryPaths` | 4 个测试 | 路径等于 root（通过）、词法等于 root（通过）、直接子级（通过）、父级（失败）|
| `TestTruthBasisForScopeIntegration` | 3 个测试 | 未知 scope fail、已知 scope 空文件有错误、已知 scope 返回 project_ref |

### 2.6 `test_business_policy_schema.py` — Schema 解析与验证（最大文件）

| 类 | 函数 | 意图 |
|---|---|---|
| `TestGatewayBusinessPolicyConfigSchema` | 12 个测试 | 37 字段完整性验证、实例化、policy_pack_path 可选/Path 类型、Path 字段类型、list/set/dict 字段类型、read_text_fn callable 验证、read_text_fn 被调用、default_project_scope 字符串类型、字段计数 |
| `TestHelperFunctions` | 17 个测试 | _path_is_under 正/反、_path_is_under_lexical 正/反、_section_bullets 找到/空/无标题、_section_body 返回文本/缺失标题/下一标题截断、_markdown_code_tokens 正/反、_json_string_values 单/多值、_json_object_keys、_existing_paths 过滤/全缺失 |
| `TestProjectMapValidator` | 5 个测试 | 有效内容零错误、缺失标记错误、round 引用标志、legal system contract 有效、missing refs 标志 |
| `TestLegalContractChecker` | 1 个测试 | 委托到 ProjectMapValidator |
| `TestFrozenTupleChecker` | 6 个测试 | 空文件零错误、缺失文件错误、期望标记缺失、期望标记存在零错误、遗留标记标志、多文件合并 |
| `TestEventContractChecker` | 6 个测试 | 空文件字典（KeyError 预期行为）、缺失文件错误、formal sets 不匹配标志、有效合约零错误、样本未知 source_type 标志、样本遗留字段标志 |
| `TestTruthBasisResolver` | 12 个测试 | 不支持 scope 返回 fail、有效项目 scope 解析、分类 legal-core、分类 project-map-index、缺失文件仍返回结构、sections 解析、缺失 sections 错误、未解决冲突错误、source/evidence 重叠错误、source/authority 重叠错误、authority/evidence 重叠错误 |
| `TestScopeResolver` | 21 个测试 | 无 hints 默认、hints 匹配、repo 外默认、get_project_canonical 合并/带 override、get_project_runtime_root/带 override、get_required_canonical、get_global_canonical、project_map_refs、decision refs 默认/项目特定、lesson refs 默认/项目特定、docs refs/缺失、无效 JSON 空、非 dict JSON 空、环境变量、绝对/相对覆盖路径解析 |
| `TestValidConfigVariants` | 5 个测试 | 最小配置、完整事件合约、完整 governance、项目映射、scope match hints |
| `TestEdgeCases` | 5 个测试 | 空 read_text 返回空串、空 read fn 产生错误、无配置路径空 overrides、TruthBasisResolver get_project_canonical 委托、可变默认值不共享 |

---

## 3. 共享的 Fixture 和测试工具

### 3.1 `conftest.py` 全局 fixtures

| Fixture | 作用域 | 返回值 |
|---|---|---|
| `repo_root` | function | `Path(__file__).parent.parent` 即 `/Users/busiji/memory` |
| `workspace_root` | function | `repo_root / "memory_core"` |
| `tmp_memory_root` | function | `tmp_path / ".memory"`（自动创建）|

### 3.2 各文件内部共享的 config 构建器

每个测试文件都有自己的 `_make_config` / `make_minimal_config` 函数，这是**有意为之的设计模式**：

| 文件 | 函数名 | 特点 |
|---|---|---|
| `test_business_policy_smoke.py` | `config` (fixture) | 创建完整目录树（memory/kb/global 等），使用 `_noop_read_text` |
| `test_business_policy_errors.py` | `_make_minimal_config` + `minimal_config` (fixture) | 创建最小文件集合（touch），使用 `_noop_read` |
| `test_business_policy_integration.py` | `_make_config`（非 fixture） | 使用 `_default_read_text`（读取真实文件内容）|
| `test_business_policy_paths.py` | `_make_config`（非 fixture） | 最简路径配置，使用 `_noop_read` |
| `test_business_policy_schema.py` | `make_minimal_config` + `minimal_config` (fixture) + `valid_config_with_files` (fixture) | 双 fixture 模式：最小配置 + 完整有效配置 |

### 3.3 共享的测试数据模式

- **`dataclasses.replace()`**: errors.py、integration.py、smoke.py 大量使用来创建 config 变体
- **`_noop_read`**: 所有文件都有的辅助函数，返回空字符串，用于控制测试中文件内容
- **`_file_reader`**: schema.py 中使用，读取真实文件内容
- **`unittest.mock.patch`**: integration.py 中 patch 环境变量
- **`pytest.MonkeyPatch`**: paths.py 中使用

### 3.4 导入的被测模块

所有文件均导入：
- `workspace.tools.business_policy_checks`：核心模块
  - `ProjectMapValidator`
  - `LegalContractChecker`
  - `FrozenTupleChecker`
  - `EventContractChecker`
  - `TruthBasisResolver`
  - `ScopeResolver`
  - 辅助函数：`_path_is_under`, `_path_is_under_lexical`, `_section_bullets`, `_section_body`, `_markdown_code_tokens`, `_json_string_values`, `_json_object_keys`, `_existing_paths`
- `workspace.tools.memory_hook_impls.GatewayBusinessPolicyConfig`
- `workspace.tools._validation_constants`（integration.py 和 schema.py）

---

## 4. 测试覆盖的业务场景分类

### 分类矩阵

| 业务场景 | smoke | errors | integration | paths | schema | 说明 |
|---|---|---|---|---|---|---|
| **模块可导入性** | ✅ | - | - | - | - | 冒烟测试基本保障 |
| **类实例化** | ✅ | - | - | - | ✅ | 每个类可被构造 |
| **Project Map 校验** | ✅ | ✅ | ✅ | - | ✅ | 4 文件覆盖，从冒烟到 schema |
| **Legal Contract 校验** | ✅ | - | ✅ | - | ✅ | 委托到 ProjectMapValidator |
| **Frozen Tuple 校验** | ✅ | ✅ | ✅ | - | ✅ | governance 文件标记检查 |
| **Event Contract 校验** | ✅ | ✅ | ✅ | - | ✅ | 上游标准/映射/合约一致性 |
| **Truth Basis 解析** | ✅ | ✅ | ✅ | ✅ | ✅ | Truth Basis 章节解析+冲突检测 |
| **Scope 解析** | ✅ | ✅ | ✅ | ✅ | ✅ | CWD → 项目 scope 确定 |
| **路径权限检查** | - | - | - | ✅ | ✅ | _path_is_under 系列 |
| **Scope 覆盖/override** | ✅ | - | ✅ | ✅ | ✅ | JSON 配置+环境变量 |
| **错误聚合** | - | ✅ | - | - | - | 多错误合并行为 |
| **错误消息格式** | - | ✅ | - | - | - | 一致性、路径泄露 |
| **报告结构** | - | ✅ | - | - | - | TruthBasisResolver dict 结构 |
| **Gateway 集成流程** | - | - | ✅ | - | - | 模拟 gateway 调用 |
| **多策略联合** | - | - | ✅ | - | - | 多个 checker 同时运行 |
| **回归保障** | - | - | ✅ | - | - | read_fn 调用次数、helper 验证 |
| **边界/极端输入** | ✅ | ✅ | - | ✅ | ✅ | Unicode、超长路径、空输入 |
| **Config Schema 完整性** | - | - | - | - | ✅ | 37 字段验证 |
| **Helper 函数** | ✅ | - | - | - | ✅ | 解析辅助函数单测 |
| **Symlink 安全** | - | - | - | ✅ | - | 逃逸检测 |
| **分类系统** | - | - | - | ✅ | ✅ | 16 种路径分类 |
| **Authority 权限** | - | - | - | ✅ | - | authority_allowed_paths |
| **Lower Evidence** | - | - | - | ✅ | - | evidence roots 检测 |

---

## 5. 测试之间的逻辑关系和覆盖矩阵

### 5.1 纵向分层关系（同一被测组件跨文件）

```
                smoke → errors → integration → paths → schema
                (基础)   (错误)     (集成)      (路径)   (全量)
ProjectMapValidator  ✅      ✅         ✅         -       ✅
LegalContractChecker ✅      -          ✅         -       ✅
FrozenTupleChecker   ✅      ✅         ✅         -       ✅
EventContractChecker ✅      ✅         ✅         -       ✅
TruthBasisResolver   ✅      ✅         ✅         ✅      ✅
ScopeResolver        ✅      ✅         ✅         ✅      ✅
_path_is_under       ✅      -          -          ✅      ✅
```

### 5.2 横向分工

| 文件 | 定位 | 与其他文件的关系 |
|---|---|---|
| `smoke.py` | 最小可用保障 | 确保模块、类、函数可用；所有其他文件的前提 |
| `errors.py` | 错误信息质量 | 聚焦错误消息的内容、格式、一致性；与 integration 的"正确路径"互补 |
| `integration.py` | 端到端流程 | 模拟 gateway 真实调用；使用 `_validation_constants` 常量确保一致性 |
| `paths.py` | 路径安全 | 独占覆盖 symlink、unicode、超长路径、分类系统 |
| `schema.py` | 最大覆盖 | 全量覆盖所有组件 + config schema 验证 + 多 config 变体 |

### 5.3 测试用例重叠分析

**高度重叠区域（同一用例在多个文件中出现）：**

| 用例 | 出现文件 | 差异 |
|---|---|---|
| `_path_is_under` 正/反 | smoke, paths, schema | paths 最全面（9 个 vs smoke 2 个 vs schema 2 个）|
| `_path_is_under_lexical` | smoke, paths, schema | paths 最全面（5 个 vs smoke 1 个 vs schema 2 个）|
| `TruthBasisResolver unknown scope → fail` | smoke, errors, integration, paths, schema | 所有文件都覆盖，但断言细节略有不同 |
| `ScopeResolver outside repo → default` | smoke, integration, paths, schema | 4 文件覆盖 |
| `FrozenTupleChecker missing files` | smoke, errors, integration, schema | 4 文件覆盖 |
| `ScopeResolver scope overrides (JSON)` | smoke, integration, paths, schema | paths 最全面（6 个用例）|
| `EventContractChecker missing files` | smoke, errors, integration, schema | 4 文件覆盖 |
| `_section_bullets` | smoke, integration, schema | schema 覆盖 edge case 更多 |
| `_existing_paths` | integration, schema | 轻微重叠 |
| `ProjectMapValidator empty → errors` | smoke, errors, schema | 各侧重不同断言 |

### 5.4 覆盖矩阵（组件 × 测试维度）

```
组件                    导入  实例化  正例  反例  边界  集成  错误消息  格式
ProjectMapValidator      ✅    ✅     ✅    ✅    ✅    ✅    ✅       ✅
LegalContractChecker     ✅    ✅     ✅    ✅    -     ✅    -        -
FrozenTupleChecker       ✅    ✅     ✅    ✅    ✅    ✅    ✅       ✅
EventContractChecker     ✅    ✅     ✅    ✅    ✅    ✅    ✅       ✅
TruthBasisResolver       ✅    ✅     ✅    ✅    ✅    ✅    ✅       ✅
ScopeResolver            ✅    ✅     ✅    ✅    ✅    ✅    ✅       ✅
_path_is_under           -     -      ✅    ✅    ✅    -     -        -
_path_is_under_lexical   -     -      ✅    ✅    ✅    -     -        -
_section_bullets         ✅    -      ✅    ✅    ✅    ✅    -        -
_section_body            ✅    -      ✅    ✅    ✅    ✅    -        -
_markdown_code_tokens    ✅    -      ✅    ✅    ✅    ✅    -        -
_json_string_values      ✅    -      ✅    ✅    -     ✅    -        -
_json_object_keys        ✅    -      ✅    -     -     -     -        -
_existing_paths          ✅    -      ✅    ✅    -     ✅    -        -
```

---

## 6. 发现的测试质量问题或冗余

### 6.1 高度冗余（建议合并或去重）

1. **`_path_is_under` / `_path_is_under_lexical` 过度测试**
   - smoke.py: 4 个测试
   - paths.py: 14 个测试（含边界/edge case）
   - schema.py: 4 个测试
   - integration.py: 2 个测试
   - **建议**：保留 paths.py 的完整覆盖，从 smoke.py 和 schema.py 中移除重复测试，或在 smoke.py 中仅保留"可调用"级别的冒烟验证

2. **`TruthBasisResolver truth_basis_for_scope("unknown-scope") → fail`**
   - smoke.py, errors.py, integration.py, paths.py, schema.py — 5 个文件都有
   - **建议**：保留 errors.py（测试错误消息内容）和 schema.py（测试结构），其他文件中简化为仅验证基本返回值类型

3. **`ScopeResolver determine_project_scope outside repo → default`**
   - smoke.py, integration.py, paths.py, schema.py — 4 个文件
   - **建议**：仅保留 paths.py 或 integration.py

4. **`FrozenTupleChecker missing files`**
   - smoke.py, errors.py, integration.py, schema.py — 4 个文件
   - **建议**：仅保留 errors.py（错误消息质量）

5. **`EventContractChecker missing files`**
   - smoke.py, errors.py, integration.py, schema.py — 4 个文件
   - **建议**：仅保留 errors.py

6. **`ScopeResolver scope overrides (JSON)`**
   - smoke.py, integration.py, paths.py, schema.py — 4 个文件
   - paths.py 的 6 个测试最全面，建议其他文件中简化

7. **`_section_bullets` / `_section_body`**
   - smoke.py, integration.py, schema.py — 3 个文件
   - **建议**：保留 schema.py 的覆盖即可

### 6.2 质量问题

1. **`test_business_policy_schema.py` 中 `TestEventContractChecker.test_no_errors_when_no_files`**
   - 注释承认 "empty dict leads to KeyError" — 这表明被测试代码本身存在 bug（对空字典未做防御性处理）
   - **建议**：修复上游代码或使用 `pytest.raises(KeyError)` 明确标记

2. **`test_business_policy_errors.py` 与 `test_business_policy_schema.py` 的 `TestProjectMapValidator` 测试高度重叠**
   - 两个文件都有 `test_validate_project_map_files_all_markers_present_no_errors` / `test_validate_project_map_files_no_errors_with_valid_content`
   - 数据构造方式不同但逻辑相同
   - **建议**：errors.py 应专注于错误消息内容校验，schema.py 专注于结构校验

3. **`test_business_policy_integration.py` 中 `_make_config` 和 `_default_read_text` 的模式与其他文件不一致**
   - 其他文件使用 `_noop_read`（返回空字符串），integration.py 使用 `_default_read_text`（读取真实文件）
   - **建议**：这是有意的设计（测试真实文件读取），但应在文档中注明

4. **`conftest.py` 的全局 fixtures 实际上几乎未被使用**
   - 每个文件都自建了 `_make_config` / `make_minimal_config`，没有引用 conftest 中的 fixtures
   - **建议**：如果 conftest fixtures 确实不被使用，可以移除或重构为共享 config builder

5. **缺少参数化测试**
   - 大量重复的测试用例（如 `TestTruthBasisResolverClassify` 的 18 个分类测试）可以使用 `@pytest.mark.parametrize` 简化
   - **建议**：将相似用例合并为参数化测试，减少代码行数同时保持可读性

6. **`test_business_policy_integration.py` 中 `_write_event_contract_files` 方法被 `_make_event_contract_dir` 部分重复**
   - 同一个文件中两个辅助方法做类似的事情
   - **建议**：统一为一个方法

7. **`test_business_policy_errors.py` 中 `TestNoErrorBoundary` 和 `TestProjectMapValidatorErrors.test_validate_project_map_files_all_markers_present_no_errors` 的数据完全重复**
   - **建议**：合并到一处

### 6.3 缺失覆盖

1. **缺少性能测试**：无测试验证大规模文件（如 1000 个 marker）的处理性能
2. **缺少并发安全测试**：无测试验证多线程/多进程场景
3. **缺少对 `policy_pack_path` 的端到端测试**：schema.py 仅验证了类型接受，未测试实际加载逻辑
4. **缺少国际化测试**：仅 paths.py 测试了 Unicode 路径，未测试文件内容的多语言支持

---

## 总结

这个测试体系（211 个测试用例）围绕 `business_policy_checks` 模块构建，采用**纵向分层**（smoke → errors → integration → paths → schema）和**横向分工**（每个文件聚焦不同维度）的策略。

**优点**：
- 覆盖全面，从冒烟到 schema 验证均有
- 错误消息质量有专门测试
- 路径安全测试详尽（symlink、unicode、超长路径）
- 边界/极端输入测试充分

**主要改进方向**：
- 消除约 30% 的重复测试用例
- 将 `conftest.py` 的 fixtures 实际利用起来
- 使用 `@pytest.mark.parametrize` 简化重复用例
- 修复 `EventContractChecker` 空字典 KeyError 的已知问题
