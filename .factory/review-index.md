# Code Review Index

> 生成时间: 2026-05-01 | 分支: branch-1 | 最新 commit: a5f943b

---

## 统计概览

| 分类 | 文件数 | 总行数 |
|------|--------|--------|
| 核心源码 (memory_core/tools/) | 23 | 7,345 |
| 测试代码 (tests/) | 32 | 11,138 |
| 其他源码 (workspace/) | 2 | 297 |
| **总计** | **57** | **18,780** |

---

## 文件清单

| 文件 | 行数 | 分组 | 关键类/函数数 |
|------|------|------|---------------|
| `memory_core/tools/__init__.py` | 25 | 核心层 | 1 函数 |
| `memory_core/tools/_validation_constants.py` | 76 | 配置层 | 0 类/函数 (常量) |
| `memory_core/tools/adapter_toml_schema.py` | 137 | 配置层 | 1 类, 4 函数 |
| `memory_core/tools/business_policy_checks.py` | 677 | 策略层 | 6 类, 8 函数 |
| `memory_core/tools/cmux_hook_state.py` | 216 | 核心层 | 1 类, 12 函数 |
| `memory_core/tools/hook_event.py` | 192 | 核心层 | 1 类, 7 函数 |
| `memory_core/tools/init_project_memory.py` | 630 | CLI层 | 17 函数 |
| `memory_core/tools/memory_hook_adapters/__init__.py` | 0 | 策略层 | - |
| `memory_core/tools/memory_hook_adapters/default_runtime_profile.py` | 118 | 策略层 | 1 函数 |
| `memory_core/tools/memory_hook_adapters/neutral_policy.py` | 25 | 策略层 | 1 类 |
| `memory_core/tools/memory_hook_adapters/workbot_policy.py` | 82 | 策略层 | 1 类 |
| `memory_core/tools/memory_hook_adapters/workbot_runtime_profile.py` | 267 | 策略层 | 1 函数 |
| `memory_core/tools/memory_hook_config.py` | 273 | 配置层 | 1 类 |
| `memory_core/tools/memory_hook_core.py` | 383 | 核心层 | 4 函数 |
| `memory_core/tools/memory_hook_gateway.py` | 1,037 | 网关层 | 63 函数 |
| `memory_core/tools/memory_hook_impls.py` | 1,332 | 实现层 | 13 类, 1 函数 |
| `memory_core/tools/memory_hook_interfaces.py` | 380 | 接口层 | 13 类 |
| `memory_core/tools/memory_hook_provider_probe.py` | 75 | 网关层 | 2 函数 |
| `memory_core/tools/memory_hook_provider_rollback.py` | 60 | 网关层 | 2 函数 |
| `memory_core/tools/memory_hook_schema.py` | 169 | 配置层 | 6 函数 |
| `memory_core/tools/memory_root_discovery.py` | 47 | 核心层 | 3 函数 |
| `memory_core/tools/migrate_project_memory.py` | 421 | CLI层 | 6 函数 |
| `memory_core/tools/validate_memory_system.py` | 269 | CLI层 | 1 类, 7 函数 |
| `memory_core/tools/validate_project_memory.py` | 454 | CLI层 | 1 类, 11 函数 |
| `memory_core/__init__.py` | 0 | 核心层 | - |

---

## 模块依赖图（ASCII）

