---
type: "[DOC:DESIGN]"
title: "Adapter 层"
shortname: DES-006
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [adapters,project-binding]
related: [DES-005, DES-007, DES-009]
---

> 文档编号：DES-006 | 版本：V1.1 | 日期：2026-09-05 | 状态：可评审 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码。

# Adapter 层设计

> 首次生成：2026-04-26（workbot/AEdu 适配器时代）
> 最近校准：2026-09-05（v0.45.6，default 适配器时代）
> 源码根：`memory_core/tools/memory_hook_adapters/`

> **📌 2026-09-05 校准备注**
>
> 1. **workbot 时代终结**：`workbot_policy.py`、`workbot_runtime_profile.py` 已删除。适配器目录现仅含 `neutral_policy.py`（31 行）、`default_runtime_profile.py`（245 行）与空 `__init__.py` 三个文件（实测 `ls`）。
> 2. **默认适配器易主**：`MEMORY_HOOK_ADAPTER` 默认值由 `workbot` 改为 `default`，`_ADAPTER_REGISTRY` 仅剩 `default` 一个条目（`_gateway_config.py:262-265`）；`consistency_check.py` 的 `check_adapter_registry_complete()`（L394-425）守护该条目不被移除。
> 3. **注入机制重写**：M3 网关拆分后不再 `globals().update()`。runtime profile 载入线程安全的 `_adapter_config` dict，经 `get_config(key)` 读取（`_gateway_config.py:283-306`），内存中仅此一份配置。
> 4. **消费项目适配方式改变**：新消费项目不写 Python 适配器，由 `memory-init` 写入 `memory/system/adapter.toml`，经 `adapter_toml_schema.py`（318 行）加载校验，`default_runtime_profile.py` 装配为运行时配置。
> 5. **配置面新增 `[global_kb]`**（v0.8.0+）：profile dict 新增 `GLOBAL_KB_ROOT` / `GLOBAL_KB_ENABLED` 两键（`default_runtime_profile.py:243-244`），驱动三层架构（Layer 1/2/3）的项目优先/全局兜底路由。

---

## 1. Adapter 层定位

Adapter 层是 memory-hook gateway 的**项目级适配层**，位于 `memory_core/tools/memory_hook_adapters/` 下。v0.45.6 时点只剩一个宿主中性的默认适配器（`default`），承担两个职责：

1. **运行时配置装配**：`build_default_runtime_profile()`（`default_runtime_profile.py:25`）读取目标项目的 `memory/system/adapter.toml`（经 `adapter_toml_schema.load_adapter_toml`，L43-44），生成扁平 dict 并载入 `_gateway_config._adapter_config`。gateway 各拆分模块通过线程安全的 `get_config(key)` 读取（`_gateway_config.py:287-291`），不再向模块全局命名空间注入变量。
2. **业务策略基座**：`NeutralGatewayBusinessPolicy`（`neutral_policy.py:15`）是 `GatewayBusinessPolicyImpl`（`memory_hook_impls.py:584`）的宿主中性透传子类，作为默认策略类挂接在 profile 的 `GATEWAY_POLICY_CLASS` 键上。

层次关系：

```
Gateway 门面 (memory_hook_gateway.py — M3 拆分后的纯 re-export 层)
  └── _gateway_config.py（配置层，最底层）
        ├── _load_adapter_profile("default") → 调用 build_default_runtime_profile()
        │     └── load_adapter_toml(<project>/memory/system/adapter.toml)
        ├── _adapter_config dict（线程安全：get_config / get_config_dict / reload_adapter）
        └── _get_gateway_business_policy()（_gateway_config.py:342）
              └── GATEWAY_POLICY_CLASS，缺省 NeutralGatewayBusinessPolicy（:388）
                    └── 继承 GatewayBusinessPolicyImpl (memory_hook_impls.py:584)
                          └── 实现 GatewayBusinessPolicy 接口 (memory_hook_interfaces.py:219)
```

