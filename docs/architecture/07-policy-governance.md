---
type: "[DOC:DESIGN]"
title: "Policy Pack 与治理"
shortname: DES-007
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [policy,governance,rules]
related: [DES-006, DES-008, DES-010]
---

> 文档编号：DES-007 | 版本：V1.1 | 日期：2026-09-05 | 状态：可评审 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码。

# 07-policy-governance

> Policy Pack 与治理机制设计文档。
> 范围：策略注册表 / 治理文档 / 所有权模型三层治理面（v0.45.6）。
> 首次生成：2026-04-26 | 最近校准：2026-09-05。

> **📌 2026-09-05 校准备注**
>
> 1. **policy-pack JSON 治理面已退役**：`memory/kb/global/` 下现存 8 个文件全部为 Markdown（hook-contract、INDEX、kb-format-spec、memory-routing、memory-system、orchestrator-security-standard、project-map-governance、truth-model），不再存在任何 `*-policy-pack.json`（实测 `ls`）。workbot-policy-pack 系列随 workbot 适配器删除。
> 2. **PolicyRegistryImpl 保留"可选动态覆盖"能力**（`memory_hook_impls.py:227`）：policy-pack 文件存在才加载（`_load_dynamic_policy_pack`，L289），缺失回退内置 `DEFAULT_POLICIES`（现为 4 键，L238-243）。
> 3. **策略键迁移**：`legality_source` / `registration_commit` 两键从 policy-pack JSON 迁移到消费项目 `adapter.toml [policy]` 段（默认 map-only / same-commit / post）。
> 4. **治理面主体易位**：当前治理主力是 `ownership.toml` 域表 + `ownership_cli`（show / validate / plan-update / apply-update / source-repo-mode / dev / prod，733 行）+ PreToolUse 守卫（fail-closed）。
> 5. **三层架构路由治理**（v0.8.0+）：`adapter.toml [global_kb]` 段启用项目优先 / 全局兜底（Layer 3 `memory/` → Layer 2 `~/.memory/global-kb/`）。
> 6. **引擎类执行体已迁 infra-core**（2026-08 M3/M5）：version-sync / daily-audit / error-patterns / scanner / heartbeat / layout-audit 等在 `hdot123-org/infra-core`，本仓仅保留协议面与 thin caller（见 `docs/specs/M5-SHRINK-DISPOSITION.md`）。

---

## 1. 策略注册表现状（原 policy-pack JSON 体系）

### 1.1 已移除的治理面

以下 workbot 时代的 JSON 治理面已移除，**不再是治理入口**：

- `memory/kb/global/memory-hook-policy-pack.json`（全局默认策略包）
- `workbot-policy-pack.json` 及 `memory-hook-policy-pack.md` / `workbot-policy-pack.md` 规范文档（scope: adapter 标记体系随之消亡）

### 1.2 保留的运行时机制：PolicyRegistryImpl

策略注册表 `PolicyRegistryImpl`（`memory_hook_impls.py:227`）仍在运行，但定位从"治理面"降级为"可选动态覆盖机制"：

```python
class PolicyRegistryImpl(PolicyRegistry):          # memory_hook_impls.py:227
    SCHEMA_VERSION = "m3-policy-pack-v1"           # L230
    POLICY_PACK_PATH_ENV = "MEMORY_HOOK_POLICY_PACK_PATH"  # L231
    DEFAULT_POLICY_PACK_PATH = (
        Path(__file__).resolve().parents[1] / "memory" / "kb" / "global" / "memory-hook-policy-pack.json"
    )                                              # L232-234（该路径当前不存在）
```

**内置默认策略（4 键，L238-243）**——注释明确其为 "Repository-agnostic fallback policies"，项目专属策略应经 gateway/runtime profile 注入：

| 策略键 | 值 | 含义 |
|--------|-----|------|
| `registration_phase` | `declared-not-enforced` | 目录登记的 git-commit gate 处于声明不强制阶段 |
| `truth_basis_policy` | `source-authority-evidence-conflict` | 正式真相必须同时具备 source/authority/evidence refs 且冲突已裁决 |
| `kb_write_mode` | `read-first-CRUD` | KB 写入必须先读取再判断操作类型 |
| `kb_overwrite_allowed` | `false` | 禁止覆盖现有 KB 内容 |