```
                    ┌─────────────────────────────┐
                    │    memory_hook_interfaces    │  ← 接口层 (ABC/Protocol)
                    │  (13 个抽象类 + TypedDict)    │
                    └─────────────┬───────────────┘
                                  │ implements
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌───────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  memory_hook_impls │  │  memory_hook_config  │  │ business_policy_   │
│  (13 个实现类)     │  │  (CoreConfig)        │  │ checks (6 类)       │
└────────┬──────────┘  └──────────┬───────────┘  └──────────┬──────────┘
         │                        │                         │
         └────────────┬───────────┘─────────────────────────┘
                      │ uses
                      ▼
            ┌─────────────────────┐
            │ memory_hook_gateway │  ← 网关层 (63 函数, 1,037 行)
            │   (核心编排)         │
            └────────┬────────────┘
                     │ calls / lazy-imports
     ┌───────────────┼───────────────┬───────────────┐
     │               │               │               │
     ▼               ▼               ▼               ▼
┌─────────────┐ ┌──────────┐ ┌────────────┐ ┌───────────────┐
│ hook_event   │ │ cmux_    │ │memory_root_│ │ adapters/     │
│ (HookEvent) │ │ hook_state│ │ discovery  │ │ (policy/      │
└─────────────┘ └──────────┘ └────────────┘ └───────────────┘
     │               │               │
     ▼               ▼               ▼
┌─────────────┐ ┌──────────┐ ┌────────────┐
│ _validation │ │ adapter  │ │  schema     │
│ _constants   │ │ _toml    │ │  (版本转换) │
└─────────────┘ └──────────┘ └────────────┘

                    ┌─────────────────────┐
                    │  memory_hook_core    │  ← 核心层 (context package 构建)
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
     ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
     │ init_project│  │ migrate_     │  │ validate_    │
     │ _memory     │  │ project_     │  │ project_     │
     │  (CLI)      │  │ memory (CLI) │  │ memory (CLI) │
     └─────────────┘  └──────────────┘  └──────────────┘
              │
              ▼
     ┌─────────────────────┐
     │ memory_hook_provider│  ← 运维工具
     │ _probe / _rollback  │
     └─────────────────────┘

tests/ (32 个文件) ────────────▶ 覆盖上述所有模块

```

---

## 各文件详情

### memory_core/tools/__init__.py
- **行数**: 25 | **分组**: 核心层
- **函数**: `__getattr__` (L12) — 延迟导出公共 API
- **imports**: `__future__.annotations`
- **导出**: `build_context_package` (from gateway), `build_context_package_simple` (from gateway), `CoreConfig` (from config), `build_context_package_from_config` (from core)
- **被引用**: `test_api_completion.py` (测试 public API)

### memory_core/tools/_validation_constants.py
- **行数**: 76 | **分组**: 配置层
- **类/函数**: 0 (纯常量模块)
- **imports**: `__future__.annotations`
- **被引用**: 由 `business_policy_checks.py`、`memory_hook_gateway.py` 等导入常量

### memory_core/tools/adapter_toml_schema.py
- **行数**: 137 | **分组**: 配置层
- **类**: `AdapterConfig` (L13)
- **函数**: `_toml_str` (L35), `_has_new_sections` (L41), `load_adapter_toml` (L49), `_load_new_format` (L81), `dump_adapter_toml` (L100)
- **imports**: `dataclasses`, `pathlib.Path`, `typing.Any`, `tomllib`
- **被引用**: `test_p4_adapter_toml.py`, `default_runtime_profile.py` (lazy import)

### memory_core/tools/business_policy_checks.py
- **行数**: 677 | **分组**: 策略层
- **类**: `ProjectMapValidator` (L145), `LegalContractChecker` (L240), `FrozenTupleChecker` (L256), `EventContractChecker` (L293), `TruthBasisResolver` (L405), `ScopeResolver` (L586)
- **函数**: `_path_is_under` (L74), `_path_is_under_lexical` (L82), `_section_bullets` (L91), `_section_body` (L107), `_markdown_code_tokens` (L124), `_json_string_values` (L128), `_json_object_keys` (L133), `_existing_paths` (L137)
- **imports**: `json`, `os`, `re`, `pathlib.Path`, `typing.Any`
- **被引用**: `test_business_policy_*.py` (多个测试文件), `memory_hook_impls.py` (通过 PolicyRegistryImpl 集成)

