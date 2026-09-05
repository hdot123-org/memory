---
type: "[DOC:DESIGN]"
title: "Provider 与回退机制"
shortname: DES-009
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [provider,fallback,resilience]
related: [DES-002, DES-006, DES-008]
---

> 文档编号：DES-009 | 版本：V1.1 | 日期：2026-09-05 | 状态：可评审 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码。

# Provider 与回退机制设计文档

> 来源文件：
> - `memory_core/tools/_gateway_policy.py`（provider 逻辑现址，M3 拆分迁入）
> - `memory_core/tools/memory_hook_gateway.py`（re-export 门面）
> - `memory_core/tools/memory_hook_provider_rollback.py` / `memory_hook_provider_probe.py`
> - `memory_core/tools/memory_hook_core.py`
> 首次生成：2026-04-26 | 最近校准：2026-09-05

> **📌 2026-09-05 校准备注**
>
> 1. **双轨机制仍然存在**，但实现已从 `memory_hook_gateway.py` 迁至 `_gateway_policy.py`（M3 网关拆分）；gateway 门面仅 re-export 两个符号（`memory_hook_gateway.py:154/158`，`__all__` :412-413），monkeypatch 经 `_gateway_patch_redirect.py:99-100` 重定向到 `_gateway_policy`。
> 2. **legacy provider 换芯**：指向的构建函数由 `build_context_package_core`（keyword-only kwargs 签名）改为 `build_context_package_from_config`（单一 `CoreConfig` 参数）；调用方式相应变为 `provider_builder(config)`（`_gateway_policy.py:379`）。
> 3. **external-core 默认短路**：默认模块路径由 `workspace.tools.memory_hook_core` 改为 `memory_core.tools.memory_hook_core`，且默认配置下直接返回静态导入的函数，不再走 `__import__`（`_gateway_policy.py:45-53`）。
> 4. **shadow run 放宽**：对端 provider 解析由 `allow_fallback=False` 改为 `allow_fallback=True`（`_gateway_policy.py:412`）；全仓 `allow_fallback=False` 仅剩一处——`memory-validate` 自检（`validate_memory_system.py:103`）。
> 5. **新增 source-repo 豁免**：memory-core 源码仓跳过消费者校验且不受降级标记影响（`_gateway_policy.py:383-407`）。
> 6. **演练工具双件套**：回滚演练脚本仍在（`memory_hook_provider_rollback.py`，58 行），新增孪生探针 `memory_hook_provider_probe.py`（73 行，显式声明"不做回滚"）；旧测试 `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` 已删除，现行为 `test_provider_rollback.py` / `test_provider_rollback_extended.py` / `test_provider_probe.py` 三个文件覆盖。

---

## 1. Provider 架构：external-core vs legacy 的设计意图

memory-hook gateway 通过 **provider** 抽象将 context package 的构建逻辑与 gateway 编排解耦。系统维护两套 provider 实现：

| Provider | 实现来源 | 加载方式 |
|---|---|---|
| `legacy` | `_gateway_policy.py` 静态导入的 `build_context_package_from_config`（`memory_hook_core.py:507`，`CoreConfig` 单参构建器；`CoreBuilder` 类型别名在 `_gateway_policy.py:42`） | 静态导入，随模块加载 |
| `external-core` | 环境变量指定的模块 + 函数；**默认即 `memory_core.tools.memory_hook_core.build_context_package_from_config`，与 legacy 同函数** | 默认配置短路直返；环境变量覆盖模块/函数时才 `__import__` 动态加载 |

**设计意图**（v0.45.6 语境）：memory-core 现为只读协议库，不存在独立维护的 external core 实现；external-core 面保留为**可插拔实验位**——在不改动 gateway 代码的前提下替换核心构建逻辑（实验性实现、独立仓库维护的 core）。两套实现共享相同签名：`(config: CoreConfig) -> dict[str, Any]`。

默认 provider 为 `legacy`。环境变量 `MEMORY_HOOK_CORE_PROVIDER` 控制选择（`_gateway_policy.py:377`）：

```python
requested_provider = os.environ.get("MEMORY_HOOK_CORE_PROVIDER", "legacy").strip() or "legacy"
```

空字符串也会被规范化为 `"legacy"`。

---

## 2. _load_external_core_builder() 实现

定义于 `_gateway_policy.py:45-58`：

