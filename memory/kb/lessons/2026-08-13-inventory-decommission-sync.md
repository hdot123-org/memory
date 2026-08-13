> Date: 2026-08-13
> Source: INFRA-265 CONTAINER_DOWN openclaw 误报分析
> Tags: [lesson, infrastructure-inventory, evolution-scanner, false-positive, decommission]
> Related: [2026-08-13-drift-convergence-baseline]

## 核心教训：下线服务时必须同步更新 infrastructure-inventory.yaml

服务容器下线后，如果不在 `~/.memory-core/infrastructure-inventory.yaml` 中同步移除，
daily_kb_audit 会持续产生 CONTAINER_DOWN critical 误报。

## 事件经过

### 发现

evolution scanner 在 2026-08-09 ~ 2026-08-13 期间多次产生 CONTAINER_DOWN finding：

- **Rule ID**: CONTAINER_DOWN
- **Location**: node-00/openclaw
- **Severity**: critical
- **Description**: 期望容器未运行：openclaw

### 根因

`openclaw` 容器已从 node-00 完全退役——`docker ps -a` 显示该容器不存在（连停止状态都没有）。
但 infrastructure-inventory.yaml 仍将其列为 node-00 的期望容器，导致每次 SSH 成功时都产生误报。

### 为什么是间歇性的

该 finding 不是每次扫描都出现，原因是 daily_kb_audit 的容器检查逻辑：

- SSH 成功 → 对比期望列表 → 发现 openclaw 缺失 → **CONTAINER_DOWN critical**
- SSH 失败 → 静默跳过容器检查 → **0 findings**（不报 SSH 失败）

SSH 到 node-00 的连接不稳定，导致 finding 时有时无，增加了诊断难度。

## 修复

从 `~/.memory-core/infrastructure-inventory.yaml` 的 node-00 `docker_containers` 列表中移除 openclaw。

修复后验证：

```bash
# node-00 实际运行容器
$ ssh node-00 'docker ps --format "{{.Names}}"'
promtail, node_exporter, cadvisor, ecxf-exam, wg-youzy, caddy,
youzy-redis, tinyproxy-upstream, tinyproxy, tailscale-derp

# openclaw 不存在于任何状态
$ ssh node-00 'docker ps -a --filter "name=openclaw"'
(empty)
```

## 教训

1. **下线服务 = 更新清单** —— 任何容器/服务下线时，必须同步更新 infrastructure-inventory.yaml，否则会产生持续的 critical 误报
2. **清单是 single source of truth** —— daily_kb_audit 完全依赖 inventory YAML 的声明式期望，不做任何推断；清单过时 = 误报
3. **间歇性 finding 要查 SSH 稳定性** —— CONTAINER_DOWN 时有时无，首要排查 SSH 连接稳定性，而非容器本身
4. **SSH 失败静默跳过是设计缺陷** —— 当前逻辑 SSH 失败时容器检查被静默跳过（0 findings 而非报 SSH 故障），这会掩盖真实的连接问题

## 改进建议

- **短期**：运维 SOP 中增加"服务下线检查清单"，包含更新 infrastructure-inventory.yaml 步骤
- **中期**：daily_kb_audit 增加 SSH 失败告警（SERVER_SSH_UNREACHABLE），避免静默跳过掩盖问题
- **长期**：考虑 inventory 文件版本化管理，与实际部署状态自动对账

## Truth Basis

### Source Refs

- `~/.memory-core/infrastructure-inventory.yaml`（node-00 docker_containers 列表）
- Linear INFRA-265：CONTAINER_DOWN openclaw
- `.evolution/findings_over_time.json`（2026-08-09 ~ 2026-08-13 间歇性 CONTAINER_DOWN 记录）

### Authority Refs

- `memory_core/tools/daily_kb_audit.py`（`_check_server_docker()` 容器检查逻辑）
- `scripts/evolution_adapters.py`（`adapt_daily_audit()` finding 转换）

### Evidence Refs

- `ssh node-00 'docker ps -a --filter "name=openclaw"'` → 空（容器不存在）
- `.evolution/heartbeat.json`（findings_count 在 0 和非 0 之间波动）

### Conflict Status

- resolved
