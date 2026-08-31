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

> **pr_number=0 根因说明（2026-08-23 更正）**: 此前日志中出现的 `pr_number=0` 通知，根因是 ci.yml 中 `${{ github.event.pull_request.number || 0 }}` 表达式在 main 分支 push 事件时构造出 `pr_number=0`（push 事件无 pull_request 对象），**并非 n8n 传参问题**。修复方案：notify-ci-complete job 的 `if` 条件从 `always()` 改为 `always() && github.event_name == 'pull_request'`，从源头杜绝 main push 触发通知。

> **200→^2 修复记录（2026-08-22）**: trigger-ci-droid.sh 成功判定从字面 HTTP 200 收窄为 `^2` 正则（481/496 行两处同步），202 等 2xx 成功响应不再被误判失败。
>
> **误判失败机制（2026-08-23 补充，INFRA-520）**: Factory Sessions API 对注入请求可能返回 `202 Accepted`（异步接受，消息已入队）。旧判定 `[ "$HTTP_CODE" = "200" ]` 下，202 既不命中重试循环的成功 break 条件，也不命中 5xx/000 重试条件，循环不等待直接空转，耗尽 `MAX_RETRIES=3` 次尝试后进入最终检查；最终 `if [ "$HTTP_CODE" = "200" ]` 同样失败，落入 `ERROR: API call failed` 分支并上报 `ci_inject_failed` PostHog 事件——注入实际已成功，却记录为失败。修复后两处判定均为 `[[ "$HTTP_CODE" =~ ^2 ]]`，覆盖全部 2xx 成功响应，与 4xx break / 5xx 退避重试的分诊语义对齐。受管副本（自 M5 起单一所有权源为 infra-core 仓 `webhook-scripts/trigger-ci-droid.sh`；PR #973 回填）与生产脚本 `~/.factory/webhook/scripts/trigger-ci-droid.sh` 保持同步。

> **会话探活与锁语义硬化（2026-08-23，INFRA-521）**: M3 里程碑将 TD-WEBHOOK-03 技术债（`write-pending-ci.sh` 写入时不验活、不选最新 session，历史 77 次注入 404 丢失）修复为四层 fail-fast 语义并回填至仓库（PR #978）：
>
> 1. **写入前探活** — 选定 session 后先 `GET /api/v0/sessions/{id}`，显式 SESSION_ID 探活 404/5xx/无 token 均拒绝写入（`ci_write_probe_fail` PostHog 事件），杜绝写入已知死会话的 pending 文件
> 2. **候选迭代** — sessions-index 候选按 mtime 降序逐个探活，404 顺延下一个；全部候选死则 fail-fast（`ci_write_all_sessions_dead`），不再写入
> 3. **候选筛选** — 仅顶层 mission-session（`callingSessionId` 为空）+ orchestrator role + cwd 匹配入选，worker 子会话与其他仓库会话被过滤
> 4. **原子写入** — tmp+mv 落盘，mv 前校验 JSON 合法性，读端不会看到半写文件；废弃的 mtime 扫描保留为 fallback 并上报 `ci_write_deprecated_scan` 事件
>
> 配套回归测试（M5 起随所有权迁至 infra-core 仓 webhook-scripts 测试族）固化上述语义；受管副本 `webhook-scripts/write-pending-ci.sh` 与生产脚本经 infra-core 仓 `webhook-scripts/sync-webhook-scripts.sh --check` 验证保持同步。

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
              "value": "<N8N_CI_TOKEN_SECRET_VALUE>"
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
| Webhook (GitHub CI) | `n8n-nodes-base.webhook` | 接收 GitHub Actions 的 POST 请求，经 n8n 实例事件入口 `/webhook/events`（路由器模式，返回 `{status,route,event}` JSON）分发，`ci-complete` 为该入口下的路由 |
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
   - 测试 URL: 在 n8n 面板 Webhook 节点中查看（`/webhook-test/` 前缀，仅在 Test workflow 监听期间有效）
   - 生产 URL: 权威来源为 1Password vault sever 条目 n8n / node-22 / Webhook Provider / Secrets 的 `webhook_url` 字段（n8n 实例事件入口为 `/webhook/events`，路由器模式）
