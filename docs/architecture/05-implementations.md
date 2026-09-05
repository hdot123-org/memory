---
type: "[DOC:DESIGN]"
title: "实现层"
shortname: DES-005
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [implementations,concrete-classes]
related: [DES-004, DES-006, DES-007]
---

> 文档编号：DES-005 | 版本：V1.1 | 日期：2026-09-05 | 状态：可评审 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码。

# 实现层设计文档

> 来源：`memory_core/tools/memory_hook_impls.py`（904 行）
> 接口：`memory_core/tools/memory_hook_interfaces.py`（341 行）
> 校准日期：2026-09-05（v0.45.6；行号均经 `grep -n` 实测）

> **📌 2026-09-05 校准备注**
> 1. `CodexDelegate` / `ClaudeDelegate` **已删除**（cmux / surface_id / workspace_id 宿主集成退役），替换为 `FactoryDelegate`（中性空响应）+ `NoopHostDelegate`（可用性标记降级）+ `resolve_host_delegate()` 工厂函数（按 `SUPPORTED_HOSTS = ("factory", "zcode")` 分派，constants.py:23）。
> 2. 新增 IF-5 组件：`ArtifactWriter`（非阻塞产物写入包装）、`DelegateRouter`（仅支持 factory 系宿主的事件路由）。
> 3. `GatewayBusinessPolicyImpl` 的校验逻辑**全部委托** `business_policy_checks.py`（706 行）中的 `ProjectMapValidator` / `FrozenTupleChecker` / `EventContractChecker` / `TruthBasisResolver`；scope 解析与覆盖逻辑抽取到 `_scope_resolver_base.py` 的 `ScopeResolverBase`（97 行）。
> 4. 共享规则助手迁至 `_rule_helpers.py`，验证标记常量迁至 `_validation_constants.py`（`MKR_*` 族），领域异常迁至 `_rule_errors.py`（`UnknownHostError` / `UnknownRouteKindError` / `UnsupportedScopeError`），`now_iso` 迁至 `_file_utils.py`。
> 5. `ArtifactSinkImpl` 改为按日目录组织快照并双写事件日志；`ErrorSinkImpl` 新增 `*-readable.log` 人类可读输出（`MEMORY_HOOK_READABLE_ERRORS_DISABLED=1` 可关闭）。
> 6. 行号全部按 v0.45.6 `grep -n "class "` 实测刷新。

---

## 1. 实现类列表与对应接口

| # | 实现类 | 接口 | 接口定义行号 | 实现行号 |
|---|--------|------|-------------|---------|
| 1 | `FactoryDelegate` | `HostDelegate` | interfaces:52-90 | impls:125-150 |
| 2 | `NoopHostDelegate` | `HostDelegate` | interfaces:52-90 | impls:152-191 |
| 3 | `resolve_host_delegate` | （模块级工厂函数） | — | impls:194-224 |
| 4 | `PolicyRegistryImpl` | `PolicyRegistry` | interfaces:97-187 | impls:227-434 |
| 5 | `RouteTargetPolicyImpl` | `RouteTargetPolicy` | interfaces:193-202 | impls:437-503 |
| 6 | `WriteTargetPolicyImpl` | `WriteTargetPolicy` | interfaces:206-214 | impls:505-539 |
| 7 | `GatewayBusinessPolicyImpl` | `GatewayBusinessPolicy` + `ScopeResolverBase` 混入 | interfaces:219-292 | impls:584-663 |
| 8 | `ArtifactSinkImpl` | `ArtifactSink` | interfaces:298-312 | impls:665-718 |
| 9 | `ErrorSinkImpl` | `ErrorSink` | interfaces:316-327 | impls:720-806 |
| 10 | `ArtifactWriter` | （无接口，包装 `ArtifactSinkImpl`） | — | impls:808-868 |
| 11 | `DelegateRouter` | （无接口，路由 `FactoryDelegate`） | — | impls:870-904 |

辅助数据类：

| # | 类名 | 用途 | 行号 |
|---|------|------|------|
| 12 | `GatewayBusinessPolicyConfig` | `@dataclass(frozen=True)` 配置载体（37 字段） | impls:541-582 |

已移除：`CodexDelegate`（旧 impls:49-87）、`ClaudeDelegate`（旧 impls:89-181）。

