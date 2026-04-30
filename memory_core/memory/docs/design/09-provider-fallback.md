---
type: "[DOC:DESIGN]"
title: "Provider 与回退机制"
shortname: DES-009
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [provider,fallback,resilience]
related: [DES-002, DES-006, DES-008]
---

> 文档编号：DES-009 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# Provider 与回退机制设计文档

> 来源文件：
> - `memory_core/tools/memory_hook_gateway.py`（981 行）
> - `memory_core/tools/memory_hook_provider_rollback.py`（60 行）
> - `memory_core/tools/memory_hook_core.py`（271 行）
> 生成日期：2026-04-26

---

## 1. Provider 架构：external-core vs legacy 的设计意图

memory-hook gateway 通过 **provider** 抽象将 context package 的构建逻辑与 gateway 编排解耦。系统维护两套 provider 实现：

| Provider | 实现来源 | 加载方式 |
|---|---|---|
| `legacy` | gateway 静态导入的 `build_context_package_core`（gateway.py:32/55 行，`CoreBuilder` 为行 152 的 callable 类型别名） | 静态导入，随 gateway 模块加载 |
| `external-core` | 由环境变量指定的模块 + 函数 | 动态 `__import__`，可替换 |

**设计意图**：legacy 是始终可用的安全底；external-core 允许在不改动 gateway 代码的前提下替换核心构建逻辑（例如实验性实现、独立仓库维护的 core）。两套实现共享相同的函数签名（keyword-only 参数，返回 `dict[str, Any]`），确保可互换。

默认 provider 为 `legacy`。环境变量 `MEMORY_HOOK_CORE_PROVIDER` 控制选择（gateway.py:782 行）：

```python
requested_provider = os.environ.get("MEMORY_HOOK_CORE_PROVIDER", "legacy").strip() or "legacy"
```

空字符串也会被规范化为 `"legacy"`。

---

## 2. _load_external_core_builder() 实现

定义于 gateway.py:155-163：

```python
def _load_external_core_builder() -> CoreBuilder:
    module_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_MODULE", "workspace.tools.memory_hook_core")
    func_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_FUNC", "build_context_package_core")
    module = __import__(module_name, fromlist=[func_name])
    builder = getattr(module, func_name)
    if not callable(builder):
        raise TypeError(f"external core builder is not callable: {module_name}.{func_name}")
    return builder
```

**关键事实**：

- 模块名默认 `workspace.tools.memory_hook_core`，函数名默认 `build_context_package_core`。这意味着在默认配置下，external-core 和 legacy 实际上指向同一个函数——external-core 的"外部性"体现在可通过环境变量覆盖。
- 使用 `__import__` 而非 `importlib.import_module`，配合 `fromlist` 确保子模块被正确加载。
- 通过 `callable()` 守卫，防止环境变量指向非函数属性。
- 任何异常（ImportError、AttributeError、TypeError）都会向上抛出，由调用方 `_resolve_core_builder()` 决定如何处理。

---

## 3. _resolve_core_builder() 的 allow_fallback 参数

定义于 gateway.py:165-173：

```python
def _resolve_core_builder(provider: str, *, allow_fallback: bool = True) -> tuple[str, CoreBuilder, list[str]]:
    if provider == "external-core":
        try:
            return "external-core", _load_external_core_builder(), []
        except Exception as exc:
            if not allow_fallback:
                raise
            return "legacy", build_context_package_core, [f"external-core load failed, fallback to legacy: {exc}"]
    return "legacy", build_context_package_core, []
```

**返回值**是一个三元组 `(provider_name, builder_callable, errors)`：

- `provider_name`：实际使用的 provider 标识（可能与请求的不同，当发生 fallback 时）
- `builder_callable`：可调用的构建函数
- `errors`：错误信息列表，fallback 时包含降级原因

**allow_fallback 参数语义**：

| allow_fallback | provider="external-core" 且加载失败 | provider="legacy" |
|---|---|---|
| `True`（默认） | 捕获异常，返回 legacy + 错误信息 | 直接返回 legacy |
| `False` | 重新抛出原始异常 | 直接返回 legacy |

`allow_fallback=False` 的唯一已知调用点在 Shadow run 机制中（gateway.py:804 行），用于探测对端 provider 的真实可用性，不允许 fallback 掩盖问题。

---

## 4. allow_fallback=True 时的自动降级行为

当 `allow_fallback=True`（默认值）且 `provider="external-core"` 加载失败时：

1. 异常被捕获，原始异常信息被格式化为字符串放入 errors 列表
2. 返回值中 `provider_name` 变为 `"legacy"`，与请求的 `"external-core"` 不同
3. `builder_callable` 切换为 gateway 内置的 `build_context_package_core`
4. 调用方 `build_context_package()`（gateway.py:783 行）记录这些信息：

