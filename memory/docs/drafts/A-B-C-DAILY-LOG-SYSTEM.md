# A+B+C 三层每日日志自动化系统

## 需求文档

### 一、整体架构

> **全自动运行**：系统部署完成后完全自动运行，无需人工干预。A 层由 Factory SessionEnd Hook 自动触发，B 层由 macOS launchd 每日 23:55 定时触发，C 层由 A/B 层异常时被动触发。唯一需要手动操作的是初始部署（已完成）。

| 层级 | 触发时机 | 功能 | 性能要求 |
|---|---|---|---|
| **A层** | Session 结束（实时） | 追加 session 统计到 `{date}-sessions.md` | <2s |
| **B层** | 每日 23:55 定时（launchd） | LLM 分类总结到 `{date}.md` | <120s（含 LLM 调用） |
| **C层** | A/B 层调用失败时 | 错误记录到 `{date}-errors.jsonl` | <100ms |

### 二、A层：Session 实时统计追加

#### 触发机制
Factory `SessionEnd` hook → `session_end_logger.py`

#### 输入
从 Factory hook stdin payload 提取：
- `session_id`
- `cwd`（项目根目录）
- `transcript_path`（jsonl 路径）

#### 输出
追加到 `{project_root}/memory/log/{YYYY-MM-DD}-sessions.md`

每条记录包含：
- session_id 前缀
- 标题、模型、时长
- Token 用量（input/output）
- 工具调用统计
- 用户意图（第一条 user message 前 200 字符）
- 助手摘要（最后一条 assistant message 片段）

#### 降级策略
- transcript 不存在 → 静默退出，错误记录到 C 层
- 超时 2s → 静默退出，错误记录到 C 层
- 任何异常 → 错误记录到 C 层，不阻塞 hook 链

#### 当前状态
- ✅ 已实现：`memory_core/tools/session_end_logger.py`
- ✅ 已验证：workbot 项目 6 个 session 追加成功
- ✅ 已修复：memory 项目日志写入（C 层 error_logger 自动创建目录）
- ✅ 已集成：失败时 C 层错误记录

### 三、B层：每日 LLM 总结

#### 触发机制
launchd 每日 23:55 → `daily_summary_generator.py --today --all-projects`

#### 输入
- A层 `{date}-sessions.md` 的 session 列表
- 对应 session 的 transcript jsonl（用于补充详情）

#### 输出
写入 `{project_root}/memory/log/{YYYY-MM-DD}.md`，包含：
- 统计概览（session 数、总 token、健康状态）
- 按主题分类的工作总结（LLM 生成）
- 经验教训（3-5 条）

#### 降级策略
- LLM 调用失败 → 降级为纯统计报告（无分类）
- API key 缺失 → 同上
- 请求超时 → 重试或降级
- 无 session 数据 → 跳过该项目
- 降级失败 → 错误记录到 C 层

#### 兜底策略
自动补前 3 天缺失日志（应对关机/断网场景）

#### 当前状态
- ✅ 已实现：`memory_core/tools/daily_summary_generator.py`
- ✅ 已验证：workbot 项目 LLM 生成成功（1220 字符，4 主题分类 + 3 条经验教训）
- ✅ 已部署：`~/Library/LaunchAgents/com.memory.daily-summary.plist` 23:55 定时
- ✅ 已集成：降级失败时 C 层错误记录

### 四、C层：全局错误日志

#### 触发时机
A 层或 B 层脚本运行时发生异常

#### 输出
追加到 `{project_root}/memory/log/{YYYY-MM-DD}-errors.jsonl`

每行一个 JSON 对象：
```json
{"ts":"2026-05-28T14:30:00+08:00","type":"transcript_missing","script":"session_end_logger","project":"/path/to/project","ctx":{"session_id":"abc12345","expected_path":"/path/to/transcript.jsonl"},"msg":"transcript not found: /path/to/transcript.jsonl"}
```

**字段规范**：
- `ts`：ISO 8601 时间戳
- `type`：错误类型枚举（8 种）
- `script`：来源脚本名
- `project`：项目根路径
- `ctx`：上下文键值对
- `msg`：错误消息（截断 500 字符，API key 自动脱敏为 `sk-...****`）

