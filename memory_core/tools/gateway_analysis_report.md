# Gateway 门面模块深度分析报告

## 文件清单

| 文件 | 大小/行数 | 角色 |
|------|-----------|------|
| `memory_hook_gateway.py` | ~40KB | 主门面模块 |
| `memory_hook_provider_probe.py` | ~1.5KB | 提供者探测工具 |
| `memory_hook_provider_rollback.py` | ~1.5KB | 回退演练工具 |

---

## 一、逐函数详细分析 (memory_hook_gateway.py)

### 1. 模块初始化与导入区 (L1-L78)

#### 1.1 标准库导入
```
argparse, json, os, re, subprocess, sys, datetime, pathlib.Path, typing.Any/Callable
```

#### 1.2 根目录发现
```python
discover_roots(Path.cwd()) → (REPO_ROOT, WORKSPACE_ROOT)
```
- 使用相对或绝对导入兼容两种运行模式（包内 / 独立脚本）

#### 1.3 核心路径常量
| 常量 | 路径 | 用途 |
|------|------|------|
| `ARTIFACT_ROOT` | `{WORKSPACE}/artifacts/memory-hook` | 工件根目录 |
| `CONTEXT_ROOT` | `{ARTIFACT_ROOT}/contexts` | 上下文快照存储 |
| `EVENT_LOG` | `{ARTIFACT_ROOT}/events.jsonl` | 事件日志 (JSONL) |
| `ERROR_LOG` | `{WORKSPACE}/memory/system/errors.log` | 错误日志 |
| `CLAUDE_HOOK_STATE_DIR` | `~/.agents/skills/cmux/scripts` | Claude Hook 状态 |

#### 1.4 条件导入 (双路径兼容)
采用 `try: from .xxx import ... except ImportError: from memory_core.tools.xxx import ...` 模式，同时支持：
- **包内运行**：相对导入 (`from .xxx`)
- **独立脚本运行**：绝对导入 (`from memory_core.tools.xxx`)

导入的关键模块：
| 模块 | 导入内容 | 职责 |
|------|----------|------|
| `memory_hook_adapters.workbot_policy` | `WorkbotGatewayBusinessPolicy` | Workbot 业务策略实现 |
| `memory_hook_adapters.workbot_runtime_profile` | `build_workbot_runtime_profile` | 运行时配置构建 |
| `memory_hook_config` | `CoreConfig` | 核心配置数据类 |
| `memory_hook_core` | `build_context_package_core`, `build_context_package_from_config` | 上下文包核心构建 |
| `memory_hook_impls` | 10 个实现类/函数 | 接口实现 |
| `memory_hook_interfaces` | 7 个接口 | 抽象契约 |
| `memory_hook_schema` | `convert_legacy_to_memory_v1`, `convert_to_v1` | Schema 转换 |

#### 1.5 Adapter 动态加载机制 (L56-L78)
```python
_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "workbot")
_ADAPTER_REGISTRY = {
    "workbot": (".memory_hook_adapters.workbot_runtime_profile", "build_workbot_runtime_profile"),
}
```
- 从环境变量获取 adapter 名称，默认 "workbot"
- 通过 `importlib.import_module` 动态加载
- 失败时回退到绝对导入
- `_adapter_config: dict[str, Any]` 存储运行时配置

---

### 2. 配置加载层

#### 2.1 `load_adapter_config(profile: dict[str, Any]) -> None`
| 项目 | 说明 |
|------|------|
| **签名** | `def load_adapter_config(profile: dict[str, Any]) -> None` |
| **参数** | `profile` — 运行时配置字典（来自 adapter profile 函数） |
| **返回值** | `None` |
| **核心逻辑** | 1. `clear()` 清空旧配置；2. `update()` 写入新配置到 `_adapter_config`；3. `globals().update(profile)` 向后兼容暴露为模块级全局变量 |
| **边界条件** | 如果 profile 的 key 与已有模块全局变量同名，会被覆盖 |
| **依赖关系** | 依赖全局变量 `_adapter_config`，影响所有后续使用 `_adapter_config.get()` 的函数 |

**注意事项**：`globals().update()` 是反模式，虽然用于向后兼容，但会导致命名空间污染和难以追踪的 bug。

#### 2.2 模块级初始化
```python
_adapter_profile = _fn(REPO_ROOT, WORKSPACE_ROOT)
load_adapter_config(_adapter_profile)
```
- 在模块加载时立即执行，无法延迟
- `_fn` 来自 adapter 注册表的动态导入结果
- 这意味着测试时需要特殊处理（mock 整个模块导入）

---

### 3. 门面模式层 — 内部 Facade 函数

#### 3.1 `__all__` 导出声明
```python
__all__ = [
    'build_context_package',
    'build_context_package_simple',
    'ArtifactWriter',
    'DelegateRouter',
]
```

#### 3.2 策略单例初始化 (L98-L100)
```python
_default_policy_registry: PolicyRegistry | None = None
_default_route_policy: RouteTargetPolicy | None = None
_default_write_policy: WriteTargetPolicy | None = None
```
三个策略对象使用模块级变量作为单例存储，延迟初始化。

---

### 4. 业务策略构建

#### 4.1 `_build_gateway_business_policy() -> GatewayBusinessPolicy`

| 项目 | 说明 |
|------|------|
| **签名** | `def _build_gateway_business_policy() -> GatewayBusinessPolicy` |
| **参数** | 无（隐式依赖 ~30 个模块级常量） |
| **返回值** | `GatewayBusinessPolicy` 实例 |
| **核心逻辑** | 1. 构建 `GatewayBusinessPolicyConfig`，传入所有配置常量；2. 从 `_adapter_config` 获取策略类或使用默认 `WorkbotGatewayBusinessPolicy`；3. 实例化并返回 |
| **边界条件** | 要求所有模块级常量 (PROJECT_MAP_ROOT, TRUTH_MODEL 等) 在调用前已定义 |
| **异常处理** | 无显式异常处理，依赖常量存在 |

