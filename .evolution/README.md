# 进化系统 (Evolution System)

memory-core 仓库的自主改进循环。扫描器每 30 分钟运行，审计系统健康状况，发现问题后自动创建 Issue 触发 Droid 修复，CI 通过后自动合并。

## 循环流程

```
evolution-scan.yml (cron */30 * * * *)
    │
    ▼
infra_core.engine.evolution_scanner (200 行，无状态)
    ├─ 检查杀开关 (DISABLED 文件 / EVOLUTION_DISABLED)
    ├─ 执行审计工具 (3 个)
    ├─ 归一化 → 去重 → 回归检测 → 严重度排序
    ├─ 创建 ≤1 Issue (evolution-found 标签)
    ├─ 写入快照 (有界 100 条)
    └─ 故障隔离检测
    │
    ▼
GitHub Issue (author=hdot123) → Linear GitHub Issue Sync → Linear webhook → n8n → trigger-droid.sh → Droid 创建 PR
    │
    ▼
ci.yml 运行 CI 检查
    │
    ▼
auto-merge.yml 自动合并 (CI 通过后)
    │
    ▼
循环重复 (下一个 tick)
```

## 组件清单

| 组件 | 路径 | 说明 |
|------|------|------|
| 扫描器 | `infra_core.engine.evolution_scanner` | 200 行无状态扫描器（由 infra-core 包提供） |
| 审计适配器 | `infra_core.engine.evolution_adapters` | 审计工具输出适配 + 安全清洗 (162 行，由 infra-core 包提供) |
| 治理配置 | `.evolution/config.yml` | 人工维护，扫描器只读不写 |
| 扫描 Workflow | `.github/workflows/evolution-scan.yml` | cron + workflow_dispatch + concurrency + actions/cache |
| 治理 Workflow | `.github/workflows/evolution-governance.yml` | 保护路径检查，阻止非 owner 修改 |
| CODEOWNERS | `.github/CODEOWNERS` | 治理路径规则 (.evolution/ → @busiji) |
| 运行状态 | `.evolution/findings_over_time.json` | 有界快照 (上限 100 条，gitignored) |
| 杀开关 | `.evolution/DISABLED` 或 `EVOLUTION_DISABLED` 环境变量 | 二选一即停止扫描器 |
| 测试 | `tests/test_ci_config.py` 等（契约测试族） | evolution 引擎测试已随 M1 F2 迁移至 infra-core 仓 `tests/test_evolution_scanner.py`；本仓保留与 workflow 配置相关的契约测试 |

## 扫描器详解

`infra_core.engine.evolution_scanner` 是一个 200 行的无状态模块，每个 tick 执行以下流程：

1. **杀开关检查** — 检测 `.evolution/DISABLED` 文件或 `EVOLUTION_DISABLED` 环境变量，存在则立即退出 (exit 0)
2. **加载配置** — 读取 `.evolution/config.yml`
3. **执行审计工具** — 依次运行 3 个配置的审计工具，60 秒超时，单工具崩溃不影响其他工具。`evolution_adapters` 中的适配器函数将各工具输出归一化为 `Finding` 结构
4. **归一化** — 适配器函数 (`adapt_daily_audit`, `adapt_consistency_check`, `adapt_error_patterns`) 将工具输出统一为 `Finding` 数据结构 (rule_id, severity, category, description, location, evidence)
5. **回归检测** — 对比历史快照中已解决 (resolved) 的问题，若复发则提升严重度为 critical
6. **去重** — 查询已打开的 evolution-found 和 evolution-isolated Issue（`--limit 200` + OR 语义搜索），按 (rule_id, location) 去重
7. **严重度排序** — 按 severity_order 排序 (critical > warning > info)
8. **创建 Issue** — 取排序后的前 N 条 (max_issues_per_tick)，创建带 `evolution-found` 标签的 Issue。`description` 和 `evidence` 字段经 `sanitize_text()` 清洗（移除 @ 提及、Markdown 格式、截断过长文本），`rule_id` 和 `location` 经 `sanitize_structured_field()` 清洗（移除控制字符）
9. **更新历史** — 写入当前 tick 快照（原子写入：先写临时文件再 `os.replace()`），计算新解决的 finding，裁剪到 snapshot_limit。JSON 解码失败时自动重置为空状态而非崩溃
10. **故障隔离** — 检测连续 N 个 tick (isolation_threshold) 出现同一 finding，标记为 evolution-isolated

## 治理配置

`.evolution/config.yml` 是人工维护的治理参数，扫描器只读不写：

