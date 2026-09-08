# memory-evolve 每日经验管道设计

> 架构设计文档。描述 memory-evolve 每日管道的组件、数据流、CLI 接口与降级语义。
> 与 `architecture.md`（mission 目录）冲突时以 mission architecture 为准。

## 目标

把全部消费项目的经验蒸馏沉淀到全局知识库（`~/.memory/global-kb`），R2 备份扩展到全部消费项目。

## 调度

| 任务 | LaunchAgent | 时间 | 职责 |
|------|-------------|------|------|
| `com.memory.daily-evolve` | 新增 | 00:10 | memory-evolve run --all |
| `com.busiji.memory-dr-backup` | 既有（改造） | 02:30 | restic 备份（含 backup-paths 动态枚举） |

## 数据流

```
00:10 com.memory.daily-evolve
  └─ memory-evolve run --all
      ① registry    枚举全部消费项目（lifecycle 注册表并集去重，健康分类）
      ② analyzer    游标增量：各项目 memory/kb/{lessons,decisions} + memory/docs
                    + memory/log/{date}.md 自上次运行的新增/变更
      ③ extractor   LLM 蒸馏（AXONHUB glm-5.3）→ 结构化候选
      ④ sediment    去重 → 全部写入 pending/（待用户 memory-promote 确认）
      ⑤ report      运行报告 → ~/.memory-core/evolution/reports/
```

## 确认记忆模型

全局库正式域（六域目录 + INDEX.md）只收录经用户显式确认（memory-promote）晋升的条目。
管道一切产物（run / propose_write / 任何 agent 触发路径）**一律只落 `pending/`**，
永不写正式域、永不更新 INDEX。

检索面（search_memory / read_global）只服务已确认正式域内容，pending/ 不出现在检索结果。

## CLI 子命令

```bash
memory-evolve run --all              # 分析全部注册项目
memory-evolve run --project <path>   # 单项目分析
memory-evolve run --dry-run          # 只打印计划，不写全局库
memory-evolve run --no-llm           # 跳过 LLM，全部降级为 unrefined
memory-evolve status                 # 注册项目清单 + 健康分类 + pending 数量
memory-evolve status --json          # 机器可读输出
memory-evolve backup-paths           # 输出全部消费项目 memory/ 路径清单
memory-evolve gk-ensure              # 全局库 git 归位（HEAD 归位 main）
memory-evolve mcp-secret <op://...>  # 通过 MCP 解析 op:// 引用（--length-only 非交互验证）
```

`--global-kb-root /tmp/...`：agent 会话测试用临时目录，避免写真实全局库。

## 密钥解析链

无人值守（launchd）密钥解析链：
1. env `AXONHUB_API_KEY`
2. 1password MCP（HTTP）—— 运行时读 `~/.factory/mcp.json` 的 `1password-connect` 条目
3. `op read`（仅交互兜底；launchd 下会挂起等 TouchID）

config.json 只允许引用键：`api_key_env` / `api_key_op_ref` / `api_key_mcp_url`。

## 备份动态枚举

`memory-dr-backup.sh` 改造：
- 静态 PATHS 追加 `memory-evolve backup-paths` 动态枚举
- 存在性过滤按架构 §3.9 保留为纵深防御（幂等）

## LLM 降级语义

| 场景 | 行为 |
|------|------|
| 单项目分析失败 | 隔离错误，继续其余项目 |
| LLM 预算耗尽 | 剩余候选降级为 unrefined |
| `--no-llm` | 全部候选降级为 unrefined |
| `daily_budget_tokens: 0` | 启动即超限，本轮零 LLM 调用 |

退出码：
- 0 = 成功（含一切降级完成）
- 1 = 致命失败
- 2 = 用法错误

## 运行报告

每次 `run` 在 `$EVOLUTION_ROOT/reports/` 落一份报告，内容含：
- 逐项目分析文件清单
- 新增/变更计数
- 候选列表（title/domain/confidence/genericity/source_refs/去向）
- skipped_duplicate/merged 计数
- 错误隔离清单
- LLM 调用与 token 用量（含降级原因）
