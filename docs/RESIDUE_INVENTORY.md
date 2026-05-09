# Residue 清单 — 本地有但远程 origin/branch-1 没有的内容

> 生成时间：2026-04-29
> 对比基准：本地 branch-2 vs origin/branch-1
> 涉及 commit：2 个未推送 commit

---

## 未推送 Commit 总览

| # | Commit | 消息 | 文件数 | 变更行数 |
|---|--------|------|--------|----------|
| 1 | `fc08100` | feat: add Projects 通用规范 + AxonHub Rebase 项目知识 | 8 | +2230 / -3 |
| 2 | `931027` | feat: add axonhub-rebase canonical descriptor | 2 | +88 / -1 |

---

## 文件级 Residue 明细

### R-01: `workspace/memory/kb/projects/axonhub-rebase/PLAN.md`

| 属性 | 值 |
|------|-----|
| 大小 | 948 行 |
| Commit | `fc08100` |
| 类型 | **真实业务项目状态** |
| 内容 | AxonHub Rebase 完整执行计划，包含分支状态、任务分解（W1-W6）、CI 命令等 |
| 建议 | **迁移** — 迁移到 `axonhub` 业务项目的 `.memory/kb/projects/axonhub-rebase/PLAN.md` |
| 理由 | 这是 AxonHub 项目的真实执行计划，包含具体的仓库路径、分支名、任务分解，属于业务项目自身状态 |

### R-02: `workspace/memory/kb/projects/axonhub-rebase/STATE.md`

| 属性 | 值 |
|------|-----|
| 大小 | 37 行 |
| Commit | `fc08100` |
| 类型 | **真实业务项目状态** |
| 内容 | AxonHub Rebase 执行状态跟踪表，引用本地路径 `/Users/busiji/tool/axonhub` |
| 建议 | **迁移** — 迁移到 `axonhub` 业务项目的 `.memory/kb/projects/axonhub-rebase/STATE.md` |
| 理由 | 这是真实项目的执行状态，包含本地文件系统路径引用，不属于 memory 仓库 |

### R-03: `workspace/memory/kb/projects/axonhub-rebase/CANONICAL.md`

| 属性 | 值 |
|------|-----|
| 大小 | 87 行 |
| Commit | `931027` |
| 类型 | **真实业务项目状态** |
| 内容 | AxonHub Rebase 项目 Canonical 描述 |
| 建议 | **迁移** — 迁移到 `axonhub` 业务项目的 `.memory/kb/projects/axonhub-rebase/CANONICAL.md` |
| 理由 | 这是具体项目的规范描述，不属于 memory 通用仓库 |

### R-04: `workspace/NOW.md`

| 属性 | 值 |
|------|-----|
| 大小 | 6 行变更 |
| Commit | `fc08100` |
| 类型 | **业务项目当前状态** |
| 内容 | 更新 NOW.md，添加 AxonHub Rebase 执行任务 |
| 建议 | **迁移** — NOW.md 属于业务项目的状态文件，应迁移到业务项目或转为 memory 仓库级 mission 描述 |
| 理由 | NOW.md 中的 "Next 3 Actions" 提到了具体的 AxonHub Rebase 业务任务，这是业务项目的当前状态 |

### R-05: `workspace/memory/kb/global/projects-spec.md`

| 属性 | 值 |
|------|-----|
| 大小 | 794 行 |
| Commit | `fc08100` |
| 类型 | **混合内容 — 大部分可保留，部分需剥离** |
| 内容 | GitHub Projects 通用制定规范框架（前部） + AxonHub 特定 CI 命令（尾部） |
| 建议 | **保留 + 清理** — 保留通用规范框架部分（约前 700 行），剥离 AxonHub 特定 CI 命令 |
| 理由 | 通用框架属于 memory 仓库（定义项目制定规范），但末尾的 `ssh ce-01` CI 命令是 AxonHub 特定运维信息，应迁移到 AxonHub 项目 |

### R-06: `workspace/memory/kb/projects/INDEX.md`

| 属性 | 值 |
|------|-----|
| 大小 | 6 行新增 |
| Commit | `fc08100` + `931027` |
| 类型 | **索引更新 — 需随 residue 清理** |
| 内容 | 添加了 axonhub-rebase 项目索引条目 |
| 建议 | **更新** — 在 axonhub-rebase 条目迁移后，INDEX.md 需同步移除该条目或标注为已迁移 |
| 理由 | 索引文件需要与实际存在的项目目录保持一致 |

### R-07: `workspace/memory/kb/global/INDEX.md`

| 属性 | 值 |
|------|-----|
| 大小 | 1 行新增 |
| Commit | `fc08100` |
| 类型 | **索引更新 — 可保留** |
| 内容 | 添加 projects-spec 索引条目 |
| 建议 | **保留** — 通用规范索引条目是合理的 |
| 理由 | 这是指向通用规范文件的索引，属于 memory 仓库职责 |

### R-08: `templates/analyze-for-review.py`

| 属性 | 值 |
|------|-----|
| 大小 | 298 行 |
| Commit | `fc08100` |
| 类型 | **通用模板 — 可保留** |
| 内容 | 代码审查分析脚本 |
| 建议 | **保留** — 这是通用工具模板，不属于任何业务项目 |
| 理由 | 模板文件是 memory 仓库的合理内容 |

