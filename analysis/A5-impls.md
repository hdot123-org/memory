# A5: `memory_hook_impls.py` 分析报告

> 文件：`workspace/tools/memory_hook_impls.py` · 1251 行 · 项目最大文件
> 分析日期：2026-04-27

---

## 1. 类清单

| # | 类名 | 接口 | 行数 | 方法数 | 职责简述 |
|---|------|------|------|--------|----------|
| 1 | `CodexDelegate` | `HostDelegate` | 38 | 4 | Codex 宿主代理：调用 `cmux codex-hook` 子进程 |
| 2 | `ClaudeDelegate` | `HostDelegate` | 93 | 4 | Claude 宿主代理：记录状态 + 调用 `cmux claude-hook` |
| 3 | `PolicyRegistryImpl` | `PolicyRegistry` | 207 | 15 | 策略注册表 + policy pack 加载 + 冲突解决 + 8 个 stub 方法 |
| 4 | `RouteTargetPolicyImpl` | `RouteTargetPolicy` | 29 | 2 | 根据事件类型解析写入路径（含日期动态路径） |
| 5 | `WriteTargetPolicyImpl` | `WriteTargetPolicy` | 29 | 2 | 写入目标路径模板字典 |
| 6 | `GatewayBusinessPolicyConfig` | dataclass | 40 | 0 | 不可变配置载荷（36 个字段） |
| 7 | `GatewayBusinessPolicyImpl` | `GatewayBusinessPolicy` | 510 | 31 | 业务策略：scope 解析、project-map 校验、truth-basis 校验、事件契约校验 |
| 8 | `ArtifactSinkImpl` | `ArtifactSink` | 39 | 3 | 将事件包写入 JSON snapshot + latest + events.jsonl |
| 9 | `ErrorSinkImpl` | `ErrorSink` | 16 | 2 | 追加式错误日志写入 |
| 10 | `ArtifactWriter` | 无接口 | 58 | 4 | 封装 `ArtifactSinkImpl` + 非阻塞错误处理 |
| 11 | `DelegateRouter` | 无接口 | 38 | 3 | 根据 host 名分发到 Codex/Claude delegate |
| 12 | `PathUtilsImpl` | `PathUtils` | 48 | 3 | 路径工具：文件 excerpt 提取 + write_targets 映射 |

**总计：12 个类（含 1 个 dataclass），83 个方法，1251 行。**

---

## 2. 方法统计

### 方法数 Top 5

| 类 | 方法数 | 总行数 | 平均方法长度 |
|----|--------|--------|-------------|
| `GatewayBusinessPolicyImpl` | 31 | 510 | 16.5 行 |
| `PolicyRegistryImpl` | 15 | 207 | 13.8 行 |
| `ArtifactWriter` | 4 | 58 | 14.5 行 |
| `CodexDelegate` | 4 | 38 | 9.5 行 |
| `ClaudeDelegate` | 4 | 93 | 23.3 行 |

`GatewayBusinessPolicyImpl` 占整个文件的 **40.8%**（510/1251 行）。

---

## 3. 职责分析（SRP）

### 3.1 职责单一的类

- **`CodexDelegate`** — 只做一件事：执行 `cmux codex-hook` 子进程。干净。
- **`RouteTargetPolicyImpl`** — 只做路径解析。干净。
- **`WriteTargetPolicyImpl`** — 只做路径模板管理。干净。
- **`ArtifactSinkImpl`** — 只做 artifact 写入。干净。
- **`ErrorSinkImpl`** — 只做错误日志追加。干净。
- **`PathUtilsImpl`** — 纯工具函数。干净。

### 3.2 职责过载的类

**`GatewayBusinessPolicyImpl`**（严重）：

这一个类承担了至少 **6 种不同的责任**：

