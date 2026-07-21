# APISIX 网关维护手册

> 最后更新：2026-05-31
> 服务器：apisix-gw-test-01 (192.168.88.11)
> 用途：面向运维人员的快速查阅手册，"忘了上次怎么修的"场景，打开即查、复制即跑。

---

## 1. 架构概览

### 1.1 服务器信息

| 项目 | 值 |
|------|-----|
| SSH 别名 | `apisix-gw-test-01` |
| IP | `192.168.88.11` |
| SSH 用户 | `ubuntu` |
| OS | Ubuntu 22.04 LTS |

### 1.2 Docker Compose 位置

```
/opt/apisix-gw-test-01/docker-compose.yml
```

### 1.3 关键端口

| 端口 | 协议 | 用途 |
|------|------|------|
| 9080 | HTTP | APISIX 数据面（代理流量入口） |
| 9180 | HTTP | APISIX Admin API（配置管理） |
| 80   | HTTP | 外部 HTTP 入口（部分路由直连） |

### 1.4 etcd 信息

APISIX 使用 etcd 作为配置存储。etcd 和 APISIX 在同一 Docker Compose 中运行。

```bash
# 查看 etcd 容器状态
ssh apisix-gw-test-01
docker ps | grep etcd

# 查看 etcd 数据目录（docker-compose.yml 中定义的 volume）
docker inspect apisix-etcd | grep -A 5 Mounts
```

etcd 连接地址（APISIX 侧）：`http://etcd:2379`（Docker 内部网络）

---

## 2. 路由速查表

### 2.1 HTTP 路由

| 外部路径 | 路由 ID | 认证方式 | 后端服务 | 备注 |
|----------|---------|----------|----------|------|
| `/mcp/1password/*` | `mcp-1password` | Consumer (key-auth) | supergateway:8000 | 最高频故障点，详见 §4.1 |
| `/mcp/showdoc/*` | `mcp-showdoc` | Consumer (key-auth) | ShowDoc MCP Proxy | 直连 8001，不走 APISIX |
| `/showdoc/*` | `showdoc-route` | 无 | ShowDoc Web | APISIX 反代 ShowDoc |
| `/n8n/*` | `n8n-route` | 无 | n8n :5678 | 自动化工作流 |
| `/webhook/*` | `webhook-route` | 无 | n8n webhook receiver | 接收 GitLab/CI 事件 |
| `/gateway-admin/*` | `gateway-admin-route` | Consumer (key-auth) | gateway-admin 服务 | 网关管理接口 |

### 2.2 TCP 路由

| 外部端口 | 路由 ID | 后端地址 | 白名单 | 备注 |
|----------|---------|----------|--------|------|
| 3306 | `stream-mysql` | 192.168.88.17:3306 | IP 白名单 (ip-restriction) | MySQL |
| 5432 | `stream-pgsql` | 192.168.88.16:5432 | IP 白名单 (ip-restriction) | PostgreSQL |

### 2.3 直连服务

| 服务名 | 端口 | 说明 |
|--------|------|------|
| showdoc-mcp-proxy | 8001 | 不走 APISIX，直连访问 |

---

## 3. 常用操作命令

### 3.1 重启 APISIX

```bash
ssh apisix-gw-test-01
cd /opt/apisix-gw-test-01 && docker compose restart
```

> 如果需要重建容器（配置变更）：
> ```bash
> cd /opt/apisix-gw-test-01 && docker compose up -d --force-recreate
> ```

### 3.2 查看 APISIX 日志

```bash
# 最近 100 行
docker logs --tail 100 apisix-gw-test-01

# 实时跟踪
docker logs -f apisix-gw-test-01

# 查看 etcd 日志
docker logs --tail 50 etcd
```

### 3.3 查看 etcd 数据（通过 Admin API）

```bash
# 先 SSH 到服务器
ssh apisix-gw-test-01

# 获取 admin_key（从 config.yaml 或 1Password 查 APISIX_ADMIN_KEY）
ADMIN_KEY="your_admin_key_here"

# 列出所有路由
curl http://127.0.0.1:9180/apisix/admin/routes \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq .

# 列出所有上游
curl http://127.0.0.1:9180/apisix/admin/upstreams \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq .

# 列出所有消费者
curl http://127.0.0.1:9180/apisix/admin/consumers \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq .
```

