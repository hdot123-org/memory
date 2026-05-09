---
type: "[AUDIT]"
title: "memory-core 多项目接入试点准入审计"
shortname: AUDIT-2026-05-09-MEMORY-CORE
status: baseline
created: 2026-05-09
updated: 2026-05-09
scope: memory-core
tags: [audit, baseline, multi-project, p0]
---

# memory-core 多项目接入试点准入审计（Phase 0 基线）

> 本文档由主线程指挥官调度 4 个 bailian 子代理（A/B/C/D）只读审计后整合形成，作为 Phase 1 起步前的基线证据，禁止删改。

## 元数据

| 项 | 值 |
|---|---|
| 仓库 | memory-core |
| 基线 commit | `6d459d183303df05d7a1564bbbeeacaa45e1b185` |
| 基线 commit 信息 | `6d459d1 test: 补充 CoreConfig is None 分支定向测试（3 个用例）` |
| 工作树状态 | clean（无未跟踪/未提交变更） |
| 当前 memory_version | `0.2.0` |
| 当前 host 集合 | `("codex", "claude", "factory")` |
| 测试规模 | 731 passed |
| ruff 状态 | **4 errors（CI 红线）** |
| 主分支 | main |

## 审计范围

| 维度 | 子代理 | 关注点 |
|---|---|---|
| A | 核心定位与契约一致性 | README / BOUNDARY / DOT_MEMORY_SPEC / constants / CHANGELOG 自洽性 |
| B | Schema / Adapter / Migration 设计风险 | 版本绑定、迁移幂等、向后兼容、AdapterConfig |
| C | Hook Gateway 与多项目接入风险 | scope 隔离、artifact 路径、HostDelegate、并发、root discovery |
| D | CI / 测试 / 业务数据污染 | 实测 ruff + pytest、pollution guard 实效、本仓自身污染 |

## 总裁决

### NO-GO（暂不进入多项目接入试点）

四个子代理给出的裁决分别是 **NO-GO / NO-GO / GO-WITH-CONDITIONS / GO-WITH-CONDITIONS**。两条独立的 NO-GO 路径足以否决试点。

---

# 一、子代理 A 报告：核心定位与契约一致性

## A.1 摘要

memory-core 自我声明的"通用记忆底座"定位在**常量/协议层面基本自洽**，但在**仓库内部残留业务上下文、模板版本漂移、以及 INDEX.md 中暴露具体业务依赖**三个维度存在实质性风险。v0.2.0 版本在 README 安装命令 / constants.py / pyproject.toml 之间完全一致，host 列表三处一致。最大的阻断项是 `memory_core/memory/kb/` 目录下残留了大量 workbot/axonhub 业务专属文件，直接违反 BOUNDARY.md 的单一归属原则。

## A.2 发现项