**隐式依赖的常量清单**（未在文件中定义，需通过 adapter profile 注入）：
`PROJECT_MAP_ROOT`, `PROJECT_MAP_FILES`, `PROJECT_MAP_GOVERNANCE`, `TRUTH_MODEL`, `GLOBAL_CANONICAL`, `AUTHORITY_ALLOWED_PATHS`, `LOWER_EVIDENCE_ROOTS`, `LEGAL_CORE_MARKERS`, `REQUIRED_REGISTRY_SCOPES`, `PROJECT_CANONICAL`, `PROJECT_RUNTIME_ROOT`, `PROJECT_DOC_REFS`, `DEFAULT_DECISION_REFS`, `PROJECT_DECISION_REFS`, `DEFAULT_LESSON_REFS`, `PROJECT_LESSON_REFS`, `GOVERNANCE_FROZEN_TUPLE_FILES`, `EVENT_CONTRACT_FILES`, `FROZEN_TUPLE_EXPECTED`, `FROZEN_TUPLE_LEGACY_MARKERS`, `FORMAL_SOURCE_TYPES`, `FORMAL_EVENT_TYPES`, `FORMAL_EVENT_STATUSES`, `FORMAL_FIELD_KEYS`, `LEGACY_FIELD_KEYS`, `REQUIRED_CANONICAL`, `HOOK_CONTRACT_PATH`, `DEFAULT_PROJECT_SCOPE`, `SCOPE_MATCH_HINTS`, `POLICY_PACK_PATH`, `POLICY_ALLOWED_SCOPES`, `POLICY_SCOPE_INHERITS`, `GLOBAL_RULE_PATH`, `ROUTE_PROJECT_RUNTIME_SCOPE`, `REGISTRATION_GIT_SCOPE`, `REGISTRATION_COMMIT_PHASE`, `REGISTRATION_COMMIT_POLICY`, `LEGALITY_SOURCE_POLICY`, `GOVERNANCE_BLOCKER_SCOPES`, `EVENT_CONTRACT_BLOCKER_SCOPES`, `CORE_EVIDENCE_REFS`

#### 4.2 `_get_gateway_business_policy() -> GatewayBusinessPolicy`

| 项目 | 说明 |
|------|------|
| **签名** | `def _get_gateway_business_policy() -> GatewayBusinessPolicy` |
| **返回值** | 新的 `GatewayBusinessPolicy` 实例（每次调用新建） |
| **核心逻辑** | 直接调用 `_build_gateway_business_policy()`，**不做单例缓存** |
| **设计决策** | 注释明确说明：不做缓存是为了让测试和运行时可以 monkeypatch 常量后立即生效 |

---

### 5. 核心构建器解析

#### 5.1 `CoreBuilder` 类型别名
```python
CoreBuilder = Callable[..., dict[str, Any]]
```

#### 5.2 `_load_external_core_builder() -> CoreBuilder`

| 项目 | 说明 |
|------|------|
| **签名** | `def _load_external_core_builder() -> CoreBuilder` |
| **返回值** | 可调用的核心构建函数 |
| **核心逻辑** | 1. 从环境变量 `MEMORY_HOOK_EXTERNAL_CORE_MODULE` (默认 `"memory_core.tools.memory_hook_core"`) 获取模块名；2. 从 `MEMORY_HOOK_EXTERNAL_CORE_FUNC` (默认 `"build_context_package_core"`) 获取函数名；3. 动态导入并返回函数 |
| **异常处理** | `TypeError` — 如果导入的对象不可调用 |
| **依赖关系** | 依赖 `__import__` 和 `getattr` 动态机制 |

#### 5.3 `_resolve_core_builder(provider, *, allow_fallback=True) -> tuple[str, CoreBuilder, list[str]]`

| 项目 | 说明 |
|------|------|
| **签名** | `def _resolve_core_builder(provider: str, *, allow_fallback: bool = True) -> tuple[str, CoreBuilder, list[str]]` |
| **参数** | `provider` — 提供者名称 ("external-core" / "legacy")；`allow_fallback` — 是否允许失败时回退 |
| **返回值** | 三元组 `(提供者名, 构建函数, 错误信息列表)` |
| **核心逻辑** | 1. 若 `provider == "external-core"`：尝试加载外部构建器；2. 失败时：若 `allow_fallback=True`，回退到 legacy 并记录错误；否则抛出异常；3. 若 `provider == "legacy"`：直接返回 legacy 构建器 |
| **边界条件** | external-core 加载失败时不一定会报错，可能静默回退 |
| **异常处理** | 捕获所有 `Exception`，根据 `allow_fallback` 决定处理方式 |

**设计意义**：这是整个系统的 Provider 双模式核心，支持 "legacy" 和 "external-core" 两种核心构建器，带 fallback 能力。

---

### 6. 策略门面 — 单例 Getter 函数

#### 6.1 `_get_policy_registry() -> PolicyRegistry`

| 项目 | 说明 |
|------|------|
| **签名** | `def _get_policy_registry() -> PolicyRegistry` |
| **返回值** | `PolicyRegistry` 单例 |
| **核心逻辑** | 懒加载单例：首次调用时创建 `PolicyRegistryImpl(policy_pack_path, allowed_scopes, scope_inherits)` |
| **依赖** | 模块级常量 `POLICY_PACK_PATH`, `POLICY_ALLOWED_SCOPES`, `POLICY_SCOPE_INHERITS` |

#### 6.2 `_get_route_policy() -> RouteTargetPolicy`

| 项目 | 说明 |
|------|------|
| **签名** | `def _get_route_policy() -> RouteTargetPolicy` |
| **返回值** | `RouteTargetPolicy` 单例 |
| **核心逻辑** | 懒加载单例：创建 `RouteTargetPolicyImpl(WORKSPACE_ROOT, REPO_ROOT, global_rule_path, project_runtime_path)` |

#### 6.3 `_get_write_policy() -> WriteTargetPolicy`

| 项目 | 说明 |
|------|------|
| **签名** | `def _get_write_policy() -> WriteTargetPolicy` |
| **返回值** | `WriteTargetPolicy` 单例 |
| **核心逻辑** | 懒加载单例：创建 `WriteTargetPolicyImpl(WORKSPACE_ROOT)` |

#### 6.4 `_get_artifact_sink() -> ArtifactSink`

| 项目 | 说明 |
|------|------|
| **签名** | `def _get_artifact_sink() -> ArtifactSink` |
| **返回值** | 新的 `ArtifactSinkImpl` 实例（**非单例，每次新建**） |
| **参数** | `CONTEXT_ROOT`, `EVENT_LOG`, `datetime_module=datetime` |

#### 6.5 `_get_error_sink() -> ErrorSink`

| 项目 | 说明 |
|------|------|
| **签名** | `def _get_error_sink() -> ErrorSink` |
| **返回值** | 新的 `ErrorSinkImpl` 实例（**非单例**） |

#### 6.6 `_get_host_delegate(host: str) -> HostDelegate`