### 3.4 添加 / 修改路由（模板命令）

```bash
# 创建或更新路由（PUT 是幂等的，不存在则创建，存在则更新）
curl -X PUT http://127.0.0.1:9180/apisix/admin/routes/{route_id} \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "uri": "/your/path/*",
    "name": "your-route-name",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "backend-service-host:port": 1
      }
    },
    "plugins": {}
  }'
```

### 3.5 查看 Docker 网络连通性

```bash
# 列出所有 Docker 网络
docker network ls

# 查看特定网络详情
docker network inspect apisix-gw-test-01_default

# 查看容器在哪些网络中
docker inspect <容器名> | jq '.[0].NetworkSettings.Networks'
```

### 3.6 从 1Password 获取 APISIX Admin Key

```bash
# 如果本地有 1Password CLI
op item get "APISIX" --fields label=admin_key

# 或手动到 1Password 搜索 APISIX_ADMIN_KEY
```

---

## 4. MCP 服务专项维护

### 4.1 1Password MCP（最高频故障）

#### 架构

```
Droid Client
  → APISIX /mcp/1password (9080)
    → supergateway:8000
      → op-connect-api:8080
```

#### Docker Compose 位置

```
/opt/1panel/mcp/1password-connect/docker-compose.yml
```

#### 关键配置项

| 变量 | 值 | 说明 |
|------|-----|------|
| `OUTPUT_TRANSPORT` | `streamableHttp` | 必须为此值，不能是 `sse` |
| `OP_CONNECT_HOST` | `http://op-connect-api:8080` | MCP 容器连接 Connect API 的地址 |

#### 网络要求

MCP 容器必须同时在 **3 个网络**中：

| 网络 | 用途 |
|------|------|
| `apisix-gw-test-01_default` | 让 APISIX 能访问 supergateway |
| `1panel-network` | 1Panel 管理网络 |
| `1password-connect_default` | 让 supergateway 能访问 op-connect-api |

#### 诊断流程

**步骤 1：检查容器状态**

```bash
ssh apisix-gw-test-01
docker ps | grep 1password
```

预期输出：`1password-connect-mcp` 和 `op-connect-api` 都在 Up 状态。

**步骤 2：检查连通性**

```bash
curl -s -w "\nHTTP:%{http_code}" http://192.168.88.11:9080/mcp/1password
```

- 返回 `200` → 正常
- 返回 `404` → 故障 A（见下方）
- 超时 → 故障 B 或网络问题

**步骤 3：检查容器日志**

```bash
docker logs --tail 50 1password-connect-mcp
```

关注：启动错误、连接拒绝、Accept 头错误等。

**步骤 4：检查网络配置**

```bash
docker inspect 1password-connect-mcp | grep -A 20 Networks
```

确认输出中包含 `apisix-gw-test-01_default`、`1panel-network`、`1password-connect_default` 三个网络。

#### 常见故障及修复

---

**故障 A：返回 404 "Cannot POST"**

- **根因**：`OUTPUT_TRANSPORT` 设为 `sse`，但客户端使用 Streamable HTTP 协议
- **修复**：

```bash
ssh apisix-gw-test-01

# 编辑 .env 文件
vi /opt/1panel/mcp/1password-connect/.env
# 确保 OUTPUT_TRANSPORT=streamableHttp

# 重建容器
cd /opt/1panel/mcp/1password-connect && docker compose up -d --force-recreate
```

---

**故障 B：连接超时 / 无法访问 1Password Connect API**

- **根因**：MCP 容器和 op-connect-api 不在同一个 Docker 网络
- **修复**：

```bash
ssh apisix-gw-test-01

# 编辑 docker-compose.yml
vi /opt/1panel/mcp/1password-connect/docker-compose.yml
```

在 MCP 服务 (supergateway) 的网络配置中加入：

```yaml
services:
  supergateway:
    # ... 其他配置 ...
    networks:
      - apisix-gw-test-01_default
      - 1panel-network
      - 1password-connect_default    # ← 确保这一行存在
```