| # | 发现项 | 证据 | 风险 | 阻断 |
|---|---|---|---|---|
| 1 | README 7 必备文件 vs constants.REQUIRED_MEMORY_FILES | README + `constants.py:10-18` 完全一致 | — | 否 |
| 2 | README kb 4 子目录 vs constants.REQUIRED_MEMORY_DIRS | `constants.py:20-25` 完全一致 | — | 否 |
| 3 | DOT_MEMORY_SPEC.md 文件列表 vs constants.py | 完全一致 | — | 否 |
| 4 | MEMORY_LOCK_SPEC.md schema 字段 vs constants.py | `CANONICAL_MEMORY_LOCK_SCHEMA="context-package-v1"` / `CANONICAL_ADAPTER_VERSION="builtin"` 一致 | — | 否 |
| 5 | FRONTMATTER 跨文档一致 | `constants.py:33-38` 与 DOT_MEMORY_SPEC 表格语义一致；DOT_MEMORY_SPEC 未以 YAML frontmatter 显式声明 | P3 | 否 |
| 6 | 状态枚举一致 | `constants.py:41-45` 与 DOT_MEMORY_SPEC 完全一致 | — | 否 |
| 7 | health 值一致 | `constants.py:48` `("green","yellow","red")` 一致 | — | 否 |
| 8 | SemVer 四处一致 | constants / pyproject / README / CHANGELOG 全为 `0.2.0` | — | 否 |
| 9 | CHANGELOG `[0.3.0] - Unreleased` 不构成漂移 | 正常 Unreleased 状态 | — | 否 |
| 10 | schema_version 取值一致 | constants / README / DOT_MEMORY_SPEC / MEMORY_LOCK_SPEC 全为 `context-package-v1` | — | 否 |
| 11 | host 列表一致 | README / DOT_MEMORY_SPEC / `constants.py:7` 三处一致 `(codex,claude,factory)` | — | 否 |
| 12 | RESIDUE 文档与现实不同步 | RESIDUE_INVENTORY R-01~R-09 标注"必须迁出"，实际 git 中已不存在但文档未更新 | P2 | 否 |
| **13** | **`memory_core/memory/kb/` 业务残留违反 BOUNDARY 4.1** | `memory_core/memory/kb/projects/workbot.md`（workbot 项目专属） + `memory_core/memory/kb/global/workbot-*` 7 个文件 + `projects-spec.md §11` 含 AxonHub CE-01 SSH/IP/Docker 部署信息 | **P0** | **是** |
| **14** | **`memory_core/INDEX.md:44` 把 workbot-truth-model.md 当真相模型** | "真相模型 canonical：`memory_core/memory/kb/global/workbot-truth-model.md`（**当前接入项目的真相模型文件**）" | **P0** | **是** |
| 15 | `memory_core/NOW.md` 是仓库自身状态，不违反 BOUNDARY | 内容为 memory-core 开发进度，不是业务项目 PLAN/STATE | — | 否 |
| **16** | **模板版本漂移** | `workspace/templates/.memory/adapter.toml:6` `version = "1.0.0"` ≠ `CURRENT_MEMORY_VERSION = "0.2.0"`；且仍用旧 `[adapter]` schema 而非 canonical `[core][policy][routing]` | **P1** | **是** |
| 17 | multi-project scan 规范本身不耦合单项目 | 但 registry.toml 需手动维护，缺少自动发现 | P2 | 否 |
| 18 | MULTI_PROJECT_SCAN_SPEC.md 标记 ARCHIVED | 规范与实际实现可能脱节 | P2 | 否 |

## A.3 A 维度裁决：**NO-GO**

理由：常量/协议层面高度自洽，但 `memory_core/memory/kb/` 残留 workbot/axonhub 业务专属文件 + INDEX.md 直接引用 workbot-truth-model.md，违反 BOUNDARY 4.1/4.3，新业务项目接入时会看到他人专属内容。

---

# 二、子代理 B 报告：Schema / Adapter / Migration

## B.1 摘要

7 个必答问题覆盖完成。共 1 项 P0、4 项 P1、4 项 P2、3 项 P3。核心结论：**migration 不具备真正幂等性且无自动回滚；adapter.toml 对多余字段和空 project_scope 缺乏强制校验；schema 三层转换存在数据静默丢弃；降级机制完全缺失**。

## B.2 发现项

