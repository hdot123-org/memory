# 测试体系 Part2 深度分析报告

## 1. 各测试文件测试函数数量与意图摘要

| # | 文件名 | 测试类/函数数 | 测试意图摘要 |
|---|--------|--------------|-------------|
| 1 | `test_api_completion.py` | 3类, 5方法 | 验证 `build_context_package_from_config` 与 `build_context_package_simple` 等价性、状态码、参数合法性 |
| 2 | `test_cmux_hook_state.py` | 7类, 17方法 | Hook 状态文件 I/O 全链路：路径解析、加载(宽容/严格)、写入、重置、事件记录(计数器)、锁文件、并发安全 |
| 3 | `test_config_validation.py` | 4类, 21方法 | CoreConfig `__post_init__` 校验全覆盖：Path 类型、13 个回调 callable、非空字符串、集合类型、合法构造 |
| 4 | `test_context_package_schema.py` | 6类, 18方法 | Context Package 多版本 Schema (v1/v2/memory-v1) 转换、结构验证、谓词函数、`build_context_package_simple` 集成 |
| 5 | `test_core_config_path.py` | 3类, 12方法 | Schema 转换 (v2→v1) 细节：版本、路径嵌套、上下文重命名、系统上下文移除；PathUtilsImpl 摘录/写入/ABC 一致性 |
| 6 | `test_hook_event.py` | 6类, 29方法 | HookEvent 规范化：Codex 解析、Claude 事件映射、上下文包输入转换、`parse_hook_event` 统一分发、跨主机一致性 |
| 7 | `test_m2_adapter_extraction.py` | 5类, 15方法 | M2 适配器提取：delegate noop 分流、cmux 不可用退化、state file 注入式、artifact compaction 策略、hook contract 降级 |
| 8 | `test_m3_consumer_truth_cleanup.py` | 4类, 20方法 | M3 消费者真相清理：governance/routing scope 声明、workbot.md 绑定、release whitelist、rollback 兼容性 |
| 9 | `test_m3_doc_scope_coverage.py` | 6类, 18方法 | M3 文档 scope 覆盖：6 份全局文档声明 `adapter` 级 scope，防止模块默认泄露 |
| 10 | `test_m3_policy_pack_wiring.py` | 3类, 9方法 | M3 策略包注入：PolicyRegistryImpl 加载链、适配器策略解析 (workbot vs neutral)、JSON 一致性校验 |
| 11 | `test_m7_independent_repo_baseline.py` | 4函数 | M7 基线门禁：runtime 状态 ok、无硬编码绝对路径、project-map 契约标记、PolicyRegistry 不绑定 workbot |
| 12 | `test_m7_p2_gateway_decoupling.py` | 4类, 10方法 | M7-P2 网关解耦：适配器发现常量/注册表、策略类解析、FORCE 环境变量、无硬编码 workbot 分支 |
| 13 | `test_m7_p3_smoke.py` | 1类, 9方法 | M7-P3 冒烟测试：status/missing/validation 三重 ok、INDEX 文件存在、绝对路径泄露检查、policy_pack/scope/evidence_refs |
| 14 | `test_m7_p4_gateway_integration.py` | 3类, 6方法 | M7-P4 集成测试：gateway→core→system_context 全链、registration_phase 解析、scope 验证、cwd 解析、force-hook |
| 15 | `test_m7_p4_policy_pack_edge_cases.py` | 3类, 7方法 | 策略包边界：畸形/缺失/空 JSON 静默退化、extra 字段忽略、scope 继承(声明式非合并)、冲突解决三种策略 |
| 16 | `test_memory_hook_core_m5_adapter_slimming.py` | 2类, 5方法 | M5 适配器瘦身：网关仅做组装、core 状态矩阵(ok/degraded)、policy-pack 失败不崩溃、证据引用非硬编码 |
| 17 | `test_memory_hook_gateway_m6_batch2_adapter_policy.py` | 3方法 | M6 Batch-2 网关策略：wrapper 委托到 business policy、scope-config 覆盖、scope 传递到 core |
| 18 | `test_memory_hook_gateway_m6_batch3_provider_switch.py` | 2方法 | M6 Batch-3 提供者切换：默认 legacy、external 失败回退、shadow run 双执行 |
| 19 | `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` | 4方法 | M6 Batch-3 结构：workbot policy 构建、rollback drill 通过/失败、main 退出码 |
| 20 | `test_memory_hook_interfaces.py` | 4类, 15方法 | 接口定义验证：TypedDict 完整性、ABC 不可实例化、`__abstractmethods__` 精确集合 |
| 21 | `test_memory_root_discovery.py` | 3类, 10方法 | 根目录发现：`.memory/` 标记查找(多层/最近优先/文件非目录)、workspace 子目录检测、fallback |
| 22 | `test_noop_host_delegate.py` | 4类, 10方法 | NoopHostDelegate + `resolve_host_delegate`：noop/cmux/auto 三种模式 + 未知主机退化 |
| 23 | `test_p4_adapter_toml.py` | 4类, 16方法 | adapter.toml 解析：legacy 单节/canonical 三节/默认值/dump 序列化/roundtrip/特殊字符 |
| 24 | `test_p4_default_runtime_profile.py` | 1类, 10方法 | 默认运行时 Profile：15 个键精确匹配、路径相对性、策略值、NeutralGateway 策略类、无 host 硬编码 |
| 25 | `test_p4_toolchain.py` | 6类, 24方法 | P4 工具链 (init/validate/migrate)：happy path、缺失检测、污染守卫、迁移幂等性、dry-run、版本检查、frontmatter、scope 发现、hooks.json/AGENTS.md 生成 |
| 26 | `test_policy_delegation.py` | 2类, 15方法 | PolicyRegistry 委托 + CoreConfig 接口字段：8 委托存根 + 7 接口字段 (policy_registry/path_utils/uses_interfaces) |
| 27 | `test_provider_rollback_extended.py` | 12函数 | Provider Rollback 扩展：健康系统双探针、独立探针开关、网关异常捕获、env var 行为、main 退出码、返回类型验证 |
| 28 | `test_refactoring.py` | 4类, 25方法 | 核心重构：CoreConfig 37 字段构造、ArtifactWriter JSON 写入+错误处理、DelegateRouter 路由/noop/未知主机 |
| 29 | `test_templates_packaged.py` | 1类, 5方法 | 模板打包验证：`workspace.templates` 子包可导入、模板文件通过 `importlib.resources` 可读取 |
| 30 | `test_validate_memory_system.py` | 2类, 5方法 | 系统验证脚本：健康系统返回 0 + 摘要打印 + 全部通过、破坏核心后检测失败 |

