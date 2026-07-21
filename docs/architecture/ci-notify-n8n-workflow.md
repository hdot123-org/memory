# n8n Workflow 配置文档: CI 完成通知转发

本文档描述如何在 n8n 面板配置一个 workflow，将 GitHub Actions CI 完成通知转发到 Mac:5555 的本地 webhook 服务。

## 架构概述

```
GitHub Actions (ci.yml)
    │
    │  POST {repo, pr_number, branch, sha, status:"passed"}
    ▼
n8n Workflow (Webhook Trigger)
    │
    │  转发 POST + X-CI-Token header
    ▼
Mac:5555 /hooks/ci-complete (adnanh/webhook)
    │
    │  调用 trigger-ci-droid.sh
    ▼
Factory Sessions API → 当前 Droid session
```

n8n 的角色: 接收 GitHub Actions 的 HTTP POST，原样转发到 Mac:5555，并附加 `X-CI-Token` 认证 header。

---

## 1. n8n Workflow JSON 模板

以下 JSON 可直接导入 n8n（Workflows → Import from File）。导入后需根据实际环境修改 `<MAC_IP_OR_HOSTNAME>` 占位符。

```json
{
  "name": "CI Complete → Mac:5555 Forward",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "ci-complete-github",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "webhook-input",
      "name": "Webhook (GitHub CI)",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [240, 300],
      "webhookId": "ci-complete-github"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://<MAC_IP_OR_HOSTNAME>:5555/hooks/ci-complete",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "X-CI-Token",
              "value": "CIComplete2026"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"repo\": \"{{ $json.body.repo }}\",\n  \"pr_number\": {{ $json.body.pr_number }},\n  \"branch\": \"{{ $json.body.branch }}\",\n  \"sha\": \"{{ $json.body.sha }}\",\n  \"status\": \"{{ $json.body.status }}\"\n}",
        "options": {
          "timeout": 10000
        }
      },
      "id": "http-forward",
      "name": "HTTP Request (Forward to Mac:5555)",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [460, 300]
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "={\"status\": \"forwarded\", \"original_status\": \"{{ $json.status }}\"}"
      },
      "id": "respond-webhook",
      "name": "Respond to Webhook",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1,
      "position": [680, 300]
    }
  ],
  "connections": {
    "Webhook (GitHub CI)": {
      "main": [
        [
          {
            "node": "HTTP Request (Forward to Mac:5555)",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "HTTP Request (Forward to Mac:5555)": {
      "main": [
        [
          {
            "node": "Respond to Webhook",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1"
  }
}
```

### 节点说明

| 节点 | 类型 | 职责 |
|------|------|------|
| Webhook (GitHub CI) | `n8n-nodes-base.webhook` | 接收 GitHub Actions 的 POST 请求，路径为 `/webhook/ci-complete-github` |
| HTTP Request (Forward to Mac:5555) | `n8n-nodes-base.httpRequest` | 将 payload 原样转发到 `http://<MAC_IP>:5555/hooks/ci-complete`，附带 `X-CI-Token` header |
| Respond to Webhook | `n8n-nodes-base.respondToWebhook` | 向 GitHub Actions 返回 200 响应 |

---

## 2. 逐步配置说明

### Step 1: 创建 Workflow

1. 登录 n8n 面板
2. 点击 **Workflows** → **Add workflow**
3. 命名为 `CI Complete → Mac:5555 Forward`

或者：点击上方 JSON 模板，选择 **Import from File** 导入，然后修改 `<MAC_IP_OR_HOSTNAME>` 占位符。

### Step 2: 配置 Webhook 输入节点

1. 添加 **Webhook** 节点
2. 配置:
   - **HTTP Method**: `POST`
   - **Path**: `ci-complete-github`
   - **Response Mode**: `Response Node`（需要最后的 Respond to Webhook 节点配合）
3. 保存后 n8n 会生成一个测试 URL 和一个生产 URL:
   - 测试 URL: `https://<n8n-host>/webhook-test/ci-complete-github`
   - 生产 URL: `https://<n8n-host>/webhook/ci-complete-github`
4. **生产 URL 即为 GitHub Actions 需要 POST 的目标地址**

### Step 3: 配置 HTTP Request 输出节点（转发到 Mac:5555）

1. 添加 **HTTP Request** 节点
2. 配置:
   - **Method**: `POST`
   - **URL**: `http://<MAC_IP_OR_HOSTNAME>:5555/hooks/ci-complete`
     - `<MAC_IP_OR_HOSTNAME>` 替换为 Mac 的局域网 IP 或 hostname（例如 `192.168.1.100`）
     - 如果 n8n 和 Mac 在同一网络，使用局域网 IP
     - 如果跨网络，需要端口转发或隧道
   - **Send Headers**: 开启
   - **Header Parameters**:
     - Name: `X-CI-Token`
     - Value: `CIComplete2026`
   - **Send Body**: 开启
   - **Body Content Type**: `JSON`
   - **Specify Body**: 使用表达式，将 Webhook 节点的 body 字段映射过来:
     ```json
     {
       "repo": "{{ $json.body.repo }}",
       "pr_number": {{ $json.body.pr_number }},
       "branch": "{{ $json.body.branch }}",
       "sha": "{{ $json.body.sha }}",
       "status": "{{ $json.body.status }}"
     }
     ```

   **注意**: `X-CI-Token` 的值 `CIComplete2026` 必须与 Mac 上 `~/.factory/webhook/hooks.json` 中 `ci-complete` hook 的 `trigger-rule` 配置一致。