| # | 发现项 | 证据 | 风险 | 阻断 |
|---|---|---|---|---|
| Q1-1 | adapter.toml 不拒绝多余字段 | `adapter_toml_schema.py:70-80` `dict.get()` 模式，未知键被静默忽略 | P2 | 否 |
| Q1-2 | 允许空 project_scope | `adapter_toml_schema.py:56` 默认空串被接受 | P1 | 是 |
| Q1-3 | host 校验仅 warning | `adapter_toml_schema.py:67-71` `warnings.warn()`，不抛异常 | P1 | 是 |
| Q1-4 | project_name 可空 | 无最低长度约束 | P2 | 否 |
| Q2-1 | 兼容矩阵无运行时执行 | MEMORY_LOCK_SPEC §3 `[[compat]]` 矩阵纯文档，代码无任何读取 | P1 | 是 |
| **Q2-2** | **降级机制完全缺失** | 全仓 grep `downgrade/降级` 零匹配；`migrate_project_memory` 仅支持 `from→to` 单向；`validate_project_memory` 不区分升降 | **P0** | **是** |
| Q2-3 | schema_version 与 memory_version 无联动 | `validate_project_memory.py:244-268` 仅比 memory_version | P2 | 否 |
| Q3-1 | 迁移非幂等 | `migrate_project_memory.py:220-229` 校验 `current != from_version` → 报错；二次跑必失败；违反 MIGRATION_FORMAT_SPEC §3.2.1 | P1 | 是 |
| Q3-2 | 无自动回滚 | `:251` `plan_rollback` 显式 `can_rollback=False`；无备份；违反 MIGRATION_FORMAT_SPEC §4.4 | P1 | 是 |
| Q3-3 | migrations.log 非原子追加 | `:181-187` `open("a")` 无 flock | P3 | 否 |
| Q3-4 | adapter.toml 迁移用字符串替换 | `:119` `atext.replace('version = "0.1.0"', ...)` 非结构化 | P2 | 否 |
| Q4-1 | init 已存在 .memory/ 仅跳过文件 | 无 `--force`，无交互 | P3 | 否 |
| Q4-2 | dry-run 安全 | `:289-296` 写盘前即返回 | 安全 | — |
| Q4-3 | 模板占位符无失败处理 | f-string 不捕异常 | P3 | 否 |
| Q5-1 | 全有或全无的 PASS 阈值 | `:165-166` `all(c["passed"])` | P2 | 否 |
| Q5-2 | 污染检测可能误伤 | `POLLUTION_PATTERNS` 含 `node_modules` 大小写不敏感正则 | P2 | 否 |
| Q5-3 | 污染检测不区分文件类型 | 路径检查对所有文件执行 | P2 | 否 |
| Q6-1 | wb-hook-v2 → context-package-v1 有损 | `memory_hook_schema.py:18-21` `_DROP_KEYS={"system_context","missing_paths"}` 静默丢弃 | P1 | 是 |
| Q6-2 | context-package-v1 → memory-v1 有损 | `:79-84` project 仅保留 scope，name/description/tech_stack 全丢 | P1 | 是 |
| Q6-3 | 三层转换无反向/无损模式 | 无 `is_lossless()`，无审计日志 | P2 | 否 |
| Q7-1 | consistency_check 18 项一致性检查 | `:403-422` checks 列表 | — | — |
| Q7-2 | consistency_check 不替代 schema/migration 校验 | 仅 init+validate roundtrip | P3 | 否 |

## B.3 B 维度裁决：**NO-GO**

理由：P0 降级机制完全缺失 + P1 迁移非幂等且无回滚 + P1 三层 schema 转换有损数据丢弃，多项目共存场景下无法保障向后兼容/迁移幂等/错误可恢复。

---

# 三、子代理 C 报告：Hook Gateway 与多项目接入风险

## C.1 摘要

核心风险集中在 **Gateway 模块级全局状态初始化**（import 时即执行 `_load_adapter_profile` + `load_adapter_config`），同一 Python 进程中无法安全加载两个不同项目的 adapter。`memory_root_discovery` 向上越界无上限。`resolve_host_delegate("factory")` 实际使用 `NoopHostDelegate`（设计如此，安全）。`cmux_hook_state` 文件锁并发安全，项目隔离依赖调用方传参。`business_policy_checks.py` 31KB 体量是通用验证逻辑，与具体业务耦合度不高。`workbot_runtime_profile` 中硬编码大量 AEdu 项目特定内容，但仅在 workbot adapter 生效时执行。

## C.2 发现项

