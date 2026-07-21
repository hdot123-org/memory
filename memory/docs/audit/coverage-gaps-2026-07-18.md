# 覆盖率盲区深度分析（2026-07-18）

> 采集基准: commit 7b90dbc | pytest 3061 passed / 3 skipped | 整体覆盖率 80.91%
> 采集工具: pytest-cov + radon cc（函数级交叉）
> 方法: 按 SOP（`memory/docs/audit/audit-sop.md`）Phase 4，用"CC × 覆盖率"矩阵定位真实风险
> 归属: 运维层（memory/docs/audit/），不对外公开

---

## 执行摘要

整体覆盖率 80.91% 健康，但**函数级分析揭示 5 个盲区**，性质差异极大：

| 盲区 | 文件 | 函数覆盖 | 真实风险 | 根因 |
|------|------|---------|---------|------|
| **HIGH** | validate_memory_system.py | 48.9% | detect_pollution CC=18 / 96% 未测 | CI 污染守卫逻辑裸奔 |
| **HIGH** | hook_upgrade.py | 74.9% | cmd_apply_upgrade 备份/失败路径未测 | 真实升级命令，数据损失可能 |
| MEDIUM | version_sync.py | 41.2% | ownership.toml 写入逻辑未测 | 配置文件修改无测试守护 |
| LOW | init_project_memory.py | 76.9% | _enrich CC=37 / 62.8% 未测 | 组合爆炸检测，测试设计缺失 |
| LOW（误报） | pretooluse_guard.py | 23.1% | 薄壳入口，真实逻辑在 _guard_classify（78%） | 覆盖率分母误导 |

**核心判断**：文件级覆盖率排名（pretooluse_guard 23% < version_sync 41% < validate 49%）**不等于**真实风险排名。函数级 + 性质分析后，`validate_memory_system` 和 `hook_upgrade` 才是真正的高风险盲区。

> ⚠️ **勘误通知（2026-07-18 验证）**
> 本报告的 P1/P2/P3 排序**已失效**。经逐条核查测试文件，5 个盲区中 2 个完全错误（#1 和 #4 漏看了已有测试），1 个部分错误（#3 主路径已被集成测试间接覆盖）。仅 #2 和 #5 基本准确。#2 已通过 PR #158 补齐 6 个测试。请阅读底部 [勘误章节](#勘误2026-07-18-验证) 获取修正后结论。

---

## 盲区 1：`validate_memory_system.py::detect_pollution`（HIGH - 安全守卫裸奔）

**位置**: L386-486 | CC=18 | 函数 96% 未测（99 行只测 4 行）| 文件覆盖 48.9%

### 函数职责
CI 污染检测守卫，遍历整个 repo，执行 3 条规则：
- **Rule 1**: 检测 `.memory/` 目录出现在非法位置（repo root / 非 memory/system / 非 archive）
- **Rule 2**: 检测 `*.STATE.md` / `*.PLAN.md` / `*.CANONICAL.md` 出现在运行时位置
- **Rule 3**: 扫描文件内容里的业务特定字符串（axonhub / workbot）

### 未测的是什么
- 3 条规则的检测逻辑全部未测
- `repo-root-missing` 早退路径（可能测了）
- 去重逻辑（`seen` set）未测

### 为什么是 HIGH 风险
这是 **CI 卫生守卫**（很可能被 `scripts/check_boundary.py` 或 `ci_health_check.sh` 调用）。如果某条规则静默失效：
- 污染文件（业务状态、其他项目字符串）会漏进仓库
- CI 不会报错（守卫本身坏了）
- 属于"守卫自身的守卫"——最危险的盲区类型

**注意**：CI 集成测试可能在端到端层面跑到它，但单元层面每条规则的检测逻辑应该独立测。覆盖率 96% 未测指的是 pytest 单元测试。

### 建议
| 项 | 内容 | 预估 |
|----|------|------|
| 必修 | Rule 1: 构造 tmp repo + 各位置 `.memory/` 目录，断言 findings | 45 分钟 |
| 必修 | Rule 2: 构造 tmp repo + 运行时位置的 STATE/PLAN/CANONICAL 文件 | 30 分钟 |
| 必修 | Rule 3: 构造含 axonhub/workbot 字符串的文件 | 30 分钟 |
| 应补 | 白名单路径（_is_whitelisted_path）+ 去重逻辑 | 30 分钟 |

---

## 盲区 2：`hook_upgrade.py::cmd_apply_upgrade`（HIGH - 升级失败路径裸奔）

**位置**: L293-381 | CC=21 | 函数 31/89 行未测 | 文件覆盖 74.9%

### 函数职责
真实的 Factory hook 升级命令（会改 `~/.factory/` 下的文件）：备份 → 审批 → 安装。

### 未测的是什么（按区间）