> 与 2026-05 版的 6 键相比，`legality_source` 与 `registration_commit` 两键移出默认表，改由 `adapter.toml [policy]` 段承载（见 DES-006 §2.2）。

**冲突解决策略（7 键，L246-254）**：`legality_source: fail-fast`、`registration_commit: preserve-and-escalate`、`registration_phase` / `truth_basis_policy` / `kb_write_mode` / `kb_overwrite_allowed`: `prefer-strict`、`default: preserve-and-escalate`。三策略语义不变：

| 策略名 | 行为 |
|--------|------|
| `fail-fast` | 遇到冲突立即失败，抛出 `ValueError` |
| `preserve-and-escalate` | 保留第一值，标记为升级到人工裁决 |
| `prefer-strict` | 选择更严格的值（`kb_overwrite_allowed` 选 `false`，`registration_phase` 选 `declared-not-enforced`） |

实现位于 `resolve_conflict()`（L351）。

**policy-pack 路径优先级链（L266-287）**：`config.policy_pack_path` > 构造参数 > 环境变量 `MEMORY_HOOK_POLICY_PACK_PATH` > `DEFAULT_POLICY_PACK_PATH`（存在才用）> `None`。文件存在时 `_load_dynamic_policy_pack()`（L289）合并其 `policies` / `conflict_strategies` / `schema_version` 字段（宽容解析：类型不符即跳过）。

**现行注入链路**：

```
memory-init 写 memory/system/adapter.toml
  → default_runtime_profile 装配 POLICY_PACK_PATH = memory/kb/global/policy-pack.json（可选文件）
    → _get_policy_registry()（_gateway_config.py:392-401）构造 PolicyRegistryImpl(policy_pack_path=...)
      → 文件存在则动态覆盖，缺失则 DEFAULT_POLICIES 生效
```

`get_policy_pack(scope)`（L331）输出的 pack dict 含 `schema_version` / `scope` / `policies` / `conflict_strategies` / `default_strategy`，以及 `inherits`（当 scope 命中 `scope_inherits` 时）。

---

## 2. 治理文档现状（memory/kb/global/）

workbot 时代的 `Scope: adapter` 标记体系已移除。当前 `memory/kb/global/` 的治理文档（均为项目层通用规范，无 adapter 专属文件）：

| 文件 | 职责 |
|------|------|
| `truth-model.md` | 真相模型（truth basis 四要素） |
| `memory-system.md` | 记忆系统全景 |
| `memory-routing.md` | 三层路由规则（读取链、Layer 2/3 fallback、scope resolution、diversity 约束） |
| `hook-contract.md` | hook 契约（见 §4） |
| `project-map-governance.md` | 项目地图治理（见 §3） |
| `kb-format-spec.md` | KB 文件格式规范 |
| `orchestrator-security-standard.md` | 编排器安全标准 |
| `INDEX.md` | 索引 |

消费项目的对应文档由 `memory-init` 从模板生成，属 Layer 3 项目层。

---

## 3. project-map-governance.md 治理规则

现行 `memory/kb/global/project-map-governance.md` 定义 project-map 子系统的治理规则。

**project-map 结构（4 文件）**：`INDEX.md`（唯一合法入口）、`legal-core-map.md`（active-legal 条目清单）、`ingestion-registry-map.md`（incoming-raw / compatibility-only 分类）、`governance.md`（治理规则声明）。

**校验体系**（执行体在 `business_policy_checks.py`，706 行）：

- `ProjectMapValidator`（L138）对 4 个 project-map 文件执行 14 条标记检查（INDEX 4 条、legal-core-map 3 条、ingestion-registry-map 4 条、governance 3 条）；
- `validate_unique_legal_system_contract()`（L206）另执行 12 条跨文件契约检查（workspace INDEX / overview / docs INDEX / global INDEX 对 project-map 的引用一致性、hook contract 双标记等）。