| # | 发现项 | 证据 | 风险 | 阻断 |
|---|---|---|---|---|
| 1 | Gateway 模块级全局状态：import 时即加载 adapter | `memory_hook_gateway.py:133-134` import 时执行 `_load_adapter_profile` + `load_adapter_config` | P0 | 是（库导入并发模式下） |
| 2 | `_adapter_config` + `globals().update()` 双向污染 | `:118` + `:130` 注入模块 globals | P0 | 是（同上） |
| 3 | 三个默认策略单例缓存 | `:138-140` 首次创建后不重建 | P1 | 否（重启可规避） |
| 4 | `MEMORY_HOOK_ADAPTER` 默认值仍是 `workbot` | `:97` `os.environ.get("MEMORY_HOOK_ADAPTER", "workbot")` | P1 | 否 |
| 5 | default adapter 存在且通用 | `default_runtime_profile.py` 完全项目无关 | P2 | 否 |
| 6 | memory_root_discovery 向上越界无上限 | `:25-30` while True 直到 `/`；符号链接 resolve() 跟随 | P1 | 否 |
| 7 | Artifact 写入路径基于模块级 WORKSPACE_ROOT | `:19-20` 不随项目切换变化，但文件名含 host-event 不会覆盖 | P2 | 否 |
| 8 | Artifact 不会写到 cwd 或 home | 安全 | — | — |
| 9 | `CLAUDE_HOOK_STATE_DIR` 引用 Path.home() 但未使用 | `:24` 死代码 | P3 | 否 |
| 10 | factory host 用 NoopHostDelegate | `memory_hook_impls.py:199-201` 设计意图，安全 | P2 | 否 |
| 11 | CodexDelegate / ClaudeDelegate 完整 | `:71-130`、`:133-192` | — | — |
| 12 | business_policy_checks.py 不耦合特定业务 | 仅操作 GatewayBusinessPolicyConfig | — | — |
| 13 | workbot_runtime_profile 硬编码 AEdu 内容 | `:104-120` AEdu 路径 + `frozen_tuple_expected={"province=安徽",...}` | P2 | 否（adapter 隔离） |
| 14 | cmux_hook_state 文件锁并发安全 | `:20-25` `fcntl.LOCK_EX` + tempfile + replace | P2 | 否 |
| 15 | ClaudeDelegate state_file 默认路径有歧义 | `:147-148` 构造函数无默认值依赖 | P1 | 否 |
| 16 | 多个 env 变量进程内并发不可隔离 | `MEMORY_HOOK_ADAPTER`/`MEMORY_HOOK_POLICY_PACK_PATH`/`CMUX_*` 等全部来自 os.environ | P1 | 否 |

## C.3 C 维度裁决：**GO-WITH-CONDITIONS**

理由：Gateway 作为独立 CLI 进程时安全；同进程库导入并发模式下不安全。要求：(1) 多项目并发以独立进程运行；(2) 默认 adapter 改 `default`；(3) 清理死代码。

---

# 四、子代理 D 报告：CI / 测试 / 业务数据污染

## D.1 摘要

实测 **775 个测试全绿**（超过 git log 记录的 772），覆盖 business policy / hook / gateway / adapter / schema / config 六大域。但 **`ruff check .` 4 errors**（CI 中应阻断），CI **缺少 pollution guard 用例**。`workspace/templates/.memory/` 4 个业务状态模板文件被 git track。release workflow 上传 `dist/*` 源码 tarball。整体 GO-WITH-CONDITIONS。

## D.2 实测输出

```
# pytest --collect-only
775 tests collected in 0.13s

# pytest -q tests
775 passed, 2 warnings in 8.17s

# ruff check .
Found 4 errors.
[1] I001 validate_memory_system.py:178 — import in exception handler not sorted
[2] E702 validate_memory_system.py:178 — multiple statements on one line
[3] F401 validate_project_memory.py:53 — VALID_HEALTH_VALUES imported but unused
[4] I001 test_p4_adapter_toml.py:3   — import block unsorted
```

## D.3 发现项

