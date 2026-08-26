# 教训：自建 runner 环境遮蔽导致子进程 CLI 版本测试假失败

- **日期**: 2026-08-25
- **事件**: PR #1030（release 0.41.1）CI 失败
- **严重度**: 中（阻塞发版，非代码缺陷）
- **修复 PR**: #1031

## 现象

release-please 发版 PR 的 test (3.12) 失败，3 个 CLI `--version` 子进程测试全红：

```
assert '0.41.1' in 'memory-promote 0.41.0\n'      # 期望 0.41.1，输出 0.41.0
assert '0.41.1' in 'init_project_memory.py 0.41.0\n'
assert '0.41.1' in 'migrate_project_memory.py 0.41.0\n'
```

## 根因

三层因素叠加：

1. **测试非封闭执行**：`subprocess.run([sys.executable, "-m", "memory_core.tools.xxx", "--version"])` 未固定 `cwd`。`python -m` 依赖 cwd 进 sys.path 解析模块；cwd 被 pytest 进程中某个 `monkeypatch.chdir` 漂移后，子进程无法解析仓库副本，退化为解析 site-packages。
2. **自建 runner 环境残留**：pve-linux runner 的 site-packages 存在 pip install -e 管不到的 memory_core 旧副本（本次 CI 安装日志 `Successfully uninstalled memory-core-0.41.0` 实证；来源为本机部署链路 release-and-dispatch.yml 的安装或快照预装）。
3. **版本巧合掩盖**：#1024（release 0.41.0）CI 全绿是假象——仓库版本恰好等于环境残留副本版本，断言 0.41.0 == 0.41.0 通过，遮蔽问题被完全掩盖。bump 到 0.41.1 才首次暴露。

## 判别证据（同 run 对照实验）

同一 CI run 中 `tests/test_integration_cli.py::test_init_version_flag`（同型断言，但带 `cwd=REPO_ROOT`）**通过**——唯一差异就是是否固定 cwd。这是定位根因的决定性证据。

## 修复

照搬仓库既有先例（test_integration_cli.py），三个测试补 `cwd=REPO_ROOT`：

```python
REPO_ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run([...], capture_output=True, text=True, cwd=REPO_ROOT)
```

## 教训

1. **子进程测试必须封闭化**：任何 `python -m` 子进程测试都应显式固定 `cwd`（以及必要时的 `env`），不能继承 pytest 进程的可变状态。同型测试必须使用同型封闭化模式。
2. **自建 runner ≠ 干净环境**：持久化 workspace + 环境里部署的包 = pip install -e 无法完全控制的解析环境。子进程 import 链必须与 site-packages 解耦（cwd=REPO_ROOT 是最低成本的解耦手段）。
3. **绿灯也可能撒谎**：#1024 全绿掩盖了三个月的潜在地雷。"恰好相等" 通过的断言没有判别力——测试设计时要问：如果环境错了，这个测试能抓住吗？
4. **诊断先找同 run 对照**：同一次 CI run 里通过的同型测试是最快的根因隔离手段，优先于本地复现（本地环境与 runner 环境不同，复现失败不代表测试错）。

## 关联

- 先例模式：tests/test_integration_cli.py（REPO_ROOT + cwd）
- 环境来源：.github/workflows/release-and-dispatch.yml（memory-core-upgrade runner 部署链路）
- 相关教训：ci-runtime-version-mismatch.md（runner 环境版本错位的另一变种）
