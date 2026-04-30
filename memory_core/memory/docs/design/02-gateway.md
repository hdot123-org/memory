---
type: "[DOC:DESIGN]"
title: "Gateway 门控设计"
shortname: DES-002
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [gateway,dispatch,routing]
related: [DES-001, DES-003, DES-009]
---

> 文档编号：DES-002 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# Gateway 设计文档

> 源文件: `memory_core/tools/memory_hook_gateway.py` (981 行)
> 关联文件:
> - `memory_core/tools/memory_hook_interfaces.py` (244 行) — 接口定义
> - `memory_core/tools/memory_hook_impls.py` (1040 行) — 默认实现
> - `memory_core/tools/memory_hook_core.py` (271 行) — 核心组装逻辑
> - `memory_core/tools/memory_hook_adapters/workbot_runtime_profile.py` (267 行) — workbot 适配器
> - `memory_core/tools/memory_hook_adapters/workbot_policy.py` (82 行) — workbot 业务策略
> - `memory_core/tools/memory_hook_adapters/neutral_policy.py` (21 行) — 中性策略基类

---

## 1. Gateway 职责定位

### 1.1 做什么

Gateway 是 memory-hook 系统的 **入口门控 + 上下文组装器 + 主机分派器**。它作为 Claude Code / Codex 的 hook 脚本被调用，完成以下工作：

1. **参数解析与 payload 读取**（行 908-911）：通过 `argparse` 接收 `--host`（`codex`/`claude`）、`--event`（`session-start`/`prompt-submit`/`stop`/`notification`）、`--no-delegate` 三个 CLI 参数；从 stdin 读取 JSON payload。

2. **外部上下文过滤**（行 914-915）：通过 `should_noop_for_external_context()` 判断当前工作目录是否在仓库内，若不在且无 `MEMORY_HOOK_FORCE`/`WORKBOT_FORCE_HOOK` 环境变量，则走 noop 分支直接返回。

3. **上下文包组装**（行 917）：调用 `build_context_package()` 将 host、event、payload 组装为结构化 JSON 上下文包（schema 版本 `wb-hook-v2`），包含 system_context、project_context、task_context、allowed_reads、allowed_writes 五大区块。

4. **产物写入**（行 918）：调用 `write_artifacts()` 将上下文包写入 `artifacts/memory-hook/contexts/` 目录（快照 + latest 双写），并追加到 `events.jsonl`。

5. **主机委托分派**（行 943-944）：根据 host 类型调用 `delegate_codex()` 或 `delegate_claude()`，通过 `cmux` CLI 将事件分派给对应的主机运行时。

6. **错误日志记录**（行 920-936, 945-966）：当上下文包状态为 `degraded`（缺失 canonical 路径或验证失败）或委托执行失败时，写入 `memory/system/errors.log`。

### 1.2 不做什么

- **不做核心业务逻辑**：核心上下文组装逻辑已抽离到 `memory_hook_core.build_context_package_core()`（M4 重构），Gateway 仅负责参数装配和依赖注入。
- **不做策略定义**：业务策略由 adapter 层（`WorkbotGatewayBusinessPolicy`）定义，Gateway 仅通过 `_get_gateway_business_policy()` 获取。
- **不做主机协议实现**：Codex/Claude 的具体执行协议由 `CodexDelegate`/`ClaudeDelegate` 实现，Gateway 仅做分派。
- **不直接操作 git**：git 状态探测通过 `git_registration_probe()` 调用 `subprocess.run(["git", ...])` 完成，Gateway 不直接操作 git。

---

## 2. 模块级初始化流程

### 2.1 Import 链（行 1-76）

初始化按以下顺序进行：

