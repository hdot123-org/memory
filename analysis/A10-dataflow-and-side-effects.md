# A10: 数据流与副作用分析

> 分析对象：`workspace/tools/` 目录下的 memory hook 系统
> 日期：2026-04-27

---

## 1. 数据流图（文字描述）

从 hook 事件入口到 artifact 写出的完整数据路径如下：

```
[Git hook event]                    # post-commit / pre-push / 其他触发
       │
       ▼
[CLI entry: memory_hook_gateway.py] # argparse 解析，分发事件
       │
       ├── MEMORY_HOOK_ADAPTER ─────► 选择 adapter（默认 workbot）
       │
       ├── Env vars 收集 ────────────► CMUX_SURFACE_ID, CMUX_WORKSPACE_ID, PWD 等
       │
       ├── Git 查询 (subprocess) ───► git diff, git log, git status
       │         │
       │         ▼
       │    raw output ─────────────► 截断 + 安全化 (truncate_to_limit / sanitize_for_json)
       │
       ├── Context builder ─────────► build_context_package_xxx()
       │         │                    组合事件元数据、git 上下文、policy/scope 配置
       │         ▼
       │    dict package ───────────► JSON-serializable 结构
       │
       └── dispatch ────────────────► _dispatch_to_provider()
                    │
                    ├── [local] ────► _get_artifact_sink().write(package)
                    │                     │
                    │                     ├── ArtifactWriter.write()
                    │                     │     生成文件名: {host}.{event}.{timestamp}.jsonl
                    │                     │
                    │                     └── ArtifactSinkImpl.write()
                    │                           open(EVENT_LOG, "a") → json.dumps → append
                    │
                    ├── [delegate: codex] ──► subprocess.run(codex ...) → stdout/stderr 透传
                    │
                    ├── [delegate: claude] ──► subprocess.run(claude ...) → stdout/stderr 透传
                    │
                    └── [stdout] ───────────► sys.stdout.write(json.dumps(package))  # --json 模式
```

**核心路径摘要**：事件触发 → 环境变量收集 → git 子进程查询 → context 组装 → provider 分发 →
本地写入 JSONL 文件 或 外部 delegate 子进程。

---

## 2. 文件系统副作用

### 2.1 写入点清单

| # | 位置 | 目标 | 写入内容 | 写入条件 |
|---|------|------|----------|----------|
| W1 | `ArtifactSinkImpl.write()` | `EVENT_LOG` (.jsonl) | JSON 序列化的事件 package，每行一条 | 每次 dispatch 成功时 |
| W2 | `ArtifactSinkImpl._ensure_dirs()` | 目录 | `CONTEXT_ROOT` 和 `EVENT_LOG.parent` | 首次写入前，`mkdir(parents=True, exist_ok=True)` |
| W3 | `ErrorSinkImpl.log_error()` | `ERROR_LOG` (.log) | `[timestamp] [component] [error] message \| context=...` | 每次调用 `log_error` 时 |
| W4 | `ArtifactWriter.write()` | 间接调用 W1 | 通过 `_sink.write(package)` 写入 | 包装 W1，增加 try/except |
| W5 | `cmux_hook_state:acquire_lock()` | 锁文件 (lock) | 空内容占位 | 获取 flock 时 `open("a+")` |
| W6 | `cmux_hook_state:atomic_write_json()` | 目标 JSON 文件 | `json.dumps()` 序列化的 state | 原子写入（tempfile + fdopen + rename） |
| W7 | `sys.stdout.write()` | stdout | JSON package 或子进程输出 | `--json` 模式或 delegate 透传 |
| W8 | `sys.stderr.write()` | stderr | 子进程 stderr | delegate 失败时透传 |

### 2.2 写入路径（运行时变量）

```
CONTEXT_ROOT  ──► _MEMORY_ROOT/contexts/     (可配置)
EVENT_LOG     ──► _MEMORY_ROOT/events.jsonl  (可配置)
ERROR_LOG     ──► _MEMORY_ROOT/logs/errors.log (可配置)
```

其中 `_MEMORY_ROOT` 默认值为 `~/.codex/memory/`。

### 2.3 原子性保障

- **cmux_hook_state** 使用了 `tempfile.mkstemp()` + `os.fdopen()` + `os.replace()` 的原子写入模式，
  并配合 `fcntl.flock()` 做进程级互斥。