`memory_hook_gateway.py` 本身已瘦身为纯 re-export 门面：M3 网关拆分为 `_gateway_config` / `_gateway_artifacts` / `_gateway_policy` / `_gateway_telemetry` / `_gateway_dispatch` / `_gateway_handlers` 六个单一职责模块（均 ≤500 行），适配器配置的真正消费者是这些拆分模块。

---

## 2. default_runtime_profile.py 完整 dict

`build_default_runtime_profile(repo_root, workspace_root=None)`（L25）以 `workspace_root`（缺省回退 `repo_root`，L42）为项目根装配配置。返回 dict 的键如下（返回块整体位于 L196-245，行号为键所在行）：

### 2.1 路径与文件类

| 键 | 值 | 行号 |
|---|---|---|
| `PROJECT_MAP_ROOT` | `<project>/project-map` | L197（定义于 L63） |
| `TRUTH_MODEL` | `memory/kb/global/truth-model.md` | L198（L65） |
| `PROJECT_MAP_FILES` | project-map 三件套：INDEX / legal-core-map / ingestion-registry-map | L199（L73-77） |
| `PROJECT_MAP_GOVERNANCE` | `memory/kb/global/project-map-governance.md` | L200（L69） |
| `HOOK_CONTRACT_PATH` | `memory/kb/global/hook-contract.md` | L201（L68） |
| `GLOBAL_RULE_PATH` | `memory/kb/global/memory-routing.md` | L202（L67） |
| `MEMORY_SYSTEM_PATH` | `memory/kb/global/memory-system.md` | L203（L66） |
| `POLICY_PACK_PATH` | `memory/kb/global/policy-pack.json` — 可选文件，缺失时 `PolicyRegistryImpl` 回退内置默认策略 | L204（L70） |
| `REQUIRED_CANONICAL` | truth-model / memory-system / memory-routing 三件 | L212（L80-84） |
| `GLOBAL_CANONICAL` | 上述三件 + hook-contract + project-map-governance 共 5 件 | L216（L90-96） |
| `AUTHORITY_ALLOWED_PATHS` | 7 个路径的集合：project-map INDEX/legal-core-map + 5 个全局 canonical | L217（L123-130） |
| `LOWER_EVIDENCE_ROOTS` | `[<project>/tools, <repo>/tests]` | L218（L132-135） |

### 2.2 策略与策略类

| 键 | 值 | 行号 |
|---|---|---|
| `GATEWAY_POLICY_CLASS` | `NeutralGatewayBusinessPolicy` 类对象 | L205（L104） |
| `LEGALITY_SOURCE_POLICY` | `adapter.toml [policy].legality_source_policy`，默认 `"map-only"`（`adapter_toml_schema.py:103`） | L206（L99） |
| `REGISTRATION_COMMIT_POLICY` | `adapter.toml [policy].registration_commit_policy`，默认 `"same-commit"`（`adapter_toml_schema.py:104`） | L207（L100） |
| `REGISTRATION_COMMIT_PHASE` | `adapter.toml [policy].registration_commit_phase`，默认 `"post"`（`adapter_toml_schema.py:105`） | L208（L101） |
| `LEGAL_CORE_MARKERS` | `["active-legal", "project-map/INDEX.md", "truth-model.md", "memory-system.md"]` | L210（L159-163） |
| `POLICY_ALLOWED_SCOPES` | `{project_scope}` — 单元素集合 | L238（L117） |
| `POLICY_SCOPE_INHERITS` | `{}` — 无跨 scope 继承 | L240（L118） |

### 2.3 注册与范围类

