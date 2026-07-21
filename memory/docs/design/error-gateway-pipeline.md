# Error Gateway Pipeline Design

> 文档编号：DESIGN-EG-001
> 版本：V1.0
> 创建日期：2026-07-17
> 更新日期：2026-07-17
> 状态：内部参考（gitignored，不公开）

## 概述

Error Gateway 是一条从 PostHog 错误告警到自动修复 PR 的端到端管道。
当错误频率超过阈值时，系统自动创建 GitHub Issue、定位代码、提交修复 PR，实现错误自愈闭环。

## 1. 完整管道链路

```
PostHog Alert (错误频率 >10/hr)
  → webhook.exa.edu.kg (internal_destination CDP Function)
    → n8n (告警路由 + 数据标准化)
      → Mac:5555 (adnanh/webhook server)
        → trigger-error-droid.sh (触发脚本)
          → droid exec --tag error-gateway (Factory Droid 自动修复)
            → GitHub Issue (创建/复用)
            → 修复 PR (Closes #N, 合并后 Issue 自动关闭)
```

### 1.1 各环节职责

| 环节 | 组件 | 职责 |
|------|------|------|
| 错误捕获 | telemetry_bridge.py | 捕获运行时错误，脱敏后发送到 PostHog |
| 告警触发 | PostHog Alert | 错误频率 >10/hr 时触发 internal_destination |
| Webhook 路由 | webhook.exa.edu.kg | CDP Function 将 PostHog 事件转发到内部 webhook |
| 数据标准化 | n8n | 解析 PostHog payload，提取 error_type/method/failed_event/count |
| 本地触发 | Mac:5555 (adnanh/webhook) | hooks.json 路由到 trigger-error-droid.sh |
| Droid 执行 | trigger-error-droid.sh | 调用 `droid exec --tag error-gateway` 启动自动修复 |
| 自动修复 | error-gateway skill | 幂等检查 → Issue 创建 → 代码定位 → 修复 → PR |

### 1.2 数据流转

```json
{
  "error_type": "HTTPError",
  "method": "batch_capture",
  "failed_event": "memory.error",
  "count": 15,
  "last_seen": "2026-07-17T10:30:00Z",
  "fingerprint": "HTTPError:batch_capture:memory.error"
}
```

## 2. 五来源错误监控体系

错误不只来自 PostHog，系统从 5 个来源收集错误，形成全面的监控覆盖。

| # | 来源 | 收集方式 | 处理方 | 频率 |
|---|------|---------|--------|------|
| 1 | Factory 软件日志 | droid-log-single.log ERROR/FATAL | factory-error-monitor.sh 阶段 1 | 每小时 |
| 2 | 项目 errors/ | 各项目 memory/system/errors/ | factory-error-monitor.sh 阶段 2 | 每小时 |
| 3 | Linear 接入层 | webhook/logs/trigger-*.log | factory-error-monitor.sh 阶段 3 | 每小时 |
| 4 | CI 流水线 | GitLab pipeline webhook | webhook ci-failed | 实时 |
| 5 | 基础设施 | daily audit | daily-audit-cron.sh | 每天 |

### 2.1 错误分类

**可忽略（瞬态/自愈）：**
- MCP server 连接抖动（list/refresh failed）
- Hook 非关键路径错误（returning empty array）

**需修复：**
- droid command 执行失败
- 项目 hook gateway 错误
- Linear 路由失败 / droid exec 崩溃
- 任何未知新错误

## 3. 幂等性检查

**核心原则：** 同一错误指纹只创建一次 Issue，防止无限循环和重复工作。

### 3.1 检查流程

```bash
# 搜索所有状态（open + closed）的 Issue
EXISTING=$(gh issue list \
  --repo <githubRepo> \
  --label posthog-error-sync \
  --state all \
  --search "<error_type> <method>" \
  --json number,state,title \
  2>/dev/null)
```

### 3.2 决策逻辑

