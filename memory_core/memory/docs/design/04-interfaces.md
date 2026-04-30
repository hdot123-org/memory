---
type: "[DOC:DESIGN]"
title: "接口契约层"
shortname: DES-004
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [interfaces,contracts,abstractions]
related: [DES-003, DES-005, DES-006]
---

> 文档编号：DES-004 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# 接口契约层设计文档

> 来源：`memory_core/tools/memory_hook_interfaces.py`（242 行）+ `memory_core/tools/memory_hook_impls.py`
> 生成日期：2026-04-26

---

## 1. Abstract Class 列表

| # | 类名 | 文件行号 | 职责 |
|---|------|----------|------|
| 1 | `HostDelegate` | interfaces:23 | 将 hook 事件委派给宿主运行时（Codex / Claude），提供能力探测、执行、降级三条契约 |
| 2 | `PolicyRegistry` | interfaces:58 | 策略查询与校验：按 key 查策略值、校验上下文、获取策略包、冲突消解 |
| 3 | `RouteTargetPolicy` | interfaces:106 | 路由目标解析：将 route kind 映射为目标路径 |
| 4 | `WriteTargetPolicy` | interfaces:119 | 写入目标解析：返回全部写入目标的 key→path 映射 |
| 5 | `GatewayBusinessPolicy` | interfaces:132 | 宿主/业务策略接口：项目作用域解析、规范文件管理、引用解析、truth basis 组装 |
| 6 | `ArtifactSink` | interfaces:218 | 产物输出：将 artifact package 写入磁盘（snapshot + latest + event log） |
| 7 | `ErrorSink` | interfaces:236 | 错误日志输出：结构化 JSON 上下文写入 error log |

---

## 2. Abstract Method 列表（按类分组）

### 2.1 HostDelegate（interfaces:23-52）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `can_handle` | `def can_handle(self) -> bool` | 27 | bool：当前 delegate 是否能处理上下文 | — |
| `execute` | `def execute(self, event: str, raw_payload: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]` | 32 | CompletedProcess（含 returncode + stdout/stderr） | — |
| `noop_response` | `def noop_response(self) -> subprocess.CompletedProcess[str]` | 46 | CompletedProcess：正式运行时不可用时的降级响应 | — |

### 2.2 PolicyRegistry（interfaces:58-99）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `get_policy` | `def get_policy(self, key: str) -> str \| None` | 62 | 策略值或 None | — |
| `validate` | `def validate(self, context: dict[str, Any]) -> list[str]` | 67 | 错误消息列表（空 = 校验通过） | — |
| `get_policy_pack` | `def get_policy_pack(self, scope: str) -> dict[str, Any]` | 76 | 策略包：含 schema_version, policies, conflict_strategy | — |
| `resolve_conflict` | `def resolve_conflict(self, policy_key: str, values: list[str], strategy: str) -> str` | 85 | 消解后的策略值 | ValueError（无法消解时） |

### 2.3 RouteTargetPolicy（interfaces:106-116）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `resolve` | `def resolve(self, kind: str) -> str` | 110 | 目标路径字符串 | ValueError（kind 不支持时） |

### 2.4 WriteTargetPolicy（interfaces:119-129）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `get_targets` | `def get_targets(self) -> dict[str, Any]` | 123 | 目标 key → 路径/配置的映射 | — |