| 项目 | 说明 |
|------|------|
| **签名** | `def _get_host_delegate(host: str) -> HostDelegate` |
| **参数** | `host` — 主机名 ("codex" / "claude") |
| **返回值** | `HostDelegate` 实例 |
| **核心逻辑** | 委托给 `resolve_host_delegate(host, mode="auto")` |

---

### 7. IF-5 门面适配器函数 (策略门面封装)

这些函数是 "IF-5" 接口适配层，将底层策略封装为简单函数调用：

#### 7.1 `_resolve_route_target_via_policy(kind: str) -> str`
- 通过 `_get_route_policy().resolve(kind)` 解析路由目标

#### 7.2 `_write_targets_via_policy() -> dict[str, Any]`
- 通过 `_get_write_policy().get_targets()` 获取写入目标

#### 7.3 `_get_policy_pack_via_registry(scope: str) -> dict[str, Any]`
- 通过 `_get_policy_registry().get_policy_pack(scope)` 获取策略包

#### 7.4 `_resolve_policy_conflict_via_registry(policy_key, values, strategy=None) -> str`
- 通过 `_get_policy_registry().resolve_conflict(...)` 解析策略冲突

#### 7.5 `_write_artifacts_via_sink(package: dict) -> dict[str, str]`
- 通过 `_get_artifact_sink().write(package)` 写入 artifacts

#### 7.6 `_append_error_log_via_sink(component, message, context) -> None`
- 通过 `_get_error_sink().log(component, message, context)` 记录错误

#### 7.7 `_execute_delegate_via_facade(host, event, raw_payload, payload) -> subprocess.CompletedProcess[str]`
- 通过 `_get_host_delegate(host).execute(event, raw_payload, payload)` 执行委托

**设计模式**：这是典型的 **Facade Pattern**，将复杂的策略对象调用封装为简单函数，便于测试时替换和调用方解耦。

---

### 8. 参数解析与工具函数

#### 8.1 `_parse_args() -> argparse.Namespace`

| 项目 | 说明 |
|------|------|
| **签名** | `def _parse_args() -> argparse.Namespace` |
| **返回值** | 解析后的命令行参数 |
| **参数定义** | `--host` (必填, choices: codex/claude), `--event` (必填, choices: session-start/prompt-submit/stop/notification), `--no-delegate` (生成 gateway artifacts 但不执行委托) |

#### 8.2 `now_iso() -> str`

| 项目 | 说明 |
|------|------|
| **签名** | `def now_iso() -> str` |
| **返回值** | 当前时区 ISO 格式时间字符串 (精确到秒) |

#### 8.3 `_read_payload(raw_payload: str) -> dict[str, Any]`

| 项目 | 说明 |
|------|------|
| **签名** | `def _read_payload(raw_payload: str) -> dict[str, Any]` |
| **参数** | JSON 格式字符串 |
| **返回值** | 解析后的字典；解析失败或空输入返回 `{}` |
| **核心逻辑** | 1. 空字符串 → `{}`；2. 尝试 `json.loads()`；3. 解析失败 → `{}`；4. 结果非 dict → 包装为 `{"payload": loaded}` |
| **边界条件** | JSON 解析失败被静默吞噬，不会通知调用方 |
| **异常处理** | 捕获 `json.JSONDecodeError` |

#### 8.4 `_payload_cwd(payload: dict[str, Any]) -> Path | None`
- 从 payload 中提取 `"cwd"` 字段，返回 Path 或 None

#### 8.5 `_environment_cwd() -> Path | None`
- 从环境变量 `PWD` 获取当前工作目录

#### 8.6 `_path_within_repo(path: Path) -> bool`

| 项目 | 说明 |
|------|------|
| **签名** | `def _path_within_repo(path: Path) -> bool` |
| **核心逻辑** | `path.resolve().relative_to(REPO_ROOT.resolve())` 成功则返回 True |
| **异常处理** | 捕获 `ValueError` (路径不在仓库内时 relative_to 抛出) |

#### 8.7 `_discover_cwd(payload: dict[str, Any]) -> Path`

| 项目 | 说明 |
|------|------|
| **签名** | `def _discover_cwd(payload: dict[str, Any]) -> Path` |
| **返回值** | 确定后的工作目录路径 |
| **核心逻辑** | 优先级链：1. payload cwd (且在 repo 内) → 2. env cwd (且在 repo 内) → 3. env cwd (fallback) → 4. payload cwd (fallback) → 5. REPO_ROOT |
| **边界条件** | 即使 payload cwd 不在 repo 内也会作为 fallback 使用 |

#### 8.8 `_should_noop_for_external_context(payload: dict[str, Any]) -> bool`

| 项目 | 说明 |
|------|------|
| **签名** | `def _should_noop_for_external_context(payload: dict[str, Any]) -> bool` |
| **返回值** | True 表示应该跳过处理 (noop) |
| **核心逻辑** | 1. 若 `MEMORY_HOOK_FORCE` 或 `WORKBOT_FORCE_HOOK` 存在 → False (不 noop)；2. 检查 env cwd 和 payload cwd 是否都不在 repo 内 → True (noop) |
| **依赖环境变量** | `MEMORY_HOOK_FORCE`, `WORKBOT_FORCE_HOOK` |

#### 8.9 `_delegate_noop_response(host: str) -> int`

| 项目 | 说明 |
|------|------|
| **签名** | `def _delegate_noop_response(host: str) -> int` |
| **返回值** | 退出码 (int) |
| **核心逻辑** | 获取 host delegate 的 noop 响应，输出 stdout 到终端，返回退出码 |
| **设计决策** | M2 架构：delegate 拥有自己的 bypass 输出格式，而非 gateway 统一调度 |

---

### 9. Truth Basis 验证层

#### 9.1 `determine_project_scope(cwd: Path) -> str`
- 委托给 `_get_gateway_business_policy().determine_project_scope(cwd)`

#### 9.2 `_extract_excerpt(path: Path, max_lines: int = 12) -> list[str]`

| 项目 | 说明 |
|------|------|
| **核心逻辑** | 读取文件，提取前 `max_lines` 行非空内容（去除空白行） |
| **边界条件** | 文件不存在时返回空列表 |

#### 9.3 `_section_bullets(text: str, heading: str) -> list[str]`

| 项目 | 说明 |
|------|------|
| **核心逻辑** | 在 Markdown 文本中定位指定 heading，提取该 section 下所有 `- ` 开头的列表项 |
| **边界条件** | 遇到下一个 `#` 级别标题时停止提取 |

#### 9.4 `_section_body(text: str, heading: str) -> str`
- 提取 heading 后的正文内容（直到下一个 `## ` 标题）

