# CLI 工具模块深度分析报告

---

## 1. CLI 入口点定义 (pyproject.toml)

```toml
[project.scripts]
memory-init     = "memory_core.tools.init_project_memory:main"
memory-migrate  = "memory_core.tools.migrate_project_memory:main"
memory-validate = "memory_core.tools.validate_project_memory:main"
```

**注册了 3 个 CLI 命令**，均为 `memory_core.tools` 包下的 `main()` 函数入口。
**注意**: `validate_memory_system.py` 未在 `pyproject.toml` 注册为 CLI 入口，只能作为脚本直接执行（`python -m memory_core.tools.validate_memory_system` 或 `python validate_memory_system.py`）。

包版本声明：`version = "0.2.0"`，Python >=3.9，无外部依赖（零依赖设计）。

---

## 2. 每个 CLI 命令的详细分析

### 2.1 `memory-init` (init_project_memory.py)

#### 参数表

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--target` | Path | 是 | 无 | 目标项目根目录 |
| `--scope` | str | 否 | None | 显式项目名称（否则自动从 git remote 或目录名推断） |
| `--dry-run` | flag | 否 | False | 仅报告不写入 |
| `--json` | flag | 否 | False | JSON 格式输出 |
| `--host` | str | 否 | `"codex"` | 钩子宿主平台（`codex` 或 `claude`） |
| `--version` | flag | 否 | 无 | 显示版本 |

#### 完整流程

```
main() 入口
  │
  ├─ 1. 解析 CLI 参数（argparse）
  │     - 通过 importlib.metadata.version("memory-core") 获取版本号
  │     - 验证 --target 是存在的目录（否则 exit 2）
  │
  ├─ 2. 调用 init_project_memory()
  │     │
  │     ├─ 2.1 解析项目名称 (_project_name)
  │     │     优先级: --scope > git remote origin > 目录名
  │     │     git remote 解析: 取 URL 最后一段，去 .git，转 slug（小写+下划线）
  │     │
  │     ├─ 2.2 Dry-run 模式: 构建 dry_run_output 字典，直接返回
  │     │
  │     ├─ 2.3 安全守卫: _find_repo_root → _is_memory_repo
  │     │     如果目标在 memory 仓库内部，拒绝初始化（防止污染）
  │     │     检测方法: 检查 memory_core/tools/memory_hook_gateway.py 或 memory_core/memory 是否存在
  │     │
  │     ├─ 2.4 创建目录结构 (DIRECTORY_STRUCTURE)
  │     │     .memory, .memory/kb, .memory/kb/projects,
  │     │     .memory/kb/decisions, .memory/kb/lessons, .memory/kb/global
  │     │     每个目录 mkdir(parents=True, exist_ok=True)
  │     │
  │     ├─ 2.5 创建 .keep 文件（空目录占位）
  │     │     所有子目录（除 .memory 根目录外）都创建空的 .keep
  │     │
  │     ├─ 2.6 创建模板文件 (FILE_TEMPLATES)
  │     │     7 个文件: memory.lock, adapter.toml, CANONICAL.md,
  │     │     PLAN.md, STATE.md, TASKS.md, migrations.log
  │     │     已存在的文件跳过（记录到 skipped 列表）
  │     │
  │     ├─ 2.7 生成 hooks.json (.claude/hooks.json)
  │     │     仅在 host="claude" 时有效，幂等追加
  │     │     4 个钩子事件: SessionStart, UserPromptSubmit, Notification, Stop
  │     │
  │     └─ 2.8 更新 AGENTS.md
  │           插入 Memory Hook 指令块（带 BEGIN/END 标记）
  │           幂等: 已有标记则替换内容，否则追加
  │
  └─ 3. 输出报告
        - JSON 模式: 直接 json.dumps(result)
        - 文本模式: 格式化的 [CREATE]/[SKIP]/[ERROR] 报告
        - 返回值: 0=成功, 1=失败