```
memory_hook_gateway.py
├── 标准库: argparse, json, os, re, shutil, subprocess, sys, datetime, pathlib, typing
├── 路径常量: SCRIPT_PATH, WORKSPACE_ROOT, REPO_ROOT, ARTIFACT_ROOT, CONTEXT_ROOT, EVENT_LOG, ERROR_LOG
├── cmux_hook_state: default_hook_state_path, record_hook_event (行 25-29)
│   └── 优先相对导入, fallback 到 ~/.agents/skills/cmux/scripts/ 绝对导入
├── memory_hook_core: build_context_package_core (行 32)
├── memory_hook_interfaces (行 33-41):
│   ├── ArtifactSink, ErrorSink — 产物/错误输出接口
│   ├── GatewayBusinessPolicy — 业务策略接口
│   ├── HostDelegate — 主机委托接口
│   ├── PolicyRegistry — 策略注册表接口
│   ├── RouteTargetPolicy, WriteTargetPolicy — 路由/写入目标策略接口
├── memory_hook_impls (行 42-50):
│   ├── ArtifactSinkImpl, ErrorSinkImpl — 默认实现
│   ├── ClaudeDelegate, CodexDelegate — 主机委托实现
│   ├── GatewayBusinessPolicyConfig — 策略配置 dataclass
│   ├── PolicyRegistryImpl, RouteTargetPolicyImpl, WriteTargetPolicyImpl — 策略实现
├── memory_hook_adapters.workbot_runtime_profile: build_workbot_runtime_profile (行 52)
└── memory_hook_adapters.workbot_policy: WorkbotGatewayBusinessPolicy (行 53)
```

所有相对导入都有 `except ImportError` 的绝对导入 fallback（行 54-76），支持 standalone 脚本模式。

### 2.2 Adapter 注册与 globals().update（行 79-91）

```python
_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "workbot")  # 行 80
_ADAPTER_REGISTRY = {
    "workbot": (".memory_hook_adapters.workbot_runtime_profile", "build_workbot_runtime_profile"),
}  # 行 81-83
_mod_path, _fn_name = _ADAPTER_REGISTRY[_ADAPTER_NAME]  # 行 84
_mod = importlib.import_module(_mod_path, package="workspace.tools")  # 行 86
_fn = getattr(_mod, _fn_name)  # 行 90
globals().update(_fn(REPO_ROOT, WORKSPACE_ROOT))  # 行 91
```

**关键机制**：`build_workbot_runtime_profile(REPO_ROOT, WORKSPACE_ROOT)` 返回一个 `dict[str, Any]`（含 30+ 个键），通过 `globals().update()` 直接注入为模块级全局变量。这意味着 Gateway 模块加载后，以下名称可直接作为全局变量使用：

| 注入变量 | 类型 | 来源行 |
|---------|------|--------|
| `PROJECT_MAP_ROOT` | `Path` | workbot_runtime_profile:193 |
| `TRUTH_MODEL` | `Path` | :194 |
| `PROJECT_MAP_FILES` | `list[Path]` | :195 |
| `PROJECT_MAP_GOVERNANCE` | `Path` | :196 |
| `HOOK_CONTRACT_PATH` | `Path` | :197 |
| `GLOBAL_RULE_PATH` | `Path` | :198 |
| `MEMORY_SYSTEM_PATH` | `Path` | :199 |
| `POLICY_PACK_PATH` | `Path` | :200 |
| `GATEWAY_POLICY_CLASS` | `type` | :201 (WorkbotGatewayBusinessPolicy) |
| `LEGALITY_SOURCE_POLICY` | `str` | :202 ("active-legal-map-only") |
| `REGISTRATION_COMMIT_POLICY` | `str` | :203 ("required-after-absorption-complete") |
| `REGISTRATION_COMMIT_PHASE` | `str` | :204 ("declared-not-enforced") |
| `REGISTRATION_GIT_SCOPE` | `list[Path]` | :205 |
| `LEGAL_CORE_MARKERS` | `list[str]` | :206 |
| `REQUIRED_REGISTRY_SCOPES` | `list[str]` | :207 |
| `REQUIRED_CANONICAL` | `list[Path]` | :208 |
| `PROJECT_CANONICAL` | `dict[str, Path]` | :209 |
| `PROJECT_RUNTIME_ROOT` | `dict[str, Path]` | :210 |
| `PROJECT_DOC_REFS` | `dict[str, list[Path]]` | :211 |
| `GLOBAL_CANONICAL` | `list[Path]` | :212 |
| `AUTHORITY_ALLOWED_PATHS` | `set[Path]` | :213 |
| `LOWER_EVIDENCE_ROOTS` | `list[Path]` | :214 |
| `DEFAULT_DECISION_REFS` | `list[Path]` | :215 |
| `PROJECT_DECISION_REFS` | `dict[str, list[Path]]` | :216 |
| `GOVERNANCE_FROZEN_TUPLE_FILES` | `list[Path]` | :217 |
| `EVENT_CONTRACT_FILES` | `dict` | :218 |
| `FROZEN_TUPLE_EXPECTED` | `dict` | :219 |
| `FROZEN_TUPLE_LEGACY_MARKERS` | `set` | :220 |
| `FORMAL_SOURCE_TYPES` | `set` | :221 |
| `FORMAL_EVENT_TYPES` | `set` | :222 |
| `FORMAL_EVENT_STATUSES` | `set` | :223 |
| `FORMAL_FIELD_KEYS` | `set` | :224 |
| `LEGACY_FIELD_KEYS` | `set` | :225 |
| `DEFAULT_LESSON_REFS` | `list[Path]` | :226 |
| `PROJECT_LESSON_REFS` | `dict[str, list[Path]]` | :227 |
| `GOVERNANCE_BLOCKER_SCOPES` | `set[str]` | :228 |
| `EVENT_CONTRACT_BLOCKER_SCOPES` | `set[str]` | :229 |
| `DEFAULT_PROJECT_SCOPE` | `str` | :230 |
| `ROUTE_PROJECT_RUNTIME_SCOPE` | `str` | :231 |
| `SCOPE_MATCH_HINTS` | `dict[str, list[Path]]` | :232 |
| `CORE_EVIDENCE_REFS` | `list[str]` | :246 |
| `POLICY_ALLOWED_SCOPES` | `set[str]` | :251 |
| `CLAUDE_HOOK_STATE_FILE` | `str` | :253 |
| `POLICY_SCOPE_INHERITS` | `dict[str, str]` | :254 |
| `ARTIFACT_COMPACTION` | `dict[str, bool]` | :259 |

