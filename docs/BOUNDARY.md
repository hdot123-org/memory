# Memory 仓库边界

> 版本：v1.0 / 2026-04-29
> 本文件定义 `memory` 仓库的职责范围，明确什么属于本仓库、什么不属于。

---

## 1. 仓库定位

`memory` 是一个**通用记忆层模块仓库**，承载协议定义、模板、Schema、Validator、Migration 工具、以及示例 Fixture。

它是一个**可复用的库（library / module）**，不是任何具体业务项目的状态存储。

---

## 2. 属于 memory 仓库的内容

| 类别 | 路径示例 | 说明 |
|------|----------|------|
| 核心代码 | `memory_core/tools/` | memory hook 接口、实现、Gateway、Schema、Validator |
| 测试 | `tests/` | 单元测试、集成测试 |
| 协议与 Schema | `memory_core/tools/memory_hook_schema.py` | 数据结构定义、校验逻辑 |
| 模板 | `templates/` | 代码审查模板、分析脚本等通用模板 |
| 文档 | `docs/` | 仓库级文档（边界、架构、验收报告等） |
| 审查记录 | `review/`, `reviews/`, `analysis/`, `audit/` | 代码审查与分析产出 |
| 示例 Fixture | `examples/`（如存在） | demo 级别的示例，不代表真实项目状态 |
| 项目配置 | `pyproject.toml`, `.gitignore`, `.github/` | 构建、CI、发布配置 |
| Lessons Learned | `memory_core/kb/lessons/` | 通用经验教训，不绑定具体项目 |
| 决策记录 | `memory_core/kb/decisions/` | 架构或设计决策，不绑定具体项目 |
| 全局规范 | `memory_core/kb/global/` | 跨项目通用规范（如 Projects 制定规范框架） |

---

## 3. 不属于 memory 仓库的内容

| 类别 | 归属地 | 说明 |
|------|--------|------|
| 真实业务项目的 PLAN | `<业务项目>/memory/kb/projects/*/PLAN.md` | 每个业务项目在自己的 `memory/` 下管理计划 |
| 真实业务项目的 STATE | `<业务项目>/memory/kb/projects/*/STATE.md` | 执行状态属于业务项目自身 |
| 真实业务项目的 CANONICAL | `<业务项目>/memory/kb/projects/*/CANONICAL.md` | 项目规范描述属于业务项目自身 |
| 业务项目的工作区文件 | `<业务项目>/workspace/` | 业务项目的工作区不属于 memory |
| 业务项目的 NOW.md | `<业务项目>/NOW.md` | 业务项目当前状态不属于 memory |
| 业务项目的具体任务分派 | `<业务项目>/memory/system/` | 任务执行配置属于业务项目 |

---

## 4. 核心原则

### 4.1 单一归属原则

**每个真实业务项目的配置和状态（adapter.toml, ownership.toml, memory.lock）只能存在于该业务项目自身的 `memory/system/` 目录下。**

memory 仓库不得成为任何具体业务项目的状态存储。

### 4.2 Fixture 与真实数据分离

- memory 仓库中的示例只能是 **demo fixture**（虚构的、最小化的、用于演示或测试的数据）
- 真实业务数据（AxonHub、WorkBot 等项目的实际 PLAN/STATE）必须存放在各自的项目仓库中

### 4.3 通用 vs 专用

- memory 仓库只存放**跨项目通用的**协议、模板、Schema、Validator、Lesson
- 任何**绑定具体业务上下文**的内容（如 AxonHub 的 rebase 计划、业务项目的执行状态）属于业务项目

### 4.4 业务项目 `memory/system/` 是项目配置归属地

每个使用 memory 模块的业务项目，其 `memory/system/` 目录才是该项目的：
- 配置管理地（adapter.toml, ownership.toml）
- 版本锁定地（memory.lock）
- 迁移日志（migrations.log）

---

## 5. 污染防护

### 5.1 `.gitignore` 禁止清单

仓库根目录 `.gitignore` 已配置污染路径防护规则，禁止以下路径被提交：

