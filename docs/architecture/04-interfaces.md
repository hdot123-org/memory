---
type: "[DOC:ARCHITECTURE]"
title: "接口契约层"
shortname: DES-004
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [interfaces,contracts,abstractions]
related: [DES-003, DES-005, DES-006]
---

> 文档编号：DES-004 | 版本：V1.1 | 日期：2026-09-05 | 状态：可评审 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码。

# 接口契约层设计文档

> 来源：`memory_core/tools/memory_hook_interfaces.py`（341 行）+ `memory_core/tools/memory_hook_impls.py`（904 行）
> 校准日期：2026-09-05（v0.45.6；行号均经 `grep -n` 实测）

> **📌 2026-09-05 校准备注**
> 1. `memory_hook_interfaces.py` 现 341 行，模块头仍维持 M2 重构的 IF 编号体系（IF-1 HostDelegate、IF-2 PolicyRegistry、IF-3 Route/WriteTargetPolicy、IF-4 Sink 族、IF-6 PathUtils）。
> 2. 新增两个 `TypedDict(total=False)` 键契约：`TruthBasis`（:21）与 `RegistrationCommitGate`（:36）；`PolicyRegistry.git_registration_probe` / `truth_basis_for_scope` 及 `GatewayBusinessPolicy.truth_basis_for_scope` 的返回类型由裸 dict 收紧为对应 TypedDict。
> 3. `HostDelegate` 新增**非抽象** property `host_unavailable`（:82-89，默认 `False`），用于将 policy_decision 与 delegate 可用性分离。
> 4. `GatewayBusinessPolicy.get_required_gateway_inputs()` 默认桥接方法**已移除**；`get_required_canonical()` 是现存的唯一 canonical 桥接。
> 5. 旧文档第 3 节的细粒度 Protocol（PolicyQueryProvider / GovernanceChecker / TruthBasisProvider）**已移除**，其职责合并回 `PolicyRegistry` 的抽象方法族；`PathUtils`（IF-6）保留。
> 6. 实现层大改：CodexDelegate / ClaudeDelegate 已删除，替换为 FactoryDelegate / NoopHostDelegate + `resolve_host_delegate` 工厂函数（详见 DES-005）。

---

## 1. Abstract Class / TypedDict 列表

| # | 类名 | 类型 | 文件行号 | 职责 |
|---|------|----------|----------|------|
| 1 | `TruthBasis` | TypedDict | interfaces:21 | truth-basis 包的键契约：refs、errors、validation、policy、project_ref、source_refs、authority_refs、evidence_refs、global_refs、conflict_status |
| 2 | `RegistrationCommitGate` | TypedDict | interfaces:36 | 注册提交门控探针的键契约：phase、enforced、gate_event、triggered_on_current_event、enforcement_result、status |
| 3 | `HostDelegate` | ABC | interfaces:52 | 将 hook 事件委派给宿主运行时：能力探测、执行、降级三条契约 + host_unavailable 可用性属性 |
| 4 | `PolicyRegistry` | ABC | interfaces:97 | 策略查询/校验/冲突消解 + 治理校验与 scope 查询（13 个抽象方法） |
| 5 | `RouteTargetPolicy` | ABC | interfaces:193 | 路由目标解析：将 route kind 映射为目标路径 |
| 6 | `WriteTargetPolicy` | ABC | interfaces:206 | 写入目标解析：返回全部写入目标的 key→path 映射 |
| 7 | `GatewayBusinessPolicy` | ABC | interfaces:219 | 宿主/业务策略：项目作用域解析、规范文件管理、引用解析、truth basis 组装（14 个抽象方法） |
| 8 | `ArtifactSink` | ABC | interfaces:298 | 产物输出：将 artifact package 写入磁盘（snapshot + latest + event log） |
| 9 | `ErrorSink` | ABC | interfaces:316 | 错误日志输出：结构化 JSON 上下文写入 error log |
| 10 | `PathUtils` | ABC | interfaces:330 | 路径相关工具回调（IF-6）：extract_excerpt / write_targets |

---

## 2. Abstract Method 列表（按类分组）

### 2.1 HostDelegate（interfaces:52-90）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `can_handle` | `def can_handle(self) -> bool` | 56 | bool：当前 delegate 是否能处理上下文 | — |
| `execute` | `def execute(self, event: str, raw_payload: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]` | 61 | CompletedProcess（含 returncode + stdout/stderr） | — |
| `noop_response` | `def noop_response(self) -> subprocess.CompletedProcess[str]` | 75 | CompletedProcess：正式运行时不可用时的降级响应 | — |
| `host_unavailable`（property，**非抽象**） | `@property def host_unavailable(self) -> bool` | 83 | 默认 `False`；`NoopHostDelegate` 覆写为 `True`，用于分离 policy_decision 与 delegate 可用性 | — |

