---
type: "[DOC:DESIGN]"
title: "Adapter 层"
shortname: DES-006
status: 草稿中
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [adapters,project-binding]
related: [DES-005, DES-007, DES-009]
---

> 文档编号：DES-006 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# Adapter 层设计

> 生成时间：2026-04-26
> 源码根：`workspace/tools/memory_hook_adapters/`

---

## 1. Adapter 层定位

Adapter 层是 memory-hook gateway 的**项目级适配层**，位于 `workspace/tools/memory_hook_adapters/` 下，承担两个职责：

1. **运行时配置注入**：通过 `build_workbot_runtime_profile()` 生成一个扁平 `dict`，将 workbot 项目的所有路径、策略、约束等配置注入到 gateway 的全局命名空间（`memory_hook_gateway.py` 第 91 行 `globals().update(...)`）。
2. **业务策略适配**：通过 `WorkbotGatewayBusinessPolicy` 继承 `NeutralGatewayBusinessPolicy`（中性默认策略），覆盖 gateway 的业务决策逻辑，实现 workbot 特定的合法性来源、提交策略、policy-pack 合并等行为。

层次关系：

```
Gateway (memory_hook_gateway.py)
  ├── 调用 build_workbot_runtime_profile() → 注入全局配置 dict
  └── 实例化 WorkbotGatewayBusinessPolicy → 驱动业务决策
        └── 继承 NeutralGatewayBusinessPolicy
              └── 继承 GatewayBusinessPolicyImpl (memory_hook_impls.py:468)
                    └── 实现 GatewayBusinessPolicy 接口 (memory_hook_interfaces.py:132)
```

`NeutralGatewayBusinessPolicy`（`neutral_policy.py` 第 14 行）本身不添加任何行为，仅作为 `GatewayBusinessPolicyImpl` 的透传子类，为后续新增中性项目适配器预留扩展点。

---

## 2. workbot_runtime_profile.py 完整 dict

`build_workbot_runtime_profile(repo_root, workspace_root)` 返回的 dict 包含以下键（行号引用自 `workbot_runtime_profile.py`）：

