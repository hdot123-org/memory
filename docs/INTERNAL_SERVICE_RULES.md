# Internal Service Rules — 内部服务技能约束

> 版本: 1.0.0 | 创建: 2026-05-19 | 状态: draft
> 适用范围: 约束 "内部服务" 类 skill，使其仅被自定义 skill/droid 调用，不直接暴露给用户
> 权威源: Git (L1)

---

## 0. 总则

以下 5 个 skill 被归类为 **Internal Service**（内部服务），意味着：
- 它们 **不是** 用户直接调用的 skill
- 它们 **只能** 被自定义的 orchestrator skill/droid 编排调用
- 它们 **必须** 在执行前后进行安全验证和注册表维护

当用户直接请求涉及这些 skill 的操作时，Agent **必须** 将请求路由到自定义 skill 层（`feishu-platform-rules`、`sync-cross-platform-rules`、`doc-management`），而非直接调用这些内部服务。

---

## 1. lark-doc

### [Skill Name] lark-doc
- **优先级**: 🔴 Critical — 最高风险，最可能绕过我们的同步管线
- **Access Level**: Internal Service Only (not user-facing)
- **Can Be Called By**:
  - `feishu-platform-rules` (飞书文档操作规则 skill)
  - `sync-cross-platform-rules` (跨平台同步规则 skill)
  - `doc-management` (文档管理 skill)
  - `doc-governance` (文档治理 skill)
- **Must NOT**:
  - Must NOT be triggered by standalone "create a Feishu doc" / "写一个飞书文档" 等直接用户请求
  - Must NOT create documents outside the defined wiki space structure (mirroring ShowDoc catalog)
  - Must NOT overwrite documents registered in `sync_registry.yaml` without first validating content against `showdoc-markdown-compat` safety subset
  - Must NOT create C9 (会议纪要) documents without registering in sync_registry with `authority: feishu`
  - Must NOT add images, H1 headings, or any element outside the 19-item safety subset to synced documents
  - Must NOT execute `docs +create` or `docs +update` without first checking sync_registry for existing mappings
- **Must**:
  - Must validate content against `showdoc-markdown-compat` 19-item safety subset before writing
  - Must register all created/updated document entries in `docs/sync_registry.yaml` (feishu_doc_id, last_feishu_sync timestamp, content_hash)
  - Must add protection banners to synced documents (C1-C8, C10 categories):
    ```
    <!-- sync_info: source=showdoc, item_id=XXX, page_id=XXX, last_sync=YYYY-MM-DD -->
    > 📋 **本文档为自动同步镜像** — 请勿直接编辑
    ```
  - Must confirm document category (C1-C10) before writing, using doc-management classification rules
  - Must log all operations to `docs/audit/showdoc-sync-YYYY-MM-DD.md`
- **Trigger Override**:
  - When user requests "create a Feishu doc" directly → route through `feishu-platform-rules` first
  - `feishu-platform-rules` determines document category, authority source, and sync direction
  - Only after routing validation does `feishu-platform-rules` delegate to `lark-doc` for actual API calls
  - Agent must NOT invoke `lark-doc` as a direct response to user intent; always pass through the custom skill layer

---

## 2. lark-wiki

### [Skill Name] lark-wiki
- **优先级**: 🟡 Warning — 知识库管理
- **Access Level**: Internal Service Only (not user-facing)
- **Can Be Called By**:
  - `feishu-platform-rules` (飞书文档操作规则 skill)
  - `sync-cross-platform-rules` (跨平台同步规则 skill)
  - `doc-management` (文档管理 skill)
- **Must NOT**:
  - Must NOT create wiki spaces outside the 3 defined projects:
    - APISIX 网关文档 (item_id=664858315)
    - memory-core 文档 (item_id=664858316)
    - Factory Droid 功能文档 (item_id=664858317)
  - Must NOT create wiki nodes that don't mirror the ShowDoc catalog structure
  - Must NOT modify wiki space hierarchy without first consulting `doc-management` classification rules
  - Must NOT create wiki nodes under "团队协作" space for content that belongs to C1-C8, C10 categories
  - Must NOT restructure existing wiki spaces without updating `sync_registry.yaml`