```python
provider_name, provider_builder, provider_errors = _resolve_core_builder(requested_provider, allow_fallback=True)
package = provider_builder(**core_kwargs)
system_context = package.setdefault("system_context", {})
if isinstance(system_context, dict):
    system_context["core_provider"] = provider_name              # 实际使用的 provider
    system_context["core_provider_requested"] = requested_provider  # 用户请求的 provider
    if provider_errors:
        system_context["core_provider_fallback_errors"] = provider_errors  # 降级原因
```

5. 如果有 provider_errors，gateway 将其追加到 `package["validation_errors"]` 列表中（行 793-796）：

```python
if provider_errors:
    package.setdefault("validation_errors", [])
    validation_errors = package.get("validation_errors")
    if isinstance(validation_errors, list):
        validation_errors.extend(provider_errors)
```

6. 若 package 原 status 为 `"ok"`，则将其降级为 `"degraded"`（gateway.py:797-798 行）：

```python
if package.get("status") == "ok":
    package["status"] = "degraded"
```

**降级不影响执行流程**：gateway 继续用 legacy builder 完成 context package 构建并写入 artifact。降级仅通过 `system_context` 中的元数据和 `status: "degraded"` 标记可观测。

---

## 5. memory_hook_provider_rollback.py 完整逻辑

文件位于 `memory_core/tools/memory_hook_provider_rollback.py`（60 行），是 **一键回滚演练工具**。

### 5.1 run_rollback_drill() 函数（第 23-36 行）

```python
def run_rollback_drill() -> dict[str, Any]:
    requested_provider = os.environ.get("MEMORY_HOOK_CORE_PROVIDER", "legacy")
    try:
        external_provider, _, external_errors = gateway._resolve_core_builder("external-core")
    except Exception as exc:
        external_provider = "external-core"
        external_errors = [str(exc)]

    try:
        legacy_provider, _, legacy_errors = gateway._resolve_core_builder("legacy")
    except Exception as exc:
        legacy_provider = "legacy"
        legacy_errors = [str(exc)]

    external_probe_ok = external_provider == "external-core" and not external_errors
    legacy_probe_ok = legacy_provider == "legacy" and not legacy_errors
    passed = legacy_probe_ok
    return {
        "status": "passed" if passed else "failed",
        "requested_provider": requested_provider,
        "external_probe_provider": external_provider,
        "external_probe_errors": external_errors,
        "external_probe_ok": external_probe_ok,
        "legacy_probe_provider": legacy_provider,
        "legacy_probe_errors": legacy_errors,
        "legacy_probe_ok": legacy_probe_ok,
        "rollback_target": "legacy",
    }
```

**执行流程**：

1. 读取当前请求的 provider（仅记录，不影响探测逻辑）
2. 以 `allow_fallback=True`（默认）分别探测 `"external-core"` 和 `"legacy"` 两个 provider，用 try/except 兜底以防异常逃逸
3. 计算 `external_probe_ok`（provider 为 `"external-core"` 且无错误）和 `legacy_probe_ok`（provider 为 `"legacy"` 且无错误）
4. 判定标准：`legacy_probe_ok` 为 `True` → `passed`，否则 `failed`

**判定逻辑的含义**：legacy provider 必须返回 `"legacy"` 标识且无任何错误，才认为系统具备回退能力。`external_probe_ok` 仅作为诊断信息输出，不影响 pass/fail 判定。

### 5.2 main() 函数（第 39-42 行）

```python
def main() -> int:
    result = run_rollback_drill()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1
```

退出码直接映射 status：`"passed"` → 0，`"failed"` → 1。可用于 CI 或 preflight 检查。

### 5.3 测试验证

测试文件 `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` 确认：

- 当 external-core 探测 fallback 到 legacy、legacy 探测正常时 → `status: "passed"`（第 23-39 行）
- 当 fake_resolve 始终返回 `"external-core"`（模拟 legacy 不可用）→ `status: "failed"`（第 42-51 行）
- main() 退出码跟踪 status（第 54-56 行）

---

## 6. Shadow run 机制（MEMORY_HOOK_SHADOW_RUN）

Shadow run 定义于 `build_context_package()` 函数中（gateway.py:800-819 行）：

```python
if os.environ.get("MEMORY_HOOK_SHADOW_RUN"):
    shadow_provider = "external-core" if provider_name == "legacy" else "legacy"
    shadow_result: dict[str, Any]
    try:
        _, shadow_builder, _ = _resolve_core_builder(shadow_provider, allow_fallback=False)
        shadow_package = shadow_builder(**core_kwargs)
        shadow_result = {
            "provider": shadow_provider,
            "status": shadow_package.get("status"),
            "validation_error_count": len(shadow_package.get("validation_errors", []) or []),
            "ok": True,
        }
    except Exception as exc:
        shadow_result = {
            "provider": shadow_provider,
            "ok": False,
            "error": str(exc),
        }
    if isinstance(system_context, dict):
        system_context["shadow_run"] = shadow_result
```