```yaml
max_issues_per_tick: 1                    # 每 tick 最多创建的 Issue 数
severity_order: [critical, warning, info] # 严重度排序
dedup_label: evolution-found              # 去重用的 Issue 标签
isolation_threshold: 3                    # 故障隔离阈值 (连续 N tick)
failure_label: evolution-isolated         # 故障隔离标签
snapshot_limit: 100                       # 快照历史上限
audit_tools:                              # 审计工具列表
  - name: daily_kb_audit
    command: "memory-audit-daily"
    output_format: json
  - name: consistency_check
    command: "memory-consistency-check"
    output_format: json
  - name: error_patterns
    command: "memory-error-patterns"
    output_format: json
```

## 抑制清单（suppress.json）

`.evolution/suppress.json` 是人工维护的 finding 抑制清单（扫描器只读）。用于抑制**源仓库固有结构**触发的 layout 审计误报——这些 finding 是对 memory-core 既定布局的"检测"而非"违规"：layout 审计工具自身的 action map 已将它们归类为 `adopt_existing_memory` / `continue_active`（采纳现状），无需任何迁移。

| rule_id | location | 依据 |
|---------|----------|------|
| `CURRENT_MEMORY` | `memory` | 本仓自带项目记忆（129 个 tracked 文件，`memory/docs`、`memory/kb` 为 critical 所有权域），设计如此（INFRA-650） |
| `PROJECT_MAP` | `project-map` | 根级 project-map 为本仓资产映射目录（3 个 tracked 文件），`continue_active` |
| `ARTIFACTS_MEMORY_HOOK` | `memory/artifacts/memory-hook` | memory-hook 运行时产物目录，`continue_active` |
| `ROOT_DOCS_DIR` | `docs` | 源仓库设计文档（specs/architecture/guides，41 个 tracked 文件），`source-repo-readonly` 约定非 memory/docs（见 docs/specs/BOUNDARY.md） |
| `AGENTS_MD_UNMARKED` | `AGENTS.md` | 本仓 AGENTS.md 为手写治理文件（无 MEMORY_HOOK 标记是刻意的），hook wrapper 通过 source-repo 检测跳过本仓 |
| `OWNERSHIP_MISSING` | `memory/system/ownership.toml` | `memory/system/` 整目录 gitignored（仅本机运行时状态，.gitignore L64），CI 干净 checkout 必然缺失；本仓为 source-repo 不走 consumer 初始化 |

维护规则：

- 条目必须**精确匹配** `(rule_id, location)`，禁止 `*` 通配——未来真实违规（如同名新路径下的污染）仍会浮出
- 每条必须有 INFRA 单号或等价依据，删除结构性目录前先删除对应条目
- 过期（`expires`）语义：到期后 finding 重新浮出，是一次天然的"抑制是否仍然成立"复查点

## 治理机制 (防止 Bot 自我修改)

进化系统通过**结构性硬锁**防止 Bot 修改自己的规则：

### evolution-governance.yml

- **触发**：`pull_request_target` (针对 main 分支)
- **保护路径**：
  - `.evolution/config.yml`
  - `scripts/**`（整个 scripts 目录）
  - `.github/workflows/evolution-*.yml`
- **规则**：PR 作者不是 `@busiji` 时，修改保护路径直接 `exit 1` 阻断

### CODEOWNERS

`.evolution/`、`scripts/**`、evolution workflows 均要求 `@busiji` 审批。

## Token 策略

扫描 Workflow 使用 `DISPATCH_TOKEN` (GitHub PAT) 而非 `GITHUB_TOKEN` 创建 Issue。

**原因**：`DISPATCH_TOKEN` 是 `@hdot123` (OWNER) 的 PAT，创建的 Issue author 为 `hdot123`，满足 CODEOWNERS 和 governance 检查。

**实际触发链路**（droid.yml 已删除，不再通过 @droid mention 触发）：
```
GitHub Issue (DISPATCH_TOKEN, author=hdot123) → Linear 原生 GitHub Issue Sync
→ Linear webhook → n8n → trigger-droid.sh → droid exec --tag linear-gateway
→ PR → CI → 合并
```

**降级方案** (DISPATCH_TOKEN 不可用时)：
1. 使用 GitHub App installation token (更细粒度、可审计)
2. 两步 workflow 链：GITHUB_TOKEN 创建 Issue，第二个 workflow 用 PAT 评论（workaround）

## 设计原则

