# Release Guide

> **完整操作手册**：本文档为快速参考。完整发版操作手册（含故障排查、hotfix 流程）详见 [RELEASE.md](../../RELEASE.md)。

本指南描述 memory-core 的发布流程。

## 自动发版（推荐）

memory-core 使用 [release-please](https://github.com/googleapis/release-please) 自动化版本管理。

### 工作原理

```
开发者提交 PR (conventional commit)
        ↓
   合并到 main
        ↓
release-please 自动创建 Release PR
   (含版本号变更 + CHANGELOG)
        ↓
   合并 Release PR
        ↓
自动创建 tag + GitHub Release + 构建 wheel
        ↓
release-and-dispatch.yml (tag push 触发):
  test → release → upgrade-consumer
        ↓
upgrade-consumer (self-hosted runner):
  git pull main + pip install -e . + 验证 __version__ == tag 版本
```

### Commit 消息规范

| 前缀 | 版本影响 | 示例 |
|------|---------|------|
| `feat:` | minor（minor 版本 +1） | `feat: 添加 memory-doctor 命令` |
| `fix:` | patch（patch 版本 +1） | `fix: 修复 ownership 分类器绝对路径问题` |
| `feat!:` / `fix!:` | major（major 版本 +1） | `feat!: 重构 hook 输出格式` |
| `chore:` / `docs:` / `test:` / `refactor:` | 不触发版本 | `chore: 更新依赖` |

> **注意：** commit 消息必须使用中文（项目铁律）。

### Release PR

release-please 会维护一个 "Release PR"，包含：
- `pyproject.toml` 版本号更新
- `memory_core/constants.py` 版本号更新
- `README.md` 版本引用更新
- `CHANGELOG.md` 新版本条目

当有新的 conventional commit 合并到 main 时，Release PR 会自动更新。
准备好发版时，合并 Release PR 即可。

### 发版后验证

```bash
# 确认 tag 已创建
git tag -l "v0.9.*"

# 确认 GitHub Release 已创建
gh release list --limit 3

# 确认 wheel 已上传
gh release view v0.9.x --json assets
```

## 手动发版（备用）

当自动发版不可用时，可通过 `release-and-dispatch.yml` 手动触发：

```bash
gh workflow run release-and-dispatch.yml \
  -f release_tag=v0.9.6 \
  -f dispatch_targets="owner/repo1,owner/repo2"
```

### 前置条件

- `pyproject.toml` 的版本号必须与 `release_tag` 匹配
- 所有测试必须通过

### 步骤

1. 确保 `pyproject.toml` 版本号正确
2. 触发 workflow（见上方命令）
3. 等待 CI 完成
4. 验证 release（见上方验证命令）

## 回滚

```bash
# 使用回滚脚本
scripts/release_rollback.sh v0.9.x

# 手动删除 GitHub Release
gh release delete v0.9.x --yes

# 删除 tag
git push origin :refs/tags/v0.9.x
```

## 下游通知

release-please 创建 release 后，可通过 `release-and-dispatch.yml` 的 `workflow_dispatch` 手动触发下游通知：

```bash
gh workflow run release-and-dispatch.yml \
  -f release_tag=v0.9.6 \
  -f dispatch_targets="hdot123/legal-core,hdot123/ingestion-registry"
```

## 相关文件

| 文件 | 用途 |
|------|------|
| `.github/workflows/release-please.yml` | 自动发版工作流 |
| `.github/workflows/release-and-dispatch.yml` | 发布流水线（test → release → upgrade-consumer）+ 下游通知 |
| `release-please-config.json` | release-please 配置 |
| `.release-please-manifest.json` | 当前版本清单 |
| `scripts/release_rollback.sh` | 回滚脚本 |
| `scripts/repo_health_check.sh` | 版本一致性检查 |