#### 9.5 `_markdown_code_tokens(text: str) -> set[str]`
- 使用正则提取所有行内代码标记 `` `code` ``

#### 9.6 `_json_string_values(text: str, key: str) -> set[str]`
- 使用正则从文本中提取指定 JSON key 对应的字符串值

#### 9.7 `_json_object_keys(text: str) -> set[str]`
- 使用正则提取文本中所有 JSON 对象的键名

#### 9.8 `governance_frozen_tuple_blocker_errors() -> list[str]`
- 委托给 business policy

#### 9.9 `event_contract_blocker_errors() -> list[str]`
- 委托给 business policy

---

### 10. Truth Ref 分类与验证

#### 10.1 `_path_is_under(path: Path, root: Path) -> bool`
- 与 `_path_within_repo` 逻辑相同但更通用，检查 path 是否在 root 下

#### 10.2 `_classify_truth_ref(path: Path) -> str`

| 项目 | 说明 |
|------|------|
| **返回值** | 分类标签字符串 |
| **可能的分类** | `legal-core`, `project-map-index`, `global-canonical`, `compatibility-only`, `project-canonical`, `docs`, `project-runtime`, `artifact`, `tooling`, `log`, `system`, `app`, `agents`, `gpt-web-to`, `repo-policy`, `workspace-entry`, `other` |
| **核心逻辑** | 按优先级匹配路径位置：1. 精确匹配 → 2. `_path_is_under` 检查子目录 → 3. 默认 "other" |
| **边界条件** | 精确匹配优先于目录匹配（如 `legal-core-map.md` 优先于 `under PROJECT_MAP_ROOT`） |

#### 10.3 `_authority_ref_allowed(path: Path) -> bool`
- 检查路径是否在 `AUTHORITY_ALLOWED_PATHS` 或 `GLOBAL_CANONICAL` 中

#### 10.4 `_lower_evidence_ref(path: Path) -> bool`
- 检查路径是否在任意 `LOWER_EVIDENCE_ROOTS` 下

#### 10.5 `_truth_basis_sections_for(path: Path) -> dict[str, Any]`

| 项目 | 说明 |
|------|------|
| **返回值** | 字典 `{source_refs, authority_refs, evidence_refs, conflict_status}`，每个值为列表 |
| **核心逻辑** | 读取文件文本，用 `_section_bullets` 提取四个 section 的内容 |

#### 10.6 `_truth_basis_errors_for(path: Path) -> list[str]`

这是最复杂的验证函数之一：

| 项目 | 说明 |
|------|------|
| **签名** | `def _truth_basis_errors_for(path: Path) -> list[str]` |
| **返回值** | 错误信息字符串列表（空列表表示验证通过） |
| **核心逻辑** | 分阶段验证： |

**验证阶段**：
1. **存在性检查**：文件不存在 → 报错
2. **结构检查**：缺少 "Truth Basis" section → 报错
3. **Section 完整性**：检查 `source_refs`, `authority_refs`, `evidence_refs`, `conflict_status` 是否都存在
4. **冲突状态**：必须存在且值为 `["resolved"]`
5. **引用路径验证**：所有引用的路径必须在仓库内且存在于磁盘
6. **引用去重**：source_refs 与 evidence_refs 不能相同
7. **引用隔离**：source_refs ∩ authority_refs = ∅；authority_refs ∩ evidence_refs = ∅
8. **Authority 合规**：每个 authority path 必须在允许路径集中
9. **来源多样性**：source refs 不能全部是 canonical 类型（必须包含非 canonical 来源）
10. **证据支撑**：evidence refs 必须包含至少一个 low-layer 支持

**边界条件**：
- 路径解析同时处理相对路径和绝对路径
- 空 section 视为缺失

---

### 11. Git 注册探测层

#### 11.1 `_existing_paths(paths: list[Path]) -> list[str]`
- 过滤并返回存在路径的字符串列表

#### 11.2 `_normalize_repo_scope_entry(value: str | Path) -> str | None`
- 将路径规范化为相对于 REPO_ROOT 的 POSIX 路径；不在仓库内则返回 None

#### 11.3 `_registration_payload_paths(payload: dict[str, Any]) -> list[str]`

| 项目 | 说明 |
|------|------|
| **核心逻辑** | 从 payload 的 `"registration_paths"` 提取路径：支持字符串或字符串列表；规范化去重 |
| **边界条件** | 非字符串类型或非字符串列表的 item 会被忽略 |

#### 11.4 `_git_name_only(*args: str) -> list[str]`
- 执行 `git -C REPO_ROOT` 命令，捕获 stdout 返回文件名列表
- 失败时返回空列表（不抛异常）

#### 11.5 `_path_matches_scope(candidate: str, scope_entry: str) -> bool`
- 检查候选路径是否匹配范围条目（精确匹配或前缀匹配）

#### 11.6 `_git_registration_probe(event: str, payload: dict[str, Any]) -> dict[str, Any]`

这是另一个核心复杂函数：

| 项目 | 说明 |
|------|------|
| **签名** | `def _git_registration_probe(event: str, payload: dict[str, Any]) -> dict[str, Any]` |
| **返回值** | 包含探测结果的结构化字典 |
| **核心逻辑** | 1. 从 `REGISTRATION_GIT_SCOPE` 和 payload 的 `registration_paths` 构建追踪范围；2. 执行 `git status --short` 检查变更；3. 获取 HEAD commit；4. 检查 HEAD commit 是否触及了相关范围；5. 判定状态 |

**状态分类**：
| 状态 | 条件 |
|------|------|
| `pending-commit` | 有未提交的变更 |
| `awaiting-registration-payload` | 没有 registration_paths |
| `committed-coupled` | map scope 和 registration scope 都在 HEAD commit 中被触及 |
| `committed-not-proven` | 已提交但无法证明耦合关系 |

**返回字段**：
`phase`, `policy`, `gate_event`, `triggered_on_current_event`, `status`, `tracked_scope`, `registration_paths`, `changed_entries`, `latest_commit`, `latest_commit_touched`, `map_scope_touched_in_latest_commit`, `registration_scope_touched_in_latest_commit`, `scope_clean`, `would_pass_if_enforced`, `probe_ok`, `stderr`

---

### 12. 公开门面 API (Thin Wrappers)

这些是公开（无下划线前缀）的薄封装函数，主要委托给 business policy：