**3 个强制治理标记**（必须出现在 project-map-governance.md 中，供校验器识别）：

1. 未经过唯一真相系统清洗
2. 只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。
3. 未完成同次 `git commit` 的目录登记，不得视为生效。

---

## 4. hook-contract.md hook 契约

现行 `memory/kb/global/hook-contract.md`（原 `workbot-hook-contract.md` 已删除）定义 hook 生命周期规则：

**2 个关键事件**：`session-start`（构建初始 context package）与 `prompt-submit`（更新 context package），均经 `memory_hook_gateway` 的 `build_context_package` 系列函数处理。

**合法上下文来源**：gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录；未完成提交的登记不生效。

**契约双标记**（缺任一导致 `validate_unique_legal_system_contract()` 校验失败）：

- `MKR_HOOK_MAP_ONLY_CONTEXT` — 声明 map-only 合法上下文来源
- `MKR_HOOK_REGISTRATION_GATE` — 声明注册 git-commit gate

**context package 必需键**：`status` / `host` / `event` / `schema_version` / `system_context`（含 `boot_entry`、`state_entry`）/ `task_context`（含 `session_id`、`event`）。

**现行 gateway 主流程**（`_gateway_handlers.py:main`，L359 起）：source repo readonly 检查 → denylist 检查 → 外部上下文 noop → PreToolUse 守卫 → session-start 侧效应（健康检查/遥测/版本跟随）→ 非注入事件快速路径 → 注入事件全量 `build_context_package` → artifact 写入 + 完整性签名/校验。

> 旧版文档记录的 `MEMORY_HOOK_ADAPTER` 默认 `workbot`、`WORKBOT_FORCE_HOOK` 等 gateway invariants 已失效：默认适配器现为 `default`（`_gateway_config.py:262`），force 开关为 `MEMORY_HOOK_FORCE` / `WORKBOT_FORCE_HOOK` 双通道（`_gateway_config.py:88`）。

---

## 5. POLICY_ALLOWED_SCOPES、POLICY_SCOPE_INHERITS 代码使用

这两个值由 `default_runtime_profile.py` 装配（L117-118），来源是 `adapter.toml [routing].project_scope`：

```python
policy_allowed_scopes: set[str] = {project_scope}   # 单元素集合
policy_scope_inherits: dict[str, str] = {}          # 无跨 scope 继承
```

workbot 时代的 `{"workbot", "AEdu", "platform-capabilities"}` 三 scope 白名单与 `AEdu → workbot` 继承链已随适配器删除。

**注入机制**：profile dict 载入 `_adapter_config`（不再 `globals().update()`，见 DES-006 §5）。

**使用位置**：`_get_policy_registry()`（`_gateway_config.py:392-401`）构造单例：

```python
_default_policy_registry = PolicyRegistryImpl(
    policy_pack_path=get_config("POLICY_PACK_PATH"),
    allowed_scopes=set(get_config("POLICY_ALLOWED_SCOPES")),
    scope_inherits=dict(get_config("POLICY_SCOPE_INHERITS")),
)
```

**继承语义**：`scope_inherits` 命中时 `get_policy_pack()` 输出附加 `inherits` 字段；子 scope 可覆盖特定策略值。默认适配器下该机制为空置状态。

---

## 6. registration_commit phase 升级路径

`registration_commit` 策略控制目录登记后是否要求附带 git 提交。现行值链：

**配置来源**：`adapter.toml [policy]` 三键（`adapter_toml_schema.py:103-105`）——`legality_source_policy="map-only"`、`registration_commit_policy="same-commit"`、`registration_commit_phase="post"`（均为默认值）。

**Phase 解析**：`registration_phase_from_policy_pack()`（`memory_hook_core.py:76-89`）从 policy pack payload 提取 `registration_phase`，缺失或类型不符回退 `declared-not-enforced`。

**Gate 评估**：`evaluate_registration_commit_gate()`（`memory_hook_core.py:92-129`）：

