# A9: Provider / Rollback / Validate / CmuxHook 分析

分析范围：

- `workspace/tools/memory_hook_provider_rollback.py`（60 行）
- `workspace/tools/validate_memory_system.py`（270 行）
- `workspace/tools/cmux_hook_state.py`（225 行）

---

## 1. Provider Rollback（memory_hook_provider_rollback.py）

### 1.1 回退机制如何工作

该模块名为 "rollback drill"（回退演练），**并非真正的回退操作工具**，而是一个**探测 + 诊断工具**。

工作流程：

1. 读取环境变量 `MEMORY_HOOK_CORE_PROVIDER`（默认 `"legacy"`）作为「用户请求的 provider」
2. 调用 `gateway._resolve_core_builder("external-core")` —— 尝试加载 external-core provider
3. 调用 `gateway._resolve_core_builder("legacy")` —— 尝试加载 legacy provider
4. 判断两个 probe 的结果：
   - `external_probe_ok`：external-core provider 名称匹配且无错误
   - `legacy_probe_ok`：legacy provider 名称匹配且无错误
5. **`passed = legacy_probe_ok`** —— 只要 legacy 可用就算通过
6. 返回一个包含完整诊断信息的 dict，打印为 JSON

### 1.2 从哪个 provider 回退到哪个

实际的回退逻辑在 `memory_hook_gateway._resolve_core_builder()` 中：

```
external-core  →  legacy  （当 external-core 加载失败且 allow_fallback=True）
```

Rollback drill 只是验证这条回退路径是否畅通：检查 external-core 和 legacy 各自的状态，并不执行实际的 provider 切换。

### 1.3 回退触发条件

- 真正的触发发生在 `gateway._resolve_core_builder()` 内部：
  - 请求的 provider 是 `"external-core"`
  - `_load_external_core_builder()` 抛出异常
  - `allow_fallback=True`（默认）
- Rollback drill 本身没有触发条件——它只是一个被动检查器
- 通过判定条件：只要 `legacy` provider 可解析且无错误即 `passed`

### 1.4 评估

**优点：**
- 轻量、无副作用——只做探测，不改状态
- 返回结构化的 JSON 诊断，便于自动化消费
- 测试覆盖了三条路径：pass、fail、exit code

**不足：**
- 名字有误导性——叫 "rollback" 但实际是 "probe/diagnostic"，没有执行任何回退动作
- `passed` 只检查 `legacy_probe_ok`，完全忽略了 `external_probe_ok` 的状态。如果 external-core 有问题但 legacy 正常，输出 `status: "passed"` 但 external 的错误信息被静默
- 与 gateway 的 `_resolve_core_builder` 形成了隐式耦合，直接探测内部函数（以 `_` 开头）

---

## 2. Validate System（validate_memory_system.py）

### 2.1 验证了哪些检查项

共 **6 个检查项**，按顺序执行：

| # | 检查项 | 函数 | 检查内容 |
|---|--------|------|----------|
| 1 | `gateway_import` | `check_gateway_import()` | `memory_hook_gateway` 能否无异常 import |
| 2 | `core_builder_resolve` | `check_core_builder_resolve()` | `_resolve_core_builder("legacy", allow_fallback=False)` 返回的 builder 是否 callable |
| 3 | `context_package` | `check_context_package()` | builder 产出的 dict 包含 `status`/`host`/`event`/`schema_version`/`system_context`/`task_context` 等顶层 key；`system_context` 包含 `boot_entry`/`state_entry`；`task_context` 包含 `session_id`/`event` |
| 4 | `core_config_path` | `check_core_config_path()` | `CoreConfig` 和 `build_context_package_from_config` 能否 import 且 callable |
| 5 | `v1_schema` | `check_v1_schema()` | `build_context_package_simple()` 产出的 package 通过 `is_v1()` 校验，且包含 `paths`/`project`/`task` key，不包含 `system_context` |
| 6 | `package_imports` | `check_package_imports()` | `workspace.tools` 包的 `build_context_package` 和 `CoreConfig` 符号是否可 import |

### 2.2 检查逻辑是否充分

**充分的地方：**
- 短路策略合理：gateway import 失败或 core builder 解析失败时立即退出，避免后续连锁报错
- 检查项覆盖了关键接口路径：import → resolve → build → schema → public API
- `check_context_package` 使用了大量 lambda stub 来构造 kwargs，确保 builder 在不依赖外部资源的情况下可以运行

