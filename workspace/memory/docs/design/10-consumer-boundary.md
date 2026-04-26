---
type: "[DOC:DESIGN]"
title: "消费边界与改进建议"
shortname: DES-010
status: 草稿中
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [consumer-boundary,improvements,suggestions]
related: [DES-001, DES-007, DES-008]
---

> 文档编号：DES-010 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# 消费边界分析与改进建议

> 创建日期：2026-04-26
> 维护人：D10（文档整理员）
> 状态：草稿
> 分析对象：`<memory-repo>`（memory 仓库） vs `<consumer-repo>`（workbot 仓库）

---

## 1. 当前消费面审计

### 1.1 Workbot 调用的 Memory 模块清单

Workbot 通过 **文件复制** 方式消费 memory 模块的全部 Python 代码层。以下是 workbot 仓库中的完整文件列表及其在 memory 仓库中的对应源文件：

| # | Workbot 路径 | Memory 源路径 | Workbot 行数 | Memory 行数 | 差异 |
|---|-------------|---------------|-------------|-------------|------|
| 1 | `workspace/tools/memory_hook_gateway.py` | `workspace/tools/memory_hook_gateway.py` | 1019 | 981 | **+38 行**（独立演化） |
| 2 | `workspace/tools/memory_hook_core.py` | `workspace/tools/memory_hook_core.py` | 271 | 271 | 完全一致 |
| 3 | `workspace/tools/memory_hook_interfaces.py` | `workspace/tools/memory_hook_interfaces.py` | 226 | 242 | **-16 行**（接口裁剪） |
| 4 | `workspace/tools/memory_hook_impls.py` | `workspace/tools/memory_hook_impls.py` | 1273 | 1040 | **+233 行**（独立演化） |
| 5 | `workspace/tools/memory_hook_adapters/workbot_runtime_profile.py` | `workspace/tools/memory_hook_adapters/workbot_runtime_profile.py` | — | 267 | workbot 版本无 `import os`、无 `GATEWAY_POLICY_CLASS`、新增 `HISTORY_PROJECTS_*`、`EXTERNAL_CORE_*` |
| 6 | `workspace/tools/memory_hook_adapters/workbot_policy.py` | `workspace/tools/memory_hook_adapters/workbot_policy.py` | — | 82 | 基本一致 |
| 7 | `workspace/tools/memory_hook_adapters/neutral_policy.py` | `workspace/tools/memory_hook_adapters/neutral_policy.py` | — | 22 | 基本一致 |
| 8 | `workspace/tools/cmux_hook_state.py` | `workspace/tools/cmux_hook_state.py` | — | 225 | 独立文件 |
| 9 | `workspace/tools/validate_memory_system.py` | `workspace/tools/validate_memory_system.py` | — | 12 | 独立文件 |

**关键发现**：workbot 不是通过 pip 安装或符号链接消费 memory 仓库，而是将全部 Python 源码复制到自身仓库中。这意味着两个仓库的代码可以独立演化，但也意味着 memory 上游的改进不会自动传播到 workbot。

### 1.2 37 个 core_kwargs 参数完整列表

`build_context_package()`（gateway 行 768-809）构造的 `core_kwargs` 字典包含 **37 个 keyword-only 参数**，全部传递给 `build_context_package_core()`（core.py 行 69-108）。

