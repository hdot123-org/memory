# Bug: Session 关闭协调器崩溃 + 子代理进程未回收 → "Session not available on this machine"

## 基本信息

- **Factory 版本**: 0.83.0 (`com.electron.factory`)
- **macOS**: darwin 25.4.0 (Sequoia)
- **Factory CLI 版本**: 0.126.0
- **复现概率**: 偶发（长会话 + 多子代理编排 + 数小时空白间隔后关闭）
- **会话 ID**: `138d7ded-8dbf-4773-9df4-022fe3c4727a`
- **报告日期**: 2026-05-16

## 问题描述

一个长时间运行的交互式会话（包含 30+ 个子代理 Task 编排，跨数小时多次活动/空白间隔）在关闭后，Factory 报错：

```
Session 138d7ded-8dbf-4773-9df4-022fe3c4727a is not available on this machine
```

重启 Factory App 后问题消失，会话可恢复。说明这不是数据丢失，而是运行态不一致。

## 根因

**Factory 的 `shutdownCoordinator.ts` 在关闭 session 时发生崩溃**，导致：
1. Session 没有写入 `SessionEnd` 事件
2. 子代理进程（`droid exec`）没有被正确回收，变成孤儿进程（PPID 被 launchd 收养）
3. 后台任务注册表被清空，daemon 不知道孤儿进程存在
4. daemon 再次尝试恢复或清理时发现运行态不一致，报 "not available"

## 证据链

### 1. 子代理进程孤儿化（PID 7023）

```
PID  7023
PPID 1 (launchd, 原父进程已退出)
启动时间: 2026-05-14T23:03:17 (UTC+8)
运行时长: >25 小时
命令: droid exec ... --calling-session-id 138d7ded-8dbf-4773-9df4-022fe3c4727a --calling-tool-use-id call_aa853a479228454590d4dbf3 --session-title "worker: 修复 11 个失败测试"
```

### 2. task-events.jsonl 只有 start 没有 end

```json
{"ts":"2026-05-14T15:03:17Z","event":"start",
  "tool_input_hash":"c0feaa8fdfaad56cd8c087ee9bb55249d1334d24",
  "subagent_type":"worker","description":"修复 11 个失败测试"}
```

后续无任何匹配的 `end` 或 `subagent_stop_audit` 事件。同一 session 中其他 30+ 子代理都有成对 start/end，唯独这一个缺失。

### 3. 父 session 无 SessionEnd 事件

Transcript 文件 `/Users/busiji/.factory/sessions/-Users-busiji-memory/138d7ded-8dbf-4773-9df4-022fe3c4727a.jsonl`（359 行，~813KB）最后一条活动停在 `2026-05-15T14:24:52.941Z`，之后没有任何 `session_end` 类型记录。

### 4. daemon 关闭协调器崩溃堆栈

`daemon-stderr.log` 中存在：

```
runCoreShutdown
  → shutdownCoordinator.ts:245
  → shutdownCoordinator.ts:153
  → shutdownCoordinator.ts:248 (反复调用)
```

这是通用 shutdown 异常，未关联到具体 session ID，但时间线与问题 session 的关闭时间吻合。

### 5. 本地文件完整（非数据丢失）

| 文件 | 状态 |
|------|------|
| `sessions/-Users-busiji-memory/138d7ded-8dbf-4773-9df4-022fe3c4727a.jsonl` | 359 行，813KB，正常 |
| `sessions-index.json` 条目 | 正常，无 `archivedAt` |
| `session-discovery-index.json` | 已缓存 |
| Transcript 末尾消息 | 正常 `message` 类型，无 error |

### 6. 后台任务注册表已清空

```json
background-tasks.json: {"tasks": []}
background-processes.json: {"processes": []}
```

Factory 主进程已不知道孤儿进程存在。

## 时间线

| 时间 (UTC+8) | 事件 |
|-------------|------|
| 2026-05-14 20:17 | Session 开始 |
| 2026-05-14 23:37 | 第一轮活动结束 |
| 2026-05-14 23:03 | 子代理 "修复 11 个失败测试" 启动（PID 7023）|
| 2026-05-15 08:39 | 第二轮恢复活动 |
| 2026-05-15 09:27 | 第二轮结束 |
| 2026-05-15 16:07 | 第三轮恢复活动 |
| 2026-05-15 16:35 | 第三轮结束 |
| 2026-05-15 22:24 | 最后一条活动记录 |
| 之后某时刻 | Session 关闭/超时 → shutdownCoordinator 崩溃 |
| 之后 | PID 7023 父进程退出，PPID 被回收至 1 |
| 之后 | daemon 尝试恢复 → 报 "not available on this machine" |

## 复现步骤（推测）

1. 启动一个交互式 session
2. 编排多个子代理 Task（≥30 个）
3. 在数小时间隔内多次恢复 session 活动
4. 关闭 session 或让其超时
5. 尝试重新 attach 该 session → 报 "not available on this machine"

## 影响

- 长会话用户在关闭后无法恢复会话
- 子代理进程变成孤儿，持续占用系统资源
- 重启 Factory App 可临时恢复（重建运行态）

## 建议修复方向

1. **`shutdownCoordinator.ts` 需要容错处理**：关闭流程应该捕获异步异常，而不是让崩溃导致 SessionEnd 事件丢失
2. **子代理进程需要超时回收机制**：如果子代理进程在一定时间后没有响应或没有写入 end 事件，daemon 应该主动回收
3. **后台任务注册表应与进程生命周期绑定**：不应该在进程未结束时清空注册表
4. **SessionEnd 事件写入应该是原子操作**：即使在关闭异常时也应该尽量写入

## 附加文件

- `~/.factory/logs/droid-log-single.log`（1.9GB，含完整 daemon 日志）
- `~/.factory/state/task-events.jsonl`（含子代理 start 记录）
- `~/.factory/sessions/-Users-busiji-memory/138d7ded-8dbf-4773-9df4-022fe3c4727a.jsonl`（完整 transcript）
- `~/.factory/sessions-index.json`
- `daemon-stderr.log`（含 shutdownCoordinator 崩溃堆栈）
