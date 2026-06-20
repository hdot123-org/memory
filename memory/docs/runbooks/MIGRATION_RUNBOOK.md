# 消费项目迁移运维手册

> 适用范围：所有使用 memory-core 的消费项目
> 最后更新：2026-06-20

---

## 一、概述

当 memory-core 发布新版本时，消费项目需要迁移到新版本。memory-core 提供迁移工具 `migrate_project_memory.py`，支持版本间结构迁移。

### 迁移工具能力

- 指定 `--from` 和 `--to` 版本
- 幂等：已迁移到目标版本则 noop
- 拒绝降级
- 迁移前自动备份
- 迁移日志原子追加（POSIX fcntl 锁）
- 失败自动回滚
- 支持 `--dry-run` 预检

### 已注册的迁移路径

| 路径 | 变更内容 |
|------|---------|
| `0.1.0 -> 0.8.0` | 初始格式到当前版本（一步到位） |
| `0.4.0 -> 0.5.0` | `.memory/` 迁移到 `memory/system/`，模板到 `memory/kb/projects/` |
| `0.7.0 -> 0.8.0` | 注入 `[global_kb]` 段，更新版本号 |

跨版本迁移（如 0.5 直接到 0.8）：如果注册表没有直接路径或链式路径，CLI 会报错。此时直接调用目标版本的迁移函数（见下文）。

---

## 二、迁移前检查

### 检查当前版本

```bash
grep memory_version <project>/memory/system/memory.lock
grep '^version' <project>/memory/system/adapter.toml | head -1
```

### 检查目标版本

```bash
python3 -c "from memory_core.constants import CURRENT_MEMORY_VERSION; print(CURRENT_MEMORY_VERSION)"
```

### Dry-run 预检

```bash
python3 -m memory_core.tools.migrate_project_memory \
  --target /path/to/project --from <当前版本> --to <目标版本> --dry-run --json
```

如果返回 `errors: ["No migration path found..."]`，说明注册表缺少跳板，需用函数直调方式（见第三节）。

---

## 三、执行迁移

### 方式一：CLI 工具（有注册路径时）

```bash
python3 -m memory_core.tools.migrate_project_memory \
  --target /path/to/project --from 0.7.0 --to 0.8.0
```

工具会自动：
1. 在 `memory/system/backups/` 创建备份
2. 执行迁移函数
3. 更新 memory.lock / adapter.toml
4. 追加 migrations.log
5. 生成 ownership.toml（旧项目没有时）
6. 更新 integrity manifest

### 方式二：直接调用迁移函数（无注册路径时）

当 CLI 报 "No migration path found" 时，直接调用目标版本的迁移函数：

```python
from memory_core.tools.migrate_project_memory import migrate_v070_to_v080
from pathlib import Path

# 参数是 memory/system/ 目录
result = migrate_v070_to_v080(Path("/path/to/project/memory/system"))
```

注意：此方式不创建备份、不写 migrations.log。建议手动备份后再操作。

### 方式三：重新初始化（极端情况）

如果项目配置严重损坏，可以删除 `memory/system/` 重新跑 `memory-init`。但这会丢失 ownership.toml 和 migrations.log，慎用。

---

## 四、迁移后验证

### 版本一致性

```bash
# 三文件版本号必须一致
lock_v=$(grep memory_version <project>/memory/system/memory.lock | sed 's/.*= *"//;s/".*//')
adapter_v=$(grep '^version' <project>/memory/system/adapter.toml | head -1 | sed 's/.*= *"//;s/".*//')
own_v=$(grep memory_version <project>/memory/system/ownership.toml | sed 's/.*= *"//;s/".*//')
echo "lock=$lock_v adapter=$adapter_v ownership=$own_v"
```

### 健康检查

```bash
python3 -m memory_core.tools.validate_project_memory /path/to/project
```

### 配置加载验证

```python
from memory_core.tools.adapter_toml_schema import load_adapter_toml
from pathlib import Path

cfg = load_adapter_toml(Path("/path/to/project/memory/system/adapter.toml"))
print(f"version={cfg.version}, global_kb_enabled={cfg.global_kb_enabled}")
```

---

## 五、迁移注册表维护

新增版本迁移时，必须在 `migrate_project_memory.py` 做两件事：

1. **实现迁移函数**：`def migrate_v0XY_to_v0XY(memory_root: Path) -> dict`
2. **注册路径**：在 `MIGRATION_REGISTRY` 添加 `f"0.X.0->0.Y.0": migrate_v0XY_to_v0XY`

如果不注册，CLI 的 `discover_migrations()` 无法发现该路径，消费项目走 CLI 会报错。

### 链式路径发现

`discover_migrations()` 支持自动发现两步链式路径（A→B→C）。如果 A→C 没有直接注册，但 A→B 和 B→C 都注册了，会自动链式执行。只支持两步链，三步以上不自动发现。