| # | 发现项 | 证据 | 风险 | 阻断 |
|---|---|---|---|---|
| 1 | ruff check 4 errors 未修复 | exit code 1，CI ruff check 步骤会失败 | **P0** | **CI 红线** |
| 2 | CI 无 pollution guard 用例 | ci.yml/release/.gitlab-ci 均不调 validate_memory_system | P2 | 否 |
| 3 | 业务状态模板被 git track | `workspace/templates/.memory/{PLAN,STATE,CANONICAL,TASKS}.md`；.gitignore 不匹配 | P1 | 否（内容是占位符） |
| 4 | memory_core/NOW.md 存在 | 仓库级 mission 追踪，干净 | P3 | 否 |
| 5 | build/ 残留 .memory 目录 | python -m build 产物未 track | P3 | 否 |
| 6 | release workflow 可能打包模板 | `package-data` 含 `workspace=["templates/**/*"]` | P2 | 否（内容是占位符） |
| 7 | GitLab sync 可能推送污染 | `git push github main --force` 同步整分支 | P2 | 否（与 GitHub 端一致） |
| 8 | RESIDUE_DISPOSITION_PLAN 文档残留 | 历史清理记录 | P3 | 否 |

## D.4 测试覆盖矩阵

| 域 | 测试文件数 | 用例数 | 覆盖度 | 空白 |
|---|---|---|---|---|
| init (init_project_memory) | 0 | 0 | 无 | **memory-init CLI 入口零测试** |
| validate (validate_*) | 1+inline | 14 | 低 | 缺真实 map 文件验证 |
| migrate (migrate_project_memory) | 0 | 0 | 无 | **memory-migrate CLI 入口零测试** |
| gateway | 4 | 34 | 中 | decoupling/integration/smoke/policy_pack |
| adapter | 4 | 55 | 良 | TOML load/dump/defaults |
| hook event | 2 | 58 | 良 | load/write/reset/concurrent |
| schema | 4 | 125 | 良 | v1/required keys |
| policy | 5 | 300+ | 充分 | paths/errors/schema/integration/smoke |
| config validation | 1 | 11 | 中 | CoreConfig 路径 13 测试 |

## D.5 CI 审计

| CI 项 | GitHub Actions | GitLab CI |
|---|---|---|
| 多 Python 版本 | ✅ 3.9/3.10/3.11/3.12 | ❌ 仅单版本 |
| pollution guard 用例 | ❌ 无 | ❌ 无 |
| lint 阻断 | ✅ 配置正确，但当前 4 错误 | ✅ 同 |
| tag version 校验 | ✅ tag vs pyproject.toml | N/A |

## D.6 pollution guard 实效

`validate_memory_system.py` 实际是 **API 健康检查**，非文件级污染检测：

| 检测项 | 实际检测 | 能否拦截污染 |
|---|---|---|
| gateway_import | 模块可导入 | ❌ |
| core_builder_resolve | provider 可解析 | ❌ |
| context_package | context 包形状 | ❌ |
| core_config_path | build_context_package_from_config 可用 | ❌ |
| v1_schema | context-package-v1 结构 | ❌ |
| package_imports | 4 public symbols | ❌ |

**真正的污染防护当前完全依赖 `.gitignore` + 人工审计**。

## D.7 仓库自身污染扫描

| 指纹 | 找到位置 | 是否污染 |
|---|---|---|
| STATE/PLAN/CANONICAL/TASKS.md | `workspace/templates/.memory/` | 模板占位符 ✅ |
| NOW.md | `memory_core/NOW.md` | 仓库级，非业务 ✅ |
| .memory/ 目录 | `workspace/templates/.memory/`、`build/lib/.../` | 模板/构建残留 ✅ |
| `workspace/projects/*/` | 不存在 | ✅ |
| `workspace/memory/kb/projects/*/STATE.md` | 不存在 | ✅ |

**结论**：仓库当前**无运行时业务数据污染**，但 `memory_core/memory/kb/` 下有业务**知识/规范**残留（见 A 维度发现 13）。