---

## 2. HostDelegate 实现族：FactoryDelegate vs NoopHostDelegate

### 2.1 构造与行为对比

两个实现均**无构造参数**、`can_handle()` 恒为 `True`、`execute()` 直接返回 `noop_response()`：

| | `FactoryDelegate`（impls:125-150） | `NoopHostDelegate`（impls:152-191） |
|---|-----------------------------------|-------------------------------------|
| 定位 | Factory 宿主的中性 delegate：无需 cmux 集成，空响应直通，不阻塞会话创建 | 降级 delegate：宿主不存在时的占位实现 |
| `noop_response()` stdout | `"{}\n"`（空 JSON） | `{"host_unavailable": true, "policy_decision": "no_host"}` + 换行 |
| `host_unavailable` | `False`（继承接口默认值，impls:148 显式覆写） | `True`（impls:190 覆写） |
| stderr / returncode | `""` / `0` | `""` / `0` |

`host_unavailable` 的语义：消费方应先检查该属性再解释 `policy_decision`，把"宿主不存在"与"策略决策"分离（5b.6 约定）。

### 2.2 `resolve_host_delegate()` 工厂函数（impls:194-224）

```python
def resolve_host_delegate(host: str, mode: str = "auto") -> HostDelegate
```

- `host ∈ SUPPORTED_HOSTS`（`("factory", "zcode")`，constants.py:23）→ 构造 `FactoryDelegate`；否则直接返回 `NoopHostDelegate()`。
- mode 分支：

| mode | 行为 |
|------|------|
| `"auto"`（默认） | FactoryDelegate 可处理则返回之，否则 NoopHostDelegate |
| `"noop"` | 恒返回 NoopHostDelegate |
| `"cmux"` | 恒返回 FactoryDelegate（允许 can_handle=False） |

### 2.3 已移除的机制（随 Codex/Claude delegate 一并退役）

- cmux 子命令集成（`cmux codex-hook` / `cmux claude-hook`）
- `surface_id` / `workspace_id` / `state_file` / `state_path_factory` / `canonicalizer` / `state_recorder` 构造参数族
- 环境变量 `CMUX_SURFACE_ID` / `CMUX_WORKSPACE_ID`
- 三段式状态文件解析与 `record_hook_event()` 状态记录

当前实现族使用的环境变量仅剩 `MEMORY_HOOK_POLICY_PACK_PATH`（PolicyRegistryImpl，impls:231）。

---

## 3. GatewayBusinessPolicyImpl 完整实现

### 3.1 配置载体 `GatewayBusinessPolicyConfig`（impls:541-582）

`@dataclass(frozen=True)` 不可变配置对象，共 **37 个字段**（36 必填 + 1 可选默认）：

| 字段 | 类型 | 用途 |
|------|------|------|
| `repo_root` | `Path` | 仓库根目录 |
| `workspace_root` | `Path` | workspace 根目录 |
| `project_map_root` | `Path` | project-map 目录 |
| `project_map_files` | `list[Path]` | project-map 文件列表（INDEX / legal-core / registry） |
| `project_map_governance` | `Path` | governance 文件 |
| `truth_model` | `Path` | 真相模型文件 |
| `global_canonical` | `list[Path]` | 全局规范文件列表 |
| `authority_allowed_paths` | `set[Path]` | 允许的权威引用路径集合 |
| `lower_evidence_roots` | `list[Path]` | 底层证据根目录 |
| `legal_core_markers` | `list[str]` | legal-core 必须包含的标记 |
| `required_registry_scopes` | `list[str]` | registry 必须包含的 scope |
| `project_canonical` | `dict[str, Path]` | scope → project canonical 映射 |
| `project_runtime_root` | `dict[str, Path]` | scope → runtime root 映射 |
| `project_doc_refs` | `dict[str, list[Path]]` | scope → 文档引用 |
| `default_decision_refs` | `list[Path]` | 默认决策引用 |
| `project_decision_refs` | `dict[str, list[Path]]` | scope → 决策引用 |
| `default_lesson_refs` | `list[Path]` | 默认经验引用 |
| `project_lesson_refs` | `dict[str, list[Path]]` | scope → 经验引用 |
| `governance_frozen_tuple_files` | `list[Path]` | governance frozen tuple 文件 |
| `event_contract_files` | `dict[str, Path]` | event contract 文件映射 |
| `frozen_tuple_expected` | `set[str]` | 期望的 frozen tuple 标记 |
| `frozen_tuple_legacy_markers` | `set[str]` | 遗留 frozen tuple 标记 |
| `formal_source_types` | `set[str]` | 正式 source 类型 |
| `formal_event_types` | `set[str]` | 正式 event 类型 |
| `formal_event_statuses` | `set[str]` | 正式 event 状态 |
| `formal_field_keys` | `set[str]` | 正式字段 key |
| `legacy_field_keys` | `set[str]` | 遗留字段 key |
| `required_canonical` | `list[Path]` | 必需的 canonical 文件 |
| `workspace_index_path` | `Path` | workspace index |
| `docs_index_path` | `Path` | docs index |
| `overview_doc_path` | `Path` | overview 文档 |
| `global_index_path` | `Path` | global index |
| `hook_contract_path` | `Path` | hook contract |
| `default_project_scope` | `str` | 默认 scope |
| `scope_match_hints` | `dict[str, list[Path]]` | scope 匹配提示 |
| `read_text_if_exists_fn` | `Callable[[Path], str]` | 文本读取回调 |
| `policy_pack_path` | `Path \| None` | 可选策略包路径（默认 `None`） |