### memory_core/tools/cmux_hook_state.py
- **行数**: 216 | **分组**: 核心层
- **类**: `HookStateError` (L13)
- **函数**: `_hook_state_lock_path` (L17), `_exclusive_hook_state_lock` (L23), `runtime_state_dir` (L34), `default_hook_state_path` (L42), `default_assignment_file_path` (L46), `default_pm_bot_watch_assignment_file_path` (L50), `default_codex_main_task_path` (L54), `default_project_overview_json_path` (L58), `default_project_overview_text_path` (L62), `default_assignment_watcher_pid_path` (L66), `default_assignment_watcher_log_path` (L70), `_base_payload` (L74), `reset_hook_state` (L82), `load_hook_state` (L89), `load_hook_state_strict` (L105), `_write_hook_state_unlocked` (L121), `write_hook_state` (L143), `get_surface_hook_state` (L149), `_default_surface_state` (L160), `record_hook_event` (L176)
- **imports**: `fcntl`, `json`, `os`, `tempfile`, `contextlib.contextmanager`, `datetime`, `pathlib.Path`
- **被引用**: `test_cmux_hook_state.py`

### memory_core/tools/hook_event.py
- **行数**: 192 | **分组**: 核心层
- **类**: `HookEvent` (L46) — dataclass
- **函数**: `_now_iso` (L61), `_parse_json` (L65), `_extract_cwd` (L76), `_map_claude_event` (L84), `_is_valid_event_type` (L89), `from_codex_payload` (L97), `from_claude_payload` (L121), `to_context_package_input` (L152), `parse_hook_event` (L172)
- **imports**: `json`, `dataclasses.dataclass`, `datetime`, `pathlib.Path`, `typing.Any`
- **被引用**: `test_hook_event.py`, `memory_hook_gateway.py`

### memory_core/tools/init_project_memory.py
- **行数**: 630 | **分组**: CLI层
- **函数**: `_now_iso` (L60), `_slug` (L64), `_project_name` (L69), `template_memory_lock` (L103), `template_adapter_toml` (L120), `template_canonical_md` (L150), `template_plan_md` (L192), `template_state_md` (L216), `template_tasks_md` (L241), `template_migrations_log` (L260), `template_keep` (L289), `template_hooks_json` (L299), `generate_hooks_json` (L311), `template_agents_md_block` (L358), `update_agents_md` (L372), `init_project_memory` (L432), `_find_repo_root` (L526), `_is_memory_repo` (L536), `main` (L549)
- **imports**: `argparse`, `importlib.metadata`, `json`, `sys`, `datetime`, `pathlib.Path`, `typing.Any`
- **入口**: `memory-init` (pyproject.toml scripts)
- **被引用**: 无 (独立 CLI)

### memory_core/tools/memory_hook_adapters/__init__.py
- **行数**: 0 | **分组**: 策略层
- **imports**: 无
- **被引用**: 无 (命名空间包)

### memory_core/tools/memory_hook_adapters/default_runtime_profile.py
- **行数**: 118 | **分组**: 策略层
- **函数**: `build_default_runtime_profile` (L26)
- **imports**: `pathlib.Path`, `typing.Any`, `.adapter_toml_schema.load_adapter_toml` (lazy import)
- **被引用**: `test_p4_default_runtime_profile.py`, `test_m2_adapter_extraction.py`, `test_m3_consumer_truth_cleanup.py`, `test_m3_policy_pack_wiring.py`, `memory_hook_gateway.py` (lazy import)

### memory_core/tools/memory_hook_adapters/neutral_policy.py
- **行数**: 25 | **分组**: 策略层
- **类**: `NeutralGatewayBusinessPolicy` (L17) — 继承 `GatewayBusinessPolicyImpl`
- **imports**: `pathlib.Path`, `.memory_hook_impls` (lazy: GatewayBusinessPolicyConfig, GatewayBusinessPolicyImpl, PolicyRegistryImpl)
- **被引用**: `test_m3_consumer_truth_cleanup.py`, `workbot_policy.py`

