"""Single source of truth for memory-core versions, hosts, and schema definitions."""

import re

from memory_core import __version__ as CURRENT_MEMORY_VERSION  # noqa: F401

__all__ = [
    "CURRENT_MEMORY_VERSION",
    "SUPPORTED_HOSTS",
    "STATUS_ENUMERATIONS",
    "SYSTEM_DIR",
    "REQUIRED_MEMORY_FILES",
    "REQUIRED_MEMORY_DIRS",
    "CANONICAL_MEMORY_LOCK_SCHEMA",
    "CANONICAL_ADAPTER_VERSION",
    "OWNERSHIP_SCHEMA_VERSION",
    "MIGRATION_LOG_LINE_PATTERN",
    "SOURCE_REPO_MODE_READONLY",
    "SOURCE_REPO_MODE_DEVELOP",
    "VALID_SOURCE_REPO_MODES",
]

SUPPORTED_HOSTS = ("factory",)

# Project lifecycle status enumerations — valid values for the ``status`` field
# in a project's ``memory/kb/projects/<name>/STATE.md`` frontmatter.
# ``active`` is the canonical default used by project templates.
STATUS_ENUMERATIONS = (
    "active",
    "planning",
    "paused",
    "deprecated",
    "archived",
    "dormant",
)

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


# Source repo modes
SOURCE_REPO_MODE_READONLY = "readonly"
SOURCE_REPO_MODE_DEVELOP = "develop"
VALID_SOURCE_REPO_MODES = (SOURCE_REPO_MODE_READONLY, SOURCE_REPO_MODE_DEVELOP)

# Migration error codes
_BACKUP_FAILED = "backup_failed"


# v0.8.0 author rewrite verified
