
> Status: accepted
> Date: 2026-07-22
> Source: Python 版本锁死 + 死代码清理 mission（2 PRs 合并，21/21 断言通过）
> Tags: [decision, python-version, ci, py314, compatibility-cleanup]
> Related: [D-005-mypy-type-safety-completion]

## 决策

将 memory-core 的 Python 支持从 3.9~3.13 多版本锁定为 3.14 单版本。同步清理 ~225 行兼容代码。

## 背景

SessionEnd hook 在 Python 3.14 上报 argparse 边缘错误（`get_data` -> `KeyboardInterrupt` timeout）。调查发现三套版本号互不一致：

| 位置 | 声明/实际版本 |
|------|-------------|
| pyproject.toml requires-python | `>=3.9`（classifiers 3.9~3.13） |
| CI 测试矩阵 | 3.9 / 3.10 / 3.11 / 3.12（不含 3.14） |
| Factory hook 实际 runtime | 3.14.6（shebang 硬编码，全局安装在 python3.14 site-packages） |

CI 永远抓不到 3.14 的边缘行为，声明与实际完全脱节。

## 关键决策

### 决策 1: 锁死到 3.14 单版本

**选择理由**：memory-core 只在 Factory hook 环境运行（shebang 硬编码 python@3.14），不存在跨版本消费场景。多版本支持的维护成本（CI 矩阵、兼容代码、mypy 语法限制）远超收益。

### 决策 2: CI 矩阵从 4 版本缩到 1 版本

test job 只跑 `["3.14"]`，advisory-security/typing 也改为 `"3.14"`。CI 时间砍 75%，且覆盖实际 runtime。

### 决策 3: 同步清理兼容代码

| 类别 | 文件数 | 操作 |
|------|--------|------|
| tomli 条件导入 | 12（memory_core + tests + scripts） | try/except -> 直接 `import tomllib` |
| `from __future__ import annotations` | ~190 | 批量删除（3.14 PEP 649 原生延迟注解） |
| typing 旧式注解 | 6 | `Optional[X]` -> `X | None` 等 |

### 决策 4: 保留 TYPE_CHECKING 块

4 个文件的 TYPE_CHECKING 块用于解决循环导入，与 Python 版本无关，3.14 仍需要，不删除。

## 影响

| 配置项 | 旧值 | 新值 |
|--------|------|------|
| requires-python | `>=3.9` | `>=3.14` |
| CI test matrix | 3.9/3.10/3.11/3.12 | 3.14 only |
| mypy python_version | `"3.9"` | `"3.14"` |
| classifiers | 3.9~3.13 | 3.14 only |
| tomli 条件依赖 | `"tomli>=2.0; python_version<'3.11'"` | 删除 |

## PR

- PR #184 (cleanup/py314-compat, merged e04ceb7): 配置锁死 + 兼容代码清理
- PR #185 (cleanup/dead-code, merged 53ca9b1): 死代码清理（含 scripts/ tomli 残留清理）

## 教训

详见 `memory/kb/lessons/ci-runtime-version-mismatch.md`：CI 测的版本和实际跑的版本必须一致。