### 2.5 GatewayBusinessPolicy（interfaces:132-211）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `determine_project_scope` | `def determine_project_scope(self, cwd: Path) -> str` | 136 | 项目作用域字符串 | — |
| `get_project_canonical` | `def get_project_canonical(self) -> dict[str, Path]` | 141 | 项目规范映射 | — |
| `get_project_runtime_root` | `def get_project_runtime_root(self) -> dict[str, Path]` | 146 | 项目运行时根映射 | — |
| `get_required_canonical` | `def get_required_canonical(self) -> list[Path]` | 158 | 必须规范文件列表 | — |
| `get_global_canonical` | `def get_global_canonical(self) -> list[Path]` | 164 | 全局规范文件列表 | — |
| `project_map_refs` | `def project_map_refs(self) -> list[str]` | 169 | 项目映射引用路径列表 | — |
| `validate_project_map_files` | `def validate_project_map_files(self) -> list[str]` | 174 | 校验错误列表 | — |
| `validate_unique_legal_system_contract` | `def validate_unique_legal_system_contract(self) -> list[str]` | 179 | 校验错误列表 | — |
| `governance_frozen_tuple_blocker_errors` | `def governance_frozen_tuple_blocker_errors(self) -> list[str]` | 184 | 冻结元组阻塞错误列表 | — |
| `event_contract_blocker_errors` | `def event_contract_blocker_errors(self) -> list[str]` | 189 | 事件契约阻塞错误列表 | — |
| `decision_refs_for_scope` | `def decision_refs_for_scope(self, project_scope: str) -> list[str]` | 194 | 决策引用路径列表 | — |
| `lesson_refs_for_scope` | `def lesson_refs_for_scope(self, project_scope: str) -> list[str]` | 199 | 经验教训引用路径列表 | — |
| `docs_refs_for_scope` | `def docs_refs_for_scope(self, project_scope: str) -> list[str]` | 204 | 文档引用路径列表 | — |
| `truth_basis_for_scope` | `def truth_basis_for_scope(self, project_scope: str) -> dict[str, Any]` | 209 | truth basis 数据包 | — |

### 2.6 ArtifactSink（interfaces:218-233）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `write` | `def write(self, package: dict[str, Any]) -> dict[str, str]` | 222 | 写入路径映射（snapshot, latest） | — |
| `ensure_dirs` | `def ensure_dirs(self) -> None` | 231 | — | — |

### 2.7 ErrorSink（interfaces:236-242）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `log` | `def log(self, component: str, message: str, context: dict[str, Any]) -> None` | 240 | — | — |

---

## 3. 非 Abstract 默认方法

### 3.1 GatewayBusinessPolicy.get_required_gateway_inputs（interfaces:150-156）

```python
def get_required_gateway_inputs(self) -> list[Path]:
    """Return required gateway inputs.

    Default to the legacy required_canonical bridge so older policy
    implementations remain compatible while gateway internals migrate.
    """
    return self.get_required_canonical()
```

- **定位**：这是一个非 abstract 的默认方法（interfaces:150），内部委托给 `get_required_canonical()`（interfaces:158）。
- **意图**：兼容旧实现——在 gateway 内部迁移期间，老策略实现只需实现 `get_required_canonical()`，新调用方使用 `get_required_gateway_inputs()` 即可获得相同结果。

---

## 4. 接口继承/依赖关系

```
                    ┌────────────────────────┐
                    │      ABC (abc)         │
                    └─────────┬──────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
   ┌──────┴──────┐   ┌───────┴───────┐   ┌───────┴──────────┐
   │ HostDelegate │   │PolicyRegistry │   │ RouteTargetPolicy│
   └─────────────┘   └───────────────┘   └──────────────────┘

   ┌──────────────────┐  ┌─────────────────────┐
   │WriteTargetPolicy │  │GatewayBusinessPolicy│
   └──────────────────┘  └─────────────────────┘

   ┌──────────────────┐  ┌──────────────────┐
   │  ArtifactSink    │  │   ErrorSink      │
   └──────────────────┘  └──────────────────┘
```

- 所有 7 个接口均直接继承自 `ABC`（interfaces:14 `from abc import ABC, abstractmethod`），彼此之间**没有**继承关系。
- 接口之间通过**参数/返回值类型**形成依赖：
  - `PolicyRegistry.validate(context: dict[str, Any])` 的 context 参数由调用方构造（impls:285 中检查 `project_scope` key）。
  - `GatewayBusinessPolicy.get_required_gateway_inputs()` 默认实现调用同接口的 `get_required_canonical()`，属于接口内部的方法委托。
  - `ArtifactSink.write(package: dict[str, Any])` 期望 package 包含 `host`、`event` key（impls:1003）。
  - `ErrorSink.log(component, message, context)` 的 context 以 JSON 序列化写入日志（impls:1038）。