- **Must**:
  - Must follow `feishu-platform-rules` routing for all wiki space creation/modification
  - Must ensure wiki node structure mirrors ShowDoc catalog structure (见 SHOWDOC_FEISHU_SYNC_PLAN §2.3)
  - Must register wiki space IDs in `sync_registry.yaml` under `feishu_wiki_space` field
  - Must validate that new wiki nodes correspond to registered pages in sync_registry
  - Must maintain the hierarchy: 项目知识空间 → 目录文件夹 → 文档节点
- **Trigger Override**:
  - When user requests "create a wiki space" or "创建知识空间" → route through `feishu-platform-rules`
  - `feishu-platform-rules` validates project mapping and catalog alignment before delegating
  - Agent must NOT invoke `lark-wiki` for structural changes without passing through the routing skill

---

## 3. lark-drive

### [Skill Name] lark-drive
- **优先级**: 🟡 Warning — 文件同步操作
- **Access Level**: Internal Service Only (not user-facing for document sync)
- **Can Be Called By**:
  - `feishu-platform-rules` (飞书文档操作规则 skill)
  - `sync-cross-platform-rules` (跨平台同步规则 skill)
  - `doc-management` (文档管理 skill)
- **Must NOT**:
  - Must NOT use `+push`/`+pull` operations for documents registered in `sync_registry.yaml`
  - Must NOT perform direct file imports for documents that should go through the sync pipeline (C1-C10)
  - Must NOT import files that haven't been validated against `showdoc-markdown-compat` safety subset
  - Must NOT upload/replace files in wiki spaces that are designated as read-only mirrors (C1-C8, C10)
  - Must NOT bypass the sync pipeline by using drive operations to update content that has a sync_registry entry
- **Must**:
  - Must check `sync_registry.yaml` before any push/pull operation — if the document is registered, use the sync pipeline instead
  - Must validate all imported files against the 19-item safety subset before entering the sync pipeline
  - Must route file operations through `sync-cross-platform-rules` for documents with `sync_enabled: true`
  - Must log drive operations that affect registered documents to audit log
  - Must preserve file integrity when downloading from cloud space for local editing before re-sync
- **Trigger Override**:
  - When user requests "push file to Feishu" or "从飞书拉取文件" → first check sync_registry
  - If document is registered with `sync_enabled: true` → route through `sync-cross-platform-rules`
  - If document is NOT registered (e.g., standalone attachment, image) → lark-drive can operate directly
  - Agent must distinguish between document sync (goes through pipeline) and file management (direct lark-drive)

---

## 4. wiki

### [Skill Name] wiki (droid-evolved wiki skill)
- **优先级**: 🟡 Warning — Factory Droid 生成的 wiki 内容
- **Access Level**: Internal Service Only (not user-facing for sync targets)
- **Can Be Called By**:
  - `doc-management` (文档管理 skill)
  - `doc-governance` (文档治理 skill)
  - `install-wiki` (CI wiki refresh skill)
- **Must NOT**:
  - Must NOT use H1 (`#`) headings in generated content — always start from H2 (`##`) to avoid ShowDoc/Feishu title conflicts
  - Must NOT generate wiki content that bypasses the sync_registry for C1-C10 categorization
  - Must NOT create wiki entries without following the doc-governance lifecycle states (draft → review → published → archived)
  - Must NOT produce content with images, H1 headings, or elements outside the 19-item safety subset if targeting ShowDoc sync
  - Must NOT generate wiki content for codebase documentation without first scanning the repository structure
- **Must**:
  - Must use H2 headings (`##`) as the highest level heading in all generated content targeting ShowDoc sync
  - Must register generated wiki entries with `sync_registry.yaml` for proper C1-C10 categorization
  - Must follow `doc-governance` lifecycle states: track content through draft → review → published → archived
  - Must validate all generated content against `showdoc-markdown-compat` safety subset before sync
  - Must include proper sync_info banners in generated documents that are part of the sync pipeline
  - Must output content in a format compatible with both ShowDoc Markdown and Feishu XML/Markdown
