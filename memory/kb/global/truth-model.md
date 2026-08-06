# 唯一真相模型

本项目的事实来源与验证规则。

## 1. Truth Basis 概念

唯一真相模型（Truth Basis）是本项目所有事实声明的唯一来源。每个 canonical 文件和 project 文件
必须包含一个 `## Truth Basis` 段，其中严格使用下列四个三级标题（h3）：

- `### Source Refs` — 声明的来源文档路径
- `### Authority Refs` — 授权来源（project-map/INDEX.md、legal-core-map.md 或全局 canonical 文件）
- `### Evidence Refs` — 校验证据（必须包含 tests/ 下的路径）
- `### Conflict Status` — 冲突状态，必须恰好为 `- resolved`

## 2. Ref 分类规则

TruthBasisResolver 的 `_classify_truth_ref` 按路径前缀将每条 Ref 归入下列类别之一：

| 类别 | 路径模式 |
|------|----------|
| `legal-core` | `project-map/legal-core-map.md` |
| `project-map-index` | `project-map/INDEX.md` |
| `global-canonical` | 5 个全局 canonical 文件 |
| `compatibility-only` | `memory/kb/global/projects/*` |
| `project-canonical` | `memory/kb/projects/*` |
| `docs` | `memory/docs/*` |
| `project-runtime` | `projects/*` |
| `artifact` | `memory/artifacts/*` |
| `tooling` | `tools/*` |
| `log` | `memory/log/*` |
| `system` | `memory/system/*` |
| `app` | `app/*` |
| `agents` | `agents/*` |
| `gpt-web-to` | `gpt-web-to/*` |
| `repo-policy` | `AGENTS.md` |
| `workspace-entry` | `INDEX.md` |
| `other` | 其它 |

## 3. TruthBasisResolver 8 阶段校验

TruthBasisResolver 对每个 canonical 文件依次执行 8 个阶段校验：

1. **Section Presence** — 四个 h3 section 必须全部存在
2. **Conflict Status** — 必须恰好为 `["resolved"]`
3. **Resolve Paths** — 将每条 bullet 解析为 `Path` 对象
4. **Path Existence** — 所有 Ref 路径必须落在仓库根目录内且磁盘上存在
5. **No Overlaps** — Source / Authority / Evidence 三个集合必须两两不相交
6. **Authority Allowed** — Authority Refs 必须属于 `authority_allowed_paths` 或 `global_canonical`
7. **Source Diversity** — Source Refs 至少包含一条非 canonical 来源路径
8. **Evidence Diversity** — Evidence Refs 至少包含一条 `tests/` 下的路径

## 4. 关键约束

- 所有 Ref 路径必须是相对仓库根目录的路径
- 禁止包含 `http://` / `https://` URL
- 禁止使用未展开的占位符（如 `<...>` 或 `~/.factory/...`）
- 禁止包含仓库外绝对路径（如 `/home/user/...` 或 `C:\Users\...`）
- Source / Authority / Evidence 三类 Ref 互不相交

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- project-map/INDEX.md
- project-map/legal-core-map.md

### Evidence Refs

- tests/conftest.py

### Conflict Status

- resolved