4. **`N8N_CI_WEBHOOK_URL` secret 的值须从上述 1Password 条目获取，禁止使用占位符模板**

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
     - Value: 来自 GitHub repository secret `N8N_CI_TOKEN` 的实际值（配置见下方 Step 6）
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

   **注意**: `X-CI-Token` 的实际值来自 GitHub repository secret `N8N_CI_TOKEN`，必须与 Mac 上 `~/.factory/webhook/hooks.json` 中 `ci-complete` hook 的 `trigger-rule` 配置一致。

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
3. 确认 webhook URL 可访问（URL 权威来源：1Password vault sever 条目 n8n / node-22 / Webhook Provider / Secrets 的 `webhook_url` 字段）

### Step 6: 配置 GitHub Secret

1. 进入 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. Name: `N8N_CI_WEBHOOK_URL`
4. Value: n8n 的生产 webhook URL（权威来源：1Password vault sever 条目 n8n / node-22 / Webhook Provider / Secrets 的 `webhook_url` 字段；n8n 实例事件入口为 `/webhook/events`，路由器模式）
5. 保存
6. 再次点击 **New repository secret**
7. Name: `N8N_CI_TOKEN`
8. Value: X-CI-Token 的实际值（与 Mac 上 `~/.factory/webhook/hooks.json` 中 `ci-complete` hook 的 `trigger-rule` 配置一致）
9. 保存

ci.yml 的 notify-ci-complete job 已引用这两个 secret，配置后即可自动工作。

---

## 3. 测试验证

### 3.1 用 curl 模拟 GitHub Actions POST

在任意能访问 n8n 的机器上执行:

```bash
# webhook URL 从 1Password 获取，不使用占位符
N8N_WEBHOOK_URL="<从 1Password vault sever 条目 n8n/node-22/Webhook Provider/Secrets 的 webhook_url 字段获取>"

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
# 使用 n8n 测试 URL（需先在 n8n 面板点击 Test workflow，URL 在 Webhook 节点中查看，
# 前缀为 /webhook-test/，仅在监听期间有效；生产 URL 一律以 1Password 权威源为准）
curl -X POST "<n8n 面板 Webhook 节点中显示的 webhook-test URL>" \
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
| GitHub Actions POST 到 n8n 返回 404 | 确认 `N8N_CI_WEBHOOK_URL` secret 与 1Password `webhook_url` 权威源一致（实例事件入口为 `/webhook/events`，路由器模式）；测试 URL（`/webhook-test/` 前缀）仅在 Test workflow 监听期间有效，不可用于生产 |
| n8n 转发到 Mac:5555 超时 | 确认 Mac 可达（ping/nc），5555 端口开放，adnanh/webhook 正在运行 |
| Mac:5555 拒绝请求 | 检查 HTTP Request 节点的 `X-CI-Token` header 值是否与 `N8N_CI_TOKEN` secret 一致 |
| GitHub Actions notification step 跳过 | 检查 `N8N_CI_WEBHOOK_URL` secret 是否已配置 |
| 日志中出现 "Hook rules were not satisfied" | X-CI-Token 值不匹配或 header 未发送 |

---

## 5. 关键参数速查

| 参数 | 值 | 来源 |
|------|-----|------|
| Mac webhook 端口 | `5555` | adnanh/webhook 启动配置 |
| Mac webhook 路径 | `/hooks/ci-complete` | hooks.json 第 6 个 hook 的 id |
| X-CI-Token | 来自 `N8N_CI_TOKEN` secret | n8n HTTP Request 节点配置（实际值与 hooks.json trigger-rule 一致，非字面量 `CIComplete2026`） |
| GitHub Secret (webhook) | `N8N_CI_WEBHOOK_URL` | ci.yml notify-ci-complete job 引用 |
| GitHub Secret (token) | `N8N_CI_TOKEN` | ci.yml notify-ci-complete job 引用，作为 X-CI-Token header 值发送 |
| Payload 字段 | `repo`, `pr_number`, `branch`, `sha`, `status` | ci.yml notify-ci-complete job 构造（仅 PR 事件触发，main push 不再发送） |
