---
type: "[DOC:DESIGN]"
title: "实现层"
shortname: DES-005
status: 草稿中
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [implementations,concrete-classes]
related: [DES-004, DES-006, DES-007]
---

> 文档编号：DES-005 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# 实现层设计文档

> 来源：`<memory-repo>/workspace/tools/memory_hook_impls.py`（1040 行）
> 接口：`<memory-repo>/workspace/tools/memory_hook_interfaces.py`（242 行）

---

## 1. 实现类列表与对应接口

| # | 实现类 | 接口 | 接口定义行号 | 实现行号 |
|---|--------|------|-------------|---------|
| 1 | `CodexDelegate` | `HostDelegate` | interfaces:23-51 | impls:49-87 |
| 2 | `ClaudeDelegate` | `HostDelegate` | interfaces:23-51 | impls:89-173 |
| 3 | `PolicyRegistryImpl` | `PolicyRegistry` | interfaces:58-99 | impls:179-342 |
| 4 | `RouteTargetPolicyImpl` | `RouteTargetPolicy` | interfaces:106-116 | impls:348-382 |
| 5 | `WriteTargetPolicyImpl` | `WriteTargetPolicy` | interfaces:119-129 | impls:385-414 |
| 6 | `GatewayBusinessPolicyImpl` | `GatewayBusinessPolicy` | interfaces:132-211 | impls:448-977 |
| 7 | `ArtifactSinkImpl` | `ArtifactSink` | interfaces:218-233 | impls:984-1022 |
| 8 | `ErrorSinkImpl` | `ErrorSink` | interfaces:236-241 | impls:1025-1040 |

辅助数据类：

| # | 类名 | 用途 | 行号 |
|---|------|------|------|
| 9 | `GatewayBusinessPolicyConfig` | `@dataclass(frozen=True)` 配置载体 | impls:422-446 |

---

## 2. CodexDelegate vs ClaudeDelegate 差异

### 2.1 构造函数参数

| 参数 | CodexDelegate (L52-60) | ClaudeDelegate (L92-114) |
|------|------------------------|--------------------------|
| `surface_id` | ✅ | ✅ |
| `workspace_id` | ❌ | ✅ — 额外必填 |
| `state_file` | ❌ | ✅ — 由 adapter policy 注入，不直接从 env 读 |
| `repo_root` | ❌ | ✅ |
| `state_path_factory` | ❌ | ✅ — 回调 `Callable[[Path], Path]` |
| `canonicalizer` | ❌ | ✅ — 回调 `Callable[[str, str], tuple[str, str]]` |
| `state_recorder` | ❌ | ✅ — 回调 `Callable[..., Any]` |
| `which_cmd` | ✅ | ✅ |
| `runner` | ✅ | ✅ |

### 2.2 `can_handle()` 判定条件

**CodexDelegate** (L62-63)：
```
cmux 在 PATH 中 AND surface_id 非空
```

**ClaudeDelegate** (L116-121)：
```
cmux 在 PATH 中 AND workspace_id 非空 AND surface_id 非空
```
Claude 多一个 `workspace_id` 必填约束。

### 2.3 `execute()` 行为差异

| 步骤 | CodexDelegate (L65-82) | ClaudeDelegate (L123-171) |
|------|------------------------|--------------------------|
| 前置校验 | 检查 `cmux` 和 `surface_id` | 检查 `cmux`、`workspace_id`、`surface_id` |
| 状态文件解析 | 无 | 三段式：`_state_file` 注入 → `default_hook_state_path()` 默认 → `state_path_factory` 回调 |
| workspace/surface 规范化 | 无 | 通过 `canonicalizer` 回调或直用原始值 |
| 状态记录 | 无 | 调用 `record_hook_event()` 或 `state_recorder` 回调 |
| 子命令 | `cmux codex-hook <event>` | `cmux claude-hook <event> --workspace <ref> --surface <ref>` |
| stdin | `raw_payload` | `raw_payload or "{}"` |

### 2.4 `noop_response()` 差异

| | CodexDelegate (L84-86) | ClaudeDelegate (L169-171) |
|---|------------------------|--------------------------|
| stdout | `"{}\n"` — 返回空 JSON | `""` — 返回空字符串 |
| stderr | `""` | `""` |
| returncode | `0` | `0` |

### 2.5 环境依赖

| 环境变量 | CodexDelegate | ClaudeDelegate |
|----------|---------------|----------------|
| `CMUX_SURFACE_ID` | ✅ (L58) | ✅ (L105) |
| `CMUX_WORKSPACE_ID` | ❌ | ✅ (L104) |
| `MEMORY_HOOK_SCOPE_CONFIG_PATH` | ❌ | 由 `GatewayBusinessPolicyImpl` 使用 (L452) |

---

## 3. GatewayBusinessPolicyImpl 完整实现

### 3.1 配置载体 `GatewayBusinessPolicyConfig` (L422-446)

`@dataclass(frozen=True)` 不可变配置对象，包含 35 个字段：

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
| `policy_pack_path` | `Path \| None` | 可选策略包路径 |