### 3.2 Scope 解析与覆盖（已迁至 ScopeResolverBase）

`GatewayBusinessPolicyImpl(ScopeResolverBase, GatewayBusinessPolicy)`（impls:584）的 `__init__`（impls:591）显式委托 `ScopeResolverBase.__init__`。scope 相关逻辑现位于 `_scope_resolver_base.py`（97 行）：

| 方法 | 行号（_scope_resolver_base.py） | 功能 |
|------|------|------|
| `_resolve_override_path` | :60 | 绝对路径直接使用，相对路径基于 `repo_root` 解析 |
| `determine_project_scope` | :66 | cwd 不在 repo_root 下 → `default_project_scope`；遍历 `scope_match_hints` 按 lexical 路径包含匹配；未匹配 → `default_project_scope` |
| `get_project_canonical` | :76 | config 合并 scope overrides |
| `get_project_runtime_root` | :83 | config 合并 scope overrides |
| `get_required_canonical` | :90 | 直接返回 config |
| `get_global_canonical` | :93 | 直接返回 config |
| `project_map_refs` | :96 | project-map 引用列表 |

scope 覆盖仍通过 `MEMORY_HOOK_SCOPE_CONFIG_PATH` 环境变量或构造参数 `scope_config_path` 加载 JSON，覆盖 `project_canonical` 与 `project_runtime_root` 两个 key。`GatewayBusinessPolicyImpl` 只覆写 `_read_text_if_exists`（impls:599，委托 config 回调）与业务校验/查询方法。

### 3.3 路径/文本工具方法（已迁至 _rule_helpers.py 共享模块）

`_path_is_under`、`_path_is_under_lexical`、`_section_bullets`、`_section_body`、`_markdown_code_tokens`、`_json_string_values`、`_json_object_keys`、`_existing_paths` 均不再定义于 impls，统一从 `_rule_helpers.py` 导入（impls:28-56，REF-001 §4.3 整合），供 impls 与 `business_policy_checks.py` 共享。

### 3.4 Truth Ref 分类（已迁至 TruthBasisResolver）

`_classify_truth_ref()` 现位于 `TruthBasisResolver`（business_policy_checks.py:472-511），改为**表驱动**实现（exact 表 + under 表），仍是 17 类标签：

`legal-core` | `project-map-index` | `repo-policy` | `workspace-entry` | `global-canonical` | `compatibility-only` | `project-canonical` | `docs` | `project-runtime` | `artifact` | `tooling` | `log` | `system` | `app` | `agents` | `gpt-web-to` | `other`

### 3.5 Truth Basis 验证（已迁至 TruthBasisResolver）

`_truth_basis_errors_for()`（business_policy_checks.py:593-637）按 8 个 Phase 执行校验：