**工作机制**：

1. 当环境变量 `MEMORY_HOOK_SHADOW_RUN` 存在（值任意，`os.environ.get()` 返回非 None 即触发）时启用
2. 选择与当前实际 provider **相反** 的 provider 作为 shadow：
   - 当前用 legacy → shadow 用 external-core
   - 当前用 external-core → shadow 用 legacy
3. 以 `allow_fallback=False` 解析 shadow provider（**不允许降级**，确保探测的是对端真实状态）
4. 用完全相同的 `core_kwargs` 调用 shadow builder
5. 将结果摘要写入 `system_context["shadow_run"]`

**Shadow run 输出字段**：

| 字段 | 成功时 | 异常时 |
|---|---|---|
| `provider` | shadow provider 名 | shadow provider 名 |
| `status` | shadow package 的 status | 无此字段 |
| `validation_error_count` | validation_errors 列表长度 | 无此字段 |
| `ok` | `True` | `False` |
| `error` | 无此字段 | 异常字符串 |

**关键约束**：shadow run 的结果 **不影响** 实际输出的 package 内容。它仅作为诊断信息附加在 `system_context` 中，用于对比两套 provider 的行为差异、验证 external-core 的兼容性。

---

## 7. memory 侧默认 provider 是 legacy 的设计意义

`MEMORY_HOOK_CORE_PROVIDER` 默认值为 `"legacy"`（gateway.py:782 行），这一设计有明确的稳定性考量：

**legacy 是零外部依赖的内置实现**。它随 gateway 模块一起加载，不存在 import 失败的风险。external-core 则依赖环境变量指定的模块路径，可能因以下原因不可用：

- 模块未安装或路径错误
- 函数名不匹配
- 模块内部 import 链断裂
- Python 环境差异

将 legacy 设为默认意味着：**gateway 在任何环境下都能正常构建 context package**，external-core 是"锦上添花"的可选增强，而非运行前提。

结合 `allow_fallback=True` 的自动降级机制，整个 provider 系统形成了一个 **fail-safe 链条**：

```
请求 external-core → 加载失败 → 自动降级到 legacy → 继续正常执行
请求 legacy → 直接使用 → 正常执行
```

这确保了 memory-hook 作为基础设施的可靠性：即使 external-core 实现有 bug 或环境配置错误，也不会阻断 gateway 的核心功能（构建 artifact、写入 event log）。

---

## 8. 新消费者接入时 provider 如何工作

新消费者（如新的 host runtime、新的 hook 触发点）接入时，provider 机制的工作流程如下：

### 8.1 默认路径（无额外配置）

消费者调用 `build_context_package(host, event, payload)` → gateway.py:782 行读取 `MEMORY_HOOK_CORE_PROVIDER`，默认 `"legacy"` → `_resolve_core_builder("legacy", allow_fallback=True)` 直接返回内置 `build_context_package_core` → 构建 context package → 写入 artifact。

**消费者无需做任何 provider 相关配置**，legacy 路径自动生效。

### 8.2 切换到 external-core

消费者设置环境变量 `MEMORY_HOOK_CORE_PROVIDER=external-core`。

如果 external-core 模块可用：provider_name 为 `"external-core"`，使用外部实现。
如果 external-core 模块不可用：自动降级到 legacy，`system_context` 中记录 `core_provider_fallback_errors`，package status 标记为 `"degraded"`。

### 8.3 可观测性

无论哪条路径，`system_context` 中始终包含：

- `core_provider`：实际使用的 provider 标识
- `core_provider_requested`：环境变量请求的 provider 标识
- `core_provider_fallback_errors`：仅 fallback 时存在，记录降级原因

消费者可通过检查 `core_provider` 与 `core_provider_requested` 是否一致来判断是否发生了静默降级。

### 8.4 Shadow run 验证

新消费者在切换到 external-core 之前，可先以 legacy 为默认 provider，同时设置 `MEMORY_HOOK_SHADOW_RUN=1`。此时：

- 实际执行走 legacy（保证稳定性）
- external-core 在 shadow 中并行执行
- `system_context["shadow_run"]` 提供 external-core 的行为快照

消费者可对比 shadow_run 与实际结果的差异，验证 external-core 的兼容性后再正式切换。

### 8.5 回滚演练

消费者可运行 `python3 memory_core/tools/memory_hook_provider_rollback.py` 验证回退能力：

- 退出码 0：legacy provider 可用，系统具备回退能力
- 退出码 1：legacy provider 不可用，存在单点故障风险

这可在部署前或环境变更后作为 preflight 检查使用。
