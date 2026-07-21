# Integrity Manifest 全面集成 + 日志实时记录

## 需求文档

### 一、背景

当前 memory-core 的 Integrity Manifest（L2 Integrity Layer）存在以下问题：

1. **`memory/log/` 完全裸奔** — 不在 ownership 域中，不在签名范围内，日志文件可被任意篡改
2. **`memory-init` 不触发签名** — 首次签名等到首次 session-start，中间有窗口期
3. **全量重签名性能差** — 每次 hook 扫描所有文件（50-500ms），频繁因 artifact 变化导致校验失败
4. **A 层绑定 SessionEnd** — 会话挂住不关闭时，所有活动对日志系统不可见
5. **会话跨日无处理** — 跨日 session 只记录到结束日期，开始日期的工作丢失

### 二、功能点

#### F1: Integrity 保护范围扩展

**目标**：将 `memory/log/` 纳入 Integrity Manifest 保护范围

**改造文件**：`memory_core/ownership.py`

**具体内容**：
- 新增 `memory_log` ownership 域，路径 `memory/log`，级别 STANDARD（非 CRITICAL），recursive
- 新增 `error_log` ownership 资源，覆盖 `memory/log/*-errors.jsonl`
- 调整 `VOLATILE_PATTERNS`：保留 `memory/system/health-report.json` 等运行时文件排除，但不再排除 errors.jsonl
- 确认 `memory/log/` 下的 `.md` 和 `.jsonl` 文件都被 `_discover_canonical_files()` 发现

#### F2: memory-init 基线快照

**目标**：项目接入后立即建立 integrity 基线

**改造文件**：`memory_core/tools/init_project_memory.py`

**具体内容**：
- 在 `memory-init` 完成所有目录/文件生成后，调用 `sign_project()` 建立基线 manifest
- 处理密钥不存在的情况（调用 `load_or_create_key()`）
- 处理签名失败的情况（warning 但不阻塞 init）
- 写审计日志到 `integrity-audit.jsonl`（reason: "memory-init baseline"）

#### F3: 增量签名机制

**目标**：从全量重签名改为增量签名，性能提升 10-100x

**改造文件**：
- `memory_core/tools/memory_hook_integrity_manifest.py`
- `memory_core/tools/memory_hook_gateway.py`

**具体内容**：

**新增 `sign_project_incremental(project_root, key, changed_paths, *, now_iso=None) -> dict | None`**：
- 参数 `changed_paths`：本次变化的文件相对路径列表
- 读取现有 manifest.json
- 只对 `changed_paths` 中的文件重新计算 SHA-256 + HMAC-SHA256
- 保留未变化文件的签名不变
- 写回 manifest.json
- 返回新的 manifest dict

**gateway 集成**：
- 新增 `_collect_changed_paths()` 函数，通过比对 manifest 和磁盘文件发现变化
- session-start 时：先校验 → 如果有变化 → 增量签名
- 签名完成后更新 artifact

**并发保护**：
- manifest 写入使用文件锁（fcntl.flock）防止并发冲突
- 获取锁失败时 warning 但不阻塞

#### F4: PromptSubmit 实时记录

**目标**：解决会话挂住不关闭的问题，实现实时可观测

**改造文件**：
- 新建 `memory_core/tools/prompt_submit_logger.py`
- `~/.factory/settings.json`（注册 PromptSubmit hook）

**具体内容**：

**新建 `prompt_submit_logger.py`**：
- 输入：Factory PromptSubmit hook 的 stdin payload（session_id, cwd, transcript_path, user_message）
- 输出：追加到 `{project_root}/memory/log/{YYYY-MM-DD}-sessions.md`
- 每条记录格式：
  ```markdown
  #### {timestamp} — {session_id[:8]} [heartbeat]
  - **用户消息**: {user_message 前 100 字符}
  - **累计 prompt 数**: {当前 session 的 prompt 计数}
  ---
  ```
- 心跳记录和 SessionEnd 的完整记录用不同的标题格式区分
- 降级策略：transcript 不可读 → 静默退出，C 层记录错误
- 超时保护：SIGALRM 2s

**注册 PromptSubmit hook**：
- 在 `~/.factory/settings.json` 的 PromptSubmit 事件中注册
- 命令：`python3 /Users/busiji/memory/memory_core/tools/prompt_submit_logger.py`
- timeout：5s

**会话跨日处理**：
- PromptSubmit 按 `datetime.now()` 的实际日期写入对应天的文件
- 午夜过后自动写入新一天的心跳
- SessionEnd 时追加最终统计（token 总量、时长、完整摘要）到结束日期的文件
- B 层每日总结时，如果发现同一 session_id 出现在两天的日志中，合并处理

#### F5: Integrity 签名集成到 A/B/C 层

**目标**：A/B/C 层写入文件后立即增量重签名

**改造文件**：
- `memory_core/tools/session_end_logger.py`
- `memory_core/tools/daily_summary_generator.py`
- `memory_core/tools/error_logger.py`

**具体内容**：

**A 层（session_end_logger.py）**：
- 追加 session 到 sessions.md 后
- 调用 `sign_project_incremental(project_root, key, changed_paths=["memory/log/{date}-sessions.md"])`
- 签名失败时 warning 但不阻塞

**B 层（daily_summary_generator.py）**：
- 写入每日总结 `{date}.md` 后
- 调用 `sign_project_incremental(project_root, key, changed_paths=["memory/log/{date}.md"])`
- 签名失败时 warning 但不阻塞

**C 层（error_logger.py）**：
- 追加错误到 `{date}-errors.jsonl` 后
- 调用 `sign_project_incremental(project_root, key, changed_paths=["memory/log/{date}-errors.jsonl"])`
- 签名失败时静默（error_logger 本身不允许抛异常）

**通用处理**：
- 所有脚本通过 `try: from memory_core.tools.memory_hook_integrity_manifest import sign_project_incremental` 导入
- 导入失败（模块不存在）时跳过签名，不影响主流程
- 密钥不存在时跳过签名

### 三、性能要求

| 操作 | 当前耗时 | 目标耗时 |
|------|---------|---------|
| 全量签名 | 50-500ms | 不变 |
| 增量签名（单文件） | N/A | <5ms |
| PromptSubmit hook | N/A | <2s |
| A 层写入+签名 | <2s | <2.5s |
| B 层写入+签名 | <120s | <121s |
| C 层写入+签名 | <100ms | <150ms |

### 四、文件布局

```
memory_core/tools/
├── error_logger.py                      # 修改：签名集成
├── session_end_logger.py                # 修改：签名集成
├── daily_summary_generator.py           # 修改：签名集成
├── prompt_submit_logger.py              # 新建：PromptSubmit 实时心跳
├── memory_hook_integrity_manifest.py    # 修改：新增增量签名函数
├── memory_hook_gateway.py               # 修改：增量签名集成
├── init_project_memory.py               # 修改：init 后基线快照
├── hook_event_stats.py                  # 不变
└── memory_health_report.py              # 不变

memory_core/ownership.py                 # 修改：新增 memory_log 域
```

### 五、待确认事项

1. **PromptSubmit hook 的 payload 格式** — 需要确认 Factory 传递给 PromptSubmit hook 的 stdin payload 结构
2. **并发写入保护** — PromptSubmit 和 SessionEnd 可能同时触发，需要确认文件锁策略
3. **签名密钥按项目隔离** — 当前全局共享，是否需要改为按项目独立密钥
4. **日志签名历史** — 是否需要对每次签名操作记录审计日志