### 2.3 惰性单例模式（行 190-238）

Gateway 使用模块级全局变量 + 惰性初始化模式管理核心组件：

| 组件 | 全局变量 | 获取函数 | 行号 |
|------|---------|---------|------|
| PolicyRegistry | `_default_policy_registry` | `_get_policy_registry()` | 178-185 |
| RouteTargetPolicy | `_default_route_policy` | `_get_route_policy()` | 188-196 |
| WriteTargetPolicy | `_default_write_policy` | `_get_write_policy()` | 198-202 |
| GatewayBusinessPolicy | `_default_business_policy` | `_get_gateway_business_policy()` | 103-156 |

---

## 3. Adapter 注册表设计

### 3.1 注册表结构（行 81-83）

```python
_ADAPTER_REGISTRY = {
    "workbot": (".memory_hook_adapters.workbot_runtime_profile", "build_workbot_runtime_profile"),
}
```

当前注册表仅支持 **一个 adapter**：`workbot`。注册表设计为 `dict[str, tuple[str, str]]`，每个条目映射：

- **key**: adapter 名称（通过 `MEMORY_HOOK_ADAPTER` 环境变量选择，默认 `"workbot"`）
- **value**: `(模块路径, 函数名)` 元组

### 3.2 动态加载流程（行 84-91）

1. 从注册表取出模块路径和函数名
2. 通过 `importlib.import_module(_mod_path, package="workspace.tools")` 动态导入
3. `getattr(_mod, _fn_name)` 获取函数引用
4. 调用 `_fn(REPO_ROOT, WORKSPACE_ROOT)` 获取配置 dict
5. `globals().update()` 注入全局变量

### 3.3 扩展方式

要添加新 adapter，需：
1. 在 `memory_hook_adapters/` 下创建 `<name>_runtime_profile.py`，实现 `build_<name>_runtime_profile(repo_root, workspace_root) -> dict`
2. 在 `_ADAPTER_REGISTRY` 中注册条目
3. 设置 `MEMORY_HOOK_ADAPTER=<name>` 环境变量

---

## 4. 全局配置注入机制

### 4.1 注入源

唯一注入源是 `build_workbot_runtime_profile()` 的返回值（workbot_runtime_profile.py 行 192-267），返回 35 个键值对。

### 4.2 注入后的分类使用

**路径类**（用于 canonical 验证、路由目标）：
- `PROJECT_MAP_ROOT`, `TRUTH_MODEL`, `HOOK_CONTRACT_PATH`, `GLOBAL_RULE_PATH`, `MEMORY_SYSTEM_PATH`, `POLICY_PACK_PATH`
- `PROJECT_MAP_FILES`, `REQUIRED_CANONICAL`, `GLOBAL_CANONICAL`, `REGISTRATION_GIT_SCOPE`
- `LOWER_EVIDENCE_ROOTS`, `AUTHORITY_ALLOWED_PATHS`