| 键 | 值 | 行号 |
|---|---|---|
| `REGISTRATION_GIT_SCOPE` | project-map INDEX + project-map-governance + hook-contract | L209（L152-156） |
| `REQUIRED_REGISTRY_SCOPES` | 8 个 glob：`project-map/**`、`memory/kb/global/**`、`memory/kb/projects/**`、`memory/docs/**`、`memory/log/**`、`memory_core/projects/**`、`memory_core/tools/**`、`tests/**` | L211（L165-174） |
| `PROJECT_CANONICAL` | `{scope: memory/kb/projects/{scope}.md}` | L213（L86-88） |
| `PROJECT_RUNTIME_ROOT` | `{scope: <project>/projects}` | L214（L147-149） |
| `DEFAULT_PROJECT_SCOPE` | `adapter.toml [routing].project_scope`，缺失回退 `"default"`（L47） | L234 |
| `ROUTE_PROJECT_RUNTIME_SCOPE` | 同 `project_scope` | L235（L188） |
| `SCOPE_MATCH_HINTS` | `{scope: []}` — 空提示列表 | L236（L189） |
| `CORE_EVIDENCE_REFS` | memory-system / memory-routing / hook-contract 的字符串路径 | L237（L190-194） |

### 2.4 引用类（空初始化）

| 键 | 值 | 行号 |
|---|---|---|
| `DEFAULT_DECISION_REFS` / `PROJECT_DECISION_REFS` | 空列表 / `{scope: []}` | L219-220（L138-139） |
| `DEFAULT_LESSON_REFS` / `PROJECT_LESSON_REFS` | 空列表 / `{scope: []}` | L230-231（L140-141） |
| `PROJECT_DOC_REFS` | `{scope: []}` | L215（L144） |

### 2.5 AEdu 时代治理集合（现全部为空）

| 键 | 值 | 行号 |
|---|---|---|
| `GOVERNANCE_FROZEN_TUPLE_FILES` / `EVENT_CONTRACT_FILES` | `[]` / `{}` | L221-222（L177-178） |
| `FROZEN_TUPLE_EXPECTED` / `FROZEN_TUPLE_LEGACY_MARKERS` | 空集合 | L223-224（L179-180） |
| `FORMAL_SOURCE_TYPES` / `FORMAL_EVENT_TYPES` / `FORMAL_EVENT_STATUSES` / `FORMAL_FIELD_KEYS` / `LEGACY_FIELD_KEYS` | 空集合 | L225-229（L181-185） |
| `GOVERNANCE_BLOCKER_SCOPES` / `EVENT_CONTRACT_BLOCKER_SCOPES` | 空集合 | L232-233（L119-120） |

> 这些键在 workbot/AEdu 时代承载硬编码的项目治理字面量；机制本身保留在 `GatewayBusinessPolicyImpl` 与 `business_policy_checks.py`（见 DES-007 §7），默认适配器将其全部置空，等价于零成本关闭。

### 2.6 运行时杂项与全局 KB

| 键 | 值 | 行号 |
|---|---|---|
| `CLAUDE_HOOK_STATE_FILE` | 环境变量 `CMUX_HOOK_STATE_FILE`，缺省 `None` | L239 |
| `ARTIFACT_COMPACTION` | 6 个 `include_*` 开关，默认全 `True`（system/project/task context、evidence refs、allowed reads/writes） | L241（L107-114） |
| `GLOBAL_KB_ROOT` | `adapter.toml [global_kb].root` 展开后的 Path（v0.8.0+，默认 `~/.memory/global-kb`） | L243 |
| `GLOBAL_KB_ENABLED` | `adapter.toml [global_kb].enabled`（默认 `True`） | L244 |

---

## 3. workbot_policy.py（已删除）

`workbot_policy.py` 与 `workbot_runtime_profile.py` 已随 workbot 时代终结删除（本节保留标题以记录处置）：

- **模块级策略覆盖**（原 `ADAPTER_POLICIES` 的 `legality_source` / `registration_commit` 两键）：迁移为消费项目 `adapter.toml [policy]` 段的 `legality_source_policy` / `registration_commit_policy` / `registration_commit_phase` 三键（`adapter_toml_schema.py:103-105`），由 schema 校验而非代码硬编码。
- **policy-pack 解析与合并**（原 `inject_policy_pack_config()`）：统一收口到 `PolicyRegistryImpl`（`memory_hook_impls.py:227`），详见 DES-007 §1。
- **策略类继承层**（原 `WorkbotGatewayBusinessPolicy`）：删除。当前唯一的策略类是中性基类 `NeutralGatewayBusinessPolicy`。

