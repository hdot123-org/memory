# 版本同步运维手册

> 适用范围：所有使用 memory-core 的消费项目
> 最后更新：2026-06-20 | 基于 v0.8.0 版本同步排查总结

---

## 一、概述

memory-core 的消费项目有三个配置文件携带版本号。升级 memory-core 后，这三个文件的版本号必须保持一致，否则会造成审计混乱和迁移工具判断异常。

### 三文件版本号

| 文件 | 路径 | 作用 | 自动同步 |
|------|------|------|---------|
| `ownership.toml` | `memory/system/ownership.toml` | hook 实际读取的权威版本 | 是（hook wrapper 自动触发 version_sync） |
| `memory.lock` | `memory/system/memory.lock` | 项目绑定记录 | **否** |
| `adapter.toml` | `memory/system/adapter.toml` | 路由/配置 | **否** |

### 常见不一致场景

`ownership.toml` 已通过 `version_sync.py` 自动更新，但 `memory.lock` 和 `adapter.toml` 停在旧版本。这是因为 version_sync 只 patch ownership.toml，不碰另外两个文件。

---

## 二、检查方法

### 快速检查（单项目）

```bash
lock_v=$(grep memory_version <project>/memory/system/memory.lock | sed 's/.*= *"//;s/".*//')
adapter_v=$(grep '^version' <project>/memory/system/adapter.toml | head -1 | sed 's/.*= *"//;s/".*//')
own_v=$(grep memory_version <project>/memory/system/ownership.toml | sed 's/.*= *"//;s/".*//')
echo "lock=$lock_v adapter=$adapter_v ownership=$own_v"
```

三个版本号必须一致。

### 批量检查（所有已知项目）

```bash
python3 -m memory_core.tools.version_sync --json
```

输出中 `patched` 列表表示 ownership.toml 已同步，`skipped` 表示已是一致。

注意：version_sync 只检查 ownership.toml，不检查 memory.lock / adapter.toml。需手动确认后者。

---

## 三、修复方法

### 方法一：调用迁移函数（推荐）

当 memory.lock / adapter.toml 版本落后时，调用对应版本的迁移函数。该函数会同时更新两个文件并注入新配置段。

```python
from memory_core.tools.migrate_project_memory import migrate_v070_to_v080
from pathlib import Path

# 注意：参数是 memory/system/ 目录，不是项目根目录
result = migrate_v070_to_v080(Path("/path/to/project/memory/system"))
print(result["success"], result["detail"])
```

该函数操作：
1. 在 adapter.toml 注入 `[global_kb]` 段（v0.8.0 新增）
2. 更新 memory.lock 的 memory_version 到 0.8.0
3. 更新 adapter.toml 的 [core].version 到 0.8.0
4. 幂等：已有目标配置则跳过

### 方法二：CLI 迁移工具

```bash
python3 -m memory_core.tools.migrate_project_memory \
  --target /path/to/project --from <当前版本> --to <目标版本>
```

注意：CLI 的 `discover_migrations()` 依赖迁移注册表（MIGRATION_REGISTRY）。如果源版本和目标版本之间缺少注册的跳板路径，会报 "No migration path found"。

**跨版本迁移**（如 0.5 直接到 0.8）：如果注册表缺中间跳板，优先用方法一直接调用目标版本的迁移函数。

### 方法三：version_sync 同步 ownership.toml

如果只有 ownership.toml 落后（memory.lock / adapter.toml 已是最新）：

```bash
# 同步所有已知项目
python3 -m memory_core.tools.version_sync

# 同步单个项目
python3 -m memory_core.tools.version_sync --target /path/to/project
```

---

## 四、三文件不一致的影响

| 影响层面 | 严重程度 | 说明 |
|---------|---------|------|
| 运行时 | 无 | hook 只读 ownership.toml；adapter.toml 缺段时有代码默认值 |
| 审计排查 | 中 | memory.lock 版本号误导排查方向 |
| 迁移工具 | 高 | migrate_project_memory 读 memory.lock 判断当前版本，版本号错误导致迁移路径判断异常 |

---

## 五、预防措施

1. **每次 memory-core 大版本升级后**，检查所有消费项目的三文件版本一致性
2. **version_sync 自动覆盖 ownership.toml，但不覆盖 memory.lock / adapter.toml** — 后两者需要手动调迁移函数
3. **迁移注册表维护**：新增版本时，在 MIGRATION_REGISTRY 补齐版本跳板路径
4. **新项目初始化**：`memory-init` 会自动写入最新版本的三文件，无需额外处理
