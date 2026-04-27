# A8: Test Quality 分析

> 分析日期: 2026-04-27
> 范围: `tests/` 目录下全部 19 个测试文件
> 总计: **216 个测试用例**，**3751 行测试代码**，覆盖 **14 个源模块**（4249 行）

---

## 1. 测试矩阵

| 测试文件 | 用例数 | 行数 | 覆盖模块 | 类型 |
|---|---|---|---|---|
| `test_refactoring.py` | 15 | 414 | CoreConfig, ArtifactWriter, DelegateRouter | unit |
| `test_cmux_hook_state.py` | 18 | 328 | cmux_hook_state (全部公开 API) | unit |
| `test_core_config_path.py` | 13 | 293 | memory_hook_config, memory_hook_gateway | unit |
| `test_m3_policy_pack_wiring.py` | 10 | 286 | policy pack 注入、adapter 策略解析 | unit |
| `test_api_completion.py` | 19 | 261 | memory_hook_schema, PolicyRegistry, PathUtils | unit |
| `test_m2_adapter_extraction.py` | 15 | 245 | adapter noop、state file、compaction、hook contract | unit |
| `test_policy_delegation.py` | 15 | 240 | PolicyRegistryImpl 委托、CoreConfig interface | unit |
| `test_m7_p4_gateway_integration.py` | 7 | 225 | gateway→core→system_context 全链路 | integration |
| `test_m7_p2_gateway_decoupling.py` | 11 | 204 | adapter discovery、policy class、force hook env | integration |
| `test_m3_consumer_truth_cleanup.py` | 22 | 189 | governance routing、project binding、release whitelist | property |
| `test_m7_p4_policy_pack_edge_cases.py` | 9 | 175 | policy pack loading、scope validation、conflict resolution | unit |
| `test_memory_hook_gateway_m6_batch2_adapter_policy.py` | 3 | 172 | gateway 委托到 business policy | unit |
| `test_memory_hook_core_m5_adapter_slimming.py` | 6 | 162 | gateway 组装、core status matrix | unit+integration |
| `test_m3_doc_scope_coverage.py` | 16 | 124 | 文档 frontmatter scope 声明 | property |
| `test_validate_memory_system.py` | 5 | 127 | validate_memory_system.py (subprocess) | e2e |
| `test_m7_p3_smoke.py` | 10 | 109 | build_context_package 冒烟 | smoke |
| `test_m7_independent_repo_baseline.py` | 4 | 64 | repo baseline 检查 | smoke |
| `test_memory_hook_gateway_m6_batch3_provider_switch.py` | 3 | 77 | provider switch + shadow run | unit |
| `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` | 4 | 56 | rollback drill、exit code tracking | unit |

---

## 2. 源模块覆盖率评估

### 有对应测试的模块

| 源模块 | 行数 | 测试覆盖度 | 说明 |
|---|---|---|---|
| `memory_hook_config.py` | 227 | **良好** | CoreConfig 构造、验证、factory 都有测试 |
| `memory_hook_impls.py` | 1251 | **中等** | ArtifactWriter、DelegateRouter、PolicyRegistryImpl 有测试，但 1251 行只有 ~30 个测试触达 |
| `memory_hook_core.py` | 383 | **偏弱** | 仅 6 个测试（M5 slimming），覆盖了 status matrix 和 degradation 路径 |
| `memory_hook_gateway.py` | 1028 | **中等** | 多个 integration/smoke 测试覆盖，但 1028 行的函数大部分只有间接覆盖 |
| `memory_hook_schema.py` | 74 | **良好** | convert_to_v1 有 5 个测试，覆盖主要转换逻辑 |
| `cmux_hook_state.py` | 225 | **良好** | 18 个测试，覆盖 load/write/reset/event/lock/concurrent |
| `validate_memory_system.py` | 270 | **偏弱** | 5 个 subprocess 测试，只测了健康/缺少 core 两种场景 |
| `workbot_runtime_profile.py` | 267 | **偏弱** | 仅 M2 测试中 4 个 compaction 测试触达 |
| `workbot_policy.py` | 82 | **偏弱** | 仅通过 M6 batch2 间接测试 |
| `neutral_policy.py` | 22 | **足够** | M3 rollback compatibility import 测试覆盖 |