| # | 参数名 | 类型 | 来源 | 分类 |
|---|--------|------|------|------|
| 1 | `host` | `str` | CLI `--host` | 直接值 |
| 2 | `event` | `str` | CLI `--event` | 直接值 |
| 3 | `payload` | `dict[str, Any]` | stdin JSON | 直接值 |
| 4 | `cwd` | `Path` | `discover_cwd(payload)` | 直接值 |
| 5 | `project_scope` | `str` | `determine_project_scope(cwd)` | 直接值 |
| 6 | `workspace_root` | `Path` | 模块常量 `WORKSPACE_ROOT` | 直接值 |
| 7 | `repo_root` | `Path` | 模块常量 `REPO_ROOT` | 直接值 |
| 8 | `required_canonical` | `list[Path]` | `business_policy.get_required_gateway_inputs()` | 策略查询 |
| 9 | `project_canonical` | `dict[str, Path]` | `business_policy.get_project_canonical()` | 策略查询 |
| 10 | `project_runtime_root` | `dict[str, Path]` | `business_policy.get_project_runtime_root()` | 策略查询 |
| 11 | `global_canonical` | `list[Path]` | `business_policy.get_global_canonical()` | 策略查询 |
| 12 | `project_map_governance` | `Path` | 全局变量 `PROJECT_MAP_GOVERNANCE` | 直接值 |
| 13 | `event_log` | `Path` | 模块常量 `EVENT_LOG` | 直接值 |
| 14 | `legality_source_policy` | `str` | 全局变量 `LEGALITY_SOURCE_POLICY` | 直接值 |
| 15 | `registration_commit_policy` | `str` | 全局变量 `REGISTRATION_COMMIT_POLICY` | 直接值 |
| 16 | `registration_commit_phase` | `str` | 全局变量 `REGISTRATION_COMMIT_PHASE` | 直接值 |
| 17 | `project_map_refs` | `list[str]` | `project_map_refs()` (代理到 policy) | 策略查询 |
| 18 | `extract_excerpt_fn` | `Callable[[Path], list[str]]` | 模块函数 `extract_excerpt` | 函数引用 |
| 19 | `now_iso_fn` | `Callable[[], str]` | 模块函数 `now_iso` | 函数引用 |
| 20 | `write_targets_fn` | `Callable[[], dict[str, Any]]` | 模块函数 `write_targets` | 函数引用 |
| 21 | `validate_project_map_fn` | `Callable[[], list[str]]` | `validate_project_map_files` | 函数引用 |
| 22 | `validate_unique_legal_system_contract_fn` | `Callable[[], list[str]]` | `validate_unique_legal_system_contract` | 函数引用 |
| 23 | `policy_validate_fn` | `Callable[[dict], list[str]]` | lambda: `_get_policy_registry().validate(context)` | 函数引用 |
| 24 | `get_policy_pack_fn` | `Callable[[str], dict]` | `get_policy_pack_via_registry` | 函数引用 |
| 25 | `governance_frozen_tuple_errors_fn` | `Callable[[], list[str]]` | `governance_frozen_tuple_blocker_errors` | 函数引用 |
| 26 | `event_contract_blocker_errors_fn` | `Callable[[], list[str]]` | `event_contract_blocker_errors` | 函数引用 |
| 27 | `git_registration_probe_fn` | `Callable[[str, dict], dict]` | `git_registration_probe` | 函数引用 |
| 28 | `truth_basis_for_scope_fn` | `Callable[[str], dict]` | `truth_basis_for_scope` | 函数引用 |
| 29 | `decision_refs_for_scope_fn` | `Callable[[str], list[str]]` | `decision_refs_for_scope` | 函数引用 |
| 30 | `lesson_refs_for_scope_fn` | `Callable[[str], list[str]]` | `lesson_refs_for_scope` | 函数引用 |
| 31 | `docs_refs_for_scope_fn` | `Callable[[str], list[str]]` | `docs_refs_for_scope` | 函数引用 |
| 32 | `hook_contract_path` | `Path` | 全局变量 `HOOK_CONTRACT_PATH` | 直接值 |
| 33 | `surface_id` | `str` | `os.environ.get("CMUX_SURFACE_ID", "")` | 直接值 |
| 34 | `workspace_id` | `str` | `os.environ.get("CMUX_WORKSPACE_ID", "")` | 直接值 |
| 35 | `governance_blocker_scopes` | `Collection[str] \| None` | 全局变量 `GOVERNANCE_BLOCKER_SCOPES` | 直接值 |
| 36 | `event_contract_blocker_scopes` | `Collection[str] \| None` | 全局变量 `EVENT_CONTRACT_BLOCKER_SCOPES` | 直接值 |
| 37 | `core_evidence_refs` | `list[str] \| None` | 全局变量 `CORE_EVIDENCE_REFS` | 直接值 |