**策略类**（用于业务决策）：
- `LEGALITY_SOURCE_POLICY`, `REGISTRATION_COMMIT_POLICY`, `REGISTRATION_COMMIT_PHASE`
- `LEGAL_CORE_MARKERS`, `REQUIRED_REGISTRY_SCOPES`
- `GOVERNANCE_BLOCKER_SCOPES`, `EVENT_CONTRACT_BLOCKER_SCOPES`

**映射类**（用于项目作用域解析）：
- `PROJECT_CANONICAL` (scope -> canonical path)
- `PROJECT_RUNTIME_ROOT` (scope -> runtime root)
- `PROJECT_DOC_REFS`, `PROJECT_DECISION_REFS`, `PROJECT_LESSON_REFS`
- `SCOPE_MATCH_HINTS` (scope -> path hints for scope detection)

**运行时类**：
- `GATEWAY_POLICY_CLASS` — 策略类引用，用于 `_get_gateway_business_policy()` 实例化
- `CLAUDE_HOOK_STATE_FILE` — Claude 委托的状态文件路径
- `ARTIFACT_COMPACTION` — 产物压缩策略（控制 output JSON 包含哪些 section）
- `POLICY_ALLOWED_SCOPES`, `POLICY_SCOPE_INHERITS` — 策略注册表配置

---

## 5. 公开函数签名与职责

### 5.1 核心入口

#### `main() -> int`（行 908-977）

CLI 入口函数。执行流程：
1. `parse_args()` — 解析 CLI 参数
2. `sys.stdin.read()` — 读取 raw payload
3. `read_payload()` — 解析 JSON
4. `discover_cwd()` — 发现工作目录
5. `should_noop_for_external_context()` — 检查是否外部上下文
6. `build_context_package()` — 组装上下文包
7. `write_artifacts()` — 写入产物
8. 状态检查：若 `status != "ok"`，写错误日志并返回 1
9. `--no-delegate` 模式：直接输出 JSON 并返回 0
10. 委托分派：`delegate_codex()` 或 `delegate_claude()`
11. 输出代理结果（stdout/stderr）

#### `build_context_package(host, event, payload) -> dict`（行 731-823）

上下文包组装入口。核心步骤：
1. `discover_cwd(payload)` — 发现工作目录
2. `determine_project_scope(cwd)` — 确定项目作用域
3. `_get_gateway_business_policy()` — 获取业务策略
4. 构建 `core_kwargs` dict（37 个参数，见第 6 节）
5. `_resolve_core_builder()` — 选择核心构建器（legacy 或 external-core）
6. 调用 `provider_builder(**core_kwargs)` — 实际组装
7. 注入 `core_provider` 元数据到 system_context
8. Shadow run（可选）：当 `MEMORY_HOOK_SHADOW_RUN` 设定时，并行运行另一 provider 做对比
9. `_apply_artifact_compaction()` — 根据 adapter 策略裁剪输出

### 5.2 参数解析与输入处理

| 函数 | 签名 | 职责 | 行号 |
|------|------|------|------|
| `parse_args` | `() -> argparse.Namespace` | 解析 `--host`, `--event`, `--no-delegate` | 276-280 |
| `read_payload` | `(raw_payload: str) -> dict` | JSON 解析，容错返回空 dict | 285-290 |
| `payload_cwd` | `(payload: dict) -> Path \| None` | 从 payload 提取 cwd | 292-296 |
| `environment_cwd` | `() -> Path \| None` | 从 PWD 环境变量获取 cwd | 298-300 |
| `discover_cwd` | `(payload: dict) -> Path` | 优先级：payload.cwd > env.PWD > REPO_ROOT | 308-317 |

### 5.3 委托分派

| 函数 | 签名 | 职责 | 行号 |
|------|------|------|------|
| `delegate_codex` | `(event: str, raw_payload: str) -> CompletedProcess` | 分派给 Codex 主机 | 900-901 |
| `delegate_claude` | `(event, raw_payload, payload) -> CompletedProcess` | 分派给 Claude 主机 | 904-905 |
| `execute_delegate_via_facade` | `(host, event, raw_payload, payload) -> CompletedProcess` | IF-5 委托门面 | 310-313 |
| `canonicalize_cmux_refs` | `(workspace_ref, surface_ref) -> tuple[str, str]` | 通过 `cmux identify` 规范化引用 | 878-897 |