**总计：30 个文件，约 98 个测试类，350+ 个测试方法。**

---

## 2. 按模块分组的测试覆盖情况

### 2.1 Gateway 层 (Gateway 入口 & 组装)
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| `build_context_package` 入口 | `test_api_completion.py`, `test_m7_p3_smoke.py`, `test_m7_p4_gateway_integration.py`, `test_memory_hook_core_m5_adapter_slimming.py` | ✅ 全覆盖 |
| `build_context_package_simple` 简化 API | `test_api_completion.py`, `test_context_package_schema.py` | ✅ |
| `build_context_package_from_config` | `test_api_completion.py`, `test_memory_hook_core_m5_adapter_slimming.py`, `test_memory_hook_gateway_m6_batch2_adapter_policy.py` | ✅ |
| 适配器发现 & 注册表 | `test_m7_p2_gateway_decoupling.py` | ✅ |
| Force-hook 环境变量 | `test_m7_p2_gateway_decoupling.py`, `test_m7_p4_gateway_integration.py` | ✅ |
| 无硬编码 workbot 分支 | `test_m7_p2_gateway_decoupling.py`, `test_m7_independent_repo_baseline.py` | ✅ |

### 2.2 Core 层 (CoreConfig & 核心逻辑)
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| CoreConfig 构造 & `__post_init__` 校验 | `test_config_validation.py`, `test_refactoring.py` | ✅ 37 字段全覆盖 |
| CoreConfig 可选接口字段 | `test_policy_delegation.py` | ✅ |
| 核心状态矩阵 (ok/degraded) | `test_memory_hook_core_m5_adapter_slimming.py` | ✅ |
| `build_context_package_core` | `test_api_completion.py`, `test_memory_hook_core_m5_adapter_slimming.py` | ✅ |

