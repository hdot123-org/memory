# A7: Adapters 分析报告

> 分析日期: 2026-04-27 | 源码根: `workspace/tools/memory_hook_adapters/`

---

## 1. 适配器架构

### 1.1 层级关系

```
GatewayBusinessPolicy (ABC, interfaces)
  └── GatewayBusinessPolicyImpl (通用实现, memory_hook_impls.py)
        └── NeutralGatewayBusinessPolicy (中性基类, neutral_policy.py)  ← 空壳透传
              └── WorkbotGatewayBusinessPolicy (workbot 特化, workbot_policy.py)
```

### 1.2 neutral vs workbot 的区别

| 维度 | neutral_policy.py | workbot_policy.py |
|---|---|---|
| **定位** | 主机中性默认策略，不绑定任何项目 | workbot 项目专属适配器 |
| **行为** | 零覆盖，纯透传 `GatewayBusinessPolicyImpl` | 覆盖 2 个策略、注入 policy-pack、合并策略 |
| **职责** | 扩展点 / 继承基类 | 实际业务决策驱动 |
| **策略覆盖** | 无 | `ADAPTER_POLICIES` (2 项硬编码覆盖) |
| **文件大小** | ~10 行 | ~82 行 |

**设计意图**: `NeutralGatewayBusinessPolicy` 在通用实现和项目特化之间插入一个中性层。它当前不添加任何方法，但为未来新增项目（如 AEdu 独立适配器、第三方消费者）提供了清晰的继承锚点。`workbot_policy.py` 通过 `from .neutral_policy import NeutralGatewayBusinessPolicy` 建立继承链，同时兼容 script-mode fallback。

### 1.3 `__init__.py`

当前为空文件 (0 行)。未导出任何公共 API。这意味着外部模块需直接引用子模块路径（如 `from .workbot_policy import WorkbotGatewayBusinessPolicy`）。

---

## 2. Policy Pack 内容

### 2.1 ADAPTER_POLICIES (硬编码覆盖)

文件: [workbot_policy.py](/Users/busiji/memory/workspace/tools/memory_hook_adapters/workbot_policy.py:18-21)

```python
ADAPTER_POLICIES: dict[str, str] = {
    "legality_source": "active-legal-map-only",
    "registration_commit": "required-after-absorption-complete",
}
```

| 策略键 | 值 | 含义 |
|---|---|---|
| `legality_source` | `active-legal-map-only` | 合法性来源仅以 active legal map 为准，不参考其他来源（如历史快照、缓存、推断） |
| `registration_commit` | `required-after-absorption-complete` | 吸收流程完成后必须执行 git 注册提交，不允许跳过 |

### 2.2 Policy Pack 解析路径优先级

在 `WorkbotGatewayBusinessPolicy.__init__` 中（L27-41），policy-pack 路径按以下优先级解析：

1. **构造函数参数** `policy_pack_path`（显式传入）
2. **环境变量** `MEMORY_HOOK_POLICY_PACK_PATH`
3. **默认路径** `workspace/memory/kb/global/memory-hook-policy-pack.json`（如果文件存在）
4. `None`（跳过 pack 加载）

### 2.3 策略合并逻辑

`inject_policy_pack_config()`（L54-75）的合并行为：

```
JSON pack policies  →  merged_policies  ←  ADAPTER_POLICIES (覆盖同名键)
```

**代码级策略优先级 > 文件级策略**。这保证了 workbot 的核心策略不会被外部 policy-pack 文件篡改。

`resolve_policies()`（L77-82）则从 `PolicyRegistryImpl.DEFAULT_POLICIES` 获取基线，再用 `ADAPTER_POLICIES` 覆盖，返回最终策略 dict。

---

## 3. Runtime Profile 配置

文件: [workbot_runtime_profile.py](/Users/busiji/memory/workspace/tools/memory_hook_adapters/workbot_runtime_profile.py)

