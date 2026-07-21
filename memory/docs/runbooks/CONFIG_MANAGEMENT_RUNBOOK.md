# 配置管理运维手册

> 适用范围：所有使用 memory-core 的消费项目
> 最后更新：2026-06-20

---

## 一、概述

每个消费项目的 `memory/system/` 目录包含三个核心配置文件。理解各自职责和更新时机是维护消费项目的基础。

### 三文件职责

| 文件 | 职责 | 谁更新 |
|------|------|--------|
| `adapter.toml` | 路由配置、项目标识、全局知识库开关 | memory-init 创建，migrate 更新版本 |
| `ownership.toml` | 所有权保护声明、hook 权威版本号 | memory-init 创建，version_sync 自动更新版本 |
| `memory.lock` | 项目与 memory-core 的版本绑定记录 | memory-init 创建，migrate 更新版本 |

### 辅助文件

| 文件 | 职责 |
|------|------|
| `migrations.log` | 迁移历史记录（时间戳 + from + to + status） |
| `manifest.json` | 完整性签名清单 |
| `backups/` | 迁移前备份目录 |

---

## 二、adapter.toml

### Schema

```toml
[core]
version = "0.8.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "<项目名>"
project_scope = "<项目作用域>"
host = "factory"

[global_kb]
enabled = true
root = "~/.memory/global-kb"
```

### 关键字段

- **[core].version**：当前 adapter 格式版本，必须与 memory.lock 一致
- **[routing].project_name**：项目唯一标识，用于路由和日志
- **[routing].project_scope**：知识作用域，默认与 project_name 相同
- **[global_kb].enabled**：全局知识库开关（v0.8.0+）
- **[global_kb].root**：全局知识库根路径（v0.8.0+）

### 全局知识库默认值

即使 adapter.toml 中没有显式写 `[global_kb]` 段，代码默认值也会生效：

- `enabled = true`（默认开启）
- `root = ~/.memory/global-kb`（默认路径）

显式写入 `[global_kb]` 段只是为了配置可见性，不影响运行时行为。这意味着：旧项目即使没跑迁移，只要代码升级到 v0.8.0+，全局知识库路由也会自动生效。

### 修改注意

- 不要手动编辑版本号，用迁移工具更新
- project_name / project_scope 修改后需同步更新 project-map 和 ownership.toml

---

## 三、ownership.toml

### Schema

```toml
schema_version = "memory-ownership-v1"
memory_version = "0.8.0"

[[domains]]
name = "<域名>"
path = "<相对路径>"
level = "critical" | "standard"
recursive = true
description = "<描述>"

[[resources]]
name = "<资源名>"
path = "<相对路径>"
level = "critical" | "standard"
domain = "<所属域>"  # 可选
description = "<描述>"

[policy]
project_name = "<项目名>"
```

### 关键字段

- **memory_version**：hook 实际读取的版本号，version_sync 自动同步到此
- **[[domains]]**：受所有权保护的目录列表
- **[[resources]]**：受所有权保护的具体文件列表
- **level**：`critical`（写入被拦截）或 `standard`（写入记录但不拦截）

### 自动版本同步

`version_sync.py` 由 hook wrapper 自动触发。当检测到 installed memory-core 版本与 ownership.toml 的 memory_version 不匹配时，自动 patch 到最新版本。

手动触发：

```bash
python3 -m memory_core.tools.version_sync           # 同步所有已知项目
python3 -m memory_core.tools.version_sync --target /path/to/project  # 同步单个项目
```

### 重要：version_sync 只更新 ownership.toml

version_sync **不更新** memory.lock 和 adapter.toml 的版本号。升级后需要单独检查这两个文件（参见 VERSION_SYNC_RUNBOOK.md）。

---

## 四、memory.lock

### Schema

```toml
[memory]
project = "<项目名>"
memory_version = "0.8.0"
schema_version = "context-package-v1"
adapter_version = "builtin"
locked_at = "<ISO 时间戳>"
lock_reason = "initial" | "upgrade to X.Y.Z"
```

### 关键字段

- **memory_version**：项目绑定的 memory-core 版本，迁移工具读此字段判断当前版本
- **schema_version**：context-package schema 版本
- **adapter_version**：adapter 实现版本（固定为 "builtin"）
- **lock_reason**：锁定原因（初始化 / 升级）

### 修改注意

- 版本号必须与 adapter.toml [core].version 一致
- 不要手动改版本号，用迁移工具更新
- locked_at 在每次迁移时自动更新

---

## 五、健康检查

### 验证配置完整性

```bash
python3 -m memory_core.tools.validate_project_memory /path/to/project
```

检查项包括：三文件存在性、版本一致性、schema 格式校验、ownership 域/资源完整性。

### 验证配置加载

```python
from memory_core.tools.adapter_toml_schema import load_adapter_toml
from pathlib import Path

cfg = load_adapter_toml(Path("/path/to/project/memory/system/adapter.toml"))
# 验证关键字段
assert cfg.version == "0.8.0"
assert cfg.global_kb_enabled == True
assert cfg.project_name  # 非空
```

### 版本一致性检查

三文件版本号必须一致。详见 [VERSION_SYNC_RUNBOOK.md](VERSION_SYNC_RUNBOOK.md)。
