# 代码质量审计 SOP（标准作业流程）

> 版本: 1.0
> 制定日期: 2026-07-18
> 适用范围: memory-core 仓库的周期性代码质量审计。其他 Python 仓库可参考但需调整工具清单。
> 归属: 运维层（memory/docs/audit/），不对外公开。

---

## 0. 为什么需要这个 SOP

### 0.1 历史教训

本仓库曾出现过一份审计报告（健康度 35/100）存在 7 大错误，重跑过程又反复出现解读错误。根因不是工具问题，而是**流程纪律问题**：

| 错误类型 | 具体案例 | 根因 |
|---------|---------|------|
| 不读已有文档 | 审计说"缺覆盖率维度"，实际 `docs/code-quality-metrics.md` 早已定义 | 跳过 Phase 0 |
| 不读 CI 配置 | 审计说"缺安全扫描"，实际 CI 已跑 pip-audit | 跳过 Phase 0 |
| 命令参数凭记忆 | radon `-e`（exclude）被当 extend 用，排除了 memory_core | 跳过 Phase 1 |
| 数据 schema 不确认 | `0/36` 被读成 "0% 覆盖"，实际是 "0 行未测 / 36 总行 = 100% 覆盖" | 跳过 Phase 3 |
| 不做合理性检查 | CC max=20（因 -e 排除了目标目录）没立即质疑 | 跳过 Phase 2 |
| 单维度下结论 | 按 CC 排 P0，没用覆盖率交叉 | 跳过 Phase 4 |

**共性根因**：把审计当"验证已有结论"，而不是"从零采集事实"。先有结论再找数据支持，数据不符时就出错。

### 0.2 核心转变

```
错误模式：推断 → 找证据支持 → 出错
正确模式：采集事实 → 多源交叉 → 下结论
```

---

## 1. 五条核心原则

1. **实证优先**：先跑再断言，不先推断再找证据。任何"应该"、"估计"、"大概"必须变成实测。
2. **多源交叉**：任何 P0 结论必须 ≥2 个独立维度支持。单维度信号不能下 P0。
3. **合理性检查**：数据与预期偏差 >20% 立即停，查根因，不继续。
4. **区分事实与推断**：报告里每个数字标注来源（实测/推断/文档），每个结论标注置信度。
5. **命令参数查文档**：不凭记忆用参数。新工具先 `--help`，关键参数用最小用例验证。

---

## 2. 完整流程（6 个 Phase）

### Phase 0: 基线确认（不推断，只读事实）

**目标**：搞清楚仓库**已经有什么**，避免"重新发明"已有指标。

**强制步骤**：

- [ ] 读 `docs/code-quality-metrics.md`（如存在）— 列出已定义的所有指标、目标值、工具
- [ ] 读 `docs/INDEX.md`（如存在）— 了解文档结构
- [ ] 读 `.github/workflows/*.yml` — 列出 CI 已跑的所有 job 和工具
- [ ] 读 `.pre-commit-config.yaml` — 列出本地钩子配置的工具和参数
- [ ] 读 `pyproject.toml` 的 `[tool.*]` 段 — 确认每个工具的配置
- [ ] 读 `ruff.toml` / `mypy.ini` 等 — 确认 lint/type 规则和豁免清单
- [ ] 读 `docs/typing-tech-debt.md`（如存在）— 了解已跟踪的技术债

**产出**：`artifacts/audit-v<N>/phase0-baseline.md`，包含：

```markdown
## 已有指标体系（来自 docs/code-quality-metrics.md）
| 维度 | 工具 | 目标 | 当前 | 来源 |
|------|------|------|------|------|
...

## CI 已跑的工具
| Job | 工具 | 阻塞/Advisory | 来源 |
|-----|------|--------------|------|
...

## 已豁免的债务（来自 ruff.toml per-file-ignores）
| 文件 | 豁免规则 | 原因 |
|------|---------|------|
...

## 本次审计需要补的维度（gap）
- [ ] 列出 docs/ 和 CI 都没覆盖的工具
```

