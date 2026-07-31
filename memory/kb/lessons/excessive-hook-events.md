---
title: "过度 Hook 事件：Factory 平台行为分析"
type: lesson
severity: medium
status: accepted
date: 2026-07-31
tags: [hook, factory, performance, investigation]
---

# 过度 Hook 事件：Factory 平台行为分析

## 问题描述

memory-hook 记录了过量事件：
- events.jsonl 达到 82MB，包含 115,509 个事件
- 单次会话（2026-07-31）记录 202 个 stop 事件和 82 个 session-start 事件
- stop 事件在某些情况下密集出现（1-16 秒内多次）

## 根因分析

### 1. Factory 平台行为

**核心发现：这是 Factory 平台的正常行为，不是 bug。**

Factory 的 hook 机制设计：
- 每个工具调用（tool call）前后触发 `pre-tool-use` 和 `post-tool-use` 事件
- 每个会话启动/结束时触发 `session-start` 和 `session-end`
- 每个用户提交时触发 `prompt-submit`
- 每个会话停止时触发 `stop` 事件

### 2. 事件分布分析

从 events.jsonl 统计（2026-05-11 至 2026-07-31）：
```
post-tool-use:    78,069 次（67.6%）
pre-tool-use:     12,947 次（11.2%）
stop:              6,111 次（5.3%）
prompt-submit:     5,412 次（4.7%）
session-start:     4,211 次（3.6%）
session-end:       3,756 次（3.3%）
notification:      2,194 次（1.9%）
health-check:      2,047 次（1.8%）
subagent-stop:       764 次（0.7%）
```

**关键观察：**
- post-tool-use 占比最高（67.6%），符合"每次工具调用触发两次"的设计
- stop 事件在不同日期波动：2026-06-24 达到 891 次，2026-07-31 为 54 次
- session-start 和 stop 数量相关，说明 Factory 频繁启动/停止会话

### 3. 密集 stop 事件的原因

**可能原因：**
1. **多轮对话**：用户快速连续提问，每轮触发 session-start/stop
2. **子代理（Subagent）**：主代理启动多个子代理，每个都有独立生命周期
3. **工具调用密集**：复杂任务需要大量工具调用，间接触发更多事件
4. **Factory 重试机制**：网络问题或超时时 Factory 可能重试会话

**示例场景（2026-07-31 的 202 个 stop）：**
- 假设单次任务包含：1 session-start + 50 tool calls + 1 session-end
- 每次 tool call 触发 pre-tool-use + post-tool-use = 100 个事件
- 如果 Factory 启动了 4 个子代理，每个都有独立生命周期
- 总计：4 × (1 + 100 + 1) = 408 个事件
- 实际观察：82 session-start + 202 stop + 大量 tool-use 事件

### 4. 为什么 '{}' 输出导致问题

**原始问题：**
- 非注入事件（stop, notification, session-end）返回 `'{}'`
- Factory 将 stdout 显示给用户
- 用户在终端看到大量空 `{}` 输出，造成视觉干扰

**这不是事件过多的问题，而是输出格式的问题。**

## 解决方案

### 修复内容

修改 `memory_core/tools/memory_hook_gateway.py` 的 `_format_factory_output()` 函数：

**修改前：**
```python
if event not in ("session-start", "prompt-submit"):
    return "{}"  # 空 JSON 被 Factory 显示给用户
```

**修改后：**
```python
if event not in ("session-start", "prompt-submit"):
    if package.get("status") == "ok":
        return '{"suppressOutput": true}'  # Factory 知道这是静默成功
    return "{}"  # 降级状态：保留错误可见性
```

### 设计原则

1. **成功时抑制输出**：`{"suppressOutput": true}` 告诉 Factory 不要显示
2. **错误时保持可见**：降级状态（`status != "ok"`）返回 `'{}'` 让错误信息可见
3. **最小改动**：只修改非注入事件，不影响 session-start 和 prompt-submit

## 经验教训

### 1. 理解平台行为 vs Bug

- Factory 的事件频率是平台设计，不是 bug
- 问题在于输出格式，不是事件数量
- 调查时先确认"这是预期行为吗？"

### 2. 事件日志管理

**当前问题：**
- events.jsonl 持续增长，已达 82MB
- 没有自动轮转或清理机制

**建议：**
- 实现日志轮转（按日期分割）
- 定期归档旧日志（压缩或删除 30 天前）
- 添加日志大小监控

### 3. 输出抑制模式

- Factory 支持 `{"suppressOutput": true}` 协议
- 对于静默成功的操作，使用此协议避免用户干扰
- 错误情况应保持输出可见，便于调试

### 4. 性能影响

**事件记录性能：**
- 每次 hook 调用写入 events.jsonl（追加模式）
- 115K 事件 × ~700 bytes = 82MB
- 追加写入性能可接受，但文件大小影响读取/分析

**优化建议：**
- 批量写入（减少 I/O）
- 异步写入（不阻塞 hook 返回）
- 定期压缩旧日志

## 相关文件

- `memory_core/tools/memory_hook_gateway.py` - hook 网关主逻辑
- `~/.memory-core/project-lifecycle/events.jsonl` - 事件日志（82MB）
- `memory_core/tools/project_lifecycle.py` - 事件记录逻辑

## 验证方法

```bash
# 测试 stop 事件输出
memory-hook --host factory --event stop
# 预期：输出 {"suppressOutput": true}

# 测试降级状态（模拟错误）
# 需要触发降级路径，观察输出仍为 '{}'

# 检查事件日志
wc -l ~/.memory-core/project-lifecycle/events.jsonl
du -h ~/.memory-core/project-lifecycle/events.jsonl
```

## 后续改进

1. **日志轮转**：实现自动日志轮转，避免单文件过大
2. **监控告警**：当日志超过阈值（如 100MB）时告警
3. **事件去重**：考虑对重复事件去重（如同一会话的多次 stop）
4. **性能优化**：异步写入事件日志，减少 I/O 阻塞

---

**来源：** memory-hook gateway 过度事件调查  
**日期：** 2026-07-31  
**触发：** Factory 平台 200+ stop 事件导致输出干扰