```

#### 生成的文件清单

| 文件路径 | 内容 | 模板函数 |
|----------|------|----------|
| `.memory/memory.lock` | JSON 版本锁定文件 | `template_memory_lock` |
| `.memory/adapter.toml` | TOML 适配器配置 | `template_adapter_toml` |
| `.memory/CANONICAL.md` | YAML frontmatter + Markdown | `template_canonical_md` |
| `.memory/PLAN.md` | YAML frontmatter + Markdown | `template_plan_md` |
| `.memory/STATE.md` | YAML frontmatter + Markdown | `template_state_md` |
| `.memory/TASKS.md` | YAML frontmatter + Markdown | `template_tasks_md` |
| `.memory/migrations.log` | 迁移日志（初始记录） | `template_migrations_log` |
| `.memory/kb/**/.keep` | 空文件 | `template_keep` |
| `.claude/hooks.json` | Claude 钩子配置 (仅 claude 模式) | `generate_hooks_json` |
| `AGENTS.md` | Agent 指令（追加 hook 块） | `update_agents_md` |

#### 错误处理

- `--target` 不是目录 → 打印 stderr → exit 2
- 目标在 memory 仓库内部 → 记录 error → 返回失败
- 目录创建失败 → 捕获异常记录到 errors 列表
- 文件写入失败 → 捕获异常记录到 errors 列表
- 最终 `success = len(errors) == 0`

---

### 2.2 `memory-migrate` (migrate_project_memory.py)

#### 参数表

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--target` | Path | 是 | 无 | 目标项目根目录 |
| `--from` | str | 是 | 无 | 当前版本（如 `0.1.0`） |
| `--to` | str | 是 | 无 | 目标版本（如 `0.2.0`） |
| `--dry-run` | flag | 否 | False | 仅报告不修改 |
| `--json` | flag | 否 | False | JSON 格式输出 |
| `--version` | flag | 否 | 无 | 显示版本 |

#### 完整流程

```
main() 入口
  │
  ├─ 1. 解析 CLI 参数
  │     - --from 映射到 dest="from_version"（避免 Python 关键字冲突）
  │     - 验证 --target 是存在的目录（否则 exit 2）
  │
  ├─ 2. 调用 migrate_project_memory()
  │     │
  │     ├─ 2.1 验证 .memory/ 目录存在
  │     │     不存在 → 记录 error → 返回
  │     │
  │     ├─ 2.2 验证版本一致性
  │     │     读取 memory.lock，比较 version 字段与 --from
  │     │     不匹配 → 记录 error → 返回
  │     │     解析失败 → 记录 error → 返回
  │     │
  │     ├─ 2.3 发现迁移路径 (discover_migrations)
  │     │     策略 1: 直接查找 "from->to" 键
  │     │     策略 2: 链式查找 "from->mid" + "mid->to"
  │     │     未找到 → 记录 error（列出可用迁移）→ 返回
  │     │
  │     ├─ 2.4 执行迁移（逐个）
  │     │     - Dry-run: 记录 "would_execute"，生成模拟日志条目
  │     │     - 实际: 调用迁移函数 → 写 migrations.log → 记录 residue
  │     │     - 失败: 停止执行（break），记录 error
  │     │
  │     └─ 2.5 生成回滚计划 (plan_rollback)
  │           can_rollback=False（迁移不可自动回滚）
  │           列出回滚步骤
  │
  └─ 3. 输出报告
        - JSON/文本两种格式
        - 包含: 迁移执行状态、日志条目、residue、错误、回滚计划
        - 返回值: 0=成功, 1=失败, 2=用法错误
```

#### 迁移注册表

当前仅注册 1 条迁移路径:

| 路径 | 函数 | 操作 |
|------|------|------|
| `0.1.0->0.2.0` | `migrate_v010_to_v020` | 更新 memory.lock 版本 + adapter.toml 版本 |

#### 迁移函数 `migrate_v010_to_v020` 详情

```
1. 读取 memory.lock (JSON)
2. 记录旧版本到 migrated_from
3. 更新 version = "0.2.0"
4. 更新 updated = 当前日期
5. 写回 memory.lock
6. 读取 adapter.toml (文本替换)
7. 将 version = "0.1.0" 替换为 version = "0.2.0"
8. 返回 {success, detail, residue[]}
```

#### migrations.log 写入规则

```
格式: TIMESTAMP | VERSION_FROM | VERSION_TO | STATUS | DETAIL
例:   2024-01-15T10:30:00Z | 0.1.0 | 0.2.0 | success | Migrated from 0.1.0 to 0.2.0
```

- 文件不存在时创建并写入 header `# Migrations Log`
- 文件存在时追加（`"a"` 模式）
- Dry-run 模式下不写入文件，返回模拟行