确保环境变量正确：

```
OP_CONNECT_HOST=http://op-connect-api:8080
```

然后重建：

```bash
cd /opt/1panel/mcp/1password-connect && docker compose up -d --force-recreate
```

---

**故障 C：supergateway 报 Accept 头错误**

- **根因**：supergateway 要求 `Accept: application/json, text/event-stream` 头，但 APISIX 未传递
- **修复**：在 APISIX 路由中添加 `proxy-rewrite` 插件注入 Accept 头

```bash
ssh apisix-gw-test-01
export ADMIN_KEY="your_admin_key_here"

# 更新 mcp-1password 路由，添加 proxy-rewrite 插件
curl -X PUT http://127.0.0.1:9180/apisix/admin/routes/mcp-1password \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "uri": "/mcp/1password/*",
    "name": "mcp-1password",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "192.168.88.11:9000": 1
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "headers": {
          "Accept": "application/json, text/event-stream"
        }
      }
    }
  }'
```

### 4.2 ShowDoc MCP

| 项目 | 值 |
|------|-----|
| 访问方式 | 直连 `192.168.88.11:8001` |
| 是否经过 APISIX | 否 |
| 容器名 | `showdoc-mcp-proxy` |

```bash
# 检查容器状态
ssh apisix-gw-test-01
docker ps | grep showdoc-mcp-proxy

# 测试连通性
curl -s http://192.168.88.11:8001/health

# 查看日志
docker logs --tail 50 showdoc-mcp-proxy
```

### 4.3 ShowDoc 本体

| 项目 | 值 |
|------|-----|
| APISIX 路由 | `/showdoc/*` → ShowDoc 容器 |
| 路由 ID | `showdoc-route` |

```bash
# 检查 ShowDoc 容器
ssh apisix-gw-test-01
docker ps | grep showdoc

# 查看路由配置
curl http://127.0.0.1:9180/apisix/admin/routes/showdoc-route \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq .
```

---

## 5. 网络拓扑图

### 5.1 Docker 网络概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          apisix-gw-test-01 主机                              │
│                                                                             │
│  ┌─ apisix-gw-test-01_default (172.18.0.0/16) ──────────────────────────┐  │
│  │                                                                      │  │
│  │  apisix-gw-test-01 (APISIX)  ◄────────► supergateway (1Password MCP) │  │
│  │  etcd                                                                │  │
│  │  showdoc                                                             │  │
│  │  showdoc-mcp-proxy                                                   │  │
│  │  n8n                                                                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─ 1panel-network (172.20.0.0/16) ─────────────────────────────────────┐  │
│  │                                                                      │  │
│  │  supergateway (1Password MCP)                                        │  │
│  │  1Panel 管理容器                                                     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─ 1password-connect_default (172.19.0.0/16) ──────────────────────────┐  │
│  │                                                                      │  │
│  │  supergateway (1Password MCP) ◄── OP_CONNECT_HOST ──► op-connect-api │  │
│  │  op-connect-api                                                      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

外部流量流向:

Client ──HTTP──► 192.168.88.11:9080 (APISIX)
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              /mcp/1password  /showdoc/*   /n8n/*
                    ▼             ▼             ▼
            supergateway     ShowDoc        n8n
            :8000            container      :5678
                │
                ▼ (1password-connect_default)
            op-connect-api
            :8080

TCP 代理:
Client ──TCP:3306──► APISIX Stream ──► 192.168.88.17:3306 (MySQL)
Client ──TCP:5432──► APISIX Stream ──► 192.168.88.16:5432 (PostgreSQL)
```

### 5.2 容器网络归属表

| 容器 | apisix-gw-test-01_default | 1panel-network | 1password-connect_default |
|------|:-------------------------:|:--------------:|:-------------------------:|
| apisix-gw-test-01 | ✅ | — | — |
| etcd | ✅ | — | — |
| supergateway (1Password MCP) | ✅ | ✅ | ✅ |
| op-connect-api | — | — | ✅ |
| showdoc | ✅ | — | — |
| showdoc-mcp-proxy | ✅ | — | — |
| n8n | ✅ | — | — |

---

## 6. Admin API 参考速查

### 6.1 基础信息

| 项目 | 值 |
|------|-----|
| Base URL | `http://127.0.0.1:9180/apisix/admin` |
| 认证 Header | `X-API-KEY: <admin_key>` |
| Admin Key 来源 | config.yaml 或 1Password 查 `APISIX_ADMIN_KEY` |

### 6.2 常用端点

| 操作 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 列出路由 | `GET` | `/routes` | 返回所有路由列表 |
| 查看路由详情 | `GET` | `/routes/{id}` | 查看指定路由配置 |
| 创建路由 | `PUT` | `/routes/{id}` | 创建或更新（幂等） |
| 删除路由 | `DELETE` | `/routes/{id}` | 删除指定路由 |
| 列出上游 | `GET` | `/upstreams` | 返回所有上游列表 |
| 查看上游 | `GET` | `/upstreams/{id}` | 查看指定上游 |
| 列出消费者 | `GET` | `/consumers` | 返回所有认证用户 |
| 查看消费者 | `GET` | `/consumers/{username}` | 查看指定消费者 |
| 列出 SSL 证书 | `GET` | `/ssl` | 返回所有 SSL 证书 |
| 列出全局插件 | `GET` | `/global_rules` | 返回全局插件规则 |
| 列出 Stream 路由 | `GET` | `/stream_routes` | TCP/UDP 路由 |

### 6.3 命令模板

```bash
# 通用变量
ADMIN_KEY="your_admin_key_here"
BASE="http://127.0.0.1:9180/apisix/admin"

# 列出所有路由
curl ${BASE}/routes -H "X-API-KEY: ${ADMIN_KEY}" | jq .

# 查看指定路由
curl ${BASE}/routes/mcp-1password -H "X-API-KEY: ${ADMIN_KEY}" | jq .

# 创建/更新路由
curl -X PUT ${BASE}/routes/my-route \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"uri": "/test/*", "upstream": {"type": "roundrobin", "nodes": {"127.0.0.1:8080": 1}}}'

# 删除路由
curl -X DELETE ${BASE}/routes/my-route -H "X-API-KEY: ${ADMIN_KEY}"

# 列出所有上游
curl ${BASE}/upstreams -H "X-API-KEY: ${ADMIN_KEY}" | jq .

# 列出所有消费者
curl ${BASE}/consumers -H "X-API-KEY: ${ADMIN_KEY}" | jq .

# 列出 SSL 证书
curl ${BASE}/ssl -H "X-API-KEY: ${ADMIN_KEY}" | jq .
```

---

## 7. TCP 代理维护

### 7.1 路由配置

| 服务 | APISIX 端口 | 后端地址 | 协议 |
|------|------------|----------|------|
| MySQL | 3306 | 192.168.88.17:3306 | TCP |
| PostgreSQL | 5432 | 192.168.88.16:5432 | TCP |

### 7.2 查看 Stream 路由

```bash
ssh apisix-gw-test-01
export ADMIN_KEY="your_admin_key_here"

# 列出所有 TCP/UDP 流路由
curl http://127.0.0.1:9180/apisix/admin/stream_routes \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq .
```

### 7.3 IP 白名单管理

IP 白名单配置在 stream 路由的 `ip-restriction` 插件中。

```bash
# 查看 MySQL stream 路由（含白名单配置）
curl http://127.0.0.1:9180/apisix/admin/stream_routes/stream-mysql \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq '.plugins.ip-restriction'
```

**添加 IP 到白名单**：

```bash
curl -X PUT http://127.0.0.1:9180/apisix/admin/stream_routes/stream-mysql \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "remote_addr": "0.0.0.0",
    "remote_port": 0,
    "upstream": {
      "host": "192.168.88.17",
      "port": 3306
    },
    "plugins": {
      "ip-restriction": {
        "whitelist": [
          "192.168.88.0/24",
          "10.0.0.5",
          "新增的IP地址"
        ]
      }
    }
  }'
```

### 7.4 TCP 连通性测试

```bash
# 测试 MySQL 连通性
nc -zv 192.168.88.11 3306

# 测试 PostgreSQL 连通性
nc -zv 192.168.88.11 5432

# 直接测试后端（绕过 APISIX）
nc -zv 192.168.88.17 3306
nc -zv 192.168.88.16 5432
```

---

## 8. 故障排查清单

### 通用排查步骤（按顺序执行）

#### 步骤 1：SSH 能连吗？

```bash
ssh ubuntu@192.168.88.11
# 或
ssh apisix-gw-test-01
```

- ✅ 能连 → 继续步骤 2
- ❌ 连不上 → 检查网络、VPN、服务器是否在线

#### 步骤 2：Docker 容器在运行吗？

```bash
docker ps
```

- 预期输出：`apisix-gw-test-01`、`etcd` 等容器状态为 `Up`
- 如果容器不在了：

```bash
# 查看所有容器（包括已停止的）
docker ps -a

# 重启
cd /opt/apisix-gw-test-01 && docker compose up -d
```

#### 步骤 3：网络连通吗？

```bash
# 测试后端服务可达性
curl -s -o /dev/null -w "%{http_code}" http://<后端IP>:<端口>/health

# 测试 Docker 网络
docker exec apisix-gw-test-01 ping -c 2 <后端容器名>

# 测试容器间 DNS 解析
docker exec apisix-gw-test-01 nslookup <后端容器名>
```

#### 步骤 4：APISIX 路由存在吗？

```bash
export ADMIN_KEY="your_admin_key_here"

# 列出所有路由
curl http://127.0.0.1:9180/apisix/admin/routes \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq '.node.nodes[] | {id: .value.id, uri: .value.uri}'

# 查看指定路由
curl http://127.0.0.1:9180/apisix/admin/routes/<route-id> \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq .
```

- 路由不存在 → 需要创建（参考 §6.3 模板）
- 路由存在但配置错误 → 参考 §6.3 更新

#### 步骤 5：后端服务健康吗？

```bash
# 1Password Connect API
curl http://op-connect-api:8080/health

# ShowDoc
curl http://<showdoc-container>:<port>/

# n8n
curl http://<n8n-container>:5678/healthz

# 通用端口测试
nc -zv <IP> <端口>
```

#### 步骤 6：日志有什么线索？

```bash
# APISIX 主日志
docker logs --tail 100 apisix-gw-test-01

# etcd 日志
docker logs --tail 50 etcd

# 特定服务日志
docker logs --tail 50 1password-connect-mcp
docker logs --tail 50 showdoc-mcp-proxy
docker logs --tail 50 n8n

# 实时跟踪（调试用）
docker logs -f apisix-gw-test-01 2>&1 | grep -i "error\|warn\|fail"
```

### 常见症状 → 可能原因速查

| 症状 | 可能原因 | 跳转 |
|------|----------|------|
| 1Password MCP 返回 404 | `OUTPUT_TRANSPORT` 配置错误 | §4.1 故障 A |
| 1Password MCP 连接超时 | Docker 网络不通 | §4.1 故障 B |
| supergateway Accept 头错误 | 缺少 proxy-rewrite 插件 | §4.1 故障 C |
| TCP 连接被拒绝 | IP 不在白名单 | §7.3 |
| 路由 404 | 路由未创建或 URI 不匹配 | §6 |
| 502 Bad Gateway | 后端服务不可达 | §8 步骤 5 |
| 容器反复重启 | 配置错误 / 资源不足 | §8 步骤 2 + 日志 |
| etcd 连接失败 | etcd 容器未运行 | §8 步骤 2 |

---

> **附录：快速命令合集（一键复制用）**
>
> ```bash
> # 一键健康检查
> ssh apisix-gw-test-01 bash -c '
>   echo "=== Docker 容器状态 ==="
>   docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
>   echo ""
>   echo "=== Docker 网络 ==="
>   docker network ls
>   echo ""
>   echo "=== APISIX Admin API 可达性 ==="
>   curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:9180/apisix/admin/routes
>   echo ""
>   echo "=== 1Password MCP 连通性 ==="
>   curl -s -w "\nHTTP %{http_code}\n" http://192.168.88.11:9080/mcp/1password
> '
> ```
