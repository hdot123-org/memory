# D-009: 生命周期事件按项目分片存储

## 状态
accepted

## 日期
2026-08-01

## 背景

生命周期事件原存储在全局单文件 `events.jsonl` 中。随着项目和事件增长，该文件会成为：

1. **性能瓶颈**：每次 hook 调用都追加写入同一文件，并发项目争抢同一 inode
2. **运维困难**：无法按项目归档或清理，全量文件无限增长
3. **迁移风险**：单文件损坏影响所有项目的历史记录

## 决策

将事件存储从全局单文件改为**按项目 × 按日期分片**：

```
projects/{project_id}/events/{YYYY-MM-DD}.jsonl
```

配套机制：
- **自动清理**：`_cleanup_old_event_files()` 按 `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS`（默认 30 天）轮转，每天每项目最多一次
- **迁移工具**：`memory-lifecycle-migrate` CLI 将旧 `events.jsonl` 迁移到新结构，幂等运行
- **向后兼容**：`rebuild_path_index()` 和 `hook_event_stats.py` 不依赖事件文件，无需修改

## 理由

- **隔离性**：不同项目的事件完全隔离，无并发写入争抢
- **可维护性**：按日期分片便于归档和清理，单日文件损坏不影响其他日期
- **零破坏性变更**：事件日志仅用于追加审计，无任何消费端读取

## 影响

- `record_project_lifecycle()` 写入路径变更
- 返回字典 `event_log` 字段指向新路径
- 全局 `events.jsonl` 弃用但不删除，可通过 CLI 迁移
- 新增 29 个测试（8 sharding + 7 retention + 7 migration + 7 compat/cross）

## PR
- PR #231: 生命周期事件按项目分片 + 自动轮转清理
- PR #232: 健壮性改进（5 项 scrutiny 修复 + 版本一致性）