- phase 不是 `enforced` → 保持 M3 语义（不硬阻断，`enforcement_result="not-enforced"`）
- phase 是 `enforced` 且事件匹配 gate_event（默认 `stop`）→ 要求 `status == "committed-coupled"`，否则返回 `registration commit enforcement failed`

**Probe 探测**：`_git_registration_probe()`（`_gateway_policy.py:241-316`）用 `git status --short` / `git diff-tree` 判定登记状态（`pending-commit` / `committed-coupled` / `committed-not-proven` / `awaiting-registration-payload`）。

**在 context package 中的输出**（`memory_hook_core.py:288-291`）：

```python
"registration_commit_policy": registration_commit_policy,
"registration_commit_gate": registration_commit_gate,
"registration_commit_enforced": registration_commit_gate.get("enforced", False),
"registration_commit_enforcement_result": registration_commit_gate.get("enforcement_result", "not-enforced"),
```

**升级路径**：当前默认 `post`（声明不强制）→ 将 `adapter.toml [policy].registration_commit_phase` 改为 enforced 语义后，登记必须附带同次 git commit，否则 gate 失败。冲突策略 `preserve-and-escalate` 语义不变。

---

## 7. frozen tuple 校验设计

Frozen tuple 是 AEdu 项目时代专用的治理校验机制。**机制保留，默认空置**：

- 默认适配器将 `GOVERNANCE_FROZEN_TUPLE_FILES` / `FROZEN_TUPLE_EXPECTED` / `FROZEN_TUPLE_LEGACY_MARKERS` / `GOVERNANCE_BLOCKER_SCOPES` 全部置空（`default_runtime_profile.py:119-120, 177-180`）——配置面已从代码中清除，非 AEdu 项目零成本。
- 校验执行体为 `FrozenTupleChecker`（`business_policy_checks.py:245`），由 `GatewayBusinessPolicyImpl.governance_frozen_tuple_blocker_errors()`（`memory_hook_impls.py:620`）委托调用；接口契约 `GatewayBusinessPolicy.governance_frozen_tuple_blocker_errors()`（`memory_hook_interfaces.py:263`）保留。
- 三步检查语义不变：治理文件存在性 → 期望标记（如 `province=安徽` 族）齐全 → 遗留标记（如 `CN_GD_SZ`）不得出现。
- `GatewayBusinessPolicyConfig` 仍为 `@dataclass(frozen=True)`（`memory_hook_impls.py:541`），配置 payload 不可变。

---

## 8. 治理面现状：所有权模型与守卫（v0.45.6 主治理面）

policy-pack 退役后，项目治理的主力面如下。

### 8.1 ownership.toml 域表

域模型在 `memory_core/ownership.py`（785 行）：`ProtectionLevel` 三级（RECOMMENDED / STANDARD / CRITICAL）+ `OwnershipDomain`（目录域）+ `OwnershipResource`（文件资源，支持 glob）。

**默认 7 域**：`memory/docs`、`memory/kb`、`memory/system`、`memory/project-map`、`audit`、`review`（均 CRITICAL）、`memory/log`（STANDARD）。
**默认 12 资源**：AGENTS.md、audit/SUMMARY.md、README.md、CHANGELOG.md、CONTRIBUTING.md、memory.lock、adapter.toml、ownership.toml、migrations.log、manifest.json、`memory/log/*-errors.jsonl` 等。

- `classify_owned_path()`：路径分类（资源优先、域递归匹配），绝对路径经单一函数 `_normalize_to_project_relative` 归一化，防绕过。
- `validate_ownership_schema()`：防弱化校验（删默认域/资源、降级保护级别、CRITICAL 域改非递归均报错）。
- `load_memory_ownership()`：读 `memory/system/ownership.toml`，缺失回退默认表。
- 本仓实例：`memory/system/ownership.toml`（schema `memory-ownership-v1`，7 域 + 12 资源 + `[policy.source_repo] mode="develop"`，2026-09-05 经 CLI 激活）。

### 8.2 ownership_cli（733 行）

