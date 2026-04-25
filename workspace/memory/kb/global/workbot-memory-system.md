# Workbot Memory System Rules

Status: rule-only, records-cleared
Scope: adapter

> 本文件是 workbot adapter 级别的记忆系统规则，不是模块默认记忆系统。
> 其他 adapter 可以定义自己的记忆系统规则，不受本文件约束。

## Layer Priority
1. Code and runtime facts
2. Locked project documents
3. Rule layer
4. Historical files as evidence only

## Policy
- No historical file may overwrite locked truth.
- Any conflict requires explicit owner confirmation.

## Truth Basis

### Source Refs
- `workspace/INDEX.md`

### Authority Refs
- `workspace/project-map/legal-core-map.md`

### Evidence Refs
- `workspace/tools/memory_hook_gateway.py`

### Conflict Status
- `resolved`
