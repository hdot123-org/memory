# 业务策略与适配器深度分析报告

## 1. Policy Check 详细分析

### 1.1 ProjectMapValidator — Project-Map 合约校验

**文件**: `business_policy_checks.py` (第 97-177 行)

#### validate_project_map_files() — 校验 project-map 合约文件

**检查内容**: 验证 4 个关键文件（INDEX.md、legal-core-map.md、ingestion-registry-map.md、governance）是否包含必需的合法性声明标记。

**检查逻辑**:
1. **INDEX.md 检查** (4项):
   - 是否声明"唯一合法入口" (`MKR_UNIQUE_LEGAL_ENTRY`)
   - 是否声明"active-legal map-only 合法性" (`MKR_ACTIVE_LEGAL_MAP_ONLY`)
   - 是否声明"git-commit 门控" (`MKR_GIT_COMMIT_GATE`)
   - 是否仍引用过渡期 round/wave 文件（残留清理检查）

2. **legal-core-map.md 检查** (3项):
   - 是否声明 active-legal 状态 (`MKR_CORE_ACTIVE_LEGAL`)
   - 是否声明 map-only 合法性 (`MKR_CORE_MAP_ONLY`)
   - 是否仍引用过渡期 round/wave 文件

3. **ingestion-registry-map.md 检查** (4项):
   - 是否分类 incoming-raw 和 compatibility-only 范围
   - 是否定义 absorbed 和 retired 状态
   - 是否声明 git-commit 门控

4. **governance 检查** (4项):
   - 是否声明合法性清洗规则 (`MKR_UNWASHED_NOT_LEGAL`)
   - 是否声明地图授予合法性 (`MKR_GOVERNANCE_MAP_GRANTS_LEGALITY`)
   - 是否声明原子性注册 git-commit 规则 (`MKR_ATOMIC_REGISTRATION_GIT_COMMIT`)
   - 是否仍引用 wave 推进/round 文件

**失败处理**: 返回错误字符串列表，每个错误一条描述性消息，调用方决定是否阻断。

#### validate_unique_legal_system_contract() — 唯一合法系统合约校验

**检查内容**: 验证工作区索引、文档索引、概览文档、全局索引、legal-core-map、ingestion-registry-map、hook-contract 之间的一致性。

**检查逻辑** (12项):
1. workspace index 是否加载 project-map 入口
2. workspace index 是否声明 active-legal map-only 合法性
3. workspace index 是否声明 git-commit 规则
4. workspace index 是否引用 truth model canonical
5. overview doc 是否引用 project-map 入口
6. docs index 是否将 docs 子树降级为 project-map 控制的原始资料
7. global index 是否将非本地规范文件降级到合法性登记册
8. global index 是否注册 truth model canonical
9. legal-core-map 是否包含所有 legal_core_markers
10. ingestion-registry-map 是否包含所有 required_registry_scopes
11. hook contract 是否声明 map-only 合法上下文来源
12. hook contract 是否声明注册 git-commit 门控

**失败处理**: 同上，返回错误列表。

---

### 1.2 LegalContractChecker — 法律合约一致性校验

**文件**: `business_policy_checks.py` (第 180-192 行)

**检查内容**: 委托给 ProjectMapValidator.validate_unique_legal_system_contract()。

**设计意图**: 职责分离的包装器，保持方法签名兼容原始 GatewayBusinessPolicyImpl 接口。

**失败处理**: 与 ProjectMapValidator 一致。

---

### 1.3 FrozenTupleChecker — 冻结元组标记校验

**文件**: `business_policy_checks.py` (第 195-224 行)

**检查内容**: 验证治理文件中的冻结元组标记是否符合预期。

**检查逻辑**:
1. **文件存在性检查**: 遍历 `cfg.governance_frozen_tuple_files`，收集缺失文件
2. **预期标记检查**: 合并所有治理文件文本，检查是否包含所有 `cfg.frozen_tuple_expected` 标记
3. **遗留标记检查**: 检测是否仍包含 `cfg.frozen_tuple_legacy_markers` 中的旧标记

**失败处理**:
- 文件缺失: 返回 `["missing governance files: ..."]`
- 标记缺失: 返回 `"missing expected tuple markers: ..."`
- 遗留标记: 返回 `"legacy frozen tuple markers still present: {file} -> {markers}"`

---

### 1.4 EventContractChecker — 事件合约阻断器校验

**文件**: `business_policy_checks.py` (第 227-337 行)

**检查内容**: 验证事件合约文件的正式/非正式一致性。

**检查逻辑**:

