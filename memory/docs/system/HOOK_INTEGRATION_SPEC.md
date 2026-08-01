---
type: "[SPEC]"
title: "Hook 集成规范：跨 IDE/平台配置标准与验证方法"
shortname: SPEC-HOOK-INTEGRATION
status: active
created: 2026-07-25
updated: 2026-07-25
scope: default
tags: [memory,system,spec,hooks,integration]
---

# SPEC-HOOK-INTEGRATION — Hook 集成规范

## 概述

memory-core 通过 hook 机制在各 IDE/Agent 平台的生命周期事件中自动执行记忆操作。
本规范定义跨平台的 hook 配置标准、事件映射、wrapper 契约及验证方法。

### 核心架构

```
IDE/Agent 平台 (生命周期事件)
    ↓ stdin JSON
memory-hook wrapper (~/.factory/bin/memory-hook)
    ↓ exec
memory-hook-gateway (--host <platform> --event <event>)
    ↓ delegate
memory-core handler (session-start, prompt-submit, ...)
```

所有平台共用同一个 wrapper 入口，通过 `--host` 参数区分来源平台。

---

## 1. 事件命名规范

### 1.1 双层命名

每个事件有两个名称：**平台事件名**（PascalCase，IDE 原生）和 **gateway 事件名**（kebab-case，内部统一）。

| 平台事件名 | gateway 事件名 | 用途 |
|------------|---------------|------|
| SessionStart | session-start | 会话开始：健康检查、上下文加载 |
| UserPromptSubmit | prompt-submit | 用户提交 prompt：上下文构建 |
| PreToolUse | pre-tool-use | 工具调用前：ownership 保护、路径检查 |
| PostToolUse | post-tool-use | 工具调用后：执行日志 |
| Stop | stop | 会话停止：状态记录、资源清理 |
| Notification | notification | 通知事件：空闲检测 |
| SubagentStop | subagent-stop | 子代理停止 |
| PreCompact | pre-compact | 压缩前：上下文保存 |
| SessionEnd | session-end | 会话结束：最终持久化 |

### 1.2 命名规则

- **配置文件中**使用平台事件名（PascalCase）
- **gateway 参数**使用 gateway 事件名（kebab-case）
- wrapper 负责 PascalCase → kebab-case 的映射

---

## 2. memory-hook Wrapper 契约

### 2.1 路径

```
~/.factory/bin/memory-hook
```

### 2.2 调用签名

```bash
memory-hook --host <platform> --event <gateway-event-name>
```

| 参数 | 值 |
|------|-----|
| `--host` | `factory`（CLI 当前仅支持 factory；内部 API 支持 codex/claude，但 argparse 限制为 factory） |
| `--event` | gateway 事件名（kebab-case，见 1.1 节） |

> **注**: gateway CLI 的 `--host` 参数当前仅接受 `factory`。其他 host 值（codex、claude）
> 在内部 API 层支持，但 CLI argparse 限制为 `choices=("factory",)`。MCP server 内部使用
> `host="factory"` 调用 `build_context_package_simple`，因为底层逻辑是平台无关的。

### 2.3 stdin 协议

所有平台通过 stdin 传入 JSON。wrapper 从中提取 `cwd` 字段确定项目根目录。

```json
{
  "cwd": "/path/to/project",
  "session_id": "...",
  ...平台特定字段
}
```

### 2.4 Wrapper 职责

1. **项目生命周期跟踪** — 记录 session 开始/结束
2. **HOME 目录防污染** — 阻止对 HOME 的误写
3. **Source repo 检测** — memory-core 自身只读，跳过写入
4. **Git root 归一化** — 从子目录调用时自动定位 git root

### 2.5 手动测试

```bash
# 模拟平台调用
echo '{"cwd":"/path/to/project"}' | ~/.factory/bin/memory-hook --host factory --event session-start
```

---

## 3. 平台配置标准

### 3.1 Factory (Droid)

**状态**: 完整支持（9/9 事件）

**配置文件**: `~/.factory/hooks.json`

```json
{
  "SessionStart": [{
    "hooks": [{
      "type": "command",
      "command": "/Users/<user>/.factory/bin/memory-hook --host factory --event session-start",
      "timeout": 10
    }]
  }]
}
```

**配置规则**:
- 9 个事件全部注册
- 每个事件一个 hook entry
- `type` 固定为 `"command"`
- `timeout` 单位为秒，默认 10
- `command` 使用 wrapper 绝对路径