1. 文件缺失 / 无 `Truth Basis` section → 直接报错
2. 提取 `source_refs` / `authority_refs` / `evidence_refs` / `conflict_status` 四个 section（`### Source Refs` 等 heading 下的 bullet）
3. 四组 refs 必须非空（section presence）
4. `conflict_status` 必须为 `["resolved"]`（否则 unresolved 错误）
5. 引用路径解析（相对路径基于 repo_root）+ 存在性校验（必须在仓库内且在磁盘上存在）
6. 互斥校验：source ≠ evidence（不能完全相同）、source ∩ authority = ∅、authority ∩ evidence = ∅
7. 所有 authority 必须在 `authority_allowed_paths` 或 `global_canonical` 中
8. source 必须包含至少一个非 canonical 来源（legal-core / project-map-index / global-canonical 之外）；evidence 必须包含至少一个 `lower_evidence_roots` 下的底层支持

### 3.6 映射获取与查询方法（GatewayBusinessPolicyImpl 本体）

| 方法 | 行号 | 逻辑 |
|------|------|------|
| `validate_project_map_files()` | impls:602 | 委托 `ProjectMapValidator`（business_policy_checks.py:138） |
| `validate_unique_legal_system_contract()` | impls:611 | 委托 `ProjectMapValidator`（business_policy_checks.py:206） |
| `governance_frozen_tuple_blocker_errors()` | impls:620 | 委托 `FrozenTupleChecker`（business_policy_checks.py:245） |
| `event_contract_blocker_errors()` | impls:629 | 委托 `EventContractChecker`（business_policy_checks.py:287） |
| `decision_refs_for_scope()` | impls:638 | default + project 合并，`_existing_paths` 过滤 |
| `lesson_refs_for_scope()` | impls:642 | 同上 |
| `docs_refs_for_scope()` | impls:646 | 仅 project，`_existing_paths` 过滤 |
| `truth_basis_for_scope()` | impls:650 | 委托 `TruthBasisResolver`（business_policy_checks.py:424，方法体 :638-706），返回 `TruthBasis` |

### 3.7 Project Map 验证（ProjectMapValidator.validate_project_map_files，business_policy_checks.py:151-204）

对四个文件（INDEX / legal-core / registry / governance）执行标记包含校验（标记常量来自 `_validation_constants.py` 的 `MKR_*` 族）：

- INDEX 必须包含：唯一合法入口（`MKR_UNIQUE_LEGAL_ENTRY`）、active-legal map-only 合法性声明、git commit 生效门控；不能包含 `round-`、`waves/` 遗留引用
- legal-core 必须包含：active-legal 状态、map-only 合法性声明；不能包含遗留引用
- registry 必须包含：`incoming-raw`、`compatibility-only` 分类，`absorbed` / `retired` 状态，git commit 门控
- governance 必须包含：合法性清洗规则、map 授予合法性声明、原子 git commit 规则；不能包含 wave/round 遗留引用

### 3.8 Unique Legal System Contract 验证（business_policy_checks.py:206-243）

校验多文件交叉引用一致性：

- workspace index 引用 project-map、active-legal 声明、git commit 规则、truth model
- overview doc 引用 project-map 入口
- docs index 降级为 project-map 管控的 raw material
- global index 降级非本地 canonical 到 registry、注册 truth model
- legal-core 包含所有 `legal_core_markers`
- registry 包含所有 `required_registry_scopes`
- hook contract 声明 map-only legal context、注册 git-commit 门控

### 3.9 Blocker 校验（business_policy_checks.py）

| 检查器 | 行号 | 功能 |
|--------|------|------|
| `FrozenTupleChecker.governance_frozen_tuple_blocker_errors` | :255-285 | governance 文件缺失、期望标记缺失、遗留标记残留 |
| `EventContractChecker.event_contract_blocker_errors` | :297-422 | event contract 文件缺失；upstream_standard / upstream_mapping / formal_contract 三文档的 source/event/status 正式集合与 config 期望集逐一比对；upstream/downstream 样本 JSON 的越权取值、缺失正式字段、遗留字段残留 |

### 3.10 Truth Basis 查询（TruthBasisResolver.truth_basis_for_scope，business_policy_checks.py:638-706）

- 不支持的 scope → `validation: "fail"`、`conflict_status: ["unresolved"]`、refs 退化为 global canonical
- 支持的 scope → 合并 global canonical + project canonical，逐文件执行 3.5 节 8 Phase 校验，返回 `pass` / `fail`