| 场景 | 动作 |
|------|------|
| 无匹配 Issue | 创建新 Issue，标签 `needs-triage,posthog-error-sync` |
| OPEN Issue 存在 | 跳过创建，在现有 Issue 添加 occurrence comment，复用 Issue 号 |
| CLOSED Issue 存在 | 判定为回归，re-open Issue，添加回归 comment，复用 Issue 号 |

### 3.3 关键约束

- **必须搜索 `--state all`**（不仅仅是 open），防止已关闭 Issue 被重复创建
- Issue 创建是硬性前置条件，未获得 Issue 号前不得开始代码修复
- PR body 必须包含 `Closes #<issue-number>`，合并后 Issue 自动关闭

## 4. 四层防护机制

防止错误管道本身成为问题来源。

### 4.1 总量熔断

单阶段错误数量 >= 10 条时，判定为系统级故障，只发送通知不触发修复。
避免在基础设施大面积故障时产生大量无意义的 Issue 和 PR。

### 4.2 每小时限流

每小时最多触发 1 次 webhook + 1 次飞书通知。
通过 HOUR_FILE 标记实现，标记先于发送写入，确保即使发送失败也不重复触发。

### 4.3 重试熔断

同一错误指纹修复 3 次后问题仍未解决时，停止自动 webhook 触发，转为通知人工介入。
防止 Agent 反复尝试无效修复导致的资源浪费。

### 4.4 指纹过期

错误指纹 24 小时后自动清除，允许相同错误重新触发管道。
避免一次性屏蔽导致真正的回归被忽略。

## 5. 飞书通知双通道

通知系统有两个通道，确保在任何环境下都能送达。

| 优先级 | 方式 | 认证方式 | 适用场景 |
|--------|------|---------|---------|
| 主通道 | `droid exec` 调 lark skill | Factory 进程内认证 | 正常环境，Factory 进程可用 |
| 降级通道 | `lark-cli` 直连 | 文件认证（需 keychain-downgrade） | cron 环境，macOS Keychain 不可访问 |

### 5.1 降级原因

cron 环境下 macOS Keychain 不可访问，lark-cli 会报 `keychain not initialized`。
解决方案：
1. `lark-cli config keychain-downgrade` 切换到文件认证
2. 或用 `droid exec` 调 lark skill 走 Factory 进程认证

### 5.2 Webhook 自愈

webhook server (adnanh/webhook, port 5555) 挂了时：
- 每小时 cron 检测 TCP 5555 → `nohup` 自动拉起
- 每天 audit 检测 → 拉起 + 飞书通知结果
- 即使 webhook 挂了，错误通知不丢（有 lark-cli 降级通道）

## 6. Issue 与 PR 规范

### 6.1 Issue 模板

```markdown
## 错误摘要
- **错误类型**: `<error_type>`
- **失败方法**: `<method>`
- **失败事件**: `<failed_event>`
- **出现次数**: <count>
- **最后出现**: <last_seen>
- **错误指纹**: `<fingerprint>`

## 自动修复
此 Issue 由 PostHog 错误管道自动创建。Droid 将自动定位代码并修复。
```

### 6.2 PR 规范

- 分支命名：`fix/posthog-<error_type>-<timestamp>`
- Commit 消息：中文，包含根因和修复描述
- PR body 必须包含 `Closes #<issue-number>`
- 所有 Issue comment 必须使用中文

## 7. 参考文档

| 文档 | 路径 | 说明 |
|------|------|------|
| error-gateway skill | ~/.factory/skills/error-gateway/SKILL.md | 完整的自动修复流程 |
| 5 来源错误监控体系 | ~/.memory/global-kb/operations/error-monitoring-system.md | 监控体系详细说明 |
| 公开可观测性文档 | docs/guides/observability-and-error-tracking.md | 面向外部的脱敏概述 |
| 全局知识库通用模式 | ~/.memory/global-kb/engineering/error-gateway-pattern.md | 可复用的架构模式 |
