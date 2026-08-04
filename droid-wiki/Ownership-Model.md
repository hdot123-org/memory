# Ownership Model

> See also: [Modules](Modules.md) (`memory_core/ownership.py`), [Gateway and Hooks](Gateway-and-Hooks.md)

The ownership model decides, for any path, **whether a tool is allowed to write to it**. It powers the PreToolUse guard and the source-repo-readonly enforcement.

## Goals

1. Protect protocol-critical paths in **this** repository (which is source-repo-readonly).
2. Let consuming projects declare their own protected domains via `ownership.toml` and `AGENTS.md` managed blocks.
3. Keep the model fail-safe: classification errors default to **deny**.
4. Stay auditable: every decision has a kind, a level, and a reason.

## Core types (`memory_core/ownership.py`)

### `ProtectionLevel` (enum, ordered least -> most strict)

| Level | Behavior |
|---|---|
| `RECOMMENDED` | Soft protection; warnings only, writes pass |
| `STANDARD` | Requires explicit override to write |
| `CRITICAL` | Denies most operations; only narrowly allow-listed writes pass |

### `OwnershipKind` (enum)

- `DOMAIN` — a directory domain (e.g., `memory/docs`)
- `RESOURCE` — a specific resource file

### `OwnershipDomain` (frozen dataclass)

```python
@dataclass(frozen=True)
class OwnershipDomain:
    name: str                 # e.g., "memory_docs"
    path: str                 # forward-slash relative path from project root
    level: ProtectionLevel
    recursive: bool = True
    description: str = ""
```

`__post_init__` normalizes the path to forward slashes with no leading/trailing slash.

### `OwnershipResource` (frozen dataclass)

```python
@dataclass(frozen=True)
class OwnershipResource:
    name: str
    path: str
    level: ProtectionLevel
    domain: str | None = None
```

## Resolution inputs

The model consumes two sources:

1. **`memory/system/ownership.toml`** — declarative domain and resource declarations
2. **`AGENTS.md` managed blocks** — embedded ownership annotations parsed by the model

Both are merged into a unified ownership table at gateway startup.

## Source-repo modes

`memory_core/constants.py` defines two modes:

| Mode | Behavior |
|---|---|
| `SOURCE_REPO_MODE_READONLY` | All writes blocked. This is the mode for the memory-core repository itself. |
| `SOURCE_REPO_MODE_DEVELOP` | Normal project mode. Ownership table decides per path. |

The mode is detected from the repository's `ownership.toml`. The PreToolUse guard consults the mode before consulting the ownership table, so readonly mode is a hard outer fence.

## PreToolUse guard flow

```
tool call (Write/Edit/Create/etc.)
   |
   v
pretooluse_guard.resolve(path)
   |
   |-- is the repo in SOURCE_REPO_MODE_READONLY?  -> DENY (source repo)
   |-- classify path:
   |      1. exact resource match?                -> use resource level
   |      2. domain match (recursive)?            -> use domain level
   |      3. AGENTS.md managed-block match?       -> use block level
   |      4. no match?                            -> default policy
   |
   v
decision: ALLOW | DENY | WARN
   |
   v
   on DENY:  block the tool call, return reason
   on WARN:  allow + record warning
   on ALLOW: proceed
```

Classification helpers live in `_guard_classify.py` (path classification, 22 KB) and `_guard_patterns.py` (pattern definitions).

### Output format (dual-format for backward compatibility)

The guard outputs JSON in **both** legacy and Factory official formats:

```json
{
  "decision": "allow",
  "reason": "path not in protected domains",
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "path not in protected domains"
  }
}
```

**Field mapping:**

| Legacy field | Factory official field | Notes |
|--------------|------------------------|-------|
| `decision: "allow"` | `permissionDecision: "allow"` | Direct mapping |
| `decision: "block"` | `permissionDecision: "deny"` | Note: "block" → "deny" |
| `reason` | `permissionDecisionReason` | Same text |
| (none) | `hookEventName: "PreToolUse"` | Always "PreToolUse" |

**Exit codes:** 0 = allow, 2 = deny (unchanged from legacy format).

## AGENTS.md managed blocks

`AGENTS.md` can carry managed blocks that the ownership model parses:

```
<!-- memory-core:ownership-domain name="memory_docs" path="memory/docs" level="standard" recursive="true" -->
...content...
<!-- /memory-core:ownership-domain -->
```

The model recognizes these block delimiters and incorporates them into the ownership table. This lets projects keep ownership declarations co-located with agent guidance.

## `memory-ownership` CLI

```bash
memory-ownership --target /path/to/project <subcommand>
```

Subcommands support inspecting the resolved ownership table, listing domains/resources, and explaining why a path would be allowed or denied. Useful for debugging guard decisions without running a real hook event.

## Boundary enforcement (this repo)

For the memory-core repository itself, [docs/specs/BOUNDARY.md](https://github.com/hdot123/memory/blob/main/docs/specs/BOUNDARY.md) formalizes the rule:

| Belongs in this repo | Does NOT belong |
|---|---|
| Core code under `memory_core/tools/` | Real project PLAN/STATE/CANONICAL/NOW |
| Tests under `tests/` | Real project task assignment |
| Protocol + schema definitions | Real project workspace files |
| Templates and demo fixtures | Real project business state |
| Cross-project lessons/decisions | Per-project runtime state |
| Repo config (`pyproject.toml`, `.github/`, etc.) | |

`.gitignore` enforces additional pollution guards, blocking paths like `workspace/projects/*/STATE.md` and `workspace/memory/kb/projects/*/PLAN.md`. Any PR that tries to land business state must be rejected at code review.

## Fail-safe semantics

- Path classification errors default to **deny**.
- Missing `ownership.toml` falls back to the built-in defaults (conservative).
- Conflicting declarations (`STANDARD` vs `CRITICAL` on the same path) resolve to the **strictest** level.
- `AGENTS.md` parse failures do not silently relax protections; the model treats them as a degraded configuration and records a warning.

## Integration points

| Caller | What it asks the model |
|---|---|
| `pretooluse_guard` | "Is this write allowed?" |
| `memory_hook_gateway` | "Should this event short-circuit?" (via business policy that consults ownership) |
| `memory-validate` | "Is the ownership table well-formed?" |
| `memory-ownership` CLI | "Show me the resolved table / explain this decision." |
