# Hook 契约

session-start 与 prompt-submit 生命周期规则。

## 1. Hook 生命周期

memory-core 的 hook 系统在两个关键事件时触发：

- **session-start** — Agent 会话开始时，构建初始 context package
- **prompt-submit** — 每次用户提交 prompt 时，更新 context package

两个事件都通过 `memory_hook_gateway` 调用 `build_context_package` 系列函数。

## 2. 合法上下文来源

gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。
未完成提交的登记不得生效。

这是 `project-map-governance.md` 中声明的核心规则，hook 系统通过 `MKR_HOOK_MAP_ONLY_CONTEXT`
和 `MKR_HOOK_REGISTRATION_GATE` 标记强制执行。

## 3. Context Package Schema

context package 必须包含下列 key：

| Key | 类型 | 说明 |
|-----|------|------|
| `status` | string | 系统状态 |
| `host` | string | 宿主环境（如 `factory`） |
| `event` | string | 触发事件（`session-start` / `prompt-submit`） |
| `schema_version` | string | Schema 版本（如 `v1`） |
| `system_context` | object | 系统上下文 |
| `task_context` | object | 任务上下文 |

`system_context` 必需子 key：`boot_entry`、`state_entry`。
`task_context` 必需子 key：`session_id`、`event`。

## 4. Hook 契约校验

`ProjectMapValidator.validate_unique_legal_system_contract()` 检查 hook 契约文件包含：

1. `MKR_HOOK_MAP_ONLY_CONTEXT` — 声明 map-only 合法上下文来源
2. `MKR_HOOK_REGISTRATION_GATE` — 声明未来注册的 git-commit gate

缺少任一标记会导致校验失败。

## 5. Hook 文件边界

hook 系统的核心实现在 `memory_core/tools/memory_hook_gateway.py`，
全局 hook wrapper 位于 `~/.factory/bin/memory-hook`。
项目级 hook 配置通过 `adapter.toml` 声明 `project_scope`。

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- memory/kb/global/project-map-governance.md

### Evidence Refs

- tests/conftest.py

### Conflict Status

- resolved