---

## 4. neutral_policy.py 用途

文件：`neutral_policy.py`（31 行）

`NeutralGatewayBusinessPolicy`（L15）是**宿主中性默认业务策略层**（L2 docstring：`Host-neutral gateway business policy layer`），仅做一件事：

```python
class NeutralGatewayBusinessPolicy(GatewayBusinessPolicyImpl):
    """Host-neutral default business policy implementation."""

    def __init__(
        self,
        config: GatewayBusinessPolicyConfig,
        scope_config_path: Path | None = None,
    ):
        super().__init__(config=config, scope_config_path=scope_config_path)
```

它不添加任何方法覆盖或属性。设计意图：

1. **默认策略类**：`default_runtime_profile` 将其挂接在 `GATEWAY_POLICY_CLASS`（L104）；`_get_gateway_business_policy()` 读取该键且以此为缺省（`_gateway_config.py:388`）。
2. **扩展点预留**：未来若需要项目特化策略，继承此类并覆盖需要定制的方法，再通过 profile 的 `GATEWAY_POLICY_CLASS` 注入。
3. **导入桥接**：包内相对导入失败时回退 `memory_core.tools.*` 绝对导入（L6-12，script-mode fallback）。

测试：`tests/test_neutral_policy.py`。

---

## 5. Adapter 发现机制

发现机制实现在 `_gateway_config.py`（M3 拆分后自 `memory_hook_gateway.py` 迁入）：

```python
# _gateway_config.py:262-265
_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "default")
_ADAPTER_REGISTRY = {
    "default": (".memory_hook_adapters.default_runtime_profile", "build_default_runtime_profile"),
}
```

加载与存取（`_gateway_config.py:268-323`）：

1. **环境变量选择**：读取 `MEMORY_HOOK_ADAPTER`，默认值 `"default"`（L262）。
2. **注册表查找**：在 `_ADAPTER_REGISTRY` 查找 `(模块路径, 函数名)` 二元组（L275-277）；未知名字抛 `KeyError: unknown adapter`。
3. **动态导入**：`importlib.import_module(_mod_path, package="memory_core.tools")`（L278）——包前缀已从 workbot 时代的 `workspace.tools` 改为 `memory_core.tools`。
4. **函数调用**：`_fn(repo_root, workspace_root)` 返回 profile dict（L280）。
5. **存入配置仓**：模块加载时执行 `_adapter_profile = _load_adapter_profile(_ADAPTER_NAME, REPO_ROOT, WORKSPACE_ROOT)` + `load_adapter_config(...)`（L306-307）；此后的读取全部走 `get_config(key)` / `get_config_dict()`（L287-296），写入受 `_config_lock` 线程锁保护。
6. **热切换**：`reload_adapter(adapter_name=None)`（L310-323）可在进程内重新加载指定适配器（测试使用）。

与旧机制的关键差异：**返回 dict 不再 `globals().update()` 注入 gateway 命名空间**。键即 `get_config()` 的查询契约（如 `get_config("PROJECT_MAP_ROOT")`），由各拆分模块按需读取。

**注册表守护**：`consistency_check.py` 的 `check_adapter_registry_complete()`（L394-425）检查 `_gateway_config.py` 中 `_ADAPTER_REGISTRY` 必须含 `"default"` 条目，缺失即报错（workbot 条目已归档，不再要求）。

**Policy 类发现**：`_get_gateway_business_policy()`（`_gateway_config.py:342-390`）组装 `GatewayBusinessPolicyConfig` 后，以 `policy_class = _adapter_config.get("GATEWAY_POLICY_CLASS", NeutralGatewayBusinessPolicy)`（L388）实例化策略类。

