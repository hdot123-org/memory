---
type: "[SPEC]"
title: "path-index cwd 键局限与同步模式选择"
shortname: SPEC-013
status: implemented
created: 2026-08-25
updated: 2026-08-25
source: INFRA-546
scope: default
tags: [path-index,lifecycle,version-sync,gateway]
---

> 文档编号：SPEC-013 | 版本：V1.0 | 日期：2026-08-25
> 维护人：Factory Droid（linear-gateway）
> 状态：implemented

# path-index cwd 键局限与同步模式选择规范

## 1. 目的

正式记录项目生命周期索引 `path-index.json` 以 **cwd（本地绝对路径）为主键**这一设计带来的两类缺陷——**残留条目（stale entries）**与**漏注册（missing registrations）**——并据此规定版本同步工具的调用约束：gateway 必须使用单项目模式 `sync_single_project`，禁止在 hook 链路中调用全量模式 `sync_all_known_projects`。

本规范是 `memory_core/tools/version_sync.py` 模块 docstring 中设计标注（PR #1020）的 tracked 文档层对应物，作为该约束的权威说明。

## 2. path-index 是什么

### 2.1 文件位置与格式

```
~/.memory-core/project-lifecycle/path-index.json
```

```json
{
  "schema_version": "project-lifecycle-path-index-v1",
  "paths": {
    "/Users/<user>/tool/workbot": {
      "project_id": "workbot-a1b2c3d4e5f6",
      "project_name": "workbot",
      "git_root": "/Users/<user>/tool/workbot",
      "git_remote": "https://github.com/hdot123/workbot",
      "identity_source": "git_remote",
      "identity_value": "https://github.com/hdot123/workbot",
      "first_observed_at": "2026-08-01T10:00:00Z",
      "last_observed_at": "2026-08-24T09:00:00Z"
    }
  }
}
```

- 主键：`paths` 对象的 key 是 hook 触发时项目的**本地绝对路径**（`_path_index_key(cwd)`，见 `memory_core/tools/project_lifecycle.py`）
- 写入时机：`record_project_lifecycle()` 在每次 hook 事件（session-start 等）时 upsert 对应 cwd 的条目
- 重建：`memory-lifecycle-rebuild` 可从 `projects/*.json` 记录全量重建索引（过滤 inactive/missing，按 `local_path` 去重保留最新 `observed_at`）

### 2.2 消费方

| 消费方 | 模式 | 说明 |
|--------|------|------|
| `memory-sync-versions`（不带 `--target`） | 全量遍历 | 遍历 `path-index.json` 的所有 `paths` 条目，逐项目做三文件补丁（`sync_all_known_projects`） |
| `memory-audit-daily` | 全量遍历 | 每日完整性审计 |
| `memory-error-patterns` | 全量遍历 | 跨项目错误模式扫描 |
| gateway session-start 探测（`probe_version_and_sync`） | **单项目** | 只对当前 hook 触发的 cwd 调用 `sync_single_project`，完全不读 path-index |

## 3. cwd 键的两类缺陷

### 3.1 残留条目（stale entries）

path-index 只在 hook 触发时 upsert，**没有删除路径**（`retention_policy = "preserve-memory-on-missing-path"`）。目录消失后条目长期残留：

- 验证运行产生的 `/tmp` 沙箱目录（如 scanner/mission 的临时 worktree）被 hook 注册后即被删除，索引中的 key 永久指向不存在的路径
- 项目目录被删除或改名后，旧路径条目仍然保留

后果：全量遍历类工具会命中这些不存在的目录。对 `sync_all_known_projects` 而言，残留条目通常被 `read_ownership_memory_version` 返回 None 后记入 `skipped`（`no ownership.toml`），无害但污染报告；对语义假设「索引条目 ≈ 可操作项目」的调用方则是隐患。

### 3.2 漏注册（missing registrations）

注册只在 hook 于某 cwd 触发时发生，因此：

- 项目**移动**到新位置后，旧 cwd 条目残留（§3.1），新 cwd 在下一次 hook 触发前**不在索引中**
- 同一项目的多个 worktree/clone 各自占用独立的 cwd key，索引视角呈现为多个「项目」
- 依赖「项目必然已注册」的全量遍历会**漏掉**这些未注册位置上的版本同步需求

### 3.3 结论