`build_workbot_runtime_profile(repo_root, workspace_root)` 返回一个包含 **~50 个键**的扁平 dict，注入到 gateway 的全局命名空间。按类别分组：

### 3.1 路径配置

| 类别 | 键 | 说明 |
|---|---|---|
| 核心路径 | `PROJECT_MAP_ROOT`, `TRUTH_MODEL`, `PROJECT_MAP_GOVERNANCE` | project-map 体系 |
| 契约路径 | `HOOK_CONTRACT_PATH`, `GLOBAL_RULE_PATH`, `MEMORY_SYSTEM_PATH`, `POLICY_PACK_PATH` | 系统契约与规则 |
| 规范文件 | `REQUIRED_CANONICAL` (12 个), `GLOBAL_CANONICAL` (5 个) | 启动前必须存在的文件 |
| 项目映射 | `PROJECT_CANONICAL`, `PROJECT_RUNTIME_ROOT`, `PROJECT_DOC_REFS`, `PROJECT_DECISION_REFS`, `PROJECT_LESSON_REFS` | 按项目名分组的引用 |

### 3.2 策略与范围

| 类别 | 键 | 说明 |
|---|---|---|
| 策略值 | `LEGALITY_SOURCE_POLICY`, `REGISTRATION_COMMIT_POLICY`, `REGISTRATION_COMMIT_PHASE` | 核心业务策略 |
| 范围控制 | `REQUIRED_REGISTRY_SCOPES` (8 个 glob), `POLICY_ALLOWED_SCOPES` (3 个项目) | 注册与作用域边界 |
| 阻断范围 | `GOVERNANCE_BLOCKER_SCOPES` (`{"AEdu"}`), `EVENT_CONTRACT_BLOCKER_SCOPES` (`{"AEdu"}`) | AEdu 特有的阻断范围 |
| 继承关系 | `POLICY_SCOPE_INHERITS` (`AEdu` → `workbot`, `platform-capabilities` → `workbot`) | 子项目策略继承 |
| 路由 | `DEFAULT_PROJECT_SCOPE` (`"workbot"`), `ROUTE_PROJECT_RUNTIME_SCOPE` (`"AEdu"`) | 默认/路由项目 |
| 匹配提示 | `SCOPE_MATCH_HINTS` | AEdu 和 platform-capabilities 的目录提示 |

### 3.3 AEdu 专用配置

| 类别 | 键 | 说明 |
|---|---|---|
| 治理冻结 | `GOVERNANCE_FROZEN_TUPLE_FILES` (4 个 AEdu 文件) | AEdu 的治理评审单 |
| 事件契约 | `EVENT_CONTRACT_FILES` (5 个 AEdu 文件) | 上游/下游事件映射 |
| 冻结元组 | `FROZEN_TUPLE_EXPECTED`, `FROZEN_TUPLE_LEGACY_MARKERS` | 期望值与遗留标记 |
| 事件定义 | `FORMAL_SOURCE_TYPES`, `FORMAL_EVENT_TYPES`, `FORMAL_EVENT_STATUSES`, `FORMAL_FIELD_KEYS` | AEdu 事件模型 |
| 遗留字段 | `LEGACY_FIELD_KEYS` | 旧版字段键兼容 |

### 3.4 其他配置

| 类别 | 键 | 说明 |
|---|---|---|
| 证据引用 | `LOWER_EVIDENCE_ROOTS` (6 个根目录), `CORE_EVIDENCE_REFS` (3 个路径字符串), `AUTHORITY_ALLOWED_PATHS` (2 个路径) | 证据链 |
| 经验教训 | `DEFAULT_LESSON_REFS` (1 个), `PROJECT_LESSON_REFS` (workbot 1 个) | 学习记录索引 |
| 压缩策略 | `ARTIFACT_COMPACTION` (6 个 bool 键) | 上下文压缩开关 |
| CMUX 集成 | `CLAUDE_HOOK_STATE_FILE` (来自环境变量) | Claude 代理状态文件 |
| Git 注册 | `REGISTRATION_GIT_SCOPE` (7 个文件), `LEGAL_CORE_MARKERS` (4 个标记) | 注册提交范围 |