| 区间 | 行数 | 性质 | 风险 |
|------|------|------|------|
| L329-338 | 10 | 交互 `input()` 审批 + EOF/Ctrl-C 中断 | 中（需 monkeypatch） |
| **L350-359** | **10** | **备份循环 + 备份失败异常** | **高（数据损失）** |
| **L365, L371-374** | **6** | **install 成功/失败分支** | **高（静默失败）** |
| L322 | 1 | 空操作早退 | 低 |
| L376,379,381 | 3 | 错误输出分支 | 低 |

### 为什么是 HIGH 风险
L350-359 是备份逻辑：
```python
for file_path_str in plan.get("files_to_backup", []):
    if file_path.exists():
        try:
            backup = _backup_existing_file(file_path)  # 未测
        except Exception as exc:
            result["errors"].append(...)  # 未测
            return result
```

**如果 `_backup_existing_file` 静默失败、或 `install_factory_hooks` 返回 `success=False` 但 `warnings` 为空**，用户可能在无备份的情况下被覆盖 hook 文件。

当前测试只覆盖 `yes=True`（跳过审批）+ happy path + dry_run，**失败路径全裸**。

### 建议
| 项 | 内容 | 预估 |
|----|------|------|
| 必修 | 备份失败路径（mock `_backup_existing_file` 抛异常，断言 errors + return） | 30 分钟 |
| 必修 | install 失败路径（mock `install_factory_hooks` 返回 `success=False`） | 30 分钟 |
| 应补 | 交互审批 3 路径（monkeypatch input → "y" / "N" / EOFError） | 45 分钟 |

---

## 盲区 3：`version_sync.py`（MEDIUM - 配置写入无守护）

**位置**: L27-168 | 文件覆盖 41.2% | 关键函数全部高未测率

### 关键未测函数

| 函数 | CC | 未测% | 职责 | 风险 |
|------|-----|-------|------|------|
| `patch_ownership_memory_version` L42 | 5 | 87% | **用 regex 改写 ownership.toml** | 中（配置损坏） |
| `read_ownership_memory_version` L27 | 4 | 85% | 读 ownership.toml 的 memory_version | 低 |
| `sync_single_project` L125 | 4 | 95% | 单项目同步编排 | 中 |
| `_try_resign_ownership` L147 | 5 | 89% | 重签名 ownership | 中 |
| `sync_all_known_projects` L79 | 9 | 41% | 全量同步编排 | 中 |
| `main` L168 | 10 | 44% | CLI 入口 | 中 |

### 重点：`patch_ownership_memory_version`（L42-66）
```python
new_content, count = re.subn(
    r'^(memory_version\s*=\s*)"[^"]+"',
    rf'\g<1>"{target_version}"',
    content, count=1, flags=re.MULTILINE,
)
...
ownership_path.write_text(new_content, encoding="utf-8")  # 无备份写入
```

**风险**：regex 如果误匹配（比如注释或其他字段含 "memory_version"），会损坏 ownership.toml；且写入前不备份。

### 建议
| 项 | 内容 | 预估 |
|----|------|------|
| 必修 | patch 成功路径（tmp ownership.toml + 旧版本 → 新版本） | 20 分钟 |
| 必修 | patch 无匹配（count==0）→ return False | 10 分钟 |
| 必修 | patch 文件不存在 → return False | 5 分钟 |
| 应补 | read 的 3 路径（存在/不存在/无字段） | 15 分钟 |
| 应补 | sync_single_project 编排（mock 子调用） | 30 分钟 |

---

## 盲区 4：`init_project_memory.py::_enrich_project_info_from_config`（LOW - 组合盲区）

**位置**: L1089-1175 | CC=37 | 函数 32/87 行未测 | 文件覆盖 76.9%

### 函数职责
纯检测逻辑：读 pyproject.toml / package.json / tsconfig.json / Cargo.toml → 填充 project_info（primary_language / project_type / toolchain）。

### 未测的是什么
20+ 个框架/语言标记的 `any(...)` 检查分支：
- pyproject: fastapi/flask/django/starlette → web/api；pytest → library
- package.json: next/gatsby/remix/react/vue/svelte/angular → frontend；express/koa/fastify/hapi → web/api
- TypeScript（typescript/ts-node）/ Rust（Cargo.toml）/ tsconfig.json

### 为什么是 LOW 风险
**最坏情况是检测出错误的 project_type**（比如把 Flask 项目标成 library），后果仅是初始化时元数据略错，**不影响任何运行时行为**（这些字段只用于 init 阶段的报告/模板选择）。

CC=37 高不是因为逻辑复杂，而是**组合分支多**。这是测试设计问题，不是代码风险。

