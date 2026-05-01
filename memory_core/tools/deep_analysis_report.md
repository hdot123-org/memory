# Memory Core 工具模块深度分析报告

## 1. 逐文件详细分析

---

### 文件 1: `memory_core/tools/memory_hook_core.py` (核心模块)

**文件职责**: 将策略驱动的注册门控评估集中在一个模块中，使 gateway 保持精简。是 M4/M5 版本上下文包组装的核心。

#### 1.1 `_resolve_callbacks(config: CoreConfig) -> dict[str, Callable]`

- **签名**: 内部函数，接收 `CoreConfig` 实例，返回 `dict[str, Callable]`（13 个回调函数名的映射）
- **参数**:
  - `config`: `CoreConfig` 实例（通过前向引用 `"CoreConfig"` 声明）
- **核心逻辑**:
  1. 检查 `config` 是否携带 `policy_registry` 组合接口对象——如果有，从中提取 11 个绑定方法（`validate_project_map`、`validate_unique_legal_system_contract`、`validate`、`get_policy_pack`、`governance_frozen_tuple_errors`、`event_contract_blocker_errors`、`git_registration_probe`、`truth_basis_for_scope`、`decision_refs_for_scope`、`lesson_refs_for_scope`、`docs_refs_for_scope`）
  2. 否则回退到 `config` 的扁平回调字段（`*_fn` 后缀）
  3. 同样逻辑处理 `path_utils` 接口对象（提取 `extract_excerpt`、`write_targets`）
  4. 回退到 `config.extract_excerpt_fn` / `config.write_targets_fn`
  5. 返回统一字典，包含全部 13 个回调
- **边界条件**: `getattr(config, "policy_registry", None)` 使用默认值 `None`，确保缺失属性不会抛异常
- **依赖关系**: 依赖 `CoreConfig` 数据结构（`memory_hook_config.py`），依赖 `PolicyRegistry` 和 `PathUtils` 接口（`memory_hook_interfaces`）
- **设计意图**: 适配两种接口模式（组合接口 vs 扁平回调），为迁移期提供兼容层

#### 1.2 `registration_phase_from_policy_pack(policy_pack, default_phase) -> str`

- **签名**: `(dict[str, Any], str = "declared-not-enforced") -> str`
- **参数**:
  - `policy_pack`: 策略包字典，期望包含 `{"policies": {"registration_phase": "..."}}` 嵌套结构
  - `default_phase`: 默认阶段，默认为 `"declared-not-enforced"`
- **核心逻辑**:
  1. `policies = policy_pack.get("policies")` 获取嵌套字典
  2. 检查 `isinstance(policies, dict)` ——必须是字典
  3. `phase = policies.get("registration_phase")` 提取阶段
  4. 检查 `isinstance(phase, str) and phase` ——必须是非空字符串
  5. 否则返回 `default_phase`
- **边界条件**: 任何层级缺失或类型不正确都会优雅降级到默认值
- **异常处理**: 无显式异常抛出，纯防御性编程

#### 1.3 `evaluate_registration_commit_gate(policy_pack, registration_commit_gate, event, default_phase) -> tuple[dict[str, Any], list[str]]`

- **签名**: `(dict[str, Any], dict[str, Any], str, str = "declared-not-enforced") -> tuple[dict, list]`
- **参数**:
  - `policy_pack`: 策略包字典
  - `registration_commit_gate`: 注册门控状态字典
  - `event`: 当前事件名（如 `"stop"`、`"session-start"`）
  - `default_phase`: 默认阶段
- **返回值**: 元组 `(gate_dict, errors_list)` ——门控状态和错误列表
- **核心逻辑**（三段式决策树）:
  1. 调用 `registration_phase_from_policy_pack` 解析阶段
  2. `enforced = phase == "enforced"` ——只有 `"enforced"` 阶段才执行硬阻塞
  3. 复制门控字典 `gate = dict(registration_commit_gate)`
  4. 注入 `phase`、`enforced`、`triggered_on_current_event` 到 gate
  5. `gate_event = gate.get("gate_event", "stop")` ——默认在 `stop` 事件触发
  6. `triggered = event == gate_event` ——判断当前事件是否匹配
  7. **分支一**: `not enforced` → `"not-enforced"`，无错误
  8. **分支二**: `enforced but not triggered` → `"awaiting-gate-event"`，无错误
  9. **分支三**: `enforced and triggered` → 检查 `status == "committed-coupled"` → `"passed"` 或 `"failed"` + 错误消息
