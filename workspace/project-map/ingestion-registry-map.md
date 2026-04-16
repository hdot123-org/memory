# Ingestion Registry Map

Status: rule-only, records-cleared

## Rule
- Registry tracks `incoming-raw` and `compatibility-only` materials.
- Registration does not grant legality.
- 目录登记同次 `git commit` 提交后才生效。

## Lifecycle Status
- `incoming-raw`
- `compatibility-only`
- `absorbed`
- `retired`

## Required Registry Scopes
- `workspace/project-map/**`
- `workspace/memory/kb/global/**`
- `workspace/memory/kb/projects/**`
- `workspace/memory/docs/**`
- `workspace/memory/log/**`
- `workspace/projects/**`
- `workspace/tools/**`
- `tests/**`
