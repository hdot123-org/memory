# Contributing to memory-core

## 分支模型

- `main` — 稳定分支，受 CI 保护
- `feature/*` — 功能分支，从 main 创建，PR 合并后删除

### 工作流程

1. 从 `main` 创建功能分支 `git checkout -b feature/xxx`
2. 开发并确保本地测试通过
3. Push 并创建 PR 到 main
4. CI 自动运行（ruff lint + pytest 3.9-3.12 矩阵）
5. CI 通过 + Review 通过后合并

## CI

| Workflow | 触发条件 | 做什么 |
|----------|---------|--------|
| `ci.yml` | push/PR 到 main | ruff lint + pytest (3.9/3.10/3.11/3.12) |
| `release.yml` | push tag `v*` | 全矩阵测试 → 版本校验 → build → GitHub Release → PyPI |

## 发版流程

1. 更新 `pyproject.toml` 中的 `version`
2. 提交并打 tag：
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to x.y.z"
   git tag vx.y.z
   git push origin main vx.y.z
   ```
3. 自动触发 release workflow：
   - 全矩阵测试 (3.9-3.12)
   - 校验 tag 版本 == pyproject.toml 版本
   - build wheel + sdist
   - 发布到 GitHub Release + PyPI
4. 验证：`pip install memory-core==x.y.z`

## 本地开发

```bash
# 安装（开发模式）
pip install -e ".[dev]"

# 测试
python -m pytest tests/

# Lint
ruff check .

# 一条命令跑完
ruff check . && python -m pytest tests/
```

## 代码风格

- ruff（E/F/W/I 规则集），target Python 3.9，行宽 120
- 提交信息格式：`类型: 简短描述`（如 `feat:`, `fix:`, `chore:`, `docs:`）

## 版本管理

- 版本号只在 `pyproject.toml` 的 `[project].version` 中维护
- 遵循语义版本（SemVer）：MAJOR.MINOR.PATCH
- tag 格式：`vX.Y.Z`，必须与 pyproject.toml 版本一致
