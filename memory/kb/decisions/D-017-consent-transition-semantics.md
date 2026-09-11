# D-017: consent 过渡语义决策记录

## 决策背景

在从旧版 memory-core 系统过渡到新版路由逻辑的过程中，需要一种机制来区分哪些非 git 目录是用户有意保留的合法项目（consent），哪些是事故残留（如 mencbo 事故产生的非预期记忆树）。这确保了系统能够正确处理现有的非 git 记忆树，同时防止新的非 git 记忆树被意外创建。

## 决策内容

### consent 标记机制

#### 创建
- 通过 `memory-init --allow-non-git` 命令创建记忆树时，会在以下位置落盘 consent 标记：
  - `memory/system/ownership.toml` 文件的 `[policy]` 段中
  - `memory/system/manifest.json` 文件中作为 token
- 标记格式：`allow_non_git = true`（TOML）或对应的 JSON 格式

#### 检测
- A 层（wrapper）：通过 grep 检测 `allow_non_git` 标记（锚定正则）
- B 层（gateway）：同样检测持久化的标记文件
- 环境变量 `MEMORY_HOOK_ALLOW_NON_GIT` 作为补充检测途径

### 语义定义

#### 有标记的非 git 项目
- **行为**：passthrough（透传）服务
- **路由**：继续服务该非 git 项目，不被探测逻辑劫持
- **目的**：允许用户明确同意的非 git 项目正常运行

#### 无标记的非 git 项目
- **行为**：被视为事故残留
- **处理**：不作为路由目标
- **如果存在唯一有效子仓库**：路由指向该子仓库
- **目的**：防止旧的事故残留干扰新的路由逻辑

### 探测触发的特殊语义

当探测逻辑触发时，对于 init 操作采用 adopt 语义：
- 不追加 AGENTS.md 注入块
- 不覆盖现有的业务文件（如 README/业务 INDEX）
- 保留用户的原有配置

### 与用户裁决的关联

#### 用户裁决 3：过渡期 consent
- **内容**：`memory-init --allow-non-git` 落盘标记作为过渡期 consent 机制
- **实现**：token `allow_non_git=true` 在 `ownership.toml` 和/或 `manifest.json` 中至少一处
- **语义**：有标记 = 合法非 git 项目 passthrough；无标记的非 git 树 = 事故残留

#### 过渡策略
- 现有带标记的非 git 项目继续正常工作
- 新的非 git 项目需要明确使用 `--allow-non-git` 标志才能创建
- 无标记的旧非 git 项目会自动迁移到合适的 git 仓库

## 影响与后果

1. **平滑过渡**：允许现有合法非 git 项目继续工作，避免破坏现有工作流程
2. **事故清理**：自动将无标记的事故残留重定向到合适的 git 仓库
3. **用户控制**：为用户提供明确的方法来创建新的非 git 项目
4. **安全性增强**：防止意外创建非 git 记忆树

## 与其他决策的关联

- 与此决策相关的单一性硬规则：consent 机制为例外情况提供了解决方案
- 与此决策相关的探测三分支语义：consent 标记影响探测行为
- 与此决策相关的硬化配置设计：配置文件本身也可视为一种显式 consent

## 实施状态

**已实施**：在 `memory-init` 的 consent 标记生成逻辑和 wrapper/gateway 的检测逻辑中

## 参考文献

- `memory/artifacts/2026-09-10-nested-repo-root-resolution-solution-qwen.md`
- 用户裁决 2026-09-10
- `_gateway_config.py` 和 `factory_global_hooks.py` 的 consent 检测实现
