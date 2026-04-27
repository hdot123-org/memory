# A1: 架构总览分析

> 生成日期：2026-04-27
> 分析范围：`workspace/` 下全部 Python 源文件

---

## 模块依赖图

### 顶层依赖方向

```
workspace/__init__.py  (空，仅标记包)
    │
    └─ workspace/tools/__init__.py  ──►  lazy-exports 4 个 public API
            │
            ├─ memory_hook_gateway.py        (1028 行) — 网关门面 + CLI 入口
            │   ├─ imports: cmux_hook_state
            │   ├─ imports: memory_hook_core
            │   ├─ imports: memory_hook_config
            │   ├─ imports: memory_hook_interfaces
            │   ├─ imports: memory_hook_impls
            │   ├─ imports: memory_hook_adapters/workbot_runtime_profile
            │   ├─ imports: memory_hook_adapters/workbot_policy
            │   └─ imports: memory_hook_schema
            │
            ├─ memory_hook_core.py           (383 行) — 核心构建逻辑
            │   └─ 仅依赖 typing / pathlib (无内部 import)
            │
            ├─ memory_hook_config.py         (227 行) — CoreConfig dataclass
            │   └─ 仅依赖 typing / pathlib (无内部 import)
            │
            ├─ memory_hook_interfaces.py     (335 行) — ABC 接口定义
            │   └─ 仅依赖 abc / typing / pathlib (无内部 import)
            │
            ├─ memory_hook_impls.py          (1251 行) — 接口实现
            │   ├─ imports: memory_hook_interfaces (ABC 基类)
            │   ├─ imports: memory_hook_config
            │   └─ imports: memory_hook_schema
            │
            ├─ memory_hook_schema.py          (74 行) — v1/v2 格式转换
            │   └─ 仅依赖 typing (无内部 import)
            │
            ├─ memory_hook_provider_rollback.py (60 行) — 回滚探针
            │   └─ imports: memory_hook_gateway (反向依赖)
            │
            ├─ cmux_hook_state.py            — 文件锁 + hook 状态持久化
            │   └─ 仅依赖 stdlib
            │
            ├─ validate_memory_system.py     — 系统验证 CLI
            │   └─ 仅依赖 stdlib + 运行时动态导入
            │
            └─ memory_hook_adapters/
                ├── __init__.py  (空)
                ├── neutral_policy.py        — 宿主中立策略
                │   └─ imports: memory_hook_impls (GatewayBusinessPolicyConfig/Impl)
                ├── workbot_policy.py        — workbot 专属策略
                │   └─ imports: neutral_policy (父类)
                └── workbot_runtime_profile.py — 运行时 profile 构建器
                    └─ imports: workbot_policy
```

### 依赖层级（从高到低）

```
Level 5 (运行时工具)    ── cmux_hook_state, validate_memory_system
Level 4 (门面/入口)     ── memory_hook_gateway
Level 3 (适配/策略)     ── adapters/workbot_policy, adapters/neutral_policy
Level 2 (实现层)        ── memory_hook_impls
Level 1 (接口/配置)     ── memory_hook_interfaces, memory_hook_config, memory_hook_schema
Level 0 (纯核心)        ── memory_hook_core  (零内部依赖)
```

---

## 分层结构评价

### 实际分层

| 层 | 职责 | 对应文件 | 清晰度 |
|----|------|----------|--------|
| **入口层** | CLI 参数解析、env 变量读取、外部调用 | `memory_hook_gateway.py` | ✅ 清晰 |
| **编排层** | CoreConfig 组装、provider 路由、policy 注入 | `memory_hook_gateway._resolve_*` | ✅ 清晰 |
| **核心层** | 上下文包构建的纯函数逻辑 | `memory_hook_core.py` | ✅ 极佳，零内部依赖 |
| **实现层** | ABC 接口的具体实现 | `memory_hook_impls.py` | ✅ 清晰 |
| **接口层** | 抽象基类 + TypedDict 契约 | `memory_hook_interfaces.py` | ✅ 清晰 |
| **适配层** | 宿主/项目专属策略 | `adapters/` | ✅ 清晰 |

### 分层判断

**分层结构清晰**。每层有明确的向上依赖方向，核心层 `memory_hook_core.py` 完全不依赖任何内部模块，仅接收回调函数参数，符合端口-适配器（Hexagonal）架构精神。

---

## 入口链：`build_context_package()` 完整调用链

```
外部调用 (CLI / hook / cmux)
    │
    ▼
build_context_package(host, event, payload)          [gateway.py:755]
    │
    ├─ _discover_cwd(payload)
    ├─ determine_project_scope(cwd)
    ├─ _get_gateway_business_policy()
    │     └─ _build_gateway_business_policy()
    │           └─ GatewayBusinessPolicyConfig(...) + WorkbotGatewayBusinessPolicy
    │
    ├─ CoreConfig(...)  ← 组装 40+ 参数
    │
    ├─ _resolve_core_builder(provider)  ← env: MEMORY_HOOK_CORE_PROVIDER
    │     ├─ "external-core" → 动态 import
    │     └─ "legacy"      → build_context_package_core
    │
    ├─ build_context_package_from_config(config)     [core.py:338]
    │     └─ _resolve_callbacks(config)
    │     └─ build_context_package_core(...)         [core.py:129]
    │           ├─ 各 policy probe 调用
    │           ├─ 证据收集 + truth basis 构建
    │           ├─ registration commit gate 评估
    │           └─ 组装 context package dict
    │
    ├─ provider shadow run (可选, MEMORY_HOOK_SHADOW_RUN)
    ├─ _apply_artifact_compaction(package)
    └─ return package


build_context_package_simple(host, event, payload)   [gateway.py:841]
    │
    └─ build_context_package(...)  →  convert_to_v1(...)  [schema.py]
```

