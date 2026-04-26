# Memory Docs Index

> 文档编号：MEM-DOCS-001  
> 版本：V1.6  
> 创建日期：2026-04-15  
> 维护人：memory system

---

## 1. 文档定位

本文件是 `workspace/memory/docs/` 目录的索引文档。

**作用**：
- 索引 docs 层所有正式文档
- 定义 docs 层的文档分类
- 提供文档检索入口

## 1.1 Docs 与 project-map 的关系

- docs 子树默认归入 `incoming-raw`，未被地图明确吸收前不授予合法性。
- docs 只能作为资料层，不得绕过 `project-map/INDEX.md` 进入 authority。

---

## 2. 文档分类

### 2.1 M3 Policy-Pack 系列

| 文档编号 | 文档名 | 文件路径 | 状态 | 审计就绪 |
|---------|--------|---------|------|---------|
| M3-000 | Memory Policy Pack | `../kb/global/workbot-policy-pack.md` | active | ✅ |
| M3-001 | Policy-Pack 注入设计 | `M3-policy-pack-design.md` | 可评审 | ✅ |
| M3-002 | Policy-Pack 注入说明与边界 | `M3-policy-pack-injection-guide.md` | 可评审 | ✅ |
| M3-003 | Policy-Pack 使用约束与回滚口径 | `M3-policy-pack-constraints-and-rollback.md` | 可评审 | ✅ |

**系列说明**：
M3 系列文档定义 memory-hook policy-pack 的 schema、注入机制、使用约束与回滚口径。

**证据链完整性**：
- ✅ Truth Basis 完整（Source + Authority + Evidence + Conflict Status）
- ✅ 审计追踪完整（审计矩阵 + 检查单 + 证据清单）
- ✅ 测试覆盖完整（M2 回归 + M3 QA + 负向测试）

### 2.2 M6 独立仓评估系列

| 文档编号 | 文档名 | 文件路径 | 状态 | 审计就绪 |
|---------|--------|---------|------|---------|
| M6-001 | 记忆核心独立仓评估（Go/No-Go） | `M6-memory-core-independent-repo-evaluation.md` | 可评审 | ✅ |
| M6-002 | 解耦整改清单（No-Go 后续） | `M6-decoupling-remediation-checklist.md` | 可执行 | ✅ |

**系列说明**：
M6 系列文档用于独立仓可行性审计，输出第一性原则判据、EV-1~EV-8 评估结果与正式 Go/No-Go 结论。

### 2.3 M7 独立仓迁出执行系列

| 文档编号 | 文档名 | 文件路径 | 状态 | 审计就绪 |
|---------|--------|---------|------|---------|
| M7-001 | 独立仓迁出执行计划（POR） | `M7-independent-repo-cutover-plan.md` | 可执行 | ✅ |

**系列说明**：  
M7 系列文档用于迁出执行与收口，覆盖路径去耦、契约重建、运行收敛、主仓切换与最终验收。


### 2.4 DES 设计文档系列

| 文档编号 | 文档名 | 文件路径 | 状态 | 审计就绪 |
|---------|--------|---------|------|---------|
| DES-001 | Memory 模块总体架构 | `design/01-architecture.md` | 草稿中 | ❌ |
| DES-002 | Gateway 门控设计 | `design/02-gateway.md` | 草稿中 | ❌ |
| DES-003 | Core Assembly 核心装配 | `design/03-core-assembly.md` | 草稿中 | ❌ |
| DES-004 | 接口契约层 | `design/04-interfaces.md` | 草稿中 | ❌ |
| DES-005 | 实现层 | `design/05-implementations.md` | 草稿中 | ❌ |
| DES-006 | Adapter 层 | `design/06-adapters.md` | 草稿中 | ❌ |
| DES-007 | Policy Pack 与治理 | `design/07-policy-governance.md` | 草稿中 | ❌ |
| DES-008 | 数据管道与 Sink | `design/08-data-pipeline.md` | 草稿中 | ❌ |
| DES-009 | Provider 与回退机制 | `design/09-provider-fallback.md` | 草稿中 | ❌ |
| DES-010 | 消费边界与改进建议 | `design/10-consumer-boundary.md` | 草稿中 | ❌ |

**系列说明**：  
DES 系列文档覆盖 memory 模块的完整架构设计，从总体架构、门控路由、核心装配、接口契约、实现层、适配器、策略治理、数据管道、Provider 回退到消费边界分析。

---

## 3. 文档检索

### 3.1 按主题检索