| 键 | 类型 | 说明 | 行号 |
|---|---|---|---|
| `PROJECT_MAP_ROOT` | `Path` | project-map 目录根 | L193 |
| `TRUTH_MODEL` | `Path` | workbot-truth-model.md 路径 | L194 |
| `PROJECT_MAP_FILES` | `list[Path]` | project-map 文件列表（INDEX、legal-core-map、ingestion-registry-map） | L195 |
| `PROJECT_MAP_GOVERNANCE` | `Path` | project-map 治理文档 | L196 |
| `HOOK_CONTRACT_PATH` | `Path` | hook 契约文档 | L197 |
| `GLOBAL_RULE_PATH` | `Path` | 全局路由规则文档 | L198 |
| `MEMORY_SYSTEM_PATH` | `Path` | 记忆系统文档 | L199 |
| `POLICY_PACK_PATH` | `Path` | policy-pack JSON 路径 | L200 |
| `GATEWAY_POLICY_CLASS` | `type` | 指向 `WorkbotGatewayBusinessPolicy` 类对象 | L201 |
| `LEGALITY_SOURCE_POLICY` | `str` | `"active-legal-map-only"` — 仅以 active legal map 为合法性来源 | L202 |
| `REGISTRATION_COMMIT_POLICY` | `str` | `"required-after-absorption-complete"` — 吸收完成后必须提交 | L203 |
| `REGISTRATION_COMMIT_PHASE` | `str` | `"declared-not-enforced"` — 声明但不强制 | L204 |
| `REGISTRATION_GIT_SCOPE` | `list[Path]` | 注册提交涉及的文件范围 | L205, L177-183 |
| `LEGAL_CORE_MARKERS` | `list[str]` | 合法核心标记列表（`active-legal` 等） | L206, L185-190 |
| `REQUIRED_REGISTRY_SCOPES` | `list[str]` | glob 模式列表，定义必须纳入注册的范围 | L207, L27-36 |
| `REQUIRED_CANONICAL` | `list[Path]` | gateway 启动前必须存在的路径清单 | L208, L38-51 |
| `PROJECT_CANONICAL` | `dict[str, Path]` | 项目名 → 项目 canonical 文档映射（workbot/AEdu/platform-capabilities） | L209, L53-57 |
| `PROJECT_RUNTIME_ROOT` | `dict[str, Path]` | 项目名 → 运行时根目录映射 | L210, L59-63 |
| `PROJECT_DOC_REFS` | `dict[str, list[Path]]` | 项目名 → 文档引用列表 | L211, L65-77 |
| `GLOBAL_CANONICAL` | `list[Path]` | 全局 canonical 文件列表 | L212, L79-85 |
| `AUTHORITY_ALLOWED_PATHS` | `set[Path]` | 权威允许的 path 集合 | L213, L87-90 |
| `LOWER_EVIDENCE_ROOTS` | `list[Path]` | 底层证据根目录列表 | L214, L92-99 |
| `DEFAULT_DECISION_REFS` | `list[Path]` | 默认决策索引 | L215, L101-103 |
| `PROJECT_DECISION_REFS` | `dict[str, list[Path]]` | 项目决策索引映射 | L216, L105-109 |
| `GOVERNANCE_FROZEN_TUPLE_FILES` | `list[Path]` | 治理冻结元组文件（AEdu 相关） | L217, L112-117 |
| `EVENT_CONTRACT_FILES` | `dict[str, Path]` | 事件契约文件映射 | L218, L118-127 |
| `FROZEN_TUPLE_EXPECTED` | `set[str]` | 期望的冻结元组标记 | L219, L129-131 |
| `FROZEN_TUPLE_LEGACY_MARKERS` | `set[str]` | 遗留冻结元组标记 | L220, L133-136 |
| `FORMAL_SOURCE_TYPES` | `set[str]` | 正式源类型集合 | L221, L138-141 |
| `FORMAL_EVENT_TYPES` | `set[str]` | 正式事件类型集合 | L222, L143-146 |
| `FORMAL_EVENT_STATUSES` | `set[str]` | 正式事件状态集合 | L223, L148-151 |
| `FORMAL_FIELD_KEYS` | `set[str]` | 正式字段键集合 | L224, L153-158 |
| `LEGACY_FIELD_KEYS` | `set[str]` | 遗留字段键集合 | L225, L159-163 |
| `DEFAULT_LESSON_REFS` | `list[Path]` | 默认经验教训引用 | L226, L165-167 |
| `PROJECT_LESSON_REFS` | `dict[str, list[Path]]` | 项目经验教训引用映射 | L227, L169-175 |
| `GOVERNANCE_BLOCKER_SCOPES` | `set[str]` | 治理阻断范围（`{"AEdu"}`） | L228 |
| `EVENT_CONTRACT_BLOCKER_SCOPES` | `set[str]` | 事件契约阻断范围（`{"AEdu"}`） | L229 |
| `DEFAULT_PROJECT_SCOPE` | `str` | 默认项目作用域（`"workbot"`） | L230 |
| `ROUTE_PROJECT_RUNTIME_SCOPE` | `str` | 路由项目运行时作用域（`"AEdu"`） | L231 |
| `SCOPE_MATCH_HINTS` | `dict[str, list[Path]]` | 作用域匹配提示路径（AEdu / platform-capabilities 的目录提示） | L232-245 |
| `CORE_EVIDENCE_REFS` | `list[str]` | 核心证据引用（字符串路径） | L246-250 |
| `POLICY_ALLOWED_SCOPES` | `set[str]` | 策略允许的作用域集合（`{"workbot", "AEdu", "platform-capabilities"}`） | L251 |
| `CLAUDE_HOOK_STATE_FILE` | `str` | 从环境变量 `CMUX_HOOK_STATE_FILE` 读取的 hook 状态文件路径 | L253 |
| `POLICY_SCOPE_INHERITS` | `dict[str, str]` | 策略作用域继承关系（AEdu → workbot, platform-capabilities → workbot） | L254-257 |
| `ARTIFACT_COMPACTION` | `dict[str, bool]` | 产物压缩策略配置（包含 system/project/task context、evidence refs、allowed reads/writes） | L259-266 |

---

## 3. workbot_policy.py 项目配置

文件：`workbot_policy.py`

### 3.1 模块级策略覆盖

`ADAPTER_POLICIES`（L20-23）定义了两个硬编码策略覆盖：

```python
ADAPTER_POLICIES: dict[str, str] = {
    "legality_source": "active-legal-map-only",
    "registration_commit": "required-after-absorption-complete",
}
```

- `legality_source`：合法性来源策略，限定为仅使用 active legal map。
- `registration_commit`：注册提交策略，要求在吸收完成后必须提交。

### 3.2 WorkbotGatewayBusinessPolicy 类

继承链：`WorkbotGatewayBusinessPolicy` → `NeutralGatewayBusinessPolicy` → `GatewayBusinessPolicyImpl` → `GatewayBusinessPolicy`（ABC）。

**policy-pack 解析路径**（L29-52）：