### memory_core/tools/memory_hook_adapters/workbot_policy.py
- **行数**: 82 | **分组**: 策略层
- **类**: `WorkbotGatewayBusinessPolicy` (L26) — 继承 `NeutralGatewayBusinessPolicy`
- **imports**: `json`, `os`, `pathlib.Path`, `typing.Any`, `.neutral_policy`, `.memory_hook_impls`
- **被引用**: `test_m7_p2_gateway_decoupling.py`, `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py`, `workbot_runtime_profile.py`

### memory_core/tools/memory_hook_adapters/workbot_runtime_profile.py
- **行数**: 267 | **分组**: 策略层
- **函数**: `build_workbot_runtime_profile` (L13)
- **imports**: `os`, `pathlib.Path`, `typing.Any`, `.workbot_policy.WorkbotGatewayBusinessPolicy`
- **被引用**: `test_m2_adapter_extraction.py`, `test_m3_consumer_truth_cleanup.py`, `test_m3_policy_pack_wiring.py`, `memory_hook_gateway.py` (lazy import)

### memory_core/tools/memory_hook_config.py
- **行数**: 273 | **分组**: 配置层
- **类**: `CoreConfig` (L17) — dataclass
- **imports**: `dataclasses`, `pathlib.Path`, `typing` (TYPE_CHECKING, Any, Callable, Collection)
- **被引用**: `test_refactoring.py`, `test_policy_delegation.py`, `test_config_validation.py`, `test_core_config_path.py`, `test_api_completion.py`, `__init__.py` (公开 API), `memory_hook_core.py`

### memory_core/tools/memory_hook_core.py
- **行数**: 383 | **分组**: 核心层
- **函数**: `_resolve_callbacks` (L14), `registration_phase_from_policy_pack` (L74), `evaluate_registration_commit_gate` (L90), `build_context_package_core` (L129), `build_context_package_from_config` (L338)
- **imports**: `pathlib.Path`, `typing.Any`, `typing.Callable`, `typing.Collection`
- **被引用**: `test_memory_hook_core_m5_adapter_slimming.py`, `test_core_config_path.py`, `test_m7_p4_gateway_integration.py`, `__init__.py` (公开 API)

### memory_core/tools/memory_hook_gateway.py
- **行数**: 1,037 | **分组**: 网关层
- **类**: 0 (纯函数模块)
- **函数**: 63 个 (详见下方关键函数)
  - **入口**: `main` (L954), `build_context_package` (L757), `build_context_package_simple` (L843)
  - **路由策略**: `resolve_route_target` (L713), `_resolve_route_target_via_policy` (L256)
  - **数据写入**: `write_artifacts` (L891), `write_targets` (L688), `_write_targets_via_policy` (L261)
  - **宿主委派**: `_delegate_codex` (L946), `_delegate_claude` (L950)
  - **验证**: `validate_project_map_files` (L664), `validate_unique_legal_system_contract` (L668)
  - **Truth Basis**: `truth_basis_for_scope` (L684), `decision_refs_for_scope` (L672), `lesson_refs_for_scope` (L676), `docs_refs_for_scope` (L680)
  - **Governance**: `governance_frozen_tuple_blocker_errors` (L441), `event_contract_blocker_errors` (L445)
  - **辅助**: `determine_project_scope` (L377), `_parse_args` (L301), `now_iso` (L309), `project_map_refs` (L654), `read_text_if_exists` (L658)
  - **Provider**: `_resolve_core_builder` (L201), `load_adapter_config` (L104)
  - **Sink/Delegate**: `_write_artifacts_via_sink` (L280), `_append_error_log_via_sink` (L285), `_execute_delegate_via_facade` (L290), `_get_host_delegate` (L250)
  - **Policy**: `_get_policy_registry` (L212), `_get_route_policy` (L223), `_get_write_policy` (L235), `_get_artifact_sink` (L242), `_get_error_sink` (L246), `_get_gateway_business_policy` (L182), `_get_policy_pack_via_registry` (L266), `_resolve_policy_conflict_via_registry` (L271)
  - **内部工具**: `_path_is_under` (L449), `_classify_truth_ref` (L457), `_authority_ref_allowed` (L493), `_lower_evidence_ref` (L497), `_truth_basis_sections_for` (L501), `_truth_basis_errors_for` (L511), `_existing_paths` (L557), `_normalize_repo_scope_entry` (L561), `_registration_payload_paths` (L569), `_git_name_only` (L585), `_path_matches_scope` (L597), `_git_registration_probe` (L602), `_apply_artifact_compaction` (L738), `_ensure_artifact_dirs` (L872), `append_error_log` (L880), `_require_env` (L917), `_canonicalize_cmux_refs` (L924)