**参数分类统计**：
- **直接值**（1-7, 12-16, 32-37）：17 个 — 从 CLI、全局变量、环境变量直接传入
- **策略查询**（8-11, 17, 21-22）：7 个 — 通过 business policy 实例的方法动态获取
- **函数引用**（18-20, 23-31）：13 个 — 回调函数，core 模块在组装过程中调用

### 1.3 调用链路全景

```
Claude/Codex Hook
    │
    ▼
cmux_claude_hook_bridge.py (workbot 外部桥接)
    │
    ▼
memory_hook_gateway.py::main()
    ├── parse_args() → host, event, no_delegate
    ├── read_payload() → payload dict
    ├── should_noop_for_external_context() → 外部上下文过滤
    ├── build_context_package(host, event, payload)
    │   ├── discover_cwd(payload) → cwd
    │   ├── determine_project_scope(cwd) → project_scope
    │   ├── _get_gateway_business_policy() → WorkbotGatewayBusinessPolicy
    │   ├── 构造 core_kwargs (37 参数)
    │   ├── _resolve_core_builder(provider) → external-core 或 legacy
    │   └── provider_builder(**core_kwargs) → context package dict
    ├── write_artifacts(package) → 写入 artifacts/contexts/
    ├── delegate_codex() / delegate_claude() → cmux CLI 分派
    └── sys.stdout.write(package) → 返回给 hook 调用方
```

---

## 2. 边界问题分析

### 2.1 核心问题：双 Gateway 独立演化

Memory 仓库的 gateway（981 行）和 Workbot 仓库的 gateway（1019 行）已经出现 **实质性分化**。以下是关键差异点：

#### 2.1.1 Gateway 层差异（38 行差异）

| 差异点 | Memory Gateway | Workbot Gateway | 影响 |
|--------|---------------|-----------------|------|
| 日志路径 | `artifacts/memory-hook/` | `log/memory-hook/` | 产物存储位置不同 |
| Adapter 加载 | `importlib` 动态加载 + `MEMORY_HOOK_ADAPTER` 环境变量 | 直接调用 `build_workbot_runtime_profile()` | memory 支持多 adapter，workbot 硬编码 workbot |
| 接口方法名 | `get_required_canonical()` | `get_required_gateway_inputs()` | **接口不兼容** |
| 全局变量 | `REQUIRED_CANONICAL` | `REQUIRED_GATEWAY_INPUTS` + `HISTORY_PROJECTS_INDEX_PATH` | 配置键名不同 |
| Core Provider 加载 | `allow_fallback=True`（自动回退 legacy） | 无 fallback，`external-core` 失败需手动回滚 | 容错策略不同 |
| External Core 加载 | 仅通过 `MEMORY_HOOK_EXTERNAL_CORE_MODULE` 环境变量 | 支持 `EXTERNAL_CORE_PATH` 文件路径 + 多模块候选 + sys.path 注入 | workbot 加载机制更复杂 |
| Shadow Run | 支持 `MEMORY_HOOK_SHADOW_RUN` 双 provider 对比 | 已移除 | memory 有验证能力，workbot 没有 |
| Artifact Compaction | 支持 `ARTIFACT_COMPACTION` 策略裁剪 | 已移除 | memory 支持产物精简，workbot 全量输出 |
| Noop 响应 | `_delegate_noop_response()` 委托给 delegate 的 `noop_response()` | `noop_for_external_host()` 硬编码 `{}\n` | workbot 简化了 noop 逻辑 |
| CMUX 非正式运行时 | 无特殊处理 | Codex 在无 CMUX 正式标记时返回 noop（行 307-327） | workbot 增加了容错 |
| history-projects 路径 | 无 | `path_is_under()` 新增 `history-root` 分支（行 506-507） | workbot 特有路径逻辑 |
| Truth ref 路径解析 | `REPO_ROOT / Path(item)` 相对路径补全 | 仅 `Path(item).expanduser()`，要求绝对路径 | 路径解析语义不同 |