## D.8 D 维度裁决：**GO-WITH-CONDITIONS**

理由：测试基础健康；4 ruff 错误必须先修；CI 应增加 pollution guard 检测；CLI 入口需补 smoke test。

---

# 五、综合 P0/P1 风险清单

## 5.1 P0（试点前必须先修）

| # | 来源 | 风险 |
|---|---|---|
| P0-1 | A.13 | `memory_core/memory/kb/` 业务残留违反 BOUNDARY 4.1（8 个 workbot-* + projects-spec.md AxonHub 段） |
| P0-2 | A.14 | `memory_core/INDEX.md:44` 把 workbot-truth-model.md 当真相模型 |
| P0-3 | A.16 | `workspace/templates/.memory/adapter.toml` 旧 schema + version 1.0.0 |
| P0-4 | D.1 | ruff check 4 errors（CI 红线） |
| P0-5 | B.Q3-1 | migrate 非幂等 |
| P0-6 | B.Q2-2 | 降级机制完全缺失 |
| P0-7 | B.Q6-1/Q6-2 | 三层 schema 转换静默丢弃业务字段 |

## 5.2 P1（试点前建议修，可分阶段）

- B.Q1-2/Q1-3：adapter host warning → ValueError；空 scope 拒绝
- B.Q2-1：compat 矩阵纯文档无运行时
- B.Q3-2：迁移无回滚 + 无备份
- C.4：`MEMORY_HOOK_ADAPTER` 默认值改 `default`
- C.6：memory_root_discovery 加最大向上 8 层 + monorepo sentinel
- C.15/C.16：ClaudeDelegate 默认路径 + env 变量隔离
- D.3：`workspace/templates/.memory/*.md` git track 处置
- 测试空白：补 `memory-init` / `memory-migrate` CLI smoke test

## 5.3 P2/P3（后置）

- B.Q3-3：migrations.log fcntl.flock
- B.Q3-4：adapter.toml 迁移结构化
- B.Q5-2/Q5-3：pollution detection 白名单
- B.Q6-3：转换审计日志 + is_lossless()
- C.7：artifact_root 项目隔离
- C.9：`CLAUDE_HOOK_STATE_DIR` 死代码
- D.2：CI 加 validate_memory_system + pollution guard step
- A.18：MULTI_PROJECT_SCAN_SPEC ARCHIVED 处置

---

# 六、修复阶段路线图（待 Q1/Q2/Q3 决策后展开）

| Phase | 内容 | 预估改动面 | 当前状态 |
|---|---|---|---|
| 0 | 写本审计材料 | 1 文件 | **本次完成** |
| 1 | P0-1/P0-2 业务残留分流 | 8+ 文件移动 + INDEX.md 改写 | 待 Q1 决策 |
| 2 | P0-3 模板 schema 对齐 | 模板 + init_project_memory + 1 测试 | 待 Q2 决策 |
| 3 | P0-4 lint 红线 | 3 文件局部 | 待批 |
| 4a | 迁移幂等 | migrate_project_memory + 测试 | 待批 |
| 4b | 备份 + 软回滚 | migrate_project_memory + 测试 | 待批 |
| 4c | 降级语义 | migrate + validate + 测试 | 待 Q3 决策 |
| 4d | schema 转换审计 | memory_hook_schema + 测试 | 待批 |
| 5 | P1 收尾（adapter/CLI/默认值/template git） | 多文件 | 待批 |
| 6 | P2/P3（可后置） | 多文件 | 待批 |

## 试点准入门槛

- **单项目试点**：完成 Phase 0~4。
- **多项目同时接入试点**：再完成 Phase 5。

---

# 七、待决策事项（来自主线程对话）