- `workspace/projects/*/STATE.md`
- `workspace/projects/*/PLAN.md`
- `workspace/projects/*/CANONICAL.md`
- `workspace/projects/*/NOW.md`
- `workspace/memory/kb/projects/*/STATE.md`
- `workspace/memory/kb/projects/*/PLAN.md`
- `workspace/memory/kb/projects/*/CANONICAL.md`

### 5.2 准入检查

任何向 memory 仓库提交涉及业务项目状态文件的 PR，必须在 code review 中被拒绝并要求迁移到业务项目仓库。

---

## 6. 例外情况

以下情况允许在 memory 仓库中保留项目相关文件：

1. **Demo Fixture**：用于演示 memory 模块功能的虚构项目示例（文件名须带 `demo-` 或 `fixture-` 前缀）
2. **测试数据**：测试用例使用的最小化 mock 数据
3. **通用规范框架**：不绑定具体项目的规范模板（如 `global/projects-spec.md` 的通用框架部分）

---

## 7. 违反边界的处置

发现违反边界的内容时：

1. 记录到 `docs/RESIDUE_INVENTORY.md`
2. 迁移真实业务数据到对应业务项目仓库
3. 或将内容转为 demo fixture（去除真实业务上下文）
4. 在 `docs/RESIDUE_DISPOSITION_PLAN.md` 中跟踪处置进度


---

## 8. 同步方向约束（铁律）

### 8.1 三端关系

```
Local (Agent/Developer)
    |
    v push branch only
GitLab (source of truth)
    |
    v CI pipeline pass -> merge
    ├── sync-to-github job
    │   v
    │   GitHub (read-only mirror)
    │
    └── sync-to-showdoc job
        v
        ShowDoc (read-only mirror)
```

### 8.2 规则

| 规则 | 说明 |
|------|------|
| Local -> GitLab | 通过分支 + MR，CI 门禁通过后合并 |
| GitLab -> GitHub | 仅 CI sync-to-github job，且必须在 test + health-check 通过后 |
| GitLab -> ShowDoc | 仅 CI sync-to-showdoc job，且必须在 test + health-check 通过后 |
| 禁止 Local -> GitHub | 任何机器/Agent 不得直接 git push origin |
| 禁止 Local -> ShowDoc | 任何机器/Agent 不得直接调用 ShowDoc API 修改文档 |

### 8.3 适用范围

此规则适用于所有 Factory/Droid 接入的项目，不限于 memory-core。

### 8.4 CI 配置要求

每个项目的 .gitlab-ci.yml 必须定义 sync-to-github job，依赖 test + health-check。
当启用 ShowDoc 同步时（adapter.toml `[sync.showdoc]` enabled = true），
还必须定义 sync-to-showdoc job，与 sync-to-github 并行执行，同样依赖 test + health-check。

使用 memory-core `memory-init --sync --sync-showdoc` 时，项目将生成：
- `.gitlab-ci.yml` 中包含 `sync-to-github` 和 `sync-to-showdoc` 两个并行 job
- `memory/system/skills/gitlab_sync_workflow.yaml` 作为 submit_gitlab / merge_after_ci / sync_github / sync_showdoc 的标准编排模板

镜像凭证必须保存在 GitLab CI 受保护变量中：
- `GITHUB_TOKEN`（GitHub 镜像）
- `SHOWDOC_API_KEY`, `SHOWDOC_API_TOKEN`（ShowDoc 认证）

### 8.5 ShowDoc 同步特性

- **幂等性**：按 page_title 进行 upsert，同一文件多次同步不产生重复页面
- **增量同步**：通过 SHA256 manifest（`.showdoc-manifest.json`）检测变更，仅同步有变更的文件
- **失败容忍**：单个文件失败不阻断其余文件同步
- **安全子集**：同步前验证 Markdown 内容符合 showdoc-markdown-compat 安全子集

### 8.6 违规处置

发现直推 GitHub 时回退违规 commit，重新通过 GitLab MR 流程提交。
发现直推 ShowDoc 时记录违规，通过 CI 重新同步恢复一致性。