| 函数 | 委托目标 |
|------|----------|
| `project_map_refs()` | `business_policy.project_map_refs()` |
| `read_text_if_exists(path)` | 读取文件内容，不存在返回 `""` |
| `validate_project_map_files()` | `business_policy.validate_project_map_files()` |
| `validate_unique_legal_system_contract()` | `business_policy.validate_unique_legal_system_contract()` |
| `decision_refs_for_scope(project_scope)` | `business_policy.decision_refs_for_scope(...)` |
| `lesson_refs_for_scope(project_scope)` | `business_policy.lesson_refs_for_scope(...)` |
| `docs_refs_for_scope(project_scope)` | `business_policy.docs_refs_for_scope(...)` |
| `truth_basis_for_scope(project_scope)` | `business_policy.truth_basis_for_scope(...)` |

---

### 13. 写入与路由

#### 13.1 `write_targets() -> dict[str, Any]`

| 项目 | 说明 |
|------|------|
| **返回值** | 包含各类型写入目标路径的字典 |
| **核心逻辑** | 尝试通过策略获取；失败时返回硬编码默认值 |
| **默认目标** | `fact`, `global_canonical`, `project_canonical`, `decision`, `lesson`, `docs`, `action`, `project_runtime`, `artifacts`, `system_error`, `invalid_memory` + `kb_policy` 配置 |
| **异常处理** | 捕获所有 Exception，返回 fallback |

#### 13.2 `resolve_route_target(kind: str) -> str`

| 项目 | 说明 |
|------|------|
| **参数** | `kind` — 路由类型 |
| **返回值** | 目标路径字符串 |
| **核心逻辑** | 尝试通过策略解析；失败时使用内置路由映射 (`fact`, `global-rule`, `source-material`, `project-runtime`, `system-error`, `invalid-memory`) |
| **异常处理** | KeyError → ValueError (unsupported route kind) |

---

### 14. Artifact 压缩

#### 14.1 `_apply_artifact_compaction(package: dict[str, Any]) -> None`

| 项目 | 说明 |
|------|------|
| **核心逻辑** | 从 `_adapter_config["ARTIFACT_COMPACTION"]` 读取压缩策略，根据布尔标志移除 package 中的 sections |
| **可压缩的 sections** | `system_context`, `project_context`, `task_context`, `evidence_refs`, `allowed_reads`, `allowed_writes` |
| **边界条件** | 默认全部包含 (策略值默认 True) |

---

### 15. 核心构建入口

#### 15.1 `build_context_package(host, event, payload) -> dict[str, Any]`

**这是整个模块最核心的公开 API 之一**：

| 项目 | 说明 |
|------|------|
| **签名** | `def build_context_package(host: str, event: str, payload: dict[str, Any]) -> dict[str, Any]` |
| **参数** | `host` ("codex"/"claude"), `event` (事件名), `payload` (事件数据) |
| **返回值** | 上下文包字典 |

**执行流程**：
```
1. _discover_cwd(payload)          → 确定 CWD
2. determine_project_scope(cwd)    → 确定项目范围
3. _get_gateway_business_policy()  → 获取业务策略
4. 构建 CoreConfig（注入大量回调函数）
5. 解析核心构建器 (legacy / external-core，支持 shadow run)
6. build_context_package_from_config(config)  → 构建包
7. 记录 provider 信息到 system_context
8. 处理 provider_errors（标记为 degraded）
9. Shadow run（可选，通过 MEMORY_HOOK_SHADOW_RUN 环境变量）
10. _apply_artifact_compaction(package)  → 压缩
11. 返回 package
```

**CoreConfig 注入的回调函数**：
- `extract_excerpt_fn`, `now_iso_fn`, `write_targets_fn`
- `validate_project_map_fn`, `validate_unique_legal_system_contract_fn`
- `policy_validate_fn`, `get_policy_pack_fn`
- `governance_frozen_tuple_errors_fn`, `event_contract_blocker_errors_fn`
- `git_registration_probe_fn`, `truth_basis_for_scope_fn`
- `decision_refs_for_scope_fn`, `lesson_refs_for_scope_fn`, `docs_refs_for_scope_fn`

**Shadow Run 模式**：
- 环境变量 `MEMORY_HOOK_SHADOW_RUN` 开启
- 同时运行另一个 provider (与主 provider 不同的另一个)
- 结果记录到 `system_context["shadow_run"]`
- 用于对比验证新旧实现的一致性

#### 15.2 `build_context_package_simple(host, event, payload=None, *, adapter=None, schema="context-package-v1") -> dict[str, Any]`

| 项目 | 说明 |
|------|------|
| **签名** | 简化入口点，支持可选 adapter 和 schema 参数 |
| **参数** | `host`, `event`, `payload` (默认 `{}`), `adapter` (可选覆盖), `schema` ("context-package-v1" 或 "memory-v1") |
| **核心逻辑** | 调用 `build_context_package` → 按 schema 转换输出 |
| **Schema 转换** | `context-package-v1`: `convert_to_v1(package)`；`memory-v1`: `convert_legacy_to_memory_v1(convert_to_v1(package))` |

---

### 16. 错误日志与 Artifact 写入

#### 16.1 `_ensure_artifact_dirs() -> None`
- 确保 artifact 目录存在
- Fallback: 直接 `CONTEXT_ROOT.mkdir(parents=True, exist_ok=True)`

#### 16.2 `append_error_log(component, message, context) -> None`

| 项目 | 说明 |
|------|------|
| **核心逻辑** | 尝试通过 sink 写入；失败时 fallback 到直接追加写入文件 |
| **Fallback 格式** | `[{now_iso}] [{component}] [error] {message} | context={json}\n` |

#### 16.3 `write_artifacts(package: dict[str, Any]) -> dict[str, str]`

| 项目 | 说明 |
|------|------|
| **返回值** | `{snapshot: path, latest: path}` |
| **核心逻辑** | 尝试通过 sink 写入；失败时 fallback 到直接写入 |
| **Fallback 行为** | 1. 确保目录存在；2. 生成带时间戳的文件名；3. 处理文件名冲突（递增后缀）；4. 写入 snapshot 和 latest 文件；5. 追加到事件日志 |

---

### 17. 辅助函数

#### 17.1 `_require_env(name: str) -> str`
- 获取必需环境变量，空值时抛出 `RuntimeError`

#### 17.2 `_canonicalize_cmux_refs(workspace_ref: str, surface_ref: str) -> tuple[str, str]`

| 项目 | 说明 |
|------|------|
| **核心逻辑** | 执行 `cmux identify --workspace ... --surface ...` 命令，解析 JSON 输出获取规范化的引用 |
| **异常处理** | 命令失败或 JSON 解析失败时返回原始引用 |

