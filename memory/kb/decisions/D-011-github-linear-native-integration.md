# D-011: GitHub↔Linear 状态流转使用 Linear 原生集成

## 状态
accepted

## 日期
2026-08-02

## 背景

`github-linear-sync.sh` 脚本曾是 GitHub PR 事件到 Linear 状态流转的桥接方案。水车验证过程中需要确认该脚本是否仍在使用。

## 调查

对 `github-linear-sync.sh` 进行全面引用审查：

| 检查项 | 结果 |
|--------|------|
| hooks.json（Mac webhook 配置） | ❌ 无引用 |
| crontab | ❌ 无引用 |
| launchd plist | ❌ 无引用 |
| n8n workflows | ❌ 无引用 |
| GitHub webhooks | ❌ 无引用 |

**结论：脚本完全未被使用，是死代码。**

同时确认 GitHub→Linear 状态流转实际由 **Linear 原生 GitHub 集成** 处理（集成 ID: `7ee5340b`，service: `github`）。Linear 内置监听 GitHub PR 事件，自动映射：

| GitHub 事件 | Linear 目标状态 |
|------------|----------------|
| PR open | In Progress |
| Review requested | In Review |
| PR merge | Done |

## 决策

1. **删除 `github-linear-sync.sh`** 及其关联文件（2 个日志、1 个 hooks.json.bak）
2. **确认 Linear 原生 GitHub 集成为唯一状态流转机制**
3. **修复所有文档漂移**：7 处文档将机制错误描述为"n8n 桥接"、"第三方集成"或"GitLab ↔ Linear"

## 理由

- 消除死代码减少维护负担和认知成本
- Linear 原生集成无需维护脚本，可靠性更高
- 文档必须与实际架构一致，避免误导后续开发者

## 影响

- 删除文件：`~/.factory/webhook/scripts/github-linear-sync.sh`、2 个日志、1 个 .bak
- 修改文档：`linear-factory-integration.md`、`AGENTS.md`、`APISIX-MAINTENANCE.md`、`linear-droid-gitlab-github-pipeline-spec.md`
- PR #245: 全面修复水车文档漂移
