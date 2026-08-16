# 基础设施监控从代码仓库剥离

> Date: 2026-08-14
> Status: accepted
> Tags: [decision, infrastructure, evolution-scanner, boundary, daily-audit]
> Related: [2026-08-13-inventory-decommission-sync, D-012-evolution-capability-tech-debt]

## 背景

memory-core evolution scanner 包含一个 `daily_audit` 工具，会对 `~/.memory-core/infrastructure-inventory.yaml` 中列出的服务器执行基础设施检查（SSH 探测、TCP 端口检查、Docker 容器验证）。这导致了以下边界违规：

1. **基础设施 finding 污染代码仓库** —— CONTAINER_DOWN、SERVER_SSH_UNREACHABLE 等基础设施 finding 在代码仓库（hdot123/memory）中创建 GitHub issue，将基础设施运维与代码开发混为一谈
2. **幽灵条目导致持续误报** —— `openclaw` 容器（从未安装）被列在 inventory 中，导致持续产生 CONTAINER_DOWN critical 误报
3. **排除配置不可项目化** —— scanner 的 `ISSUE_EXCLUDED_CATEGORIES` 是硬编码全局常量，无法按项目配置

详见教训记录：`lessons/2026-08-13-inventory-decommission-sync.md`。

## 决策

1. **memory-core 不再做基础设施监控** —— `.evolution/config.yml` 的 daily_audit 命令改为 `memory-audit-daily --json --no-infra`
2. **删除 `~/.memory-core/infrastructure-inventory.yaml`** —— 不再需要
3. **不创建独立的基础设施 repo（yuanzu）** —— 评估后认为 `--no-infra` 已从源头切断问题，不需要第二个 repo
4. **基础设施问题走现有渠道** —— PostHog error gateway、手动 Linear，不需要自动化 scanner

## 备选方案

| 方案 | 评估 | 结论 |
|------|------|------|
| 创建 yuanzu repo 接管基础设施扫描 | 已实施后评估为过度设计 | 已删除——`--no-infra` 从源头消除了需求 |
| 保留 scanner 但做项目级排除配置 | 让 `ISSUE_EXCLUDED_CATEGORIES` 可配置 | 过于复杂，不如直接 `--no-infra` |
| 保留 inventory 文件但不创建 issue | PR #611 已实现此方案 | scanner 仍白跑 SSH/TCP 探测，浪费资源 |

## 影响

- memory-core scanner 每 30 分钟不再做任何基础设施检查
- `daily_audit` 仍跑项目记忆巡检（知识库审计），只是跳过 infra 部分
- `ISSUE_EXCLUDED_CATEGORIES` 中保留 `daily_audit` 作为防御性配置，实际不会再触发
- scanner `ISSUE_EXCLUDED_CATEGORIES` 仍为硬编码全局常量，未来如有新项目可能需要改为配置化

## 相关 PR

- PR #611：scanner 排除 daily_audit 类 finding 避免 GitHub issue 误报（INFRA-265）
- PR #613：P1-2 硬退出排除 daily_audit 避免纯基础设施 tick 误报（INFRA-268）
- PR #615：`.evolution/config.yml` 的 daily_audit 命令加 `--no-infra` flag

## Truth Basis

### Source Refs

- `.evolution/config.yml`（当前版本，daily_audit 命令含 `--no-infra`）
- `scripts/evolution_scanner.py`（`ISSUE_EXCLUDED_CATEGORIES` 定义于第 42-43 行）

### Authority Refs

- `memory_core/tools/daily_kb_audit.py`（`--no-infra` flag 实现）

### Evidence Refs

- PR #611、#613、#615 均已合并
- `~/.memory-core/infrastructure-inventory.yaml` 已删除
- PostHog `linear_webhook_failure` 事件：8/11 峰值 3905 次 → 8/14 降为零

### Conflict Status

- resolved