#### 错误处理

- `.memory/` 不存在 → error 返回
- `memory.lock` 版本不匹配 → error 返回
- `memory.lock` 解析失败 → error 返回
- 无可用迁移路径 → error 返回（列出所有可用路径）
- 迁移执行失败 → 停止链式执行，记录 error
- adapter.toml 更新失败 → 不中断，记录到 residue

---

### 2.3 `memory-validate` (validate_project_memory.py)

#### 参数表

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--target` | Path | 是 | 无 | 目标项目根目录 |
| `--json` | flag | 否 | False | JSON 格式输出 |
| `--dry-run` | flag | 否 | False | 仅报告不读取文件 |
| `--version` | flag | 否 | 无 | 显示版本 |

#### 完整流程

```
main() 入口
  │
  ├─ 1. 解析 CLI 参数
  │     - 验证 --target 是存在的目录（否则 exit 2）
  │
  ├─ 2. 调用 validate_project_memory()
  │     │
  │     ├─ 2.1 Dry-run 模式: 记录所有"would check"条目，直接返回
  │     │
  │     ├─ 2.2 验证 .memory/ 目录存在
  │     │     不存在 → 记录 error → 返回
  │     │
  │     ├─ 2.3 check_required_files (7 个文件)
  │     │     memory.lock, adapter.toml, CANONICAL.md, PLAN.md,
  │     │     STATE.md, TASKS.md, migrations.log
  │     │
  │     ├─ 2.4 check_required_dirs (4 个目录)
  │     │     kb/projects, kb/decisions, kb/lessons, kb/global
  │     │
  │     ├─ 2.5 check_frontmatter (4 个 Markdown 文件)
  │     │     使用正则解析 YAML frontmatter
  │     │     CANONICAL.md: type, title, shortname, status, created, updated
  │     │     PLAN.md:      type, title, shortname, status, created
  │     │     STATE.md:     type, title, shortname, status, updated
  │     │     TASKS.md:     type, title, shortname, status
  │     │
  │     ├─ 2.6 check_lock_version
  │     │     解析 memory.lock（JSON 或 key=value 格式）
  │     │     比较 version 与 CURRENT_MEMORY_VERSION (0.2.0)
  │     │
  │     ├─ 2.7 check_adapter_version
  │     │     解析 adapter.toml（简单 key=value 解析器，无 TOML 依赖）
  │     │     读取 core.version 或 version 字段
  │     │     比较与 CURRENT_MEMORY_VERSION
  │     │
  │     ├─ 2.8 check_pollution
  │     │     递归扫描 .memory/ 下所有文件
  │     │     检查路径名和文件内容是否匹配污染模式:
  │     │       node_modules, __pycache__, .venv, target/,
  │     │       .gradle, .DS_Store, .git/
  │     │
  │     └─ 2.9 check_migrations_log
  │           验证文件存在、非空
  │           统计迁移记录行数（排除注释）
  │
  └─ 3. 输出报告
        - JSON: CheckResult.to_dict()
        - 文本: CheckResult.to_text() (格式化的 [PASS]/[FAIL] 报告)
        - 返回值: 0=全部通过, 1=有失败