### 缺失直接测试的模块

| 源模块 | 行数 | 状态 |
|---|---|---|
| `memory_hook_interfaces.py` | 335 | **无直接测试** — 仅作为类型被引用，无 ABC 契约验证测试 |
| `memory_hook_provider_rollback.py` | 60 | **无直接测试** — 仅 M6 batch3 间接测试 rollback drill |

---

## 3. 测试分层

| 层级 | 用例数 | 占比 | 文件数 |
|---|---|---|---|
| **Unit** | ~140 | 65% | 12 |
| **Integration** | ~50 | 23% | 4 |
| **E2E / Smoke** | ~20 | 9% | 3 |
| **Property (文档声明)** | ~16 | 7% | 2 |

**评价**: 金字塔结构合理，unit 占主导。但 integration 层偏薄 — 1028 行的 gateway 模块主要靠 7 个 integration 测试覆盖，深度不够。E2E 层只有 validate_memory_system 的 subprocess 调用，缺乏真正的全流程端到端测试。

---

## 4. 测试质量

### 强测试（断言充分、验证行为）
- `test_refactoring.py` — 对 CoreConfig 的 37 个字段逐一验证，错误路径用 `pytest.raises` 精确匹配 message
- `test_cmux_hook_state.py` — 覆盖缺失文件、corrupt JSON、非 dict 根节点、并发写、幂等往返等边界场景
- `test_m7_p4_gateway_integration.py` — 全链路测试验证 system_context 的 policy_pack、scope、schema_version 存在性
- `test_m7_p4_policy_pack_edge_cases.py` — malformed JSON、空文件、extra fields 等降级路径都有测试

### 弱测试（只检查"不报错"或存在性）
- `test_m7_p3_smoke.py` — 大部分测试只验证 `status == "ok"` 和文件存在，未检查返回内容的**结构正确性**或**语义合理性**
- `test_m7_independent_repo_baseline.py` — 4 个测试都是"文件存在/不包含某字符串"的检查，属于 baseline 检查而非行为测试
- `test_m3_doc_scope_coverage.py` — 16 个测试全是字符串包含检查（`assert "Scope: adapter" in text`），无结构解析
- `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` — 4 个测试中 3 个只验证函数不抛异常
- `test_memory_hook_gateway_m6_batch3_provider_switch.py` — 3 个测试，依赖 mock FakeBusinessPolicy，断言较浅

### 断言质量问题
- `test_m7_p3_smoke.py` 中的 `test_policy_pack_loads` 只检查 `len(policy_pack) > 0`，未验证 policy_pack 内部结构
- `test_m7_p3_smoke.py` 中的 `test_evidence_refs_present` 只检查非空列表，未验证引用路径的有效性
- `test_api_completion.py` 中的 `test_interface_matches_abc` 只检查 `isinstance`，未验证方法签名

---

## 5. 命名规范

### 好的方面
- M 系列里程碑测试 (`test_m7_p3_smoke`, `test_m7_p4_gateway_integration`) 命名清晰表达了所属里程碑和阶段
- 测试类命名遵循 `Test*` 前缀 + 功能描述
- 方法命名使用 `test_` + 动词短语，如 `test_core_config_rejects_invalid_host`

### 问题
- **命名长度不一致**: 有的简短（`test_no_missing_paths`），有的过长（`test_core_degrades_with_policy_pack_resolution_failure_without_crash`）
- **M 系列前缀混合**: `test_m7_*` 和 `test_memory_hook_core_m5_*` 命名风格不统一
- **测试方法名有时描述实现而非意图**: 如 `test_build_context_package_is_core_assembly_call` 读起来像实现细节而非行为描述
- `test_m3_doc_scope_coverage.py` 中的测试名冗余度高，如 `test_memory_system_has_adapter_scope` 和 `test_memory_system_declares_not_module_default` 可合并为参数化测试

---

## 6. 缺失场景