**检查点**：在 Phase 0 完成前，**禁止**跑任何采集命令。先搞清楚已有什么。

---

### Phase 1: 工具验证（先确认能用）

**目标**：确认每个要用的工具能正确运行，参数含义明确。

**强制步骤**：

- [ ] 每个工具跑 `--version` 确认安装
- [ ] 每个工具跑 `--help` 确认参数含义（不凭记忆）
- [ ] 对关键参数，用最小测试用例验证行为：
  - 例：radon `-e` 是 exclude 还是 extend？在一个文件上试，看输出
  - 例：vulture `--min-confidence 80` 实际过滤多少？对比默认输出
- [ ] 确认扫描范围（目标目录存在、文件数合理）

**产出**：在 phase0-baseline.md 追加工具验证结果。

**检查点**：任何参数含义不明，**禁止**继续。先 `--help` 或查文档。

---

### Phase 2: 数据采集（原始落盘）

**目标**：用真跑数据，不用推断。

**强制步骤**：

- [ ] 每个工具独立跑，输出重定向到原始文件（不让输出回显到 context）
- [ ] 采集后立即做**合理性检查**：
  - 数字范围是否合理？（函数数、错误数、覆盖率）
  - 与 Phase 0 读到的历史数据对比（如 CI baseline）
  - 与工具文档示例对比
  - 与上一次审计对比（如有）
- [ ] 任何偏差 >20% **立即停**，查根因：
  - 是工具配置问题？
  - 是命令参数问题？
  - 是仓库真的变化了？
- [ ] 记录每个工具的 exit code（很多工具非 0 不代表失败，如 bandit 发现问题）

**产出**：`artifacts/audit-v<N>/` 目录下的原始文件：
- `cc.json`, `mi.json`, `raw.json` (radon)
- `deadcode.txt` (vulture，**必须带 --min-confidence 80**)
- `lint.txt` (ruff)
- `types.txt` (mypy)
- `deps.txt` (deptry)
- `cov.json` (pytest-cov)
- `bandit.txt` (bandit，如配置)
- `pip-audit.txt` (pip-audit，如配置)
- `jscpd-report.json` (jscpd，如配置)

**检查点**：每个原始文件生成后，立即抽样核对 1-2 个已知数据点。

---

### Phase 3: 数据解读（先确认 schema）

**目标**：正确理解数据格式，避免解读错误。

**强制步骤**：

- [ ] 读工具文档确认输出 schema（每个字段含义）
- [ ] 用**已知用例**验证解读：
  - 例：找一个已知简单的函数，看它的覆盖率是多少
  - 例：找一个已知复杂的函数，看它的 CC 是多少
- [ ] 对 ambiguous 格式，明确标注字段含义：
  - coverage `0/36` = "0 行未测 / 36 总行 = 100% 覆盖"（不是 0% 覆盖！）
  - vulture `60% confidence` = 最低阈值（不是高置信度）
  - bandit exit code 1 = 发现问题（不是工具失败）
- [ ] 解读后做交叉验证：用第二种方法核对（如 AST 解析 vs 工具报告）

**产出**：每个维度的结构化解读（Python 脚本输出）。

**检查点**：任何数字与预期不符，**先怀疑解读**，再怀疑数据。

---

### Phase 4: 多维度交叉评估

**目标**：用多维度交叉判断真实风险，单维度不下 P0 结论。

**强制步骤**：

- [ ] 定义真实风险公式：`风险 = f(CC, 覆盖率, 调用频率, 副作用, 业务关键性)`
- [ ] **覆盖率是必选维度**（不能跳过）
- [ ] 任何 P0 必须有 ≥2 个独立维度支持：
  - 高 CC ∧ 低覆盖率 → 真 P0
  - 高 CC ∧ 高覆盖率 → 降级（测试网强，strangler fig 安全）
  - 低覆盖率 ∧ 低 CC → 补测试，不是重构