```python
def _load_external_core_builder() -> CoreBuilder:
    """加载外部 core builder。"""
    module_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_MODULE", "memory_core.tools.memory_hook_core")
    func_name = os.environ.get("MEMORY_HOOK_EXTERNAL_CORE_FUNC", "build_context_package_from_config")

    if module_name == "memory_core.tools.memory_hook_core" and func_name == "build_context_package_from_config":
        return build_context_package_from_config

    module = __import__(module_name, fromlist=[func_name])
    builder = getattr(module, func_name)
    if not callable(builder):
        raise TypeError(f"external core builder is not callable: {module_name}.{func_name}")
    return cast(Callable[..., dict[str, Any]], builder)
```

**关键事实**（相对 2026-05 版的变化）：

- 默认模块名由 `workspace.tools.memory_hook_core` 改为 `memory_core.tools.memory_hook_core`，默认函数名由 `build_context_package_core` 改为 `build_context_package_from_config`。
- **新增默认短路**（L50-51）：环境变量未覆盖时直接返回静态导入的 `build_context_package_from_config`，完全跳过 `__import__`——默认配置下 external-core 与 legacy 是同一个函数对象，"外部性"仅体现在可被环境变量覆盖。
- 仅当环境变量指向别处时才 `__import__`（配合 `fromlist` 加载子模块）；`callable()` 守卫防非函数属性；异常（ImportError / AttributeError / TypeError）向上抛出，由 `_resolve_core_builder()` 决定处理。

---

## 3. _resolve_core_builder() 的 allow_fallback 参数

定义于 `_gateway_policy.py:60-73`：

```python
def _resolve_core_builder(provider: str, *, allow_fallback: bool = True) -> tuple[str, CoreBuilder, list[str]]:
    """解析 core builder provider。"""
    if provider == "external-core":
        try:
            return "external-core", _load_external_core_builder(), []
        except Exception as exc:
            if not allow_fallback:
                raise
            return (
                "legacy",
                build_context_package_from_config,
                [f"external-core load failed, fallback to legacy: {exc}"],
            )
    return "legacy", build_context_package_from_config, []
```

**返回值**是三元组 `(provider_name, builder_callable, errors)`：实际使用的 provider 标识（fallback 时与请求不同）、可调用的构建函数（均接受 `CoreConfig`）、错误信息列表（降级原因）。

**allow_fallback 参数语义**：

| allow_fallback | provider="external-core" 且加载失败 | provider="legacy" |
|---|---|---|
| `True`（默认） | 捕获异常，返回 legacy + 错误信息 | 直接返回 legacy |
| `False` | 重新抛出原始异常 | 直接返回 legacy |

`allow_fallback=False` 的**唯一现存调用点**是 `memory-validate` 自检 `check_core_builder_resolve()`（`validate_memory_system.py:98-119`，L103 传 `allow_fallback=False`）——校验 legacy provider 能否解析出 callable。shadow run 原本的 `allow_fallback=False` 已改为 `True`（见 §6）。

---

## 4. allow_fallback=True 时的自动降级行为

`build_context_package()`（`_gateway_policy.py:319-436`）中的降级链（L377-407）：

1. 读取 `MEMORY_HOOK_CORE_PROVIDER`（默认 `legacy`），以 `allow_fallback=True` 解析（L377-378）。
2. 以单一 `CoreConfig` 参数调用构建器：`package = provider_builder(config) if provider_builder is not None else build_context_package_from_config(config)`（L379）。
3. **source-repo 豁免（新增，Bug 3 fix，L383-389）**：若 cwd 是 memory-core 源码仓（develop 模式下运行），强制 `package["status"]="ok"`、清空 `validation_errors` / `missing_paths`，并在 `system_context` 打 `source_repo_skip_validation=True`——源码仓不接受消费者项目的校验语义。
4. 写入 provider 元数据（L393-398）：

```python
system_context["core_provider"] = provider_name            # 实际使用的 provider
system_context["core_provider_requested"] = requested_provider  # 请求的 provider
# 仅 fallback 时：
system_context["core_provider_fallback_errors"] = provider_errors
```

5. 仅当**非源码仓**（`not is_memory_core_source_repo(cwd)`，L400）时：provider_errors 追加进 `package["validation_errors"]`，且 status 为 `"ok"` 时降级为 `"degraded"`（L401-407）。

**降级不阻断执行**：gateway 继续用 legacy builder 完成构建并写 artifact；降级仅通过 `system_context` 元数据与 `status: "degraded"` 可观测（消费项目侧）。

---

## 5. 演练工具双件套

