# Runbooks 文档索引

本目录收录 memory-core 的运维手册，分为**通用维护手册**（所有消费者适用）和**环境特定手册**（特定部署环境的运维经验）。

## 通用维护手册（所有消费者适用）

这些手册不依赖特定 CI/CD 平台或部署环境，任何使用 memory-core 的项目都适用。

| 文件 | 说明 |
|------|------|
| [VERSION_SYNC_RUNBOOK.md](VERSION_SYNC_RUNBOOK.md) | 三文件版本同步：ownership.toml / memory.lock / adapter.toml 版本号一致性检查与修复 |
| [MIGRATION_RUNBOOK.md](MIGRATION_RUNBOOK.md) | 消费项目迁移：版本间结构迁移操作、迁移工具使用、跨版本迁移处理 |
| [CONFIG_MANAGEMENT_RUNBOOK.md](CONFIG_MANAGEMENT_RUNBOOK.md) | 配置管理：adapter.toml / ownership.toml / memory.lock schema 说明与健康检查 |

## 环境特定手册（特定部署环境，仅供参考）

这些手册基于特定部署环境（GitLab CI + GitHub 镜像），不适用于所有消费者。如果你的环境使用其他方案，请参考你自己的 CI/CD 配置。

| 文件 | 说明 |
|------|------|
| [CI_CD_RUNBOOK.md](CI_CD_RUNBOOK.md) | GitLab CI 配置与发布自动化（环境特定） |
| [GIT_PUSH_SPEC.md](GIT_PUSH_SPEC.md) | Git Push 规范：GitLab → GitHub 单向同步（环境特定） |
| [RUNBOOKS.md](RUNBOOKS.md) | 事件响应、监控、部署可观测性（环境特定） |

## 法律地位声明
本索引所列内容均为 **incoming-raw** 原始素材，受 `project-map/` 管辖。
runbooks 子目录下的所有内容属于待摄入的原始材料，**未被地图明确吸收**，不具备 canonical 合法性。
只有当 `project-map/` 显式注册后，相关条目才获得合法上下文地位。