### 3.2 Scope 覆盖机制 (L452-477)

- 通过 `MEMORY_HOOK_SCOPE_CONFIG_PATH` 环境变量或构造函数参数加载 JSON scope 配置
- 覆盖 `project_canonical` 和 `project_runtime_root` 两个 key
- `_resolve_override_path()` (L479-483)：绝对路径直接使用，相对路径基于 `repo_root` 解析

### 3.3 路径工具方法

| 方法 | 行号 | 功能 |
|------|------|------|
| `_path_is_under()` | L485-490 | 跟随 symlink 检查路径是否在 root 下 |
| `_path_is_under_lexical()` | L492-499 | 词法层面检查，不跟随 symlink |
| `_section_bullets()` | L501-512 | 从 Markdown 提取指定 heading 下的 bullet 列表 |
| `_section_body()` | L514-525 | 从 Markdown 提取指定 heading 下的正文 |
| `_markdown_code_tokens()` | L527-528 | 提取所有反引号代码片段 |
| `_json_string_values()` | L530-532 | 提取 JSON 中指定 key 的所有字符串值 |
| `_json_object_keys()` | L534-535 | 提取 JSON 所有 key |

### 3.4 Truth Ref 分类 (L543-571)

`_classify_truth_ref()` 将路径分为 17 类：

`legal-core` | `project-map-index` | `global-canonical` | `compatibility-only` | `project-canonical` | `docs` | `project-runtime` | `artifact` | `tooling` | `log` | `system` | `app` | `agents` | `gpt-web-to` | `repo-policy` | `workspace-entry` | `other`

### 3.5 Truth Basis 验证 (L685-721)

`_truth_basis_errors_for()` 执行以下校验：
1. 文件不存在 → 跳过
2. 提取 `source_refs` / `authority_refs` / `evidence_refs` / `conflict_status` 四个 section
3. 四组 refs 必须非空
4. source ≠ evidence（不能相同）
5. source ∩ authority = ∅
6. authority ∩ evidence = ∅
7. 所有 authority 必须在 `authority_allowed_paths` 或 `global_canonical` 中
8. source 必须包含至少一个非 canonical 来源
9. evidence 必须包含至少一个 lower-layer 支持

### 3.6 Scope 判定 (L723-732)

`determine_project_scope()`：
1. cwd 不在 repo_root 下 → 返回 `default_project_scope`
2. 遍历 `scope_match_hints`，按 lexical 路径包含匹配
3. 未匹配 → 返回 `default_project_scope`

### 3.7 映射获取方法

| 方法 | 行号 | 逻辑 |
|------|------|------|
| `get_project_canonical()` | L734-740 | config 合并 scope overrides |
| `get_project_runtime_root()` | L742-748 | config 合并 scope overrides |
| `get_required_canonical()` | L750-751 | 直接返回 config |
| `get_global_canonical()` | L753-754 | 直接返回 config |

### 3.8 Project Map 验证 (L760-802)

`validate_project_map_files()` 对四个文件（INDEX / legal-core / registry / governance）执行字符串包含校验：

- INDEX 必须包含：`唯一合法入口`、`active-legal` 合法性声明、`git commit` 生效门控
- INDEX 不能包含：`round-`、`waves/`（遗留引用）
- legal-core 必须包含：`active-legal`、map-only 合法性声明
- registry 必须包含：`incoming-raw`、`compatibility-only`、`absorbed`、`retired`
- governance 必须包含：合法性清洗规则、map 授予合法性声明、原子 git commit 规则
- 不能包含遗留 wave/round 引用

### 3.9 Unique Legal System Contract 验证 (L804-842)

`validate_unique_legal_system_contract()` 校验六个文件的交叉引用一致性：

- workspace index 引用 project-map、active-legal 声明、git commit 规则、truth model
- overview doc 引用 project-map
- docs index 降级为 raw material
- global index 降级非 canonical 到 registry、注册 truth model
- legal-core 包含所有 `legal_core_markers`
- registry 包含所有 `required_registry_scopes`
- hook contract 声明 map-only legal context、git commit 门控

### 3.10 Blocker 校验 (L844-898)

| 方法 | 行号 | 功能 |
|------|------|------|
| `governance_frozen_tuple_blocker_errors()` | L844-869 | 检查 governance 文件缺失、期望标记缺失、遗留标记残留 |
| `event_contract_blocker_errors()` | L871-898 | 检查 event contract 文件缺失、期望标记缺失、遗留标记残留 |

### 3.11 Ref 查询方法 (L900-927)

| 方法 | 行号 | 逻辑 |
|------|------|------|
| `decision_refs_for_scope()` | L900-903 | default + project 合并，过滤存在路径 |
| `lesson_refs_for_scope()` | L905-907 | 同上 |
| `docs_refs_for_scope()` | L909-911 | 仅 project，过滤存在路径 |

### 3.12 Truth Basis 查询 (L913-977)