优先级链：构造函数参数 `policy_pack_path` > 环境变量 `MEMORY_HOOK_POLICY_PACK_PATH` > 默认路径 `workspace/memory/kb/global/memory-hook-policy-pack.json` > `None`。

**inject_policy_pack_config()**（L54-75）：

1. 读取 policy-pack JSON 文件（如果存在）。
2. 先加载 JSON 中的 `policies` 字段。
3. 用 `ADAPTER_POLICIES` 覆盖 JSON 中的同名策略（代码级策略优先级高于文件级）。
4. 返回合并后的配置 dict，包含 `schema_version`、`scope`、`policies`、`conflict_strategies`、`adapter_scope`。

**resolve_policies()**（L77-82）：

1. 从 `PolicyRegistryImpl.DEFAULT_POLICIES` 获取基线策略。
2. 用 `ADAPTER_POLICIES` 覆盖。
3. 返回最终策略 dict。

这保证了 workbot 项目的两个核心策略（合法性来源、提交时机）始终生效，不受外部 policy-pack 文件篡改。

---

## 4. neutral_policy.py 用途

文件：`neutral_policy.py`

`NeutralGatewayBusinessPolicy` 是**主机中性默认业务策略层**（L2 docstring），目前仅做一件事：

```python
class NeutralGatewayBusinessPolicy(GatewayBusinessPolicyImpl):
    def __init__(self, config, scope_config_path=None):
        super().__init__(config=config, scope_config_path=scope_config_path)
```

它不添加任何方法覆盖或属性。设计意图：

1. **扩展点预留**：为未来新增的非 workbot 项目（或其他 host-neutral 消费者）提供继承基类。新适配器只需继承此类并覆盖需要定制的方法。
2. **层次清晰**：在 `GatewayBusinessPolicyImpl`（通用实现）和 `WorkbotGatewayBusinessPolicy`（项目特化）之间插入一个中性层，使继承意图更明确。
3. **导入桥接**：`workbot_policy.py` 通过 `from .neutral_policy import NeutralGatewayBusinessPolicy` 建立继承链（L12），同时兼容 script-mode fallback（L14-16）。

---

## 5. Adapter 发现机制

发现机制实现在 `memory_hook_gateway.py`（L80-91）：

```python
_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "workbot")
_ADAPTER_REGISTRY = {
    "workbot": (".memory_hook_adapters.workbot_runtime_profile", "build_workbot_runtime_profile"),
}
_mod_path, _fn_name = _ADAPTER_REGISTRY[_ADAPTER_NAME]
_mod = importlib.import_module(_mod_path, package="workspace.tools")
_fn = getattr(_mod, _fn_name)
globals().update(_fn(REPO_ROOT, WORKSPACE_ROOT))
```

工作流程：

1. **环境变量选择**：读取 `MEMORY_HOOK_ADAPTER` 环境变量，默认值为 `"workbot"`（L80）。
2. **注册表查找**：在 `_ADAPTER_REGISTRY` dict 中查找对应的模块路径和函数名（L81-83）。当前注册表只有一个条目 `"workbot"`。
3. **动态导入**：通过 `importlib.import_module` 动态加载模块（L86），带 package 前缀 `workspace.tools`。
4. **函数获取**：从模块中获取指定名称的函数（L90）。
5. **全局注入**：调用函数并 `globals().update()` 将返回的 dict 键值对注入 gateway 的全局命名空间（L91）。

这意味着：

- 新增适配器只需在 `_ADAPTER_REGISTRY` 中注册一个条目（键名 = 环境变量值，元组 = (模块路径, 函数名)）。
- 适配器函数签名必须为 `fn(repo_root: Path, workspace_root: Path) -> dict[str, Any]`。
- 返回的 dict 键会直接成为 gateway 模块级全局变量（如 `PROJECT_MAP_ROOT`、`TRUTH_MODEL` 等），供后续代码直接使用。

**Policy 类发现**：runtime profile dict 中的 `GATEWAY_POLICY_CLASS` 键（L201）指向 `WorkbotGatewayBusinessPolicy` 类对象，gateway 在 `_build_gateway_business_policy()`（L103）中通过 `POLICY_CLASS = GATEWAY_POLICY_CLASS` 方式引用并实例化。

---

## 6. 新消费者接入指南

假设新项目名称为 `newproject`，接入步骤如下：

### 6.1 创建运行时 Profile

在 `workspace/tools/memory_hook_adapters/` 下新建 `newproject_runtime_profile.py`：