#### 2.1.2 Interfaces 层差异（16 行差异）

Workbot 的 interfaces 文件（226 行）比 memory（242 行）**少了 16 行**：

- **移除 `noop_response()` 抽象方法**：memory 的 `HostDelegate` 接口定义了 `noop_response()`（IF-1），workbot 将其移除。这意味着 workbot 的 delegate 实现不再需要实现此方法。
- **方法名重命名**：memory 的 `GatewayBusinessPolicy` 接口同时有 `get_required_canonical()`（兼容桥接）和 `get_required_gateway_inputs()`（新方法），workbot 仅保留 `get_required_gateway_inputs()` 并改变了其 docstring。

#### 2.1.3 Impl 层差异（233 行差异）

Workbot 的 impls 文件（1273 行）比 memory（1040 行）**多了 233 行**，主要差异：

- **`import hashlib`**：workbot 新增 hashlib 导入（memory 没有）
- **`CodexDelegate.noop_response()` 简化**：workbot 将 noop 返回值从 `args=[]` 改为 `args=["noop"]`
- **`ClaudeDelegate` 移除 state_file 自动解析**：memory 版本支持从 `CMUX_HOOK_STATE_FILE` 环境变量或 `state_path_factory` 自动解析 state file 路径；workbot 版本要求 `_state_file` 必须注入且非空，否则抛 `RuntimeError`
- **`PolicyRegistryImpl` 构造函数签名变化**：memory 接受 `config: GatewayBusinessPolicyConfig | None` + `default_policies`/`conflict_strategies` 参数；workbot 移除 `config` 参数，使用内置默认值
- **`LEGACY_POLICY_PACK_PATH`**：workbot 新增内置默认策略包路径
- **`LEGACY_DEFAULT_ALLOWED_SCOPES` / `LEGACY_DEFAULT_SCOPE_INHERITS`**：workbot 新增内置默认 scope 配置
- **路径解析差异**：workbot 的 `policy_pack_path` 解析不使用 `path is None` 检查，而是直接检查 `path.exists()`

#### 2.1.4 Runtime Profile 差异

| 差异项 | Memory | Workbot |
|--------|--------|---------|
| `POLICY_PACK_PATH` | 有 | 无 |
| `GATEWAY_POLICY_CLASS` | 有（指向 `WorkbotGatewayBusinessPolicy`） | 无 |
| `HISTORY_PROJECTS_ROOT` | 无 | 有 |
| `HISTORY_PROJECTS_INDEX_PATH` | 无 | 有 |
| `REQUIRED_CANONICAL` | 有 | 重命名为 `REQUIRED_GATEWAY_INPUTS` |
| `DEFAULT_CORE_PROVIDER` | 无 | `"external-core"` |
| `EXTERNAL_CORE_DEFAULT_MODULE` | 无 | `"memory_hook_core"` |
| `EXTERNAL_CORE_RELEASE_REF` | 无 | `"hdot123/memory@main"` |
| `EXTERNAL_CORE_PATH` | 无 | `"~/memory/workspace/tools"` |
| `CLAUDE_HOOK_STATE_FILE` | 有（从环境变量注入） | 无 |
| `ARTIFACT_COMPACTION` | 有 | 无 |
| `legal_core_markers` | 4 个 marker | 6 个 marker（新增"唯一正式历史根"、"history-projects/"） |
| `project_lesson_refs.workbot` | `pm-bot-crawl4ai-runtime-path.md` | `pm-bot-global-binding-and-legacy-fence.md` |

### 2.2 边界问题总结

#### 问题 1：复制而非引用

