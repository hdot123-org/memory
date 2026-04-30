---
type: "[DOC:DESIGN]"
title: "Policy Pack 与治理"
shortname: DES-007
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [policy,governance,rules]
related: [DES-006, DES-008, DES-010]
---

> 文档编号：DES-007 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# 07-policy-governance

> Policy Pack 与治理机制设计文档。
> 范围：memory 模块 / workbot adapter 级别。
> 生成日期：2026-04-26。

---

## 1. memory-hook-policy-pack.json 完整结构

全局默认策略包位于 `memory-hook-policy-pack.json`（`memory_core/memory/kb/global/memory-hook-policy-pack.json`），workbot 专用策略包位于 `workbot-policy-pack.json`（`memory_core/memory/kb/global/workbot-policy-pack.json`）。两者结构相同，仅 `scope` 字段不同。

```json
{
  "schema_version": "m3-policy-pack-v1",
  "scope": "default" | "workbot",
  "policies": {
    "legality_source": "active-legal-map-only",
    "registration_commit": "required-after-absorption-complete",
    "registration_phase": "declared-not-enforced",
    "truth_basis_policy": "source-authority-evidence-conflict",
    "kb_write_mode": "read-first-CRUD",
    "kb_overwrite_allowed": "false"
  },
  "conflict_strategies": {
    "legality_source": "fail-fast",
    "registration_commit": "preserve-and-escalate",
    "registration_phase": "prefer-strict",
    "truth_basis_policy": "prefer-strict",
    "kb_write_mode": "prefer-strict",
    "kb_overwrite_allowed": "prefer-strict",
    "default": "preserve-and-escalate"
  },
  "adapter_scope": true
}
```

**字段说明：**

| 顶层键 | 类型 | 含义 |
|--------|------|------|
| `schema_version` | `str` | 策略包 schema 版本，当前固定为 `m3-policy-pack-v1` |
| `scope` | `str` | 策略包作用域，`default` 为模块默认，`workbot` 为 workbot adapter 专用 |
| `policies` | `dict[str, str]` | 6 个策略键值对 |
| `conflict_strategies` | `dict[str, str]` | 各策略键的冲突解决策略，`default` 为兜底策略 |
| `adapter_scope` | `bool` | 标记该策略包由 adapter 注入（当前固定为 `true`） |

**6 个策略键：**

| 策略键 | 值 | 含义 |
|--------|-----|------|
| `legality_source` | `active-legal-map-only` | 只承认 `active-legal` 地图条目为合法目录来源 |
| `registration_commit` | `required-after-absorption-complete` | 吸收完成后必须附带 git 提交 |
| `registration_phase` | `declared-not-enforced` | 当前为声明阶段，未强制执行 |
| `truth_basis_policy` | `source-authority-evidence-conflict` | 正式真相必须同时具备 source/authority/evidence refs 且冲突已裁决 |
| `kb_write_mode` | `read-first-CRUD` | KB 写入必须先读取再判断操作类型 |
| `kb_overwrite_allowed` | `false` | 禁止覆盖现有 KB 内容 |

**3 种冲突解决策略：**

| 策略名 | 行为 |
|--------|------|
| `fail-fast` | 遇到冲突立即失败，抛出 `ValueError` |
| `preserve-and-escalate` | 保留第一值，标记为升级到人工裁决 |
| `prefer-strict` | 选择更严格的值（如 `kb_overwrite_allowed` 选 `false`，`registration_phase` 选 `declared-not-enforced`） |

冲突解决逻辑实现在 `PolicyRegistryImpl.resolve_conflict()`（`memory_core/tools/memory_hook_impls.py` 约 L325-358）。

---

## 2. workbot-policy-pack.md scope 标记

`workbot-policy-pack.md`（`memory_core/memory/kb/global/workbot-policy-pack.md`）是 workbot adapter 级别的策略包规范文档。

**关键 scope 标记：**

- 文件头声明 `Scope: adapter`，表示这是 adapter 级别策略，不是模块默认
- 开篇声明："本文件是 workbot adapter 级别的策略包规范，不是模块默认策略。其他 adapter 可以定义自己的策略包，不受本文件约束"
- schema 版本标记为 `M3-policy-pack-v1`
- 状态标记为 `in-progress (M3 wiring in progress)`

**注入链路：**