**第一阶段 — 文件存在性**:
- 检查 5 个事件合约文件: upstream_standard, upstream_mapping, formal_contract, upstream_samples, downstream_samples

**第二阶段 — 正式集合匹配**:
对 3 个文档（upstream_standard, upstream_mapping, formal_contract）分别检查：
- `source_types`: 从特定 Markdown 章节提取代码标记，与 `cfg.formal_source_types` 比对
- `event_types`: 从特定 Markdown 章节提取代码标记，与 `cfg.formal_event_types` 比对
- `event_statuses`: 从特定 Markdown 章节提取代码标记，与 `cfg.formal_event_statuses` 比对

**第三阶段 — 样例 JSON 校验**:
对 upstream_samples 和 downstream_samples 检查：
- 提取 JSON 中的 source_type/event_type/event_status 值
- 提取字段键，与 formal_field_keys 和 legacy_field_keys 交集
- 检查是否包含非合约范围的值
- 检查是否缺少正式字段
- 检查是否仍使用遗留字段

**失败处理**: 返回详细错误描述，包括期望值和实际值。

---

### 1.5 TruthBasisResolver — 事实基准校验

**文件**: `business_policy_checks.py` (第 340-502 行)

**检查内容**: 解析和验证给定项目范围的事实基准。

**关键方法**:

#### _classify_truth_ref() — 路径分类
将路径分类为 16 种类型：legal-core, project-map-index, global-canonical, compatibility-only, project-canonical, docs, project-runtime, artifact, tooling, log, system, app, agents, gpt-web-to, repo-policy, workspace-entry, other。

#### _truth_basis_errors_for() — 单个文件的事实基准校验 (15项检查):
1. 文件是否存在
2. 是否包含 "Truth Basis" 章节
3. Source Refs 是否存在
4. Authority Refs 是否存在
5. Evidence Refs 是否存在
6. Conflict Status 是否存在
7. Conflict Status 是否为 "resolved"
8. 所有引用是否在仓库范围内
9. 所有引用是否在磁盘上存在
10. Source Refs 和 Evidence Refs 不能完全相同
11. Source Refs 和 Authority Refs 不能重叠
12. Authority Refs 和 Evidence Refs 不能重叠
13. Authority Ref 必须是正式规范路径
14. Source Refs 必须包含非规范来源
15. Evidence Refs 必须包含下层支撑

#### truth_basis_for_scope() — 范围级事实基准
返回包含 policy, refs, source_refs, authority_refs, evidence_refs, conflict_status, errors, validation 的 TruthBasis 字典。

**失败处理**: 返回 validation="fail" 和详细错误列表。

---

### 1.6 ScopeResolver — 项目范围解析

**文件**: `business_policy_checks.py` (第 505-567 行)

**检查内容**: 从当前工作目录解析项目范围，管理范围覆盖。

**关键方法**:
- `determine_project_scope(cwd)`: 通过 scope_match_hints 匹配 cwd 到最近的范围根目录
- `get_project_canonical()`: 合并配置和覆盖的项目规范路径
- `get_project_runtime_root()`: 合并配置和覆盖的运行时根目录
- `decision_refs_for_scope()`: 返回默认 + 项目特定的决策引用
- `lesson_refs_for_scope()`: 返回默认 + 项目特定的课程引用
- `docs_refs_for_scope()`: 返回项目特定的文档引用

**覆盖机制**: 通过 `MEMORY_HOOK_SCOPE_CONFIG_PATH` 环境变量或构造函数参数加载 JSON 覆盖配置。

---

## 2. Adapter 详细分析

### 2.1 GatewayBusinessPolicyImpl — 基类实现

**文件**: `memory_hook_impls.py` (第 252-594 行)

**继承链**: `GatewayBusinessPolicyImpl → GatewayBusinessPolicy (ABC)`

**核心职责**:
1. 接收 GatewayBusinessPolicyConfig 配置
2. 加载范围覆盖配置 (JSON)
3. 提供所有业务策略方法的默认实现

**方法实现** (与 business_policy_checks.py 中对应类的方法一致，但使用中文硬编码标记字符串):
- `validate_project_map_files()` — 验证 project-map 合约
- `validate_unique_legal_system_contract()` — 验证唯一合法系统合约
- `governance_frozen_tuple_blocker_errors()` — 冻结元组校验
- `event_contract_blocker_errors()` — 事件合约校验
- `truth_basis_for_scope()` — 事实基准校验
- `determine_project_scope()` — 项目范围解析
- `get_project_canonical()` — 项目规范映射
- `get_project_runtime_root()` — 项目运行时根映射
- `get_required_canonical()` — 必需规范文件列表
- `get_global_canonical()` — 全局规范文件列表
- `project_map_refs()` — project-map 引用路径
- `decision_refs_for_scope()` — 决策引用
- `lesson_refs_for_scope()` — 课程引用
- `docs_refs_for_scope()` — 文档引用

