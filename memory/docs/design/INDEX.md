# Design 文档索引

本目录收录 memory-core 模块的详细设计文档，涵盖总体架构、Gateway 门控、核心装配、接口契约、实现层、适配器层、策略治理、数据管道、Provider 回退机制、消费边界分析以及 API 契约。

## 设计文档列表

| 文件 | 说明 |
|------|------|
| [01-architecture.md](01-architecture.md) | 总体架构设计：仓库概览、模块结构、核心组件关系与依赖 |
| [02-gateway.md](02-gateway.md) | Gateway 门控设计：事件路由、能力探测、降级策略与上下文包构建 |
| [03-core-assembly.md](03-core-assembly.md) | 核心装配设计：build_context_package_core 函数签名、v2→v1 格式转换 |
| [04-interfaces.md](04-interfaces.md) | 接口契约层：抽象类定义（HostDelegate、Policy、Sink、Provider 等） |
| [05-implementations.md](05-implementations.md) | 实现层：具体实现类与对应接口的映射关系 |
| [06-adapters.md](06-adapters.md) | Adapter 层：项目级适配层定位、配置管理与适配器注册机制 |
| [07-policy-governance.md](07-policy-governance.md) | Policy Pack 与治理：全局策略包结构、规则定义与作用域管理 |
| [08-data-pipeline.md](08-data-pipeline.md) | 数据管道与 Sink：Context Package 生命周期、写入路径与 v2→v1 转换层 |
| [09-provider-fallback.md](09-provider-fallback.md) | Provider 与回退机制：external-core vs legacy 设计、降级策略 |
| [10-consumer-boundary.md](10-consumer-boundary.md) | 消费边界与改进建议：消费面审计、消费者契约更新与建议 |
| [API-CONTRACT.md](API-CONTRACT.md) | Memory API 契约（context-package-v1）：入口函数、出口结构、字段定义 |
| [error-gateway-pipeline.md](error-gateway-pipeline.md) | Error Gateway 管道设计：PostHog Alert → webhook → n8n → Droid → Issue + PR 自动修复闭环 |

## 法律地位声明
本索引所列内容均为 **incoming-raw** 原始素材，受 `project-map/` 管辖。
design 子目录下的所有内容属于待摄入的原始材料，**未被地图明确吸收**，不具备 canonical 合法性。
只有当 `project-map/` 显式注册后，相关条目才获得合法上下文地位。