- **imports**: `argparse`, `json`, `os`, `re`, `subprocess`, `sys`, `datetime`, `pathlib.Path`, `typing.Any`, `typing.Callable`, `importlib` (延迟导入), 懒加载: `memory_root_discovery`, `workbot_runtime_profile`
- **被引用**: `memory_hook_provider_probe.py`, `memory_hook_provider_rollback.py`, `__init__.py`, 多个测试文件

### memory_core/tools/memory_hook_impls.py
- **行数**: 1,332 | **分组**: 实现层
- **类**: 
  - `CodexDelegate` (L90) — 继承 `HostDelegate`
  - `ClaudeDelegate` (L130) — 继承 `HostDelegate`
  - `NoopHostDelegate` (L225) — 继承 `HostDelegate`
  - `PolicyRegistryImpl` (L273) — 继承 `PolicyRegistry`
  - `RouteTargetPolicyImpl` (L486) — 继承 `RouteTargetPolicy`
  - `WriteTargetPolicyImpl` (L517) — 继承 `WriteTargetPolicy`
  - `GatewayBusinessPolicyConfig` (L554) — dataclass
  - `GatewayBusinessPolicyImpl` (L596) — 继承 `GatewayBusinessPolicy`
  - `ArtifactSinkImpl` (L1112) — 继承 `ArtifactSink`
  - `ErrorSinkImpl` (L1153) — 继承 `ErrorSink`
  - `ArtifactWriter` (L1175)
  - `DelegateRouter` (L1235)
  - `PathUtilsImpl` (L1285) — 继承 `PathUtils`
- **函数**: `resolve_host_delegate` (L243)
- **imports**: `json`, `os`, `re`, `shutil`, `subprocess`, `dataclasses`, `datetime`, `pathlib.Path`, `typing`
- **被引用**: `test_refactoring.py`, `test_m2_adapter_extraction.py`, `test_policy_delegation.py`, `test_memory_hook_interfaces.py`, `test_noop_host_delegate.py`, `test_m3_consumer_truth_cleanup.py`, `test_m7_independent_repo_baseline.py`, `test_api_completion.py`, `test_m3_policy_pack_wiring.py`, `test_m7_p4_gateway_integration.py`, `neutral_policy.py`, `workbot_policy.py`

### memory_core/tools/memory_hook_interfaces.py
- **行数**: 380 | **分组**: 接口层
- **类**: 
  - `TruthBasis` (L22) — TypedDict
  - `RegistrationCommitGate` (L36) — TypedDict
  - `HostDelegate` (L50) — ABC
  - `PolicyRegistry` (L85) — ABC
  - `PolicyQueryProvider` (L183) — Protocol
  - `GovernanceChecker` (L197) — Protocol
  - `TruthBasisProvider` (L211) — Protocol
  - `RouteTargetPolicy` (L226) — ABC
  - `WriteTargetPolicy` (L239) — ABC
  - `GatewayBusinessPolicy` (L252) — ABC
  - `ArtifactSink` (L338) — ABC
  - `ErrorSink` (L356) — ABC
  - `PathUtils` (L369) — ABC
- **imports**: `subprocess`, `abc.ABC`, `abc.abstractmethod`, `pathlib.Path`, `typing` (Any, Protocol, TypedDict)
- **被引用**: `test_memory_hook_interfaces.py`, `test_policy_delegation.py`, `test_api_completion.py`

