# memory-core

为任意项目提供标准化的 `.memory/` 目录结构与版本管理能力。memory-core 只提供协议、模板、schema 和工具，不存储任何业务数据。

## 安装

### 从 GitHub Release 安装

```bash
gh release download v0.2.0 --repo hdot123/memory --pattern "*.whl" && pip install memory_core-0.2.0-py3-none-any.whl
```

### 从源码安装

```bash
pip install git+https://github.com/hdot123/memory.git@v0.2.0
```

### 升级

更换版本号并加 `--upgrade`：

```bash
pip install --upgrade git+https://github.com/hdot123/memory.git@v0.3.0
```

## 快速开始

三个核心 CLI 命令，覆盖项目接入的全生命周期：

### 1. 初始化 — `memory-init`

在目标项目中创建 `.memory/` 标准目录结构：

```bash
memory-init --target /path/to/project
```

**选项：**

| 选项 | 说明 |
|---|---|
| `--dry-run` | 只输出将要执行的操作，不实际写入文件 |
| `--json` | 以 JSON 格式输出结果，便于脚本集成 |

```bash
# 预览不执行
memory-init --target /path/to/project --dry-run

# JSON 输出
memory-init --target /path/to/project --dry-run --json
```

### 2. 校验 — `memory-validate`

检查项目 `.memory/` 目录是否完整、schema 是否合规：

```bash
memory-validate --target /path/to/project
```

校验内容包括：
- 必需文件是否存在（`memory.lock`、`adapter.toml`、`CANONICAL.md`、`PLAN.md`、`STATE.md`、`TASKS.md`、`migrations.log`）
- Markdown 文件的 frontmatter 字段是否完整
- `memory.lock` 与 `adapter.toml` 版本是否兼容
- **污染防护**：检测 memory 仓库是否被写入了业务数据

**选项：**

| 选项 | 说明 |
|---|---|
| `--dry-run` | 只执行检查，不修改任何文件 |
| `--json` | 以 JSON 格式输出校验结果 |

### 3. 版本迁移 — `memory-migrate`

在 schema 版本之间迁移：

```bash
memory-migrate --target /path/to/project --from 0.1.0 --to 0.2.0
```

**选项：**

| 选项 | 说明 |
|---|---|
| `--from <version>` | 当前版本号 |
| `--to <version>` | 目标版本号 |
| `--dry-run` | 预览迁移步骤，不实际执行 |
| `--json` | 以 JSON 格式输出迁移结果 |

## `.memory/` 目录结构

`memory-init` 后在项目根目录下生成：

```
.memory/
├── memory.lock        # 版本锁定文件，记录当前 schema 版本
├── adapter.toml       # 项目适配器配置
├── CANONICAL.md       # 项目规范
├── PLAN.md            # 执行计划
├── STATE.md           # 项目状态
├── TASKS.md           # 任务清单
├── migrations.log     # 迁移日志
└── kb/
    ├── projects/      # 项目知识
    ├── decisions/     # 决策记录
    ├── lessons/       # 经验教训
    └── global/        # 全局规范
```

## 版本管理

### memory.lock

`memory.lock` 是项目 `.memory/` 目录的版本锁定文件，记录当前使用的 schema 版本。每次 `memory-init` 会创建它，`memory-validate` 会校验它，`memory-migrate` 会更新它。

### 升级流程

```
init → validate → migrate
```

1. **初始化**：新项目用 `memory-init` 创建 `.memory/` 结构
2. **校验**：用 `memory-validate` 确认当前结构完整
3. **迁移**：schema 升级时用 `memory-migrate --from <old> --to <new>` 执行迁移，`migrations.log` 会记录每次迁移的详细信息

## 设计原则

- **业务项目数据隔离**：所有业务数据只存在于业务项目自己的 `.memory/` 下，memory 仓库不存储任何业务数据
- **协议层中立**：memory 仓库只提供协议、模板、schema 和工具，不内建任何单项目默认绑定
- **不污染**：`memory-validate` 内置 pollution guard，防止 memory 仓库被写入业务状态

## 开发与测试

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python -m pytest tests/
```

## 版本

- **当前版本**：v0.2.0
- **Python 要求**：>= 3.9
