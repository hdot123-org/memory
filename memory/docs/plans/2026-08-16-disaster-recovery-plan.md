# 记忆系统全链路容灾方案（DR Plan v1）

> 制定日期：2026-08-16
> 状态：proposed（待批准后进入 P0 实施）
> 范围：memory-core 仓库 + 项目记忆数据 + 本地自动化链路 + 远端云端服务

---

## 1. 目的与范围

为整套记忆系统（本地数据、代码、CI、webhook 链路、错误网关、密钥）建立统一的容灾体系：
明确资产清单、故障域、RTO/RPO 目标、备份策略、恢复手册与演练机制。

**不在本方案范围**：memory-core 库本身的功能迭代（见 chaos-test backlog，属测试层加固，与本方案互补）。

---

## 2. 资产清单与保护现状（2026-08-16 实测）

| # | 资产 | 位置 | 体量 | 当前保护 | 缺口 |
|---|------|------|------|----------|------|
| A1 | 记忆 KB（kb/docs） | `memory/memory/kb`、`memory/memory/docs` | ~1M，124 文件 | git 跟踪 + GitHub | 仅一个 remote（GitLab 已摘除） |
| A2 | **artifacts** | `memory/memory/artifacts` | **1.9G** | 仅本机 + 本地 TM | **被 .gitignore 忽略，零异地备份** |
| A3 | **system 运行数据** | `memory/memory/system` | **159M** | 仅本机 + 本地 TM | 未跟踪、未异地备份 |
| A4 | 日志 | `memory/memory/log` | 7.8M | 仅本机 | `log/` 被 gitignore |
| A5 | **inbox.md（action 队列）** | `memory/memory/inbox.md` | 4K | 仅本机 | **未跟踪，丢失即丢待办** |
| A6 | NOW.md / project-map | 仓库根 | 小 | git 跟踪（NOW.md 部分忽略） | 低 |
| A7 | 全局 KB | `~/.memory/global-kb` | 708K / 106 文件 | 仅本机 | 不在任何 git 仓库内 |
| A8 | **项目生命周期状态** | `~/.memory-core/project-lifecycle` | **125M** | 仅本机 | events.jsonl 丢了无法回放 |
| A9 | 完整性密钥 | `~/.memory-core/keys/project-integrity.key` | — | 仅本机 | 丢失导致 hook 校验全线失败 |
| A10 | 代码仓库 | github.com/hdot123/memory | .git 34M | GitHub + 本地 | **无第二代码托管备份** |
| A11 | webhook 脚本 | `~/.factory/webhook/scripts` 等 | — | 手工 .bak 文件（8 份散落） | 无版本管理 |
| A12 | launchd/cron 配置 | `~/Library/LaunchAgents`、crontab | 10+ 项 | 仅本机 | 重装后需凭记忆重建 |
| A13 | self-hosted runner | `~/actions-runner` | — | 仅本机 | Mac 挂 → CI 全停 |
| A14 | 密钥托管 | 1Password Connect | — | SaaS | Connect 故障时无本地应急副本 |
| A15 | 任务面板 | Linear | — | SaaS | 可接受，有 GitHub 侧同步 |
| A16 | Time Machine | 本地盘（"2.5"，Kind: Local） | — | 有 | **与主机同故障域** |

---

## 3. 故障域与单点分析

**最大单点：这台 Mac。** 它同时承担了六重角色：

1. 记忆数据唯一热副本（A2/A3/A5/A7/A8/A9）
2. webhook 监听（com.factory.webhook，Mac:5555）
3. self-hosted CI runner（A13）
4. launchd 服务群（gateway / reconcile / watchdog / docs-sync / summary）
5. cron 任务（daily-audit、error-monitor）
6. Time Machine 目标盘也在本机（A16）

次要单点：

- **GitHub**：代码 + CI + Issue + Release 全链唯一供应商（A10）
- **APISIX 网关（192.168.88.11）→ n8n**：错误网关与 CI 通知的唯一入站通道
- **1Password Connect**：所有运行时密钥的唯一来源（A14）

---

## 4. 容灾目标分级（RTO / RPO）