### 2.2 PolicyRegistry（interfaces:97-187，13 个抽象方法）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `get_policy` | `def get_policy(self, key: str) -> str \| None` | 101 | 策略值或 None | — |
| `validate` | `def validate(self, context: dict[str, Any]) -> list[str]` | 106 | 错误消息列表（空 = 校验通过） | — |
| `get_policy_pack` | `def get_policy_pack(self, scope: str) -> dict[str, Any]` | 115 | 策略包：含 schema_version, policies, conflict_strategies, default_strategy | — |
| `resolve_conflict` | `def resolve_conflict(self, policy_key: str, values: list[str], strategy: str) -> str` | 124 | 消解后的策略值 | ValueError（无法消解时） |
| `validate_project_map` | `def validate_project_map(self) -> list[str]` | 143 | 验证 project-map 合同文件，返回错误列表 | — |
| `validate_unique_legal_system_contract` | `def validate_unique_legal_system_contract(self) -> list[str]` | 148 | 验证唯一合法系统合约，返回错误列表 | — |
| `governance_frozen_tuple_errors` | `def governance_frozen_tuple_errors(self) -> list[str]` | 153 | 返回治理冻结元组阻塞错误 | — |
| `event_contract_blocker_errors` | `def event_contract_blocker_errors(self) -> list[str]` | 158 | 返回事件合约阻塞错误 | — |
| `git_registration_probe` | `def git_registration_probe(self, event: str, payload: dict[str, Any]) -> RegistrationCommitGate` | 163 | 探测 git 注册状态，返回 gate 键契约 | — |
| `truth_basis_for_scope` | `def truth_basis_for_scope(self, scope: str) -> TruthBasis` | 168 | 返回指定 scope 的 truth basis 包 | — |
| `decision_refs_for_scope` | `def decision_refs_for_scope(self, scope: str) -> list[str]` | 173 | 返回指定 scope 的决策引用列表 | — |
| `lesson_refs_for_scope` | `def lesson_refs_for_scope(self, scope: str) -> list[str]` | 178 | 返回指定 scope 的经验教训引用列表 | — |
| `docs_refs_for_scope` | `def docs_refs_for_scope(self, scope: str) -> list[str]` | 183 | 返回指定 scope 的文档引用列表 | — |

### 2.3 RouteTargetPolicy（interfaces:193-202）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `resolve` | `def resolve(self, kind: str) -> str` | 197 | 目标路径字符串 | ValueError（kind 不支持时） |

### 2.4 WriteTargetPolicy（interfaces:206-214）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `get_targets` | `def get_targets(self) -> dict[str, Any]` | 210 | 目标 key → 路径/配置的映射 | — |

### 2.5 GatewayBusinessPolicy（interfaces:219-292，14 个抽象方法）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `determine_project_scope` | `def determine_project_scope(self, cwd: Path) -> str` | 223 | 项目作用域字符串 | — |
| `get_project_canonical` | `def get_project_canonical(self) -> dict[str, Path]` | 228 | 项目规范映射 | — |
| `get_project_runtime_root` | `def get_project_runtime_root(self) -> dict[str, Path]` | 233 | 项目运行时根映射 | — |
| `get_required_canonical` | `def get_required_canonical(self) -> list[Path]` | 238 | 必须规范文件列表（legacy 兼容桥） | — |
| `get_global_canonical` | `def get_global_canonical(self) -> list[Path]` | 243 | 全局规范文件列表 | — |
| `project_map_refs` | `def project_map_refs(self) -> list[str]` | 248 | 项目映射引用路径列表 | — |
| `validate_project_map_files` | `def validate_project_map_files(self) -> list[str]` | 253 | 校验错误列表 | — |
| `validate_unique_legal_system_contract` | `def validate_unique_legal_system_contract(self) -> list[str]` | 258 | 校验错误列表 | — |
| `governance_frozen_tuple_blocker_errors` | `def governance_frozen_tuple_blocker_errors(self) -> list[str]` | 263 | 冻结元组阻塞错误列表 | — |
| `event_contract_blocker_errors` | `def event_contract_blocker_errors(self) -> list[str]` | 268 | 事件契约阻塞错误列表 | — |
| `decision_refs_for_scope` | `def decision_refs_for_scope(self, project_scope: str) -> list[str]` | 273 | 决策引用路径列表 | — |
| `lesson_refs_for_scope` | `def lesson_refs_for_scope(self, project_scope: str) -> list[str]` | 278 | 经验教训引用路径列表 | — |
| `docs_refs_for_scope` | `def docs_refs_for_scope(self, project_scope: str) -> list[str]` | 283 | 文档引用路径列表 | — |
| `truth_basis_for_scope` | `def truth_basis_for_scope(self, project_scope: str) -> TruthBasis` | 288 | truth basis 数据包（TypedDict） | — |