### R-09: `templates/code-review-template.md`

| 属性 | 值 |
|------|-----|
| 大小 | 143 行 |
| Commit | `fc08100` |
| 类型 | **通用模板 — 可保留** |
| 内容 | 代码审查模板 |
| 建议 | **保留** — 这是通用模板，不属于任何业务项目 |
| 理由 | 模板文件是 memory 仓库的合理内容 |

---

## 汇总统计

| 建议 | 文件数 | 说明 |
|------|--------|------|
| **迁移到业务项目** | 3 | PLAN.md, STATE.md, CANONICAL.md（axonhub-rebase） |
| **迁移 + 剥离** | 1 | NOW.md（业务状态需迁出） |
| **保留 + 清理** | 1 | projects-spec.md（剥离末尾 AxonHub CI 命令） |
| **更新索引** | 1 | projects/INDEX.md（移除已迁移条目） |
| **保留** | 3 | templates/* (2), global/INDEX.md |

---

## 分类标签

- 🔴 **必须迁出**：R-01, R-02, R-03, R-04（真实业务状态）
- 🟡 **需清理**：R-05（混合内容）
- 🟢 **可保留**：R-07, R-08, R-09（通用模板/索引）
- 🔵 **需同步**：R-06（索引更新）

---

## 2026-05-09 Phase 1 闭环 — Workbot/AxonHub Residue 迁出

> 触发：`docs/audit/2026-05-09-memory-core-audit.md` A.13/A.14（P0-1/P0-2 业务残留违反 BOUNDARY 4.1）
> 决策：Phase1=A（真正迁出到 archive/，保留可回滚；详见 `archive/legacy-workbot/README.md`）

### 迁出文件清单（kb，8 个）

| 文件 | 原路径 | 新位置 | 原因 |
|---|---|---|---|
| workbot.md | `memory_core/memory/kb/projects/workbot.md` | `archive/legacy-workbot/kb/workbot.md` | workbot 项目真相，违反 BOUNDARY 4.1 |
| workbot-truth-model.md | `memory_core/memory/kb/global/` | `archive/legacy-workbot/kb/` | 同上 |
| workbot-memory-system.md | 同 | 同 | 同上 |
| workbot-hook-contract.md | 同 | 同 | 同上 |
| workbot-project-map-governance.md | 同 | 同 | 同上 |
| workbot-policy-pack.md | 同 | 同 | 同上 |
| workbot-policy-pack.json | 同 | 同 | 同上 |
| workbot-memory-routing.md | 同 | 同 | 同上 |

### 迁出文件清单（tests-disabled，7 个）

| 文件 | 原路径 | 新位置 | 原因 |
|---|---|---|---|
| test_m3_doc_scope_coverage.py | `tests/` | `archive/legacy-workbot/tests-disabled/` | 直接读取 6 个 workbot-* 文件 |
| test_m3_consumer_truth_cleanup.py | 同 | 同 | 读 workbot-memory-routing.md + workbot.md |
| test_m3_policy_pack_wiring.py | 同 | 同 | 读 workbot-policy-pack.json |
| test_m2_adapter_extraction.py | 同 | 同 | 读 workbot-hook-contract.md |
| test_memory_hook_core_m5_adapter_slimming.py | 同 | 同 | 读 workbot-* kb |
| test_business_policy_errors.py | 同 | 同 | 读 workbot-* kb |
| test_m7_independent_repo_baseline.py | 同 | 同 | 读 workbot-project-map-governance.md |
| test_m7_p3_smoke.py | 同 | 同 | 自标 "workbot-scoped"，强制启用 workbot adapter，需 8 个 kb 文件 |

### 内容剥离

- `memory_core/memory/kb/global/projects-spec.md` 第 11 节"CE-01 自动化部署"（含 SSH 别名 `ce-01`、IP `REDACTED_IP`、Docker 服务名、镜像版本等 AxonHub 专属运维信息）→ 剥离到 `archive/legacy-workbot/projects-spec-axonhub-section.md`
- 同 spec 第 4 节中的 `AxonHub Rebase`/`AxonHub Audit`/`Youzy Clone` 任务名示例 → 替换为 `<Project>` 通用占位符

### 索引改写

- `memory_core/INDEX.md`：删除"真相模型 canonical：`workbot-truth-model.md`"硬绑定，改为"由各业务项目通过 adapter runtime profile 自行声明，memory-core 仓库不内建任何业务项目专属的真相模型文件"

### Pytest 路径

- `pyproject.toml` 中 `testpaths = ["tests"]` 已确保 `archive/` 不被默认收集，无需额外 norecursedirs 配置

### 已知约束

- `memory_core/tools/memory_hook_adapters/workbot_runtime_profile.py` 仍硬编码引用了部分原路径，**仅在 `MEMORY_HOOK_ADAPTER=workbot` 时生效**。如需启用 workbot adapter，需按 `archive/legacy-workbot/README.md` 中的恢复步骤先恢复文件。

### 恢复方法

见 `archive/legacy-workbot/README.md` "恢复方法" 段。
