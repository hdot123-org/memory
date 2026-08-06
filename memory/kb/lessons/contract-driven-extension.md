---
type: [KB:LESSON]
title: "契约驱动扩展：声明式版本协商优于硬编码兼容矩阵"
shortname: CONTRACT-DRIVEN-EXTENSION
status: accepted
created: 2026-08-03
updated: 2026-08-03
source: local-canonical
confidence: high
tags: [lesson, architecture, extension, contract, versioning, declarative]
related: [version-upgrade-fullchain-sync, ci-runtime-version-mismatch, D-007-doc-routing-engine]

---

# 契约驱动扩展：声明式版本协商优于硬编码兼容矩阵

## 经验来源

oh-my-cli vs memory-core 工程对比分析（维度 01：契约驱动扩展 vs 硬编码版本矩阵）。oh-my-cli 采用声明式契约扩展架构，memory-core 采用硬编码版本兼容矩阵。

## 核心教训

### 教训 1：扩展应是声明式的，新增不改核心代码

oh-my-cli 的 Provider、Tool、MCP Server、Workflow 四类扩展统一为 settings.json 中的版本化契约。新增一个 provider 只需在 settings.json 中声明 `contractVersion`，运行时自动协商支持版本，不支持的版本 fail-closed 拒绝。**核心代码零修改**。

memory-core 的 `_COMPAT_MATRIX` 在 `compat.py` 中逐版本硬编码（已累积 14 个版本条目），每次发版必须手改矩阵 + constants.py + pyproject.toml + README + 测试文件，曾因遗漏导致 CI 失败（见 `version-upgrade-fullchain-sync.md`）。

**原则**：扩展机制的维护成本应与扩展数量成正比，而非与系统复杂度成正比。

### 教训 2：版本协商应 fail-closed，不可静默降级

oh-my-cli 的版本协商逻辑：

```typescript
if (!SUPPORTED_VERSIONS.includes(version)) {
  throw new Error(`version ${version} is not supported`);
}
```

不在支持列表的版本被**拒绝**，不是静默降级。这避免了"以为兼容但实际行为不一致"的隐蔽错误。

memory-core 的 `check_compatibility()` 只检查版本是否在矩阵中，不检查组件运行时是否可用。无法在运行时发现组件不可用并优雅降级。

**原则**：版本不兼容时，快速失败优于静默降级。调用方需要明确的错误信号来采取行动。

### 教训 3：生命周期状态机让扩展可观测

oh-my-cli 的 MCP/Tool 契约引入三态生命周期：`declared` → `ready` → `isolated`。每个扩展有明确的状态，可被查询和诊断。`resolveMcpLifecycle()` 函数根据 enabled 标志、探测超时、命令解析结果确定状态。

memory-core 的组件没有生命周期状态——要么存在要么不存在。无法回答"这个 hook 当前是正常工作还是降级状态"。

**原则**：有状态的扩展比无状态的配置更易调试和监控。三态模型（declared/ready/isolated）是一个通用的好模式。

## 迁移方向

| 建议 | 优先级 | 可行性 | 实施方向 |
|------|--------|--------|----------|
| 将 `_COMPAT_MATRIX` 从逐版本硬编码改为区间映射 | 高 | 高 | `(min_version, max_version) → component_versions`，14 行压缩为 3-4 个区间 |
| 新增组件可用性运行时检查 | 中 | 中 | 在 `check_compatibility()` 基础上加 `probe_component()` 健康检查 |
| 为 hook 工具引入生命周期状态 | 中 | 中 | 参考 declared/ready/isolated 三态模型，在 project_lifecycle 中追踪 hook 状态 |

## 关联

- 对比文档：oh-my-cli 契约驱动扩展分析文档（contracts.md）
- 差距总结：oh-my-cli 工程对比分析文档（gap-priorities.md）→ G-01-1, G-01-2, G-01-3
- 相关教训：`version-upgrade-fullchain-sync.md`（硬编码矩阵的维护痛点）

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- memory/kb/global/truth-model.md
- memory/kb/global/memory-routing.md
- project-map/INDEX.md

### Evidence Refs

- tests/test_compat.py
- tests/test_compat_and_cross_flows.py
- memory_core/compat.py

### Conflict Status

- resolved

