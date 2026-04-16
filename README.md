# memory

独立记忆层仓库（从 `workbot` 的 M6 Go 基线迁入），用于给多个项目提供统一的 memory core 能力。

## 目录结构

- Core 组装逻辑：`workspace/tools/memory_hook_core.py`
- Gateway 编排与 provider 解析：`workspace/tools/memory_hook_gateway.py`
- 接口与默认实现：`workspace/tools/memory_hook_interfaces.py`、`workspace/tools/memory_hook_impls.py`
- 适配层（当前含 workbot profile）：`workspace/tools/memory_hook_adapters/`
- 回退演练：`workspace/tools/memory_hook_provider_rollback.py`
- 测试：`tests/`

## 运行模型

- 推荐 provider：`external-core`
- 兼容 provider：`legacy`（仅用于受控回滚）
- 外部消费者（例如 `workbot` / `tabd`）通过网关加载 core builder，并按自身 profile 执行后续 delegate/artifact/error 流程

## 给消费者项目的接入口径

消费者侧至少需要：

1. `memory_hook_gateway.py`（调用入口）
2. `<project>_runtime_profile.py`（项目配置）
3. `memory_hook_provider_rollback.py`（回滚演练）

关键环境变量：

- `MEMORY_HOOK_CORE_PROVIDER`：`external-core`（默认）或 `legacy`
- `MEMORY_HOOK_EXTERNAL_CORE_MODULE`：默认 `memory_hook_core`
- `MEMORY_HOOK_EXTERNAL_CORE_PATH`：联调时可指定本地路径

## 回归与演练

全量回归：

```bash
python3 -m pytest -q tests
```

回滚演练：

```bash
python3 workspace/tools/memory_hook_provider_rollback.py
```

## 自动发布与下游触发

本仓已配置自动发布工作流：

- `.github/workflows/release-and-dispatch.yml`

行为：

1. `main` 变更触发测试
2. 自动计算并创建下一个 `v0.1.x` tag
3. 自动创建 GitHub Release
4. 向 `hdot123/workbot` 发送 `repository_dispatch` 事件（`memory_release_published`）

必需 Secret：

- `WORKBOT_REPO_DISPATCH_TOKEN`：用于触发下游仓库升级流水线  
  未配置时，发布仍会执行，但跨仓 dispatch 会跳过并输出 warning。

## 当前状态

- 已完成模块化独立仓迁移
- 已接入自动发布与下游升级触发
- 仍保留 `legacy` 回滚能力用于故障处置