- [ ] 函数级覆盖率分析（不只是文件级）：
  - 用 AST 解析 cc.json 得到函数边界
  - 用 coverage missing_lines 计算每个函数的覆盖率
  - 输出 "CC × 覆盖率" 矩阵
- [ ] 副作用识别：函数是否有文件/网络/subprocess/全局状态操作？

**产出**：`artifacts/audit-v<N>/risk-matrix.md`：

```markdown
## 真实风险矩阵（CC × 覆盖率）

| CC | 覆盖率 | 函数 | 真实风险 | 处理方式 |
|----|--------|------|---------|---------|
| 40 | 40% | _extract_session_info_streaming | 极高 | 先补测试 |
| 43 | 96.8% | check_server | 低 | strangler fig 安全起点 |
| 118 | 89.2% | init_project_memory | 中 | 可重构 |
```

**检查点**：任何 P0 必须在矩阵里标注支持的维度。单维度 P0 **拒绝**。

---

### Phase 5: 交叉验证（独立方法核对）

**目标**：用独立方法核对每个结论。

**强制步骤**：

- [ ] 对每个"死代码"：用 grep/rg 引用扫描确认（区分定义点 vs 调用点 vs 字符串提及）
- [ ] 对每个"重复代码"：
  - 客观工具（jscpd / pylint R0801）给字面重复率
  - 手动 diff 确认逻辑重复
  - 明确区分"字面重复" vs "逻辑重复"
- [ ] 对每个"P0 函数"：
  - 调用点扫描（谁调用它？调用频率？）
  - 副作用识别（parity test 难度）
  - 测试影响（tests/ 引用数 + 实际覆盖率）
- [ ] 对每个"安全发现"：
  - bandit severity 分级
  - pip-audit 实际可利用性
  - 区分 dev 依赖 vs 运行时依赖
- [ ] **对每个"覆盖率盲区"（Phase 4 产出的低覆盖函数）**，必须执行以下 4 步：

#### Step 1: grep 发现所有相关测试文件

不能只看文件名匹配（如 `test_<模块名>.py`），必须 grep 整个 tests/ 目录找所有引用目标函数的测试：

```bash
# 模板：搜索所有引用目标函数名的测试文件
rg '<函数名>' tests/

# 示例：detect_pollution 的测试在哪些文件？
rg 'detect_pollution' tests/
# -> tests/test_p2_pollution_whitelist.py（注意：不是 test_validate_memory_system.py！）
```

**反面案例**：覆盖率盲区报告（2026-07-18）曾声称 `detect_pollution` 96% 未测，但 `test_p2_pollution_whitelist.py` 有 11 个测试全面覆盖（Rule 1/2/3 全测到）。报告作者只搜了 `test_validate_memory_system.py`（文件名匹配），漏看了真正测试文件。5 个盲区中因此 2 个完全错误。

#### Step 2: pytest-cov term-missing 验证

确认声称未测的行号是否真的 missing，区分"完全未测" vs "间接覆盖"：

```bash
# 查看特定模块的 missing lines
pytest --cov=memory_core.<模块路径> --cov-report=term-missing tests/ -q --no-header

# 示例：version_sync.py 哪些行没测到？
pytest --cov=memory_core.tools.version_sync --cov-report=term-missing tests/ -q --no-header
```

如果 missing lines 集中在异常分支/默认值，而非主路径，则风险等级应下调。

#### Step 3: 读断言判断覆盖深度

找到测试文件后，读断言内容区分 smoke test vs 真实路径覆盖：

```bash
# 读测试函数体，看断言是否真正验证了目标行为
rg -A 20 'def test_.*<函数名>' tests/<找到的测试文件>.py
```

判断标准：
- 断言只检查 `result is not None` / `exit_code == 0` -> smoke test，不算真实覆盖
- 断言检查具体输出值 / 副作用 / 异常类型 -> 真实路径覆盖

#### Step 4: 区分单元 vs 集成覆盖