```
workbot_runtime_profile.build_workbot_runtime_profile()
  → globals().update() 注入 POLICY_PACK_PATH 常量
    → _build_gateway_business_policy() 传入 GatewayBusinessPolicyConfig(policy_pack_path=...)
      → PolicyRegistryImpl.__init__(config=config) 解析 config.policy_pack_path
```

优先级链：config 参数 > 环境变量 `MEMORY_HOOK_POLICY_PACK_PATH` > 默认文件路径 > 空回退。

---

## 3. workbot-project-map-governance.md 治理规则

`workbot-project-map-governance.md`（`memory_core/memory/kb/global/workbot-project-map-governance.md`）定义 workbot adapter 级别的项目地图治理规则。

**Scope 标记：** `rule-only, records-cleared`，`Scope: adapter`

**5 条核心治理规则：**

1. Rule files can define policy — 规则文件可以定义策略
2. Historical materials cannot define policy — 历史材料不能定义策略
3. 冲突资料若未经过唯一真相系统清洗，不得作为正式真相来源
4. 只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性
5. 未完成同次 `git commit` 的目录登记，不得视为生效

这些规则在 hook contract 的 truth-basis gate 和 registration commit gate 中被执行。

---

## 4. workbot-hook-contract.md hook 契约

`workbot-hook-contract.md`（`memory_core/memory/kb/global/workbot-hook-contract.md`）定义 Codex 与 Claude 通过 workbot adapter 进入总记忆系统时的 hook 合同。

**元数据：**

| 字段 | 值 |
|------|-----|
| `type` | `KB:GLOBAL` |
| `shortname` | `WB-HOOK` |
| `status` | `active` |
| `scope` | `adapter` |
| `created` | `2026-04-11` |
| `updated` | `2026-04-26` |

**5 个 Gateway Phases（§2）：**

1. **preflight** — 识别宿主、仓库根目录、工作区、事件类型、项目范围；不合法时 fail-fast
2. **context-resolve** — 读取 canonical，只承认 `active-legal` 地图条目；检查 truth basis 完整性
3. **context-package** — 组装统一结构，不允许宿主各自定义读取顺序
4. **write-route** — 判定写入层级（`log/kb/docs/projects/artifacts/system/archive`），不允许绕过路由
5. **post-write-sync** — 更新健康状态、兼容索引、追踪记录；登记迁移必须附带同次 `git commit`

**Truth Basis Gate（§2.4.1）：**

进入正式 canonical 的对象必须同时具备：
- `source_refs` — 不能全部退化为 canonical 自指
- `authority_refs` — 只能指向 formal canonical 或 legal core
- `evidence_refs` — 必须包含至少一条 lower-layer support
- `conflict_status = resolved`

**Shared Contract Surface（§3）：**

统一合同必须回答 8 个问题：当前宿主、当前项目域、允许读取的 canonical、允许引用的资料层文档、允许写入的层级、错误落点、正式真相的 truth basis、对象是否达到正式真相标准。

**Gateway Invariants（§8）：**

- `MEMORY_HOOK_ADAPTER` 环境变量控制 adapter 选择（默认 `workbot`）
- `MEMORY_HOOK_FORCE` 控制强制 hook，`WORKBOT_FORCE_HOOK` 为向后兼容 fallback

---

## 5. POLICY_ALLOWED_SCOPES、POLICY_SCOPE_INHERITS 代码使用

这两个常量定义在 `workbot_runtime_profile.py`（`memory_core/tools/memory_hook_adapters/workbot_runtime_profile.py` L251-260）的 `build_workbot_runtime_profile()` 返回值中：

```python
"POLICY_ALLOWED_SCOPES": {"workbot", "AEdu", "platform-capabilities"},
"POLICY_SCOPE_INHERITS": {
    "AEdu": "workbot",
    "platform-capabilities": "workbot",
},
```

**注入机制：** gateway 通过 `globals().update(_fn(REPO_ROOT, WORKSPACE_ROOT))`（`memory_hook_gateway.py` L91）将 runtime profile 的所有键注入为 gateway 全局变量。

**使用位置：** `_get_policy_registry()`（`memory_hook_gateway.py` L175-184）创建 `PolicyRegistryImpl` 时传入：

```python
_default_policy_registry = PolicyRegistryImpl(
    policy_pack_path=POLICY_PACK_PATH,
    allowed_scopes=set(POLICY_ALLOWED_SCOPES),
    scope_inherits=dict(POLICY_SCOPE_INHERITS),
)
```