Workbot 将 memory 的全部 Python 源码复制到自身仓库，导致：
- memory 上游的 bug 修复和改进不会自动传播到 workbot
- 两个仓库的代码可能产生不可预见的行为差异
- 维护两套代码的成本随分化程度线性增长

#### 问题 2：接口不兼容

- memory 使用 `get_required_canonical()` + `get_required_gateway_inputs()` 双方法桥接
- workbot 仅使用 `get_required_gateway_inputs()`
- memory 的 `HostDelegate.noop_response()` 在 workbot 中被移除
- 这意味着 workbot 的 interfaces 和 memory 的 interfaces **不能互换使用**

#### 问题 3：core_kwargs 膨胀

37 个 keyword-only 参数传递给 `build_context_package_core()`，其中：
- 13 个是函数引用（callback），增加了测试和 mock 的复杂度
- 7 个是策略查询，每次调用都通过 business policy 动态获取
- 17 个是直接值，但分散在 gateway 的不同位置（全局变量、环境变量、CLI 参数）

这种设计使得 core 函数的签名极度膨胀，任何新增配置都需要同时修改 gateway 和 core 两个文件。

#### 问题 4：Gateway 职责过重

Gateway 同时承担以下职责：
1. CLI 参数解析
2. 外部上下文过滤
3. Adapter 动态加载
4. Business policy 获取
5. Core kwargs 构造（37 参数）
6. Core provider 解析和 fallback
7. Artifact 写入
8. Host delegate 分派
9. 错误日志记录
10. Shadow run 对比（memory 版本）

这违反了单一职责原则，使得 gateway 文件难以维护和测试。

---

## 3. 理想设计：一个入口一个出口

### 3.1 设计目标

1. **Gateway 是唯一入口**：所有外部调用必须通过 Gateway，不得直接调用 core
2. **Context Package 是唯一出口**：Gateway 返回标准化的 context package dict
3. **Core 是纯函数**：core 模块不依赖任何模块级状态，所有依赖通过参数注入
4. **Adapter 是配置边界**：项目特化配置通过 adapter 层注入，不修改 gateway/core 代码

### 3.2 建议的对外 API 签名

#### 3.2.1 Gateway 入口（CLI）

```python
# memory_hook_gateway.py
# 唯一公开入口：CLI 调用

def main() -> int:
    """CLI 入口：解析参数 → 读取 payload → 构建上下文包 → 写入产物 → 分派委托。
    
    CLI 参数：
        --host: "codex" | "claude"
        --event: "session-start" | "prompt-submit" | "stop" | "notification"
        --no-delegate: 跳过委托分派，仅返回上下文包
    
    stdin: JSON payload
    stdout: JSON context package
    stderr: 错误信息
    
    返回：0 = 成功, 1 = degraded, 2 = error
    """
```

#### 3.2.2 Gateway 入口（Python API）

```python
# memory_hook_gateway.py
# 供 Python 代码直接调用的 API（替代直接调用 core）

def build_context_package(
    host: str,
    event: str,
    payload: dict[str, Any] | None = None,
    *,
    cwd: Path | None = None,
    adapter: str | None = None,
) -> dict[str, Any]:
    """构建上下文包（Python API）。
    
    参数：
        host: 主机标识（"codex" / "claude"）
        event: 事件名
        payload: 事件载荷（可选，默认为空 dict）
        cwd: 工作目录（可选，默认使用当前目录）
        adapter: adapter 名称（可选，默认使用环境变量或 "workbot"）
    
    返回：
        Context package dict，结构见 3.3 节
    
    异常：
        RuntimeError: 当 adapter 加载失败或关键配置缺失时
    """
```

#### 3.2.3 Core 函数签名（内部）

Core 的 37 个参数应该被重构为 **结构化配置对象**，而非扁平的 keyword-only 参数列表。建议：