### 5.4 产物与错误输出

| 函数 | 签名 | 职责 | 行号 |
|------|------|------|------|
| `write_artifacts` | `(package: dict) -> dict[str, str]` | 写入快照 + latest + event log | 851-868 |
| `ensure_artifact_dirs` | `() -> None` | 确保产物目录存在 | 826-831 |
| `append_error_log` | `(component, message, context) -> None` | 写入错误日志 | 833-842 |
| `write_artifacts_via_sink` | `(package: dict) -> dict[str, str]` | IF-5 产物写入门面 | 304-306 |
| `append_error_log_via_sink` | `(component, message, context) -> None` | IF-5 错误日志门面 | 308-309 |

### 5.5 策略与路由门面（IF-5）

| 函数 | 签名 | 职责 | 行号 |
|------|------|------|------|
| `resolve_route_target_via_policy` | `(kind: str) -> str` | 通过 RouteTargetPolicy 解析路由 | 264-266 |
| `write_targets_via_policy` | `() -> dict` | 通过 WriteTargetPolicy 获取写入目标 | 268-270 |
| `get_policy_pack_via_registry` | `(scope: str) -> dict` | 通过 PolicyRegistry 获取策略包 | 272-274 |
| `resolve_policy_conflict_via_registry` | `(key, values, strategy) -> str` | 通过 PolicyRegistry 解决策略冲突 | 276-281 |
| `resolve_route_target` | `(kind: str) -> str` | 带 fallback 的路由解析 | 707-719 |
| `write_targets` | `() -> dict` | 带 fallback 的写入目标获取 | 687-705 |

### 5.6 业务策略代理

| 函数 | 签名 | 职责 | 行号 |
|------|------|------|------|
| `determine_project_scope` | `(cwd: Path) -> str` | 确定项目作用域 | 421-422 |
| `project_map_refs` | `() -> list[str]` | 获取 project-map 引用 | 665-666 |
| `validate_project_map_files` | `() -> list[str]` | 验证 project-map 文件 | 670-671 |
| `validate_unique_legal_system_contract` | `() -> list[str]` | 验证合法系统契约唯一性 | 673-674 |
| `decision_refs_for_scope` | `(scope: str) -> list[str]` | 获取决策引用 | 676-677 |
| `lesson_refs_for_scope` | `(scope: str) -> list[str]` | 获取课程引用 | 679-680 |
| `docs_refs_for_scope` | `(scope: str) -> list[str]` | 获取文档引用 | 682-683 |
| `truth_basis_for_scope` | `(scope: str) -> dict` | 获取真值基础包 | 685-686 |
| `governance_frozen_tuple_blocker_errors` | `() -> list[str]` | 获取治理冻结元组阻塞错误 | 455-456 |
| `event_contract_blocker_errors` | `() -> list[str]` | 获取事件契约阻塞错误 | 458-459 |

### 5.7 工具函数

| 函数 | 签名 | 职责 | 行号 |
|------|------|------|------|
| `now_iso` | `() -> str` | 当前时间 ISO 格式 | 282-283 |
| `extract_excerpt` | `(path: Path, max_lines: int) -> list[str]` | 提取文件前 N 行非空内容 | 424-433 |
| `section_bullets` | `(text, heading) -> list[str]` | 提取 Markdown section 下的 bullet 列表 | 435-445 |
| `section_body` | `(text, heading) -> str` | 提取 Markdown section 的正文 | 447-457 |
| `path_is_under` | `(path, root) -> bool` | 检查路径是否在 root 下 | 477-481 |
| `classify_truth_ref` | `(path: Path) -> str` | 对 truth ref 进行分类标签 | 483-507 |
| `authority_ref_allowed` | `(path: Path) -> bool` | 检查 authority ref 是否被允许 | 509-510 |
| `lower_evidence_ref` | `(path: Path) -> bool` | 检查是否为 lower-layer evidence | 512-513 |
| `truth_basis_sections_for` | `(path: Path) -> dict` | 解析 truth basis 的四个 section | 515-521 |
| `truth_basis_errors_for` | `(path: Path) -> list[str]` | 验证 truth basis 完整性 | 523-561 |
| `git_registration_probe` | `(event, payload) -> dict` | 探测 git 注册状态 | 591-633 |
| `should_noop_for_external_context` | `(payload: dict) -> bool` | 判断是否外部上下文 | 319-331 |
| `_delegate_noop_response` | `(host: str) -> int` | 生成 noop 响应 | 349-356 |
| `_apply_artifact_compaction` | `(package: dict) -> None` | 根据 adapter 策略裁剪产物 | 720-734 |
| `_resolve_core_builder` | `(provider, allow_fallback) -> tuple` | 选择核心构建器 | 165-172 |