### memory_core/tools/memory_hook_provider_probe.py
- **行数**: 75 | **分组**: 网关层
- **函数**: `probe_provider_availability` (L27), `main` (L68)
- **imports**: `json`, `os`, `sys`, `pathlib.Path`, `typing.Any`, `memory_hook_gateway` (as gateway)
- **被引用**: 无

### memory_core/tools/memory_hook_provider_rollback.py
- **行数**: 60 | **分组**: 网关层
- **函数**: `run_rollback_drill` (L23), `main` (L53)
- **imports**: `json`, `os`, `sys`, `pathlib.Path`, `typing.Any`, `memory_hook_gateway` (as gateway)
- **被引用**: `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py`, `test_provider_rollback_extended.py`

### memory_core/tools/memory_hook_schema.py
- **行数**: 169 | **分组**: 配置层
- **函数**: `convert_to_v1` (L30), `is_v1` (L67), `is_v2` (L72), `convert_to_memory_v1` (L91), `convert_legacy_to_memory_v1` (L129), `_convert_v1_to_memory_v1` (L143), `is_memory_v1` (L167)
- **imports**: `typing.Any`
- **被引用**: `test_context_package_schema.py`, `test_api_completion.py`, `test_core_config_path.py`, `validate_memory_system.py`

### memory_core/tools/memory_root_discovery.py
- **行数**: 47 | **分组**: 核心层
- **函数**: `discover_project_root` (L19), `discover_workspace_root` (L37), `discover_roots` (L43)
- **imports**: `pathlib.Path`
- **被引用**: `test_memory_root_discovery.py`, `memory_hook_gateway.py` (lazy import)

### memory_core/tools/migrate_project_memory.py
- **行数**: 421 | **分组**: CLI层
- **函数**: `migrate_v010_to_v020` (L47), `discover_migrations` (L107), `append_migration_log` (L155), `plan_rollback` (L188), `migrate_project_memory` (L209), `main` (L327)
- **imports**: `argparse`, `importlib.metadata`, `json`, `sys`, `datetime`, `pathlib.Path`, `typing.Any`, `typing.Callable`
- **入口**: `memory-migrate` (pyproject.toml scripts)
- **被引用**: 无 (独立 CLI)

### memory_core/tools/validate_memory_system.py
- **行数**: 269 | **分组**: CLI层
- **类**: `ValidateResult` (L48)
- **函数**: `_empty_truth_basis` (L33), `check_gateway_import` (L80), `check_core_builder_resolve` (L91), `check_context_package` (L109), `check_core_config_path` (L194), `check_v1_schema` (L208), `check_package_imports` (L242), `main` (L242)
- **imports**: `sys`, `pathlib.Path`, `typing.Any`
- **被引用**: `test_validate_memory_system.py`

### memory_core/tools/validate_project_memory.py
- **行数**: 454 | **分组**: CLI层
- **类**: `CheckResult` (L177)
- **函数**: `_parse_frontmatter` (L81), `_is_json_like` (L102), `_parse_lock_file` (L108), `_parse_adapter_toml` (L125), `_check_pollution` (L147), `check_required_files` (L221), `check_required_dirs` (L234), `check_frontmatter` (L247), `check_lock_version` (L266), `check_adapter_version` (L295), `check_pollution` (L324), `check_migrations_log` (L335), `validate_project_memory` (L359), `main` (L411)
- **imports**: `argparse`, `importlib.metadata`, `json`, `re`, `sys`, `pathlib.Path`, `typing.Any`
- **入口**: `memory-validate` (pyproject.toml scripts)
- **被引用**: `test_validate_memory_system.py`

### memory_core/__init__.py
- **行数**: 0 | **分组**: 核心层
- **内容**: 空文件 (命名空间包)

---

## 测试文件清单

