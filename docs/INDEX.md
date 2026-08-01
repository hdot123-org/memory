# 全局知识文档索引

> 本目录是 memory-core 仓库的展示层，AutoWiki 扫描此目录生成 Factory App Wiki。
> 运行时路由仍由 `memory/kb/` 和 `memory/docs/` 负责。

## 目录结构

### architecture/ — 架构设计
memory-core 架构系列文档。

| 文件 | 说明 |
|------|------|
| [01-architecture.md](architecture/01-architecture.md) | 整体架构设计 |
| [02-gateway.md](architecture/02-gateway.md) | 网关层设计 |
| [03-core-assembly.md](architecture/03-core-assembly.md) | 核心装配 |
| [04-interfaces.md](architecture/04-interfaces.md) | 接口定义 |
| [05-implementations.md](architecture/05-implementations.md) | 实现层 |
| [06-adapters.md](architecture/06-adapters.md) | 适配器 |
| [07-policy-governance.md](architecture/07-policy-governance.md) | 策略与治理 |
| [08-data-pipeline.md](architecture/08-data-pipeline.md) | 数据管道 |
| [09-provider-fallback.md](architecture/09-provider-fallback.md) | Provider 回退 |
| [10-consumer-boundary.md](architecture/10-consumer-boundary.md) | 消费端边界 |
| [API-CONTRACT.md](architecture/API-CONTRACT.md) | API 契约 |
| [ci-notify-n8n-workflow.md](architecture/ci-notify-n8n-workflow.md) | CI 通知 n8n 工作流 |
| [error-gateway-pipeline.md](architecture/error-gateway-pipeline.md) | 错误网关流水线 |
| [linear-factory-integration.md](architecture/linear-factory-integration.md) | Linear-Factory 集成 |
| [REF-000-architecture-audit-findings.md](architecture/REF-000-architecture-audit-findings.md) | 架构审计发现 |
| [REF-001-rule-engine-and-llm-isolation.md](architecture/REF-001-rule-engine-and-llm-isolation.md) | 规则引擎与 LLM 隔离 |

### specs/ — 协议规格
memory-core 协议规格文档，定义 .memory/ 协议的行为规范。

| 文件 | 说明 |
|------|------|
| [BOUNDARY.md](specs/BOUNDARY.md) | 边界定义 |
| [DOT_MEMORY_SPEC.md](specs/DOT_MEMORY_SPEC.md) | .memory/ 协议规格 |
| [MEMORY_LOCK_SPEC.md](specs/MEMORY_LOCK_SPEC.md) | 内存锁规格 |
| [MULTI_PROJECT_SCAN_SPEC.md](specs/MULTI_PROJECT_SCAN_SPEC.md) | 多项目扫描规格 |

### guides/ — 使用指南

| 文件 | 说明 |
|------|------|
| [observability-and-error-tracking.md](guides/observability-and-error-tracking.md) | 可观测性和错误追踪概述 |
| [posthog-event-taxonomy.md](guides/posthog-event-taxonomy.md) | PostHog 事件分类 |
| [posthog-privacy.md](guides/posthog-privacy.md) | PostHog 隐私配置 |
| [test-validation-positive.md](guides/test-validation-positive.md) | 测试验证正面示例 |

### qa/ — 质量报告

| 文件 | 说明 |
|------|------|
| [qa-report-template.md](qa/qa-report-template.md) | QA 报告模板 |

### CLASSIFICATION.md — 文档分类决策树
写入文档时的分类指引，Droid 每次"文档记录"时参照此文件。

### Loose Files

| 文件 | 说明 |
|------|------|
| [code-quality-metrics.md](code-quality-metrics.md) | 代码质量指标 |
| [otel-setup.md](otel-setup.md) | OpenTelemetry 配置 |
| [typing-tech-debt.md](typing-tech-debt.md) | 类型债务分析 |

## 与 memory/ 目录的关系

```
docs/                  ← 展示层（AutoWiki 可见，git tracked）
  architecture/        ← 架构设计文档
  specs/               ← 协议规格文档（唯一源）
  guides/              ← 使用指南
  qa/                  ← 质量报告
  CLASSIFICATION.md    ← 分类决策树

memory/                ← 运行时知识层（实例特定）
  kb/decisions/        ← 决策记录（D-001 ~ D-011）
  kb/lessons/          ← 经验教训
  kb/patterns/         ← 错误模式注册表
  kb/projects/         ← 项目 canonical
  docs/system/         ← 系统集成规范（HOOK_INTEGRATION_SPEC）
  docs/plans/          ← 执行计划
  docs/audit/          ← 审计记录
  docs/runbooks/       ← 运维手册
  docs/refactor-logs/  ← 重构日志
  docs/drafts/         ← 产品草案
  docs/rfcs/           ← RFC 提案
  docs/notes/          ← 工程笔记
  docs/bug-reports/    ← Bug 记录
  docs/archive/        ← 已归档文档
```

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-08-01 | 全面同步: 删除幽灵引用(infrastructure/droid-computers/byok-models), 补充遗漏文件(architecture 5个/qa/guides 3个/loose 3个), 更新 memory/ 关系图 |
| 2026-07-17 | 添加 architecture/ 和 specs/ 目录条目 |
| 2026-06-01 | 初始创建 |