**重要差异**: GatewayBusinessPolicyImpl 使用**硬编码中文字符串**作为验证标记，而 business_policy_checks.py 中的类使用**_validation_constants.py 中的常量**。这是两种不同的标记来源策略。

---

### 2.2 NeutralGatewayBusinessPolicy — 主机中立策略

**文件**: `neutral_policy.py`

**继承链**: `NeutralGatewayBusinessPolicy → GatewayBusinessPolicyImpl → GatewayBusinessPolicy (ABC)`

**设计意图**: 提供一个纯粹的透传适配器，不覆盖任何方法，仅作为所有具体策略的基类。

**关键特征**:
- 构造函数签名与基类完全一致
- 不注入任何策略覆盖
- 作为策略继承链的中性层

**代码量**: 仅 19 行（不含导入），极简设计。

---

### 2.3 WorkbotGatewayBusinessPolicy — Workbot 策略适配器

**文件**: `workbot_policy.py`

**继承链**: `WorkbotGatewayBusinessPolicy → NeutralGatewayBusinessPolicy → GatewayBusinessPolicyImpl → GatewayBusinessPolicy (ABC)`

**关键覆盖**:

#### ADAPTER_POLICIES 常量
```python
{
    "legality_source": "active-legal-map-only",
    "registration_commit": "required-after-absorption-complete",
}
```

#### 构造函数 — 策略包路径解析
优先级: 显式参数 > 环境变量 (MEMORY_HOOK_POLICY_PACK_PATH) > 默认文件路径 > None

默认文件路径: `memory/kb/global/memory-hook-policy-pack.json`

#### inject_policy_pack_config() — 注入策略包配置
1. 尝试读取策略包 JSON 文件
2. 合并 ADAPTER_POLICIES 到包的 policies 中（适配器策略优先级更高）
3. 返回完整的策略包字典

#### resolve_policies() — 合并策略
1. 获取 PolicyRegistryImpl.DEFAULT_POLICIES
2. 用 ADAPTER_POLICIES 更新
3. 返回合并后的策略字典

---

### 2.4 GatewayBusinessPolicyConfig — 配置数据类

**文件**: `memory_hook_impls.py` (第 239-263 行)

这是一个 `@dataclass(frozen=True)`，包含 27 个字段：
- `repo_root`, `workspace_root`, `project_map_root`
- `project_map_files`, `project_map_governance`
- `truth_model`, `global_canonical`
- `authority_allowed_paths`, `lower_evidence_roots`
- `legal_core_markers`, `required_registry_scopes`
- `project_canonical`, `project_runtime_root`
- `project_doc_refs`, `default_decision_refs`, `project_decision_refs`
- `default_lesson_refs`, `project_lesson_refs`
- `governance_frozen_tuple_files`, `event_contract_files`
- `frozen_tuple_expected`, `frozen_tuple_legacy_markers`
- `formal_source_types`, `formal_event_types`, `formal_event_statuses`
- `formal_field_keys`, `legacy_field_keys`
- `required_canonical`
- `workspace_index_path`, `docs_index_path`, `overview_doc_path`, `global_index_path`
- `hook_contract_path`
- `default_project_scope`, `scope_match_hints`
- `read_text_if_exists_fn`
- `policy_pack_path` (可选)

---

## 3. 策略继承链 Neutral → Workbot 完整映射

```
GatewayBusinessPolicy (ABC)  ← 接口定义
    ↑
GatewayBusinessPolicyImpl    ← 默认实现（所有验证方法）
    ↑
NeutralGatewayBusinessPolicy ← 透传适配器（无覆盖）
    ↑
WorkbotGatewayBusinessPolicy ← Workbot 特定覆盖
    ├── ADAPTER_POLICIES = {legality_source, registration_commit}
    ├── inject_policy_pack_config()  ← 新增方法
    └── resolve_policies()           ← 覆盖策略合并
```

### 方法继承表

