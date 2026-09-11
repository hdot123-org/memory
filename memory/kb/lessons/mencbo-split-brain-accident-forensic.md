# mencbo split-brain 事故考古与教训总结

## 事故概述

mencbo split-brain 事故是 memory-core 系统中发生的重大路由缺陷事故，导致在非 git 父目录中错误地创建了记忆树，而在嵌套的 git 仓库中也有独立的记忆状态，造成了"split-brain"（分裂脑）现象。这个问题揭示了系统在处理非 git 父目录 + 嵌套 git 仓库布局时的严重缺陷。

## 根因分析 (Root Cause)

### 技术根因
1. **Wrapper 路由缺陷**：`memory_core/tools/factory_global_hooks.py` 中的 render_wrapper 模板只执行向上 `git rev-parse` 操作
2. **单向路由逻辑**：当会话在非 git 父目录启动时，`PROJECT_CWD` 被保留为非 git 外层，没有向下探测逻辑
3. **Gateway 无二次校验**：`memory_core/tools/_gateway_config.py:80-88` 中的 `discover_roots` 函数无条件信任 wrapper 传来的 `PROJECT_CWD` 值，没有二次校验机制
4. **Python 发现逻辑**：`memory_root_discovery.py` 采用纯向上解析，没有向下或横向探测能力

### 时间轴
- **事故发生时间**：早期 memory-core 版本
- **问题发现时间**：2026-08 至 2026-09 期间
- **问题解决时间**：2026-09-10 作为 M1 Phase 1 的一部分

### file:line 级别根因
- `memory_core/tools/factory_global_hooks.py` render_wrapper L151-157：向上 `git rev-parse` 逻辑
- `memory_core/tools/_gateway_config.py` L80-88：`discover_roots` 函数无二次校验
- `memory_root_discovery.py`：纯向上解析逻辑

## 事故影响

### 直接影响
1. **数据分离**：在 `/Users/busiji/mencbo` (外层非 git 目录) 和 `/Users/busiji/mencbo/mencbo` (内层 git 仓库) 同时存在记忆树
2. **状态不一致**：两个位置的记忆状态可能不一致，导致混乱
3. **维护困难**：需要分别维护两个记忆树，增加了复杂性

### 系统影响
1. **架构违反**：违反了"一个项目 = 一个 git 治理的记忆根 = 一棵记忆树"的核心假设
2. **路由不确定性**：无法确定应该在哪个位置访问项目的记忆数据
3. **潜在数据丢失风险**：在错误的位置进行操作可能导致数据丢失

## 解决方案与修复要点

### 主要修复措施
1. **wrapper 探测层**：实现四级路由优先级（git 向上归一化 > 项目根硬化配置 > 启发式向下探测 > 显式拒绝）
2. **gateway cwd 语义修复**：修复 `_discover_cwd` 在 `PREFER_EXTERNAL_CWD=1` 下的优先级问题
3. **B 层种子精炼**：在 `_gateway_config.py` 中实现非 git 种子精炼函数

### 修复代码要点
- 在 `render_wrapper` 模板中增加向下探测逻辑
- 实现三分支语义（唯一 → 路由子仓 / 0 → noop / ≥2 → noop+stderr）
- 修复 gateway 层 cwd 语义，确保内存根语义调用点使用 `REPO_ROOT`

### 安全性增强
- 添加门控条件确保只在合适的情况下进行探测
- 实现探测结果的安全性验证（rev-parse 确认有效仓库）
- 防止探测逻辑对非法路径的影响

## 教训与启示

### 设计教训
1. **防御性设计不足**：系统只考虑了理想路径，没有充分考虑边缘情况
2. **缺乏二次校验**：下游组件无条件信任上游组件的结果
3. **路由逻辑不完整**：只有向上路由，缺乏向下和横向路由能力

### 测试教训
1. **边缘案例覆盖不足**：没有充分测试非 git 父目录 + git 子目录的布局
2. **集成测试缺失**：单元测试未能发现组件间交互的问题
3. **回归测试不足**：没有针对路由变化的全面回归测试

### 架构教训
1. **单一责任原则**：路由逻辑不应该只依赖单一组件
2. **容错设计**：系统应该能够在不完美输入下优雅降级
3. **确定性行为**：系统在面对歧义时应该有明确的行为规范

## 预防措施

### 技术预防
1. **四层路由机制**：确保即使某一层失效，其他层也能提供正确路由
2. **consent 标记**：区分合法非 git 项目和事故残留
3. **配置驱动**：通过 `memory-project.toml` 明确指定项目边界

### 流程预防
1. **全面的边缘案例测试**：涵盖各种目录布局情况
2. **集成测试强化**：测试组件间的交互逻辑
3. **回归测试**：确保路由逻辑变更不会引入新问题

## 不可溯源声明

虽然我们成功识别并修复了 mencbo split-brain 事故的技术原因，但对于以下方面无法完全溯源：

1. **事故首次发生的确切时间**：由于历史日志可能已被覆盖，无法确定第一次出现该问题的具体时间
2. **所有受影响的实例**：可能还有其他类似的 split-brain 实例尚未被发现和修复
3. **间接影响范围**：事故可能对相关系统和工作流程产生了无法完全评估的间接影响

因此，我们的修复主要集中在解决根本技术问题和建立防止类似问题的防御机制，而非追溯所有历史实例。

## 参考资料

- `memory/artifacts/2026-09-10-nested-repo-root-resolution-solution-qwen.md`
- mission.md 中关于 mencbo 事故的详细描述
- 修复代码：`factory_global_hooks.py`, `_gateway_config.py`, `memory_root_discovery.py`