---

## 4. PolicyRegistryImpl 策略加载和冲突解决（impls:227-434）

### 4.1 类常量与策略包路径解析优先级（impls:230-233、:256-288）

```
config.policy_pack_path > 构造参数 policy_pack_path > MEMORY_HOOK_POLICY_PACK_PATH 环境变量 > 默认文件路径 > None
```

默认路径（impls:232-234）：包内 `memory_core/memory/kb/global/memory-hook-policy-pack.json`（仓库无关 fallback；项目专属 policy pack 应由 gateway/runtime profile 注入）。

### 4.2 默认策略（impls:238-244）

```python
DEFAULT_POLICIES = {
    "registration_phase": "declared-not-enforced",
    "truth_basis_policy": "source-authority-evidence-conflict",
    "kb_write_mode": "read-first-CRUD",
    "kb_overwrite_allowed": "false",
}
```

### 4.3 冲突策略（impls:246-255）

```python
CONFLICT_STRATEGIES = {
    "legality_source": "fail-fast",
    "registration_commit": "preserve-and-escalate",
    "registration_phase": "prefer-strict",
    "truth_basis_policy": "prefer-strict",
    "kb_write_mode": "prefer-strict",
    "kb_overwrite_allowed": "prefer-strict",
    "default": "preserve-and-escalate",
}
```

### 4.4 动态策略包加载（impls:289-319）

`_load_dynamic_policy_pack()`：
1. 路径为 None 或不存在 → 跳过
2. JSON 解析失败 / 非 dict 类型 → 跳过
3. 提取 `schema_version`（非空字符串则覆写）、`policies`、`conflict_strategies` 三个顶层 key
4. 策略值覆盖默认值（key-value 均为 string 才接受）

### 4.5 冲突解决算法（impls:351-393）

`resolve_conflict(policy_key, values, strategy)`：

| 策略 | 行为 |
|------|------|
| `fail-fast` | 直接 raise `ValueError` |
| `preserve-and-escalate` | 返回 `values[0]`，标记为已升级 |
| `prefer-strict` | 对 `kb_overwrite_allowed` → 选 `"false"`；对 `registration_phase` → 选 `"declared-not-enforced"`；其他 → `values[0]` |
| 未知策略 | 返回 `values[0]` |

空 values 直接 raise `ValueError`；单值直接返回。

### 4.6 验证（impls:324-329）

`validate()` 仅检查 `project_scope` 是否在 `allowed_scopes` 中（如果配置了的话）。

### 4.7 治理/查询 stub 方法（impls:395-431）

`validate_project_map` / `validate_unique_legal_system_contract` / `governance_frozen_tuple_errors` / `event_contract_blocker_errors` / `git_registration_probe` / `truth_basis_for_scope` / `decision_refs_for_scope` / `lesson_refs_for_scope` / `docs_refs_for_scope` 共 9 个方法在本实现中为 **stub**（返回空值），生产环境由 `GatewayBusinessPolicyImpl` 承担真实逻辑——接口要求这些方法存在，PolicyRegistryImpl 仅满足接口契约。

### 4.8 Schema 版本

默认固定为 `"m3-policy-pack-v1"`（impls:230），可被动态 policy pack 的 `schema_version` 覆写。

---

## 5. ArtifactSinkImpl 写入逻辑（impls:665-718）

### 5.1 构造函数（impls:668-676）

| 参数 | 类型 | 用途 |
|------|------|------|
| `context_root` | `Path` | 快照根目录（快照按日组织在其 `<day>/` 子目录下） |
| `event_log` | `Path` | legacy 事件日志文件（当日日志写到其旁的 `events/<day>.jsonl`） |
| `datetime_module` | `Any` | 时间模块（默认 `datetime`，可注入测试） |

### 5.2 写入流程 `write(package)`（impls:682-718）