path-index 是**观测性注册表**（hook 触发时才记录），不是**权威项目清单**。任何把索引当作完整、实时项目清单的消费方都会被上述两类缺陷误导。

## 4. 同步模式规范（强制）

### 4.1 规则

| 规则 | 内容 |
|------|------|
| R1 | gateway session-start 探测（`_gateway_handlers.py::_handle_session_start_setup` → `probe_version_and_sync(cwd)`）**必须**使用 `sync_single_project`，以 hook 触发时的 cwd 为准，完全不依赖 path-index |
| R2 | hook 链路（gateway 及其所有子调用）**禁止**调用 `sync_all_known_projects` |
| R3 | `sync_all_known_projects` 仅保留给人工维护场景：`memory-sync-versions` 不带 `--target` 的手动 CLI 调用，且调用方需知晓 §3 的索引缺陷 |
| R4 | 自动化代码如需同步某个项目，一律走 `sync_single_project(project_path)`（等价于 CLI 的 `--target` 模式） |

### 4.2 理由

- **正确性**：session-start 时当前 cwd 是唯一确定的项目位置，无需借助可能过期/缺失的索引
- **爆炸半径**：单项目模式只写一个项目的 `memory/system/` 三文件；全量模式会遍历（含残留条目在内的）所有注册路径
- **幂等与并发**：两个入口共享 INFRA-545 的 `.sync.lock` 并发防护与降级门禁，但单项目模式天然避免了跨项目级联

### 4.3 现状确认（截至本规范创建时）

- `probe_version_and_sync`（`version_sync.py`）：读当前 cwd 的 `memory/system/memory.lock`，版本不匹配时调用 `sync_single_project` —— 符合 R1
- `_handle_session_start_setup`（`_gateway_handlers.py`）：以 hook cwd 调用探测，异常 fail-safe 不阻塞主链 —— 符合 R1/R2
- `sync_all_known_projects`：仅由 `memory-sync-versions` CLI 的全局模式调用 —— 符合 R3

## 5. 工具使用指引

```bash
# 自动链路（gateway session-start）—— 无需人工操作，单项目模式自动执行

# 人工单项目同步（推荐，不受索引缺陷影响）
memory-sync-versions --target /path/to/project

# 人工全量同步（维护用途；结果受 §3 缺陷影响，残留路径会出现在 skipped）
memory-sync-versions

# 索引膨胀时的维护动作：重建索引可过滤 path_exists=false 的记录
memory-lifecycle-rebuild --dry-run --json   # 先查看统计
memory-lifecycle-rebuild                    # 原地重建
```

注意：`memory-lifecycle-rebuild` 过滤的是**记录文件**（`projects/*.json`）中 `path_exists=false` 的快照，不能发现「记录仍标 active 但目录已删」的残留（hook 不会为不存在的目录刷新记录）。残留条目的最终清理依赖对 `paths` key 的磁盘存在性核验，属于后续演进项，不在本规范范围。

## 6. 验收标准

- [x] path-index 的 cwd 主键机制与写入时机已记录（§2）
- [x] 残留条目与漏注册两类缺陷的成因与后果已记录（§3）
- [x] gateway 必须使用 `sync_single_project`、禁止 `sync_all_known_projects` 的规则及理由已成文（§4）
- [x] 代码域标注（`version_sync.py` docstring，PR #1020）与本规范互相引用
- [x] 对现有实现无行为变更（纯文档规范）

## 7. 参考

- `memory_core/tools/version_sync.py` — 模块 docstring 设计标注（M3）；`sync_all_known_projects` / `sync_single_project` / `probe_version_and_sync` 实现
- `memory_core/tools/project_lifecycle.py` — `_path_index_key` / `record_project_lifecycle` / `rebuild_path_index`
- `memory_core/tools/_gateway_handlers.py` — `_handle_session_start_setup`（session-start 探测挂载点）
- [MULTI_PROJECT_SCAN_SPEC.md](MULTI_PROJECT_SCAN_SPEC.md) — SPEC-012，多项目升级扫描 registry 指针规范
- [MEMORY_LOCK_SPEC.md](MEMORY_LOCK_SPEC.md) — SPEC-010，版本锁与兼容矩阵
- INFRA-545（`.sync.lock` 并发防护，PR #1019）、INFRA-546（本规范）
