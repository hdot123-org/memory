# pytest fixture finalizer 泄漏：Python 3.11 CI 中 pytest-rerunfailures + pytest 8.x 的兼容性问题

> Type: [KB:LESSON]
> Title: pytest fixture finalizer 泄漏（pytest-rerunfailures + pytest 8.x + Python 3.11）
> Status: active
> Created: 2026-07-20
> Updated: 2026-07-20
> Source: local-canonical
> Confidence: high
> Tags: [lesson, pytest, ci, python311, fixture, finalizer, rerunfailures, singleton, telemetry]
> Related: [D-004-v5-dplus-refactor-completion]

## 问题

Python 3.11 CI 环境中，pytest 测试间歇性崩溃：

```
assert not self._finalizers
    at _pytest/fixtures.py:1221
```

错误发生在 fixture teardown 阶段，表现为 `FixtureDef` 的 `_finalizers` 列表在 cleanup 后不为空，触发 internal assertion。

## 根因

三个因素叠加：

### 1. 全局 `--reruns 2` 配置

`pyproject.toml` 中 `addopts` 包含 `--reruns 2`，对所有测试全局启用失败重试。pytest-rerunfailures 在重试时重新执行 test function，但不重新创建 fixture（除非标记 `scope="function"` 的 autouse fixture）。

### 2. Telemetry singleton 状态泄漏

`telemetry_bridge.py` 使用模块级 singleton 缓存连接状态。当 test A 修改了 singleton 状态（如 mock 了 HTTP session），test B 在 rerun 时继承了这个污染状态，导致 fixture finalizer 注册了额外的 cleanup callback。

### 3. CI 依赖不锁定

CI 的 `pip install` 不锁定 pytest/pytest-rerunfailures 版本。pytest 8.x 的 fixture finalizer 机制与 pytest-rerunfailures 0.14 存在兼容性问题（pytest 8.0 改了 `FixtureDef._finalizers` 的清理语义）。

## 症状

- **频率**：约 5% 的 CI run 出现（非确定性）
- **错误位置**：`_pytest/fixtures.py:1221` 的 `assert not self._finalizers`
- **影响范围**：只在 Python 3.11 CI 出现（本地 3.14 不触发）
- **特征**：失败测试不固定（不同 run 不同测试触发），但总在 fixture teardown 阶段

## 解决方案

### 修复 1: 移除全局 --reruns

从 `pyproject.toml` 的 `addopts` 中移除 `--reruns 2`。如果特定测试需要重试，用 marker 精确标记：

```python
@pytest.mark.flaky(reruns=2)
def test_specific_flaky_thing():
    ...
```

**理由**：全局 --reruns 掩盖真实测试问题（test isolation failure），应只在已知 flaky 测试上精确启用。

### 修复 2: autouse singleton cleanup fixture

新增 conftest.py 中的 autouse fixture，每个 test 后重置 telemetry singleton：

```python
@pytest.fixture(autouse=True)
def _reset_telemetry_singleton():
    yield
    from memory_core.tools.telemetry_bridge import _reset_global_state
    _reset_global_state()
```

**理由**：防止 singleton 状态跨测试泄漏，消除 rerun 时的污染根因。

### 修复 3: Pin CI 依赖

CI workflow 中使用 `requirements-ci.txt` 锁定关键测试依赖版本：

```
pytest==8.3.5
pytest-rerunfailures==15.0
```

**理由**：避免 pytest 大版本升级引入不兼容变更。

## 教训

1. **全局 `--reruns` 是反模式**：它掩盖 test isolation failure，让本来应该失败的测试"通过"重试。应精确标记特定 flaky 测试。
2. **Singleton + pytest = 隐患**：模块级 singleton 在 pytest 多测试环境下天然有状态泄漏风险。必须用 autouse fixture 做 teardown 清理。
3. **CI 依赖必须锁定**：`pip install` 不锁版本等于把 CI 稳定性交给上游。pytest 大版本升级（7->8）经常引入 fixture 机制变更。
4. **Python 版本差异会暴露隐藏 bug**：同一代码在 3.14 正常但在 3.11 崩溃，说明问题与 GC 时序 / dict ordering / 内部实现变更有关。CI 应覆盖最低支持版本。

## 修复 PR

- PR #172: `fix: 修复 Python 3.11 CI fixture finalizer 泄漏`

## Verification Refs

- CI workflow: `.github/workflows/ci.yml`
- pyproject.toml: `addopts` 变更
- conftest.py: 新增 `_reset_telemetry_singleton` fixture