---

## 6. core_kwargs 组装：37 个参数来源

`build_context_package()` 行 739-776 构建 `core_kwargs` dict，传递给 `build_context_package_core()`（memory_hook_core.py 行 69-108）。

| # | 参数名 | 来源 | 行号 |
|---|--------|------|------|
| 1 | `host` | CLI 参数 `args.host` | 740 |
| 2 | `event` | CLI 参数 `args.event` | 741 |
| 3 | `payload` | stdin JSON 解析结果 | 742 |
| 4 | `cwd` | `discover_cwd(payload)` | 743 |
| 5 | `project_scope` | `determine_project_scope(cwd)` | 744 |
| 6 | `workspace_root` | 模块常量 `WORKSPACE_ROOT` | 745 |
| 7 | `repo_root` | 模块常量 `REPO_ROOT` | 746 |
| 8 | `required_canonical` | `business_policy.get_required_canonical()` | 747 |
| 9 | `project_canonical` | `business_policy.get_project_canonical()` | 748 |
| 10 | `project_runtime_root` | `business_policy.get_project_runtime_root()` | 749 |
| 11 | `global_canonical` | `business_policy.get_global_canonical()` | 750 |
| 12 | `project_map_governance` | 全局变量 `PROJECT_MAP_GOVERNANCE` | 751 |
| 13 | `event_log` | 模块常量 `EVENT_LOG` | 752 |
| 14 | `legality_source_policy` | 全局变量 `LEGALITY_SOURCE_POLICY` | 753 |
| 15 | `registration_commit_policy` | 全局变量 `REGISTRATION_COMMIT_POLICY` | 754 |
| 16 | `registration_commit_phase` | 全局变量 `REGISTRATION_COMMIT_PHASE` | 755 |
| 17 | `project_map_refs` | `project_map_refs()` (代理到 policy) | 756 |
| 18 | `extract_excerpt_fn` | 模块函数 `extract_excerpt` | 757 |
| 19 | `now_iso_fn` | 模块函数 `now_iso` | 758 |
| 20 | `write_targets_fn` | 模块函数 `write_targets` | 759 |
| 21 | `validate_project_map_fn` | `validate_project_map_files` | 760 |
| 22 | `validate_unique_legal_system_contract_fn` | `validate_unique_legal_system_contract` | 761 |
| 23 | `policy_validate_fn` | lambda: `_get_policy_registry().validate(context)` | 762 |
| 24 | `get_policy_pack_fn` | `get_policy_pack_via_registry` | 763 |
| 25 | `governance_frozen_tuple_errors_fn` | `governance_frozen_tuple_blocker_errors` | 764 |
| 26 | `event_contract_blocker_errors_fn` | `event_contract_blocker_errors` | 765 |
| 27 | `git_registration_probe_fn` | `git_registration_probe` | 766 |
| 28 | `truth_basis_for_scope_fn` | `truth_basis_for_scope` | 767 |
| 29 | `decision_refs_for_scope_fn` | `decision_refs_for_scope` | 768 |
| 30 | `lesson_refs_for_scope_fn` | `lesson_refs_for_scope` | 769 |
| 31 | `docs_refs_for_scope_fn` | `docs_refs_for_scope` | 770 |
| 32 | `hook_contract_path` | 全局变量 `HOOK_CONTRACT_PATH` | 771 |
| 33 | `surface_id` | `os.environ.get("CMUX_SURFACE_ID", "")` | 772 |
| 34 | `workspace_id` | `os.environ.get("CMUX_WORKSPACE_ID", "")` | 773 |
| 35 | `governance_blocker_scopes` | 全局变量 `GOVERNANCE_BLOCKER_SCOPES` | 774 |
| 36 | `event_contract_blocker_scopes` | 全局变量 `EVENT_CONTRACT_BLOCKER_SCOPES` | 775 |
| 37 | `core_evidence_refs` | 全局变量 `CORE_EVIDENCE_REFS` | 776 |

