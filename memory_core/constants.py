"""Single source of truth for memory-core versions, hosts, and schema definitions."""

CURRENT_MEMORY_VERSION = "0.2.0"

SUPPORTED_HOSTS = ("codex", "claude", "factory")

REQUIRED_MEMORY_FILES = [
    "memory.lock",
    "adapter.toml",
    "CANONICAL.md",
    "PLAN.md",
    "STATE.md",
    "TASKS.md",
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

# Frontmatter requirements per file type
FRONTMATTER_REQUIREMENTS = {
    "CANONICAL.md": ["type", "title", "shortname", "status", "created", "updated"],
    "PLAN.md": ["type", "title", "shortname", "status", "created"],
    "STATE.md": ["type", "title", "shortname", "status", "updated"],
    "TASKS.md": ["type", "title", "shortname", "status"],
}