### 5.1 memory_hook_provider_rollback.py（58 行，一键回滚演练）

`run_rollback_drill()`（L21-49）流程：

1. 读取当前请求的 provider（仅记录）；
2. 以 `allow_fallback=True`（默认）分别探测 `"external-core"` 与 `"legacy"`，try/except 兜底防异常逃逸；
3. 计算 `external_probe_ok`（解析为 `"external-core"` 且无错误）与 `legacy_probe_ok`（解析为 `"legacy"` 且无错误）；
4. **判定标准**：`passed = legacy_probe_ok`——legacy 必须可用，系统才具备回退能力；external 探测仅作诊断输出。

`main()`（L52-55）退出码直接映射 status（`passed` → 0，`failed` → 1），可作 preflight 检查。返回 dict 含 `rollback_target: "legacy"`。

### 5.2 memory_hook_provider_probe.py（73 行，新增孪生探针）

`probe_provider_availability()`（L26-64）探测逻辑与 5.1 相同，但模块 docstring 显式声明 **"This module does not perform rollback"**——它只探测两个 provider 的可解析性并输出结构化诊断。保留向后兼容别名 `run_rollback_drill = probe_provider_availability`（L67）。

### 5.3 测试验证

- `tests/test_provider_rollback.py` / `tests/test_provider_rollback_extended.py`：回滚演练语义（含 `MEMORY_HOOK_CORE_PROVIDER` 设定/清除的分支）；
- `tests/test_provider_probe.py`：探针语义与 `main()` 退出码；
- shadow run 覆盖在 `tests/test_gateway_remaining_coverage.py:2046-2093`（`MEMORY_HOOK_SHADOW_RUN=1` + provider=legacy 组合）；
- 2026-05 版引用的 `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` 已删除。

---

## 6. Shadow run 机制（MEMORY_HOOK_SHADOW_RUN）

定义于 `build_context_package()` 内（`_gateway_policy.py:408-431`）：

```python
if os.environ.get("MEMORY_HOOK_SHADOW_RUN"):
    shadow_provider = "external-core" if provider_name == "legacy" else "legacy"
    shadow_result: dict[str, Any]
    try:
        _, shadow_builder, _ = _resolve_core_builder(shadow_provider, allow_fallback=True)
        if shadow_builder is not None:
            shadow_package = shadow_builder(config)
        else:
            shadow_package = build_context_package_from_config(config)
        shadow_result = {
            "provider": shadow_provider,
            "status": shadow_package.get("status"),
            "validation_error_count": len(shadow_package.get("validation_errors", []) or []),
            "ok": True,
        }
    except Exception as exc:
        shadow_result = {"provider": shadow_provider, "ok": False, "error": str(exc)}
    if isinstance(system_context, dict):
        system_context["shadow_run"] = shadow_result
```

**工作机制**：

1. 环境变量 `MEMORY_HOOK_SHADOW_RUN` 存在（值任意非 None）即启用；
2. 选择与当前实际 provider **相反** 的 provider 作为 shadow（legacy ↔ external-core）；
3. 以 **`allow_fallback=True`** 解析 shadow provider——相对 2026-05 版的 `allow_fallback=False` 已放宽：对端加载失败时解析结果退化为 legacy builder，探测的不再是"对端真身可用性"而是"对端请求在当前环境下最终能用什么构建"；
4. 用同一个 `config`（CoreConfig）调用 shadow builder；
5. 结果摘要写入 `system_context["shadow_run"]`。

**Shadow run 输出字段**：

| 字段 | 成功时 | 异常时 |
|---|---|---|
| `provider` | shadow provider 名 | shadow provider 名 |
| `status` | shadow package 的 status | 无此字段 |
| `validation_error_count` | validation_errors 列表长度 | 无此字段 |
| `ok` | `True` | `False` |
| `error` | 无此字段 | 异常字符串 |

**关键约束**：shadow run 的结果**不影响**实际输出的 package 内容，仅作为 `system_context` 中的诊断信息附加。

---

## 7. 默认 provider 是 legacy 的设计意义

`MEMORY_HOOK_CORE_PROVIDER` 默认值为 `"legacy"`（`_gateway_policy.py:377`），稳定性考量不变，但承载物已换：