集成测试可能通过调用上层函数间接覆盖目标函数，这类间接覆盖应计入：

```bash
# 搜索所有调用目标函数的代码（生产代码 + 测试代码）
rg '<函数名>\(' memory_core/ tests/
```

如果集成测试调用了上层函数（如 `init_project_memory`），上层函数内部调用了目标函数（如 `_enrich`），则目标函数的主路径已被间接覆盖。仅异常分支和边缘 case 可能仍缺。

**反面案例**：覆盖率盲区报告曾将 `patch_ownership_memory_version` 列为 MEDIUM（87% 未测），但 `test_version_sync_resign.py` 的 6 个集成测试通过 patch+sign 流程间接覆盖了主写入路径。仅 regex no-match 边缘 case 缺。报告未识别间接覆盖，错误高估了风险。

#### 覆盖率盲区验证反面案例总结

本次（2026-07-18）覆盖率盲区报告的 5 个盲区准确率仅 ~40%：

| 盲区 | 报告判断 | 实际 | 错因 |
|------|---------|------|------|
| detect_pollution | P1 HIGH 96% 未测 | 有 11 个测试 | 漏看 test_p2_pollution_whitelist.py |
| cmd_apply_upgrade | P1 HIGH 未测 | 准确（已修复）| - |
| patch_ownership_memory_version | P2 MEDIUM 87% 未测 | 主路径已有间接覆盖 | 未识别集成测试间接覆盖 |
| pretooluse_guard 早退 | P2 LOW 应补 | 已有直接测试 | 漏看 test_pretooluse_guard.py:633 |
| _enrich | P3 LOW | 准确 | - |

根因：只看文件名匹配的测试文件 + 未识别集成测试间接覆盖。上述 Step 1-4 正是为了防止此类错误。

**产出**：`artifacts/audit-v<N>/cross-validation.md`。

**检查点**：任何结论没有第二证据，标注"待验证"，不能进最终报告。

---

### Phase 6: 报告产出（区分事实与推断）

**目标**：产出可信、可追溯、可复现的报告。

**强制步骤**：

- [ ] 每个数字标注来源：
  - `[实测]` 来自本次工具运行
  - `[文档]` 来自 docs/ 或 CI 配置
  - `[推断]` 基于其他数据推算（需说明依据）
- [ ] 每个结论标注置信度：
  - `高`：≥2 独立证据 + 交叉验证
  - `中`：单维度证据 + 合理性检查通过
  - `低`：推断或待验证
- [ ] 明确列出"未验证的假设"和"方法论局限"
- [ ] 健康度评分算法必须可复现（扣减系数要让公式产出与结论一致）
- [ ] P0 标签严格定义：阻塞 / 安全漏洞 / 正确性缺陷。可维护性债务用独立标签。

**产出**：`artifacts/code-quality-audit-v<N>.md`。

**报告结构模板**：

```markdown
# 代码质量审计 v<N>

## 1. 执行摘要
- 健康度评分: X/100（算法: ...）
- 测试状态: N passed / M failed
- 整体覆盖率: X%

## 2. 与上次审计的差异（如有）
| 维度 | 上次 | 本次 | 变化原因 |

## 3. 真实维度数据
### 3.1 覆盖率（必选）
### 3.2 复杂度
### 3.3 类型检查
### 3.4 安全扫描
### 3.5 漏洞扫描
### 3.6 死代码（min-confidence 80）
### 3.7 重复代码（jscpd + 手动 diff）
### 3.8 依赖检查

## 4. 风险矩阵（CC × 覆盖率）

## 5. 优先级清单
### P0（阻塞/安全/正确性）
### P1（高风险可维护性）
### P2（中风险）
### P3（低风险/细节）

## 6. strangler fig 可行性评估

## 7. 未验证的假设与方法论局限

## 8. 原始数据索引
```

**检查点**：报告里任何"缺失维度"必须先确认 `docs/code-quality-metrics.md` 和 CI 配置里真的没有。不能跳过 Phase 0 就报"缺失"。

