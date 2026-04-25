# Workbot Policy Pack

> 本文件是 workbot adapter 级别的策略包规范，不是模块默认策略。
> 其他 adapter 可以定义自己的策略包，不受本文件约束。
>
> 本文件定义 `workbot` 记忆钩子系统的策略包（policy-pack）规范。  
版本：M3-policy-pack-v1
状态：active
Scope: adapter

---

## 1. Policy Pack Schema

```json
{
  "schema_version": "m3-policy-pack-v1",
  "scope": "workbot",
  "policies": {
    "<policy_key>": "<policy_value>"
  },
  "conflict_strategies": {
    "<policy_key>": "<strategy>",
    "default": "<strategy>"
  }
}
```

### 1.1 策略键命名规范

- 使用 `snake_case` 命名
- 按领域分组：`legality_*`, `registration_*`, `truth_*`, `kb_*`
- 所有策略键必须在 `conflict_strategies` 中有对应策略或回退到 `default`

---

## 2. 默认策略定义

### 2.1 合法性策略

| 策略键 | 默认值 | 说明 |
|--------|--------|------|
| `legality_source` | `active-legal-map-only` | 只承认 `active-legal` 地图条目为合法目录来源 |
| `registration_commit` | `required-after-absorption-complete` | 吸收完成后必须附带 git 提交 |
| `registration_phase` | `declared-not-enforced` | 当前为声明阶段，未强制执行 |

### 2.2 Truth Basis 策略

| 策略键 | 默认值 | 说明 |
|--------|--------|------|
| `truth_basis_policy` | `source-authority-evidence-conflict` | 正式真相必须同时具备 source/authority/evidence refs 且冲突已裁决 |

### 2.3 知识库写入策略

| 策略键 | 默认值 | 说明 |
|--------|--------|------|
| `kb_write_mode` | `read-first-CRUD` | KB 写入必须先读取再判断操作类型 |
| `kb_overwrite_allowed` | `false` | 禁止覆盖现有 KB 内容，只能追加 `superseded` 标记 |

---

## 3. 冲突解决策略

### 3.1 策略类型

| 策略名 | 行为 | 适用场景 |
|--------|------|----------|
| `fail-fast` | 遇到冲突立即失败，抛出错误 | 核心合法性策略冲突 |
| `preserve-and-escalate` | 保留第一值，升级到人工裁决 | 非关键配置冲突 |
| `prefer-strict` | 选择更严格/更限制性的值 | 安全/写入权限策略 |

### 3.2 各策略键的冲突解决方式

| 策略键 | 冲突策略 | 说明 |
|--------|----------|------|
| `legality_source` | `fail-fast` | 合法性来源冲突必须立即失败 |
| `registration_commit` | `preserve-and-escalate` | 提交要求冲突保留第一值并升级 |
| `registration_phase` | `prefer-strict` | 阶段冲突时优先选择未强制执行 |
| `truth_basis_policy` | `prefer-strict` | truth basis 冲突时优先更严格要求 |
| `kb_write_mode` | `prefer-strict` | 写入模式冲突时优先更限制模式 |
| `kb_overwrite_allowed` | `prefer-strict` | 覆盖权限冲突时优先禁止 |
| `default` | `preserve-and-escalate` | 未明确定义的策略使用默认策略 |

---

## 4. Scope 继承规则

### 4.1 继承链

```
workbot (base)
  ├─ AEdu (inherits: workbot)
  └─ platform-capabilities (inherits: workbot)
```

### 4.2 继承语义

- 子 scope 默认继承父 scope 的所有策略
- 子 scope 可以覆盖特定策略值
- 冲突策略定义必须显式声明，不隐式继承

---

## 5. Policy Pack 注入点

### 5.1 Gateway 注入

`memory_hook_gateway.py` 在 `build_context_package()` 中注入 policy pack：

```python
policy_pack = get_policy_pack_via_registry(project_scope)
package["system_context"]["policy_pack"] = policy_pack
```

### 5.2 上下文包中的位置

```json
{
  "system_context": {
    "policy_pack": {
      "schema_version": "m3-policy-pack-v1",
      "scope": "workbot",
      "policies": { ... },
      "conflict_strategies": { ... },
      "default_strategy": "preserve-and-escalate"
    }
  }
}
```

---

## 6. 错误处理

### 6.1 Policy Pack 解析失败

如果 policy pack 解析失败，context package 应包含错误信息：

```json
{
  "policy_pack": {
    "error": "unsupported scope: unknown",
    "scope": "unknown"
  }
}
```

同时 `validation_errors` 数组应包含相应错误。

### 6.2 冲突解决失败

当 `fail-fast` 策略触发时，应抛出 `ValueError`：

```python
raise ValueError(
    f"conflict on {policy_key} with values {values!r}: strategy={effective_strategy}"
)
```

---

## 7. Truth Basis

### Source Refs
- `workspace/INDEX.md`
- `workspace/memory/kb/global/workbot-hook-contract.md`

### Authority Refs
- `workspace/memory/kb/global/workbot-truth-model.md`
- `workspace/memory/kb/global/workbot-memory-system.md`

### Evidence Refs
- `workspace/tools/memory_hook_interfaces.py`
- `workspace/tools/memory_hook_impls.py`
- `workspace/tools/memory_hook_gateway.py`
- `tests/test_memory_hook_gateway_m3_policy_pack.py`

### Conflict Status
- `resolved`

---

## 8. 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-04-15 | M3-policy-pack-v1 | 初始版本：定义 schema、默认策略、冲突策略、注入点 |