```python
from pathlib import Path
from typing import Any

def build_newproject_runtime_profile(repo_root: Path, workspace_root: Path) -> dict[str, Any]:
    # 1. 定义项目路径配置
    project_map_root = workspace_root / "project-map"
    # ... 其他路径 ...

    # 2. 定义策略值
    # 3. 返回完整 dict（键名需与 gateway 期望的全局变量一致）
    return {
        "PROJECT_MAP_ROOT": project_map_root,
        "TRUTH_MODEL": ...,
        "GATEWAY_POLICY_CLASS": NewprojectGatewayBusinessPolicy,
        # ... 参见 §2 完整键列表 ...
    }
```

### 6.2 创建业务策略适配器

新建 `newproject_policy.py`：

```python
from pathlib import Path
from typing import Any

try:
    from .neutral_policy import NeutralGatewayBusinessPolicy
    from ..memory_hook_impls import GatewayBusinessPolicyConfig
except ImportError:
    from workspace.tools.memory_hook_adapters.neutral_policy import NeutralGatewayBusinessPolicy
    from workspace.tools.memory_hook_impls import GatewayBusinessPolicyConfig

# 可选：定义项目级策略覆盖
ADAPTER_POLICIES: dict[str, str] = {
    # "legality_source": "...",
    # "registration_commit": "...",
}

class NewprojectGatewayBusinessPolicy(NeutralGatewayBusinessPolicy):
    def __init__(self, config: GatewayBusinessPolicyConfig, scope_config_path: Path | None = None, policy_pack_path: Path | None = None):
        # 可选：自定义 policy-pack 解析逻辑
        super().__init__(config=config, scope_config_path=scope_config_path)

    def resolve_policies(self) -> dict[str, str]:
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl
        base = dict(PolicyRegistryImpl.DEFAULT_POLICIES)
        base.update(ADAPTER_POLICIES)
        return base
```

### 6.3 注册到 Gateway

在 `memory_hook_gateway.py` 的 `_ADAPTER_REGISTRY` 中添加条目：

```python
_ADAPTER_REGISTRY = {
    "workbot": (".memory_hook_adapters.workbot_runtime_profile", "build_workbot_runtime_profile"),
    "newproject": (".memory_hook_adapters.newproject_runtime_profile", "build_newproject_runtime_profile"),
}
```

### 6.4 激活

设置环境变量后调用 gateway：

```bash
MEMORY_HOOK_ADAPTER=newproject python -m workspace.tools.memory_hook_gateway --host codex --event PostCommit
```

### 6.5 必须提供的 dict 键

新适配器的 profile dict 必须包含 gateway 代码中直接引用的全局变量名。核心键包括：

- `PROJECT_MAP_ROOT`、`TRUTH_MODEL`、`PROJECT_MAP_FILES`、`PROJECT_MAP_GOVERNANCE`
- `HOOK_CONTRACT_PATH`、`GLOBAL_RULE_PATH`、`MEMORY_SYSTEM_PATH`、`POLICY_PACK_PATH`
- `GATEWAY_POLICY_CLASS` — 策略类对象
- `LEGALITY_SOURCE_POLICY`、`REGISTRATION_COMMIT_POLICY`
- `REQUIRED_REGISTRY_SCOPES`、`REQUIRED_CANONICAL`
- `PROJECT_CANONICAL`、`PROJECT_RUNTIME_ROOT`、`PROJECT_DOC_REFS`
- `GLOBAL_CANONICAL`、`AUTHORITY_ALLOWED_PATHS`、`LOWER_EVIDENCE_ROOTS`
- `DEFAULT_DECISION_REFS`、`PROJECT_DECISION_REFS`
- `DEFAULT_LESSON_REFS`、`PROJECT_LESSON_REFS`
- `GOVERNANCE_BLOCKER_SCOPES`、`EVENT_CONTRACT_BLOCKER_SCOPES`
- `DEFAULT_PROJECT_SCOPE`、`ROUTE_PROJECT_RUNTIME_SCOPE`、`SCOPE_MATCH_HINTS`
- `POLICY_ALLOWED_SCOPES`、`POLICY_SCOPE_INHERITS`
- `ARTIFACT_COMPACTION`、`CLAUDE_HOOK_STATE_FILE`
- 以及所有 `FORMAL_*`、`LEGACY_*`、`FROZEN_TUPLE_*`、`EVENT_CONTRACT_FILES`、`GOVERNANCE_FROZEN_TUPLE_FILES`、`REGISTRATION_GIT_SCOPE`、`LEGAL_CORE_MARKERS`、`CORE_EVIDENCE_REFS` 系列键

完整参考见 §2 表格。