### 建议
| 项 | 内容 | 预估 |
|----|------|------|
| 应补 | 参数化测试：pyproject 各框架（5 种） | 40 分钟 |
| 应补 | 参数化测试：package.json 各框架（8+ 组合） | 60 分钟 |
| 应补 | TypeScript / Rust / tsconfig 检测 | 30 分钟 |
| 可不补 | ImportError fallback、`except: pass` 防御块 | - |

---

## 盲区 5：`pretooluse_guard.py`（LOW - 覆盖率误报）

**位置**: L1-150 | 文件覆盖 23.1% | 但这是**薄壳入口**

### 关键澄清：文件级 23% 是误导
`pretooluse_guard.py` 只有 150 行，是**薄壳 CLI 入口**：
- `_load_project_root()` - 读环境变量找 project root
- `_write_metrics_jsonl()` - 写 metrics（委托给 `append_metrics_record`）
- `_rule_result_to_hook_json()` - RuleResult → hook JSON dict 转换
- `main()` - 读 stdin JSON → 规范化 → 调 `classify_tool_use`（在 `_guard_classify.py`）→ 输出

**真实守卫逻辑在 `_guard_classify.py::classify_tool_use`（CC=54, 78.3% 覆盖）**，51KB 的 `test_pretooluse_guard.py` 主要测的是那边。

### 未测的是什么（薄壳自身的路径）
- `_load_project_root` 41% 未测：环境变量 fallback 链（FACTORY_PROJECT_DIR → MEMORY_HOOK_ORIGINAL_CWD → cwd）
- `main` 49% 未测：stdin 解析错误路径、"非 memory-managed 项目"早退、metrics 写入失败
- `_rule_result_to_hook_json` 72% 未测：RuleResult 转换的 isinstance 守卫、decision 默认值

### 唯一值得注意的未测路径
`main()` L119-123 的**守卫旁路**：
```python
if not (project_root / "memory" / "system").exists():
    print(json.dumps({"decision": "allow", "reason": "Not a memory-managed project"}))
    return 0
```
如果这条路径有 bug，守卫可能被静默禁用。但逻辑很简单（一个 exists 检查），风险低。

### 建议
| 项 | 内容 | 预估 |
|----|------|------|
| 应补 | "非 memory-managed 项目"早退路径（无 memory/system 目录） | 15 分钟 |
| 应补 | stdin 无效 JSON → allow 路径 | 15 分钟 |
| 可不补 | 环境变量 fallback 链（低风险） | - |

---

## 跨盲区优先级总排序

| 优先级 | 盲区 | 理由 | 总预估 |
|--------|------|------|---------|
| **P1** | validate_memory_system::detect_pollution | 安全守卫裸奔，CI 卫生依赖它 | 2.25 小时 |
| **P1** | hook_upgrade::cmd_apply_upgrade | 真实升级命令，备份/失败路径未测 | 1.75 小时 |
| **P2** | version_sync::patch_ownership_memory_version | 配置写入无守护（可损坏 ownership.toml） | 1.5 小时 |
| **P2** | pretooluse_guard::main 守卫旁路 | 关键早退路径，低风险但值得锁 | 0.5 小时 |
| **P3** | init_project_memory::_enrich | 组合盲区，低风险，量大 | 2.16 小时 |

**总预估**: P1 必修约 4 小时，P2 约 2 小时，P3 约 2 小时。

---

## 方法论说明

本报告严格按 `memory/docs/audit/audit-sop.md` 的 Phase 4（多维度交叉评估）执行：
- 不只看文件级覆盖率（会被薄壳文件误导，如 pretooluse_guard 23%）
- 用 AST 解析 cc.json 得函数边界 + coverage missing_lines 算**函数级覆盖率**
- 按"CC × 覆盖率 × 副作用 × 业务关键性"综合判风险
- 每个盲区标注性质（守卫/升级/检测/配置写入）和真实后果

### 与文件级覆盖率的差异（重要）
文件级排名：pretooluse_guard 23% < version_sync 41% < validate 49% < init 77% < hook_upgrade 75%
真实风险排名：validate > hook_upgrade > version_sync > pretooluse_guard > init

**差异根因**：文件级覆盖率把"薄壳入口"（pretooluse_guard）和"真实逻辑"（_guard_classify）分开算，导致薄壳显得极差。函数级 + 性质分析才能还原真实风险。

---

## 原始数据

- 覆盖率: `/tmp/cov-deepdive.json`（pytest-cov 输出，604KB）
- 复杂度: `/tmp/cc-deepdive.json`（radon cc 输出）
- 注：原始数据未归档到 artifacts/（被 .gitignore），如需复现按 SOP Phase 2 命令模板重跑

---

## 勘误（2026-07-18 验证）

> 验证方法：grep 全 tests/ 目录找所有引用目标函数的测试文件（不仅看文件名匹配），直接读测试断言确认覆盖深度。
> 验证者：explorer subagent ff94e665 初查 + orchestrator 逐文件核查测试断言