### 2.3 Policy & Registry 层
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| PolicyRegistryImpl 抽象方法/实现 | `test_memory_hook_interfaces.py`, `test_m3_policy_pack_wiring.py`, `test_policy_delegation.py` | ✅ |
| Policy pack 加载链 (显式 > env > 默认 > 退化) | `test_m3_policy_pack_wiring.py` | ✅ |
| Policy pack 边界 (畸形/缺失/空/extra) | `test_m7_p4_policy_pack_edge_cases.py` | ✅ |
| 冲突解决策略 (fail-fast/prefer-strict/preserve-and-escalate) | `test_m7_p4_policy_pack_edge_cases.py` | ✅ |
| Scope 验证 & 继承 | `test_m7_p4_policy_pack_edge_cases.py`, `test_m7_p4_gateway_integration.py` | ✅ |
| Adapter 策略 (workbot vs neutral) | `test_m3_policy_pack_wiring.py`, `test_p4_default_runtime_profile.py` | ✅ |

### 2.4 Adapter & Delegate 层
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| CodexDelegate / ClaudeDelegate | `test_m2_adapter_extraction.py`, `test_noop_host_delegate.py` | ✅ |
| NoopHostDelegate | `test_noop_host_delegate.py`, `test_m2_adapter_extraction.py` | ✅ |
| `resolve_host_delegate` (noop/cmux/auto) | `test_noop_host_delegate.py` | ✅ |
| DelegateRouter 路由 | `test_refactoring.py` | ✅ |
| Artifact compaction | `test_m2_adapter_extraction.py` | ✅ |
| Runtime profile | `test_p4_default_runtime_profile.py` | ✅ |

### 2.5 Schema & Event 层
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| v1/v2/memory-v1 转换 | `test_context_package_schema.py`, `test_core_config_path.py` | ✅ |
| HookEvent 解析 (Codex/Claude) | `test_hook_event.py` | ✅ |
| 跨主机规范化 | `test_hook_event.py` | ✅ |

### 2.6 State & I/O 层
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| Hook state 文件 I/O | `test_cmux_hook_state.py` | ✅ |
| 并发写入安全 | `test_cmux_hook_state.py` | ✅ |
| Memory root 发现 | `test_memory_root_discovery.py` | ✅ |
| ArtifactWriter | `test_refactoring.py` | ✅ |

### 2.7 Toolchain & 文档 层
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| init/validate/migrate | `test_p4_toolchain.py` | ✅ |
| adapter.toml 解析/序列化 | `test_p4_adapter_toml.py` | ✅ |
| 文档 scope 声明 | `test_m3_doc_scope_coverage.py` | ✅ |
| 模板打包 | `test_templates_packaged.py` | ✅ |
| 系统验证脚本 | `test_validate_memory_system.py` | ✅ |

### 2.8 接口 & 契约 层
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| TypedDict 完整性 | `test_memory_hook_interfaces.py` | ✅ |
| ABC 不可实例化 | `test_memory_hook_interfaces.py` | ✅ |
| `__abstractmethods__` 精确集合 | `test_memory_hook_interfaces.py` | ✅ |

### 2.9 Rollback & Provider Switch 层
| 覆盖维度 | 文件 | 状态 |
|---------|------|------|
| Provider 切换 (legacy/external) | `test_memory_hook_gateway_m6_batch3_provider_switch.py` | ✅ |
| Rollback drill | `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py`, `test_provider_rollback_extended.py`, `test_m3_consumer_truth_cleanup.py` | ✅ |
| Shadow run | `test_memory_hook_gateway_m6_batch3_provider_switch.py` | ✅ |

---

## 3. 关键测试用例深度分析

### 3.1 边界条件测试

