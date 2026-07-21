# D-002: gateway adapter 注入模式属于过度工程

> Status: accepted（判断成立，暂不清理）
> Date: 2026-07-18
> Source: 代码质量审计维度深挖（mypy name-defined 根因分析）

## 判断

`memory_hook_gateway.py` 的 adapter 注入机制（`globals().update()` + adapter 注册表 + 环境变量选择）**属于过度工程**。当前规模下付出的成本（静态分析失明）大于收益（多 adapter 切换能力，但实际未使用）。

## 证据

1. **adapter 注册表只有 1 个 adapter**
   - `_ADAPTER_REGISTRY = {"default": ...}`（L247-249）
   - 设计了"多 adapter 可切换 + 热重载"的完整机制，但实际只有 default 一个
   - 为没出现的需求建了基础设施

2. **三套配置访问机制并存**
   - `globals().update()`（运行时注入，L301/L338，mypy/ruff 看不见）
   - `_adapter_config` dict（L274，注释说"replaces globals injection"但没替换完）
   - `CoreConfig` dataclass（`memory_hook_config.py`，第三套）
   - 三套做同一件事，互相重叠，迁移没做完就停了

3. **静态分析完全失明**
   - gateway 有 36 处裸常量引用（`PROJECT_MAP_ROOT` 等），mypy 报 59 个 name-defined
   - ruff 已豁免 F821（`ruff.toml`：`"memory_hook_gateway.py" = ["F821", ...]`）
   - **两个检查器都不检查这 36 处引用** → 重构隐患（改 adapter key 名只在运行时炸）

4. **"向后兼容"注释暴露遗留**
   - L299 "Backward-compat: expose keys as module globals so existing callers still work"
   - 说明 `globals().update()` 本该删，但因调用方还在用裸常量不敢删 = 中间状态重构债

## 为什么暂不清理（accepted 而非 actioned）

- gateway 测试覆盖 95%，287 处测试引用，**运行时安全**
- 这个文件稳定不常改，过度工程不活跃产生 bug
- 清理是**大重构**（删 globals().update + 统一到 CoreConfig），风险高于当前收益
- 有更高优先级的事（detect_pollution 守卫裸奔、hook_upgrade 备份未测，见 `memory/docs/audit/coverage-gaps-2026-07-18.md`）

## 如果未来要清理（方向，非计划）

**不要**只做表面迁移（36 处裸引用 → `_adapter_config.get()`，那只是让 mypy 闭嘴，仍是 `dict[str, Any]` 无类型安全）。

**正确方向**：
1. 统一用 `CoreConfig` dataclass（已存在于 `memory_hook_config.py`）显式传递配置
2. 删掉 `globals().update()` 和 `_adapter_config` dict
3. 删掉 adapter 注册表（只有 1 个 adapter，不需要注册表）
4. 收回 ruff F821 豁免，让静态分析重新生效

这是去过度工程，不是"完成未完成的重构"。

## 关联

- mypy baseline：`docs/typing-tech-debt.md`（gateway 69 errors 属于此 baseline 的一部分）
- 覆盖率盲区报告：`memory/docs/audit/coverage-gaps-2026-07-18.md`
- 审计 SOP：`memory/docs/audit/audit-sop.md`