| 方法 | GatewayBusinessPolicyImpl | Neutral | Workbot |
|------|--------------------------|---------|---------|
| determine_project_scope() | ✓ 实现 | 继承 | 继承 |
| get_project_canonical() | ✓ 实现 | 继承 | 继承 |
| get_project_runtime_root() | ✓ 实现 | 继承 | 继承 |
| get_required_canonical() | ✓ 实现 | 继承 | 继承 |
| get_global_canonical() | ✓ 实现 | 继承 | 继承 |
| project_map_refs() | ✓ 实现 | 继承 | 继承 |
| validate_project_map_files() | ✓ 实现 | 继承 | 继承 |
| validate_unique_legal_system_contract() | ✓ 实现 | 继承 | 继承 |
| governance_frozen_tuple_blocker_errors() | ✓ 实现 | 继承 | 继承 |
| event_contract_blocker_errors() | ✓ 实现 | 继承 | 继承 |
| decision_refs_for_scope() | ✓ 实现 | 继承 | 继承 |
| lesson_refs_for_scope() | ✓ 实现 | 继承 | 继承 |
| docs_refs_for_scope() | ✓ 实现 | 继承 | 继承 |
| truth_basis_for_scope() | ✓ 实现 | 继承 | 继承 |
| inject_policy_pack_config() | — | — | ✓ 新增 |
| resolve_policies() | — | — | ✓ 新增 |

### 关键差异：标记字符串来源

- **GatewayBusinessPolicyImpl**: 使用硬编码中文字符串（如 `"唯一合法入口"`）
- **business_policy_checks.py**: 使用 `_validation_constants.py` 中的常量（如 `MKR_UNIQUE_LEGAL_ENTRY`）

这表明 `business_policy_checks.py` 是从 `GatewayBusinessPolicyImpl` 中提取的**独立检查类**，目的是将验证逻辑与实现解耦，便于测试和复用。

---

## 4. Policy-Pack 热切换机制详解

### 4.1 三层路径解析

策略包路径解析遵循以下优先级（在两个类中均有实现）：

**WorkbotGatewayBusinessPolicy**:
```
1. 构造函数参数 policy_pack_path
2. 环境变量 MEMORY_HOOK_POLICY_PACK_PATH
3. 默认文件 memory/kb/global/memory-hook-policy-pack.json
4. None (跳过策略包加载)
```

**PolicyRegistryImpl**:
```
1. config.policy_pack_path
2. 构造函数参数 policy_pack_path
3. 环境变量 MEMORY_HOOK_POLICY_PACK_PATH
4. 默认文件 memory/kb/global/memory-hook-policy-pack.json
5. None (跳过策略包加载)
```

### 4.2 策略加载流程

```
Gateway 初始化
    ↓
WorkbotGatewayBusinessPolicy.__init__(policy_pack_path=...)
    ↓
解析策略包路径 → self._policy_pack_path
    ↓
调用 super().__init__() → Neutral → GatewayBusinessPolicyImpl
    ↓
PolicyRegistryImpl.__init__(config=...)
    ↓
_load_dynamic_policy_pack()
    ├── 读取 JSON 文件
    ├── 更新 _schema_version
    ├── 更新 _policies
    └── 更新 _conflict_strategies
```

### 4.3 策略合并规则

**inject_policy_pack_config() 中的合并**:
```python
merged_policies = {}
# 1. 先加载策略包文件中的 policies
if isinstance(pack_content.get("policies"), dict):
    merged_policies.update(pack_content["policies"])
# 2. 再用 ADAPTER_POLICIES 覆盖（适配器优先级更高）
merged_policies.update(ADAPTER_POLICIES)
```

**resolve_policies() 中的合并**:
```python
base = dict(PolicyRegistryImpl.DEFAULT_POLICIES)
base.update(ADAPTER_POLICIES)  # 适配器策略覆盖默认值
```

### 4.4 冲突解决策略

`PolicyRegistryImpl.CONFLICT_STRATEGIES`:
| 策略键 | 冲突解决策略 |
|--------|------------|
| legality_source | fail-fast (直接报错) |
| registration_commit | preserve-and-escalate (保留首个值并升级) |
| registration_phase | prefer-strict (偏好严格值) |
| truth_basis_policy | prefer-strict |
| kb_write_mode | prefer-strict |
| kb_overwrite_allowed | prefer-strict (偏好 "false") |
| default | preserve-and-escalate |

### 4.5 运行时覆盖

通过 `MEMORY_HOOK_SCOPE_CONFIG_PATH` 环境变量加载 JSON 覆盖配置，支持：
- `project_canonical`: 项目规范路径覆盖
- `project_runtime_root`: 项目运行时根目录覆盖

---

## 5. 模块间依赖关系

### 5.1 依赖图