#### 3.1.1 并发安全 (`test_cmux_hook_state.py::TestConcurrentWrites`)
- **测试意图**: 验证 3 个线程同时写入同一 state 文件，每个线程 10 次记录，不丢数据
- **数据构造**: 3 个独立 surface，各自记录 10 次 prompt-submit 事件
- **断言逻辑**: `errors` 列表为空 + 每个 surface 的计数器精确为 10
- **评价**: 设计良好，验证了文件系统级并发安全性（基于 `path.write_text(mode='x')` 原子性）

#### 3.1.2 策略包加载边界 (`test_m7_p4_policy_pack_edge_cases.py::TestPolicyPackLoading`)
- **畸形 JSON**: `{ invalid json !!!` → 静默退化到 DEFAULT_POLICIES
- **缺失文件**: 指向不存在文件 → 不崩溃，使用默认值
- **空 JSON**: `{}` → 所有默认值保留
- **Extra 字段**: 未知键 → 不报错，忽略
- **评价**: 覆盖了所有可能的加载失败模式，确保系统鲁棒性

#### 3.1.3 冲突解决策略 (`test_m7_p4_policy_pack_edge_cases.py::TestConflictResolution`)
- **fail-fast**: 两个不同值 → `ValueError`
- **prefer-strict**: `kb_overwrite_allowed` 取 `"false"` (更严), `registration_phase` 取 `"declared-not-enforced"` (更严)
- **preserve-and-escalate**: 保留第一个值
- **评价**: 三种策略各自有明确语义和测试用例

#### 3.1.4 回调校验 (`test_config_validation.py::TestCallableTypeValidation`)
- 13 个回调字段 × 3 种非法类型 (string/None/int) = **39 个参数化测试**
- 使用 `@pytest.mark.parametrize` 高效覆盖
- **评价**: 参数化测试最佳实践，避免手动编写 39 个测试函数

#### 3.1.5 ArtifactWriter 错误处理 (`test_refactoring.py::TestArtifactWriter.test_artifact_writer_handles_write_error_gracefully`)
- 注入自定义 `datetime_module` 模拟第一次 `now()` 抛出 `OSError("disk full")`
- 断言不抛异常 + 错误写入日志文件
- **评价**: 创造性地模拟了依赖异常，验证了错误处理路径

### 3.2 异常场景测试

#### 3.2.1 Provider 降级 (`test_memory_hook_gateway_m6_batch3_provider_switch.py`)
- external-core 加载失败 → 自动回退到 legacy
- 断言：provider 变为 "legacy" + errors 包含 "fallback to legacy"
- **评价**: 关键路径，确保系统始终可用

#### 3.2.2 Policy pack 解析失败 (`test_memory_hook_core_m5_adapter_slimming.py::test_core_degrades_with_policy_pack_resolution_failure_without_crash`)
- `get_policy_pack_fn` 抛出 `RuntimeError("policy backend unavailable")`
- 断言：status = "degraded" + validation_errors 包含错误信息 + 不崩溃
- **评价**: 验证了核心逻辑在策略后端不可用时优雅降级

#### 3.2.3 Hook state 损坏 JSON (`test_cmux_hook_state.py::TestLoadHookState`)
- 宽容模式 (`load_hook_state`): 损坏 JSON → 返回默认空状态
- 严格模式 (`load_hook_state_strict`): 损坏 JSON → `HookStateError`
- **评价**: 双模式设计合理，区分了"尝试恢复"和"必须成功"两种场景

#### 3.2.4 跨主机事件映射 (`test_hook_event.py::TestFromClaudePayload`)
- `SessionStart` → `session-start`
- `UserPromptSubmit` → `prompt-submit`
- `Notification` → `notification`
- `Stop` → `stop`
- `UnknownEvent` / 缺失 event → 默认 `prompt-submit`
- **评价**: 所有 Claude 事件类型全覆盖 + 未知事件降级

### 3.3 文档/文件契约测试

#### 3.3.1 Scope 声明检查 (`test_m3_doc_scope_coverage.py`)
- 6 份文档文件逐一读取，验证包含 `Scope: adapter` 和 `不是模块默认` 声明
- JSON 策略包验证 `adapter_scope: true`
- **评价**: 确保文档层正确声明 adapter 级作用域，防止消费者误用为模块默认