1. **Scope 解析**：`determine_project_scope()` — 路径匹配判定
2. **Project-map 校验**：`validate_project_map_files()` — 检查 4 个文档中是否包含特定中文字符串
3. **Legal system contract 校验**：`validate_unique_legal_system_contract()` — 检查 7 个文档的一致性
4. **Frozen tuple 校验**：`governance_frozen_tuple_blocker_errors()` — 标记检查
5. **Event contract 校验**：`event_contract_blocker_errors()` — **100 行**，解析 markdown 章节 + JSON 字段交叉验证
6. **Truth basis 校验**：`truth_basis_for_scope()` + `_truth_basis_errors_for()` — 路径分类 + 引用验证

此外还包含：
- 12 个 `_` 前缀的私有工具方法（markdown 解析、JSON 提取、路径判断）
- 路径分类器 `_classify_truth_ref()`（35 行，20 个分支）

**建议拆分方向**：按上述 6 种责任拆成 5-6 个独立的 validator 类，`GatewayBusinessPolicyImpl` 退化为 orchestrator。

**`PolicyRegistryImpl`**（中度）：

- 核心职责：policy pack 加载 + 策略查询 + 冲突解决
- 但包含 **8 个 stub 方法**（L364-398），这些方法的 docstring 都写着 "Real impl delegates to GatewayBusinessPolicy"
- 这些 stub 说明 `PolicyRegistryImpl` 承担了接口适配层的角色，但实际逻辑被委托出去

**`ClaudeDelegate`**（轻度）：

- 除了执行 `cmux` 子进程外，还负责：
  - 状态文件路径解析（L140-151）
  - 状态记录调用（L159-173）
  - ID canonicalization（L153-157）
- 这些职责可能应该属于一个独立的 `StateRecorder` 组件

---

## 4. 硬编码问题

### 4.1 硬编码路径（严重）

文件中存在 **大量** 硬编码的 `"memory"` 路径段，分散在 3 个类中：

| 位置 | 类 | 行数 |
|------|----|------|
| L198 | `PolicyRegistryImpl.DEFAULT_POLICY_PACK_PATH` | `"memory" / "kb" / "global" / ...` |
| L420-424 | `RouteTargetPolicyImpl.__init__` | 5 处 `"memory" / ...` |
| L429 | `RouteTargetPolicyImpl.resolve` | `"memory" / "log" / ...` |
| L443-452 | `WriteTargetPolicyImpl.__init__` | 10 处 `"memory" / ...` |
| L641-656 | `GatewayBusinessPolicyImpl._classify_truth_ref` | 7 处 `"memory" / ...` |
| L1235-1245 | `PathUtilsImpl.write_targets` | 10 处 `"memory" / ...` |

这些路径在 `RouteTargetPolicyImpl`、`WriteTargetPolicyImpl`、`PathUtilsImpl.write_targets()` 中**重复了 3 次**，但内容基本一致。没有统一的 path 常量或配置源。

### 4.2 硬编码字符串（中度）

`GatewayBusinessPolicyImpl` 的校验方法中嵌入了 **18+ 条中文字符串**作为文档内容断言：

```
"唯一合法入口"
"只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。"
"同次 `git commit` 提交后才生效"
"按 wave 推进"
...
```

这些字符串与上游文档的精确措辞强耦合。文档改一个字，校验就失效。

### 4.3 硬编码字符串键（轻度）

`PolicyRegistryImpl` 的 `resolve_conflict()` 中对 `"kb_overwrite_allowed"` 和 `"registration_phase"` 做了硬编码分支（L352-355），这些 key 应该来自配置。

### 4.4 Magic Number

- `max_lines: int = 12`（L1210）—— 可接受，作为合理默认值
- `suffix:02d`（L1053）—— 合理的格式化
- 无其他显著 magic number

---

## 5. 错误处理模式

### 5.1 一致的部分

- 所有 I/O 操作（文件读取）都使用了 `try/except (OSError, json.JSONDecodeError)` 安全模式
- `PolicyRegistryImpl._load_dynamic_policy_pack()` 和 `_load_scope_overrides()` 都静默吞掉异常返回默认值
- `ArtifactWriter.write()` 使用非阻塞错误处理：异常被记录而不是抛出