- **Trigger Override**:
  - When user requests "generate wiki for this repo" or "为仓库生成文档" → route through `doc-management` or `wiki` skill's own orchestration
  - The wiki skill itself orchestrates the generation, but when output targets ShowDoc/Feishu sync, it must:
    1. Validate output format against safety subset
    2. Register in sync_registry
    3. Route through `sync-cross-platform-rules` for actual sync
  - Agent must NOT use wiki-generated content for direct sync without going through the validation pipeline

---

## 5. docx

### [Skill Name] docx (local .docx editing)
- **优先级**: 🟡 Warning — 本地 Word 文档操作
- **Access Level**: Internal Service Only (not user-facing for sync targets)
- **Can Be Called By**:
  - `doc-management` (文档管理 skill)
  - `doc-governance` (文档治理 skill)
  - `feishu-platform-rules` (when importing local docs to Feishu)
- **Must NOT**:
  - Must NOT directly sync .docx content to ShowDoc or Feishu without first importing via `lark-drive`
  - Must NOT export content to sync targets without validating against `showdoc-markdown-compat` safety subset
  - Must NOT modify .docx files that are registered in sync_registry without updating the registry after changes
  - Must NOT bypass the sync pipeline by converting .docx → Markdown → direct upload
- **Must**:
  - Must import local .docx files via `lark-drive` before they can enter the sync pipeline
  - Must validate exported/converted content against the 19-item safety subset before any sync operation
  - Must convert .docx content to Markdown format compatible with both ShowDoc and Feishu before sync
  - Must register imported documents in `sync_registry.yaml` with appropriate C1-C10 category
  - Must preserve formatting fidelity during .docx ↔ Markdown ↔ ShowDoc ↔ Feishu conversions where possible
  - Must log all .docx import/conversion operations to audit trail
- **Trigger Override**:
  - When user requests "export to Word" or "导入 Word 文档" → determine if the document is part of the sync pipeline
  - If YES (registered in sync_registry) → must go through lark-drive import → validation → sync pipeline
  - If NO (standalone local document) → docx can operate directly for local editing only
  - Agent must NOT use docx skill as a shortcut to bypass the sync pipeline

---

## 6. Consolidated Internal Service Rules

The following rules apply to **ALL** internal service skills listed above. This section can be added as a preamble to each skill's SKILL.md, or maintained as a standalone wrapper skill.

### 6.1 Access Control Matrix

| Skill | User Direct Access | Via Custom Skills | Via Agent Ad-hoc |
|-------|-------------------|-------------------|-----------------|
| lark-doc | ❌ Blocked | ✅ Allowed | ❌ Blocked |
| lark-wiki | ❌ Blocked | ✅ Allowed | ❌ Blocked |
| lark-drive (sync docs) | ❌ Blocked | ✅ Allowed | ⚠️ Only for non-registered files |
| wiki (sync targets) | ❌ Blocked | ✅ Allowed | ❌ Blocked |
| docx (sync targets) | ❌ Blocked | ✅ Allowed | ⚠️ Only for local editing |

### 6.2 Universal Must-Do Rules

1. **Routing Rule**: All user requests involving these skills MUST be routed through custom skill layer first:
   - `feishu-platform-rules` → for Feishu document operations
   - `sync-cross-platform-rules` → for cross-platform sync operations
   - `doc-management` → for document lifecycle and classification

2. **Validation Rule**: ALL content written to any platform MUST be validated against `showdoc-markdown-compat` 19-item safety subset before execution

3. **Registration Rule**: ALL created/updated documents MUST be registered in `docs/sync_registry.yaml` with:
   - `showdoc_page_id` / `feishu_doc_id`
   - `doc_category` (C1-C10)
   - `authority` source designation
   - `sync_direction`
   - `last_*_sync` timestamps
   - `content_hash`

