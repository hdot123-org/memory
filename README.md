# memory

标准记忆模块，为多个项目提供统一的 memory core 能力。

架构原则：
- 一个正式入口：统一 gateway
- 一个正式出口合同：统一 route/write contract
- 不同项目只做 adapter 适配，不改入口/出口协议
- 模块层禁止内建任何单项目默认真相

## 目录结构

- Core 组装逻辑：`workspace/tools/memory_hook_core.py`
- Gateway 编排与 provider 解析：`workspace/tools/memory_hook_gateway.py`
- 接口与默认实现：`workspace/tools/memory_hook_interfaces.py`、`workspace/tools/memory_hook_impls.py`
- 适配层（含 workbot profile 等项目适配器）：`workspace/tools/memory_hook_adapters/`
  - adapter 运行文档：`workspace/tools/memory_hook_adapters/docs/`
- 回退演练：`workspace/tools/memory_hook_provider_rollback.py`
- 测试：`tests/`

## 运行模型

- 推荐 provider：`external-core`
- 兼容 provider：`legacy`（仅用于受控回滚）
- 消费者项目通过 gateway 加载 core builder，并按自身 adapter profile 执行后续 delegate/artifact/error 流程

## 给消费者项目的接入口径

消费者侧至少需要：

1. `memory_hook_gateway.py`（统一调用入口）
2. `<project>_runtime_profile.py`（项目 adapter 配置）
3. `memory_hook_provider_rollback.py`（回滚演练）

关键环境变量：

- `MEMORY_HOOK_CORE_PROVIDER`：`external-core`（默认）或 `legacy`
- `MEMORY_HOOK_EXTERNAL_CORE_MODULE`：默认 `memory_hook_core`
- `MEMORY_HOOK_EXTERNAL_CORE_PATH`：联调时可指定本地路径

## M3 Consumer Truth 清理

M3 将 workbot-only 治理真相和交付链从模块默认层彻底清出：

- 治理文档去默认化：routing、legal-core、ingestion-registry 全部声明 `Scope: adapter`
- project binding 修正：workbot.md 声明为 consumer adapter 描述符，消除绝对路径
- 发布链中立化：移除默认 workbot dispatch，改为可配置白名单 `dispatch_targets`
- M2 遗留测试补齐：delegate gate、state file strictness、compaction policy、adapter hook contract 共 15 条

相关 commit：`234ff7a`


## M8 API 完成

- CoreConfig dataclass：37 参数结构化配置对象
- build_context_package_simple(host, event, payload)：3 参数简化入口
- context-package-v1：新输出格式（扁平化 paths/project/task，诊断分离）
- PathUtils + PolicyRegistry 扩展：callback 归入接口对象
- ArtifactWriter + DelegateRouter：gateway 职责分离
- pip 包入口点：memory-validate, memory-rollback
- 179+ tests passed

## M2 Adapter 剥离

M2 将 workbot 运行特化从模块默认层剥离为 adapter 能力：

- Codex bypass 下沉到 adapter：`HostDelegate` 新增 `noop_response()`，gateway 不再硬编码宿主输出格式
- CMUX_HOOK_STATE_FILE 改为 adapter policy：`ClaudeDelegate` 不再直读环境变量，由 runtime profile 注入
- artifact compaction 策略框架：`ARTIFACT_COMPACTION` 字典控制 context package 裁剪
- hook-contract 降为 adapter 合同：`scope: adapter`，明确不是模块全局默认
- cli-tools 归位到 adapter docs 目录

相关 commit：`d9e45d0`

## M1 合同收敛

M1 完成了以下基座修复：

- `required_gateway_inputs` 合约：取代旧 `required_canonical`，旧字段保留为兼容桥
- registration_phase / policy-pack 语义对齐：模块默认层不再内建 workbot 绑定默认值
- provider / validator / baseline 最小修复：独立仓基线从 degraded 恢复为 ok
- `memory_hook_interfaces.py` 新增 `get_required_gateway_inputs` 默认委托方法

相关 commit：`5a686b4`

## 回归与演练

全量回归：

```bash
python3 -m pytest -q tests
```

回滚演练：

```bash
python3 workspace/tools/memory_hook_provider_rollback.py
```

## 自动发布与下游触发

本仓已配置自动发布工作流：

- `.github/workflows/release-and-dispatch.yml`

行为：

1. `main` 分支变更触发全量测试
2. 测试通过后自动计算并创建下一个 `v0.1.x` tag
3. 自动创建 GitHub Release
4. 按白名单 `dispatch_targets` 向下游项目发送 `repository_dispatch` 事件

下游 dispatch 采用白名单式可配置策略：`dispatch_targets` 输入参数默认为空，即不向任何项目发送 dispatch。需触发下游时，通过 workflow dispatch 手动指定目标仓库列表。

## 当前状态

- **M8 已完成**：CoreConfig 结构化、简化入口、v1 schema、接口扩展、职责分离、pip 包入口点、179+ tests
- **M1 已完成**：合同收敛、policy 对齐、基线修复、`get_required_gateway_inputs` 默认委托方法
- **M2 已完成**：adapter 下沉、运行特化从模块默认层剥离、`noop_response()` 接口化、state_file 注入链、compaction 策略框架、hook-contract 降为 adapter 合同
- **M3 已完成**：consumer truth 清理、治理文档 adapter scope 声明、发布链中立化、绝对路径清除
- **模块默认层已完全中立化**：不再内建任何单项目默认绑定
- **所有 workbot 文档已标记 adapter scope**：routing、legal-core、ingestion-registry、workbot.md 均声明 `Scope: adapter`
- **发布链已中立化**：移除默认 workbot dispatch，改为可配置白名单 `dispatch_targets`
- **绝对路径已全部清除**：project binding 中不再包含任何宿主绝对路径
- **77 条测试全量通过**：含 M2 遗留 15 条补齐测试（delegate gate、state file strictness、compaction policy、adapter hook contract）
- 仍保留 `legacy` 回滚能力用于故障处置