### 2.6 ArtifactSink（interfaces:298-312）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `write` | `def write(self, package: dict[str, Any]) -> dict[str, str]` | 302 | 写入路径映射（snapshot, latest, event_log） | — |
| `ensure_dirs` | `def ensure_dirs(self) -> None` | 311 | — | — |

### 2.7 ErrorSink（interfaces:316-327）

| 方法 | 签名 | 行号 | 返回值 | 异常 |
|------|------|------|--------|------|
| `log` | `def log(self, component: str, message: str, context: dict[str, Any]) -> None` | 319 | — | — |

### 2.8 PathUtils（interfaces:330-341，IF-6）

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `extract_excerpt` | `def extract_excerpt(self, path: Path, max_lines: int = 12) -> list[str]` |
| `write_targets` | `def write_targets(self) -> dict[str, Any]` |

---

## 3. 细粒度 Protocol（已移除）

旧版本的 `PolicyQueryProvider` / `GovernanceChecker` / `TruthBasisProvider` 三个 Protocol **已移除**：当前 `memory_hook_interfaces.py` 不含任何 `Protocol` 定义。其原定职责（策略查询、治理校验、truth-basis 查询）由 `PolicyRegistry` 的 13 个抽象方法统一承载；`CoreConfig`（memory_hook_config.py:21）通过 `policy_registry` / `path_utils` 两个接口对象字段实现等价的依赖注入。`PathUtils`（ABC，IF-6）保留。

---

## 4. 非 Abstract 默认方法

旧文档记录的 `GatewayBusinessPolicy.get_required_gateway_inputs()`（v1 兼容桥接，委托 `get_required_canonical()`）**已移除**。当前接口文件中唯一的非抽象默认成员是：

### 4.1 HostDelegate.host_unavailable（interfaces:82-89）

```python
@property
def host_unavailable(self) -> bool:
    """Whether the host delegate represents an unavailable host.

    NoopHostDelegate returns True; real delegates return False.
    Used to separate policy_decision from delegate availability.
    """
    return False
```

- **定位**：非抽象 property，默认 `False`，真实 delegate（FactoryDelegate）继承默认值，`NoopHostDelegate` 覆写为 `True`。
- **意图**：消费方在解释 `policy_decision` 前应先检查 `host_unavailable`，把"宿主不存在"与"策略决策"两类信号分离。

---

## 5. 接口继承/依赖关系

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

   ┌──────────────────┐  ┌─────────────────────┐  ┌─────────────┐
   │WriteTargetPolicy │  │GatewayBusinessPolicy│  │  PathUtils  │
   └──────────────────┘  └─────────────────────┘  └─────────────┘

   ┌──────────────────┐  ┌──────────────────┐   ┌───────────────────────┐
   │  ArtifactSink    │  │   ErrorSink      │   │ TypedDict: TruthBasis │
   └──────────────────┘  └──────────────────┘   │ RegistrationCommitGate│
                                                 └───────────────────────┘