- **无状态** — 无 session、无 ledger、无 FSM。扫描器读取配置，运行工具，创建 Issue，写入快照，退出。所有状态在 `findings_over_time.json` 中，每次 tick 全量重建。
- **反过度工程** — 扫描器控制在 200 行以内。复杂度放在配置里，不放在代码里。
- **结构化治理** — CODEOWNERS + evolution-governance.yml 是硬锁，不是审批门。Bot 无法修改自己的规则。
- **杀开关** — `.evolution/DISABLED` 文件或 `EVOLUTION_DISABLED` 环境变量立即停止扫描器 (exit 0)，无需修改 CI 配置。
- **故障隔离** — 单个审计工具崩溃返回空列表，不影响其他工具。连续 N tick 出现同一问题自动标记 isolation。

## 安全与健壮性改进

以下改进在 16 项缺陷修复任务中完成，涵盖安全加固、健壮性增强和 CI 持久化：

### 安全加固

| 改进 | 说明 |
|------|------|
| `sanitize_text()` | Issue 的 `description` 和 `evidence` 字段清洗：移除 @ 提及、Markdown 格式、截断过长文本，防止 prompt injection |
| `sanitize_structured_field()` | Issue body 中 `rule_id` 和 `location` 字段清洗：移除控制字符，防止换行注入伪造结构化字段 |
| 去重 key 防伪 | `_parse_issue_fields()` 遇到 Description/Evidence section 时停止解析，防止 evidence 内容伪造 rule_id/location |

### 健壮性增强

| 改进 | 说明 |
|------|------|
| 原子历史写入 | `update_history()` 先写临时文件再 `os.replace()`，避免并发/中断导致 JSON 损坏 |
| JSON 损坏恢复 | 历史快照 JSON 解码失败时自动重置为空状态，而非崩溃 |
| `--limit 200` | 所有 `gh issue list` 调用添加 `--limit 200`，防止超过 30 条 open Issue 时去重失效 |
| OR 语义标签搜索 | `get_open_issues()` 使用 `--search label:evolution-found OR label:evolution-isolated` 单次查询两个标签 |
| API 效率 | `check_isolation()` 循环前一次性查询 Issue 列表，而非循环内 N 次调用 |
| exit code 语义 | `run_audit_tool()` 无论 returncode 如何都解析 stdout，适配非零退出但有输出的工具 |

### CI 持久化

| 改进 | 说明 |
|------|------|
| `actions/cache@v4` | evolution-scan.yml 新增缓存步骤，跨 CI 运行持久化 `findings_over_time.json` |
| 缓存 key 策略 | run-scoped key (`evolution-history-${{ github.run_id }}`) + 稳定 restore prefix (`evolution-history-`) |

## 使用方法

### 本地运行扫描器

```bash
# 需要 gh CLI 已认证
python -m infra_core.engine.evolution_scanner
```

### 杀开关

```bash
# 停止扫描器 (方式一：文件)
touch .evolution/DISABLED

# 停止扫描器 (方式二：环境变量)
export EVOLUTION_DISABLED=1

python -m infra_core.engine.evolution_scanner  # 输出 "Kill switch active, exiting" 后立即退出

# 恢复扫描器
rm .evolution/DISABLED
unset EVOLUTION_DISABLED
```

### 运行测试

```bash
# 契约测试（本仓 workflow 配置相关）
pytest tests/test_ci_config.py -v --no-cov
# 引擎测试已迁移至 infra-core 仓 tests/test_evolution_scanner.py
```

### 检查行数限制

```bash
# 扫描器必须不超过 200 行
python -c "import infra_core.engine.evolution_scanner as m; from pathlib import Path; print(sum(1 for _ in open(Path(m.__file__).with_suffix('.py'))))"
```

### 手动触发扫描

在 GitHub Actions 页面手动触发 `Evolution Scan` workflow (workflow_dispatch)，或本地运行 `python -m infra_core.engine.evolution_scanner`。

## 文件结构

```
.evolution/
├── config.yml                 # 人工维护的治理配置 (git tracked)
├── suppress.json              # 人工维护的 finding 抑制清单 (git tracked)
├── findings_over_time.json    # 运行状态快照 (gitignored, CI actions/cache 持久化)
└── DISABLED                   # 杀开关 (存在即停止，按需创建)

tests/
└── test_ci_config.py          # 契约测试族（evolution workflow 配置相关；引擎测试已迁移至 infra-core）

.github/workflows/
├── evolution-scan.yml         # cron 扫描 + workflow_dispatch + actions/cache
└── evolution-governance.yml   # 保护路径 CI 检查

.github/
└── CODEOWNERS                 # 治理路径 → @busiji
```

引擎模块（`infra_core.engine.evolution_scanner` / `evolution_adapters` 等）由 infra-core 包提供，不再本地存放副本。
