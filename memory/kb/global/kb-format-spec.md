# KB 格式规范

本文件记录 `memory/kb/` 下所有 canonical 与 lesson 文件必须遵循的 Truth Basis 格式要求，
以及 TruthBasisResolver 与 evidence_ref_validator 的校验语义。

适用范围：`memory/kb/global/` 下的 5 个全局 canonical 文件、`memory/kb/projects/` 下的项目 canonical 文件，
以及 `memory/kb/lessons/` 下的经验教训文件。

## 1. Truth Basis 结构要求

每个 canonical 文件与 lesson 文件必须包含一个 `## Truth Basis` 二级标题，
其下必须严格使用下列 **三级** 标题（h3），不得使用二级标题（h2）：

- `### Source Refs`
- `### Authority Refs`
- `### Evidence Refs`
- `### Conflict Status`

每一项下为 markdown bullet 列表，每条 bullet 是一个相对仓库根目录的文件路径。

### 1.1 Conflict Status 取值

`### Conflict Status` 必须恰好为单条 bullet：`- resolved`。其它取值（如 `unresolved`、`partial`、空段落）
都会使 TruthBasisResolver 的 Phase 2 报错。

### 1.2 Ref 路径书写规则

- 必须是相对仓库根目录的路径（例如 `memory/docs/记忆系统全景文档.md`、`tests/conftest.py`）。
- 禁止包含 `http://` / `https://` 这类 URL。
- 禁止使用未展开的占位符（例如 `<...>`、`~/.factory/...` 之类）。
- 禁止包含仓库外的绝对路径（例如 `/Users/...`）。

## 2. TruthBasisResolver 的 8 个校验阶段

TruthBasisResolver 在 `memory_core` scope 下会同时对 5 个全局 canonical 文件以及项目 canonical 文件进行校验，
依次执行下列 8 个阶段，前一阶段未通过则不会进入下一阶段：

| 阶段 | 名称 | 校验内容 |
|------|------|----------|
| 1 | Section Presence | 四个 h3 section 必须全部存在：Source Refs / Authority Refs / Evidence Refs / Conflict Status。 |
| 2 | Conflict Status | Conflict Status 必须恰好为 `["resolved"]`。 |
| 3 | Resolve Paths | 内部阶段：将每条 bullet 解析为 `Path` 对象（`expanduser()` + `resolve()`）。 |
| 4 | Path Existence | 所有 Ref 路径必须落在仓库根目录内，并且在磁盘上实际存在。 |
| 5 | No Overlaps | Source / Authority / Evidence 三个集合必须两两不相交；Source 与 Evidence 不得为完全相同的集合。 |
| 6 | Authority Allowed | Authority Refs 的每条路径必须属于 `authority_allowed_paths`（`project-map/INDEX.md`、`project-map/legal-core-map.md`）或 5 个全局 canonical 文件之一。 |
| 7 | Source Diversity | Source Refs 中至少要包含一条"非 canonical 来源"的路径，即不得全部被分类为 `global-canonical` / `legal-core` / `project-map-index`。 |
| 8 | Evidence Diversity | Evidence Refs 中至少要包含一条位于 `lower_evidence_roots`（例如 `tests/`）下的路径。 |

## 3. Ref 分类规则

TruthBasisResolver 的 `_classify_truth_ref` 会按路径前缀把每条 Ref 归入下列类别之一：

| 类别 | 路径模式 |
|------|----------|
| `legal-core` | `project-map/legal-core-map.md` |
| `project-map-index` | `project-map/INDEX.md` |
| `global-canonical` | 5 个全局 canonical 文件（`truth-model.md` / `memory-system.md` / `memory-routing.md` / `hook-contract.md` / `project-map-governance.md`） |
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

Phase 6 仅允许 `global-canonical` 与 `authority_allowed_paths` 内路径作为 Authority Ref；
Phase 7 要求 Source Refs 中至少有一条不属于 `global-canonical` / `legal-core` / `project-map-index` 的路径。

## 4. evidence_ref_validator 行为

`evidence_ref_validator.validate_evidence_refs_on_disk` 独立于 TruthBasisResolver，
对 `memory/kb/` 与 `memory/system/kb/` 下所有 `.md` 文件进行扫描，
校验每个 `### Evidence Refs` bullet 指向的文件是否在磁盘上存在。

关键行为：

1. **只识别 h3**：仅扫描 `### Evidence Refs`（h3）下的 bullet；`## Evidence Refs`（h2）会被完全忽略，
   该文件不会进入校验（但也会被排除在合法格式之外）。
2. **Section 解析**：从 `### Evidence Refs` 起向下读取 bullet（`- value`），
   遇到同级或更高级标题（`#` 数更少或相等）时终止。
3. **路径解析**：bullet 值先剥去两端反引号，再相对 `project_root` 解析。
4. **跳过项**：`http://` / `https://` 开头的 URL，以及含 `*` / `?` 的 glob 模式会被跳过；
   解析后逃出 `project_root` 的路径也不在职责范围内。
5. **报错条件**：解析成功且落在仓库内的路径，如果磁盘上不存在，则报错。

## 5. KB 文件编写清单

创建或编辑 `memory/kb/` 下的 `.md` 文件时，按下列清单自查：

- [ ] 包含 `## Truth Basis` 段；四个 h3 section 全部存在。
- [ ] 所有 Ref 路径相对仓库根目录，且磁盘上确实存在。
- [ ] Conflict Status 恰好为 `- resolved`。
- [ ] Source / Authority / Evidence 三类 Ref 互不相交。
- [ ] Authority Refs 仅来自 `authority_allowed_paths` 或全局 canonical 文件。
- [ ] Source Refs 至少包含一条非 canonical 来源路径。
- [ ] Evidence Refs 至少包含一条位于 `tests/` 下的路径。
- [ ] 不出现占位符（如 `<...>` 或 `~/.factory/...` 之类）。
- [ ] 不出现仓库外绝对路径（如 `/Users/...`）。
- [ ] 不出现已禁止的内容污染字符串，以免触发 `detect_pollution`。
- [ ] INDEX.md 中登记了该文件条目，且与同次 `git commit` 一并提交。

## Truth Basis

### Source Refs

- memory_core/tools/business_policy_checks.py
- memory_core/tools/evidence_ref_validator.py

### Authority Refs

- memory/kb/global/truth-model.md

### Evidence Refs

- tests/conftest.py

### Conflict Status

- resolved