**继承语义：** AEdu 和 platform-capabilities 继承 workbot 的所有策略，子 scope 可覆盖特定策略值，但冲突策略定义不隐式继承（`workbot-policy-pack.md` §4）。

---

## 6. registration_commit phase 升级路径

`registration_commit` 策略控制目录登记后是否要求附带 git 提交。当前状态为 `declared-not-enforced`（声明但未强制执行）。

**常量定义：** `workbot_runtime_profile.py` L203-204

```python
"REGISTRATION_COMMIT_POLICY": "required-after-absorption-complete",
"REGISTRATION_COMMIT_PHASE": "declared-not-enforced",
```

**Phase 解析：** `registration_phase_from_policy_pack()`（`memory_hook_core.py` L14-27）从 policy pack 中提取 `registration_phase`，缺失或格式错误时回退到 `declared-not-enforced`。

**Gate 评估：** `evaluate_registration_commit_gate()`（`memory_hook_core.py` L30-66）逻辑：

- phase 不是 `enforced` → 保持 M3 语义（不硬阻断）
- phase 是 `enforced` 且事件匹配 gate_event → 要求 `status == committed-coupled`

**升级路径：**

1. 当前：`declared-not-enforced` — 登记不要求 git commit，不阻断
2. 升级：将 `REGISTRATION_COMMIT_PHASE` 改为 `enforced` → 登记必须附带同次 git commit，否则 gate 失败
3. 冲突策略 `preserve-and-escalate`（`memory_hook_impls.py` L209）确保冲突时保留第一值并升级

**在 context package 中的输出（`memory_hook_core.py` L230-233）：**

```python
"registration_commit_policy": registration_commit_policy,
"registration_commit_gate": registration_commit_gate,
"registration_commit_enforced": registration_commit_gate.get("enforced", False),
"registration_commit_enforcement_result": registration_commit_gate.get("enforcement_result", "not-enforced"),
```

---

## 7. frozen tuple 校验设计

Frozen tuple 是 AEdu 项目专用的治理校验机制，确保关键治理文件中包含一组不可变的"冻结元组"标记。

**配置定义：** `workbot_runtime_profile.py` L112-131

```python
governance_frozen_tuple_files = [
    aedu_root / "00_导航与管理" / "KB+INGEST 模块级开发准入评审单.md",
    aedu_root / "00_导航与管理" / "SIM模块级开发准入评审单.md",
    aedu_root / "12_实施与试点运营" / "09_KB+INGEST 试点范围与责任边界.md",
    aedu_root / "scripts" / "validate_kb_closure.py",
]
frozen_tuple_expected = {
    "province=安徽",
    "region_id=CN_AH",
    "rule_package=AH_RULE_V1",
    "kb_version_prefix=KB_CN_AH_",
}
frozen_tuple_legacy_markers = {
    "CN_GD_SZ",
    "KB_CN_GD_SZ",
}
```

**阻塞 scope：** `GOVERNANCE_BLOCKER_SCOPES = {"AEdu"}`（`workbot_runtime_profile.py` L228），仅 AEdu 项目触发 frozen tuple 校验。

**校验逻辑：** `governance_frozen_tuple_blocker_errors()`（`memory_hook_impls.py` L913-936）执行三步检查：

1. **文件存在性** — 所有 `governance_frozen_tuple_files` 必须存在，缺失则返回 `missing governance files: ...`
2. **期望标记检查** — 所有文件合并文本中必须包含每个 `frozen_tuple_expected` 标记，缺失则返回 `missing expected tuple markers: ...`
3. **遗留标记检查** — 所有文件中不得出现 `frozen_tuple_legacy_markers`（如 `CN_GD_SZ`、`KB_CN_GD_SZ`），出现则返回 `legacy frozen tuple markers still present: ...`

**配置不可变性：** `GatewayBusinessPolicyConfig` 使用 `@dataclass(frozen=True)`（`memory_hook_impls.py` L425），确保配置 payload 不可变。

**在 context package 中的输出（`memory_hook_core.py` L239-240）：**

```python
"governance_frozen_tuple_validation": "pass" if not governance_tuple_errors else "fail",
"governance_frozen_tuple_errors": governance_tuple_errors,
```

**接口契约：** `GatewayBusinessPolicy.governance_frozen_tuple_blocker_errors()`（`memory_hook_interfaces.py` L184-185）定义返回 `list[str]` 的抽象方法。