| 级别 | 资产 | RPO 目标 | RTO 目标 | 理由 |
|------|------|----------|----------|------|
| L0 | 记忆 KB、inbox、NOW、project-map | ≤ 1h | ≤ 2h | 认知资产，丢失不可重建 |
| L1 | artifacts、system、log、project-lifecycle | ≤ 24h | ≤ 24h | 可重建成本高但非即时需要 |
| L2 | 代码仓库 + CI | ≈ 0（PR 即远端） | ≤ 4h | GitHub SaaS + 本地双份 |
| L3 | webhook/错误网关链路 | 事件可重放（≤ 1h 窗口丢失可接受） | ≤ 4h | 有 pending-ci.json / 幂等指纹兜底 |
| L4 | 密钥（1PW + integrity.key） | 0 | ≤ 1h | 恢复一切的前置条件 |

---

## 5. 备份体系（3-2-1 改造）

现状是"1.5-1"（本机 + 本机 TM + GitHub 单 remote）。目标 3-2-1-1-0：

- **3 份数据、2 种介质、1 份异地、1 份离线、0 错误（定期验证）**

### 5.1 数据分通道

| 通道 | 内容 | 方式 | 频率 |
|------|------|------|------|
| git 通道 | kb/docs/NOW/project-map（A1/A6） | 现有仓库 + 恢复 GitLab 第二 remote，或 GitHub 第二私有仓镜像 | 每次 commit |
| **git 通道补漏** | inbox.md、log 索引 | 修改 .gitignore 策略：inbox.md 纳入跟踪（4K，低噪音） | 每日定时 commit |
| 快照通道 | artifacts、system、log、global-kb、project-lifecycle、~/.factory（A2-A5/A7/A8/A11/A12） | restic 加密仓库 → 云端对象存储（B2/R2 均可） | 每日 02:30（daily-audit 之后） |
| 离线通道 | integrity.key、1PW 应急套件（break-glass） | 1Password 附紧急包 + 打印离线封存 | 变更时 |

### 5.2 关键设计点

1. **artifacts 冷热分层**：1.9G 中按 mtime 分层，>90 天未访问的移入冷备（restic 单独 repo，压缩去重），本地仅留热数据与索引。
2. **restic 而非 rsync**：加密（密钥存 1PW）+ 去重 + 快照可回滚，适配 125M events.jsonl 每日追加的场景。
3. **launchd/cron 声明化**：把全部 plist + crontab 收进一个 `infra-manifest` git 仓（dotfiles 化），附 `install.sh` 一键重放。webhook 脚本（去掉 .bak 惯例）也入此仓。
4. **Time Machine 保留**：作为本地快速恢复层，但不再视为"异地"。
5. **第二代码 remote**：恢复 GitLab push（AGENTS.md 已声明保留用于历史备份），或建 GitHub 私有 mirror 仓，`git remote set-url --add --push` 双推。

---

## 6. 组件级恢复手册（Runbook 索引）

每条链路落盘到 `memory/docs/runbooks/`，统一格式：**症状 → 诊断 → 恢复步骤 → 验证**。

| RB# | 场景 | 兜底机制（现状） | 恢复路径（目标） |
|-----|------|------------------|------------------|
| RB-01 | Mac 整机故障/重装 | 本地 TM | TM 全量 + infra-manifest 重放 + restic 云端恢复 + 1PW 取密钥 |
| RB-02 | 记忆数据误删/损坏 | git（仅 kb/docs） | 三路恢复：git revert → restic 快照 → TM |
| RB-03 | GitHub 不可用/仓库误删 | 无 | GitLab/镜像仓 re-push；期间冻结发版（release-please 本就依赖 GitHub） |
| RB-04 | Actions / runner 故障 | 无 | runner 重建（infra-manifest）；极端时临时切 GitHub hosted ubuntu-labeled job |
| RB-05 | release-please 故障 | 已有预案 | `workflow_dispatch` 手动触发 release-and-dispatch.yml（AGENTS.md 已定义） |
| RB-06 | n8n / APISIX 断 | 无 | 事件侧：PostHog alert 仍在；消费侧：hourly factory-error-monitor + pending-ci.json 兜底；修复后 reconcile-evolution.sh 对账 |
| RB-07 | Mac:5555 监听挂 | 无 | launchd KeepAlive 自动拉起；手动 `launchctl kickstart`；CI 通知降级为手动 `gh pr checks` |
| RB-08 | hook gateway 故障 | 无 | 记忆写入降级为直接 markdown 编辑 + 恢复后跑 daily-audit reconcile；project-lifecycle 事件可从 events.jsonl 回放 |
| RB-09 | Linear 不可用 | GitHub 同步 | 降级 GitHub Issue 面板（issue-flow.md 已定义双轨职责） |
| RB-10 | 1Password Connect 故障 | 无 | break-glass 离线应急包（L4 离线通道） |
| RB-11 | integrity.key 丢失 | 无 | 重新签发流程 + 全量 canonical 重校验（需在 memory-core 增加工具，见 §7） |
| RB-12 | 误 push 污染 main | branch protection | 标准回滚（revert PR），禁止 force push（既有铁律） |