- **EVENT_LOG** 和 **ERROR_LOG** 使用 `"a"` (append) 模式，多进程并发写入时依赖操作系统级
  append 原子性（POSIX 保证追加写的原子性，但无锁保护）。

---

## 3. subprocess 使用

### 3.1 调用清单

| # | 调用位置 | 命令 | 用途 |
|---|----------|------|------|
| S1 | `GitContextCollector.collect()` | `git diff / git log / git status` | 收集变更集、提交历史、工作区状态 |
| S2 | `_run_git_diff()` | `git diff --cached / git diff HEAD` | 获取 staged/unstaged diff |
| S3 | `_get_head_commit()` | `git rev-parse HEAD` | 获取当前 commit SHA |
| S4 | `_delegate_codex()` | `codex ...` (外部命令) | 将事件转发给 Codex CLI |
| S5 | `_delegate_claude()` | `claude ...` (外部命令) | 将事件转发给 Claude CLI |
| S6 | `shutil.which()` 间接调用 | 系统 PATH 搜索 | 检查 codex/claude 等命令是否可用 |

### 3.2 可注入性设计

`GitContextCollector` 和 `WorkbotRuntimeProfileAdapter` 的 `runner` 参数允许注入
`subprocess.run` 的替代品（包括 `noop`），这使得这些组件在测试中可以被完全 mock。

### 3.3 风险评估

- S4/S5 调用外部 CLI，依赖 PATH 中存在 `codex`/`claude` 可执行文件
- 命令拼接方式：使用 `shlex.quote()` 对参数做了基本的转义保护
- 超时设置：使用 `timeout=30` 防止子进程挂起

---

## 4. 环境变量依赖

### 4.1 环境变量清单

| 变量名 | 读取位置 | 默认值 | 用途 | 是否必需 |
|--------|----------|--------|------|----------|
| `MEMORY_HOOK_ADAPTER` | gateway:88 | `"workbot"` | 选择 adapter 名称 | 否 |
| `MEMORY_HOOK_EXTERNAL_CORE_MODULE` | gateway:172 | `"workspace.tools.memory_hook_core"` | 外部 core 模块路径 | 否 |
| `MEMORY_HOOK_EXTERNAL_CORE_FUNC` | gateway:173 | `"build_context_package_core"` | 外部 core 函数名 | 否 |
| `MEMORY_HOOK_CORE_PROVIDER` | gateway:798, rollback:24 | `"legacy"` | 选择 provider（legacy / external） | 否 |
| `MEMORY_HOOK_FORCE` | gateway:356 | - | 强制执行 hook（跳过条件检查） | 否 |
| `WORKBOT_FORCE_HOOK` | gateway:356 | - | 同 MEMORY_HOOK_FORCE 的别名 | 否 |
| `MEMORY_HOOK_SHADOW_RUN` | gateway:816 | - | 影子模式（执行但不写入） | 否 |
| `MEMORY_HOOK_POLICY_PACK_PATH` | impls:237, adapters/workbot_policy:44 | - | policy pack 文件路径 | 条件必需 |
| `MEMORY_HOOK_SCOPE_CONFIG_PATH` | impls:529 | - | scope config 文件路径 | 否 |
| `CMUX_SURFACE_ID` | gateway:792, impls:62,78,109,138 | - | cmux 表面对象 ID | **必需** (impls 会 raise) |
| `CMUX_WORKSPACE_ID` | gateway:793, impls:108,136 | - | cmux 工作区 ID | **必需** (impls 会 raise) |
| `CMUX_HOOK_STATE_FILE` | adapters/workbot_runtime_profile:253 | - | hook state 文件路径 | 否 |
| `PWD` | gateway:329 | - | 当前工作目录备用 | 否 |

### 4.2 分类

- **运行时标识**（必需）：`CMUX_SURFACE_ID`, `CMUX_WORKSPACE_ID`
- **模式切换**：`MEMORY_HOOK_ADAPTER`, `MEMORY_HOOK_CORE_PROVIDER`
- **调试/测试**：`MEMORY_HOOK_FORCE`, `MEMORY_HOOK_SHADOW_RUN`
- **路径配置**：`MEMORY_HOOK_POLICY_PACK_PATH`, `MEMORY_HOOK_SCOPE_CONFIG_PATH`

---

## 5. 外部依赖清单

