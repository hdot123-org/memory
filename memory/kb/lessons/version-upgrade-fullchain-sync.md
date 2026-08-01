---
title: "版本升级需全链路同步"
type: lesson
severity: high
status: accepted
date: 2026-08-01
tags: [version, release, ci, consistency]
---

# 版本升级需全链路同步

## 问题描述

v0.9.3 → v0.9.4 版本升级时，只更新了 `pyproject.toml`，导致 CI 失败：

- 测试期望版本 `0.9.3`，但 `pyproject.toml` 已是 `0.9.4`
- `constants.py` 的 `CURRENT_MEMORY_VERSION` 仍是 `0.9.3`
- `compat.py` 的 `_COMPAT_MATRIX` 缺少 `0.9.4` 条目
- README.md 中 7 处版本引用过时
- 5 个测试文件硬编码 `0.9.3`

## 根因

版本号散布在多个文件中，没有集中的版本升级检查清单。

## 全链路同步清单

版本升级时必须同步修改以下文件：

| 文件 | 字段 | 说明 |
|------|------|------|
| `pyproject.toml` | `version` | 包版本 |
| `memory_core/constants.py` | `CURRENT_MEMORY_VERSION` | 运行时版本常量 |
| `memory_core/compat.py` | `_COMPAT_MATRIX` | 兼容性矩阵 |
| `README.md` | 多处引用 | 安装命令、架构头、下载链接 |
| `tests/test_version_*.py` | 断言 | 版本号测试 |
| `tests/test_compat_*.py` | 断言 | 兼容性测试 |

### 快速检查命令

```bash
# 搜索所有硬编码的旧版本号
rg "0\.9\.3" --type py --type md

# 确认新版本号已全局替换
rg "0\.9\.4" memory_core/constants.py memory_core/compat.py
```

## CI 失败模式

版本不一致导致 CI 失败的模式：
1. `test_version_bump_*.py` 断言 `CURRENT_MEMORY_VERSION == "0.9.3"` → 失败
2. `test_compat_*.py` 断言兼容性矩阵不包含新版本 → 失败
3. CI 门禁阻止合并

## 版本升级 SOP

1. 更新 `pyproject.toml` version
2. 更新 `constants.py` CURRENT_MEMORY_VERSION
3. 更新 `compat.py` _COMPAT_MATRIX（添加新条目）
4. 更新 README.md（搜索旧版本号替换）
5. 更新测试文件（`sed` 批量替换）
6. 运行 `grep` 确认无残留
7. 运行测试确认通过

## 经验教训

1. **版本号是分布式状态** — 不能只改一个文件
2. **测试中的版本断言是保护机制** — 它们存在的意义就是防止版本不一致
3. **CI 是最后防线** — 版本不一致会在 CI 阶段被拦截，但修复成本高于开发阶段

## 相关 PR

- PR #232: 版本一致性修复（constants + compat + README + 5 测试文件）

---
**来源：** v0.9.3 → v0.9.4 版本升级 CI 失败
**日期：** 2026-08-01