**不充分的地方：**
- `check_context_package` 注入了 20+ 个 lambda stub（`lambda: []`, `lambda: {}` 等），这些 stub 绕过了实际的 policy 校验、governance 校验、event contract 校验。这意味着即使真实的 policy/governance 逻辑被破坏，这个检查也不会发现
- `check_core_config_path` 只检查了 import 和 callable，**没有真正调用** `build_context_package_from_config()`，如果该函数内部有运行时错误，这个检查测不出来
- 缺少对错误路径的验证：不检查当 provider 配置错误时，系统是否能产生有意义的错误信息
- `check_v1_schema` 使用了 `assert` 语句——如果 assert 被 `-O` 优化掉，这部分检查会静默失效

### 2.3 与测试的关系

**有专门的测试文件：** `tests/test_validate_memory_system.py`

测试覆盖情况：

| 测试场景 | 覆盖状态 |
|----------|----------|
| 健康系统返回 exit 0 | ✅ 覆盖 |
| 输出包含 summary 报告 | ✅ 覆盖 |
| 所有检查项通过（numerator == denominator） | ✅ 覆盖 |
| core builder 被破坏时检测失败 | ✅ 覆盖（monkeypatch + in-process 测试） |
| 返回结构无效时 context_package 检查失败 | ✅ 覆盖 |

**测试质量评价：**
- 使用了 monkeypatch 注入故障，覆盖了关键的失败路径
- 既有 subprocess 级别的黑盒测试（检查 exit code 和 stdout），又有 in-process 的白盒测试（检查 ValidateResult 内部状态）
- 覆盖了 ValidateResult 类本身的 `record`、`all_passed`、`summary` 行为
- **缺少**：对 `check_core_config_path`、`check_v1_schema`、`check_package_imports` 的失败路径测试

---

## 3. Cmux Hook State（cmux_hook_state.py）

### 3.1 状态文件记录了什么

状态文件是一个 JSON 文件（默认路径 `.../cmux-runtime/hook-state.json`），结构如下：

```json
{
  "runtime": "cmux",
  "updated_at": "<ISO timestamp>",
  "surfaces": {
    "<surface_ref>": {
      "workspace_ref": "<string>",
      "surface_ref": "<string>",
      "session_start_count": <int>,
      "prompt_submit_count": <int>,
      "stop_count": <int>,
      "notification_count": <int>,
      "last_event": "<event_name>",
      "last_event_at": "<timestamp>",
      "last_session_id": "<string>",
      "last_cwd": "<string>"
    }
  }
}
```

**每个 surface 是一个独立的状态追踪单元**，支持多 surface 并发记录。

### 3.2 事件记录格式

`record_hook_event()` 是核心写入函数：

- **事件类型**：`session-start`、`prompt-submit`、`stop`、`notification`（4 种）
- **计数器**：每个事件类型对应一个独立计数器，按 +1 递增
- **时间戳格式**：`time.strftime("%Y-%m-%dT%H:%M:%S%z")` —— 注意这是 `%z`（时区偏移如 `+0800`），**不是** ISO 8601 的 `+08:00` 格式，缺少冒号分隔符
- **幂等性**：每次写入前加载最新状态，在内存中更新后原子写入，防止并发丢失

### 3.3 与 gateway/core 的集成方式

**直接集成点：**

从当前代码来看，`cmux_hook_state` 是一个**独立模块**，不直接依赖 gateway 或 core：

- 无 gateway import
- 无 core import
- 纯文件系统操作 + JSON 序列化
- 路径推导函数（`runtime_state_dir`、`default_hook_state_path` 等）供外部调用

**间接集成：**
- 状态文件路径模式：`workspace/artifacts/cmux-runtime/` 或 `.cmux-runtime/`
- 通过 `surfaces` 机制与 cmux 的多 surface 架构对齐（`codex-main`、`pm-bot` 等）
- `cmux-assignment.json`、`codex-main-task.json` 等文件路径由同一套 `runtime_state_dir` 逻辑管理

### 3.4 评估

**优点：**
- 使用 `fcntl.flock(LOCK_EX)` 实现进程级互斥，配合原子写入（`mkstemp` + `replace`），并发安全性良好
- 测试覆盖非常全面（300+ 行测试），包括并发写入测试
- `load_hook_state`（容错模式）和 `load_hook_state_strict`（严格模式）分离得当
- 自定义 `HookStateError` 异常，语义清晰

**不足：**
- `_write_hook_state_unlocked` 写完后调用 `load_hook_state_strict(path)` 做「自我验证」——如果写入成功但读取失败，会抛出异常但 temp 文件已经被替换，**原始数据已经丢失**，这个验证实际上是 destructive 的
- 时间戳格式 `%Y-%m-%dT%H:%M:%S%z` 缺少冒号（如 `+0800` vs `+08:00`），在某些 JSON 解析器或日志工具中可能不被识别为合法 ISO 8601
- 事件类型是硬编码的 4 种（`if/elif` 链），新增事件类型需要修改代码——可以考虑注册表模式
- `record_hook_event` 中 `surface_state` 的默认初始化代码重复了两次（`setdefault` 后的 fallback block），存在 DRY 问题

