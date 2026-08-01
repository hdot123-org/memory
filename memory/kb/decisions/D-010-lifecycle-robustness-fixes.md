# D-010: 生命周期工具健壮性修复策略

## 状态
accepted

## 日期
2026-08-01

## 背景

PR #231 引入生命周期事件分片后，scrutiny 审查发现 5 个非阻塞健壮性问题：

1. 迁移函数对非对象 JSON 行（如 `[1,2]`、`"string"`）无 `isinstance` 守卫
2. 空行在迁移统计中被忽略（`skipped` 计数不包含空行）
3. 清理异常被静默吞掉（`except Exception: pass`，无日志）
4. `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS` 环境变量非整数时崩溃
5. `VAL-COMPAT-03` 测试为占位符，无实际验证

## 决策

采用**防御性编程**策略修复全部 5 项：

| 问题 | 修复方式 |
|------|---------|
| 非对象 JSON | `isinstance(event_data, dict)` 守卫，跳过非对象行 |
| 空行统计 | 空行计入 `skipped` 计数 |
| 静默异常 | `warnings.warn()` 在 `except` 块中记录 |
| 环境变量解析 | `try/except ValueError` 回退到默认值 30 |
| 占位符测试 | 替换为 API 签名验证测试 |

## 理由

- **防御性编程**：生命周期工具处理不可信输入（用户数据、环境变量），必须防御性编程
- **可观测性**：异常不应被静默吞掉，至少 `warnings.warn()` 留痕
- **优雅降级**：环境变量解析失败应回退默认值，不应崩溃
- **测试完整性**：占位符测试没有验证价值，应替换为有意义的断言

## 影响

- `project_lifecycle.py` 修改 5 处
- `test_lifecycle_migration.py` 修改断言（`skipped == 3`）
- `test_compat_matrix.py` 替换占位符测试
- 全部修改向后兼容，无 API 变更

## PR
- PR #232: 健壮性改进（5 项 scrutiny 修复 + 版本一致性）