### 边界条件
- **CoreConfig**: 未测试 payload 为 None、空 dict、含嵌套 dict 的情况
- **ArtifactWriter**: 未测试 context_root 为只读目录、磁盘满（除了模拟 datetime 异常的 trick）、文件名冲突
- **DelegateRouter**: 未测试 payload 含非 JSON 可序列化内容、超大 payload
- **PolicyRegistryImpl**: 未测试磁盘 policy pack 目录不存在但有缓存的场景

### 异常路径
- **Gateway**: 未测试 `_discover_cwd` 在 cwd 为符号链接、不存在路径、权限不足时的行为
- **Core**: 未测试 `build_context_package_core` 在部分 validation 失败时的 partial result
- **Schema**: `memory_hook_schema.py` 只有 convert_to_v1 测试，**没有 is_v1/is_v2 验证测试**，没有 convert_to_v2（如果存在）测试
- **Provider Rollback**: 60 行模块无直接测试

### 场景覆盖
- **无并发/竞态测试**（除了 `test_cmux_hook_state.py` 中 1 个 `test_concurrent_writes_no_data_loss`）
- **无性能/回归测试** — 没有测试 build_context_package 的耗时或内存占用
- **无 subprocess 集成测试** — 所有 delegate 测试都用 MagicMock，未验证真实子进程交互
- **无 Windows 兼容性测试** — 所有路径测试假设 POSIX 语义
- **无 adapter 扩展测试** — 只有 codex/claude 两个 adapter，未测试第三方 adapter 注册流程
- **无 migration/向后兼容测试** — 没有测试旧版 context package 格式能否被正确读取

---

## 7. 改进建议

### 1. 为 `memory_hook_interfaces.py` 添加 ABC 契约验证测试
335 行的接口定义完全没有测试。应添加测试验证：
- 所有 ABC 抽象方法确实被标记为 `@abstractmethod`
- 实现类（PolicyRegistryImpl, PathUtilsImpl）通过 `isinstance` 和 `isclass` 检查
- 接口方法签名与实现一致（可用 `inspect.signature`）

### 2. 将 smoke 测试升级为结构化断言测试
`test_m7_p3_smoke.py` 的 10 个测试中 8 个只检查"存在"或"不报错"。应增加：
- 验证 `build_context_package` 返回 dict 的完整 schema（可用 `jsonschema` 或手动校验）
- 验证 `allowed_reads` 中的路径实际存在于文件系统
- 验证 `system_context` 中每个 section 的结构符合预期

### 3. 为 `memory_hook_schema.py` 补充完整测试覆盖
当前只测试了 `convert_to_v1`，缺失：
- `is_v1()` / `is_v2()` 的正/反/边界测试
- `convert_to_v1` 对非法输入的拒绝行为（非 dict、缺失必需字段）
- 如果存在 `convert_to_v2` 或 round-trip 测试也应补充

### 4. 增加参数化测试减少重复
多个测试文件中有重复的模式检查，可用 `@pytest.mark.parametrize` 收敛：
- `test_m3_doc_scope_coverage.py` 的 16 个测试可以参数化为 3-4 个参数化测试
- `test_refactoring.py` 中 CoreConfig 的多个 reject 测试可以参数化
- `test_m7_p4_policy_pack_edge_cases.py` 的 conflict resolution 测试可以参数化策略名

### 5. 增加 `memory_hook_provider_rollback.py` 直接测试
60 行的模块目前只能通过 M6 batch3 间接测试。应添加直接测试：
- `drill_rollback()` 在 legacy 可用/不可用两种场景
- rollback 脚本的实际执行（或 mock subprocess）
- 状态报告的结构验证

---

## 附录: 测试/源码比例

```
测试代码: 3751 行
源码代码: 4249 行
测试/源码比: 0.88:1

测试文件: 19
源文件:   14
用例数:   216
```

> 0.88:1 的比例在成熟项目中偏低（通常建议 1:1 到 2:1）。但考虑到大量 property 测试和 milestone smoke 测试的存在，实际有效行为测试密度可能更低。
