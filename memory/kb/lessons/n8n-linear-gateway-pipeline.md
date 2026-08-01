# n8n Linear Gateway 管线：3 个基础设施陷阱

> Type: [KB:LESSON]
> Title: n8n Linear→Droid 管线基础设施陷阱（payload 嵌套 / op daemon 挂起 / dedup）
> Status: active
> Created: 2026-08-02
> Source: local-canonical
> Confidence: high
> Tags: [lesson, n8n, linear, webhook, launchd, 1password, dedup, trigger-droid]
> Related: [webhook-session-routing, linear-factory-integration]

## 问题

水车（Linear → n8n → Mac webhook → Droid）验证时发现 3 个基础设施问题，逐一导致管线失败。

## 陷阱 1: n8n Code 节点 payload 嵌套

### 症状

n8n HTTP Request 节点向 Mac:5555 发送空 `{}` body，trigger-droid.sh 收不到任何参数。

### 根因

Linear webhook 的 payload 在 n8n 中被嵌套在 `input.body.*` 下，而非顶层 `input.*`。"Build JSON Body" Code 节点访问 `input.action` 得到 `undefined`。

### 解决

Code 节点改为访问 `input.body.action`、`input.body.type`、`input.body.data`。

### 教训

n8n Webhook 节点的 payload 结构取决于节点类型。Webhook trigger 节点将原始 body 嵌套在 `body` 字段下。不要假设字段在顶层。

## 陷阱 2: 1Password `op` CLI 在 launchd daemon 中挂起

### 症状

trigger-droid.sh 通过 `op item get` 获取 LINEAR_API_KEY 时永久挂起，droid exec 永不启动。

### 根因

launchd 后台进程没有 TTY 和完整的 session 环境，`op` CLI 需要 account 解锁或交互式认证，在无 TTY 的 daemon 上下文中挂起。

### 解决

创建 `~/.factory/webhook/.linear-api-key`（chmod 600）存储 key，trigger-droid.sh 增加 file-based fallback：

```bash
if [ -z "$LINEAR_API_KEY" ]; then
    KEY_FILE="${WEBHOOK_BASE}/.linear-api-key"
    [ -f "$KEY_FILE" ] && LINEAR_API_KEY=$(cat "$KEY_FILE" 2>/dev/null || true)
fi
```

### 教训

**不要在 launchd/cron/daemon 上下文调用 `op` CLI。** 这些环境没有 TTY 和完整 session。敏感凭证应通过文件（chmod 600）或环境变量传递，不依赖交互式工具。

## 陷阱 3: Issue.create + Issue.update 触发重复 droid exec

### 症状

一个 Linear issue 创建后，Droid 被启动两次（约 2 秒间隔），浪费资源且可能导致冲突。

### 根因

Linear 对同一 issue 的创建操作会触发两个事件：`Issue.create` 和 `Issue.update`（Linear 内部在创建后立即更新一些字段如 sortOrder）。两个事件都通过 webhook 到达 n8n → Mac → trigger-droid.sh，各启动一个 droid exec。

### 解决

trigger-droid.sh 增加 5 分钟 dedup lock：

```bash
LOCK_DIR="${WEBHOOK_BASE}/locks"
LOCK_FILE="${LOCK_DIR}/l2d-${ISSUE_REF}.lock"
mkdir -p "$LOCK_DIR"
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0) ))
    [ "$LOCK_AGE" -lt 300 ] && exit 0  # skip duplicate
fi
touch "$LOCK_FILE"
```

### 教训

**Linear webhook 对同一动作可能触发多个事件。** Issue.create 总是伴随 Issue.update。消费端必须做幂等/dedup 处理，不能假设"一个动作 = 一个事件"。

## 修复文件

- n8n database (node-22): workflow `zV3mKyKEI04AanmI` Code 节点 + HTTP Request responseFormat
- `~/.factory/webhook/scripts/trigger-droid.sh`: file-based API key fallback + dedup lock
- `~/.factory/webhook/.linear-api-key`: 新建（chmod 600）

## 验证

全链路测试（VAL-L2D-005 至 VAL-L2D-009）全部 PASS。Issue 触发 → 单次 droid exec → Linear comment 回写成功。