**特殊**: SessionEnd 有两个 hook entry（session_end_logger + memory-hook）。

### 3.2 ZCode

**状态**: 配置可加载，dispatch 未实现（v3.4.2）

**配置文件**: `~/.zcode/cli/config.json`

```json
{
  "hooks": {
    "enabled": true,
    "timeoutMs": 10000,
    "events": {
      "SessionStart": [{
        "matcher": "startup|clear|compact",
        "hooks": [{
          "type": "command",
          "command": "<wrapper-cmd>",
          "timeoutMs": 10000
        }]
      }],
      "PreToolUse": [{
        "matcher": ".*",
        "hooks": [{ "type": "command", "command": "<wrapper-cmd>", "timeoutMs": 10000 }]
      }]
    }
  }
}
```

**配置规则**:
- `hooks.enabled` 必须为 `true`
- `timeoutMs` 单位为毫秒（与 Factory 的秒不同）
- `matcher` 字段**必须 >= 1 字符**，空字符串导致 schema 验证失败
  - 使用 `".*"` 匹配全部（UI 提示"留空匹配全部"但 schema 拒绝空串）
- 7 个事件可用: SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure, Stop
- 缺少 Factory 的: Notification, SubagentStop, PreCompact, SessionEnd

**已知问题**:
- v3.4.2 的 `createHooksService()` 只有 `loadHooks`/`saveHooks`，**无 dispatch 代码**
- hooks 在 bootstrap 时加载到内存（日志可见 `hookCount`），但生命周期事件不会触发执行
- 详细分析见 `~/.zcode/cli/HOOKS-STATUS.md`

**cwd 提取**（ZCode stdin 格式与 Factory 不同）:
```bash
FACTORY_PROJECT_DIR="$(echo "$(cat)" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)" /Users/<user>/.factory/bin/memory-hook --host zcode --event <event>
```

### 3.3 新平台接入清单

接入新 IDE/Agent 平台时：

1. **确认事件列表** — 该平台支持哪些生命周期事件
2. **找到配置文件路径** — 平台读取 hook 配置的位置
3. **确认 stdin 格式** — 平台传给 hook 的 JSON schema（特别是 `cwd` 字段名）
4. **确认 matcher 语义** — 空字符串是否合法、regex 还是 glob
5. **确认 timeout 单位** — 秒还是毫秒
6. **验证 dispatch 实现** — 配置加载后是否有实际执行代码（参考验证方法）
7. **编写配置模板** — 按本规范格式生成配置
8. **端到端测试** — 参考 4.2 节验证方法

---

## 4. 验证方法

### 4.1 Wrapper 独立验证

```bash
# 验证 wrapper 可执行
~/.factory/bin/memory-hook --host factory --event session-start

# 验证 9 个事件全部接受
for event in session-start prompt-submit stop notification pre-tool-use post-tool-use subagent-stop pre-compact session-end; do
  echo '{}' | memory-hook-gateway --host factory --event "$event" --no-delegate > /dev/null 2>&1 && echo "PASS $event" || echo "FAIL $event"
done
```

### 4.2 平台端到端验证

在目标平台中执行以下操作，然后检查 per-project 事件文件或 hook 输出日志：

| 操作 | 预期事件 |
|------|---------|
| 新建会话 / 启动 | session-start |
| 发送一条消息 | prompt-submit |
| AI 调用工具 | pre-tool-use + post-tool-use |
| AI 响应结束 | stop |
| 关闭会话 | session-end（Factory）/ 无（ZCode） |

**验证脚本**:
```bash
# 检查最近 N 秒内是否有新事件（v0.9.4+ per-project 分片结构）
TAIL_SECONDS=30
find ~/.memory-core/project-lifecycle -name "*.jsonl" -newermt "-${TAIL_SECONDS} seconds" -exec tail -5 {} \;
```

### 4.3 Dispatch 实现验证（新平台必做）

当接入新平台时，**必须验证配置加载后是否有实际 dispatch 代码**：

1. 检查启动日志中的 `hookCount`（应为配置的 hook 数量）
2. 检查是否有 `config.file.invalid` 警告（schema 验证失败会导致 hookCount=0）
3. 提取平台源码，搜索 dispatch 函数:
   ```
   grep -rl "executeHook\|triggerHook\|runHook\|fireHook\|dispatchHook\|invokeHook" <platform-source>/
   ```
4. 如果无结果，该平台的 hooks 功能**未实现 dispatch**，配置不会生效