### 3.5 类对象引用

`GATEWAY_POLICY_CLASS` 直接指向 `WorkbotGatewayBusinessPolicy` 类对象（非字符串），在 gateway 中通过 `globals().get("GATEWAY_POLICY_CLASS", WorkbotGatewayBusinessPolicy)` 获取并实例化。

---

## 4. 扩展性评估

### 4.1 添加新项目适配器需要做什么

**必须步骤**:

1. **创建 `newproject_runtime_profile.py`**: 实现 `build_newproject_runtime_profile(repo_root, workspace_root) -> dict[str, Any]`，返回包含所有 gateway 期望键的 dict
2. **创建 `newproject_policy.py`** (可选): 继承 `NeutralGatewayBusinessPolicy`，定义 `ADAPTER_POLICIES` 和覆盖方法
3. **在 `memory_hook_gateway.py` 注册**: 在 `_ADAPTER_REGISTRY` 中添加条目 `{"newproject": (".memory_hook_adapters.newproject_runtime_profile", "build_newproject_runtime_profile")}`
4. **激活**: `MEMORY_HOOK_ADAPTER=newproject` 调用 gateway

### 4.2 扩展性评级: **中等偏高**

| 维度 | 评级 | 说明 |
|---|---|---|
| **注册机制** | 良好 | `_ADAPTER_REGISTRY` 字典 + 环境变量选择，扩展只需加一行 |
| **函数签名约束** | 明确 | `fn(repo_root: Path, workspace_root: Path) -> dict` |
| **Profile dict 键** | 较重 | ~50 个键必须提供，但很多是项目无关的（如 AEdu 专用配置），新适配器需复制大量样板 |
| **继承链** | 清晰 | 三层继承 (Impl → Neutral → Project) 职责分明 |
| **动态注入** | 有风险 | `globals().update()` 直接污染模块命名空间，调试困难 |
| **Policy 类绑定** | 灵活 | 通过 dict 中传递类对象，非硬编码 |

**主要痛点**: profile dict 键数量大且部分键是特定于 AEdu/workbot 的。新项目适配器如果不需要 AEdu 的事件契约，仍需决定是传递空集合还是省略键——省略可能导致 gateway KeyError。

---

## 5. 与 core/gateway 的集成点

### 5.1 Gateway 发现与加载

文件: [memory_hook_gateway.py](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py)

```python
# L80-83: 环境变量 + 注册表
_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "workbot")
_ADAPTER_REGISTRY = {
    "workbot": (".memory_hook_adapters.workbot_runtime_profile", "build_workbot_runtime_profile"),
}

# L86-91: 动态导入 + 全局注入
_mod_path, _fn_name = _ADAPTER_REGISTRY[_ADAPTER_NAME]
_mod = importlib.import_module(_mod_path, package="workspace.tools")
_fn = getattr(_mod, _fn_name)
globals().update(_fn(REPO_ROOT, WORKSPACE_ROOT))  # 所有键成为模块级全局变量

# L158: Policy 类引用
_policy_class = globals().get("GATEWAY_POLICY_CLASS", WorkbotGatewayBusinessPolicy)
```

### 5.2 集成流程图

```
┌─────────────────────────────────────────────────┐
│  memory_hook_gateway.py                         │
│                                                  │
│  1. 读取 MEMORY_HOOK_ADAPTER 环境变量            │
│  2. 查 _ADAPTER_REGISTRY 获取 (module, func)     │
│  3. importlib.import_module → 加载 profile 模块  │
│  4. globals().update(build_xxx_profile(...))     │
│     ↓ 注入 ~50 个全局变量                         │
│  5. 通过 GATEWAY_POLICY_CLASS 获取策略类         │
│  6. 实例化策略类 → 驱动业务决策                  │
│     ↓                                            │
│     NeutralGatewayBusinessPolicy                 │
│       ↓                                          │
│     WorkbotGatewayBusinessPolicy                 │
│       - resolve_policies()                       │
│       - inject_policy_pack_config()              │
└─────────────────────────────────────────────────┘
```