```
memory_hook_interfaces.py (接口定义)
    ↑
memory_hook_impls.py (默认实现)
    ├── GatewayBusinessPolicyConfig
    ├── GatewayBusinessPolicyImpl
    ├── PolicyRegistryImpl
    ├── CodexDelegate / ClaudeDelegate / NoopHostDelegate
    ├── RouteTargetPolicyImpl
    ├── WriteTargetPolicyImpl
    ├── ArtifactSinkImpl / ErrorSinkImpl
    ├── ArtifactWriter / DelegateRouter
    └── PathUtilsImpl
    ↑
_validation_constants.py (验证常量)
    ↑
business_policy_checks.py (独立检查类)
    ├── ProjectMapValidator
    ├── LegalContractChecker
    ├── FrozenTupleChecker
    ├── EventContractChecker
    ├── TruthBasisResolver
    └── ScopeResolver
    ↑
memory_hook_adapters/
    ├── neutral_policy.py → GatewayBusinessPolicyImpl
    ├── workbot_policy.py → NeutralGatewayBusinessPolicy
    ├── workbot_runtime_profile.py → WorkbotGatewayBusinessPolicy
    └── default_runtime_profile.py → NeutralGatewayBusinessPolicy

adapter_toml_schema.py (default_runtime_profile.py 依赖)
```

### 5.2 关键依赖说明

| 模块 | 依赖 | 说明 |
|------|------|------|
| `business_policy_checks.py` | `_validation_constants.py`, `memory_hook_impls.py`, `memory_hook_interfaces.py` | 独立检查类，使用常量而非硬编码 |
| `neutral_policy.py` | `memory_hook_impls.py` | 透传适配器 |
| `workbot_policy.py` | `neutral_policy.py`, `memory_hook_impls.py` | Workbot 特定策略 |
| `workbot_runtime_profile.py` | `workbot_policy.py` | Workbot 运行时配置字典 |
| `default_runtime_profile.py` | `neutral_policy.py`, `adapter_toml_schema.py` | 通用默认配置 |

### 5.3 双模式导入

所有模块都实现了**双模式导入**（包模式和脚本模式）：
```python
try:
    from ..memory_hook_impls import GatewayBusinessPolicyConfig
except ImportError:
    from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig
```

这允许代码既作为 Python 包导入，也作为独立脚本运行。

---

## 6. 其他实现类分析

### 6.1 HostDelegate 实现

| 类 | 用途 | can_handle 条件 |
|----|------|-----------------|
| CodexDelegate | Codex 主机委托 | cmux 命令存在 + surface_id |
| ClaudeDelegate | Claude 主机委托 | cmux 命令存在 + workspace_id + surface_id |
| NoopHostDelegate | 无操作回退 | 始终返回 True |

### 6.2 路由和写入策略

| 类 | 用途 | 关键方法 |
|----|------|---------|
| RouteTargetPolicyImpl | 路由目标解析 | resolve(kind) |
| WriteTargetPolicyImpl | 写入目标解析 | get_targets() |

### 6.3 接收器实现

| 类 | 用途 | 关键方法 |
|----|------|---------|
| ArtifactSinkImpl | 工件写入 | write(package) → 快照 + 最新 + 事件日志 |
| ErrorSinkImpl | 错误日志 | log(component, message, context) |

---

## 7. 总结

### 架构设计亮点

1. **职责分离**: `business_policy_checks.py` 将验证逻辑从 `GatewayBusinessPolicyImpl` 中提取为独立的检查器类，便于测试和复用。

2. **策略继承链**: `GatewayBusinessPolicyImpl → NeutralGatewayBusinessPolicy → WorkbotGatewayBusinessPolicy` 提供了清晰的扩展点。

3. **热切换机制**: 三层路径解析（参数 > 环境变量 > 默认文件）支持运行时策略切换。

4. **双模式导入**: 支持包模式和脚本模式，便于开发和部署。

5. **冲突解决**: 多种冲突解决策略（fail-fast, preserve-and-escalate, prefer-strict）适用于不同场景。

### 需要注意的问题

1. **标记字符串双源**: `GatewayBusinessPolicyImpl` 使用硬编码中文字符串，而 `business_policy_checks.py` 使用常量。这可能导致验证逻辑不一致。

2. **ScopeResolver 重复**: `business_policy_checks.py` 中的 `ScopeResolver` 与 `GatewayBusinessPolicyImpl` 中的范围解析逻辑重复。

3. **硬编码依赖**: `workbot_runtime_profile.py` 包含大量硬编码路径，不易迁移到其他项目。