### 4.4 配置有效性检查

```bash
# JSON 语法验证
python3 -c "import json; json.load(open('<config-path>')); print('Valid')"

# 检查 matcher 非空（ZCode 特有约束）
python3 -c "
import json
cfg = json.load(open('<config-path>'))
for event, entries in cfg.get('hooks',{}).get('events',{}).items():
    for entry in entries:
        m = entry.get('matcher', '')
        if m == '': print(f'WARNING: {event} has empty matcher (may fail validation)')
"
```

---

## 5. Gateway 性能优化：非注入事件快速路径

### 5.1 优化背景

非注入事件（stop、notification、subagent-stop、post-tool-use、pre-compact、session-end）不需要向用户注入上下文信息，但仍执行完整的 `build_context_package()` 流程，包括：
- 12-25 次文件读取（canonical files、project-map、governance 等）
- 5 次 git 子进程调用（git registration probe）
- 7-10 次文件写入（artifact snapshot、event log、metrics）

这些开销对非注入事件是浪费的，因为它们最终只输出 `{"suppressOutput": true}`。

### 5.2 快速路径设计

Gateway 在 `main()` 中为非注入事件实现快速路径，跳过昂贵的上下文包构建：

```
main()
├── 解析参数、读取 stdin
├── source repo 检查
├── PreToolUse guard（如适用）
│
├── 判断：是否为非注入事件？
│   ├── YES → 快速路径：
│   │   ├── _record_project_lifecycle_event()  ← 保留生命周期记录
│   │   ├── _emit_fast_path_metrics()          ← 记录性能指标
│   │   ├── _record_event_log_minimal()        ← 轻量审计日志
│   │   └── 输出 {"suppressOutput": true}
│   │
│   └── NO → 完整路径（session-start、prompt-submit）：
│       ├── build_context_package()            ← 完整构建
│       ├── _write_artifacts_and_emit_metrics()
│       └── 输出 hookSpecificOutput + additionalContext
```

### 5.3 事件分类

| 事件类型 | 事件列表 | 处理路径 | 输出 |
|---------|---------|---------|------|
| 非注入事件 | stop, notification, subagent-stop, post-tool-use, pre-compact, session-end | 快速路径 | `{"suppressOutput": true}` |
| 注入事件 | session-start, prompt-submit | 完整路径 | `hookSpecificOutput` + `additionalContext` |

### 5.4 快速路径保证

快速路径保留以下功能：
1. **生命周期记录** — `_record_project_lifecycle_event()` 仍被调用，确保项目活动跟踪不中断
2. **性能指标** — `_emit_fast_path_metrics()` 记录事件执行时间
3. **审计日志** — `_record_event_log_minimal()` 写入轻量级事件日志（仅时间戳、事件名、状态）

快速路径跳过以下功能：
- `build_context_package()` — 不构建完整上下文包
- Artifact snapshot 写入 — 不写入 `contexts/{date}/` 快照文件
- Git registration probe — 不执行 git 子进程探测
- Project-map 验证 — 不验证项目映射完整性

### 5.5 降级处理

快速路径中的异常不会导致崩溃：
- `lifecycle/metrics/event_log` 异常被捕获并记录到 error log
- 即使发生异常，仍返回 `{"suppressOutput": true}` 和 exit code 0
- 非注入事件的降级状态对用户无意义，因此保持静默

**内容级降级不检测**：快速路径不执行内容级降级检测（如 canonical path 缺失、project-map 验证失败）。这与 VAL-DEGRADED-001 的放松一致——非注入事件的输出被抑制，降级状态对用户无意义。降级检测仅由注入事件（session-start、prompt-submit）的完整路径覆盖，注入事件仍执行完整验证并在 status 字段中标记降级。

---

## 6. 事件覆盖矩阵

| 事件 | Factory | ZCode v3.4.2 | ZCode dispatch |
|------|---------|-------------|----------------|
| SessionStart | 可用 | 可配置 | 未实现 |
| UserPromptSubmit | 可用 | 可配置 | 未实现 |
| PreToolUse | 可用 | 可配置 | 未实现 |
| PostToolUse | 可用 | 可配置 | 未实现 |
| Stop | 可用 | 可配置 | 未实现 |
| Notification | 可用 | 无此事件 | N/A |
| SubagentStop | 可用 | 无此事件 | N/A |
| PreCompact | 可用 | 无此事件 | N/A |
| SessionEnd | 可用 | 无此事件 | N/A |
| PermissionRequest | 无此事件 | 可配置 | 未实现 |
| PostToolUseFailure | 无此事件 | 可配置 | 未实现 |