3. 连接: Webhook 节点 → HTTP Request 节点

### Step 4: 配置 Respond to Webhook 节点

1. 添加 **Respond to Webhook** 节点
2. 配置:
   - **Respond With**: `JSON`
   - **Response Body**: `{"status": "forwarded"}`
3. 连接: HTTP Request 节点 → Respond to Webhook 节点

### Step 5: 激活 Workflow

1. 点击右上角 **Save**
2. 切换 **Inactive** → **Active**（生产模式）
3. 确认 webhook URL 可访问: `https://<n8n-host>/webhook/ci-complete-github`

### Step 6: 配置 GitHub Secret

1. 进入 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. Name: `N8N_CI_WEBHOOK_URL`
4. Value: n8n 的生产 webhook URL（即 `https://<n8n-host>/webhook/ci-complete-github`）
5. 保存

ci.yml 的 notification step 已引用 `${{ secrets.N8N_CI_WEBHOOK_URL }}`，配置 secret 后即可自动工作。

---

## 3. 测试验证

### 3.1 用 curl 模拟 GitHub Actions POST

在任意能访问 n8n 的机器上执行:

```bash
# 替换 <n8n-host> 为实际的 n8n 地址
N8N_WEBHOOK_URL="https://<n8n-host>/webhook/ci-complete-github"

# 模拟 GitHub Actions 发送的 payload
curl -v -X POST "$N8N_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "owner/memory",
    "pr_number": 999,
    "branch": "feature/test-n8n",
    "sha": "abc123def456",
    "status": "passed"
  }'
```

### 3.2 验证预期结果

成功时:

1. **n8n 端**:
   - Webhook 节点收到请求，执行历史中出现一条新执行记录
   - HTTP Request 节点成功转发到 Mac:5555
   - Respond to Webhook 返回 `{"status": "forwarded"}`

2. **Mac:5555 端**:
   - 查看 webhook 日志: `~/.factory/webhook/logs/ci-complete-pr999-*.log`
   - 日志应显示:
     - 参数解析: `PR_NUMBER=999 BRANCH=feature/test-n8n SHA=abc123def456 STATUS=passed`
     - `trigger-ci-droid.sh` 被调用（前提是 `pending-ci.json` 存在且 X-CI-Token 正确）

3. **curl 响应**: HTTP 200，body 包含 `{"status": "forwarded"}`

### 3.3 验证 X-CI-Token 转发

确认 n8n 的 HTTP Request 节点确实携带了 `X-CI-Token` header:

```bash
# 在 Mac 上监控 webhook 日志
tail -f ~/.factory/webhook/logs/ci-complete-*
```

如果 n8n 未发送 `X-CI-Token` 或值不匹配，Mac:5555 会拒绝请求（hooks.json 的 trigger-rule 不满足），不会调用脚本。

### 3.4 测试 n8n 测试模式

n8n 提供测试模式（Test workflow），可以:

1. 在 n8n 面板点击 **Test workflow**
2. 在另一个终端用 curl POST 到 webhook-test URL
3. 在 n8n 面板观察数据在各节点间流动
4. 确认 HTTP Request 节点的输出包含正确的转发结果

```bash
# 使用 n8n 测试 URL（需要在 n8n 面板点击 Test workflow 后使用）
curl -X POST "https://<n8n-host>/webhook-test/ci-complete-github" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "owner/memory",
    "pr_number": 999,
    "branch": "feature/test-n8n",
    "sha": "abc123def456",
    "status": "passed"
  }'
```

---

## 4. 故障排查

| 问题 | 排查 |
|------|------|
| GitHub Actions POST 到 n8n 返回 404 | 确认 workflow 已激活（Active 状态），URL 使用 `/webhook/` 而非 `/webhook-test/` |
| n8n 转发到 Mac:5555 超时 | 确认 Mac 可达（ping/nc），5555 端口开放，adnanh/webhook 正在运行 |
| Mac:5555 拒绝请求 | 检查 HTTP Request 节点的 `X-CI-Token` header 是否为 `CIComplete2026` |
| GitHub Actions notification step 跳过 | 检查 `N8N_CI_WEBHOOK_URL` secret 是否已配置 |
| 日志中出现 "Hook rules were not satisfied" | X-CI-Token 值不匹配或 header 未发送 |

---

## 5. 关键参数速查

| 参数 | 值 | 来源 |
|------|-----|------|
| Mac webhook 端口 | `5555` | adnanh/webhook 启动配置 |
| Mac webhook 路径 | `/hooks/ci-complete` | hooks.json 第 6 个 hook 的 id |
| X-CI-Token | `CIComplete2026` | hooks.json ci-complete hook 的 trigger-rule |
| GitHub Secret | `N8N_CI_WEBHOOK_URL` | ci.yml notification step 引用 |
| Payload 字段 | `repo`, `pr_number`, `branch`, `sha`, `status` | ci.yml notification step 构造 |