```

#### 解析器实现细节

- **Frontmatter 解析**: 正则 `^---\s*\n(.*?)\n---` 提取 YAML 块，按行 `split(":")` 解析键值对
- **Lock 解析**: 先检测是否为 JSON（首字符 `{` 或 `[`），否则按 `key=value` 行解析
- **Adapter TOML 解析**: 追踪 `[section]` 状态，构建 `section.key` 格式的扁平字典
- **污染检测**: 对 `.md, .toml, .json, .lock, .log, .txt` 文件逐行扫描

---

### 2.4 `validate_memory_system.py` (未注册 CLI)

#### 定位
这是**系统级验证脚本**，验证 memory hook 系统的**代码层面**健康状况，而非项目目录结构。

#### 完整流程

```
main() 入口
  │
  ├─ 1. 准备 sys.path
  │     添加 _SCRIPT_DIR 和 _REPO_ROOT 到 sys.path
  │
  ├─ 2. check_gateway_import
  │     尝试 import memory_hook_gateway
  │     失败 → 打印报告 → exit 1
  │
  ├─ 3. check_core_builder_resolve
  │     导入 _resolve_core_builder，用 "legacy" provider 测试
  │     验证 builder 可调用
  │     失败 → 打印报告 → exit 1
  │
  ├─ 4. check_context_package
  │     用 builder 构建上下文包（传入完整参数集）
  │     验证返回 dict 的顶层键:
  │       status, host, event, schema_version, system_context, task_context
  │     验证 system_context 包含: boot_entry, state_entry
  │     验证 task_context 包含: session_id, event
  │
  ├─ 5. check_core_config_path
  │     验证 build_context_package_from_config 可从 memory_hook_core 导入
  │
  ├─ 6. check_v1_schema
  │     验证 build_context_package_simple 返回 context-package-v1
  │     检查 v1 结构: 有 paths, project, task，无 system_context
  │
  ├─ 7. check_package_imports
  │     验证 memory_core.tools 包的公开 API:
  │       build_context_package, CoreConfig
  │
  └─ 8. 打印汇总报告
        返回值: 0=全部通过, 1=有失败
```

#### 关键设计

- 使用 `ValidateResult` 类收集检查项，支持早期退出（import 或 builder resolve 失败后直接 exit）
- `check_context_package` 使用 `_empty_truth_basis()` 提供最小化的 truth-basis mock
- 验证 v1 schema 时通过 `assert` 确保结构正确性

---

## 3. init → validate → migrate 生命周期完整流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                     项目记忆生命周期                                 │
│                                                                     │
│  ┌─────────────┐      ┌──────────────┐      ┌───────────────────┐   │
│  │ memory-init │ ───> │memory-validate│ ───> │  memory-migrate   │   │
│  │ (初始化)    │      │  (验证)       │      │  (迁移)           │   │
│  └─────────────┘      └──────────────┘      └───────────────────┘   │
│        │                      │                       │             │
│        ▼                      ▼                       ▼             │
│  创建 .memory/          检查 .memory/           版本升级操作         │
│  创建 7 个文件           验证 7 个文件           更新 memory.lock    │
│  创建 4 个目录           验证 4 个目录           更新 adapter.toml   │
│  生成 hooks.json        检查 frontmatter        写入 migrations.log │
│  更新 AGENTS.md         检查版本号              支持回滚计划        │
│  安全守卫               污染检查                                │
│                                                                     │
│  典型流程:                                                          │
│  1. 新项目: memory-init → memory-validate（确认通过）               │
│  2. 版本升级: memory-validate（发现版本不匹配）                     │
│                → memory-migrate --from 0.1.0 --to 0.2.0             │
│                → memory-validate（确认通过）                        │
│  3. CI 检查: memory-validate --json（自动化验证）                   │
│  4. 安全预检: memory-init --dry-run（预览变更）                     │
│  5. 迁移预检: memory-migrate --dry-run（预览变更）                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 版本一致性保证

| 工具 | 版本常量 | 用途 |
|------|----------|------|
| init_project_memory | `CURRENT_MEMORY_VERSION = "0.2.0"` | 生成文件的版本 |
| validate_project_memory | `CURRENT_MEMORY_VERSION = "0.2.0"` | 验证期望版本 |
| migrate_project_memory | 无全局常量 | 依赖注册表中的版本映射 |

---

## 4. validate_project vs validate_system 的区别

| 维度 | `validate_project_memory.py` | `validate_memory_system.py` |
|------|------------------------------|------------------------------|
| **CLI 注册** | ✅ 已注册为 `memory-validate` | ❌ 未注册 |
| **验证对象** | 目标项目的 `.memory/` 目录结构 | memory hook 系统的代码模块 |
| **验证层面** | 文件系统 / 数据完整性 | Python 模块 / 运行时 |
| **检查内容** | 文件存在性、frontmatter、版本一致性、污染 | import 成功性、builder 可调用性、context package 结构 |
| **输入** | `--target` 项目路径 | 无参数（在 memory 仓库内执行） |
| **依赖** | 无外部模块依赖 | 需要 `memory_hook_gateway`, `memory_hook_core`, `memory_hook_schema` |
| **使用场景** | CI/项目验收/日常检查 | 开发者验证系统代码健康度 |
| **退出码** | 0=通过, 1=失败, 2=用法错误 | 0=通过, 1=失败 |
| **执行位置** | 任意业务项目根目录 | memory 仓库内部 |

**一句话总结**: `validate_project` 验的是**数据**（.memory/ 目录是否正确），`validate_system` 验的是**代码**（hook 系统模块是否可正常运行）。

---

## 5. 文件/目录操作清单

### 5.1 读取操作

| 文件 | 工具 | 操作 |
|------|------|------|
| `memory.lock` | init, migrate, validate | 读取 JSON 获取版本/项目信息 |
| `adapter.toml` | init, migrate, validate | 读取 TOML 获取版本/配置 |
| `CANONICAL.md` | validate | 读取 frontmatter |
| `PLAN.md` | validate | 读取 frontmatter |
| `STATE.md` | validate | 读取 frontmatter |
| `TASKS.md` | validate | 读取 frontmatter |
| `migrations.log` | migrate, validate | 读取/追加日志 |
| `.claude/hooks.json` | init | 读取现有钩子（幂等追加） |
| `AGENTS.md` | init | 读取检查标记 |
| git remote | init | `git -C target remote get-url origin` |
| `.memory/` 下所有文件 | validate | 递归扫描污染 |

### 5.2 写入操作

| 文件 | 工具 | 操作 |
|------|------|------|
| `.memory/` (6 个子目录) | init | 创建（mkdir -p） |
| `.memory/memory.lock` | init, migrate | 创建/更新版本 |
| `.memory/adapter.toml` | init, migrate | 创建/替换版本字符串 |
| `.memory/CANONICAL.md` | init | 创建 |
| `.memory/PLAN.md` | init | 创建 |
| `.memory/STATE.md` | init | 创建 |
| `.memory/TASKS.md` | init | 创建 |
| `.memory/migrations.log` | init, migrate | 创建初始记录/追加 |
| `.memory/kb/**/.keep` | init | 创建空文件 |
| `.claude/hooks.json` | init | 创建或追加钩子 |
| `AGENTS.md` | init | 追加/替换 hook 块 |

### 5.3 安全保护

| 保护机制 | 工具 | 实现 |
|----------|------|------|
| 防污染内存仓库 | init | `_is_memory_repo` 检测 + 拒绝初始化 |
| 文件不覆盖 | init | `file_path.exists()` 检查，已存在则跳过 |
| 幂等 hooks.json | init | 比对 (event, command) 键集合，只追加缺失项 |
| 幂等 AGENTS.md | init | BEGIN/END 标记检测，已存在则替换内容 |
| 污染检测 | validate | 7 种模式匹配路径和内容 |
| 版本一致性校验 | migrate | memory.lock 版本与 --from 参数比对 |

---

## 6. 错误处理与用户反馈机制

### 6.1 退出码约定

| 退出码 | 含义 | 适用工具 |
|--------|------|----------|
| 0 | 成功 | 全部 |
| 1 | 失败（业务逻辑错误） | 全部 |
| 2 | 用法错误（参数/路径无效） | init, migrate, validate |

### 6.2 错误处理模式

```python
# 模式 1: CLI 层参数验证
if not target.is_dir():
    print(f"Error: ...", file=sys.stderr)
    return 2

# 模式 2: 业务逻辑错误收集（不中断）
result["errors"].append("description")
result["success"] = len(result["errors"]) == 0

# 模式 3: 业务逻辑错误收集（中断）
result["errors"].append("description")
return result  # 立即返回

# 模式 4: 异常安全
try:
    content = file_path.read_text(encoding="utf-8")
except Exception as exc:
    result["errors"].append(f"failed: {exc}")

# 模式 5: 验证器检查项收集
result.record("check_name", False, "detail")
return 0 if result.all_passed else 1
```

### 6.3 用户反馈格式

**文本格式**:
```
============================================================
Project Memory Initialization Report
============================================================
  [CREATE] dir:.memory
  [CREATE] file:memory.lock
  [SKIP]   file:adapter.toml (already exists)
  [ERROR]  failed to create STATE.md: Permission denied
------------------------------------------------------------
  Status: FAILED
============================================================
```

**JSON 格式**:
```json
{
  "success": false,
  "dry_run": false,
  "target": "/path/to/project",
  "created": ["dir:.memory", "file:memory.lock"],
  "skipped": ["file:adapter.toml (already exists)"],
  "errors": ["failed to create STATE.md: Permission denied"]
}
```

---

## 7. 潜在问题与改进建议

### 7.1 已识别问题

| # | 严重度 | 位置 | 问题描述 |
|---|--------|------|----------|
| 1 | 中 | `init_project_memory.py` `_project_name()` | git remote 解析使用 `rsplit(":", 1)` 处理 SSH URL 时，若 URL 含端口号（如 `git@host:port/repo.git`），会错误提取端口号而非仓库名 |
| 2 | 中 | `migrate_project_memory.py` `migrate_v010_to_v020()` | adapter.toml 版本更新使用简单的 `str.replace()`，若文件中出现多次 `"0.1.0"` 字符串（如注释中），可能误替换 |
| 3 | 低 | `migrate_project_memory.py` `discover_migrations()` | 链式迁移只支持单跳（A→B→C），不支持多跳（A→B→C→D），且找到第一条链即返回，可能存在多条路径时的非确定性 |
| 4 | 低 | `validate_project_memory.py` `_parse_adapter_toml()` | 使用简易 TOML 解析器，不支持嵌套 section（如 `[routing.sub]`），不支持数组和布尔类型 |
| 5 | 低 | `validate_memory_system.py` | 硬编码依赖 `memory_hook_gateway` 等模块名称，重构时容易断裂 |
| 6 | 低 | `init_project_memory.py` `_is_memory_repo()` | 仅检查两个路径特征，若 memory 仓库结构变化（如重命名 memory_core），检测会失效 |
| 7 | 信息 | 全部 | `CURRENT_MEMORY_VERSION` 在 init 和 validate 中各定义一次，存在重复声明风险，建议在共享常量模块统一定义 |
| 8 | 信息 | `migrate_project_memory.py` | 迁移函数 `migrate_v010_to_v020` 标记为 "Sample migration"，实际项目中应替换为真实迁移逻辑或删除 |

### 7.2 改进建议

| # | 建议 | 理由 |
|---|------|------|
| 1 | 将 `CURRENT_MEMORY_VERSION` 提取到 `memory_core/constants.py` 统一引用 | 避免多处声明不一致 |
| 2 | `memory-migrate` 支持 `--auto-detect` 从 memory.lock 自动读取 `--from` | 减少用户手动指定版本的错误 |
| 3 | 迁移注册表支持版本范围或通配符 | 方便批量迁移 |
| 4 | 污染检测支持用户自定义排除模式（如 `.memoryignore` 文件） | 某些项目可能需要特殊目录 |
| 5 | `validate_memory_system.py` 注册为 CLI 入口（如 `memory-validate-system`） | 统一 CLI 体验 |
| 6 | init 工具增加 `--force` 选项覆盖已存在文件 | 支持重置场景 |
| 7 | migrate 工具增加 `--backup` 选项备份迁移前的文件 | 降低迁移风险 |
| 8 | 统一错误输出到 stderr（目前 validate 的输出到 stdout） | 符合 CLI 惯例 |

---

## 8. 架构总结

```
memory-core CLI 工具架构
├── memory-init          → 项目初始化（脚手架 + 钩子配置）
│   ├── 目录创建 (6 dirs)
│   ├── 文件创建 (7 files)
│   ├── 钩子配置 (claude 模式)
│   └── Agent 集成 (AGENTS.md)
│
├── memory-validate      → 项目验证（数据完整性）
│   ├── 文件/目录存在性
│   ├── Frontmatter 校验
│   ├── 版本一致性
│   └── 污染检测
│
├── memory-migrate       → 版本迁移（schema 升级）
│   ├── 路径发现（直接/链式）
│   ├── 迁移执行
│   ├── 日志记录
│   └── 回滚计划
│
└── validate_memory_system → 系统验证（代码健康度）
    ├── 模块 import 检查
    ├── Builder 调用检查
    ├── Context package 结构验证
    └── Schema v1 合规性
```

**设计优点**:
1. **零依赖**: 不依赖任何第三方库（TOML/YAML 解析均为手写）
2. **幂等性**: init 操作可重复执行，不覆盖已存在文件
3. **Dry-run**: 所有工具支持预览模式
4. **双输出**: 文本 + JSON 两种格式
5. **安全守卫**: 防止误操作污染 memory 仓库本身