除标准库（`pathlib`, `json`, `os`, `subprocess`, `shutil`, `argparse`, `sys`,
`datetime`, `re`, `contextlib`, `fcntl`, `tempfile`, `time`, `abc`, `dataclasses`, `typing`）之外：

| 依赖 | 使用位置 | 用途 |
|------|----------|------|
| **无第三方依赖** | — | 整个 tools/ 目录仅使用 Python 标准库 |

项目刻意保持零外部 Python 依赖，所有功能通过标准库 + 子进程调用外部 CLI 实现。

---

## 6. 副作用隔离评估

### 6.1 集中程度：中等偏上

**良好隔离的部分：**
- `ArtifactSinkImpl` 和 `ErrorSinkImpl` 将文件写入集中在两个类中，实现了
  `ArtifactSink` / `ErrorSink` 接口，便于替换实现
- `ArtifactWriter` 作为防腐层，把 filename 生成逻辑和错误处理包了一层
- `cmux_hook_state.py` 的 `atomic_write_json()` 封装了完整的原子写入 + flock 模式
- `GitContextCollector` 的 `runner` 参数允许注入 mock subprocess

**散落的部分：**
- `subprocess.run()` 在 `gateway.py` 中有 4 处直接调用（S2-S5），未经封装
- `sys.stdout.write()` / `sys.stderr.write()` 散布在 gateway 的多个函数中
- 环境变量读取散落在 `gateway`, `impls`, `adapters`, `rollback` 四个文件中，
  没有统一的配置层
- `CONTEXT_ROOT`, `EVENT_LOG`, `ERROR_LOG` 等路径是模块级全局变量

### 6.2 隔离评分

| 维度 | 评分 (1-5) | 说明 |
|------|------------|------|
| 文件 I/O 集中度 | 4 | ArtifactSink/ErrorSink 接口做得好 |
| subprocess 集中度 | 3 | 部分有封装，但 gateway 内有直接调用 |
| 环境变量集中度 | 2 | 分散在 4+ 文件中，无统一配置层 |
| 全局状态 | 2 | 多个模块级全局变量 |
| 可测试性 | 4 | 多数组件支持依赖注入 |

---

## 7. 改进建议

### 7.1 统一环境变量配置层

当前环境变量散落在 `gateway`、`impls`、`adapters`、`rollback` 四个模块中。
建议引入一个 `EnvConfig` 数据类或模块，集中声明、读取和校验所有环境变量：

```python
@dataclass(frozen=True)
class EnvConfig:
    surface_id: str
    workspace_id: str
    adapter: str = "workbot"
    core_provider: str = "legacy"
    force: bool = False
    shadow_run: bool = False
    ...

    @classmethod
    def from_env(cls) -> "EnvConfig": ...
```

**收益**：环境变量读取点从 15+ 处收敛到 1 处；缺失校验集中在构造函数中。

### 7.2 封装 subprocess 调用为独立组件

`gateway.py` 中有 4 处直接 `subprocess.run()` 调用。建议提取为 `ExternalCommandRunner`
类，至少把 git 相关命令（S2-S3）和 delegate 命令（S4-S5）分开。

**收益**：子进程调用的超时、错误处理、参数转义等策略统一；测试时只需 mock 一个对象。

### 7.3 消除模块级全局路径变量

`CONTEXT_ROOT`, `EVENT_LOG`, `ERROR_LOG`, `_MEMORY_ROOT` 是模块级全局变量。
建议改为 `PathConfig` 数据类，通过依赖注入传入需要路径的组件。

**收益**：测试时不再需要 monkeypatch 模块变量；多实例运行（不同 workspace）不再冲突。

### 7.4 为 append 模式的日志文件添加锁保护

`EVENT_LOG` 和 `ERROR_LOG` 使用 `"a"` 模式但无锁。虽然 POSIX 保证单次 `write()` 的原子性，
但 `json.dumps() + "\n"` 作为两次写入（Python 的 `write` 可能分多次系统调用），
在极端并发下可能交错。

建议复用 `cmux_hook_state.py` 中的 flock 模式，或在 `_get_artifact_sink()` 级别
加一个文件锁。

### 7.5 环境变量改为配置优先（env var 作为 fallback）

目前 `CMUX_SURFACE_ID` 等关键标识只能从环境变量获取。建议支持配置文件
（如 `~/.codex/memory/config.json`）作为首选，环境变量作为覆盖层。

**收益**：用户不需要在每个 shell session 中 export 这些变量；配置可版本管理（不含敏感信息时）。