#### 错误分类表

| 错误类型 | 来源 | 严重度 | ctx 字段 |
|---|---|---|---|
| `transcript_missing` | A层 | low | session_id, expected_path |
| `hook_timeout` | A层 | medium | session_id, timeout_seconds |
| `json_parse_error` | A层 | low | file_path, line_number |
| `directory_creation_failed` | A/B/C | medium | project_root, log_path |
| `file_write_failed` | A/B | medium | file_path, error_msg |
| `llm_api_error` | B层 | high | http_status, model, error_body |
| `llm_timeout` | B层 | high | model, timeout_seconds, prompt_length |
| `settings_read_failed` | B层 | low | settings_path |

#### 设计约束
- **轻量**：错误日志写入不应再触发异常（避免递归）
- **隔离**：按项目独立记录，互不污染
- **可观测**：支持 `jq` / `grep` 快速定位
- **静默**：不阻塞正常流程，只在失败时追加
- **安全**：不记录敏感信息（API key 脱敏为 `sk-...****`）
- **截断**：error_msg 超过 500 字符自动截断

#### 错误写入函数
```python
def write_error_log(project_root: str, error_type: str, context: dict, error_msg: str) -> bool:
    """追加错误到 {project_root}/memory/log/{date}-errors.jsonl。
    
    此函数本身发生异常时静默返回 False，不重试、不递归。
    API key 自动脱敏，error_msg 超过 500 字符自动截断。
    """
    try:
        log_path = Path(project_root) / "memory" / "log" / f"{today}-errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": iso_timestamp(),
            "type": error_type,
            "script": context.get("script", "unknown"),
            "project": project_root,
            "ctx": context,
            "msg": truncate(sanitize_api_keys(error_msg), 500),
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False  # 静默，不再记录
```

### 五、配置与部署

| 组件 | 路径 | 说明 |
|---|---|---|
| A层脚本 | `memory_core/tools/session_end_logger.py` | Hook 入口 |
| B层脚本 | `memory_core/tools/daily_summary_generator.py` | 定时入口 |
| SessionEnd hook | `~/.factory/settings.json` | Factory 启动快照 |
| Hook 备份 | `~/.factory/settings.local.json` | Factory UI 不覆盖 |
| 定时任务 | `~/Library/LaunchAgents/com.memory.daily-summary.plist` | 23:55 执行 |

### 六、文件布局

```
{project}/memory/log/
├── 2026-05-28-sessions.md       # A层：session 追加
├── 2026-05-28.md                # B层：每日总结
└── 2026-05-28-errors.jsonl      # C层：错误日志（JSON Lines）
```

### 七、已知问题

| 问题 | 状态 | 描述 |
|---|---|---|
| Factory 重启覆盖 settings.json | ✅ 已修复（双保险） | 使用 settings.local.json 作为第二持久层 |
| NODE_CHANNEL_FD 泄漏 | ✅ 已修复 | .zshrc 条件 unset + GitHub #1163 提交 |
| SSL handshake 失败（urllib） | ✅ 已修复 | 改用 `curl -sk` subprocess |
| memory 项目 sessions 日志缺失 | ✅ 已修复 | C 层 error_logger 已自动创建目录，写入 Bug 已修复 |
| C层错误日志未接入 | ✅ 已实现 | `error_logger.py` 已实现，A/B 层已集成 |

### 八、待确认事项

1. ~~**错误日志格式**：纯 markdown 追加（当前方案） vs JSON lines（更机器友好）~~ → **已决策：采用 JSON Lines 格式**
2. **错误日志大小上限**：超过 100 条/天是否需要归档到 archive/？
3. **通知机制**：是否需要 high 级别错误时发送提醒（如飞书/webhook）？
4. **非 A/B 层错误接入**：是否也要记录其他 hook（如 PromptSubmit/SessionStart）的失败？
5. **C层独立触发器**：是否需要一个独立的 cron 任务来检查 C 层并汇总？