---

## 4. 综合评估

### 4.1 职责是否清晰

| 模块 | 职责清晰度 | 评价 |
|------|-----------|------|
| `memory_hook_provider_rollback` | ⚠️ 模糊 | 名字暗示「执行回退」，实际只做「探测诊断」，建议重命名 |
| `validate_memory_system` | ✅ 清晰 | 命名和实现一致，是一个健康检查工具 |
| `cmux_hook_state` | ✅ 清晰 | 命名和实现一致，是一个状态持久化 + 事件记录工具 |

### 4.2 错误处理是否一致

**不一致之处：**

1. **异常类型**：
   - `cmux_hook_state` 使用自定义 `HookStateError(RuntimeError)`
   - `validate_memory_system` 直接捕获通用 `Exception`，不抛出自定义异常
   - `memory_hook_provider_rollback` 同样捕获通用 `Exception` 并降级为字符串

2. **降级策略**：
   - `rollback`：遇到异常时静默降级（`except: external_provider = "external-core"`），但保留错误信息
   - `validate`：早期检查失败后短路退出，但不报告部分结果
   - `cmux_hook_state`：严格模式抛出异常，容错模式返回默认值——**这是最一致的处理方式**

3. **错误信息传递**：
   - `rollback` 返回 JSON，错误信息结构化
   - `validate` 打印文本报告，错误信息嵌入 `detail` 字符串
   - `cmux_hook_state` 异常消息包含文件路径和原始异常——信息量最大

### 4.3 改进建议

**1. 重命名 `memory_hook_provider_rollback.py`**

当前名字误导。建议改为 `memory_hook_provider_probe.py` 或 `memory_hook_provider_diagnostic.py`，反映其只做探测、不执行回退的本质。

**2. 修复 `check_core_config_path` 的空检查**

`check_core_config_path` 只验证了 import 和 callable，没有实际调用。建议增加一行真正的调用：

```python
# 当前：只检查 callable
if not callable(build_context_package_from_config): ...

# 建议：增加实际调用
config = CoreConfig.load_default()  # 或构造最小有效 config
package = build_context_package_from_config(config)
assert package.get("status") is not None
```

**3. 修复 `check_v1_schema` 的 `assert` 风险**

将 `assert` 改为显式的 `if` 检查并调用 `result.record()`，避免 `-O` 优化后检查失效：

```python
# 当前
assert "paths" in package, "missing 'paths' key"

# 建议
if "paths" not in package:
    result.record("v1_schema", False, "missing 'paths' key")
    return False
```

**4. 消除 `record_hook_event` 中的重复代码**

`surface_state` 的默认值初始化在 `setdefault` 和 fallback block 中重复了两次。建议提取为常量或函数：

```python
def _default_surface_state(workspace_ref: str, surface_ref: str) -> dict:
    return {
        "workspace_ref": workspace_ref,
        "surface_ref": surface_ref,
        "session_start_count": 0,
        # ...
    }
```

**5. 修复时间戳格式为完整 ISO 8601**

将 `time.strftime("%Y-%m-%dT%H:%M:%S%z")` 改为生成 `+HH:MM` 格式的时区偏移：

```python
# 当前
now = time.strftime("%Y-%m-%dT%H:%M:%S%z")  # → 2026-04-27T12:00:00+0800

# 建议
from datetime import datetime, timezone
now = datetime.now(timezone.utc).astimezone().isoformat()  # → 2026-04-27T12:00:00+08:00
```

或者使用 `datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")` 后手动插入冒号。

---

## 5. 测试覆盖总结

| 模块 | 测试文件 | 覆盖行 | 覆盖场景 |
|------|----------|--------|----------|
| `memory_hook_provider_rollback` | `test_memory_hook_gateway_m6_batch3_structure_and_rollback.py` | 约 4 个测试 | pass/fail/exit code/fake resolve |
| `validate_memory_system` | `test_validate_memory_system.py` | 5 个测试 | 健康系统/summary/全通过/core 破坏/无效 package |
| `cmux_hook_state` | `test_cmux_hook_state.py` | 约 15 个测试 | 路径助手/加载/写入/重置/事件记录/锁文件/并发写入 |

**整体评价**：`cmux_hook_state` 测试最全面（含并发测试），`validate_memory_system` 测试中等（缺少部分失败路径），`memory_hook_provider_rollback` 测试基础但够用。
