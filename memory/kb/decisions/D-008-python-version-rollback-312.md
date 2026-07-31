> Status: accepted
> Date: 2026-07-31
> Source: Python 3.14→3.12 版本回滚（稳定性问题 + 平台标准化）
> Tags: [decision, python-version, rollback, py312, stability]
> Related: [D-006-python-version-pin-314]

## 决策

将 memory-core 的 Python 版本从 3.14 回滚到 3.12，requires-python 锁定到 ==3.12.*。

## 背景

D-006 将 Python 版本锁定到 3.14 单版本（2026-07-22），但后续发现以下问题：

1. **稳定性问题**: Python 3.14 存在 argparse 边缘 bug（SessionEnd hook 的 `get_data` -> `KeyboardInterrupt` timeout 问题在 3.14 上重现）
2. **平台标准化**: Factory 平台已标准化到 Python 3.12，与平台保持一致可降低维护成本
3. **生态兼容性**: 部分依赖库在 3.14 上的支持不如 3.12 成熟

## 关键决策

### 决策 1: 回滚到 Python 3.12

**选择理由**: Factory 平台 runtime 已标准化到 3.12，保持与平台一致可避免版本碎片化，且 3.12 生态更稳定。

### 决策 2: requires-python 锁定到 ==3.12.*

**选择理由**: 避免意外升级到 3.13+，确保所有环境使用完全一致的 Python 版本。使用 `==3.12.*` 而非 `>=3.12` 防止自动升级。

### 决策 3: 保留 D-006 作为历史记录

**选择理由**: D-006 记录了当时的决策背景和理由，是完整的历史记录。标记为 superseded 而非删除，便于追溯决策演变。

## 影响

| 配置项 | 旧值 (D-006) | 新值 (D-008) |
|--------|--------------|--------------|
| requires-python | `>=3.14` | `==3.12.*` |
| CI test matrix | 3.14 only | 3.12 only |
| mypy python_version | `"3.14"` | `"3.12"` |
| classifiers | 3.14 only | 3.12 only |

## 迁移步骤

1. 修改 `pyproject.toml`: `requires-python = "==3.12.*"`
2. 更新 CI 矩阵: `.github/workflows/ci.yml` 和 `qa.yml` 中所有 `python-version` 从 `"3.14"` 改为 `"3.12"`
3. 更新 mypy 配置: `mypy.ini` 中 `python_version = "3.12"`
4. 更新 classifiers: 从 `Programming Language :: Python :: 3.14` 改为 `3.12`
5. 重建虚拟环境: 删除旧 venv，使用 Python 3.12 重建
6. 重新安装依赖: `pip install -e .[dev]`

## PR

- 待创建（本决策记录的一部分）

## 教训

详见 `memory/kb/lessons/platform-standardization.md`：与平台保持版本一致可降低维护成本，避免版本碎片化。