---

## 5. 数据协议约定

### 5.1 CoreBuilder 类型别名

**代码中不存在 `CoreBuilder` 类型别名。** `memory_hook_interfaces.py` 和 `memory_hook_impls.py` 均未定义该别名。

### 5.2 PolicyRegistry.validate 上下文结构

根据 impls:285-289 的实现：

```python
def validate(self, context: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if self._allowed_scopes and context.get("project_scope") not in self._allowed_scopes:
        errors.append(f"invalid project_scope: {context.get('project_scope')}")
    return errors
```

- **context 结构**：`dict[str, Any]`，当前仅使用 `project_scope` 一个 key。
- **校验逻辑**：当 registry 配置了 `_allowed_scopes` 时，检查 `context["project_scope"]` 是否在允许列表中；不在则返回错误消息。
- **返回值**：`list[str]`，空列表表示校验通过。

### 5.3 PolicyRegistry.get_policy_pack 返回结构

根据 impls:298-312：

```python
{
    "schema_version": str,
    "scope": str,
    "policies": dict[str, str],
    "conflict_strategies": dict[str, str],
    "default_strategy": str,
    "inherits": str,        # 可选，仅当 scope_inherits 存在时
}
```

### 5.4 GatewayBusinessPolicyConfig（dataclass）

定义于 impls:425-438：

```python
@dataclass(frozen=True)
class GatewayBusinessPolicyConfig:
    repo_root: Path
    workspace_root: Path
    project_map_root: Path
    project_map_files: list[Path]
    project_map_governance: Path
    truth_model: Path
    global_canonical: list[Path]
    authority_allowed_paths: set[Path]
    lower_evidence_roots: list[Path]
    legal_core_markers: list[str]
    required_registry_scopes: list[str]
    project_canonical: dict[str, Path]
```

- 使用 `@dataclass(frozen=True)`，不可变配置 payload。
- 12 个字段，覆盖：仓库根路径、工作区根路径、项目映射配置、truth 模型、全局规范、权限路径、证据根、法律核心标记、注册表作用域、项目规范映射。

### 5.5 GatewayBusinessPolicy.truth_basis_for_scope 返回结构

根据 impls:938-977：

```python
{
    "policy": "source-authority-evidence-conflict",
    "refs": list[str],           # 全局 canonical + 项目文件
    "global_refs": list[str],
    "project_ref": str,
    "source_refs": list[str],
    "authority_refs": list[str],
    "evidence_refs": list[str],
    "conflict_status": list[str],
    "errors": list[str],
    "validation": "pass" | "fail",
}
```

### 5.6 ArtifactSink.write 输入/输出协议

- **输入 package 必需 key**：`host`（str）、`event`（str）（impls:1003）
- **输出**：`{"snapshot": str, "latest": str}`——两个文件的绝对路径字符串
- **副作用**：在 event_log 中追加一行 JSON（impls:1019-1020）

---

## 6. 实现类映射表

| 接口 | 实现类 | 文件 | 行号 |
|------|--------|------|------|
| `HostDelegate` | `CodexDelegate` | impls | 49 |
| `HostDelegate` | `ClaudeDelegate` | impls | 89 |
| `PolicyRegistry` | `PolicyRegistryImpl` | impls | 255 |
| `RouteTargetPolicy` | `RouteTargetPolicyImpl` | impls | 392 |
| `WriteTargetPolicy` | `WriteTargetPolicyImpl` | impls | 412 |
| `GatewayBusinessPolicy` | `GatewayBusinessPolicyImpl` | impls | 545 |
| `ArtifactSink` | `ArtifactSinkImpl` | impls | 984 |
| `ErrorSink` | `ErrorSinkImpl` | impls | 1025 |