---

## 7. 预防性加固（超出备份的部分）

1. **全链路探活**：扩展 daily-audit-cron 为 `system-health-check`，覆盖：webhook:5555、gateway、runner 注册状态、n8n 可达、1PW 可达、restic 上次快照年龄、GitHub API 配额。异常写 `memory/system/errors.log` + 每日 summary 提及。
2. **webhook outbox 模式**：入站事件先落盘（JSONL）再处理，处理成功打标；链路恢复后重放未打标事件。pending-ci.json 已是此模式的单点实现，泛化到 error-gateway。
3. **快照年龄告警**：restic 最后快照 >26h 即在每日 summary 中标红（防"静默备份失效"，最常见事故形态）。
4. **key 轮换工具**：memory-core 增加 `memory-rekey`（签发/轮换 project-integrity.key + 重校验），补 RB-11 的工具缺口。
5. **artifacts 生命周期**：增量进冷备后本地可裁剪，防 1.9G 无限膨胀（也缓解 TM 压力）。

---

## 8. 实施路线

### P0（本周，堵最大窟窿）

| 事项 | 验收标准 |
|------|----------|
| restic 云端仓库建立 + 每日 02:30 快照 cron | `restic snapshots` 可见当日快照；快照包含 A2-A5/A7/A8/A11 |
| integrity.key + 1PW 应急包入离线通道 | 1PW 内可检索到 restic 密码 + 应急 kit |
| inbox.md 纳入 git 跟踪 | `git ls-files memory/inbox.md` 非空 |
| 第二代码 remote 恢复（GitLab 或私有 mirror） | `git push --dry-run` 双 remote 成功 |
| 本方案 + RB-01/02 两个 runbook 落盘 | runbooks/INDEX.md 更新 |

### P1（两周）

- infra-manifest 仓（plist/crontab/webhook 脚本声明化 + install.sh）
- RB-03 ~ RB-07 runbook 落盘
- system-health-check 上线（§7.1）
- webhook outbox 泛化到 error-gateway

### P2（一个月）

- artifacts 冷热分层自动化（§5.2.1）
- RB-08 ~ RB-12 runbook 补全
- memory-rekey 工具（§7.4）
- 首次全量 DR 演练 + 演练报告

---

## 9. 演练机制

- **频率**：每月最后一个周六，随机抽取一项 RB 执行"盲演练"（不看文档先操作，再对照文档补差）。
- **记录**：`memory/docs/runbooks/DR-DRILL-YYYY-MM.md`，记录耗时 vs RTO 目标、发现的文档缺口。
- **升级规则**：连续两个月同一 RB 演练失败 → 升级为 INFRA issue 进 Linear。

---

## 10. 与既有机制的关系

| 既有机制 | 本方案定位 |
|----------|-----------|
| chaos-test backlog（2026-08-14） | 测试层加固（代码内故障注入），与本体方案（基础设施层）互补，不重复 |
| pending-ci.json + PR=0 fallback | RB-06/07 的已验证兜底，保留并泛化 |
| suppress.json expires、flock 等测试 | 代码韧性既有覆盖，不涉及 |
| .bak 手工备份惯例（webhook 脚本 8 份） | 由 infra-manifest git 化取代 |
| AGENTS.md 各铁律（禁 --admin、发版纪律） | RB-05/RB-12 直接引用，不复制规则本体 |

---

## Truth Basis

### Source Refs

- 2026-08-16 session 实测盘点（git ls-files / du / tmutil / launchd / crontab）

### Authority Refs

- memory/kb/global/memory-system.md（三层架构与资产定位）
- memory/docs/runbooks/INDEX.md（既有 runbook 索引）

### Evidence Refs

- `git ls-files`：memory/artifacts=0、memory/system=0、memory/log=0、memory/inbox.md=0 tracked
- `du -sh`：memory/ 全量 2.1G（artifacts 1.9G、system 159M）
- `tmutil destinationinfo`：Time Machine Kind=Local
- `git remote -v`：仅 origin（github.com/hdot123/memory）
- `~/Library/LaunchAgents/actions.runner.hdot123-memory.memory-core-mac.plist` → `/Users/busiji/actions-runner/runsvc.sh`

### Conflict Status

- resolved
