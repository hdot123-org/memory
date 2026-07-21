# D-002: pytest 版本策略与 CI 缓存治理

> 决策日期：2026-06-02
> 关联 Lesson：[ci-pyc-cache-pollution](../../kb/lessons/ci-pyc-cache-pollution.md)
> 关联 Issue：INFRA-5（memory-core v0.6.0 升级）

## 背景

CI runner 预装 pytest 9.0.3，与项目 pytest 配置不兼容。具体表现为：

- `pip show pytest` 报 `RECORD` 文件缺失错误
- pytest 执行失败，Pipeline #392 阻断
- 根因：runner 预装版本通过系统包管理器安装，缺少 pip `RECORD` 元数据文件，且 `.pyc` 缓存污染叠加导致 import 错误

## 问题

1. **版本冲突**：runner 预装 pytest 9.0.3 与项目期望的 pytest 8.x 不兼容
2. **缓存污染**：旧版 `.pyc` 缓存在删除模块/常量后仍被 Python 加载
3. **元数据缺失**：系统预装的 pytest 缺少 pip `RECORD` 文件，`pip show` 报错

## 决策

### 1. pytest 版本锁定

在项目依赖中锁定 pytest 版本范围：

```
"pytest>=8.0,<9.0"
```

**理由**：
- 避免与 runner 预装的 pytest 9.x 冲突
- pytest 8.x 稳定且满足项目测试需求
- 明确的上限版本防止未来 9.x 引入 breaking changes

### 2. CI before_script 清理缓存

在 CI 配置的 `before_script` 中执行：

```yaml
before_script:
  - find . -type f -name "*.pyc" -delete
  - find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
```

**理由**：
- 彻底清除旧版 `.pyc` 缓存，防止 import 到已删除的模块/常量
- 在每次 CI 运行前强制执行，不依赖 cache key 更新

### 3. 禁止写入字节码

设置环境变量：

```yaml
variables:
  PYTHONDONTWRITEBYTECODE: "1"
```

**理由**：
- CI 环境不需要 `.pyc` 缓存（每次都是干净安装）
- 避免本次运行产生新的缓存污染下次运行
- 轻微减少磁盘 I/O

### 4. 使用 `--no-cache-dir` 安装

```yaml
script:
  - pip install --no-cache-dir -e .
```

**理由**：
- 避免 pip wheel cache 残留旧版本
- 确保每次 CI 运行都从源码重新安装
- 与 `PYTHONDONTWRITEBYTECODE` 配合，双重防止缓存污染

## 影响

- **正面**：CI 稳定性提升，消除 `.pyc` 缓存导致的间歇性失败
- **负面**：CI 安装时间略有增加（无法利用 pip cache），但在可接受范围内
- **风险**：低 — 所有变更均为防御性配置

## 替代方案（已否决）

| 方案 | 否决理由 |
|------|---------|
| 升级 runner 预装 pytest 到 9.x | 可能引入其他 breaking changes，且 runner 为共享资源，不可控 |
| 仅更新 CI cache key | 治标不治本，下次删除模块时仍会出问题 |
| 卸载系统预装 pytest | Shell Runner 为共享环境，可能影响其他项目 |

## 相关决策

- [ci-pyc-cache-pollution Lesson](../../kb/lessons/ci-pyc-cache-pollution.md)
