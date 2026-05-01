# `memory_hook_impls.py` 深度分析报告

> 文件路径：`/Users/busiji/memory/memory_core/tools/memory_hook_impls.py`
> 文件大小：~58KB
> 所属模块：M2 Default Implementations for memory-hook-gateway interfaces

---

## 目录

1. [每个实现类的详细分析](#1-每个实现类的详细分析)
2. [类之间的关系图](#2-类之间的关系图)
3. [与 `interfaces.py` 中 ABC 的对应关系](#3-与-interfacespy-中-abc-的对应关系)
4. [关键设计模式](#4-关键设计模式)
5. [复杂度最高的方法深度分析](#5-复杂度最高的方法深度分析)
6. [潜在问题或改进建议](#6-潜在问题或改进建议)

---

## 1. 每个实现类的详细分析

### 1.1 CodexDelegate (IF-1: HostDelegate)

**继承关系**: `CodexDelegate` → `HostDelegate(ABC)`

**职责**: 为 Codex host 提供 hook 事件委托执行能力。通过调用 `cmux codex-hook` CLI 将事件转发给外部运行时。

**构造函数**:
```python
def __init__(
    self,
    surface_id: str | None = None,
    which_cmd: Callable[[str], str | None] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
):
```
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `surface_id` | `str \| None` | `None` | 表面标识符，回退到环境变量 `CMUX_SURFACE_ID` |
| `which_cmd` | `Callable[[str], str\|None] \| None` | `None` | 命令查找函数，回退到 `shutil.which` |
| `runner` | `Callable[..., subprocess.CompletedProcess[str]] \| None` | `None` | 进程运行器，回退到 `subprocess.run` |

**实例属性**:
- `self.surface_id`: `str | None` — 由参数或环境变量决定
- `self._which`: `Callable` — 命令查找
- `self._runner`: `Callable` — 子进程运行器

**方法分析**:

| 方法 | 签名 | 返回值 | 说明 |
|------|------|--------|------|
| `can_handle` | `() -> bool` | `bool` | 检查 `cmux` 命令是否存在 **且** `surface_id` 非空 |
| `execute` | `(event, raw_payload, payload) -> subprocess.CompletedProcess[str]` | 子进程结果 | 前置检查 `cmux` 和 `surface_id`，任一缺失返回 noop；否则执行 `cmux codex-hook {event}`，stdin 传入 `raw_payload` |
| `noop_response` | `() -> subprocess.CompletedProcess[str]` | `CompletedProcess` | 返回 returncode=0, stdout="{}\n" 的空响应 |

**关键逻辑**:
- `execute` 中 `check=False` 表示不抛出异常，调用方需检查 `returncode`
- 注入依赖 (`which_cmd`, `runner`) 支持单元测试隔离外部进程
- Codex 的 noop 返回 `"{}\n"` (空 JSON)，与 Claude 的空字符串不同

---

### 1.2 ClaudeDelegate (IF-1: HostDelegate)

**继承关系**: `ClaudeDelegate` → `HostDelegate(ABC)`

**职责**: 为 Claude host 提供 hook 事件委托。调用 `cmux claude-hook` CLI，并额外记录状态文件。

**构造函数**:
```python
def __init__(
    self,
    workspace_id: str | None = None,
    surface_id: str | None = None,
    state_file: str | None = None,
    repo_root: Path | None = None,
    which_cmd: Callable[[str], str | None] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    state_path_factory: Callable[[Path], Path] | None = None,
    canonicalizer: Callable[[str, str], tuple[str, str]] | None = None,
    state_recorder: Callable[..., Any] | None = None,
):
```

| 参数 | 说明 |
|------|------|
| `workspace_id` | 工作区 ID，回退到 `CMUX_WORKSPACE_ID` |
| `surface_id` | 表面 ID，回退到 `CMUX_SURFACE_ID` |
| `state_file` | 状态文件路径（**必须由 adapter policy 注入**，不能直接读环境变量） |
| `repo_root` | 仓库根路径 |
| `state_path_factory` | 状态路径工厂函数 |
| `canonicalizer` | 规范化器：`(workspace_id, surface_id) -> (workspace_ref, surface_ref)` |
| `state_recorder` | 状态记录器回调 |

**方法分析**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `can_handle` | `() -> bool` | 三个条件：`cmux` 存在 **且** `workspace_id` 非空 **且** `surface_id` 非空 |
| `execute` | `(event, raw_payload, payload) -> subprocess.CompletedProcess[str]` | 1. 三项前置检查 2. 解析 `state_file`（参数→factory→默认函数）3. 规范化 ID（canonicalizer 或原样）4. 调用 `record_hook_event` 写入状态 5. 执行 `cmux claude-hook {event} --workspace {ref} --surface {ref}` |
| `noop_response` | `() -> subprocess.CompletedProcess[str]` | 返回 stdout="" 空字符串（**不同于 Codex 的 `"{}\n"`**） |

**与 CodexDelegate 的差异**:
1. 多了 `workspace_id` 作为前置条件
2. 执行前需写入 hook 状态文件
3. 支持 `canonicalizer` 对 ID 进行规范化
4. CLI 参数多了 `--workspace` 和 `--surface`
5. noop 返回空字符串而非 `"{}\n"`

---

### 1.3 NoopHostDelegate (IF-1: HostDelegate)

**继承关系**: `NoopHostDelegate` → `HostDelegate(ABC)`

**职责**: 空操作委托，总是 `can_handle=True`，总是返回空 JSON 响应。用于降级/测试场景。

| 方法 | 实现 |
|------|------|
| `can_handle` | 永远返回 `True` |
| `execute` | 忽略所有参数，返回 `noop_response()` |
| `noop_response` | 返回 `returncode=0, stdout="{}\n"` |

---

### 1.4 `resolve_host_delegate` (工厂函数)

**签名**: `def resolve_host_delegate(host: str, mode: str = "auto") -> HostDelegate`

**模式**:
| 模式 | 行为 |
|------|------|
| `"auto"` | 尝试创建对应 delegate，如果 `can_handle()` 为 True 则返回，否则返回 `NoopHostDelegate` |
| `"noop"` | 始终返回 `NoopHostDelegate` |
| `"cmux"` | 始终返回对应的 cmux delegate（即使 `can_handle=False`） |
| 其他 | 等同于 `"auto"` |

**host 映射**:
- `"codex"` → `CodexDelegate()`
- `"claude"` → `ClaudeDelegate()`
- 其他 → 直接返回 `NoopHostDelegate()`

**设计意义**: 这是一个**策略工厂**，将 host 字符串映射到对应的 Delegate 实例，封装了创建逻辑和降级策略。

---

### 1.5 PolicyRegistryImpl (IF-2: PolicyRegistry)

**继承关系**: `PolicyRegistryImpl` → `PolicyRegistry(ABC)`

**职责**: 默认策略注册表实现，支持从磁盘加载 policy-pack JSON 文件进行运行时策略覆盖。

**类常量**:

| 常量 | 值 | 说明 |
|------|-----|------|
| `SCHEMA_VERSION` | `"m3-policy-pack-v1"` | Schema 版本标识 |
| `POLICY_PACK_PATH_ENV` | `"MEMORY_HOOK_POLICY_PACK_PATH"` | 环境变量名 |
| `DEFAULT_POLICY_PACK_PATH` | `.../memory/kb/global/memory-hook-policy-pack.json` | 默认策略包路径 |
| `DEFAULT_POLICIES` | `dict[str, str]` | 4 条默认策略 |
| `CONFLICT_STRATEGIES` | `dict[str, str]` | 7 条冲突解决策略 |

**默认策略**:
```python
{
    "registration_phase": "declared-not-enforced",
    "truth_basis_policy": "source-authority-evidence-conflict",
    "kb_write_mode": "read-first-CRUD",
    "kb_overwrite_allowed": "false",
}
```

**默认冲突策略**:
```python
{
    "legality_source": "fail-fast",
    "registration_commit": "preserve-and-escalate",
    "registration_phase": "prefer-strict",
    "truth_basis_policy": "prefer-strict",
    "kb_write_mode": "prefer-strict",
    "kb_overwrite_allowed": "prefer-strict",
    "default": "preserve-and-escalate",
}
```

**构造函数**:
```python
def __init__(
    self,
    policy_pack_path: Path | None = None,
    *,
    config: GatewayBusinessPolicyConfig | None = None,
    allowed_scopes: set[str] | None = None,
    scope_inherits: dict[str, str] | None = None,
    default_policies: dict[str, str] | None = None,
    conflict_strategies: dict[str, str] | None = None,
):
```

**策略包路径解析优先级**:
1. `config.policy_pack_path`（最高）
2. 直接参数 `policy_pack_path`
3. 环境变量 `MEMORY_HOOK_POLICY_PACK_PATH`
4. 默认文件路径 `DEFAULT_POLICY_PACK_PATH`（如果存在）
5. `None`（最低）

**方法分析**:

| 方法 | 签名 | 返回值 | 说明 |
|------|------|--------|------|
| `_load_dynamic_policy_pack` | `() -> None` | `None` | 从磁盘加载 JSON 策略包，覆盖 `self._schema_version`、`self._policies`、`self._conflict_strategies`。文件不存在或 JSON 解析失败时静默跳过 |
| `get_policy` | `(key: str) -> str \| None` | `str \| None` | 字典查找 |
| `validate` | `(context: dict[str, Any]) -> list[str]` | `list[str]` | 仅校验 `project_scope` 是否在 `allowed_scopes` 中，基础实现 |
| `get_policy_pack` | `(scope: str) -> dict[str, Any]` | `dict` | 返回包含 schema_version、scope、policies、conflict_strategies、default_strategy 的完整策略包；可选包含 `inherits` 字段 |
| `resolve_conflict` | `(policy_key, values, strategy) -> str` | `str` | 三种策略：`fail-fast`（抛异常）、`preserve-and-escalate`（返回第一个值）、`prefer-strict`（对布尔选"false"，对 phase 选"declared-not-enforced"） |

**Stub 方法**（返回空值，生产环境应委托给 `GatewayBusinessPolicy`）:

| 方法 | 返回 |
|------|------|
| `validate_project_map` | `[]` |
| `validate_unique_legal_system_contract` | `[]` |
| `governance_frozen_tuple_errors` | `[]` |
| `event_contract_blocker_errors` | `[]` |
| `git_registration_probe` | `{}` |
| `truth_basis_for_scope` | `{}` |
| `decision_refs_for_scope` | `[]` |
| `lesson_refs_for_scope` | `[]` |
| `docs_refs_for_scope` | `[]` |

---

### 1.6 RouteTargetPolicyImpl (IF-3: RouteTargetPolicy)

**继承关系**: `RouteTargetPolicyImpl` → `RouteTargetPolicy(ABC)`

**职责**: 将路由种类（`kind`）解析为具体目标路径。

**构造函数**:
```python
def __init__(
    self,
    workspace_root: Path,
    repo_root: Path,
    *,
    global_rule_path: Path | None = None,
    project_runtime_path: Path | None = None,
):
```

**内部路由表** (`self._routes`):
| kind | 路径 | 说明 |
|------|------|------|
| `fact` | `None` | 懒求值：`{workspace}/memory/log/{today}.md` |
| `global-rule` | `{workspace}/memory/kb/global/memory-routing.md` | 可覆盖 |
| `source-material` | `{workspace}/memory/docs/references` | |
| `project-runtime` | `{workspace}/projects` | 可覆盖 |
| `system-error` | `{workspace}/memory/system/errors.log` | |
| `invalid-memory` | `{workspace}/memory/archive/invalid` | |

**方法**:
- `resolve(kind: str) -> str`: 对 `fact` 类型进行懒求值（每次调用计算当天日期），其他类型查表。未知 kind 抛 `ValueError`。

**设计考量**: `fact` 类型使用懒求值避免跨午夜时日期过期。

---

### 1.7 WriteTargetPolicyImpl (IF-3: WriteTargetPolicy)

**继承关系**: `WriteTargetPolicyImpl` → `WriteTargetPolicy(ABC)`

**职责**: 提供所有写入目标路径的映射。

**构造函数**:
```python
def __init__(self, workspace_root: Path):
```

**内部目标表** (`self._targets`): 12 个键，其中 `fact` 为 `None`（懒求值），包含 `kb_policy` 嵌套字典。

| 键 | 路径 |
|----|------|
| `fact` | `{workspace}/memory/log/{today}.md` (懒求值) |
| `global_canonical` | `{workspace}/memory/kb/global` |
| `project_canonical` | `{workspace}/memory/kb/projects` |
| `decision` | `{workspace}/memory/kb/decisions` |
| `lesson` | `{workspace}/memory/kb/lessons` |
| `docs` | `{workspace}/memory/docs` |
| `action` | `{workspace}/memory/inbox.md` |
| `project_runtime` | `{workspace}/projects` |
| `artifacts` | `{workspace}/artifacts` |
| `system_error` | `{workspace}/memory/system/errors.log` |
| `invalid_memory` | `{workspace}/memory/archive/invalid` |
| `kb_policy` | `{"mode": "read-first-CRUD", ...}` |

**方法**:
- `get_targets() -> dict[str, Any]`: 深拷贝 `_targets`，如果 `fact` 为 None 则求值当天日期路径。

---

### 1.8 GatewayBusinessPolicyConfig (dataclass)

**类型**: `@dataclass(frozen=True)` — 不可变配置数据类

**职责**: 为 `GatewayBusinessPolicyImpl` 提供结构化配置载荷，替代旧版 37 个关键字参数。

**字段分组**（共 38 个字段）:

| 组别 | 关键字段数 | 说明 |
|------|------------|------|
| 路径配置 | 14 个 `Path`/`list[Path]` 字段 | repo_root, workspace_root, project_map_root, global_canonical 等 |
| 映射关系 | 5 个 `dict` 字段 | project_canonical, project_runtime_root, project_doc_refs 等 |
| 集合 | 6 个 `set[str]` 字段 | formal_source_types, formal_event_types, frozen_tuple_expected 等 |
| 回调 | 1 个 `Callable[[Path], str]` | read_text_if_exists_fn |
| 字符串 | 2 个 `str` | default_project_scope, policy_pack_path |

**不可变语义**: `frozen=True` 保证配置在运行时不被修改。

---

### 1.9 GatewayBusinessPolicyImpl (IF-3.5: GatewayBusinessPolicy)

**继承关系**: `GatewayBusinessPolicyImpl` → `GatewayBusinessPolicy(ABC)`

**职责**: 核心业务策略实现，负责项目范围判定、真相基础验证、project-map 合法性校验、governance/event contract 校验等。

**构造函数**:
```python
def __init__(
    self,
    config: GatewayBusinessPolicyConfig,
    scope_config_path: Path | None = None,
):
```
- 加载 scope overrides 配置文件（`_scope_config_path` 或环境变量 `MEMORY_HOOK_SCOPE_CONFIG_PATH`）
- 调用 `_load_scope_overrides()` 解析 JSON

**私有静态方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `_path_is_under` | `(path, root) -> bool` | 使用 `resolve().relative_to()` 检查路径包含关系（跟随符号链接） |
| `_path_is_under_lexical` | `(path, root) -> bool` | 使用 `expanduser().absolute().relative_to()` 词法检查（**不跟随符号链接**） |
| `_section_bullets` | `(text, heading) -> list[str]` | 从 Markdown 文本中提取指定标题下的 `-` 列表项 |
| `_section_body` | `(text, heading) -> str` | 提取指定标题下的正文（到下一个 `##` 为止） |
| `_markdown_code_tokens` | `(text) -> set[str]` | 提取 Markdown 反引号中的代码标记 |
| `_json_string_values` | `(text, key) -> set[str]` | 用正则提取 JSON 中指定 key 的字符串值 |
| `_json_object_keys` | `(text) -> set[str]` | 用正则提取 JSON 对象的所有 key |

**私有实例方法**:

| 方法 | 说明 |
|------|------|
| `_read_text_if_exists` | 调用 config 中的 `read_text_if_exists_fn` 读取文件 |
| `_existing_paths` | 过滤出不存在的路径 |
| `_classify_truth_ref` | 将路径分类为 15 种类型：legal-core, project-map-index, global-canonical, project-canonical, docs, project-runtime, artifact, tooling, log, system, app, agents, gpt-web-to, repo-policy, workspace-entry, other |
| `_authority_ref_allowed` | 检查 authority ref 是否在允许路径或 global_canonical 中 |
| `_lower_evidence_ref` | 检查路径是否属于任意 `lower_evidence_roots` |
| `_truth_basis_sections_for` | 从 Markdown truth canonical 文件中提取 4 个 section：source_refs, authority_refs, evidence_refs, conflict_status |
| `_truth_basis_errors_for` | **高复杂度方法**，验证 truth canonical 文件的完整性 |

**公开方法**:

| 方法 | 签名 | 返回值 | 说明 |
|------|------|--------|------|
| `determine_project_scope` | `(cwd: Path) -> str` | `str` | 根据 cwd 匹配 `scope_match_hints` 返回项目范围，未匹配返回默认 |
| `get_project_canonical` | `() -> dict[str, Path]` | `dict` | 合并 config 和 scope overrides |
| `get_project_runtime_root` | `() -> dict[str, Path]` | `dict` | 合并 config 和 scope overrides |
| `get_required_canonical` | `() -> list[Path]` | `list` | 返回 config.required_canonical |
| `get_global_canonical` | `() -> list[Path]` | `list` | 返回 config.global_canonical |
| `project_map_refs` | `() -> list[str]` | `list[str]` | 返回 project_map_files 路径字符串 |
| `validate_project_map_files` | `() -> list[str]` | `list[str]` | 校验 INDEX.md、legal-core-map.md、ingestion-registry-map.md、governance 文件的合法性声明 |
| `validate_unique_legal_system_contract` | `() -> list[str]` | `list[str]` | 校验 workspace index、docs index、global index、hook contract 中的法律声明 |
| `governance_frozen_tuple_blocker_errors` | `() -> list[str]` | `list[str]` | 检查治理文件中缺失/遗留的 frozen tuple 标记 |
| `event_contract_blocker_errors` | `() -> list[str]` | `list[str]` | **高复杂度方法**，校验事件契约文件中的 source_types, event_types, event_statuses 是否匹配，以及样本 JSON 是否使用正式字段 |
| `decision_refs_for_scope` | `(scope: str) -> list[str]` | `list[str]` | 合并 default 和 project-specific refs |
| `lesson_refs_for_scope` | `(scope: str) -> list[str]` | `list[str]` | 合并 default 和 project-specific refs |
| `docs_refs_for_scope` | `(scope: str) -> list[str]` | `list[str]` | 返回 project-specific refs |
| `truth_basis_for_scope` | `(scope: str) -> TruthBasis` | `TruthBasis` | **高复杂度方法**，构建 truth basis 包 |

---

### 1.10 ArtifactSinkImpl (IF-4: ArtifactSink)

**继承关系**: `ArtifactSinkImpl` → `ArtifactSink(ABC)`

**职责**: 将上下文包写入 JSON 快照文件、latest 指针文件和事件日志。

**构造函数**:
```python
def __init__(
    self,
    context_root: Path,
    event_log: Path,
    datetime_module: Any = datetime,
):
```

**方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `ensure_dirs` | `() -> None` | 创建 `context_root` 目录树 |
| `write` | `(package: dict) -> dict[str, str]` | 1. 生成时间戳 `YYYYMMDDTHHMMSSffffff` 2. 构造 `{timestamp}-{host}-{event}.json` 路径 3. 冲突时追加 `-{suffix:02d}` 序号 4. 写入 snapshot 和 latest 文件 5. 追加到 event_log (JSONL) 6. 返回 artifact 引用路径 |

**设计特性**:
- 防冲突文件名（递增序号）
- 同时维护快照和 latest 指针
- 事件日志为 JSONL 格式（逐行追加）

---

### 1.11 ErrorSinkImpl (IF-4: ErrorSink)

**继承关系**: `ErrorSinkImpl` → `ErrorSink(ABC)`

**职责**: 将错误日志追加到错误日志文件。

**构造函数**:
```python
def __init__(
    self,
    error_log: Path,
    now_iso_fn: Callable[[], str] | None = None,
):
```

**方法**:
- `log(component, message, context)`: 确保目录存在 → 将 context 序列化为排序 JSON → 写入 `[timestamp] [component] [error] message | context={json}` 格式

---

### 1.12 ArtifactWriter

**继承关系**: 独立类（不继承任何 ABC）

**职责**: 包装 `ArtifactSinkImpl`，提供非阻塞的错误处理。

**构造函数**:
```python
def __init__(
    self,
    context_root: Path,
    error_log: Path,
    datetime_module: Any = None,
):
```
内部创建 `ArtifactSinkImpl` 实例。

**方法**:
- `write(host, event, package) -> bool`: 设置 `host` 和 `event` 到 package → 调用 `_sink.write()` → 异常时调用 `_log_error()` 并返回 `False`
- `_log_error(host, event, exc)`: 写入错误日志
- `last_error` property: 返回最近一次错误

**设计意义**: 装饰器/适配器模式，在 `ArtifactSinkImpl` 之上增加了非阻塞错误处理层。

---

### 1.13 DelegateRouter

**继承关系**: 独立类（不继承任何 ABC）

**职责**: 根据 host 名称路由到对应的 Delegate 实例。

**构造函数**:
```python
def __init__(
    self,
    codex_delegate: CodexDelegate,
    claude_delegate: ClaudeDelegate,
):
```

**方法**:
- `route(host, event, raw_payload, payload) -> subprocess.CompletedProcess[str]`: 根据 host 分发到对应 delegate 的 `execute()`，未知 host 抛 `ValueError`
- `noop(host) -> subprocess.CompletedProcess[str]`: 根据 host 分发到对应 delegate 的 `noop_response()`，未知 host 抛 `ValueError`

**设计意义**: 路由/分发器模式，将 host 字符串映射到具体 Delegate 方法调用。

---

### 1.14 PathUtilsImpl (IF-6: PathUtils)

**继承关系**: `PathUtilsImpl` → `PathUtils(ABC)`

**职责**: 路径相关工具回调。

**构造函数**:
```python
def __init__(self, workspace_root: Path):
```

**方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `extract_excerpt` | `(path, max_lines=12) -> list[str]` | 读取文件，去除空白行，返回前 N 行非空内容 |
| `write_targets` | `() -> dict[str, Any]` | 返回与 `WriteTargetPolicyImpl` 完全相同的目标映射表 |

---

## 2. 类之间的关系图

```
                      ┌─────────────────────────┐
                      │    memory_hook_interfaces.py (ABC/Protocol)
                      ├─────────────────────────┤
                      │  HostDelegate (ABC)     │
                      │  PolicyRegistry (ABC)    │
                      │  RouteTargetPolicy (ABC) │
                      │  WriteTargetPolicy (ABC) │
                      │  GatewayBusinessPolicy(ABC)
                      │  ArtifactSink (ABC)      │
                      │  ErrorSink (ABC)         │
                      │  PathUtils (ABC)         │
                      │  PolicyQueryProvider     │
                      │  GovernanceChecker       │
                      │  TruthBasisProvider      │
                      └────────┬────────────────┘
                               │ implements
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
   ┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐
   │CodexDelegate │  │PolicyRegistryImpl│  │RouteTargetPolicyImpl
   │ClaudeDelegate│  │                  │  │WriteTargetPolicyImpl
   │NoopHostDelegate│                   │  │GatewayBusinessPolicyImpl
   └──────┬───────┘  └────────┬────────┘  │ArtifactSinkImpl    │
          │                   │           │ErrorSinkImpl       │
          │            ┌──────┴──────┐    │PathUtilsImpl       │
          │            │GatewayBusiness│   └──────────────────┘
          │            │PolicyConfig  │
          │            │(frozen dataclass)
          │            └─────────────┘
          │
          ▼
   ┌─────────────┐     uses     ┌───────────────┐
   │DelegateRouter├────────────►│CodexDelegate  │
   │ArtifactWriter├────────────►│ClaudeDelegate  │
   └─────────────┘     uses     └───────────────┘
                               uses
                          ┌──────────────┐
                          │ArtifactSinkImpl│
                          └──────────────┘

resolve_host_delegate(host, mode) ── Factory ──► HostDelegate instances
```

**使用关系**:
- `DelegateRouter` 持有 `CodexDelegate` + `ClaudeDelegate`
- `ArtifactWriter` 内部持有 `ArtifactSinkImpl`
- `GatewayBusinessPolicyImpl` 持有 `GatewayBusinessPolicyConfig`
- `PolicyRegistryImpl` 的 `_load_dynamic_policy_pack` 读取磁盘 JSON

---

## 3. 与 `interfaces.py` 中 ABC 的对应关系

| 接口 (ABC) | 实现类 | 实现完整度 | 备注 |
|-----------|--------|-----------|------|
| `HostDelegate` | `CodexDelegate` | ✅ 完整 | |
| `HostDelegate` | `ClaudeDelegate` | ✅ 完整 | |
| `HostDelegate` | `NoopHostDelegate` | ✅ 完整 | 降级实现 |
| `PolicyRegistry` | `PolicyRegistryImpl` | ⚠️ 部分 | 核心方法已实现，9 个 stub 方法返回空值 |
| `RouteTargetPolicy` | `RouteTargetPolicyImpl` | ✅ 完整 | |
| `WriteTargetPolicy` | `WriteTargetPolicyImpl` | ✅ 完整 | |
| `GatewayBusinessPolicy` | `GatewayBusinessPolicyImpl` | ✅ 完整 | |
| `ArtifactSink` | `ArtifactSinkImpl` | ✅ 完整 | |
| `ErrorSink` | `ErrorSinkImpl` | ✅ 完整 | |
| `PathUtils` | `PathUtilsImpl` | ✅ 完整 | |

**Protocol 接口** (structural typing, 不需要显式实现):

| Protocol | 隐式匹配 |
|----------|---------|
| `PolicyQueryProvider` | `PolicyRegistryImpl` (部分), `GatewayBusinessPolicyImpl` (需扩展) |
| `GovernanceChecker` | `GatewayBusinessPolicyImpl`, `PolicyRegistryImpl` (stub) |
| `TruthBasisProvider` | `GatewayBusinessPolicyImpl` |

**注意**: `interfaces.py` 定义了 3 个细粒度 Protocol（`PolicyQueryProvider`、`GovernanceChecker`、`TruthBasisProvider`）作为 `PolicyRegistry` 的功能分解，但 `memory_hook_impls.py` 中**没有**专门实现这些 Protocol 的独立类。

---

## 4. 关键设计模式

### 4.1 策略模式 (Strategy Pattern)

**体现**: `HostDelegate` 接口族

```
                    HostDelegate (ABC)
                         /    |    \
                    Codex  Claude  Noop
```

每个 `HostDelegate` 实现是处理不同宿主环境的策略。`DelegateRouter` 根据 `host` 字符串选择策略。

### 4.2 工厂模式 (Factory Pattern)

**体现**: `resolve_host_delegate(host, mode) -> HostDelegate`

根据 host 名称和 mode 创建不同的 Delegate 实例，封装了：
- 实例化逻辑
- 降级策略（auto 模式下 can_handle 检查）
- 未知 host 的兜底处理

### 4.3 委托模式 (Delegation Pattern)

**体现**: `DelegateRouter.route()` 将调用委托给具体 Delegate 的 `execute()`

### 4.4 适配器模式 (Adapter Pattern)

**体现**: `ArtifactWriter` 包装 `ArtifactSinkImpl`
- 提供非阻塞错误处理
- 将 `host`/`event` 注入到 package 中
- 对外暴露 `bool` 返回值，内部消化异常

### 4.5 装饰器模式 (Decorator Pattern)

**体现**: `ArtifactWriter` 在 `ArtifactSinkImpl` 之上增加了错误捕获层

### 4.6 依赖注入 (Dependency Injection)

**多处体现**:
1. `CodexDelegate.__init__` 接受 `which_cmd` 和 `runner` 可调用对象，便于测试时 mock 子进程
2. `ClaudeDelegate` 接受 `canonicalizer`、`state_recorder`、`state_path_factory` 回调
3. `GatewayBusinessPolicyConfig` 持有 `read_text_if_exists_fn` 回调
4. `ArtifactSinkImpl` 接受 `datetime_module` 参数以支持测试时间模拟
5. `ErrorSinkImpl` 接受 `now_iso_fn` 参数

### 4.7 策略优先级/配置解析链 (Chain of Responsibility)

**体现**: `PolicyRegistryImpl` 的 `_policy_pack_path` 解析
```
config.policy_pack_path → 直接参数 → 环境变量 → 默认文件 → None
```

### 4.8 策略模式 - 冲突解决

**体现**: `PolicyRegistryImpl.resolve_conflict()` 支持三种策略：
- `fail-fast`: 立即抛出异常
- `preserve-and-escalate`: 返回第一个值
- `prefer-strict`: 选择更严格的值

### 4.9 数据类配置模式 (Configuration Dataclass)

**体现**: `GatewayBusinessPolicyConfig` 使用 `@dataclass(frozen=True)` 提供不可变配置，替代 37 个关键字参数。

### 4.10 懒求值 (Lazy Evaluation)

**体现**: `RouteTargetPolicyImpl` 和 `WriteTargetPolicyImpl` 中的 `fact` 路径
- 初始化为 `None`
- 在 `resolve()`/`get_targets()` 时才计算当天日期
- 避免跨午夜时日期过期

### 4.11 兼容回退模式 (Graceful Degradation)

**体现**: `NoopHostDelegate` 总是返回 `can_handle=True`，在 `resolve_host_delegate` auto 模式下作为最终兜底。

---

## 5. 复杂度最高的方法深度分析

### 5.1 `_truth_basis_errors_for` — 真相基础验证器

**行数**: 约 85 行
**圈复杂度**: 估计 15+
**责任**: 验证 truth canonical Markdown 文件的完整性和一致性

**流程**:
```
1. 检查文件是否存在 → 缺失则返回错误
2. 读取文本 → 检查是否包含 "Truth Basis" 标题
3. 提取 4 个 section (source_refs, authority_refs, evidence_refs, conflict_status)
4. 验证 4 个 section 都存在
5. 验证 conflict_status == ["resolved"]
6. 将 ref 字符串解析为 Path 对象
7. 验证所有 ref 在仓库内且存在于磁盘
8. 验证 source_refs ≠ evidence_refs（不能相同）
9. 验证 source_refs ∩ authority_refs = ∅（不能重叠）
10. 验证 authority_refs ∩ evidence_refs = ∅（不能重叠）
11. 验证每个 authority_path 是 formal canonical
12. 验证 source_refs 不全来自 canonical/legal-core/project-map-index（必须有非标准来源）
13. 验证 evidence_refs 包含至少一个 lower-layer ref
```

**复杂度来源**:
- 多层嵌套的条件判断
- 路径解析逻辑（相对路径 vs 绝对路径）
- 多集合操作（交集、差集、成员检查）
- 多个独立的业务规则验证

### 5.2 `event_contract_blocker_errors` — 事件契约校验器

**行数**: 约 95 行
**圈复杂度**: 估计 20+
**责任**: 校验多个文档文件中的 source_types、event_types、event_statuses 是否一致，并校验样本 JSON

**流程**:
```
1. 读取 5 个契约文件 (upstream_standard, upstream_mapping, formal_contract, upstream_samples, downstream_samples)
2. 检查缺失文件
3. 对 3 个正式文档分别提取：
   a. Markdown 章节中的 code tokens
   b. 与 formal_sets 取交集
   c. 与期望值比较
4. 对 2 个样本 JSON 分别提取：
   a. source_type 字符串值
   b. event_type 字符串值
   c. event_status 字符串值
   d. 字段 keys
5. 验证样本中的值是否在正式集合内
6. 验证样本包含所有正式字段
7. 验证样本不使用遗留字段
```

**复杂度来源**:
- 嵌套字典结构（formal_sets, sample_sets, expected_formal_sets）
- 多次 Markdown 解析 + 正则提取
- 集合比较逻辑
- 多文档、多字段的交叉验证

### 5.3 `validate_project_map_files` — Project-map 校验器

**行数**: 约 40 行
**圈复杂度**: 估计 18
**责任**: 校验 4 个 project-map 契约文件是否包含所有必需的合法性声明文本

**流程**:
```
对 4 个文件分别进行 2-5 个字符串包含检查：
- INDEX.md: 5 个检查（唯一合法入口、active-legal、git-commit gate、无 round/waves 引用）
- legal-core-map.md: 3 个检查（active-legal、map-only、无 round/waves）
- ingestion-registry-map.md: 3 个检查（scope 分类、absorbed/retired、git-commit gate）
- governance: 4 个检查（清洗规则、map grants legality、atomic registration、无 wave 推进）
```

**复杂度来源**: 大量的中文字符串匹配，业务规则密集。

### 5.4 `execute` (ClaudeDelegate) — Claude 委托执行

**行数**: 约 40 行
**圈复杂度**: 估计 10
**责任**: Claude host 的事件执行，包括状态文件解析、ID 规范化、状态记录、CLI 调用

**流程**:
```
1. 三项前置检查 (cmux, workspace_id, surface_id)
2. 解析 state_file: 参数 → state_path_factory → 默认函数
3. 规范化 ID: canonicalizer 或原样使用
4. 确定 recorder: 参数或动态导入 record_hook_event
5. 调用 recorder 记录状态
6. 调用 cmux claude-hook CLI
```

**复杂度来源**: 多个可选参数分支，动态导入，运行时回退链。

---

## 6. 潜在问题或改进建议

### 6.1 高优先级

**P1: `PolicyRegistryImpl` 的 stub 方法未委托给真实实现**

`PolicyRegistryImpl` 中有 9 个方法返回空值（`[]`, `{}`, `True`）。根据注释这些"应该委托给 `GatewayBusinessPolicy`"。但在实际使用中如果 caller 直接调用 `PolicyRegistryImpl` 的 `truth_basis_for_scope()`，会得到空结果而不是错误。

**建议**: 在 stub 方法中抛出 `NotImplementedError` 或至少记录 warning，而不是静默返回空值。

**P2: `_truth_basis_errors_for` 中路径解析逻辑复杂且易错**

```python
source_paths = [
    (self._config.repo_root / Path(item).expanduser()).resolve()
    if not Path(item).expanduser().is_absolute()
    else Path(item).expanduser()
    for item in source_refs
]
```

这行列表推导式同时执行了路径拼接、绝对化、resolve 三种操作，嵌套在条件表达式中，可读性差且可能产生重复调用 `expanduser()` 的性能问题。

**建议**: 提取为 `_resolve_ref_path(ref_str: str) -> Path` 辅助方法。

**P3: `resolve_host_delegate` 中未知 mode 等同于 "auto"**

```python
elif mode == "cmux":
    return cmux_delegate
else:
    # "auto" or unknown mode
```

当用户传入错误的 mode 名称时（如 `"cmx"` 拼写错误），静默降级到 auto 行为而不是报错。

**建议**: 对未知 mode 抛出 `ValueError(f"unknown mode: {mode}")`。

### 6.2 中优先级

**P4: `GatewayBusinessPolicyConfig` 字段过多（38 个）**

虽然使用 dataclass 分组，但 38 个字段意味着构造成本高，且任何新增字段都需要更新所有实例化点。

**建议**: 考虑进一步拆分为子配置类，如 `PathsConfig`、`PolicyStringsConfig`、`ContractConfig` 等，再组合到顶层 config 中。

**P5: `GatewayBusinessPolicyImpl` 包含大量 Markdown/JSON 解析逻辑**

该类同时承担：
- 策略配置管理
- 项目范围判定
- Markdown 文件解析
- JSON 正则提取
- 真相基础验证

违反了单一职责原则。

**建议**: 将 `_section_bullets`、`_section_body`、`_markdown_code_tokens`、`_json_string_values`、`_json_object_keys` 提取到独立的 `MarkdownUtils` 或 `ContractParser` 工具类中。

**P6: `ArtifactWriter` 和 `DelegateRouter` 未实现任何 ABC 接口**

这两个类是独立的组合类，没有实现接口。如果后续有替代实现，无法通过接口切换。

**建议**: 如果预期有替代实现，考虑定义 `ArtifactWriter` 和 `DelegateRouter` 的抽象接口。如果确定只有一种实现，当前设计可以接受。

### 6.3 低优先级

**P7: `ArtifactSinkImpl.write` 中的文件名冲突处理使用 `while` 循环**

在高并发场景下，如果多个进程同时写入，`while snapshot_path.exists()` 可能导致序号快速递增。

**建议**: 考虑使用 UUID 或纳秒时间戳来避免冲突，或使用文件锁。

**P8: `_load_dynamic_policy_pack` 静吞异常**

```python
except (OSError, json.JSONDecodeError):
    return
```

文件读取失败或 JSON 解析失败时完全静默，使用者无法知道策略包是否被加载。

**建议**: 至少记录 debug/warning 日志。

**P9: 硬编码的中文字符串验证**

`validate_project_map_files` 和 `validate_unique_legal_system_contract` 中大量硬编码中文字符串（如 `"唯一合法入口"`、`"只有出现在合法目录地图中..."`）。

**建议**: 将这些验证字符串提取到配置或常量文件中，便于维护和国际化。

**P10: `write_targets` 方法在 `PathUtilsImpl` 和 `WriteTargetPolicyImpl` 中重复**

两者的返回完全相同。

**建议**: 让 `PathUtilsImpl.write_targets()` 委托给 `WriteTargetPolicyImpl`，或提取到共享函数。

---

## 附录：文件导入关系

```
memory_hook_impls.py
  ├── memory_hook_interfaces.py (ABC/Protocol/TypedDict 定义)
  │     ├── HostDelegate, PolicyRegistry, RouteTargetPolicy
  │     ├── WriteTargetPolicy, GatewayBusinessPolicy
  │     ├── ArtifactSink, ErrorSink, PathUtils
  │     ├── TruthBasis, RegistrationCommitGate (TypedDict)
  │     └── PolicyQueryProvider, GovernanceChecker, TruthBasisProvider (Protocol)
  ├── _validation_constants.py (MKR_* 和 SEC_* 常量)
  ├── cmux_hook_state.py (default_hook_state_path, record_hook_event)
  ├── subprocess (进程调用)
  ├── json (数据序列化)
  └── datetime (时间戳生成)
```

## 附录：测试友好性评估

| 类 | 测试友好性 | 原因 |
|----|-----------|------|
| `CodexDelegate` | ✅ 高 | 完全注入 `which_cmd` 和 `runner` |
| `ClaudeDelegate` | ✅ 高 | 6 个可注入回调点 |
| `NoopHostDelegate` | ✅ 高 | 无外部依赖 |
| `PolicyRegistryImpl` | ✅ 高 | 可注入 `default_policies`, `conflict_strategies` |
| `RouteTargetPolicyImpl` | ✅ 高 | 可覆盖路径参数 |
| `WriteTargetPolicyImpl` | ✅ 高 | 仅依赖 `workspace_root` |
| `GatewayBusinessPolicyImpl` | ⚠️ 中 | 依赖 38 字段 config 构造，但所有文件 I/O 通过 `read_text_if_exists_fn` 注入 |
| `ArtifactSinkImpl` | ✅ 高 | 可注入 `datetime_module` |
| `ErrorSinkImpl` | ✅ 高 | 可注入 `now_iso_fn` |
| `ArtifactWriter` | ✅ 高 | 非阻塞设计，可注入 `datetime_module` |
| `DelegateRouter` | ✅ 高 | 依赖注入具体 Delegate |
| `PathUtilsImpl` | ✅ 高 | 仅依赖 `workspace_root` |