#### 17.3 `_delegate_codex(event, raw_payload) -> subprocess.CompletedProcess[str]`
- 执行 codex 委托 (不传 payload)

#### 17.4 `_delegate_claude(event, raw_payload, payload) -> subprocess.CompletedProcess[str]`
- 执行 claude 委托 (传递 payload)

---

### 18. 主入口函数

#### 18.1 `main() -> int`

**完整的执行流程**：

```
1. _parse_args()                     → 解析命令行参数
2. sys.stdin.read()                  → 读取原始 payload
3. _read_payload(raw_payload)        → 解析为字典
4. _discover_cwd(payload)            → 确定 CWD
5. _should_noop_for_external_context → 检查是否需要 noop
   └─ 是: _delegate_noop_response() → 返回退出码
6. ArtifactWriter(...)               → 创建写入器
7. build_context_package(...)        → 构建上下文包
8. writer.write(...)                 → 写入 artifacts
   └─ 失败: append_error_log + stderr 提示
9. 检查 package["status"]
   └─ != "ok": append_error_log + stderr 提示，return 1
10. args.no_delegate 检查
    └─ 是: 输出 JSON，return 0
11. 执行委托 (codex 或 claude)
    └─ RuntimeError: append_error_log + noop_response，return 0
12. 检查 proc.returncode
    └─ != 0: append_error_log
13. 输出 stdout/stderr
14. return proc.returncode
```

**退出码**：
| 退出码 | 条件 |
|--------|------|
| 0 | 成功 或 delegate noop 或 delegate preflight 失败 |
| 1 | package status != "ok" |
| N | delegate 命令的退出码 |

**设计特点**：
- Preflight 失败 (RuntimeError) 时不阻断，返回 noop 响应 (exit 0)
- Delegate 命令失败时仍输出结果，只记录日志
- `--no-delegate` 模式用于仅生成 gateway artifacts 的场景

---

## 二、函数分组归类

### A. 公开 API (通过 `__all__` 导出)

| 函数/类 | 类型 | 说明 |
|---------|------|------|
| `build_context_package` | 函数 | 核心入口：构建上下文包 |
| `build_context_package_simple` | 函数 | 简化入口：带 schema 转换 |
| `ArtifactWriter` | 类 (从 impls 导入) |  artifact 写入器 |
| `DelegateRouter` | 类 (从 impls 导入) | 委托路由器 |

### B. 公开门面函数 (无下划线前缀，外部可用)

| 函数 | 用途 |
|------|------|
| `determine_project_scope(cwd)` | 确定项目作用域 |
| `governance_frozen_tuple_blocker_errors()` | 治理冻结元组阻断错误 |
| `event_contract_blocker_errors()` | 事件契约阻断错误 |
| `project_map_refs()` | 获取项目映射引用 |
| `read_text_if_exists(path)` | 安全读取文件 |
| `validate_project_map_files()` | 验证项目映射文件 |
| `validate_unique_legal_system_contract()` | 验证唯一法律系统契约 |
| `decision_refs_for_scope(scope)` | 获取决策引用 |
| `lesson_refs_for_scope(scope)` | 获取课程引用 |
| `docs_refs_for_scope(scope)` | 获取文档引用 |
| `truth_basis_for_scope(scope)` | 获取真理基础 |
| `write_targets()` | 获取写入目标 |
| `resolve_route_target(kind)` | 解析路由目标 |
| `append_error_log(...)` | 追加错误日志 |
| `write_artifacts(package)` | 写入 artifacts |
| `now_iso()` | 当前时间 ISO 格式 |
| `main()` | CLI 主入口 |

### C. 内部辅助函数 (下划线前缀)

#### C1. 配置与策略
| 函数 | 用途 |
|------|------|
| `load_adapter_config(profile)` | 加载 adapter 配置 |
| `_build_gateway_business_policy()` | 构建业务策略实例 |
| `_get_gateway_business_policy()` | 获取业务策略（每次新建） |

#### C2. 核心构建器
| 函数 | 用途 |
|------|------|
| `_load_external_core_builder()` | 加载外部核心构建器 |
| `_resolve_core_builder(provider, ...)` | 解析核心构建器（带 fallback） |

#### C3. 策略门面 Getter（单例/瞬态）
| 函数 | 模式 |
|------|------|
| `_get_policy_registry()` | 单例 |
| `_get_route_policy()` | 单例 |
| `_get_write_policy()` | 单例 |
| `_get_artifact_sink()` | 瞬态（每次新建） |
| `_get_error_sink()` | 瞬态（每次新建） |
| `_get_host_delegate(host)` | 瞬态（每次新建） |

#### C4. IF-5 门面适配器
| 函数 | 委托目标 |
|------|----------|
| `_resolve_route_target_via_policy(kind)` | RouteTargetPolicy.resolve |
| `_write_targets_via_policy()` | WriteTargetPolicy.get_targets |
| `_get_policy_pack_via_registry(scope)` | PolicyRegistry.get_policy_pack |
| `_resolve_policy_conflict_via_registry(...)` | PolicyRegistry.resolve_conflict |
| `_write_artifacts_via_sink(package)` | ArtifactSink.write |
| `_append_error_log_via_sink(...)` | ErrorSink.log |
| `_execute_delegate_via_facade(...)` | HostDelegate.execute |

#### C5. 路径与 CWD 发现
| 函数 | 用途 |
|------|------|
| `_parse_args()` | CLI 参数解析 |
| `_read_payload(raw_payload)` | 解析 JSON payload |
| `_payload_cwd(payload)` | 从 payload 提取 cwd |
| `_environment_cwd()` | 从环境变量提取 cwd |
| `_path_within_repo(path)` | 检查路径在仓库内 |
| `_discover_cwd(payload)` | 按优先级发现 CWD |
| `_should_noop_for_external_context(payload)` | 判断是否应 noop |
| `_delegate_noop_response(host)` | 获取 delegate noop 响应 |
| `_path_is_under(path, root)` | 检查路径在 root 下 |

#### C6. Truth Basis 验证
| 函数 | 用途 |
|------|------|
| `_extract_excerpt(path, max_lines)` | 提取文件片段 |
| `_section_bullets(text, heading)` | 提取 Markdown 列表项 |
| `_section_body(text, heading)` | 提取 Markdown 正文 |
| `_markdown_code_tokens(text)` | 提取行内代码 |
| `_json_string_values(text, key)` | 提取 JSON 值 |
| `_json_object_keys(text)` | 提取 JSON 键 |
| `_classify_truth_ref(path)` | 分类 truth reference |
| `_authority_ref_allowed(path)` | 检查 authority 是否允许 |
| `_lower_evidence_ref(path)` | 检查低层证据引用 |
| `_truth_basis_sections_for(path)` | 提取 truth basis sections |
| `_truth_basis_errors_for(path)` | 全面验证 truth basis |