#### 3.3.2 绝对路径泄露检测 (`test_m7_independent_repo_baseline.py::test_no_legacy_workbot_absolute_paths`)
- 递归扫描 `memory_core/` 下所有文件，搜索 `/Users/busiji/workbot`
- **评价**: CI 门禁级别测试，防止硬编码路径提交

---

## 4. 测试之间的关系（验证同一功能的正反面）

### 4.1 PolicyRegistryImpl 加载链

| 正向测试 | 反向/边界测试 | 关联文件 |
|---------|-------------|---------|
| `test_m3_policy_pack_wiring.py::test_config_accepts_policy_pack_path` (显式路径加载) | `test_m7_p4_policy_pack_edge_cases.py::test_missing_policy_pack_graceful_degradation` (缺失文件退化) | 同一加载链不同分支 |
| `test_m3_policy_pack_wiring.py::test_env_var_policy_pack_fallback` (环境变量回退) | `test_m7_p4_policy_pack_edge_cases.py::test_malformed_json_silent_fallback` (畸形 JSON 退化) | 同一加载链不同退化路径 |
| `test_m3_policy_pack_wiring.py::test_graceful_degradation_when_no_pack` (三重缺失) | - | 最终退化兜底 |

### 4.2 CoreConfig 校验

| 正向测试 | 反向测试 | 关联文件 |
|---------|---------|---------|
| `test_refactoring.py::test_core_config_constructs_with_all_fields` (合法构造) | `test_config_validation.py::TestPathTypeValidation` (Path 类型拒绝) | 同类型正反面 |
| `test_refactoring.py::test_core_config_from_gateway_kwargs` (工厂方法) | `test_config_validation.py::TestCallableTypeValidation` (callable 类型拒绝) | 同类型正反面 |
| `test_refactoring.py::test_core_config_accepts_claude_host` | `test_refactoring.py::test_core_config_rejects_invalid_host` | 合法/非法 host |

### 4.3 Delegate 路由

| 正向 | 退化 | 关联文件 |
|------|------|---------|
| `test_noop_host_delegate.py::TestResolveCmuxMode` (cmux 模式路由) | `test_noop_host_delegate.py::TestResolveAutoMode` (cmux 不可用时 auto 退化) | 同一路由函数 |
| `test_refactoring.py::test_delegate_router_routes_to_codex` | `test_refactoring.py::test_delegate_router_rejects_unknown_host` | 正常/异常 |
| `test_m2_adapter_extraction.py::test_codex_delegate_noop_returns_empty_json` | `test_m2_adapter_extraction.py::test_codex_execute_no_cmux_returns_noop` | 正常执行/退化 noop |

### 4.4 Provider 切换 & Rollback

| 场景 | 文件 |
|------|------|
| 正常切换 (legacy → legacy) | `test_memory_hook_gateway_m6_batch3_provider_switch.py::test_resolve_core_builder_defaults_to_legacy` |
| 切换失败回退 | `test_memory_hook_gateway_m6_batch3_provider_switch.py::test_resolve_core_builder_fallbacks_to_legacy_when_external_load_fails` |
| Rollback drill 通过 | `test_provider_rollback_extended.py::test_healthy_system_both_probes_pass` |
| Rollback drill 失败 | `test_provider_rollback_extended.py::test_legacy_probe_fails_status_failed` |
| 双探针异常 | `test_provider_rollback_extended.py::test_both_resolve_raises` |

### 4.5 Schema 转换链

| 转换方向 | 文件 |
|---------|------|
| v2 → v1 | `test_core_config_path.py::TestSchemaConversion` |
| v2 → memory-v1 | `test_context_package_schema.py::TestV2ToMemoryV1` |
| v1 → memory-v1 | `test_context_package_schema.py::TestV1ToMemoryV1` |
| memory-v1 → memory-v1 (恒等) | `test_context_package_schema.py::TestMemoryV1Identity` |

---

## 5. 测试质量评估

### 5.1 优点

