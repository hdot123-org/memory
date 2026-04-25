# Workbot Adapter: Ingestion Registry Map

Status: rule-only, records-cleared
Scope: adapter

> 本文件是 workbot adapter 级别的摄入登记册，不是模块默认登记。
> 其他 adapter 可以定义自己的登记范围，不受本文件约束。

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