#### C7. Git 注册探测
| 函数 | 用途 |
|------|------|
| `_existing_paths(paths)` | 过滤存在的路径 |
| `_normalize_repo_scope_entry(value)` | 规范化范围条目 |
| `_registration_payload_paths(payload)` | 提取注册路径 |
| `_git_name_only(*args)` | 执行 git 获取文件名 |
| `_path_matches_scope(candidate, scope)` | 路径匹配范围 |
| `_git_registration_probe(event, payload)` | Git 注册状态探测 |

#### C8. Artifact 处理
| 函数 | 用途 |
|------|------|
| `_apply_artifact_compaction(package)` | 压缩 artifact sections |
| `_ensure_artifact_dirs()` | 确保 artifact 目录存在 |

#### C9. 委托执行
| 函数 | 用途 |
|------|------|
| `_require_env(name)` | 获取必需环境变量 |
| `_canonicalize_cmux_refs(wr, sr)` | 规范化 cmux 引用 |
| `_delegate_codex(event, raw_payload)` | 执行 codex 委托 |
| `_delegate_claude(event, raw_payload, payload)` | 执行 claude 委托 |

---

## 三、与其他模块的依赖关系

### 3.1 直接导入依赖

```
memory_hook_gateway.py
├── memory_root_discovery         (discover_roots)
├── cmux_hook_state               (可选, 静默忽略)
├── memory_hook_adapters.workbot_policy (WorkbotGatewayBusinessPolicy)
├── memory_hook_adapters.workbot_runtime_profile (build_workbot_runtime_profile)
├── memory_hook_config            (CoreConfig)
├── memory_hook_core              (build_context_package_core, build_context_package_from_config)
├── memory_hook_impls             (10 个实现类/函数)
├── memory_hook_interfaces        (7 个接口定义)
└── memory_hook_schema            (convert_legacy_to_memory_v1, convert_to_v1)
```

### 3.2 外部命令依赖

| 命令 | 用途 | 函数 |
|------|------|------|
| `git` | 状态检查、文件变更追踪 | `_git_name_only`, `_git_registration_probe` |
| `cmux` | 标识规范化 | `_canonicalize_cmux_refs` |

### 3.3 环境变量依赖

| 环境变量 | 用途 | 默认值 |
|----------|------|--------|
| `MEMORY_HOOK_ADAPTER` | 选择 adapter | `"workbot"` |
| `MEMORY_HOOK_CORE_PROVIDER` | 选择核心构建器 | `"legacy"` |
| `MEMORY_HOOK_EXTERNAL_CORE_MODULE` | 外部模块名 | `"memory_core.tools.memory_hook_core"` |
| `MEMORY_HOOK_EXTERNAL_CORE_FUNC` | 外部函数名 | `"build_context_package_core"` |
| `MEMORY_HOOK_FORCE` / `WORKBOT_FORCE_HOOK` | 强制执行 hook | - |
| `MEMORY_HOOK_SHADOW_RUN` | 开启 shadow run | - |
| `CMUX_SURFACE_ID` | 表面标识 | `""` |
| `CMUX_WORKSPACE_ID` | 工作区标识 | `""` |
| `PWD` | 当前工作目录 | - |

### 3.4 被依赖模块

```
memory_hook_provider_probe.py     → import memory_hook_gateway (调用 _resolve_core_builder)
memory_hook_provider_rollback.py  → import memory_hook_gateway (调用 _resolve_core_builder)
```

### 3.5 依赖注入路径

Gateway 通过 `CoreConfig` 向下游模块 (`memory_hook_core`) 注入大量回调函数：

```
CoreConfig → build_context_package_from_config → memory_hook_core
├── extract_excerpt_fn = _extract_excerpt
├── now_iso_fn = now_iso
├── write_targets_fn = write_targets
├── validate_project_map_fn = validate_project_map_files
├── policy_validate_fn = lambda: _get_policy_registry().validate(context)
├── get_policy_pack_fn = _get_policy_pack_via_registry
├── governance_frozen_tuple_errors_fn = governance_frozen_tuple_blocker_errors
├── event_contract_blocker_errors_fn = event_contract_blocker_errors
├── git_registration_probe_fn = _git_registration_probe
├── truth_basis_for_scope_fn = truth_basis_for_scope
├── decision_refs_for_scope_fn = decision_refs_for_scope
├── lesson_refs_for_scope_fn = lesson_refs_for_scope
├── docs_refs_for_scope_fn = docs_refs_for_scope
└── ... (更多)
```

这种设计实现了 **控制反转 (IoC)**，使核心构建逻辑可在测试时被替换。

---

## 四、关键设计决策与模式识别

### 4.1 架构模式

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **Facade Pattern** | 整个模块 | 作为 memory hook 系统的统一门面，封装底层 Policy/Sink/Delegate |
| **Adapter Pattern** | `_ADAPTER_REGISTRY` | 支持不同运行时 (workbot) 的插件化 |
| **Strategy Pattern** | PolicyRegistry, RouteTargetPolicy, WriteTargetPolicy | 策略可替换 |
| **Dependency Injection** | CoreConfig | 回调函数注入实现控制反转 |
| **Singleton (Lazy)** | Policy 相关 getter | 延迟初始化单例 |
| **Provider Pattern** | `_resolve_core_builder` | 双 provider (legacy/external-core) 模式 |
| **Circuit Breaker** | `write_targets`, `resolve_route_target` | 策略失败时 fallback 到硬编码默认值 |

### 4.2 单例 vs 瞬态设计决策

| 对象 | 模式 | 理由 |
|------|------|------|
| PolicyRegistry | 单例 | 策略注册表是共享状态，缓存提升性能 |
| RouteTargetPolicy | 单例 | 路由策略不变 |
| WriteTargetPolicy | 单例 | 写入策略不变 |
| GatewayBusinessPolicy | **每次新建** | 允许测试 monkeypatch 常量后立即生效 |
| ArtifactSink | 瞬态 | 每次写入独立实例 |
| ErrorSink | 瞬态 | 每次记录独立实例 |
| HostDelegate | 瞬态 | 委托执行独立实例 |

### 4.3 双导入路径兼容

