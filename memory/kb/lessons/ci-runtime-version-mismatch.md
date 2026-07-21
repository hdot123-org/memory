
> Date: 2026-07-22
> Source: SessionEnd hook argparse 边缘错误调查
> Tags: [lesson, ci, python-version, testing, hook]
> Related: [D-006-python-version-pin-314]

## 问题

CI 测试的 Python 版本矩阵（3.9/3.10/3.11/3.12）和实际运行环境的 Python 版本（3.14）完全不匹配。

## 发现过程

SessionEnd hook 在 3.14 上报 argparse 边缘错误：

```
File ".../python3.14/argparse.py", line 2729, in _get_formatter
    formatter = self.formatter_class(prog=self.prog)
  File ".../python3.14/argparse.py", line 178, in __init__
    import shutil
  ...
KeyboardInterrupt  # 10秒超时被杀
```

调查发现三层脱节：

1. **pyproject.toml** 声明 `requires-python = ">=3.9"`，classifiers 列出 3.9~3.13
2. **CI 矩阵** 只测 3.9/3.10/3.11/3.12，不含 3.14
3. **实际 Factory runtime** 用 3.14.6（`memory-hook-gateway` shebang `#!/opt/homebrew/opt/python@3.14/bin/python3.14`，memory-core 安装在 `/opt/homebrew/lib/python3.14/site-packages`）

CI 永远抓不到 3.14 的边缘行为。

## 根因

"多版本支持"的惯性思维：pyproject 声明了宽版本范围，CI 测了一部分，但实际只有一个 runtime 版本。三套版本号各自演化，互不同步。

## 教训

1. **CI 矩阵必须覆盖实际 runtime 版本** —— 测不到的版本等于没测
2. **requires-python 不应声明不测试的版本** —— 声明 3.9~3.13 但 CI 只测到 3.12 且实际跑 3.14，三个都不一致
3. **"多版本支持"的维护成本远超收益** —— 特别是只有一个真实 runtime 时：CI 时间 x4、兼容代码 ~225 行、mypy 语法锁在 3.9、条件依赖

## 解决方案

锁死到 3.14 单版本（PR #184），CI 只跑 3.14。详见 D-006。