```
1. ensure_dirs()（impls:678）— 创建 context_root 与 events/ 目录树
2. 生成时间戳 YYYYMMDDTHHMMSSffffff（微秒精度）与 day（ISO 日期）
3. 构造当日目录 context_root/<day>/
4. 快照路径: <day>/{timestamp}-{host}-{event}.json
5. 冲突处理: 路径已存在时插入 -{suffix:02d}- 递增直到可用（impls:690-693）
6. 构造 latest 路径: context_root/latest-{host}-{event}.json（根目录）
   与 daily_latest 路径: <day>/latest-{host}-{event}.json（当日目录）
7. 注入 artifact_refs 到 package（5 个 key，impls:698-703）:
   - snapshot: 快照绝对路径
   - latest: 根目录 latest 绝对路径
   - daily_latest: 当日 latest 绝对路径
   - event_log: events/<day>.jsonl 绝对路径
   - legacy_event_log: 构造传入的 event_log 绝对路径
8. 渲染 JSON: ensure_ascii=False, indent=2, 尾部换行
9. 写入 snapshot、latest、daily_latest 三个文件（内容相同）
10. 追加写入两处事件日志（JSON Lines，无缩进）:
    events/<day>.jsonl（当日）+ legacy event_log（每次一行）
11. 返回 {"snapshot": path, "latest": path, "event_log": daily_event_log}
```

### 5.3 双 latest 机制

每个 artifact 同时维护两个 latest 视图：根目录 `latest-*`（全局最新）与当日目录 `latest-*`（按日最新）；快照本体只落在当日目录，事件日志同时追加当日与 legacy 两份。

---

## 6. ErrorSinkImpl 错误日志格式（impls:720-806）

### 6.1 构造函数（impls:733-738）

| 参数 | 类型 | 用途 |
|------|------|------|
| `error_log` | `Path` | 主错误日志文件路径 |
| `now_iso_fn` | `Callable[[], str] \| None` | 时间戳回调（默认 `_file_utils.now_iso`，ISO 8601 带时区秒级精度） |

### 6.2 双轨输出 `log(component, message, context)`（impls:776-806）

**轨道 1 — 结构化 JSON 行**（机器消费），同一条写两处：

```
[{iso_timestamp}] [{component}] [error] {message} | context={json_context}
```

- 当日日志：`errors/<day>.log`（`error_log` 旁的 errors/ 目录）
- 主日志：构造传入的 `error_log`

context 以 `ensure_ascii=False, sort_keys=True` 序列化；追加模式（`"a"`），UTF-8；自动创建父目录。

**轨道 2 — 人类可读行**（开发者排查），写 `*-readable.log`（当日与主日志各一份）：

```
[{timestamp}] [ERROR] component={component} {message} | key=value ...
```

- 命名规则：`<log stem>-readable.log`（`READABLE_SUFFIX`，impls:730）
- 关闭开关：`MEMORY_HOOK_READABLE_ERRORS_DISABLED=1`（`_readable_enabled`，impls:773-774）
- best-effort：可读输出失败（OSError）时静默跳过，绝不阻塞结构化输出（impls:798-800）
- 值含空格/制表符时 JSON 引号包裹；dict/list 以 JSON 渲染（`_format_kv`，impls:746-759）

---

## 7. IF-5 组件：ArtifactWriter 与 DelegateRouter（impls:808-904）

### 7.1 ArtifactWriter（impls:808-868）

包装 `ArtifactSinkImpl` 的**非阻塞**写入器：

- 构造（:816）：`context_root` + `error_log` + 可注入 `datetime_module`；内部以 `context_root.parent / "events.jsonl"` 为 event_log 组装 `ArtifactSinkImpl`
- `write(host, event, package) -> bool`（:829）：向 package 注入 `host` / `event` 后委托 sink；任何异常被捕获、记录并返回 `False`（不 raise）
- `last_error` property（:846）：暴露最近一次写入错误
- `_log_error`（:849）：失败时按 ArtifactWriter 组件名写当日 + 主错误日志两份

### 7.2 DelegateRouter（impls:870-904）

将 context package 路由到 factory 系宿主 delegate（INV-6 约束，仅 factory）：

- 构造（:876）：可选注入 `FactoryDelegate`（默认自建）
- `route(host, event, raw_payload, payload)`（:882）：`host ∈ SUPPORTED_HOSTS` → `factory_delegate.execute(...)`；否则 raise `UnknownHostError`
- `noop(host)`（:897）：同判定下执行 `factory_delegate.noop_response()`；否则 raise `UnknownHostError`