```python
# memory_hook_core.py（重构后）

@dataclass
class CoreConfig:
    """核心组装配置。将 37 个参数归类为 4 个配置组。"""
    # 组 1：环境信息
    host: str
    event: str
    payload: dict[str, Any]
    cwd: Path
    project_scope: str
    workspace_root: Path
    repo_root: Path
    
    # 组 2：路径配置
    required_canonical: list[Path]
    project_canonical: dict[str, Path]
    project_runtime_root: dict[str, Path]
    global_canonical: list[Path]
    project_map_governance: Path
    event_log: Path
    hook_contract_path: Path
    surface_id: str
    workspace_id: str
    
    # 组 3：策略配置
    legality_source_policy: str
    registration_commit_policy: str
    registration_commit_phase: str
    governance_blocker_scopes: Collection[str] | None
    event_contract_blocker_scopes: Collection[str] | None
    core_evidence_refs: list[str] | None
    
    # 组 4：回调函数（通过 PolicyRegistry 统一封装）
    policy_registry: PolicyRegistry  # 替代 21-26, 28-31 共 10 个 callback
    path_utils: PathUtils  # 替代 18-20 共 3 个 callback


def build_context_package_core(config: CoreConfig) -> dict[str, Any]:
    """核心上下文组装（重构后：单参数）。
    
    参数：
        config: 结构化配置对象
    
    返回：
        Context package dict
    """
```

**重构效果**：
- 37 个参数 → 1 个 `CoreConfig` 对象
- 13 个 callback → 2 个接口对象（`PolicyRegistry` + `PathUtils`）
- 签名从 `def fn(*, a, b, c, ..., z, aa, bb, cc) -> dict` 简化为 `def fn(config) -> dict`

### 3.3 Context Package 返回契约

Gateway 返回的 context package 应遵循以下稳定契约（当前 `wb-hook-v2` 版本）：

```python
{
    # === 元数据 ===
    "schema_version": "wb-hook-v2",          # 固定
    "generated_at": "2026-04-26T12:00:00",   # ISO 时间戳
    "host": "codex",                         # 主机标识
    "event": "session-start",                # 事件名
    
    # === 状态 ===
    "status": "ok" | "degraded",             # 组装状态
    "missing_paths": ["/path/to/missing"],   # 缺失的必需路径
    "validation_errors": ["error message"],  # 验证错误列表
    
    # === 系统上下文 ===
    "system_context": {
        "boot_entry": "...",                 # INDEX.md 路径
        "state_entry": "...",                # NOW.md 路径
        "state_summary": [...],              # NOW.md 摘要
        "project_map_validation": "pass" | "fail",
        "legality_contract_validation": "pass" | "fail",
        "truth_basis_validation": "pass" | "fail",
        "governance_frozen_tuple_validation": "pass" | "fail",
        "event_contract_alignment_validation": "pass" | "fail",
        "registration_commit_enforced": bool,
        "registration_commit_enforcement_result": "...",
        "decision_refs": [...],
        "lesson_refs": [...],
        "docs_refs": [...],
        "policy_pack": {...},
        # ... 其他系统级信息
    },
    
    # === 项目上下文 ===
    "project_context": {
        "scope": "workbot",
        "canonical": "...",
        "truth_basis_canonical": "...",
        "truth_status": "truth-ready" | "truth-incomplete",
        "runtime_root": "...",
        "source_refs": [...],
        "authority_refs": [...],
        "evidence_refs": [...],
        "conflict_status": "...",
    },
    
    # === 任务上下文 ===
    "task_context": {
        "event": "session-start",
        "task_ref": "workbot:session-start",
        "session_id": "...",
        "surface_id": "...",
        "workspace_id": "...",
        "payload_keys": [...],
    },
    
    # === 读写权限 ===
    "allowed_reads": ["/path/to/read"],       # 允许读取的文件列表
    "allowed_writes": {...},                 # 允许写入的目标
    "evidence_refs": ["/path/to/evidence"],  # 证据引用
}
```

