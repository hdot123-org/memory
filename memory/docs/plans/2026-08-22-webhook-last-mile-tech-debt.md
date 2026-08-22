# CI webhook「最后一公里」注入链路三缺陷——技术债清单

> 创建日期：2026-08-22
> 来源：2026-08-22 PR #960 CI 失败通知未到达 session 的全程排查（1630 次历史触发日志取证）
> 性质：incoming-raw 待办素材，非 canonical
> 标注：webhook（全局基础设施域，脚本在 ~/.factory/webhook/scripts/，非本仓库代码）
> 关联：memory/kb/lessons/webhook-session-routing.md（同域前案：session 路由 mtime→index 修复）

## 背景

链路：GitHub CI 完成 → n8n webhook → 本机 `trigger-ci-droid.sh` → Factory Sessions API 注入当前 session。上游（GitHub→n8n→本机）始终通畅，断裂全部发生在本地「最后一公里」的静态环境假设上。

对 `~/.factory/webhook/logs/ci-complete-*.log` 全量 1630 次触发的取证（2026-08-22 统计）：

| 结局 | 次数 | 占比 |
|------|------|------|
| 成功注入 | 439 | 27% |
| PR_NUMBER=0（main 推送，无 pending 文件）→ fallback | 310 | 19% |
| fallback droid exec 失败（路径失效为主） | 146 | 9% |
| 注入目标 session 已死（API 404） | 77 | 5% |
| 其余（504 重试耗尽、4xx、无 pending、重复触发等） | ~658 | 40% |

真实成功率（剔除 PR#0 噪音后）约 35%。「经常断」的体感与数据一致。

## 技术债清单

### TD-WEBHOOK-01: n8n 对 main 分支推送传 PR_NUMBER=0，脚本不早退 — 🔓 开放（优先级高）

- **现状**：main 分支 CI 完成（PR 合并后）无 PR 号，n8n 传 `PR_NUMBER=0`，`trigger-ci-droid.sh` 找不到 `pending-ci-0.json` 走 fallback，spawn ghost `droid exec`（prompt 为「请检查并合并 PR #0」，不存在的 PR）
- **影响**：2026-08 每天 13-28 次（8/13-8/22 每天 9~28 次，仍在发生），每次产生一个空转 droid session；浪费配额且污染 logs/locks 目录
- **候选方案**：脚本头部 `if [ "$PR_NUMBER" = "0" ] || [ -z "$PR_NUMBER" ]; then log "main-branch push, no PR to route — early exit"; exit 0; fi`——一行早退，消掉最大噪音桶
- **备选**：n8n 侧过滤 `pull_request` 事件再触发，但需要 n8n 流程改动；脚本侧早退更简单且立即生效

### TD-WEBHOOK-02: droid 二进制路径硬编码漂移 — ✅ 已修复（2026-08-22，未走 PR）

- **现状（修复前）**：fallback 硬编码 `/Users/busiji/.local/bin/droid`，droid 迁移到 `/usr/local/bin` 后整个 8 月 110 次全部死在 `No such file or directory`
- **修复**：改为 `"${DROID_BIN:-$(command -v droid || echo /usr/local/bin/droid)}"` 动态解析，含 `DROID_BIN` 环境变量覆盖口（全局脚本就地修复，属本机基础设施，无需 PR）
- **教训**：同一缺陷模式（静态路径假设）在 trigger-error-droid.sh / trigger-droid.sh 等姊妹脚本中可能同样存在，排查时应一并检查

### TD-WEBHOOK-03: write-pending-ci.sh 写入时不验活、不选最新 session — 🔓 开放（优先级高）

- **现状**：从 sessions-index.json 解析 session 时不校验存活（不 probe API）、不按 mtime 取最新，选到过期 orchestrator session；CI 完成时（快则 4 分钟、慢则小时级）session 已死，注入 404
- **影响**：77 次注入丢失（全部 2026-08），PR #960 即此案——pending 文件选了 9 天前的 orchestrator session（94520efa），而非当前活跃 session（b49eb0fa）
- **候选方案**：`write-pending-ci.sh` 选定 session 后先 probe `GET /sessions/{id}`，404 则顺延选该 repo cwd 下 mtime 最新的 session，再验，全部死则报错退出（fail-fast）而非写入已知死 session
- **关联前案**：memory/kb/lessons/webhook-session-routing.md（PR #173/#174 修复的是「mtime 猜测选错活 session」；本债是「不验活写入死 session」，同一查找逻辑的两个缺口，那次修复未覆盖验活）

### TD-WEBHOOK-04: 注入失败 fallback 语义过宽，失败静默累积 — 🔓 开放（优先级中）

- **现状**：fallback 失败仅记 WARN 日志 + PostHog `ci_fallback_failed` 事件，无兜底告警通道；1630 次里约 40% 结局分散在 504/4xx/无 pending，多数最终无人知晓
- **影响**：链路健康度不可见，只能靠用户发现「没收到通知」才倒查日志
- **候选方案**：daily 汇总（cron 聚合前 24h 结局分布，异常率 >50% 时推送通知）；或 fallback 失败时写 status 文件由 session-start hook 提示
- **明确不做**：给每次失败加即时告警（噪音大，PostHog 已有事件，缺的是聚合视图）

## 修复优先级与依赖

1. TD-WEBHOOK-01（一行早退）与 TD-WEBHOOK-03（验活+选最新）为高优先级，均为 `~/.factory/webhook/scripts/` 内的全局脚本改动，可在一个 session 内完成
2. TD-WEBHOOK-02 已修复，姊妹脚本排查随 01/03 顺带
3. TD-WEBHOOK-04 依赖 01/03 落地后重新统计基线

## 明确不做

- 修改 Factory Sessions API 客户端重试策略（已有 3 次指数退避，504 占比小）
- 把 n8n 流程迁回本机（n8n→本机段实测通畅，非瓶颈）

## 验证方法

修复后观察一周 `ci-complete-*.log`：
```bash
grep -c "early exit.*main-branch" ~/.factory/webhook/logs/ci-complete-*.log  # TD-01 生效即有计数
grep -c "PROBE FAILED" ~/.factory/webhook/logs/ci-complete-*.log             # TD-03 生效后应趋零
```