- **边界条件**:
  - `gate_event` 默认 `"stop"`
  - 非 enforced 状态保持 M3 语义（不硬阻塞）
- **依赖关系**: 依赖 `registration_phase_from_policy_pack`

#### 1.4 `build_context_package_core(...) -> dict[str, Any]` (主函数)

- **签名**: 37 个 keyword-only 参数（全部 `*` 之后）
- **参数分组**:
  - **环境 (7)**: `host`, `event`, `payload`, `cwd`, `project_scope`, `workspace_root`, `repo_root`
  - **路径 (6)**: `required_canonical`, `project_canonical`, `project_runtime_root`, `global_canonical`, `project_map_governance`, `event_log`
  - **策略 (7)**: `legality_source_policy`, `registration_commit_policy`, `registration_commit_phase`, `project_map_refs`, `hook_contract_path`, `surface_id`, `workspace_id`
  - **回调 (14)**: `extract_excerpt_fn`, `now_iso_fn`, `write_targets_fn`, `validate_project_map_fn`, `validate_unique_legal_system_contract_fn`, `policy_validate_fn`, `get_policy_pack_fn`, `governance_frozen_tuple_errors_fn`, `event_contract_blocker_errors_fn`, `git_registration_probe_fn`, `truth_basis_for_scope_fn`, `decision_refs_for_scope_fn`, `lesson_refs_for_scope_fn`, `docs_refs_for_scope_fn`
  - **可选 (3)**: `governance_blocker_scopes`, `event_contract_blocker_scopes`, `core_evidence_refs`