**契约保证**：
- `schema_version` 不变时，所有字段均为可选向后兼容新增
- `status` 为 `"ok"` 时表示所有验证通过
- `status` 为 `"degraded"` 时表示部分验证失败但上下文包仍可用
- `validation_errors` 列表为空当且仅当 `status == "ok"`

### 3.4 Gateway 应该成为唯一入口而不是 Core

**当前问题**：workbot 的代码中，`build_context_package_core()` 理论上可以被任何代码直接调用（因为它是公开函数），绕开 gateway 的 adapter 加载、artifact 写入、delegate 分派等逻辑。

**理想状态**：
- `build_context_package_core()` 应标记为 `_build_context_package_core()`（内部函数）
- 所有外部调用必须通过 `build_context_package()`（gateway 公开函数）
- Gateway 负责：adapter 加载 → 配置组装 → core 调用 → artifact 写入 → delegate 分派
- Core 仅负责：纯函数组装逻辑，不依赖任何模块级状态

---

## 4. 迁移路径

### 4.1 阶段 1：统一接口（不改变行为）

**目标**：让 memory 和 workbot 的 interfaces 保持一致。

| 步骤 | 操作 | 文件 | 风险 |
|------|------|------|------|
| 1.1 | workbot interfaces 恢复 `noop_response()` 方法 | `workbot/.../memory_hook_interfaces.py` | 低：仅添加抽象方法，不改变现有实现 |
| 1.2 | workbot interfaces 恢复 `get_required_canonical()` 桥接方法 | `workbot/.../memory_hook_interfaces.py` | 低：桥接方法委托到 `get_required_gateway_inputs()` |
| 1.3 | memory gateway 统一使用 `get_required_gateway_inputs()` | `memory/.../memory_hook_gateway.py` | 低：内部方法名变更 |
| 1.4 | 同步 `ClaudeDelegate` 的 state_file 解析逻辑 | 两边的 `memory_hook_impls.py` | 中：需要确保两边行为一致 |

### 4.2 阶段 2：Core 参数结构化

**目标**：将 37 个 keyword-only 参数重构为 `CoreConfig` 数据类。

| 步骤 | 操作 | 文件 | 风险 |
|------|------|------|------|
| 2.1 | 在 core.py 中定义 `CoreConfig` dataclass | `memory/.../memory_hook_core.py` | 低：新增类型定义 |
| 2.2 | 将 `PolicyRegistry` 接口扩展为包含所有 callback | `memory/.../memory_hook_interfaces.py` | 中：需要确保现有实现兼容 |
| 2.3 | 定义 `PathUtils` 接口封装路径相关 callback | `memory/.../memory_hook_interfaces.py` | 低：新增接口 |
| 2.4 | 重构 `build_context_package_core()` 接受 `CoreConfig` | `memory/.../memory_hook_core.py` | 高：核心函数签名变更 |
| 2.5 | 重构 gateway 的 `core_kwargs` 构造为 `CoreConfig` 构造 | `memory/.../memory_hook_gateway.py` | 高：调用方变更 |
| 2.6 | 同步 workbot 的 core 和 gateway | `workbot/.../memory_hook_core.py`, `memory_hook_gateway.py` | 高：需要同步 |

### 4.3 阶段 3：建立引用而非复制

**目标**：workbot 不再复制 memory 源码，而是通过 pip 安装或符号链接引用。

| 步骤 | 操作 | 文件 | 风险 |
|------|------|------|------|
| 3.1 | memory 仓库发布为 pip 包（`memory-core`） | `memory/pyproject.toml` | 低：已有 pyproject.toml |
| 3.2 | workbot 添加 `memory-core` 依赖 | `workbot/pyproject.toml` 或 `requirements.txt` | 中：需要处理依赖版本 |
| 3.3 | workbot 移除复制的 memory 源码文件 | `workbot/workspace/tools/memory_hook_*.py` | 高：需要确保所有引用正确 |
| 3.4 | workbot 仅保留 adapter 层（项目特化配置） | `workbot/workspace/tools/memory_hook_adapters/` | 中：adapter 需要适配新的接口 |