---

## 7. 常见问题

### Q: ZCode 配置了 hooks 但不触发？
A: ZCode v3.4.2 未实现 hook dispatch。`createHooksService()` 只有 load/save，无执行代码。配置会被正确加载（日志可见 hookCount），但生命周期事件不会触发执行。等待后续版本更新。

### Q: ZCode 报 `config.file.invalid` matcher 错误？
A: ZCode schema 要求 matcher >= 1 字符。将空字符串 `""` 改为 `".*"` 匹配全部。

### Q: Factory 的 timeout 和 ZCode 的 timeoutMs 有什么区别？
A: Factory `timeout` 单位是秒（`"timeout": 10`），ZCode `timeoutMs` 单位是毫秒（`"timeoutMs": 10000`）。

### Q: 如何确认新平台的 hooks 真的会触发？
A: 参考 4.3 节的 dispatch 实现验证。**配置加载成功不等于会执行**，必须确认源码中有 dispatch 代码。

---

## 8. MCP 补充路径（Hook 不可用时）

> 参考依据：Claude Code 官方文档明确区分 Hook = enforcement（保证执行），MCP = external access（按需调用）。
> "Put guardrails in hooks. If a rule must hold every time, make it a hook rather than a prompt instruction."

### 8.1 分层原则

| 能力类型 | 路径 | 原因 |
|---------|------|------|
| 生命周期自动化（上下文注入、写入保护、事件记录） | Hook | 必须保证执行（enforcement） |
| 外部数据访问（知识库搜索、项目查询） | MCP | AI 按需调用（on-demand） |
| 两者的交集 | 优先 Hook | Hook 是 guaranteed，MCP 是 advisory |

### 8.2 平台集成矩阵

| 平台 | Hook | MCP 暴露工具 | 配置文件 |
|------|------|-------------|---------|
| Factory (Droid) | 9/9 事件 | 仅 `search_memory` | `~/.factory/mcp.json` |
| ZCode | 不触发（v3.4.2） | 全部 9 工具 | `~/.zcode/cli/config.json` |
| 新平台 | 先验 dispatch | dispatch 不可用 → 全量 MCP | 平台 MCP 配置 |

### 8.3 MCP Server 配置

**系统级命令**: `memory-mcp-server`

**Factory 配置**（`~/.factory/mcp.json`）:
```json
{
  "mcpServers": {
    "memory-core": {
      "command": "memory-mcp-server",
      "args": ["--tools", "search_memory"],
      "type": "stdio"
    }
  }
}
```

**ZCode 配置**（`~/.zcode/cli/config.json`）:
```json
{
  "mcp": {
    "servers": {
      "memory-core": {
        "type": "stdio",
        "command": "memory-mcp-server",
        "timeoutMs": 30000
      }
    }
  }
}
```

### 8.4 工具过滤

MCP server 支持 `--tools` 参数限制暴露的工具集：

```bash
# 全量（9 工具）— 用于无 hook 的平台
memory-mcp-server

# 仅搜索能力 — 用于已有 hook 的平台
memory-mcp-server --tools search_memory

# 自定义子集
memory-mcp-server --tools search_memory,list_projects,get_health
```

### 8.5 9 工具与 Hook 能力对照

| MCP 工具 | 对应 Hook 事件 | Factory 上需要? | ZCode 上需要? |
|---------|---------------|----------------|---------------|
| `load_context` | session-start | 不需要（Hook 覆盖） | 需要 |
| `search_memory` | (新能力) | **需要** | **需要** |
| `resolve_doc_path` | (辅助) | 不需要 | 需要 |
| `save_memory` | 各种写入 | 不需要（Hook 覆盖） | 需要 |
| `validate_write` | pre-tool-use | 不需要（Hook 是 enforcement） | 需要（advisory 版） |
| `record_event` | 全部生命周期 | 不需要（Hook 覆盖） | 需要 |
| `get_health` | session-start | 不需要（Hook 覆盖） | 需要 |
| `list_projects` | (辅助) | 可选 | 可选 |
| `get_daily_summary` | session-end | 不需要（Hook 覆盖） | 需要 |

### 8.6 MCP 的局限性（必须承认）