### 5.3 关键集成点

| 位置 | 集成点 | 说明 |
|---|---|---|
| `gateway.py:91` | `globals().update(...)` | profile dict 注入，所有键成为全局变量 |
| `gateway.py:158` | `GATEWAY_POLICY_CLASS` | 策略类动态引用 |
| `workbot_policy.py:12` | `from .neutral_policy import ...` | workbot 继承 neutral，建立策略链 |
| `workbot_policy.py:77-82` | `resolve_policies()` | 合并基线 + adapter 覆盖，供 gateway 调用 |
| `workbot_runtime_profile.py:201` | `"GATEWAY_POLICY_CLASS": WorkbotGatewayBusinessPolicy` | profile dict 中传递类对象 |

---

## 6. 改进建议

### 6.1 引入 Profile 基类或 Protocol

**问题**: 当前 `build_workbot_runtime_profile` 返回的 dict 有 ~50 个键，没有类型约束。新项目适配器容易遗漏键导致 gateway 运行时 KeyError。

**建议**: 定义一个 `RuntimeProfile` TypedDict 或 dataclass，声明所有必需键及其类型。让 profile 构建函数返回该类型实例，在构建时或 gateway 注入时做完整性校验。

### 6.2 分离项目无关键与项目专属键

**问题**: profile dict 混合了 gateway 核心需要的键（如 `PROJECT_MAP_ROOT`、`HOOK_CONTRACT_PATH`）和项目专属的键（如 `GOVERNANCE_FROZEN_TUPLE_FILES`、`EVENT_CONTRACT_FILES`）。新适配器需要决定是复制所有 AEdu 配置还是省略。

**建议**: 将 profile dict 拆分为两层：
- `core_keys`: 所有适配器必须提供（~15-20 个）
- `project_keys`: 按需覆盖，缺失时使用 neutral 默认值

在 gateway 中先注入 core_keys，再合并 project_keys（带 fallback）。

### 6.3 替换 `globals().update()` 为显式命名空间

**问题**: `globals().update()` 直接污染模块全局命名空间，调试时难以追踪变量来源，也与静态分析工具不兼容。

**建议**: 使用一个 `AdapterContext` 对象（或命名空间 dict）替代全局注入，所有代码通过 `ctx.PROJECT_MAP_ROOT` 而非裸 `PROJECT_MAP_ROOT` 访问。这需要重构 gateway 中的引用方式，但显著提升可维护性。

### 6.4 填充 `__init__.py` 导出公共 API

**问题**: `__init__.py` 为空，外部无法通过 `from workspace.tools.memory_hook_adapters import WorkbotGatewayBusinessPolicy` 导入，只能写完整子模块路径。

**建议**: 在 `__init__.py` 中导出核心类型：
```python
from .neutral_policy import NeutralGatewayBusinessPolicy
from .workbot_policy import WorkbotGatewayBusinessPolicy, ADAPTER_POLICIES
from .workbot_runtime_profile import build_workbot_runtime_profile
```

### 6.5 ADAPTER_POLICIES 考虑从配置而非硬编码读取

**问题**: `ADAPTER_POLICIES` 是模块级硬编码 dict，修改需要改代码。虽然 policy-pack 机制提供了文件级覆盖，但 adapter 优先级始终高于文件。

**建议**: 保留硬编码作为最后防线，但增加一个中间层（如项目配置 YAML/JSON），让策略可以从文件读取、环境变量覆盖、代码硬编码回退的三层优先级。或者至少将 `ADAPTER_POLICIES` 移出模块级别，放在 `__init__.py` 或独立配置文件中，减少 policy 代码文件的耦合。