### 4.4 阶段 4：Gateway 职责精简

**目标**：Gateway 仅负责编排，不直接实现业务逻辑。

| 步骤 | 操作 | 文件 | 风险 |
|------|------|------|------|
| 4.1 | 提取 artifact 写入逻辑到独立 `ArtifactWriter` 类 | `memory/.../memory_hook_impls.py` | 低：逻辑提取 |
| 4.2 | 提取 delegate 分派逻辑到独立 `DelegateRouter` 类 | `memory/.../memory_hook_impls.py` | 低：逻辑提取 |
| 4.3 | 提取 noop 响应逻辑到 `HostDelegate.noop_response()` | `memory/.../memory_hook_interfaces.py` | 低：接口统一 |
| 4.4 | Gateway main() 精简为：parse → build → write → delegate | `memory/.../memory_hook_gateway.py` | 中：重构 main 函数 |

### 4.5 优先级建议

| 优先级 | 阶段 | 理由 |
|--------|------|------|
| P0 | 阶段 1 | 接口不兼容是当前最大的风险，任何一方的变更都可能导致另一方行为异常 |
| P1 | 阶段 4 | Gateway 职责精简可以降低后续维护成本，且不影响外部接口 |
| P2 | 阶段 2 | Core 参数结构化是技术债清理，需要充分测试 |
| P3 | 阶段 3 | 引用替代复制是最终目标，但需要前三个阶段完成后再进行 |

---

## 5. 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| memory 上游修复 bug 但 workbot 未同步 | 高 | 中 | 阶段 3 完成后自动同步 |
| workbot 特化需求与 memory 通用设计冲突 | 中 | 高 | 通过 adapter 层隔离，不修改 core |
| 37 参数 core 签名导致测试覆盖不足 | 中 | 中 | 阶段 2 重构后减少参数数量 |
| Gateway 单点故障影响所有 host | 低 | 高 | 阶段 4 精简后降低复杂度 |
| 迁移过程中出现行为回归 | 中 | 高 | 每个阶段完成后运行完整测试套件 |

---

## 6. 附录

### 6.1 文件路径索引

| 文件 | Memory 路径 | Workbot 路径 |
|------|------------|-------------|
| Gateway | `<memory-repo>/workspace/tools/memory_hook_gateway.py` | `<consumer-repo>/workspace/tools/memory_hook_gateway.py` |
| Core | `<memory-repo>/workspace/tools/memory_hook_core.py` | `<consumer-repo>/workspace/tools/memory_hook_core.py` |
| Interfaces | `<memory-repo>/workspace/tools/memory_hook_interfaces.py` | `<consumer-repo>/workspace/tools/memory_hook_interfaces.py` |
| Impl  s | `<memory-repo>/workspace/tools/memory_hook_impls.py` | `<consumer-repo>/workspace/tools/memory_hook_impls.py` |
| Runtime Profile | `<memory-repo>/workspace/tools/memory_hook_adapters/workbot_runtime_profile.py` | `<consumer-repo>/workspace/tools/memory_hook_adapters/workbot_runtime_profile.py` |
| Workbot Policy | `<memory-repo>/workspace/tools/memory_hook_adapters/workbot_policy.py` | `<consumer-repo>/workspace/tools/memory_hook_adapters/workbot_policy.py` |
| Neutral Policy | `<memory-repo>/workspace/tools/memory_hook_adapters/neutral_policy.py` | `<consumer-repo>/workspace/tools/memory_hook_adapters/neutral_policy.py` |

### 6.2 相关文档

- [01-architecture.md](./01-architecture.md) — Memory 模块架构设计
- [02-gateway.md](./02-gateway.md) — Gateway 设计文档
- [03-core-assembly.md](./03-core-assembly.md) — Core Assembly 设计文档
- [04-interfaces.md](./04-interfaces.md) — 接口设计文档
- [06-adapters.md](./06-adapters.md) — Adapter 设计文档