4. **Protection Rule**: ALL synced documents (C1-C8, C10) MUST have protection banners added:
   ```markdown
   <!-- sync_info: source=<platform>, item_id=XXX, page_id=XXX, last_sync=YYYY-MM-DD -->
   > 📋 **本文档为自动同步镜像**
   > - 请勿直接编辑，修改请前往权威源
   ```

5. **Audit Rule**: ALL operations MUST be logged to `docs/audit/showdoc-sync-YYYY-MM-DD.md` with:
   - Operation type and direction
   - Document IDs and categories
   - Success/failure status
   - Content hash before and after

6. **Category Rule**: ALL documents MUST be classified into C1-C10 categories before any sync operation, using `doc-management` classification rules

7. **Heading Rule**: ALL Markdown content targeting ShowDoc or Feishu sync MUST start from H2 (`##`), never H1 (`#`)

8. **Safety Rule**: ALL content MUST conform to the 19-item safety subset:
   - ✅ H2-H6 headings, bold, italic, strikethrough, inline code, underline
   - ✅ Lists (unordered, ordered, checkbox) with 2-space indent
   - ✅ Single-level blockquotes, standard tables (no alignment markers)
   - ✅ Links, code blocks with language tags, formulas ($/$$), horizontal rules, HTML comments
   - ❌ NO H1, NO [TOC], NO table alignment, NO nested quotes, NO images, NO <grid>, NO <callout>, NO <text color>, NO anchor links

### 6.3 Enforcement Mechanism

When an Agent encounters a user request that would trigger one of these internal service skills:

```
1. Intercept: Identify the user intent maps to an internal service skill
2. Classify: Determine document category (C1-C10) using doc-management rules
3. Route: Redirect to appropriate custom skill:
   ├── Feishu doc operations → feishu-platform-rules
   ├── Cross-platform sync → sync-cross-platform-rules
   ├── Document lifecycle → doc-management / doc-governance
   └── Local docx editing → docx (only if NOT registered)
4. Validate: Custom skill validates against safety subset
5. Execute: Custom skill delegates to internal service with validated params
6. Register: Update sync_registry.yaml
7. Audit: Log to audit file
```

### 6.4 Exception Handling

| Scenario | Exception | Resolution |
|----------|-----------|------------|
| User directly requests Feishu doc creation | Blocked by routing rule | Route through `feishu-platform-rules`, explain the routing |
| Document not in sync_registry but user wants to sync | Missing registration | First register in sync_registry, then proceed through pipeline |
| Content fails safety subset validation | Validation failure | Report violations, offer auto-fix, wait for user confirmation |
| lark-cli authentication expired | Auth failure | Notify user to re-authenticate, pause sync operations |
| Sync conflict detected (both sides modified) | Conflict (S1-S6) | Apply conflict resolution strategy per SHOWDOC_FEISHU_SYNC_PLAN §5 |

---

## 7. Integration with Existing Skills

### 7.1 How to Add These Rules to Existing SKILL.md Files

For each internal service skill that has an existing SKILL.md (in `~/.factory/skills/`), append the following section:

```markdown
---

## ⚠️ Internal Service Restrictions

This skill is classified as **Internal Service** in the memory-core project.
It MUST NOT be called directly by user requests.

**Allowed callers**: [list from above]
**Must route through**: [list from above]
**Must validate against**: showdoc-markdown-compat 19-item safety subset
**Must register in**: docs/sync_registry.yaml

See `docs/INTERNAL_SERVICE_RULES.md` for full constraints.
```

### 7.2 Project-Level Skill Override

If project-level skill definitions are needed (in `.factory/skills/`), create wrapper skill files that:
1. Reference the base skill
2. Add the internal service constraints as preconditions
3. Define the routing logic for user requests

Example wrapper structure for `feishu-platform-rules`:
```
~/.factory/skills/feishu-platform-rules/SKILL.md
  ├── References lark-doc, lark-wiki, lark-drive as internal tools
  ├── Defines routing logic for user requests
  ├── Validates against doc-management classification
  └── Delegates to internal services only after validation
```