| 文件 | 行数 | 对应模块 |
|------|------|----------|
| `tests/conftest.py` | 23 | 通用 fixtures |
| `tests/test_api_completion.py` | 259 | 公开 API 可达性 |
| `tests/test_business_policy_errors.py` | 805 | 策略层错误处理 |
| `tests/test_business_policy_integration.py` | 1,028 | 策略层集成测试 |
| `tests/test_business_policy_paths.py` | 857 | 策略路径验证 |
| `tests/test_business_policy_schema.py` | 1,311 | 策略 schema 验证 |
| `tests/test_business_policy_smoke.py` | 666 | 策略冒烟测试 |
| `tests/test_cmux_hook_state.py` | 327 | cmux hook 状态管理 |
| `tests/test_config_validation.py` | 281 | CoreConfig 验证 |
| `tests/test_context_package_schema.py` | 244 | Schema 版本转换 |
| `tests/test_core_config_path.py` | 289 | 核心配置路径测试 |
| `tests/test_hook_event.py` | 360 | HookEvent 解析 |
| `tests/test_m2_adapter_extraction.py` | 282 | M2 适配器提取 |
| `tests/test_m3_consumer_truth_cleanup.py` | 187 | M3 消费者清理 |
| `tests/test_m3_doc_scope_coverage.py` | 122 | M3 文档覆盖 |
| `tests/test_m3_policy_pack_wiring.py` | 285 | M3 策略包连线 |
| `tests/test_m7_independent_repo_baseline.py` | 64 | M7 独立仓库基线 |
| `tests/test_m7_p2_gateway_decoupling.py` | 204 | M7 P2 网关解耦 |
| `tests/test_m7_p3_smoke.py` | 107 | M7 P3 冒烟 |
| `tests/test_m7_p4_gateway_integration.py` | 223 | M7 P4 网关集成 |
| `tests/test_m7_p4_policy_pack_edge_cases.py` | 175 | M7 P4 策略边界 |
| `tests/test_memory_hook_core_m5_adapter_slimming.py` | 162 | M5 适配器瘦身 |
| `tests/test_memory_hook_gateway_m6_batch2_adapter_policy.py` | 172 | M6 网关适配器策略 |
| `tests/test_memory_hook_gateway_m6_batch3_provider_switch.py` | 77 | M6 Provider 切换 |
| `tests/test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` | 56 | M6 结构与回滚 |
| `tests/test_memory_hook_interfaces.py` | 187 | 接口层测试 |
| `tests/test_memory_root_discovery.py` | 113 | 根目录发现 |
| `tests/test_noop_host_delegate.py` | 95 | Noop 宿主代理 |
| `tests/test_p4_adapter_toml.py` | 237 | P4 适配器 TOML |
| `tests/test_p4_default_runtime_profile.py` | 133 | P4 默认运行时配置 |
| `tests/test_p4_toolchain.py` | 690 | P4 工具链 |
| `tests/test_policy_delegation.py` | 239 | 策略委托 |
| `tests/test_provider_rollback_extended.py` | 301 | Provider 回滚扩展 |
| `tests/test_refactoring.py` | 413 | 重构验证 |
| `tests/test_templates_packaged.py` | 37 | 模板打包 |
| `tests/test_validate_memory_system.py` | 127 | 系统验证 |

---

## 根目录配置文件

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | 构建配置: setuptools, 项目元数据, entry points (memory-init/migrate/validate), pytest/ruff 配置 |
| `ruff.toml` | Ruff linter 配置: py39, 120 行限制, E/F/W/I 规则 |
| `.gitignore` | Git 忽略规则 |
| `.github/workflows/ci.yml` | GitHub Actions CI 配置 |
| `MANIFEST.in` | 打包清单 |
| `.github/` | GitHub 配置目录 |

---

## 入口点 (CLI commands)

| 命令 | 模块 | 入口函数 |
|------|------|----------|
| `memory-init` | `init_project_memory.py` | `main()` |
| `memory-migrate` | `migrate_project_memory.py` | `main()` |
| `memory-validate` | `validate_project_memory.py` | `main()` |
