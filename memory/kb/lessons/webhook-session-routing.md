# CI webhook session_id 路由失效：mtime scan 猜测 vs sessions-index.json 精确查找

> Type: [KB:LESSON]
> Title: CI webhook session_id 路由失效（mtime scan 猜测导致事件路由到已死 session）
> Status: active
> Created: 2026-07-20
> Updated: 2026-07-20
> Source: local-canonical
> Confidence: high
> Tags: [lesson, webhook, ci, session-routing, sessions-index, mtime, orchestrator, worker]
> Related: [D-004-v5-refactor-completion, ci-gateway]

## 问题

CI 完成后的 webhook 事件无法路由到正确的 session。具体表现：PR 创建后 CI 通过，但 trigger-ci-droid.sh 注入消息到了已死的 worker session，而非存活的 orchestrator session，导致事件丢失。

## 根因

`write-pending-ci.sh` 的 session_id 查找逻辑有根本性缺陷：

### 原逻辑：mtime scan 猜测

```bash
# 旧逻辑（有 bug）
LATEST_SESSION=$(ls -t ~/.factory/sessions/*/session.json | head -1 | xargs dirname | xargs basename)
```

用 `ls -t` 按 mtime 排序取最新的 session 目录。假设"最新修改的 session = 当前活跃的 session"。

### 为什么失败

在 multi-agent mission 中：
1. orchestrator session 先创建（启动时间早）
2. worker session 后创建（被 orchestrator spawn）
3. worker 创建 PR 时，worker session 的 session.json mtime 比 orchestrator 新
4. `write-pending-ci.sh` 找到的是 worker session
5. CI 完成后，消息注入到 worker session（已死），orchestrator session（存活）收不到事件

**核心错误**：mtime 反映的是"最后修改时间"，不是"谁是 orchestrator"。worker session 在活跃工作期间 mtime 永远比 orchestrator 新。

## 症状

- CI 通过但 orchestrator session 没有收到 CI 完成通知
- 检查 `pending-ci.json` 发现 `session_id` 指向已退出的 worker session
- 需要人工干预才能继续 mission 流程

## 解决方案

### 修复 1: sessions-index.json 精确查找

用 sessions-index.json 的结构化 metadata 代替 mtime 猜测：

```bash
# 新逻辑（正确）
SESSION_ID=$(python3 -c "
import json
with open('$HOME/.factory/sessions/sessions-index.json') as f:
    idx = json.load(f)
for sid, meta in idx.items():
    if meta.get('role') == 'orchestrator' and meta.get('status') == 'active':
        print(sid)
        break
")
```

**优势**：
- 按 `role: orchestrator` 精确匹配，不依赖时间假设
- 检查 `status: active` 确保 session 还存活
- 结构化数据 > 文件系统元数据

### 修复 2: 全局化到 ~/.factory/webhook/scripts/

将 `write-pending-ci.sh` 从项目级脚本迁移到全局位置 `~/.factory/webhook/scripts/write-pending-ci.sh`：

- 消除每个消费项目维护 wrapper 脚本的冗余
- `PROJECT_CWD` 运行时检测（`git rev-parse --show-toplevel`），不硬编码项目路径
- `PYTHON_BIN` 动态查找（`${PYTHON_BIN:-$(command -v python3)}`）
- 各项目保留 wrapper 脚本调用全局脚本，保持向后兼容

## 教训

1. **不要用 mtime 猜测 session 归属**：mtime 是文件系统元数据，反映 IO 活动，不是逻辑归属。用 sessions-index.json 的结构化 metadata（role/status/created_at）。
2. **multi-agent 场景下"最新"不等于"最相关"**：orchestrator 和 worker 并存时，需要按 role 区分，不能只看时间。
3. **项目级脚本应该全局化**：webhook 基础设施是跨项目的，每个项目维护一份只会导致不一致。识别到重复时就立即全局化。
4. **CI webhook 路由是 mission 关键路径**：路由失败 = mission 卡死。应该在 PR 创建后立即验证 pending-ci.json 内容（检查 session_id 是否指向正确 session）。

## 验证方法

创建 PR 后立即检查：
```bash
cat ~/.factory/webhook/locks/pending-ci.json
# 确认 session_id 指向 orchestrator session，不是 worker session
```

## 修复 PR

- PR #173: `fix: 修复 webhook session 路由失效问题`
- PR #174: `refactor: write-pending-ci.sh 核心逻辑提取到全局 ~/.factory/webhook/scripts/`

## Verification Refs

- 全局脚本：`~/.factory/webhook/scripts/write-pending-ci.sh`
- 项目 wrapper：`scripts/write-pending-ci.sh`
- sessions-index：`~/.factory/sessions/sessions-index.json`
- pending-ci lock：`~/.factory/webhook/locks/pending-ci.json`