```bash
python -m memory_core.tools.ownership_cli show         --project-root /path [--json]
python -m memory_core.tools.ownership_cli validate     --project-root /path [--json]
python -m memory_core.tools.ownership_cli plan-update  --project-root /path [--json]
python -m memory_core.tools.ownership_cli apply-update --project-root /path --yes
python -m memory_core.tools.ownership_cli source-repo-mode [--project-root /path] [readonly|develop]
python -m memory_core.tools.ownership_cli dev          --project-root /path   # develop 别名
python -m memory_core.tools.ownership_cli prod         --project-root /path   # readonly 别名
```

`apply-update` 前置 `validate_ownership_schema` 校验，非交互执行需 `--yes`。

### 8.3 source repo readonly / develop 模式

memory-core 源码仓（`is_memory_core_source_repo()`，`ownership.py:690`，按 `memory_core/tools/memory_hook_gateway.py` 等 marker 文件判定）默认 readonly：

- 模式存于 `ownership.toml [policy.source_repo].mode`（`get_source_repo_mode()`，`ownership.py:763`；非法值回退 readonly）；
- readonly 下 gateway 对所有事件输出只读 context package 后退出（`_handle_source_repo_check`，`_gateway_handlers.py:107-115`）；
- develop 模式（经 `source-repo-mode develop` / `dev` 切换）放行代码修改，但仍跳过消费者项目的校验面：context package 强制 `status="ok"`、清空 `validation_errors`，并打 `system_context["source_repo_skip_validation"]=True`（`_gateway_policy.py:383-389`）。

### 8.4 PreToolUse 守卫（fail-closed）

gateway 对 `pre-tool-use` 事件以 5 秒超时子进程运行 `python -m memory_core.tools.pretooluse_guard`（`_gateway_handlers.py:118-158`），拦截 `Write` / `Edit` / `MultiEdit` / `NotebookEdit` / `Execute`：

- 守卫按所有权表分类路径，输出双格式 JSON（旧版 `decision` + Factory 官方 `hookSpecificOutput.permissionDecision`），ALLOW exit 0 / BLOCK exit 2；
- **故障关闭**：守卫超时或崩溃时，gateway 回退 `is_protected_path_target()` 上下文检查——受保护路径（memory/kb、memory/system、memory/docs、memory/log）**一律拒绝**（exit 2），非保护路径放行并记错误日志。

### 8.5 三层架构路由治理（v0.8.0+）

- `adapter.toml [global_kb]` 段（`enabled` / `root`，默认 `~/.memory/global-kb`）启用项目优先 / 全局兜底：知识查找先命中项目 `memory/kb/`，领域条目缺失时 fallback 到 Layer 2 `~/.memory/global-kb/`（operations / engineering / collaboration / pending 四域）；
- `memory-init` 幂等创建全局 KB 并写入该段；`memory-migrate --from 0.7.0 --to 0.8.0` 向存量项目补注入；
- 路由规则文档化为 `memory-routing.md`（读取链、scope resolution、authority/source/evidence diversity 约束）；
- 沉淀流：session-end 自动捕获候选到 `pending/`，`memory-promote` 人工晋升到正式领域。

---

## 附：与 2026-05-14 版（V1.0）的结构对照

| V1.0 章节 | V1.1 处置 |
|---|---|
| §1 memory-hook-policy-pack.json 完整结构 | 治理面标已移除；运行时机制重写为 §1.2（DEFAULT_POLICIES 4 键） |
| §2 memory-hook-policy-pack.md scope 标记 | 标已移除，治理文档现状重写为 §2 |
| §3 workbot-project-map-governance.md | 重写为 §3（现行 project-map-governance.md，14+12 条校验） |
| §4 workbot-hook-contract.md | 重写为 §4（现行 hook-contract.md + gateway 主流程） |
| §5 POLICY_ALLOWED_SCOPES 代码使用 | 重写为 §5（单 scope，_adapter_config 注入） |
| §6 registration_commit phase 升级路径 | 保留，值源更新为 adapter.toml（§6） |
| §7 frozen tuple 校验设计 | 保留，标注默认空置（§7） |
| —（新增） | §8 所有权模型与守卫治理面 |
