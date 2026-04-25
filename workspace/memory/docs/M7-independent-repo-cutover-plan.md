# M7 独立仓迁出执行计划（POR）

> 文档编号：M7-001  
> 版本：V1.0  
> 日期：2026-04-16  
> 维护人：codex

---

## 1. 名称与用途

本计划的标准名称是：**POR（Plan of Record，执行基线计划）**。  
用途：用于跟踪 `memory` 独立仓从“已迁入”到“可生产切换”的收口动作与验收门槛。

---

## 2. 当前基线

- 仓库：`https://github.com/hdot123/memory`
- 迁入提交：`297976e`
- 测试：`python3 -m pytest -q tests` -> `16 passed`
- 回退演练：`python3 workspace/tools/memory_hook_provider_rollback.py` -> `passed`
- 运行烟测：`build_context_package(...)` 当前 `status=degraded`（需收口）

---

## 3. 工作包（WBS）

| 阶段 | 工作包 | 输出物 | 通过标准 |
|---|---|---|---|
| P1 | 文档与路径去耦 | 消除仓内 `workbot` 绝对路径引用 | `rg '<repo-root>'` 结果为 `0` |
| P2 | 治理契约重建 | `project-map` / `INDEX` / `hook-contract` 对齐独立仓语义 | `build_context_package` 关键契约错误清零 |
| P3 | 运行基线收敛 | 默认运行从 `degraded` 收敛为 `ok` | `build_context_package(...).status == ok` |
| P4 | 测试门禁增强 | 新增 runtime/path/contract 断言测试 | 测试全绿，覆盖高于当前基线 |
| P5 | 主仓消费切换 | `workbot` 指向独立仓发布产物 | 主仓回归通过 + 回退演练通过 |
| P6 | 双审与验收 | rea-bot 一审 + 主线程二审 | 双审通过并落卡 Done |

---

## 4. 执行顺序与节奏

1. 先做 P1+P2（去耦与契约），再做 P3（运行收敛）。  
2. P3 达标后做 P4（测试增强），避免“测试先固化错误行为”。  
3. P4 全绿后执行 P5（主仓切换灰度）。  
4. 最后 P6（交叉审计、状态更新、冻结版本）。

---

## 5. 风险与回退

- 风险：契约文本改动可能引入误判。  
  - 控制：每次改动后立刻跑 `pytest` + `build_context_package` 烟测。
- 风险：主仓切换后外部依赖异常。  
  - 控制：保留 `external-core -> legacy` 回退开关与演练脚本。

---

## 6. 完成定义（DoD）

满足以下全部条件才算 M7 完成：

1. 独立仓运行烟测 `status=ok`。  
2. 独立仓内 `workbot` 绝对路径引用为 `0`。  
3. 独立仓测试与 CI 全绿。  
4. 主仓切换后回归与回退演练通过。  
5. rea-bot 一审与主线程二审通过并留档。

---

## 7. 状态看板

| 项 | 状态 |
|---|---|
| P1 文档与路径去耦 | 待开始 |
| P2 治理契约重建 | 待开始 |
| P3 运行基线收敛 | 待开始 |
| P4 测试门禁增强 | 待开始 |
| P5 主仓消费切换 | 待开始 |
| P6 双审与验收 | 待开始 |

