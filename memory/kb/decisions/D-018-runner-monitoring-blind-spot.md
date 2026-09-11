# D-018: 自建 Runner 监控盲区——技术债跟踪

> **状态**：技术债（方案已定，待实施）
> **日期**：2026-09-11
> **来源**：runner 历史审计（2026-09-11 会话）+ 官方/社区方案调研

## 背景

GitHub 后台 runner 页面只显示瞬时心跳状态（online/offline/busy），`status=online` 仅代表 runner 进程心跳正常，不代表它在接活。存在三类监控盲区，全部无后台提示：

1. **空转盲区**：runner 显示 online 但长期不接活
2. **消失盲区**：runner 被注销下线，无人知晓
3. **卡死盲区**：run 停在 queued 状态可长达数周，后台显示"排队中"

## 实证（2026-09-11 审计）

拉取 09-03 ~ 09-11 共 1474 个 run / 2838 条 job 记录反推（详见审计证据 artifact）：

| 盲区 | 实证 |
|------|------|
| 空转 | pve-runner-04 于 09-03~09-07 连续 5 天零任务，同期 01/02/03/05 每天 11~74 个 job，label 完全相同 |
| 消失 | pve-runner-06 于 09-08 后无任务，当前 org runner 列表已无此 runner |
| 卡死 | run 32215817674（QA）、32215348648（Evolution Governance）自 08-19 起 queued 23+ 天 |

另发现：每天 22~129 个 job 跑在 GitHub 托管 runner，未全走自建 fleet（部分 workflow 声明了托管 label，待查）。

## 官方/社区方案调研结论

- **官方无现成方案**：文档仅覆盖状态查看与诊断日志；"job 等待 runner 告警"在 GitHub community 讨论区长期悬而未决
- **官方原材料**：`workflow_job` org webhook（实时 job 生命周期 + runner_name）、REST API、Audit log（runner 注册/注销事件）
- **ARC（actions-runner-controller）** 是唯一官方带 Prometheus metrics 的方案，但要求 K8s，不适用 PVE standalone 场景
- **大 fleet 社区主流**：webhook/exporter → Prometheus → Grafana（如 github-actions-observability、Labbs/github-actions-exporter）
- **小 fleet（5 台）结论**：定时审计脚本足够，无需常驻监控栈

## 已定方案（待实施）

**载体**：新建公开监控仓（如 runner-health），workflow 跑 ubuntu-latest——公开仓托管 runner 免费且独立于被监控 fleet（自建 runner 全挂不影响监控运行）。

**三条检测规则**：

1. 空转检测：self-hosted runner 近 N 天（默认 2 天）job 数为 0 → 告警
2. 消失检测：manifest 期望 runner 清单 vs org runner 列表差集 → 告警
3. 卡死检测：run queued 超过 24h → 告警

**安全设计**（公开仓特有）：

- Token 分离：公开仓只存只读 fine-grained PAT（org Administration:read + 目标仓 Actions:read）；高权限 token 不进公开仓
- 告警 Issue 用监控仓自带 GITHUB_TOKEN 创建（开在监控仓自身，零额外凭证）
- 触发器锁死 schedule + workflow_dispatch，禁用 pull_request_target（防 fork PR secret 外泄）

**已知坑**：

- 公开仓 scheduled workflow 60 天无 commit 自动禁用，需保持仓库活跃
- schedule 高峰延迟（分钟级到半小时），每日审计可接受
- 空转检测必须跨仓聚合 job 历史（runner 为 org 级，服务多个消费仓库，manifest 配置仓库清单），否则误报

**暂缓项**：

- 卡死 run 只告警不自动取消（避免为写权限 token 进公开仓），清理由人或 droid 会话执行
- Prometheus/Grafana 实时路线留待 fleet 扩至 10+ 台或需要实时仪表盘时升级

## 实施状态

**未实施**。落地物：一个 workflow 文件 + 一个 Python 审计脚本 + manifest（期望 runner 清单与阈值）。

## 参考文献

- `memory/artifacts/2026-09-11-runner-audit.md`（审计证据与可复现方法）
- `memory/kb/decisions/D-012-evolution-capability-tech-debt.md`（技术债跟踪格式先例）