- **核心逻辑**（逐阶段分析）:

  **阶段 1 — 内部辅助函数**:
  ```python
  def _safe_tb(basis: dict, key: str, default: Any = None) -> Any:
  ```
  安全提取 truth_basis 字典中的键，等价于 `basis.get(key, default)`。避免 `basis` 中意外 `None` 值导致 `AttributeError`。

  **阶段 2 — 路径与合约验证**:
  ```python
  missing_paths = [str(path) for path in required_canonical if not path.exists()]
  ```
  检查所有必需规范路径是否存在，不存在的收集为字符串列表。

  ```python
  project_map_errors = validate_project_map_fn()
  contract_errors = validate_unique_legal_system_contract_fn()
  ```
  调用项目地图验证和合法性合约验证回调。

  **阶段 3 — 策略验证（带异常保护）**:
  ```python
  try:
      policy_errors = policy_validate_fn({...})
  except Exception as exc:
      policy_errors = [f"policy validation failed: {exc}"]
  ```
  将 host、event、cwd、project_scope 传入策略验证，使用宽泛的 `except Exception` 兜底。

  **阶段 4 — 治理与事件合约检查**:
  ```python
  governance_scopes = set(governance_blocker_scopes or [])
  event_contract_scopes = set(event_contract_blocker_scopes or [])
  governance_tuple_errors = governance_frozen_tuple_errors_fn() if project_scope in governance_scopes else []
  event_contract_errors = event_contract_blocker_errors_fn() if project_scope in event_contract_scopes else []
  ```
  仅当当前 `project_scope` 在治理/事件合约阻塞范围内时才执行对应检查——范围感知优化。

  **阶段 5 — Git 注册探测与门控评估**:
  ```python
  registration_commit_gate = git_registration_probe_fn(event, payload)
  ```
  获取 git 注册探测状态。

  ```python
  policy_pack = get_policy_pack_fn(project_scope)  # 带 try/except
  ```
  解析策略包，失败时注入错误信息到 `policy_pack` 字典。

  ```python
  registration_commit_gate, registration_gate_errors = evaluate_registration_commit_gate(...)
  ```
  执行注册门控评估。

  **阶段 6 — 项目文件解析**:
  ```python
  project_file = project_canonical.get(project_scope)
  if project_file is None:
      policy_errors.append(f"unsupported project_scope: {project_scope}")
      project_file = workspace_root / "projects" / project_scope / "PROJECT.md"
  elif not project_file.exists():
      missing_paths.append(str(project_file))
  ```
  三种情况：无映射 → 错误 + 默认路径；存在但不存在 → 加入 missing；正常 → 使用。

  **阶段 7 — Truth Basis 引用收集**:
  ```python
  decisions = decision_refs_for_scope_fn(project_scope)
  lessons = lesson_refs_for_scope_fn(project_scope)
  docs_refs = docs_refs_for_scope_fn(project_scope)
  truth_basis = truth_basis_for_scope_fn(project_scope)
  truth_basis_refs = _safe_tb(truth_basis, "refs", [])
  truth_basis_errors = list(_safe_tb(truth_basis, "errors", []))
  ```
  收集决策、课程、文档引用以及 truth basis 数据。

  **阶段 8 — Reads 列表构建与集合校验**:
  ```python
  reads = [
      str(workspace_root / "NOW.md"),
      *project_map_refs,
      str(workspace_root / "memory" / "kb" / "INDEX.md"),
      str(workspace_root / "memory" / "docs" / "INDEX.md"),
      *truth_basis_refs,
      *decisions,
      *lessons,
      *docs_refs,
  ]
  ```
  构建允许读取的文件列表。

  **阶段 9 — 集合交叉验证（重要约束检查）**:
  ```python
  truth_basis_set = set(truth_basis_refs)
  if not truth_basis_set.issubset(read_set):
      truth_basis_errors.append("allowed_reads does not cover all truth basis refs")
  if set(decisions) & truth_basis_set:
      truth_basis_errors.append("decision refs overlap with truth basis refs")
  if set(lessons) & truth_basis_set:
      truth_basis_errors.append("lesson refs overlap with truth basis refs")
  if set(docs_refs) & truth_basis_set:
      truth_basis_errors.append("docs refs overlap with truth basis refs")
  ```
  四个约束：
  1. truth basis refs 必须是 allowed_reads 的子集
  2. decision refs 不能与 truth basis refs 重叠
  3. lesson refs 不能与 truth basis refs 重叠
  4. docs refs 不能与 truth basis refs 重叠

  **阶段 10 — 状态判定**:
  ```python
  status = "ok" if not missing_paths and not project_map_errors and not contract_errors
      and not policy_errors and not truth_basis_errors and not blocker_errors else "degraded"
  ```
  所有验证通过 → `"ok"`，否则 → `"degraded"`。

  **阶段 11 — 构建返回字典**:
  返回结构包含：
  - `schema_version`: 固定 `"wb-hook-v2"`
  - `generated_at`: ISO 时间戳
  - 环境信息：host、event、各种根路径
  - `status` + `validation_errors`（聚合所有错误源）
  - `system_context`: 完整的系统级上下文（治理、合约、truth basis、策略包等）
  - `project_context`: 项目级上下文（truth status、runtime_root、evidence_refs 等）
  - `task_context`: 任务级上下文（event、task_ref、session_id 等）
  - `allowed_reads` / `allowed_writes`: 读写权限列表
  - `evidence_refs`: 证据引用列表

#### 1.5 `build_context_package_from_config(config: CoreConfig) -> dict[str, Any]`

- **签名**: 接收单个 `CoreConfig` 对象
- **核心逻辑**:
  1. 调用 `_resolve_callbacks(config)` 解析回调字典
  2. 将所有 config 字段映射为 `build_context_package_core()` 的 37 个 keyword 参数
  3. 行为与 `build_context_package_core()` 完全一致，仅参数接口不同
- **设计意图**: 用结构化配置替代 37 个散列参数，是迁移目标接口

---

### 文件 2: `memory_core/tools/__init__.py` (公共 API 入口)

**文件职责**: 定义 memory-core 公共 API，使用延迟导入避免重型模块加载。

#### `__getattr__(name: str)` — 延迟导入机制

- **签名**: `(str) -> Any`
- **核心逻辑**:
  1. `build_context_package` → 延迟从 `memory_hook_gateway` 导入
  2. `build_context_package_simple` → 延迟从 `memory_hook_gateway` 导入
  3. `CoreConfig` → 延迟从 `memory_hook_config` 导入
  4. `build_context_package_from_config` → 延迟从 `memory_hook_core` 导入
  5. 未匹配 → `raise AttributeError`
- **`__all__`**: 声明 4 个公开符号
- **设计意图**: 避免 `import memory_core.tools` 时加载所有依赖（gateway、config 等可能有重型导入链）

---

