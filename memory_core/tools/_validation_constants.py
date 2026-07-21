"""Validation constants extracted from memory_hook_impls.py.

Centralises all hardcoded Chinese marker strings and Markdown section
headers used in gateway business-policy validation methods.
"""


# ---------------------------------------------------------------------------
# Project-map index markers
# ---------------------------------------------------------------------------
MKR_UNIQUE_LEGAL_ENTRY = "唯一合法入口"
MKR_ACTIVE_LEGAL_MAP_ONLY = "只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。"
MKR_GIT_COMMIT_GATE = "同次 `git commit` 提交后才生效"

# ---------------------------------------------------------------------------
# Legal-core-map markers
# ---------------------------------------------------------------------------
MKR_CORE_ACTIVE_LEGAL = "active-legal"
MKR_CORE_MAP_ONLY = "只有本图列出的 `active-legal` 条目或目录，才是当前合法资料。"

# ---------------------------------------------------------------------------
# Ingestion-registry-map markers
# ---------------------------------------------------------------------------
MKR_INCOMING_RAW = "incoming-raw"
MKR_COMPATIBILITY_ONLY = "compatibility-only"
MKR_ABSORBED_STATUS = "`absorbed`"
MKR_RETIRED_STATUS = "`retired`"
MKR_REGISTRY_GIT_COMMIT_GATE = "同次 `git commit` 提交后才生效"

# ---------------------------------------------------------------------------
# Project-map governance markers
# ---------------------------------------------------------------------------
MKR_UNWASHED_NOT_LEGAL = "未经过唯一真相系统清洗"
MKR_GOVERNANCE_MAP_GRANTS_LEGALITY = "只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。"
MKR_ATOMIC_REGISTRATION_GIT_COMMIT = "未完成同次 `git commit` 的目录登记，不得视为生效。"

# ---------------------------------------------------------------------------
# Workspace index markers
# ---------------------------------------------------------------------------
MKR_WORKSPACE_PROJECT_MAP_REF = "project-map/INDEX.md"
MKR_WORKSPACE_ACTIVE_LEGAL_MAP_ONLY = "只有被地图标为 `active-legal` 的条目或目录，才是合法资料；仅进入登记册不授予合法性。"
MKR_WORKSPACE_GIT_COMMIT_RULE = "目录登记和目录状态迁移必须与相关文件同次 `git commit` 才生效。"

# ---------------------------------------------------------------------------
# Docs index markers
# ---------------------------------------------------------------------------
MKR_DOCS_UNABSORBED = "未被地图明确吸收"

# ---------------------------------------------------------------------------
# Global index markers
# ---------------------------------------------------------------------------
MKR_NON_LEGAL_MATERIAL = "Non-Legal Material"
MKR_INGESTION_REGISTRY_REF = "ingestion-registry-map.md"

# ---------------------------------------------------------------------------
# Hook contract markers
# ---------------------------------------------------------------------------
MKR_HOOK_MAP_ONLY_CONTEXT = "gateway 只承认 `project-map/` 中被明确标为 `active-legal` 的条目或目录是合法上下文来源。"
MKR_HOOK_REGISTRATION_GATE = "未完成提交的登记不得生效"

# ---------------------------------------------------------------------------
# Markdown section headers (used in _section_body lookups)
# ---------------------------------------------------------------------------
SEC_UPSTREAM_STANDARD_SOURCES = "## 3. 正式输入源"
SEC_UPSTREAM_STANDARD_EVENTS = "## 4. 正式事件类型"
SEC_UPSTREAM_STANDARD_STATUSES = "## 6. event_status 标准"

SEC_UPSTREAM_MAPPING_SOURCES = "## 2. 正式输入源范围"
SEC_UPSTREAM_MAPPING_TABLE = "## 3. 输入源到正式事件的映射主表"
SEC_UPSTREAM_MAPPING_ROUTING = "## 4. 主路由规则"
SEC_UPSTREAM_MAPPING_ERRORS = "## 5. 错误码与原因码"

SEC_FORMAL_CONTRACT_SOURCES = "## 3. source_type 正式白名单"
SEC_FORMAL_CONTRACT_EVENTS = "## 4. event_type 正式清单"
SEC_FORMAL_CONTRACT_STATUSES = "## 6. event_status 正式取值"