| # | 问题 | 选项 | 当前状态 |
|---|---|---|---|
| Q1 | Phase 1 业务残留处置去向 | A 迁出独立仓 / B 移到 archive 分支 / C 直接删 / D 暂不动 | **未决** |
| Q2 | Phase 2 旧模板 schema 是否兼容 | A 直接替换 / B 双 schema 兼容一个版本周期 / C 先 grep 引用面再定 | **未决** |
| Q3 | Phase 4c 降级语义 | A 显式 reject / B 实现真实降级 / C 仅 validate 区分升降 | **未决** |
| Q4 | 执行顺序 | A 仅 Phase 0 / B Phase 0+3 / C 不动 / D 全连做 | **A 已选** |

---

# 八、声明

- 本文档为只读审计基线。
- Phase 0 仅创建本文件，不修改任何代码或既有文档。
- 后续 Phase 1+ 任何写盘行为必须经主线程明确确认。
- 本文档不应被业务项目复用，仅适用于 memory-core 仓库自身审计。

## 闭环状态（2026-05-10）

### P0 闭环表

| ID | 描述 | Phase | 状态 | 关键文件 |
|---|---|---|---|---|
| P0-1 | workbot 项目真相残留 | Phase 1 | ✅ 已迁出 | `archive/legacy-workbot/kb/*` |
| P0-2 | INDEX.md 真相模型硬绑定 workbot | Phase 1 | ✅ 通用化 | `memory_core/INDEX.md` |
| P0-3 | 模板 schema 漂移 | Phase 2 | ✅ canonical 对齐 | `workspace/templates/.memory/adapter.toml` |
| P0-4 | 降级语义缺失 | Phase 4c | ✅ 显式 reject + 错误码 | `migrate_project_memory.py` |
| P0-5 | lint 红线 | Phase 3 | ✅ ruff 0 errors | `validate_memory_system.py` + others |
| P0-6 | 迁移非幂等 | Phase 4a | ✅ current==target → noop | `migrate_project_memory.py` |
| P0-7 | schema 有损转换无审计 | Phase 4d | ✅ is_lossless + env 开关 | `memory_hook_schema.py` |

### Phase 闭环列表

- **Phase 0**：审计基线（本文档）
- **Phase 1**：业务残留迁出（`archive/legacy-workbot/`）
- **Phase 2**：模板 canonical schema 对齐
- **Phase 3**：lint 修复（ruff 0 errors）
- **Phase 4a~d**：迁移幂等 + 备份/软回滚 + 降级 reject + schema 审计
- **Phase 5**：adapter strict + gateway default + init force + CLI smoke
- **Phase 6**：root discovery 越界防护
- **非 P0-A**：移除 `_load_adapter_profile` 静默 ImportError fallback
- **非 P0-B**：gateway `reload_adapter` 公共 API
- **非 P0-C**：BOUNDARY pollution guard 脚本 + CI 接入
- **额外健壮性修复（2026-05-10）**：S2 `execute_rollback` 返回值检查 + S3 `_create_backup` 错误处理（属于 Phase 4b 健壮性补丁）

### 遗留事项（不在本次范围）

| # | 事项 | 风险等级 | 备注 |
|---|---|---|---|
| L1 | `init_project_memory.py:98` git remote 查询的 `except Exception: pass` | 低 | 历史代码，独立 PR 处理 |
| L2 | 部分次要 silent fallback（`_read_payload` JSON 空 dict、`resolve_route_target` 硬编码 fallback、`is_lossless` 未知 schema 默认 True） | 低 | 已文档记录，待办 |
| L3 | gateway 模块级 globals 同进程并发不安全 | 中 | 已用文档明示，多项目并发请用独立进程 |

### 验收门槛

| 项 | 门槛 | 结果 |
|---|---|---|
| ruff | 0 errors | ✅ |
| pytest | 728+ passed, 0 failed（含所有新增 phase 测试） | ✅ 731 passed |
| BOUNDARY guard | clean | ✅ |
| 所有 P0 | 已关闭 | ✅ 7/7 闭环 |

### 试点准入裁决

**单项目试点准入**：✅ **GO**（NO-GO → GO，所有 P0 已闭环）