---

## 3. 工具命令模板（memory-core 专用）

```bash
# 所有命令在仓库根目录执行，使用 .venv
cd /Users/busiji/memory

# Phase 2 采集（注意参数！）
.venv/bin/radon cc -j memory_core scripts workspace > artifacts/audit-v<N>/cc.json
.venv/bin/radon mi -j memory_core scripts workspace > artifacts/audit-v<N>/mi.json
.venv/bin/radon raw -j memory_core scripts workspace > artifacts/audit-v<N>/raw.json

# vulture 必须带 --min-confidence 80（与 pre-commit 一致）
.venv/bin/vulture --min-confidence 80 memory_core > artifacts/audit-v<N>/deadcode.txt 2>&1

.venv/bin/ruff check . > artifacts/audit-v<N>/lint.txt 2>&1
.venv/bin/deptry . > artifacts/audit-v<N>/deps.txt 2>&1
.venv/bin/mypy --strict memory_core > artifacts/audit-v<N>/types.txt 2>&1

# 覆盖率（必跑，不能跳过）
.venv/bin/pytest --cov=memory_core \
  --cov-report=json:artifacts/audit-v<N>/cov.json \
  --cov-report=term-missing \
  -q --no-header tests

# 安全（如已安装）
.venv/bin/bandit -r memory_core -f json -q > artifacts/audit-v<N>/bandit.json 2>&1
.venv/bin/pip-audit --progress-spinner off > artifacts/audit-v<N>/pip-audit.txt 2>&1

# 重复代码（客观度量）
npx --yes jscpd memory_core --reporters json --output artifacts/audit-v<N>/jscpd
# 配合手动 diff 验证逻辑重复
```

---

## 4. 常见错误模式（反 checklist）

审计过程中**禁止**以下行为：

- [ ] ❌ 不读 `docs/code-quality-metrics.md` 就报"缺失维度"
- [ ] ❌ 不读 CI 配置就说"CI 没跑 X"
- [ ] ❌ 凭记忆用工具参数（radon `-e`、vulture 不带 `--min-confidence`）
- [ ] ❌ 解读前不确认数据 schema（`0/36` 读反）
- [ ] ❌ 数据与预期偏差时不立即停
- [ ] ❌ 单维度下 P0 结论（只用 CC，不用覆盖率交叉）
- [ ] ❌ 把"字面重复"和"逻辑重复"混为一谈
- [ ] ❌ 健康度评分算法与报告结论脱节
- [ ] ❌ 把"已豁免的债务"（ruff.toml per-file-ignores）当"新发现"
- [ ] ❌ 不区分 dev 依赖漏洞和运行时漏洞

---

## 5. 与已有文档的关系

| 文档 | 作用 | 本 SOP 的关系 |
|------|------|--------------|
| `docs/code-quality-metrics.md` | 定义指标体系 | Phase 0 必读 |
| `docs/typing-tech-debt.md` | typing 技术债 backlog | Phase 0 必读 |
| `docs/INDEX.md` | 文档结构索引 | Phase 0 必读 |
| `.github/workflows/ci.yml` | CI 管道 | Phase 0 必读 |
| `.pre-commit-config.yaml` | 本地钩子 | Phase 0 必读 |
| `ruff.toml` | lint 规则 + 豁免清单 | Phase 0 必读 |
| `pyproject.toml [tool.*]` | 工具配置 | Phase 0 必读 |

---

## 6. 审计周期建议

- **每次 release 前**：跑 Phase 2 全套采集，对比上次，生成差异报告
- **每季度**：完整 6 Phase 审计，重排 P0/P1
- **重大重构后**：完整 6 Phase 审计，确认无回归
- **新增工具时**：更新 `docs/code-quality-metrics.md` + 本 SOP 的命令模板

---

## 7. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-07-18 | 初始版本，基于历史审计的错误教训总结 |