### 文件 3: `memory_core/tools/cmux_hook_state.py` (Hook 状态管理)

**文件职责**: 管理 hook 运行时状态的持久化、并发安全读写。

#### 3.1 `HookStateError(RuntimeError)` — 自定义异常类

- **签名**: `class HookStateError(RuntimeError)`
- **继承**: `RuntimeError`
- **用途**: 所有 hook 状态相关错误的统一异常类型

#### 3.2 `_hook_state_lock_path(path: Path) -> Path`

- **签名**: 内部函数，`(Path) -> Path`
- **逻辑**: `path.with_name(f"{path.name}.lock")` — 在同目录下生成同名 `.lock` 文件

#### 3.3 `_exclusive_hook_state_lock(path: Path)` — 排他锁上下文管理器

- **签名**: `@contextmanager` 装饰器，`(Path) -> Generator`
- **逻辑**:
  1. 创建 lock 文件（`mkdir -p parents=True`）
  2. `fcntl.flock(handle, LOCK_EX)` — POSIX 排他文件锁
  3. `yield` — 执行临界区
  4. `finally: fcntl.flock(handle, LOCK_UN)` — 确保解锁
- **边界条件**: 锁文件在父目录不存在时自动创建
- **平台依赖**: 使用 `fcntl`，仅适用于 POSIX 系统（Linux/macOS），**不支持 Windows**

#### 3.4 `runtime_state_dir(project_dir: Path) -> Path`

- **逻辑**: 检查 `project_dir / "memory_core" / "artifacts"` 是否存在 → 若存在则返回 `{artifacts}/cmux-runtime`；否则返回 `project_dir / ".cmux-runtime"`
- **设计意图**: 支持两种运行时目录布局（标准 vs 工作区）

#### 3.5 路径工厂函数群（8 个）

| 函数 | 返回路径 |
|------|---------|
| `default_hook_state_path` | `{runtime}/hook-state.json` |
| `default_assignment_file_path` | `{runtime}/cmux-assignment.json` |
| `default_pm_bot_watch_assignment_file_path` | `{runtime}/pm-bot-watch.json` |
| `default_codex_main_task_path` | `{runtime}/codex-main-task.json` |
| `default_project_overview_json_path` | `{runtime}/project-task-overview.json` |
| `default_project_overview_text_path` | `{runtime}/project-task-overview.txt` |
| `default_assignment_watcher_pid_path` | `{runtime}/watch_cmux_assignments.pid` |
| `default_assignment_watcher_log_path` | `{runtime}/watch_cmux_assignments.log` |

#### 3.6 `_base_payload() -> dict[str, object]`

- **返回**: `{"runtime": "cmux", "updated_at": "", "surfaces": {}}`

#### 3.7 `reset_hook_state(path: Path) -> Path`

- **逻辑**: 确保目录存在 → 写入基础 payload → 返回路径
- **依赖**: `write_hook_state`

#### 3.8 `load_hook_state(path: Path) -> dict[str, object]` — 宽松模式

- **逻辑**:
  1. 文件不存在 → 返回 `_base_payload()`
  2. 解析 JSON 失败（`OSError` 或 `JSONDecodeError`）→ 返回 `_base_payload()`
  3. 顶层不是 dict → 返回 `_base_payload()`
  4. `surfaces` 不是 dict → 修复为 `{}`
  5. 返回修复后的 payload
- **特点**: 完全容错，任何异常都降级到基础状态

#### 3.9 `load_hook_state_strict(path: Path) -> dict[str, object]` — 严格模式

- **逻辑**: 与 `load_hook_state` 相同步骤，但每一步失败都抛出 `HookStateError` 而非降级
- **边界条件**: 文件不存在 → `HookStateError("hook state file missing: ...")`
- **用途**: 用于写入后的回读验证

#### 3.10 `_write_hook_state_unlocked(path, payload)` — 无锁写入

- **逻辑**:
  1. 序列化 JSON（`ensure_ascii=False, indent=2`）
  2. `tempfile.mkstemp` 创建临时文件
  3. 写入 → `flush` → `fsync`（确保落盘）
  4. `Path(tmp_name).replace(path)` — 原子替换
  5. `finally` 清理临时文件
  6. `load_hook_state_strict(path)` — 回读验证
- **原子性保障**: 临时文件 + rename 模式确保写入原子性
- **依赖**: `load_hook_state_strict` 用于写入后校验