**legacy 是零外部依赖的内置实现**。`build_context_package_from_config`（`memory_hook_core.py:507`）随 `_gateway_policy` 模块静态加载，不存在 import 失败风险；它从 `CoreConfig`（`memory_hook_config.py`）读取全部依赖（canonical 清单、校验回调、注册 probe 等）。external-core 依赖环境变量指定的模块路径，可能因模块未安装、函数名不匹配、import 链断裂、Python 环境差异而不可用。且默认配置下 external-core 与 legacy 指向同一函数，仅当环境变量覆盖后才存在真实分叉。

> 兼容性备注：kwargs 签名的 `build_context_package_core`（`memory_hook_core.py:331`）仍保留（gateway 门面同步 re-export），供旧调用路径使用；provider 体系的 legacy 指向的是 CoreConfig 版本。

fail-safe 链条（消费项目侧）：

```
请求 external-core → 加载失败 → 自动降级到 legacy → 继续正常执行
请求 legacy → 直接使用 → 正常执行
```

即使 external-core 实现有 bug 或环境配置错误，也不会阻断 gateway 核心功能（构建 artifact、写 event log）。源码仓侧则额外豁免降级标记（§4 步骤 5）。

---

## 8. 新消费者接入时 provider 如何工作

### 8.1 默认路径（无额外配置）

消费者 hook 调用 gateway → `_gateway_policy.py:377` 读取 `MEMORY_HOOK_CORE_PROVIDER`（默认 `legacy`）→ `_resolve_core_builder("legacy")` 直接返回 `build_context_package_from_config` → 构建 context package → 写 artifact。**消费者无需任何 provider 配置**。

### 8.2 切换到 external-core

设置 `MEMORY_HOOK_CORE_PROVIDER=external-core`（可选配 `MEMORY_HOOK_EXTERNAL_CORE_MODULE` / `MEMORY_HOOK_EXTERNAL_CORE_FUNC` 指向自定义实现）：

- 模块可用：provider_name 为 `"external-core"`，使用外部实现；
- 模块不可用：自动降级到 legacy，`system_context.core_provider_fallback_errors` 记录原因，package status 标记 `"degraded"`（memory-core 源码仓豁免此标记）。

### 8.3 可观测性

`system_context` 始终包含 `core_provider`（实际）与 `core_provider_requested`（请求）；fallback 时附加 `core_provider_fallback_errors`；源码仓场景附加 `source_repo_skip_validation`。对比 `core_provider` 与 `core_provider_requested` 即可判断是否发生静默降级。指标侧：`memory_hook_metrics` 从 `system_context.core_provider` 提取该字段计入 metrics 记录（`memory_hook_metrics.py:61-73`）。

### 8.4 Shadow run 验证

切换前可设 `MEMORY_HOOK_SHADOW_RUN=1`：实际执行走当前 provider，对端 provider 并行执行，`system_context["shadow_run"]` 提供对端行为快照。注意 §6 第 3 点——当前实现对 shadow 请求允许 fallback，快照反映的是"对端请求最终解析到的构建器"的行为。

### 8.5 回滚演练与自检

```bash
python3 -m memory_core.tools.memory_hook_provider_rollback   # 退出码 0 = legacy 可用
python3 -m memory_core.tools.memory_hook_provider_probe      # 同语义探针（不做回滚）
memory-validate --target /path/to/project                    # 自检含 check_core_builder_resolve
```

`memory-validate` 的 `check_core_builder_resolve()` 以 `allow_fallback=False` 验证 legacy provider 可解析为 callable（`validate_memory_system.py:98-119`），是部署前/环境变更后的标准 preflight。

---

## 附：与 2026-05-14 版（V1.0）的结构对照

| V1.0 章节 | V1.1 处置 |
|---|---|
| §1 双轨设计意图（gateway.py:782） | 保留，实现迁至 `_gateway_policy.py:377`；legacy 换芯为 `build_context_package_from_config`（§1） |
| §2 _load_external_core_builder（gateway.py:155-163） | 重写为 §2（默认短路 + 模块路径改名） |
| §3 allow_fallback 参数（gateway.py:165-173） | 重写为 §3（唯一 False 调用点改为 memory-validate 自检） |
| §4 自动降级行为 | 重写为 §4（新增 source-repo 豁免） |
| §5 回滚演练脚本 | 重写为 §5（双件套：rollback + probe；测试三件套） |
| §6 Shadow run（gateway.py:800-819） | 重写为 §6（allow_fallback 放宽为 True） |
| §7 默认 legacy 的设计意义 | 保留并更新承载函数（§7） |
| §8 新消费者接入 | 重写为 §8（新增 memory-validate 自检路径） |
