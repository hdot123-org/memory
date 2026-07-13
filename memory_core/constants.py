"""Single source of truth for memory-core versions, hosts, and schema definitions."""

import re

CURRENT_MEMORY_VERSION = "0.8.1"

SUPPORTED_HOSTS = ("factory",)

SYSTEM_DIR = "memory/system"

REQUIRED_MEMORY_FILES = [
    "memory.lock",
    "adapter.toml",
    "migrations.log",
]

REQUIRED_MEMORY_DIRS = [
    "kb/projects",
    "kb/decisions",
    "kb/lessons",
    "kb/global",
]

CANONICAL_MEMORY_LOCK_SCHEMA = "context-package-v1"
CANONICAL_ADAPTER_VERSION = "builtin"

# Ownership protection schema version
OWNERSHIP_SCHEMA_VERSION = "memory-ownership-v1"

# Migration log line pattern: "timestamp | from | to | status | detail"
# Example: "2026-05-09T12:34:56Z | 0.1.0 | 0.2.0 | success | Migrated from ..."
MIGRATION_LOG_LINE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\s*\|\s*\S+\s*\|\s*\S+\s*\|\s*\S+\s*\|.*$"
)

MESSAGE_VERSION_MISMATCH_UPGRADE_NEEDED = "version_mismatch_upgrade_needed: please run memory-migrate --from {current} --to {target}"
MESSAGE_VERSION_MISMATCH_DOWNGRADE_DETECTED = "version_mismatch_downgrade_detected: project pinned to {current} > installed {target}; install matching memory-core or open issue"

# Source repo modes
SOURCE_REPO_MODE_READONLY = "readonly"
SOURCE_REPO_MODE_DEVELOP = "develop"
VALID_SOURCE_REPO_MODES = (SOURCE_REPO_MODE_READONLY, SOURCE_REPO_MODE_DEVELOP)

# Migration error codes
_BACKUP_FAILED = "backup_failed"


# v0.8.0 author rewrite verified