```

- 8 个 ABC 均直接继承自 `ABC`（interfaces:12 `from abc import ABC, abstractmethod`），彼此之间**没有**继承关系；`GatewayBusinessPolicyImpl`（实现侧）额外混入 `ScopeResolverBase`（见 DES-005）。
- 2 个 TypedDict（`TruthBasis` / `RegistrationCommitGate`）不参与继承，仅作返回值键契约。
- 接口之间通过**参数/返回值类型**形成依赖：
  - `PolicyRegistry.validate(context: dict[str, Any])` 的 context 参数由调用方构造（impls:324 中检查 `project_scope` key）。
  - `PolicyRegistry.git_registration_probe` 与 `evaluate_registration_commit_gate`（memory_hook_core.py:92）通过 `RegistrationCommitGate` 键契约衔接。
  - `ArtifactSink.write(package: dict[str, Any])` 期望 package 包含 `host`、`event` key（impls:682）。
  - `ErrorSink.log(component, message, context)` 的 context 以 JSON 序列化写入日志（impls:776）。

---

## 6. 数据协议约定

### 6.1 CoreBuilder 类型别名

**代码中不存在 `CoreBuilder` 类型别名。** `memory_hook_interfaces.py` 和 `memory_hook_impls.py` 均未定义该别名。结构化配置的角色由 `CoreConfig` dataclass（memory_hook_config.py:21）承担（见 DES-003 第 7 节）。

### 6.2 PolicyRegistry.validate 上下文结构

根据 impls:324-329 的实现：

```python
def validate(self, context: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    # Basic validation - can be extended
    if self._allowed_scopes and context.get("project_scope") not in self._allowed_scopes:
        errors.append(f"invalid project_scope: {context.get('project_scope')}")
    return errors
```

- **context 结构**：`dict[str, Any]`，当前仅使用 `project_scope` 一个 key。
- **校验逻辑**：当 registry 配置了 `_allowed_scopes` 时，检查 `context["project_scope"]` 是否在允许列表中；不在则返回错误消息。
- **返回值**：`list[str]`，空列表表示校验通过。

### 6.3 PolicyRegistry.get_policy_pack 返回结构

根据 impls:331-350：

```python
{
    "schema_version": str,           # 默认 "m3-policy-pack-v1"，可被动态包覆写
    "scope": str,
    "policies": dict[str, str],
    "conflict_strategies": dict[str, str],
    "default_strategy": str,
    "inherits": str,                 # 可选，仅当 scope_inherits 存在时
}
```

### 6.4 GatewayBusinessPolicyConfig（dataclass）

定义于 impls:541-582，`@dataclass(frozen=True)` 不可变配置载体，共 **37 个字段**（36 必填 + `policy_pack_path: Path | None = None` 可选），分组覆盖：仓库/工作区根路径、project-map 配置（root / files / governance）、truth 模型、全局规范、authority 允许路径、底层证据根、legal-core 标记、registry 必需 scope、项目 canonical 与 runtime 映射、decision/lesson/docs 引用表、治理冻结元组与事件合约文件、正式/遗留字段白名单、必需 canonical、workspace/docs/overview/global index 与 hook contract 路径、默认 scope、scope 匹配提示、文本读取回调、可选策略包路径。完整字段清单见 DES-005 第 3.1 节。

### 6.5 GatewayBusinessPolicy.truth_basis_for_scope 返回结构（TruthBasis）

键契约由 `TruthBasis` TypedDict（interfaces:21-33）定义；实际由 `TruthBasisResolver`（business_policy_checks.py:638-706）产出：

```python
{
    "policy": "source-authority-evidence-conflict",
    "refs": list[str],          # 全局 canonical + 项目文件
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

不支持的 scope：`validation: "fail"`、`conflict_status: ["unresolved"]`、`errors` 含 unsupported 消息。

### 6.6 ArtifactSink.write 输入/输出协议

- **输入 package 必需 key**：`host`（str）、`event`（str）（impls:682）
- **注入 `artifact_refs`（5 个 key）**：`snapshot`、`latest`、`daily_latest`、`event_log`（当日 `events/<day>.jsonl`）、`legacy_event_log`（impls:694-700）
- **输出**：`{"snapshot": str, "latest": str, "event_log": str}` — 三个文件的绝对路径字符串
- **副作用**：同一条 JSONL 追加写入当日事件日志与 legacy 事件日志两处（impls:709-714）

---

## 7. 实现类映射表

| 接口 | 实现类 | 文件 | 行号 |
|------|--------|------|------|
| `HostDelegate` | `FactoryDelegate` | impls | 125-150 |
| `HostDelegate` | `NoopHostDelegate` | impls | 152-191 |
| （HostDelegate 解析） | `resolve_host_delegate`（模块级工厂函数） | impls | 194-224 |
| `PolicyRegistry` | `PolicyRegistryImpl` | impls | 227-434 |
| `RouteTargetPolicy` | `RouteTargetPolicyImpl` | impls | 437-503 |
| `WriteTargetPolicy` | `WriteTargetPolicyImpl` | impls | 505-539 |
| `GatewayBusinessPolicy` | `GatewayBusinessPolicyImpl`（混入 ScopeResolverBase） | impls | 584-663 |
| `ArtifactSink` | `ArtifactSinkImpl` | impls | 665-718 |
| `ErrorSink` | `ErrorSinkImpl` | impls | 720-806 |
| （无接口，包装 ArtifactSinkImpl） | `ArtifactWriter` | impls | 808-868 |
| （无接口，路由 FactoryDelegate） | `DelegateRouter` | impls | 870-904 |

已移除的实现：`CodexDelegate`、`ClaudeDelegate`（cmux 宿主集成已退役，由 `FactoryDelegate` / `NoopHostDelegate` 取代，详见 DES-005 第 2 节）。