#### 3.11 `write_hook_state(path, payload)` — 带锁写入

- **逻辑**: 获取排他锁 → 调用 `_write_hook_state_unlocked`
- **并发安全**: 多进程并发写入不会冲突

#### 3.12 `get_surface_hook_state(path, surface_ref) -> dict[str, object]`

- **逻辑**: 加载状态 → 提取 `surfaces[surface_ref]` → 返回或 `{}`
- **边界**: 任何层级缺失都返回空字典

#### 3.13 `_default_surface_state(workspace_ref, surface_ref) -> dict[str, object]`

- **返回结构**:
  ```python
  {
      "workspace_ref": workspace_ref,
      "surface_ref": surface_ref,
      "session_start_count": 0,
      "prompt_submit_count": 0,
      "stop_count": 0,
      "notification_count": 0,
      "last_event": "",
      "last_event_at": "",
      "last_session_id": "",
      "last_cwd": "",
  }
  ```

#### 3.14 `record_hook_event(path, *, event_name, workspace_ref, surface_ref, payload) -> dict[str, object]`

- **逻辑**:
  1. 获取排他锁
  2. 加载状态，确保 `surfaces` 存在
  3. 获取或创建 surface 状态
  4. 更新时间戳、last_event、last_session_id、last_cwd
  5. **计数器递增**（4 种事件类型）:
     - `session-start` → `session_start_count += 1`
     - `prompt-submit` → `prompt_submit_count += 1`
     - `stop` → `stop_count += 1`
     - `notification` → `notification_count += 1`
  6. 更新 `state["updated_at"]`
  7. 调用 `_write_hook_state_unlocked` 持久化
  8. 返回 surface_state
- **边界条件**: `int(surface_state.get(...) or 0)` 处理 None/缺失值

---

### 文件 4: `memory_core/tools/hook_event.py` (事件标准化)

**文件职责**: 为 Codex/Claude 双宿主（dual-host）内存钩子提供统一事件标准化层。

#### 4.1 常量

```python
_CLAUDE_EVENT_MAP = {
    "SessionStart": "session-start",
    "UserPromptSubmit": "prompt-submit",
    "Notification": "notification",
    "Stop": "stop",
}
_VALID_EVENT_TYPES = {"session-start", "prompt-submit", "notification", "stop"}
```

#### 4.2 `HookEvent` dataclass

- **字段**:
  - `source: str` — `"codex"` 或 `"claude"`
  - `event_type: str` — 4 种标准事件类型之一
  - `payload: dict[str, Any]` — 原始载荷
  - `cwd: Path` — 当前工作目录
  - `timestamp: str` — ISO 格式时间戳
  - `project_scope: str = ""` — 项目作用域（可选）

#### 4.3 `_now_iso() -> str`

- **逻辑**: `datetime.now().astimezone().isoformat(timespec="seconds")` — 本地时区 ISO 格式

#### 4.4 `_parse_json(raw: str) -> dict[str, Any]`

- **逻辑**:
  1. 空字符串 → `{}`
  2. `json.loads` 失败 → `{}`
  3. 结果不是 dict → `{"payload": loaded}`（将非标量结果包装为字典）
- **边界条件**: 完全容错

#### 4.5 `_extract_cwd(payload: dict) -> Path | None`

- **逻辑**: 检查 `payload.get("cwd")` 是否为非空字符串 → 返回 `Path(value).expanduser()`

#### 4.6 `_map_claude_event(raw_event: str) -> str`

- **逻辑**: 查 `_CLAUDE_EVENT_MAP`，未匹配则返回原始值

#### 4.7 `_is_valid_event_type(event_type: str) -> bool`

- **逻辑**: 检查是否在 `_VALID_EVENT_TYPES` 中

#### 4.8 `from_codex_payload(raw, event="", cwd=None) -> HookEvent`

- **逻辑**:
  1. 解析 JSON
  2. 事件来源: `event` 参数 > `payload["event"]` > `"prompt-submit"`
  3. 无效事件类型 → 回退到 `"prompt-submit"`
  4. cwd: 参数 > payload > `Path.cwd()`
  5. 构造并返回 `HookEvent(source="codex", ...)`

#### 4.9 `from_claude_payload(raw, cwd=None) -> HookEvent`