### 5.2 不一致的部分

- **`ClaudeDelegate.execute()`**（L133-138）：缺少环境变量时抛 `RuntimeError`，但 `CodexDelegate.execute()`（L75-78）的模式相同——这两个类保持一致，好。
- **`PolicyRegistryImpl` stub 方法**：8 个方法都返回空列表/空字典。这不是错误处理，而是**静默失败**——如果上游期待非空结果，调用方不会得到任何失败信号。
- **`ArtifactSinkImpl.write()`**（L1047-1069）：直接访问 `package['host']` 和 `package['event']`，如果 key 不存在会抛 `KeyError`，没有任何防御。
- **`DelegateRouter.route()`**（L1182）：对未知 host 抛 `ValueError`——正确的做法，但与 `ArtifactWriter.write()` 的吞异常策略形成对比。

### 5.3 评估

错误处理策略**总体可以接受但不够一致**。`ArtifactWriter` 的非阻塞设计是合理的（artifact 写入不应阻断主流程），但 `PolicyRegistryImpl` 的 8 个 stub 方法构成静默失败风险。

---

## 6. 复杂度热点

### 6.1 超长方法（>50 行）

| 方法 | 行数 | 位置 |
|------|------|------|
| `event_contract_blocker_errors()` | 100 | L873-972 |
| `execute()` (ClaudeDelegate) | 55 | L127-181 |
| `resolve_conflict()` | 45 | L316-360 |
| `_truth_basis_errors_for()` | 47 | L679-731 |
| `validate_unique_legal_system_contract()` | 42 | L815-856 |
| `validate_project_map_files()` | 37 | L767-802 |
| `_classify_truth_ref()` | 35 | L628-662 |

### 6.2 嵌套过深

- `event_contract_blocker_errors()` 内部有 **4 层嵌套**（dict comprehension + if + for + if）
- `_truth_basis_errors_for()` 中 L699-701 有一行长达 **196 字符** 的路径构造列表推导式，可读性极差：
  ```python
  source_paths = [(self._config.repo_root / Path(item).expanduser()).resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser() for item in source_refs]
  ```

### 6.3 认知复杂度最高的方法

`event_contract_blocker_errors()`（100 行）是整个文件最复杂的方法。它：
1. 读取 5 个文件
2. 对 3 个文档做 markdown 章节解析
3. 对每个文档做 3 种 set 交叉验证
4. 对 2 个 JSON 样本文件做 5 种字段验证
5. 积累所有错误到同一个列表

### 6.4 重复代码

`WriteTargetPolicyImpl` 的路径字典和 `PathUtilsImpl.write_targets()` 的路径字典**高度重复**（10+ 个相同 key），但结构不完全一致。这表明存在一个未被提取的共享 path map 概念。

---

## 7. 代码质量评分

### 评分：**6 / 10**

**得分理由（+）：**
- 接口实现完整，每个 `HostDelegate` 方法都有实现
- 依赖注入做得好（`which_cmd`, `runner`, `datetime_module` 等都可注入，便于测试）
- `try/except ImportError` 兼容 direct 和 package import 模式
- `GatewayBusinessPolicyConfig` 使用 frozen dataclass，配置不可变
- 文件 I/O 都指定了 `encoding="utf-8"`
- 整体没有使用全局状态

**扣分理由（-）：**
- `GatewayBusinessPolicyImpl` 510 行、31 个方法，严重违反 SRP（-2）
- 硬编码路径在 3 个类中重复出现，没有统一管理（-1）
- 18+ 条中文字符串硬编码作为文档断言，与上游文档强耦合（-0.5）
- 8 个 stub 方法返回空值，构成静默失败风险（-0.5）

---

## 8. 重构建议

### 建议 1：拆分 `GatewayBusinessPolicyImpl`（优先级：高）

将 510 行的巨兽拆成：

