# Workbot Adapter: Memory Routing Rules

Status: rule-only, records-cleared
Scope: adapter

> 本文件是 workbot adapter 级别的路由规则，不是模块默认路由。
> 其他 adapter 可以定义自己的路由规则，不受本文件约束。

## Routing Rules
- Rule layer is read-first for policy decisions.
- Historical materials route to frontstage quarantine, not canonical memory.
- Locked project domains are read-only unless owner authorizes change.

## Truth Basis

### Source Refs
- `workspace/INDEX.md`

### Authority Refs
- `workspace/project-map/legal-core-map.md`

### Evidence Refs
- `workspace/tools/memory_hook_gateway.py`

### Conflict Status
- `resolved`
