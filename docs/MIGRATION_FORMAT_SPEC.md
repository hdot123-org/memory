---
type: "[SPEC]"
title: "migration 格式、幂等、回滚与日志"
shortname: SPEC-011
status: 草稿
created: 2026-04-29
updated: 2026-04-29
source: Issue-#11
scope: default
tags: [migration,idempotent,rollback,logging]
---

> 文档编号：SPEC-011 | 版本：V1.0 | 日期：2026-04-29
> 维护人：P3-版本子代理
> 状态：草稿

# migration 格式、幂等、回滚与日志规范

## 1. 目的

定义 memory-core 版本升级时 migration 脚本的格式与行为标准，确保：

1. migration 可重复执行而不破坏项目（幂等）
2. 失败时留下可追踪的 residue
3. 回滚策略明确可执行

## 2. migration 命名规范

### 2.1 目录结构

```
.memory/
├── migrations/
│   ├── 001_add_lock_fields.py
│   ├── 002_schema_v1_to_v2.py
│   └── 003_migrate_adapter_config.py
└── migrations.log
```

### 2.2 命名格式

采用 `<序号>_<描述>.<扩展名>` 格式：

```
<number>_<description>.<ext>
```

- `<number>`：三位数字序号，从 001 开始递增
- `<description>`：小写 snake_case，描述变更内容
- `<ext>`：扩展名，根据 migration 类型

### 2.3 扩展名与类型

| 扩展名 | 类型 | 说明 |
|--------|------|------|
| .py | Python 脚本 | 复杂逻辑迁移 |
| .toml | 配置变更 | 简单字段增删 |
| .json | 数据转换 | JSON 格式数据迁移 |

### 2.4 命名示例

```
001_add_lock_fields.toml       # 添加 memory.lock 字段
002_schema_v1_to_v2.py         # schema 版本升级
003_migrate_adapter_config.py  # adapter 配置迁移
004_add_policy_pack.json       # 添加 policy pack 数据
```

## 3. 幂等要求

### 3.1 定义

幂等 migration 指：重复执行同一 migration 不会改变最终状态，
不会报错，不会破坏项目数据。

### 3.2 实现模式

#### 3.2.1 Python migration 幂等模板

```python
#!/usr/bin/env python3
"""Migration 002: schema v1 to v2.

Idempotent: safe to run multiple times.
"""
import sys
import json
from pathlib import Path

MIGRATION_ID = "002"
MIGRATION_DESC = "schema_v1_to_v2"

def run(project_root: Path) -> dict:
    """Execute migration. Returns result dict."""
    lock_path = project_root / ".memory" / "memory.lock"
    if not lock_path.exists():
        return {"status": "skipped", "reason": "no memory.lock found"}

    # Parse current lock
    import tomllib
    with open(lock_path, "rb") as f:
        lock_data = tomllib.load(f)

    current_schema = lock_data.get("memory", {}).get("schema_version", "")

    # Already migrated?
    if current_schema == "context-package-v1":
        return {"status": "skipped", "reason": "already at target schema"}

    # Apply migration
    if current_schema == "wb-hook-v2":
        lock_data["memory"]["schema_version"] = "context-package-v1"
        with open(lock_path, "w") as f:
            import tomli_w
            tomli_w.dump(lock_data, f)
        return {"status": "applied", "from": "wb-hook-v2", "to": "context-package-v1"}

    return {"status": "error", "reason": f"unknown schema: {current_schema}"}

if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    result = run(root)
    print(json.dumps(result))
```

#### 3.2.2 TOML migration 幂等模板

```toml
# migration 001: add lock fields
# 声明需要确保存在的字段，执行方负责写入

[memory]
# 以下字段如果不存在则添加，已存在则不修改
lock_reason = ""
locked_at = ""
```

### 3.3 幂等检查清单

每个 migration 必须满足：

- [ ] 执行前检查当前状态
- [ ] 如果已处于目标状态，返回 skipped
- [ ] 不会覆盖已手动设置的值
- [ ] 不会删除不属于自己的字段
- [ ] 失败时不回滚已成功的子操作（由回滚机制处理）

## 4. rollback 记录格式

### 4.1 rollback 触发

当 migration 执行失败时：

1. 记录失败信息到 migrations.log
2. 生成 rollback 记录
3. 不自动执行回滚（避免部分回滚破坏数据）
4. 由人工或主线程决定回滚策略