- **逻辑**:
  1. 解析 JSON
  2. `raw_event = payload.get("event", "")` → 通过 `_CLAUDE_EVENT_MAP` 映射
  3. 无效 → 回退到 `"prompt-submit"`
  4. cwd 解析同 Codex
  5. 构造并返回 `HookEvent(source="claude", ...)`

#### 4.10 `to_context_package_input(event: HookEvent) -> dict[str, Any]`

- **返回**: `{"host": source, "event": event_type, "payload": payload, "cwd": str(cwd)}`
- **用途**: 将 `HookEvent` 转换为 gateway `build_context_package()` 所需的参数格式

#### 4.11 `parse_hook_event(host, event, raw_payload) -> HookEvent`

- **逻辑**: 统一入口分发器
  - `host == "codex"` → `from_codex_payload(raw_payload, event=event)`
  - `host == "claude"` → `from_claude_payload(raw_payload)`
  - 其他 → `raise ValueError(f"unknown host: {host!r}")`
- **异常**: `ValueError` 对未知宿主

---

### 文件 5: `memory_core/tools/memory_root_discovery.py` (根目录发现)

**文件职责**: 通过遍历目录树发现内存系统项目根目录。纯函数，不依赖 gateway 全局变量。

#### 5.1 常量

```python
_SCRIPT_PATH = Path(__file__).resolve()
_FALLBACK_REPO_ROOT = _SCRIPT_PATH.parents[2]  # 向上三级：tools/ → memory_core/ → repo_root
_MEMORY_DIR = ".memory"
_WORKSPACE_DIR = "memory_core"
```

#### 5.2 `discover_project_root(start_path: Path) -> Path`

- **逻辑**:
  1. `current = start_path.resolve()`
  2. 循环：检查 `current / ".memory"` 是否为目录 → 是则返回
  3. 到达文件系统根（`parent == current`）→ 退出
  4. 回退到 `_FALLBACK_REPO_ROOT`
- **边界条件**: 无限循环被 `parent == current` 条件终止（文件系统根目录的 parent 是自身）
- **回退策略**: 基于模块文件位置推导（`__file__` 上两级）

#### 5.3 `discover_workspace_root(project_root: Path) -> Path`

- **逻辑**: 检查 `project_root / "memory_core"` 是否存在 → 存在则返回，否则返回 `project_root`
- **注意**: 这里实际检查的是 `memory_core` 目录而非 `"workspace"`，与 `_WORKSPACE_DIR` 常量一致

#### 5.4 `discover_roots(start_path: Path) -> tuple[Path, Path]`

- **返回**: `(repo_root, workspace_root)` 元组
- **逻辑**: 组合调用上面两个函数

---

### 文件 6: `memory_core/tools/memory_hook_config.py` (配置数据类)

**文件职责**: 用结构化 `CoreConfig` 替换 `build_context_package_core()` 的 37 个 keyword-only 参数。

#### 6.1 `CoreConfig` dataclass — 字段分组

| 组 | 字段数 | 说明 |
|---|---|---|
| Group 1: Environment | 7 | host, event, payload, cwd, project_scope, workspace_root, repo_root |
| Group 2: Paths | 7 | required_canonical, project_canonical, project_runtime_root, global_canonical, project_map_governance, event_log, hook_contract_path |
| Group 3: Policy config | 6 | legality_source_policy, registration_commit_policy, registration_commit_phase, project_map_refs, surface_id, workspace_id |
| Group 4: Callbacks | 14 | 14 个 Callable 字段 |
| Group 5: Optional | 5 | policy_registry, path_utils, governance_blocker_scopes, event_contract_blocker_scopes, core_evidence_refs |

#### 6.2 `uses_interfaces` 属性

- **逻辑**: `self.policy_registry is not None and self.path_utils is not None`

#### 6.3 `__post_init__()` — 运行时类型验证

对每个字段进行严格的类型检查：
- **Environment**: `host` 必须是 `"codex"` 或 `"claude"`；`event`/`project_scope` 非空字符串；路径必须是 `Path`；`payload` 必须是 `dict`
- **Paths**: `required_canonical`/`global_canonical` 必须是 `list`；`project_canonical`/`project_runtime_root` 必须是 `dict`
- **Policy**: 字符串字段非空校验；`surface_id`/`workspace_id` 类型检查
- **Callbacks**: 所有 14 个回调必须 `callable()`

