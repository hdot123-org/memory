# 项目地图治理

project-map 结构、合法性校验与治理标记。

## 1. Project-Map 结构

project-map 子系统由下列文件组成：

| 文件 | 职责 |
|------|------|
| `project-map/INDEX.md` | 项目地图索引，声明唯一合法入口 |
| `project-map/legal-core-map.md` | 合法核心地图，列出所有 `active-legal` 条目 |
| `project-map/ingestion-registry-map.md` | 摄取注册表，分类 `incoming-raw` 和 `compatibility-only` |
| `project-map/governance.md` | 治理规则，声明合法性清洗和 git-commit gate |

## 2. ProjectMapValidator 14 条标记检查

ProjectMapValidator 对上述 4 个文件执行 14 条标记检查：

**INDEX.md 检查（4 条）：**
1. 包含「唯一合法入口」标记
2. 包含「只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。」
3. 包含「同次 `git commit` 提交后才生效」
4. 不包含过渡期文件引用

**legal-core-map.md 检查（3 条）：**
5. 包含 `active-legal` 标记
6. 包含「只有本图列出的 `active-legal` 条目或目录，才是当前合法资料。」
7. 不包含过渡期文件引用

**ingestion-registry-map.md 检查（4 条）：**
8. 包含 `incoming-raw` 和 `compatibility-only` 分类
9. 包含 `absorbed` 和 `retired` 状态定义
10. 包含 git-commit gate 标记

**governance.md 检查（3 条）：**
11. 包含合法性清洗标记（见下方第 4 节）
12. 包含地图授予合法性标记（见下方第 4 节）
13. 包含目录登记 git-commit 规则标记（见下方第 4 节）

## 3. 跨文件契约校验

`validate_unique_legal_system_contract()` 额外检查 12 条跨文件契约：

- workspace INDEX.md 引用 project-map 并声明 active-legal 规则
- overview 文档引用 project-map
- docs INDEX.md 将 docs 子树降级为 project-map 控制的 raw material
- global INDEX.md 将非 local-canonical 文件降级到 legality registry
- legal-core-map 包含所有必需标记
- ingestion-registry-map 包含所有必需 scope
- hook contract 包含 map-only context 和 registration gate 标记

## 4. 治理标记（强制校验）

下列标记必须出现在本文件中，供 ProjectMapValidator 校验：

- 未经过唯一真相系统清洗
- 只有地图中被明确标为 `active-legal` 的条目或目录，才授予合法性。
- 未完成同次 `git commit` 的目录登记，不得视为生效。

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- project-map/INDEX.md
- memory/kb/global/memory-system.md

### Evidence Refs

- tests/conftest.py

### Conflict Status

- resolved