### 4.2 rollback 记录格式

```json
{
  "rollback_id": "RB-002-20260429-001",
  "migration_id": "002",
  "migration_desc": "schema_v1_to_v2",
  "project_path": "/Users/busiji/tool/workbot",
  "failed_at": "2026-04-29T10:30:00Z",
  "error": "tomllib.TOMLDecodeError: ...",
  "state_before": {
    "memory_version": "0.1.0",
    "schema_version": "wb-hook-v2",
    "adapter_version": "builtin"
  },
  "state_after_partial": {
    "memory_version": "0.1.0",
    "schema_version": "wb-hook-v2",
    "adapter_version": "builtin"
  },
  "residue": [
    "memory.lock backup created at .memory/backups/memory.lock.002.bak"
  ],
  "rollback_action": "restore .memory/backups/memory.lock.002.bak"
}
```

### 4.3 回滚策略

| 场景 | 策略 |
|------|------|
| 单文件变更 | 从备份恢复 |
| 多文件变更 | 按反向 migration 执行 |
| 数据转换 | 保留原始数据，反向转换 |
| 不可逆变更 | 标记为 manual-resolve |

### 4.4 备份规则

每个 migration 执行前必须：

1. 备份将被修改的文件到 .memory/backups/
2. 备份文件名格式：<原文件名>.<migration_id>.bak
3. 保留最近 3 个版本的备份

## 5. .memory/migrations.log 格式

### 5.1 文件格式

migrations.log 是 NDJSON（每行一个 JSON 对象）格式：

```json
{"ts":"2026-04-29T10:00:00Z","migration_id":"001","desc":"add_lock_fields","project":"/path/to/proj","status":"applied","duration_ms":12,"details":{"from":"none","to":"v1"}}
{"ts":"2026-04-29T10:01:00Z","migration_id":"002","desc":"schema_v1_to_v2","project":"/path/to/proj","status":"applied","duration_ms":45,"details":{"from":"wb-hook-v2","to":"context-package-v1"}}
{"ts":"2026-04-29T10:05:00Z","migration_id":"003","desc":"migrate_adapter_config","project":"/path/to/proj","status":"failed","duration_ms":3,"details":{"error":"KeyError: adapter","residue":"backup created"}}
{"ts":"2026-04-29T10:06:00Z","migration_id":"003","desc":"migrate_adapter_config","project":"/path/to/proj","status":"rolled_back","duration_ms":5,"details":{"rollback_id":"RB-003-20260429-001"}}
```

### 5.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ts | ISO-8601 | 是 | 事件时间戳 |
| migration_id | string | 是 | 三位序号 |
| desc | string | 是 | migration 描述 |
| project | string | 是 | 项目绝对路径 |
| status | enum | 是 | applied/skipped/failed/rolled_back |
| duration_ms | int | 否 | 执行耗时（毫秒） |
| details | object | 否 | 附加信息 |

### 5.3 status 枚举

| status | 含义 |
|--------|------|
| applied | 成功应用 |
| skipped | 已处于目标状态，跳过 |
| failed | 执行失败 |
| rolled_back | 已回滚 |

### 5.4 residue 追踪

当 status 为 failed 时，details 中必须包含：

- error：错误信息
- residue：已产生的副作用描述
- rollback_action：建议的回滚操作

## 6. migration 执行流程

```
读取 memory.lock -> 对比目标版本
    |
    +-- 需要 migration?
        |
        +-- 否 -> 结束
        |
        +-- 是 -> 按序号顺序执行
            |
            +-- 读取 001_xxx.py
            |   |
            |   +-- 创建备份
            |   +-- 执行
            |   +-- 记录到 migrations.log
            |   +-- 成功 -> 继续下一个
            |   +-- 失败 -> 记录 residue，停止，报告
            |
            +-- 读取 002_xxx.py
            |   ...
            |
            +-- 全部完成 -> 更新 memory.lock memory_version
```

## 7. 验收标准

- [x] migration 命名规范明确（序号_描述.扩展名）
- [x] 幂等要求定义（重复执行不会破坏项目）
- [x] rollback 记录格式定义
- [x] migrations.log 格式定义（NDJSON）
- [x] 失败时留下可追踪 residue
- [x] 回滚策略明确（备份恢复 / 反向 migration / manual-resolve）