| 主题 | 相关文档 |
|------|---------|
| Policy-Pack Schema | M3-001 |
| 注入机制 | M3-001, M3-002 |
| 注入边界 | M3-002 |
| 使用约束 | M3-003 |
| 回滚机制 | M3-003 |
| 降级策略 | M3-003 |
| 独立仓评估 | M6-001 |
| Go/No-Go 判定 | M6-001 |
| 拆仓影响边界 | M6-001 |
| 解耦整改路线 | M6-002 |
| 迁出执行计划 | M7-001 |
| 总体架构 | DES-001 |
| Gateway 门控 | DES-002 |
| 核心装配 | DES-003 |
| 接口契约 | DES-004 |
| 实现层 | DES-005 |
| 适配器层 | DES-006 |
| 策略治理 | DES-007 |
| 数据管道 | DES-008 |
| Provider 回退 | DES-009 |
| 消费边界 | DES-010 |

### 3.2 按流程检索

| 流程阶段 | 相关文档 |
|---------|---------|
| 设计 | M3-001 |
| 执行 | M3-002 |
| 运维 | M3-003 |
| 治理评审 | M6-001 |
| 整改执行 | M6-002 |
| 迁出收口 | M7-001 |
| 架构设计 | DES-001 |
| 门控设计 | DES-002 |
| 核心设计 | DES-003 |
| 接口设计 | DES-004 |
| 实现设计 | DES-005 |
| 适配器设计 | DES-006 |
| 治理设计 | DES-007 |
| 管道设计 | DES-008 |
| 回退设计 | DES-009 |
| 边界分析 | DES-010 |

---

## 4. 审计就绪检查单

### 4.1 REA 审计检查单

- [ ] Truth Basis 四要素完整（source/authority/evidence/conflict）
- [ ] 文档引用关系清晰
- [ ] 边界定义明确
- [ ] 变更历史可追溯

### 4.2 QA 审计检查单

- [ ] 测试覆盖所有 policy key（PP-1 ~ PP-4, PP-6, PP-7）
- [ ] 测试覆盖所有错误码（POL-001 ~ POL-005）
- [ ] 测试覆盖注入点（context-resolve / truth-basis-gate / write-route）
- [ ] 测试覆盖回滚机制
- [ ] 测试覆盖降级策略

### 4.3 证据链审计检查单

| 证据类型 | 位置 | 状态 |
|---------|------|------|
| 接口定义 | `workspace/tools/memory_hook_interfaces.py` | ✅ |
| 实现代码 | `workspace/tools/memory_hook_impls.py` | ✅ |
| Gateway 注入 | `workspace/tools/memory_hook_gateway.py` | ✅ |
| QA 测试 | `tests/test_memory_hook_gateway_m3_policy_and_contamination.py` | ✅ |
| 主规范 | `workspace/memory/kb/global/workbot-policy-pack.md` | ✅ |

---

## 5. 与其他索引的关系

| 本文档 | 关联文档 | 关系说明 |
|--------|----------|----------|
| MEM-DOCS-001 Memory Docs Index | `../kb/INDEX.md` | 本文档索引 docs 层，kb INDEX 索引 kb 层 |
| MEM-DOCS-001 Memory Docs Index | `../kb/global/INDEX.md` | 本文档是 global kb 的下游资料层索引 |
| MEM-DOCS-001 Memory Docs Index | `../kb/projects/INDEX.md` | 本文档是 project kb 的下游资料层索引 |

---

## 5. 文档治理

### 5.1 文档状态定义

| 状态 | 定义 | 可被引用 |
|------|------|---------|
| 草稿中 | 正在编写，内容不完整 | ❌ |
| 可评审 | 内容完整，等待评审 | ✅ |
| 已冻结 | 评审通过，版本锁定 | ✅ |
| 已归档 | 历史版本，被新版替代 | ❌ |

### 5.2 文档更新流程

```text
文档编写/修改
    ↓
自我审查
    ↓
提交评审（如需要）
    ↓
评审通过
    ↓
更新状态为"已冻结"
```

---

## 6. 变更历史

| 版本 | 日期 | 变更人 | 变更内容 |
|------|------|--------|----------|
| V1.0 | 2026-04-15 | doc-bot | 初始版本，建立 M3 系列索引 |
| V1.1 | 2026-04-16 | codex | 增加 M6 独立仓评估索引（M6-001） |
| V1.2 | 2026-04-16 | codex | 增加 M6 解耦整改清单索引（M6-002） |
| V1.3 | 2026-04-16 | codex | M6 系列更新到 Batch-2 完成 / Batch-3 部分完成状态 |
| V1.4 | 2026-04-16 | codex | M6 系列更新到 Batch-3 完成并可提请复审 |
| V1.5 | 2026-04-16 | codex | M6 系列更新到 Go（彻底收口，312 passed） |
| V1.6 | 2026-04-16 | codex | 新增 M7 迁出执行计划（POR）索引入口 |
| V1.7 | 2026-04-26 | codex | 消费者无关化措辞；维护人从 workbot 改为 memory system |
| V1.8 | 2026-04-26 | codex | 新增 DES 设计文档系列索引（DES-001 ~ DES-010） |

---

**文档状态**：草稿中  
**审批人**：待定  
**下次评审日期**：待定