| 能力 | Hook (Factory) | MCP (ZCode) |
|------|---------------|-------------|
| 写入阻断 | **Enforcement**（exit code 2 阻断执行） | **Advisory**（AI 可能忽略建议） |
| 上下文注入 | **自动**（每次 session-start 保证） | **依赖 AI 调用**（可能忘记） |
| 事件记录 | **自动**（每个事件触发） | **依赖 AI 调用**（可能遗漏） |

MCP 是 hook 不可用时的 fallback，不是 hook 的等价替代。

---

## 9. 生命周期事件存储结构

### 9.1 按项目分片存储

从 v0.9.4 开始，生命周期事件从全局单文件 `events.jsonl` 迁移到按项目、按日期分片的存储结构。

**旧结构（已弃用）**:
```
~/.memory-core/project-lifecycle/
├── projects/
│   └── {project_id}.json                    ← 状态文件（路径不变）
├── path-index.json                          ← 路径索引（不变）
└── events.jsonl                             ← 全局事件日志（已弃用，停止写入）
```

**新结构（v0.9.4+）**:
```
~/.memory-core/project-lifecycle/
├── projects/
│   ├── {project_id}.json                    ← 状态文件（路径不变）
│   ├── {project_id}/                        ← 新增：按项目事件目录
│   │   └── events/
│   │       └── 2026-08-01.jsonl             ← 每日事件日志（按天追加）
│   └── ...
├── path-index.json                          ← 不变
└── events.jsonl                             ← 已弃用（迁移工具会归档）
```

### 9.2 写入路径

`record_project_lifecycle()` 函数现在执行 3 次写入：

1. **状态文件** `projects/{project_id}.json` — 覆盖写入（不变）
2. **路径索引** `path-index.json` — 覆盖写入（不变）
3. **每日事件日志** `projects/{project_id}/events/{YYYY-MM-DD}.jsonl` — 追加写入（新增）

返回字典的 `event_log` 字段指向新的每日事件文件路径。

### 9.3 自动清理

新增 `_cleanup_old_event_files()` 函数，在每次 hook 调用时机会性清理超过保留期的事件文件。

**配置**:
- 环境变量: `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS`（默认: 30）
- 设置为 `0` 禁用清理
- 通过 `projects/{project_id}/.last-cleanup` 哨兵文件节流，每个项目每天最多清理一次

### 9.4 迁移工具

提供 `memory-lifecycle-migrate` CLI 工具，将旧的 `events.jsonl` 迁移到新的按项目分片结构：

```bash
# 迁移（默认 lifecycle root）
memory-lifecycle-migrate

# 指定 lifecycle root
memory-lifecycle-migrate --lifecycle-root ~/.memory-core/project-lifecycle

# JSON 输出
memory-lifecycle-migrate --json
```

**迁移行为**:
1. 读取 `events.jsonl`，按 `project_id` 和日期分组
2. 写入 `projects/{project_id}/events/{YYYY-MM-DD}.jsonl`
3. 将原文件重命名为 `events.jsonl.archived`（字节相同）
4. 输出统计信息（total_read, total_written, per_project, skipped, archive_path）

**幂等性**: 重复运行不会产生重复数据或错误。

### 9.5 向后兼容性

以下组件不受此变更影响：

| 组件 | 影响 | 原因 |
|------|------|------|
| `rebuild_path_index()` | 无 | 仅读取 `projects/*.json`，不依赖事件日志 |
| `build_project_lifecycle_record()` | 无 | 构建记录字典，不写入事件文件 |
| `hook_event_stats.py` | 无 | 读取 artifact `EVENT_LOG`（不同文件） |
| 状态文件路径 | 无 | `projects/{project_id}.json` 路径不变 |
| 路径索引 | 无 | `path-index.json` 路径不变 |

---

## Changelog

| Version | Date | Author | Change |
|---------|------|--------|--------|
| v1.3 | 2026-08-01 | droid | 新增第 9 章：生命周期事件存储结构（按项目分片、自动清理、迁移工具、向后兼容性） |
| v1.2 | 2026-08-01 | droid | Section 5.5: 补充降级处理说明（非注入事件不检测内容级降级）；修复 section 编号重复（FAQ 改为 7，MCP 改为 8） |
| v1.1 | 2026-07-25 | droid | 新增第 7 章：MCP 补充路径（Hook vs MCP 分层、平台矩阵、工具过滤、局限性） |
| v1.0 | 2026-07-25 | droid | 初始版本：Factory 9/9 完整支持 + ZCode v3.4.2 dispatch 未实现记录 |