---

## Public API 表面

### `workspace.tools` (via `workspace/tools/__init__.py`)

使用 `__getattr__` 懒加载，导出 4 个符号：

| 符号 | 来源模块 | 类型 | 说明 |
|------|----------|------|------|
| `build_context_package` | `memory_hook_gateway` | `Callable(host, event, payload) -> dict` | 主入口，返回 v2 格式包 |
| `build_context_package_simple` | `memory_hook_gateway` | `Callable(host, event, payload?) -> dict` | 简化入口，返回 v1 格式包 |
| `CoreConfig` | `memory_hook_config` | `@dataclass` | 核心配置对象，40+ 字段 |
| `build_context_package_from_config` | `memory_hook_core` | `Callable(CoreConfig) -> dict` | 从 Config 直接构建 |

### `workspace.tools.memory_hook_gateway` 额外导出

`__all__` 还包含：
- `ArtifactWriter` — 直接写入 artifact 的工具类
- `DelegateRouter` — 宿主代理路由器

### CLI 入口 (pyproject.toml)

| 命令 | 入口 | 说明 |
|------|------|------|
| `memory-validate` | `workspace.tools.validate_memory_system:main` | 系统自检 |
| `memory-rollback` | `workspace.tools.memory_hook_provider_rollback:main` | 回滚探针 |

---

## 循环依赖检查

### 静态分析结果

**存在一个已知的反向依赖**：

```
memory_hook_provider_rollback.py ──► memory_hook_gateway
```

`rollback` 模块 import 了整个 `gateway` 模块来调用 `_resolve_core_builder()`。这不是严格意义的循环（gateway 不 import rollback），而是一个**工具模块依赖主模块**的关系，运行时不会造成 ImportError。

### 运行时验证

```
全部 11 个 .py 文件均可成功 import，无 ImportError
```

**结论**：无真正的循环 import。gateway 内使用 `try/except ImportError` 双路径 import（相对 import + 绝对 import）来兼容包模式和脚本模式，这是一种防御性设计而非循环依赖。

---

## 架构评价

### 优点

1. **核心层零依赖**：`memory_hook_core.py` 不 import 任何内部模块，所有外部能力通过回调注入。这使核心逻辑可独立测试、可被外部替换，符合依赖倒置原则。

2. **接口-实现分离干净**：`memory_hook_interfaces.py` 定义了 8 个 ABC（HostDelegate, PolicyRegistry, RouteTargetPolicy, WriteTargetPolicy, GatewayBusinessPolicy, ArtifactSink, ErrorSink, PathUtils），`memory_hook_impls.py` 提供对应实现。接口和实现分属不同文件，职责边界清晰。

3. **适配层可扩展**：`adapters/` 目录通过 `neutral_policy → workbot_policy → workbot_runtime_profile` 三级继承链，实现了"中立基类 → 项目子类 → 运行时 profile"的可扩展模式。通过 `MEMORY_HOOK_ADAPTER` 环境变量可切换适配器。

4. **Provider 可切换**：`_resolve_core_builder()` 支持 `external-core` / `legacy` 双 provider 路由 + shadow run 对比，为未来的核心替换预留了无风险切换路径。

5. **懒加载公共 API**：`workspace/tools/__init__.py` 使用 `__getattr__` 延迟导入，避免了未使用时加载整个模块树的开销。

### 可改进点

1. **Gateway 文件过大**：`memory_hook_gateway.py` 共 1028 行，承担了 CLI 解析、policy 构建、provider 路由、artifact 写入、adapter 加载等多重职责。建议拆分为 `gateway_cli.py`、`gateway_policy.py`、`gateway_artifacts.py` 等小文件，每个文件 200-300 行。

2. **Impl 文件过于庞大**：`memory_hook_impls.py` 共 1251 行，包含了 10 个类的实现。建议按接口拆分，例如 `impls_delegates.py`、`impls_policies.py`、`impls_sinks.py`。

3. **双重 import 模式增加认知负担**：gateway.py 中每个内部依赖都用 `try/except ImportError` 写了两套 import（相对 + 绝对），共约 50 行。这虽然解决了脚本模式的兼容问题，但增加了维护成本。可考虑用一个统一的 bootstrap 模块处理路径设置。

4. **适配器注册表不够通用**：`_ADAPTER_REGISTRY` 硬编码在 gateway 内部，仅支持 `workbot` 一个适配器。如果有新宿主接入，需要修改 gateway 源码而非配置文件。可改为从外部文件或 entry_points 发现适配器。

5. **缺少类型标注的一致性**：`CoreConfig` 使用了 dataclass + `TYPE_CHECKING`，但 gateway 中的全局变量（如 `_default_policy_registry`）使用 `| None` 联合类型而没有初始化时的类型约束。在严格 mypy 模式下可能有告警。