1. **边界覆盖全面**: 策略包加载覆盖了显式路径 → 环境变量 → 默认路径 → 不存在文件 → 空文件 → 畸形 JSON 的完整退化链
2. **参数化高效**: `test_config_validation.py` 使用 `@pytest.mark.parametrize` 将 13 字段 × 3 类型压缩为少量测试函数
3. **并发测试**: `test_cmux_hook_state.py` 的并发写入测试使用了真实的多线程 + 计数器验证
4. **接口契约验证**: `test_memory_hook_interfaces.py` 精确验证了每个 ABC 的 `__abstractmethods__` 集合
5. **文档即测试**: 大量文档文件 scope 声明测试确保文档与代码约定一致
6. **工具链端到端**: `test_p4_toolchain.py` 覆盖 init→validate→migrate 完整生命周期
7. **monkeypatch 使用成熟**: `test_m7_p2_gateway_decoupling.py` 中 `_reload_gateway` 函数通过清 `sys.modules` + 重加载实现环境变量隔离
8. **错误处理路径**: ArtifactWriter 自定义 datetime 模拟 + Policy pack 解析异常捕获

### 5.2 改进建议

1. **缺少 fixture 重用**: 多个文件各自定义了 `_make_minimal_kwargs` 类似函数（`test_config_validation.py`, `test_api_completion.py`, `test_memory_hook_core_m5_adapter_slimming.py`, `test_policy_delegation.py`, `test_refactoring.py`），建议提取到 `conftest.py`
2. **缺少负向断言粒度**: 部分测试只断言 `isinstance(result, list)` 但不验证列表为空或内容，如 `test_policy_delegation.py::test_validate_project_map_returns_list`
3. **硬编码路径扫描**: `test_m7_p3_smoke.py` 和 `test_m7_independent_repo_baseline.py` 都做 `/Users/busiji` 路径扫描，存在重叠
4. **测试文件命名不一致**: 部分使用 `test_m2_` 前缀、部分用 `test_memory_hook_` 前缀，建议统一
5. **`test_m3_policy_pack_wiring.py` 注释提到 dataclass 字段顺序 bug**：该注释说明测试针对"预期最终形状"，若字段 bug 未修复，测试可能在当前代码下失败
6. **部分测试跳过逻辑**: `test_m3_policy_pack_wiring.py` 中有 `pytest.skip("workbot-policy-pack.json not present")`，建议在 CI 环境中确保这些文件始终存在
7. **`test_p4_toolchain.py` 使用 `shutil.rmtree` 但 import 在 finally 块内部**：应提前 import，避免 finally 块中 `ImportError` 影响清理

### 5.3 覆盖缺口

| 模块 | 可能缺失的测试 | 风险等级 |
|------|--------------|---------|
| `build_context_package_core` 的 `truth_basis_for_scope` 集成 | 仅验证返回值结构，未验证实际 truth basis 逻辑 | 中 |
| `event_contract_blocker_errors` | 只在委托/接口测试中作为存根，未见真实 blocker 场景 | 中 |
| `governance_frozen_tuple_errors` | 同上，仅验证空列表返回值 | 中 |
| 多 scope 场景 | 主要围绕 `workbot` scope，缺少多 scope 交叉测试 | 低 |
| `registration_commit` enforced 场景 | `test_memory_hook_core_m5_adapter_slimming.py` 有一例，但未见 `enforced` 下成功提交的完整流程 | 中 |

### 5.4 总体评分

| 维度 | 评分 (1-5) | 说明 |
|------|-----------|------|
| 功能覆盖率 | 4.5 | 核心模块覆盖全面，少量治理逻辑缺真实场景测试 |
| 边界条件覆盖 | 4.5 | 策略包、并发、错误处理等边界覆盖优秀 |
| 测试代码质量 | 4.0 | 参数化使用良好，但 fixture 重复较多 |
| 可维护性 | 3.5 | 命名不一致、helper 分散、部分文件有路径耦合 |
| 集成测试深度 | 4.0 | 端到端链路测试存在但数量偏少 |

---

*报告生成时间: 2026-05-01*
