# ShowDoc Sync Record

> 本文件记录 ShowDoc 与 Git 的同步状态

## 2026-05-14: v0.4.0 Beta 发布同步

### Scope

- Git source: README.md, docs/DOT_MEMORY_SPEC.md, docs/MEMORY_LOCK_SPEC.md, docs/PLAN-STATUS.md, CONTRIBUTING.md, CHANGELOG.md
- ShowDoc project: 664858316 (35 pages)

### Changes

| Page | Direction | Status | Notes |
|------|-----------|--------|-------|
| Alpha → Beta 质量加固计划 (269622139) | Git ↔ ShowDoc | synced | status→completed, all checklist [x] |
| CLI API 冻结清单 (269622140) | Git → ShowDoc | synced | 11 CLI signatures frozen |
| Python API 文档 (9 pages) | Git → ShowDoc | synced | hook_event, interfaces, CoreConfig, adapter, schema, root_discovery, lifecycle, constants |
| ShowDoc 同步闭环流程规范 (269622149) | Git → ShowDoc | synced | 流程规范 + 页面清单 + 收尾 checklist |
| 专业级项目文档管理计划 | Git → ShowDoc | synced | 文档管理计划 |

### Verification

- [x] Version matches CURRENT_MEMORY_VERSION (0.4.0)
- [x] Plan checklist matches Git facts
- [x] Archived pages in docs/archive/
- [x] Design docs have snapshot annotations
- [x] All tests pass (1351 passed)
- [x] Lint clean (F821/F401/F841/E741 all zero)