#### 6.4 `to_gateway_kwargs() -> dict[str, Any]`

- **逻辑**: `dataclasses.asdict(self)` 转换为字典，用于传递给遗留的 `**kwargs` 接口

#### 6.5 `from_gateway_kwargs(...)` — 类方法桥接

- **参数**: 39 个（37 个核心 + `policy_registry` + `path_utils`）
- **逻辑**: 接收旧版 kwargs，构造并返回 `CoreConfig` 实例
- **标记**: `TODO: remove if unused` — 迁移完成后可能需要移除

---

## 2. 模块间依赖关系图

```
                        ┌─────────────────────────────┐
                        │   __init__.py (公共 API)     │
                        │  延迟导入入口                 │
                        └──────────┬──────────────────┘
                                   │ __getattr__
                    ┌──────────────┼──────────────┐
                    │              │              │
        ┌───────────▼──────┐ ┌────▼─────────┐ ┌──▼──────────────────┐
        │memory_hook_gateway│ │memory_hook_  │ │memory_hook_core.py │
        │   (外部模块)       │ │config.py     │ │ (核心组装)          │
        │ build_context_    │ │ CoreConfig   │ │                     │
        │ package / simple  │ │ dataclass    │ │                     │
        └───────────────────┘ └──────┬───────┘ └──┬──────────────────┘
                                     │            │
                                     │            │ 消费 CoreConfig
                                     └────────────┤
                                                  │
                                     ┌────────────▼────────────┐
                                     │  _resolve_callbacks()   │
                                     │  从 config 提取 13 个回调│
                                     └────────────┬────────────┘
                                                  │
                                    ┌─────────────┼──────────────┐
                                    │             │              │
                          ┌─────────▼─────┐ ┌─────▼─────┐ ┌──────▼─────┐
                          │ PolicyRegistry │ │ PathUtils │ │  其他回调  │
                          │ (interfaces)   │ │(interfaces)│ │ (callbacks)│
                          └───────────────┘ └───────────┘ └────────────┘


独立模块（不依赖 core，但被其他模块消费）:
┌─────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ cmux_hook_state.py  │  │  hook_event.py       │  │ memory_root_discovery│
│ Hook 状态持久化      │  │ HookEvent 标准化     │  │ .py 根目录发现       │
│                     │  │                      │  │                      │
│ HookStateError      │  │ HookEvent (dataclass)│  │ discover_project_    │
│ load/write/reset    │  │ from_codex/claude    │  │   root()             │
│ record_hook_event   │  │ parse_hook_event()   │  │ discover_workspace_  │
│                     │  │ to_context_pkg_input │  │   root()             │
└─────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

**依赖方向**:
- `__init__.py` → `memory_hook_gateway`、`memory_hook_config`、`memory_hook_core`（延迟）
- `memory_hook_core.py` → `memory_hook_config.py`（通过 `CoreConfig`）
- `memory_hook_config.py` → `memory_hook_interfaces`（TYPE_CHECKING 时导入 `PolicyRegistry`、`PathUtils`）
- `cmux_hook_state.py` → 无内部依赖（纯独立模块）
- `hook_event.py` → 无内部依赖（纯独立模块）
- `memory_root_discovery.py` → 无内部依赖（纯独立模块）

---

## 3. 关键设计决策与模式识别

### 3.1 回调接口适配模式（Adapter Pattern）
`_resolve_callbacks()` 实现了双模式兼容：当 `config` 携带 `PolicyRegistry` / `PathUtils` 接口对象时从中提取方法；否则使用扁平的 `*_fn` 回调字段。这是渐进式迁移的典型模式。

### 3.2 防御性降级模式（Defensive Degradation）
- `registration_phase_from_policy_pack`: 任何层级缺失/类型不对 → 返回默认值
- `load_hook_state`: 任何异常 → 返回基础 payload
- `policy_validate_fn` 的 `try/except Exception` → 返回错误列表而非崩溃
- `get_policy_pack_fn` 的 `try/except` → 注入错误信息

### 3.3 三态门控评估模式
`evaluate_registration_commit_gate` 采用经典的三态决策：
1. **Not enforced** → 不阻塞
2. **Enforced, awaiting event** → 等待
3. **Enforced, triggered** → 检查状态 → pass/fail

### 3.4 原子写入 + 回读验证模式
`_write_hook_state_unlocked` 使用临时文件 + `replace()` 实现原子写入，并通过 `load_hook_state_strict()` 回读验证写入完整性。

### 3.5 范围感知的策略执行
`governance_tuple_errors` 和 `event_contract_errors` 仅在 `project_scope in scopes` 时才执行——避免不必要的开销。

### 3.6 引用集合交叉验证
严格检查 truth_basis_refs、decision_refs、lesson_refs、docs_refs 之间的互斥关系，防止数据模型不一致。

### 3.7 延迟导入模式（Lazy Import）
`__init__.py` 使用 `__getattr__` 实现延迟导入，避免 `import memory_core.tools` 触发完整的依赖链加载。

### 3.8 双宿主事件标准化
`hook_event.py` 统一了 Codex 和 Claude 两种不同事件源的数据格式，提供统一入口 `parse_hook_event()`。

### 3.9 纯函数根目录发现
`memory_root_discovery.py` 完全不依赖全局状态，仅通过文件系统遍历和模块位置推导。

### 3.10 结构化配置替代散列参数
`CoreConfig` 将 37 个 keyword-only 参数封装为带类型验证的 dataclass，提供 `__post_init__` 运行时校验。

---

## 4. 潜在问题与改进建议

### 4.1 平台兼容性问题 ⚠️
**`cmux_hook_state.py` 使用 `fcntl.flock`**，这是 POSIX 专属 API，在 Windows 上会 `ImportError`。
- **建议**: 在 Windows 上回退到 `msvcrt.locking` 或使用 `filelock` 第三方库。

### 4.2 过度宽泛的异常捕获
`build_context_package_core` 中：
```python
except Exception as exc:  # pragma: no cover
```
- **建议**: 区分可预期异常（如 `ValueError`、`KeyError`）和不可预期异常，对后者应记录日志或重新抛出。

### 4.3 `_parse_json` 的语义不一致
当 JSON 解析结果不是 dict 时，返回 `{"payload": loaded}`，这与其他容错点返回 `{}` 的行为不一致。
- **建议**: 统一行为或增加日志说明。

### 4.4 `CoreConfig.__post_init__` 的性能开销
每次实例化都遍历 14 个回调进行 `callable()` 检查，虽然安全但可能重复。
- **建议**: 如果性能敏感，可考虑在 `TYPE_CHECKING` 下使用类型检查替代部分运行时检查。

### 4.5 `build_context_package_core` 参数过多（37 个）
虽然 `CoreConfig` 提供了替代方案，但核心函数本身的 37 参数接口仍然脆弱。
- **建议**: 最终应废弃 `build_context_package_core` 的 kwargs 版本，统一使用 `build_context_package_from_config`。

### 4.6 `discover_workspace_root` 命名误导
函数名中的 `workspace` 实际检查的是 `memory_core` 目录（`_WORKSPACE_DIR = "memory_core"`）。
- **建议**: 重命名为 `discover_memory_core_root` 或更新 `_WORKSPACE_DIR` 常量名为 `_MEMORY_CORE_DIR`。

### 4.7 `record_hook_event` 中的计数器类型转换
```python
int(surface_state.get("session_start_count") or 0)
```
当计数值为 `0`（整数零，是 falsy）时，`or 0` 仍返回 0，行为正确；但如果值为字符串 `"0"`，`or 0` 也会返回 0（因为非空字符串为 truthy）。这是一个微妙的正确行为，但可读性差。
- **建议**: 使用 `int(surface_state.get("session_start_count", 0))` 更清晰。

### 4.8 `hook_event.py` 中 `timestamp` 精度问题
`_now_iso()` 使用 `timespec="seconds"`，精度为秒级。
- **建议**: 如果需要更高精度（如事件排序），可改为 `timespec="microseconds"`。

### 4.9 `__init__.py` 缺少 `build_context_package_core` 导出
`__all__` 中包含 `build_context_package_from_config` 但未包含 `build_context_package_core`。
- **建议**: 如果 `build_context_package_core` 需要公开使用，应加入 `__all__`。

### 4.10 缺少单元测试覆盖指示
`build_context_package_core` 中的 `# pragma: no cover` 注释表明异常分支未被测试覆盖。
- **建议**: 补充策略验证异常场景的测试用例。