```
GatewayBusinessPolicyImpl          # orchestrator，只负责路由和组装
├── ProjectMapValidator            # validate_project_map_files()
├── LegalSystemContractValidator   # validate_unique_legal_system_contract()
├── FrozenTupleValidator           # governance_frozen_tuple_blocker_errors()
├── EventContractValidator         # event_contract_blocker_errors()
├── TruthBasisValidator            # truth_basis_for_scope() + _truth_basis_errors_for()
└── ScopeResolver                  # determine_project_scope() + get_project_*()
```

每个 validator 只依赖 `GatewayBusinessPolicyConfig` 和私有工具方法。

### 建议 2：提取 `WorkspacePathMap` 常量类（优先级：高）

把分散在 `RouteTargetPolicyImpl`、`WriteTargetPolicyImpl`、`PathUtilsImpl.write_targets()` 中的重复路径定义统一为一个来源：

```python
@dataclass(frozen=True)
class WorkspacePathMap:
    workspace_root: Path

    def fact_log(self) -> Path: ...
    def global_kb(self) -> Path: ...
    def project_kb(self) -> Path: ...
    # etc.
```

三个消费者直接引用这个 map，消除 30+ 行重复。

### 建议 3：将硬编码文档断言字符串外部化（优先级：中）

把 `GatewayBusinessPolicyImpl` 中 18+ 条中文字符串提取到一个配置常量文件（如 `workspace/tools/memory_contract_markers.py`）或 JSON/YAML 配置：

```python
# memory_contract_markers.py
PROJECT_MAP_INDEX_MARKERS = [
    "唯一合法入口",
    "只有出现在合法目录地图中并被标为 `active-legal` 的条目或目录，才是合法资料。",
    ...
]
```

这样文档措辞变更只需要改一个地方。

### 建议 4：消除 `PolicyRegistryImpl` 的 8 个 stub 方法（优先级：中）

这些 stub 的存在说明 `PolicyRegistry` 接口承担了不属于它的职责。两个选择：

- **选项 A**：从 `PolicyRegistry` 接口移除这些方法，调用方直接访问 `GatewayBusinessPolicyImpl`
- **选项 B**：保留接口但实现为 `NotImplementedError` 而非静默返回空值，让调用方明确知道需要 `GatewayBusinessPolicy`

### 建议 5：拆分 `ClaudeDelegate` 的状态记录职责（优先级：低）

将状态文件解析 + 记录逻辑提取到独立的 `ClaudeStateRecorder` 类，`ClaudeDelegate.execute()` 只需调用 `recorder.record(...)` 再执行 `cmux`。这样 `ClaudeDelegate` 的行数从 93 降到约 60，职责更清晰。

---

## 附录：文件结构概览

```
memory_hook_impls.py  (1251 lines)
├── IF-1: HostDelegate 实现
│   ├── CodexDelegate        (38 lines, 4 methods)
│   └── ClaudeDelegate       (93 lines, 4 methods)
├── IF-2: PolicyRegistry 实现
│   └── PolicyRegistryImpl   (207 lines, 15 methods)  ← 含 8 个 stub
├── IF-3: Route/Write Target 实现
│   ├── RouteTargetPolicyImpl  (29 lines, 2 methods)
│   └── WriteTargetPolicyImpl  (29 lines, 2 methods)
├── IF-3.5: GatewayBusinessPolicy 实现
│   ├── GatewayBusinessPolicyConfig  (40 lines, dataclass)
│   └── GatewayBusinessPolicyImpl    (510 lines, 31 methods)  ← 复杂度热点
├── IF-4: Artifact/Error Sink 实现
│   ├── ArtifactSinkImpl     (39 lines, 3 methods)
│   └── ErrorSinkImpl        (16 lines, 2 methods)
├── IF-5: 辅助类
│   ├── ArtifactWriter       (58 lines, 4 methods)
│   └── DelegateRouter       (38 lines, 3 methods)
└── IF-6: PathUtils 实现
    └── PathUtilsImpl        (48 lines, 3 methods)
```