**参数分类**：
- **直接值**（1-7, 12-16, 32-37）：从 CLI、全局变量、环境变量直接传入
- **策略查询**（8-11, 17, 21-22）：通过 business policy 实例的方法动态获取
- **函数引用**（18-20, 23-31）：回调函数，core 模块在组装过程中调用

---

## 7. Host Delegate 分派逻辑

### 7.1 分派入口（main() 行 943-944）

```python
proc = delegate_codex(args.event, raw_payload) if args.host == "codex" else delegate_claude(args.event, raw_payload, payload)
```

### 7.2 Delegate 获取（行 204-224）

`_get_host_delegate(host)` 根据 host 名称创建对应 Delegate 实例：

**CodexDelegate**（行 207-211）：
- 仅需 `which_cmd` 和 `runner` 两个依赖注入
- 内部从 `CMUX_SURFACE_ID` 环境变量获取 surface_id

**ClaudeDelegate**（行 212-222）：
- 需要更多依赖：`repo_root`, `state_file`, `state_path_factory`, `canonicalizer`, `state_recorder`
- `state_file` 来自全局变量 `CLAUDE_HOOK_STATE_FILE`（由 adapter 注入，最终来自 `CMUX_HOOK_STATE_FILE` 环境变量）
- `state_path_factory` = `default_hook_state_path`（来自 cmux_hook_state 模块）
- `canonicalizer` = `canonicalize_cmux_refs`（通过 `cmux identify` 规范化引用）
- `state_recorder` = `record_hook_event`（来自 cmux_hook_state 模块）

### 7.3 Delegate 执行协议

**CodexDelegate.execute()**（impls.py 行 65-82）：
```python
subprocess.run(
    ["cmux", "codex-hook", event],
    input=raw_payload,
    text=True,
    capture_output=True,
)
```

**ClaudeDelegate.execute()**（impls.py 行 123-170）：
1. 检查 `cmux` 在 PATH 中
2. 检查 `CMUX_WORKSPACE_ID` 和 `CMUX_SURFACE_ID` 环境变量
3. 确保 state file 存在（不存在则创建空 JSON）
4. 调用 `cmux identify` 规范化 memory_core/surface 引用
5. 记录 hook state（通过 `state_recorder`）
6. 执行 `["cmux", "claude-hook", event, "--workspace", workspace_id, "--surface", surface_id]`

### 7.4 Noop 响应（行 349-356, 968-976）

当 delegate 不可用或外部上下文时：
1. 调用 `_get_host_delegate(host).noop_response()`
2. CodexDelegate 返回 `{}\n`（impls.py 行 84-86）
3. ClaudeDelegate 返回相同格式的空 JSON（impls.py 行 141-143）
4. Gateway 将 noop stdout 写入 sys.stdout

### 7.5 分派失败处理（行 945-976）

- `RuntimeError` 异常：记录到错误日志，输出到 stderr，返回 1
- 非零 returncode：记录到错误日志（含 stdout/stderr），但仍继续输出结果
- delegate 无 stdout 时：使用 noop_response 的 stdout 作为 fallback（行 970-974）

---

## 附录：关键路径常量

| 常量 | 值 | 定义行 |
|------|-----|--------|
| `SCRIPT_PATH` | `memory_hook_gateway.py` 的绝对路径 | 16 |
| `WORKSPACE_ROOT` | `SCRIPT_PATH.parents[1]` -> `memory_core/` | 17 |
| `REPO_ROOT` | `SCRIPT_PATH.parents[2]` -> `<memory-repo>` | 18 |
| `ARTIFACT_ROOT` | `WORKSPACE_ROOT/artifacts/memory-hook` | 19 |
| `CONTEXT_ROOT` | `ARTIFACT_ROOT/contexts` | 20 |
| `EVENT_LOG` | `ARTIFACT_ROOT/events.jsonl` | 21 |
| `ERROR_LOG` | `WORKSPACE_ROOT/memory/system/errors.log` | 22 |
