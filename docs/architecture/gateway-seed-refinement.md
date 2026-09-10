# Gateway 种子精炼机制（B 层）

## 概述

memory-core 的 gateway 配置层（`_gateway_config.py`）实现了 B 层种子精炼机制，用于在非 git 目录启动时自动识别并路由到唯一的有效子仓库。

## 设计动机

当会话从非 git 目录启动（例如 `mencbo` 事故现场：外层非 git 目录 + 内层 git 仓库），gateway 需要正确识别项目根。A 层（wrapper）通过向下探测完成此任务，而 B 层（gateway 配置层）作为防御纵深，在 A 层失效或跳过时提供相同的语义保证。

## 精炼逻辑

`_refine_non_git_seed()` 函数在 `_gateway_config.py` 模块加载时执行，对种子路径进行精炼：

```python
def _refine_non_git_seed(seed: Path) -> Path:
    """非 git 种子精炼：唯一有效子仓库时返回子仓库路径。"""
```

### 精炼条件

精炼仅在以下条件**全部满足**时触发：

1. **种子自身无 `.git`**：如果种子本身是 git 仓库，直接透传（passthrough）
2. **无 consent 标记**：`MEMORY_HOOK_ALLOW_NON_GIT` 环境变量未设置
3. **恰好存在一个有效子仓库**：
   - 子目录包含 `.git`（文件或目录形式，支持 worktree）
   - 子目录名不以 `.` 开头（与 shell glob 行为对齐）
   - 使用纯文件系统检查，**不产生 git 子进程**

### 精炼结果

- **0 个有效子仓库**：返回原始种子（不精炼）
- **1 个有效子仓库**：返回该子仓库路径
- **≥2 个有效子仓库**：返回原始种子（歧义，不静默选择）

## 影响面

B 层种子精炼影响所有依赖 gateway 配置的 CLI 工具在非 git 目录启动时的解析行为：

### 受影响的 CLI 工具

以下工具在 import `_gateway_config` 模块时会触发种子精炼：

1. **`memory-hook-gateway`**：gateway 主入口
2. **`mcp_server`**：MCP 服务接口
3. **`memory_health_report`**：健康报告生成
4. **所有 `memory_core.tools.*` 模块**：任何在 import 时读取 `REPO_ROOT` 的模块

### 行为变化

| 场景 | 精炼前行为 | 精炼后行为 |
|------|-----------|-----------|
| 非 git 目录 + 唯一 git 子仓 | `REPO_ROOT` = 非 git 目录 | `REPO_ROOT` = 子仓库路径 |
| 非 git 目录 + 多个 git 子仓 | `REPO_ROOT` = 非 git 目录 | `REPO_ROOT` = 非 git 目录（不精炼） |
| 非 git 目录 + 无 git 子仓 | `REPO_ROOT` = 非 git 目录 | `REPO_ROOT` = 非 git 目录（不精炼） |
| git 仓库目录 | `REPO_ROOT` = 当前目录 | `REPO_ROOT` = 当前目录（透传） |

### 纯文件系统保证

精炼过程**不产生任何 git 子进程**，仅使用 `Path.exists()` 检查 `.git` 存在性。这意味着：

- 即使在 `PATH` 中注入失败的 git stub，精炼仍能成功
- 精炼性能仅取决于文件系统 stat 操作，无进程创建开销
- 与 A 层（wrapper）的探测逻辑保持一致的语义

## 与 A 层的关系

A 层（wrapper 探测）和 B 层（种子精炼）形成防御纵深：

```
会话启动
  ↓
A 层：wrapper 向下探测（factory_global_hooks.py）
  ↓ 设置 MEMORY_HOOK_PROJECT_CWD=子仓库
  ↓
B 层：gateway 配置层精炼（_gateway_config.py）
  ↓ 再次检查并精炼（防御 A 层失效场景）
  ↓
REPO_ROOT = 最终项目根
```

### A 层失效场景

B 层作为防御纵深，覆盖以下 A 层可能失效的场景：

1. **wrapper 未重渲染**：系统升级后 wrapper 未通过 `memory-factory-hooks install` 重渲染
2. **wrapper 手动覆盖**：用户或第三方工具覆盖了 wrapper
3. **跳过 wrapper 直接调用**：某些工具直接 import gateway 模块而不经过 wrapper
4. **wrapper 探测被禁用**：`MEMORY_HOOK_DISABLE_DOWNWARD_PROBE=1` 逃生口启用

在这些场景下，B 层确保语义一致性。

## 测试覆盖

验证契约覆盖以下断言：

- **VAL-GTW-006**：非 git 种子 + 无 consent + 唯一有效子仓 → `REPO_ROOT` = 子仓库
- **VAL-GTW-007**：种子自带 `.git` → 透传，`REPO_ROOT` = 种子本身
- **VAL-GTW-008**：点目录子项不计入候选（与 shell glob 对齐）
- **VAL-GTW-009**：歧义子仓（≥2）不静默选择
- **VAL-GTW-011**：候选判定为纯文件系统操作（无 git 子进程）
- **VAL-GTW-012**：`.git` 文件形式（worktree）同样计为有效候选
- **VAL-GTW-014**：`mcp_server` 等 CLI 在非 git 目录启动行为可预期
- **VAL-GTW-015**：B 层影响面文档声明存在（本文件）

## 实现细节

### 位置

- **文件**：`memory_core/tools/_gateway_config.py`
- **函数**：`_refine_non_git_seed()`
- **调用点**：模块加载时（第 80-88 行）

### 关键代码

```python
# 种子精炼：非 git + 无 consent + 唯一有效子仓 → 使用子仓
_cwd_seed_refined = _refine_non_git_seed(_cwd_seed)
REPO_ROOT, WORKSPACE_ROOT = discover_roots(_cwd_seed_refined)
```

### 设计约束

1. **不修改 `discover_project_root` 契约**：精炼在种子层完成，不影响上层发现逻辑
2. **纯文件系统操作**：不使用 git 子进程，确保性能和可靠性
3. **点目录过滤**：与 shell glob 行为对齐，跳过以 `.` 开头的目录
4. **歧义不选择**：多个候选时返回原始种子，避免静默错误

## 未来扩展

B 层种子精炼为 Phase 2 硬化配置（`memory-project.toml`）奠定基础。未来的四级优先级路由将在精炼层之上实现：

1. git 向上归一化
2. 项目根硬化配置（`memory-project.toml`）
3. 启发式向下探测（当前 B 层）
4. 显式拒绝（歧义/无效）

当前 B 层覆盖第 3 级，为后续扩展预留接口。