`truth_basis_for_scope()` 返回完整 truth basis 包：
- 不支持的 scope → `validation: "fail"`, `conflict_status: ["unresolved"]`
- 支持的 scope → 合并 global canonical + project canonical，逐文件验证，返回 `pass`/`fail`

---

## 4. PolicyRegistryImpl 策略加载和冲突解决

### 4.1 策略包路径解析优先级 (L207-221)

```
config.policy_pack_path > 构造参数 > MEMORY_HOOK_POLICY_PACK_PATH 环境变量 > 默认文件路径 > None
```

默认路径 (L183-185)：`workspace/memory/kb/global/memory-hook-policy-pack.json`

### 4.2 默认策略 (L187-192)

```python
DEFAULT_POLICIES = {
    "registration_phase": "declared-not-enforced",
    "truth_basis_policy": "source-authority-evidence-conflict",
    "kb_write_mode": "read-first-CRUD",
    "kb_overwrite_allowed": "false",
}
```

### 4.3 冲突策略 (L194-202)

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

### 4.4 动态策略包加载 (L223-250)

`_load_dynamic_policy_pack()`：
1. 路径不存在 → 跳过
2. JSON 解析失败 → 跳过
3. 非 dict 类型 → 跳过
4. 提取 `schema_version`、`policies`、`conflict_strategies` 三个顶层 key
5. 策略值覆盖默认值（key-value 均为 string 才接受）

### 4.5 冲突解决算法 (L283-320)

`resolve_conflict(policy_key, values, strategy)`：

| 策略 | 行为 |
|------|------|
| `fail-fast` | 直接 raise `ValueError` |
| `preserve-and-escalate` | 返回 `values[0]`，标记为已升级 |
| `prefer-strict` | 对 `kb_overwrite_allowed` → 选 `"false"`；对 `registration_phase` → 选 `"declared-not-enforced"`；其他 → `values[0]` |
| 未知策略 | 返回 `values[0]` |

### 4.6 验证 (L268-274)

`validate()` 仅检查 `project_scope` 是否在 `allowed_scopes` 中（如果配置了的话）。

### 4.7 Schema 版本

固定为 `"m3-policy-pack-v1"` (L181)。

---

## 5. ArtifactSinkImpl 写入逻辑 (L984-1022)

### 5.1 构造函数

| 参数 | 类型 | 用途 |
|------|------|------|
| `context_root` | `Path` | 快照存放目录 |
| `event_log` | `Path` | 事件日志文件 |
| `datetime_module` | `Any` | 时间模块（默认 `datetime`，可注入测试） |

### 5.2 写入流程 `write(package)` (L1000-1022)

```
1. ensure_dirs() — 创建 context_root 目录树
2. 生成时间戳: YYYYMMDDTHHMMSSffffff（微秒精度）
3. 构造快照路径: {timestamp}-{host}-{event}.json
4. 冲突处理: 如果路径已存在，追加 -{suffix:02d} 后缀递增直到可用
5. 构造 latest 路径: latest-{host}-{event}.json
6. 注入 artifact_refs 到 package:
   - snapshot: 快照绝对路径
   - latest: latest 文件绝对路径
   - event_log: 事件日志绝对路径
7. 渲染 JSON: ensure_ascii=False, indent=2, 尾部换行
8. 写入 snapshot 文件（覆盖）
9. 写入 latest 文件（覆盖，内容与 snapshot 相同）
10. 追加写入 event_log（JSON Lines 格式，无缩进）
11. 返回 {"snapshot": path, "latest": path}
```

### 5.3 文件名冲突解决

时间戳 + 微秒仍可能冲突时，使用递增后缀 `01`, `02`, ... (L1004-1007)。

### 5.4 双写机制

每个 artifact 同时写入两个文件：
- **snapshot**：带时间戳的永久快照
- **latest**：同 host+event 组合的最新版本（每次覆盖）

---

## 6. ErrorSinkImpl 错误日志格式 (L1025-1040)

### 6.1 构造函数

| 参数 | 类型 | 用途 |
|------|------|------|
| `error_log` | `Path` | 错误日志文件路径 |
| `now_iso_fn` | `Callable[[], str] \| None` | 时间戳生成回调（默认 `datetime.now().astimezone().isoformat(timespec="seconds")`） |

### 6.2 日志格式 `log(component, message, context)` (L1036-1040)

单行格式：
```
[{iso_timestamp}] [{component}] [error] {message} | context={json_context}
```

示例：
```
[2026-04-26T10:30:00+08:00] [GatewayBusinessPolicy] [error] validation failed | context={"scope": "workbot", "file": "INDEX.md"}
```

### 6.3 格式特征

| 特征 | 实现 |
|------|------|
| 时间戳 | ISO 8601 带时区，秒级精度 |
| component | 方括号包裹，标识错误来源组件 |
| 级别 | 固定 `[error]` |
| context | JSON 序列化，`ensure_ascii=False`, `sort_keys=True` |
| 写入模式 | 追加（`"a"`），UTF-8 |
| 目录创建 | 自动创建父目录 |