**测试**：`tests/test_default_adapter_smoke.py`（`MEMORY_HOOK_ADAPTER=default` 下 status='ok' 回归）、`tests/test_routing_fallback.py`（含 `GLOBAL_KB_ROOT` 注入断言，L308-314）、`tests/test_init_global_kb_integration.py`、`tests/test_cross_project_sedimentation.py`。

---

## 6. 新消费者接入指南

v0.45.6 起，消费项目接入 memory-core 的标准路径是**配置文件而非代码**。

### 6.1 标准路径：adapter.toml（无需写代码）

```bash
memory-init --target /path/to/project [--scope my-project] [--host factory|zcode]
```

`memory-init` 在目标项目 `memory/system/adapter.toml` 写入规范布局，并幂等创建全局知识库 `~/.memory/global-kb/`：

```toml
[core]
version = "0.45.6"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "my-project"
host = "factory"
canonical_files = []

[global_kb]
enabled = true
root = "~/.memory/global-kb"
```

- 各段键白名单由 `adapter_toml_schema.py` 定义：`[core]`（version、adapter）、`[policy]`（3 键）、`[routing]`（project_name、project_scope、host、canonical_files、artifact_root）、`[global_kb]`（enabled、root）。
- `load_adapter_toml(path, strict=True)`（`adapter_toml_schema.py:163`）做严格校验：未知键、空 `project_scope` / `project_name`、不支持的 host 均抛 `ValueError`。legacy 单段 `[adapter]` 布局仍向后兼容。
- `routing.project_scope` 驱动 §2 中全部 scope 派生键（PROJECT_CANONICAL、POLICY_ALLOWED_SCOPES、PROJECT_RUNTIME_ROOT 等）；`[global_kb]` 驱动三层路由兜底（v0.8.0+，`memory-migrate --from 0.7.0 --to 0.8.0` 可向存量项目补注入该段）。
- 布局校验用 `memory-validate --target /path/to/project`；适配器 schema 测试见 `tests/test_adapter_toml_strict.py`、`tests/test_adapter_toml_global_kb.py`、`tests/test_p2_adapter_toml_structured.py`、`tests/test_p4_adapter_toml.py`。

### 6.2 库级新适配器（仅 memory-core 源码仓）

只有当默认适配器无法表达新语义时（例如需要新的策略类），才在库层面新增适配器：

1. 在 `memory_core/tools/memory_hook_adapters/` 下新建 `xxx_runtime_profile.py`，签名 `fn(repo_root: Path, workspace_root: Path | None = None) -> dict[str, Any]`。
2. 在 `_gateway_config.py` 的 `_ADAPTER_REGISTRY` 注册条目（键名 = 环境变量值）。
3. 如需自定义策略类，继承 `NeutralGatewayBusinessPolicy` 并通过返回 dict 的 `GATEWAY_POLICY_CLASS` 键注入。
4. 返回 dict 的键是 `get_config()` 查询契约，需覆盖 gateway 读取的全部键（完整清单见 §2 表格；缺省键由 `get_config(key, default)` 兜底）。

### 6.3 激活

```bash
MEMORY_HOOK_ADAPTER=default memory-hook-gateway --host factory --event session-start
```

默认即 `default`，消费项目通常无需设置该变量。

---

## 附：与 2026-05-14 版（V1.0）的结构对照

| V1.0 章节 | V1.1 处置 |
|---|---|
| §2 workbot_runtime_profile 完整 dict | 重写为 §2 default_runtime_profile dict（键面基本一致，值源改为 adapter.toml，新增 GLOBAL_KB_* 两键） |
| §3 workbot_policy.py | 标记已删除，处置说明见 §3 |
| §5 MEMORY_HOOK_ADAPTER 机制（globals().update） | 重写为 §5（_adapter_config 存储机制） |
| §6 新消费者接入（写 Python 适配器） | 重写为 §6（adapter.toml 标准路径优先，库级适配器降为例外路径） |
