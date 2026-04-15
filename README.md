# memory

独立记忆层仓库（从 `workbot` 的 M6 Go 基线迁入）。

## 当前范围

- 核心组装逻辑：`workspace/tools/memory_hook_core.py`
- 网关编排与 provider 切换：`workspace/tools/memory_hook_gateway.py`
- 接口与默认实现：`workspace/tools/memory_hook_interfaces.py`、`workspace/tools/memory_hook_impls.py`
- 适配层：`workspace/tools/memory_hook_adapters/`
- 回退演练：`workspace/tools/memory_hook_provider_rollback.py`

## 回归

```bash
python3 -m pytest -q tests
```

## 迁移阶段说明

当前为迁移初始化阶段，保留 `legacy/external-core` 双轨与回退能力。