```python
try:
    from .memory_hook_core import ...
except ImportError:
    from memory_core.tools.memory_hook_core import ...
```

这个模式使模块既可作为包的一部分运行，也可作为独立脚本运行。

### 4.4 Provider 双模式 + Shadow Run

```
MEMORY_HOOK_CORE_PROVIDER = "legacy" (默认) 或 "external-core"
                              ↓
                    _resolve_core_builder()
                              ↓
         ┌────────────────────┼────────────────────┐
         ↓                    ↓                    ↓
    external-core         legacy (fallback)    shadow run
    (如果可用)             (如果失败)            (对比验证)
```

- **正常模式**：使用请求的 provider，失败时 fallback
- **Shadow Run**：同时运行两个 provider，对比结果用于验证

### 4.5 降级模式 (Degraded Mode)

当 external-core 加载失败时，系统不会完全失败，而是：
1. 回退到 legacy provider
2. 设置 `package["status"] = "degraded"`
3. 记录 fallback errors 到 `system_context["core_provider_fallback_errors"]`

### 4.6 错误处理分层

```
Level 1: Facade 函数内部 try/except → fallback 到硬编码默认值
Level 2: write_artifacts / append_error_log → try/except → fallback 到直接文件操作
Level 3: main() 中的 delegate 执行 → try/except → 返回 noop 响应 (exit 0)
```

系统倾向于 "尽力运行" 而非 "快速失败"。

### 4.7 Git 注册探测状态机

```
git status 有变更? ──是──→ "pending-commit"
         │
         否
         ↓
有 registration_paths? ──否──→ "awaiting-registration-payload"
         │
         是
         ↓
map_touched AND registration_touched? ──是──→ "committed-coupled"
         │
         否
         ↓
"committed-not-proven"
```

---

## 五、潜在问题与改进建议

### 5.1 严重问题

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | **模块级常量依赖过重**：`_build_gateway_business_policy` 依赖 ~40 个未在此文件定义的模块级常量 | 常量缺失时产生 `NameError`，难以调试 | 将这些常量集中在一个配置类/数据类中，明确传递而非隐式依赖全局变量 |
| 2 | **`globals().update()` 污染命名空间**：`load_adapter_config` 将配置键注入模块全局命名空间 | 与现有变量冲突，难以追踪 | 使用配置对象替代，移除 globals().update |
| 3 | **模块级立即执行**：`_adapter_profile = _fn(...)` 在模块加载时执行 | 测试困难，无法 mock | 延迟到首次使用时执行 (lazy initialization) |

### 5.2 中等问题

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 4 | **异常吞噬**：`_read_payload` 静默返回 `{}` | 上游错误被掩盖 | 至少记录警告日志 |
| 5 | **`memory_hook_provider_probe.py` 与 `memory_hook_provider_rollback.py` 重复**：两个文件逻辑几乎完全相同 | 维护负担，代码重复 | 合并为一个模块或共用基类 |
| 6 | **硬编码路径**：大量路径硬编码在模块级 | 缺乏配置灵活性 | 通过配置对象统一管理 |
| 7 | **环境变量隐式依赖**：大量环境变量缺乏文档 | 使用者难以理解 | 添加文档或在启动时打印有效配置 |

### 5.3 轻微问题

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 8 | **类型注解不完整**：部分函数缺少类型注解 | IDE 支持差 | 补全类型注解 |
| 9 | **`_path_within_repo` 与 `_path_is_under` 逻辑重复** | 代码冗余 | 统一为一个函数 |
| 10 | **Magic strings**：大量硬编码字符串（路径、常量名） | 重构困难 | 提取为常量 |
| 11 | **`_truth_basis_errors_for` 函数过长** (~70 行) | 可读性差 | 拆分为多个子验证函数 |
| 12 | **`_git_registration_probe` 中的 `REGISTRATION_GIT_SCOPE[: len(REGISTRATION_GIT_SCOPE)]`** | 冗余切片 | 直接使用该变量 |

### 5.4 架构改进建议

1. **配置对象化**：将所有模块级常量整合为 `GatewayConfig` 数据类，通过参数传递而非全局变量
2. **延迟初始化**：将 adapter profile 加载改为 lazy，在首次需要时才执行
3. **异常分类**：区分可恢复和不可恢复异常，而非统一 fallback
4. **Provider 注册表**：将 provider 选择改为注册表模式，支持更多 provider
5. **测试友好性**：所有隐式依赖（环境变量、全局变量）改为显式依赖注入

---

## 附录 A: 依赖文件分析

### memory_hook_provider_probe.py

**功能**：探测 external-core 和 legacy provider 的可用性

| 项目 | 说明 |
|------|------|
| **入口函数** | `probe_provider_availability() → dict[str, Any]` |
| **核心逻辑** | 调用 `gateway._resolve_core_builder("external-core")` 和 `gateway._resolve_core_builder("legacy")`，检查两者是否可解析 |
| **返回值** | 包含两个 provider 的探测结果和整体 status |
| **别名** | `run_rollback_drill = probe_provider_availability` (向后兼容) |
| **CLI** | `main()` 输出 JSON 结果，status="passed" 时 exit 0 |

### memory_hook_provider_rollback.py

**功能**：一键回退演练（实际上与 probe 逻辑相同）

| 项目 | 说明 |
|------|------|
| **入口函数** | `run_rollback_drill() → dict[str, Any]` |
| **核心逻辑** | 与 probe 模块完全相同的逻辑 |
| **返回值** | 与 probe 模块完全相同的结构 |
| **CLI** | `main()` 输出 JSON 结果 |

**注意**：两个文件功能重复，rollback.py 仅作为向后兼容的入口点存在。

---

## 附录 B: 接口依赖总览

```
memory_hook_interfaces (抽象契约)
├── ArtifactSink ─────→ ArtifactSinkImpl (memory_hook_impls)
├── ErrorSink ────────→ ErrorSinkImpl (memory_hook_impls)
├── GatewayBusinessPolicy → WorkbotGatewayBusinessPolicy (adapters)
├── HostDelegate ─────→ resolve_host_delegate (memory_hook_impls)
├── PolicyRegistry ───→ PolicyRegistryImpl (memory_hook_impls)
├── RouteTargetPolicy → RouteTargetPolicyImpl (memory_hook_impls)
└── WriteTargetPolicy → WriteTargetPolicyImpl (memory_hook_impls)
```

Gateway 作为门面，仅依赖接口，实现由 `memory_hook_impls` 和 `memory_hook_adapters` 提供。