### 盲区 1：detect_pollution — ❌ 完全错误（false）

| 项 | 内容 |
|----|------|
| 真实性 | **false** — 报告声称 "96% 未测"，实际已被 11 个测试全面覆盖 |
| 实测发现 | `tests/test_p2_pollution_whitelist.py` 直接导入并调用 `detect_pollution(tmp_path)`：Rule 1（`.memory/` 目录位置）4 个测试、Rule 2（STATE/PLAN 文件位置）5 个测试、Rule 3（axonhub/workbot 字符串）2 个测试，共 11 个测试。报告遗漏此文件 |
| 补测试价值 | **无** — 已充分覆盖 |
| 修正后建议 | 从 P1 移除。原报告漏看此文件因只搜了 `test_validate_memory_system.py`（文件名匹配），未 grep 整个 tests/ 目录 |

### 盲区 2：cmd_apply_upgrade — ✅ 准确（true），已修复

| 项 | 内容 |
|----|------|
| 真实性 | **true** — 报告正确识别了备份/失败路径未测 |
| 实测发现 | 确认原测试只覆盖 dry_run 和空 plan 早退路径 |
| 补测试价值 | **高** — 已通过 PR #158 补齐 6 个测试（备份异常 mock、install 成功/失败 mock、交互 y/N/EOF 三路径）|
| 修正后建议 | 已修复，保留 P1 标签作为历史记录 |

### 盲区 3：patch_ownership_memory_version — ⚠️ 部分准确（partially-true）

| 项 | 内容 |
|----|------|
| 真实性 | **partially-true** — 主写入路径已被间接覆盖，仅边缘 case 缺 |
| 实测发现 | `tests/test_version_sync_resign.py` 有 6 个集成测试（test_calls_sign_project_incremental_after_patch、test_no_sign_when_already_up_to_date、test_no_sign_when_no_ownership、test_sign_failure_does_not_block_patch、test_version_actually_updated_in_file、test_manifest_sha256_matches_file），通过 patch+sign 流程间接覆盖主写入路径。但 regex 无匹配（count==0 -> return False）和文件不存在路径无直接单元测试 |
| 补测试价值 | **低** — 仅边缘 case |
| 修正后建议 | 降级。主路径已有集成测试守护，可选择性补 regex no-match 单元测试 |

### 盲区 4：pretooluse_guard main 早退 — ❌ 完全错误（false）

| 项 | 内容 |
|----|------|
| 真实性 | **false** — 报告声称 "应补非 memory-managed 项目早退路径"，实际已有直接测试 |
| 实测发现 | `tests/test_pretooluse_guard.py:633 test_guard_allows_non_memory_project` 直接测试了 "无 memory/system 目录 -> allow + 早退" 路径 |
| 补测试价值 | **无** — 已有直接测试 |
| 修正后建议 | 从 P2 移除。原报告漏看此测试 |

### 盲区 5：_enrich — ⚠️ 基本准确（true），低风险

| 项 | 内容 |
|----|------|
| 真实性 | **true** — grep 全 tests/ 目录无匹配 `enrich_project_info_from_config`，无直接单元测试 |
| 实测发现 | 可能有集成测试通过 `init_project_memory` 间接覆盖主路径，但无直接断言验证 `_enrich` 的各框架检测分支 |
| 补测试价值 | **低** — 最坏情况是 project_type 元数据略错，不影响运行时行为 |
| 修正后建议 | 保留 P3。可选择性补参数化测试 |

### 修正后优先级总排序

| 修正后优先级 | 盲区 | 理由 |
|-------------|------|------|
| ~~P1~~ -> 已修复 | cmd_apply_upgrade | PR #158 已补 6 个测试 |
| ~~P1~~ -> 移除 | detect_pollution | 已有 11 个测试，原报告漏看 |
| ~~P2~~ -> 降级 P3 | version_sync 边缘 case | 主路径已有集成覆盖 |
| ~~P2~~ -> 移除 | pretooluse_guard 早退 | 已有直接测试，原报告漏看 |
| P3（保留）| _enrich | 低风险，可选补 |

### 教训

本次盲区报告准确率约 40%（5 个中 2 个完全错误、1 个部分错误）。根因：

1. **只看文件名匹配的测试文件** — 搜 `test_validate_memory_system.py` 没找到 detect_pollution 测试，但 `test_p2_pollution_whitelist.py` 有 11 个。应 grep 整个 tests/ 找所有引用目标函数的测试文件
2. **未识别集成测试的间接覆盖** — `test_version_sync_resign.py` 通过 patch+sign 流程间接覆盖了 `patch_ownership_memory_version`，但报告只看单元测试

这些问题已在 `memory/docs/audit/audit-sop.md` Phase 5 中补充为具体可执行步骤（grep 发现 / pytest-cov term-missing / 读断言 / 区分单元集成）+ 反面案例。
