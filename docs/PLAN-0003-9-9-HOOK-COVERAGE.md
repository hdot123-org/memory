# PLAN-0003: 9/9 Factory Hook 全覆盖 (100% 融合)

```yaml
plan_id: PLAN-0003
title: "9/9 Factory Hook 全覆盖 (100% 融合)"
status: completed
version: v0.5.0
showdoc:
  item_id: 664858316
owner: main-agent
last_sync: 2026-05-19
last_verified: 2026-05-19
```

## 背景

Factory 官方支持 9 个 hook 事件，memory-core 此前只支持 4 个。为实现 100% Factory 融合，需要将 gateway 扩展到支持全部 9 个事件。

## 已完成项

| id | item | status | evidence |
|---|---|---|---|
| P0003-C001 | Gateway choices 扩展至 9 个事件 | completed | memory_hook_gateway.py +5行 |
| P0003-C002 | FACTORY_HOOK_EVENTS 扩展至 9 个事件 | completed | factory_global_hooks.py +4行 |
| P0003-C003 | settings.json 安装 9 个事件 | completed | 9/9 注册成功 |
| P0003-C004 | 测试更新支持 9 个事件 | completed | 1612 tests passed |
| P0003-C005 | pretooluse_guard Factory 格式兼容 | completed | 3c67ced commit |

## 9/9 Hook 事件矩阵

| Factory 事件 | Gateway 事件 | 用途 | 状态 |
|-------------|-------------|------|------|
| SessionStart | session-start | 会话开始：健康检查、完整性验证、历史报告注入 | ✅ |
| UserPromptSubmit | prompt-submit | 用户提交 prompt：上下文构建、artifact 生成 | ✅ |
| Stop | stop | 会话停止：最终状态记录、资源清理 | ✅ |
| Notification | notification | 通知事件：空闲检测、状态更新 | ✅ |
| PreToolUse | pre-tool-use | 工具调用前：ownership 保护、路径检查 | ✅ |
| PostToolUse | post-tool-use | 工具调用后：执行日志、状态记录 | ✅ 新增 |
| SubagentStop | subagent-stop | 子代理停止：子代理状态记录 | ✅ 新增 |
| PreCompact | pre-compact | 压缩前：上下文保存、状态快照 | ✅ 新增 |
| SessionEnd | session-end | 会话结束：最终持久化、统计记录 | ✅ 新增 |

## 代码改动

### memory_hook_gateway.py
```diff
- parser.add_argument("--event", required=True, choices=("session-start", "prompt-submit", "stop", "notification"))
+ parser.add_argument("--event", required=True, choices=(
+     "session-start", "prompt-submit", "stop", "notification",
+     "pre-tool-use", "post-tool-use", "subagent-stop",
+     "pre-compact", "session-end",
+ ))
```

### factory_global_hooks.py
```diff
 FACTORY_HOOK_EVENTS: tuple[tuple[str, str], ...] = (
     ("SessionStart", "session-start"),
     ("UserPromptSubmit", "prompt-submit"),
     ("Stop", "stop"),
     ("Notification", "notification"),
     ("PreToolUse", "pre-tool-use"),
+    ("PostToolUse", "post-tool-use"),
+    ("SubagentStop", "subagent-stop"),
+    ("PreCompact", "pre-compact"),
+    ("SessionEnd", "session-end"),
 )
```

### settings.json
9 个事件全部注册，每个事件使用相同格式：
```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event session-start", "timeout": 10}]}],
    ...
    "SessionEnd": [{"hooks": [{"type": "command", "command": "memory-hook --host factory --event session-end", "timeout": 10}]}]
  }
}
```

## 验证结果

```bash
# Gateway 接受所有 9 个事件
for event in session-start prompt-submit stop notification pre-tool-use post-tool-use subagent-stop pre-compact session-end; do
  echo '{}' | memory-hook-gateway --host factory --event "$event" --no-delegate > /dev/null && echo "✅ $event" || echo "❌ $event"
done
# 结果: 9/9 全部通过 ✅

# settings.json 注册检查
# 结果: 9/9 全部注册 ✅

# 全量测试
# 结果: 1612 passed, 0 failed ✅
```

## 里程碑

- 2026-05-19: PLAN-0003 创建，9/9 全覆盖实施完成
- 2026-05-19: Commit `7666fae` 推送到 main
- 2026-05-19: 文档同步到 ShowDoc + Feishu

## 下一步

- P2: Factory Plugin 格式（hooks.json 自动合并）
- P3: PostToolUse hook 用于文档变更自动检测
