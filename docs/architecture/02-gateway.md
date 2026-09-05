---
type: "[DOC:DESIGN]"
title: "Gateway 门控设计"
shortname: DES-002
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [gateway,dispatch,routing]
related: [DES-001, DES-003, DES-009]
---

> 文档编号：DES-002 | 版本：V1.1 | 日期：2026-09-05 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码（`memory_core/tools/_gateway_*.py`）。

# Gateway 门控设计文档

> **📌 2026-09-05 校准备注**：本文档上次校准于 2026-05-14（v0.4.0 Beta），此后 gateway 经历重大重构：
>
> 1. **模块拆分**：981 行单体拆为门面（`memory_hook_gateway.py` 494 行，纯 re-export）+ 六个单一职责子模块（`_gateway_config` / `_gateway_artifacts` / `_gateway_policy` / `_gateway_telemetry` / `_gateway_dispatch` / `_gateway_handlers`，均 ≤500 行）+ patch-redirect 兼容层；旧行号锚点全部失效，本文改用函数名定位。
> 2. **入口重指**：console 入口 `memory-hook-gateway` 从 `memory_hook_gateway:main` 改为 `hook_runtime_guard:gateway_main`——import 重量级模块前先装 SIGALRM(8s)/SIGINT 处理器（SessionEnd 防护第一层）。
> 3. **事件面扩展**：`--host` 限定 `factory` / `zcode`（`SUPPORTED_HOSTS`）；`--event` 扩至 9 个；新增非注入事件 fast path、PreToolUse guard 子进程拦截、source repo readonly 分支。
> 4. **配置注入重构**：`globals().update()` 已废弃，改为线程安全 `_adapter_config` 存储；唯一 adapter 为 `default`（从消费项目 `memory/system/adapter.toml` 派生）。workbot adapter 已删除。
> 5. **宿主委派重写**：`CodexDelegate` / `ClaudeDelegate` 已删除，代之以中性的 `FactoryDelegate` / `NoopHostDelegate`；输出新增 Factory 官方 hook JSON 格式（`_build_factory_hook_output`）。
> 6. **新增横切面**：本地优先遥测（metrics.jsonl + 每小时窗口批量同步 PostHog）、session-start 自动版本跟随（探测 memory.lock → infra-core `sync_single_project`）、L2 完整性签名/验证。

> 源文件: `memory_core/tools/memory_hook_gateway.py`（门面，494 行）
> 拆分子模块（2026-09-05 `wc -l` 实测）:
> - `memory_core/tools/_gateway_handlers.py`（495 行）— 事件处理器与 main 入口
> - `memory_core/tools/_gateway_policy.py`（487 行）— 上下文构建与业务策略
> - `memory_core/tools/_gateway_telemetry.py`（483 行）— PostHog 同步与 prompt 日志
> - `memory_core/tools/_gateway_config.py`（467 行）— 常量、adapter 存储、IF-5 门面
> - `memory_core/tools/_gateway_dispatch.py`（444 行）— CWD 发现、delegate、输出格式化
> - `memory_core/tools/_gateway_artifacts.py`（301 行）— artifact/error 写入、readonly 包
> - `memory_core/tools/_gateway_patch_redirect.py`（158 行）— monkeypatch 兼容层
> - `memory_core/tools/hook_runtime_guard.py`（40 行）— console 入口引导守卫
>
> 关联文件: `memory_hook_interfaces.py`（341 行）、`memory_hook_impls.py`（904 行）、`memory_hook_core.py`（552 行）、`memory_hook_config.py`（262 行，CoreConfig）、`memory_hook_adapters/default_runtime_profile.py`（245 行）、`memory_hook_adapters/neutral_policy.py`（23 行）

---

## 1. Gateway 职责定位

### 1.1 做什么

Gateway 是 memory-hook 系统的**入口门控 + 上下文组装器 + 宿主分派器**。它作为 Factory / zcode 的 hook 脚本被调用（经 `~/.factory/bin/memory-hook` wrapper），完成以下工作：

1. **参数解析与 payload 读取**（`_gateway_dispatch._parse_args` / `_read_payload`）：`--host`（choices = `SUPPORTED_HOSTS = ("factory", "zcode")`）、`--event`（9 个：session-start / prompt-submit / stop / notification / pre-tool-use / post-tool-use / subagent-stop / pre-compact / session-end）、`--no-delegate`；从 stdin 读取 JSON payload。

2. **门禁链**（`_gateway_handlers.main()` 前段）：
   - **source repo readonly 检查**（`_handle_source_repo_check`）：memory-core 自身仓库且非 develop 模式 → 返回 `source-repo-rules` 只读上下文包（`allowed_writes: {}` + 所有权域表 + 保护路径），exit 0
   - **拒绝列表**（`is_denied_project_root`）：命中 → 输出 `{}`，exit 0
   - **外部上下文过滤**（`_should_noop_for_external_context`）：cwd 不在仓库内且无强制 env → delegate noop 响应

3. **PreToolUse 守卫拦截**（`_handle_pretooluse_guard`）：pre-tool-use 事件委派子进程 `python -m memory_core.tools.pretooluse_guard`（timeout 5s）做所有权分类，透传其 allow/block 双格式 JSON；守卫失败时按目标路径 fail-closed / fail-open 兜底。

4. **上下文包组装**（`_gateway_policy.build_context_package`）：将 host、event、payload 组装为 `wb-hook-v2` 内部 schema 的 context package（system_context / project_context / task_context / allowed_reads / allowed_writes 五大区块），source repo develop 模式跳过消费者验证层。

5. **产物写入与完整性签名**（`_write_artifacts_and_emit_metrics`）：snapshot + latest + 按日 event log 双写；成功后 `_integrity_sign` 增量重签 manifest；每次调用追加 `metrics.jsonl`。

6. **session-start 副作用**（`_handle_session_start_setup`）：后台健康检查、状态动态字段更新、遥测批量同步（小时窗口）、自动版本跟随（探测 `memory.lock` 版本 → infra-core `probe_version_and_sync`）。

7. **宿主输出分派**（`_gateway_dispatch._execute_delegate` / `_build_factory_hook_output`）：factory/zcode 输出 Factory 官方 hook JSON（SessionStart / UserPromptSubmit 注入 `## Memory Context` additionalContext，其余事件 `{"suppressOutput": true}`）；`--no-delegate` 直接输出完整 context package。

8. **错误与异常记录**（`append_error_log` / `_gateway_excepthook`）：degraded 状态、委托失败、守卫异常写入 `memory/system/errors.log`（含按日分片）；未捕获异常经 excepthook 落 `metrics.jsonl` 的 `hook_error` 记录。

### 1.2 不做什么

- **不做核心业务逻辑**：核心组装在 `memory_hook_core.build_context_package_from_config`（经 `CoreConfig`），gateway 仅做依赖装配与门禁。
- **不做策略定义**：业务策略由 `GatewayBusinessPolicyImpl`（+ `NeutralGatewayBusinessPolicy` 基类）与 adapter.toml 派生配置决定，gateway 经 `_get_gateway_business_policy()` 获取。
- **不做宿主协议实现**：委派协议由 `FactoryDelegate` / `NoopHostDelegate` 实现（返回中性空 JSON），gateway 仅分派。
- **不做所有权判定本体**：PreToolUse 判定在 `pretooluse_guard` + `memory_core/ownership.py`，gateway 只负责子进程编排与 fail-closed 兜底。
- **不做版本同步本体**：自动版本跟随的引擎在 `infra_core.engine.version_sync`（infra-core 仓），gateway 仅注入 resign hook 并进程内调用。
- **不直接操作 git**（限注册探测面）：git 状态探测集中在 `_git_registration_probe`（`git status` / `rev-parse` / `diff-tree`，均带 5s timeout）。

## 2. 入口引导与模块级初始化

### 2.1 引导链（hook_runtime_guard）

```
console-script: memory-hook-gateway
  → hook_runtime_guard.gateway_main()
      → install_guard():
          signal(SIGALRM, _exit0_handler) + signal.alarm(8)
          signal(SIGINT,  _exit0_handler)
      → import memory_core.tools.memory_hook_gateway（重量级 import）
      → gateway.main()
```

- `_BOOT_SECONDS = 8`（早于 Factory 的 10s 硬超时）；`os._exit(0)` 跳过 atexit 回调（避免 telemetry PostHog Client.join 在解释器关闭期抛 traceback）
- 仅 console-script 入口生效；pytest collection 与进程内 `main()` 调用不受影响
- 门面 `memory_hook_gateway.py` 自身在 `__main__` 直跑场景（脚本模式）也安装同款 SIGALRM/SIGINT 处理器，并在结尾 `signal.alarm(0)` 解除

### 2.2 门面 Import 链

门面按 `if __package__:` 分双路径 re-export（包内相对导入 / 裸模块绝对导入 fallback，兼容把 tools 目录加入 sys.path 的脚本模式）。导入的模块族：

```
memory_hook_gateway.py（门面）
├── _gateway_config:      路径常量、_adapter_config 存储、IF-5 门面、完整性签名/验证
├── _gateway_artifacts:   write_artifacts、append_error_log、_build_readonly_source_repo_package、
│                         _launch_async_health_check、_inject_health_alert、_update_state_dynamic_fields
├── _gateway_policy:      build_context_package、_resolve_core_builder、业务策略委托、
│                         _git_registration_probe、_apply_artifact_compaction
├── _gateway_telemetry:   _maybe_sync_telemetry、_log_prompt_submit、_sanitize_for_log
├── _gateway_dispatch:    _parse_args、_read_payload、_discover_cwd、_delegate_*、
│                         _build_factory_hook_output、_execute_delegate、_record_project_lifecycle_event
├── _gateway_handlers:    main、_handle_source_repo_check、_handle_pretooluse_guard、
│                         _gateway_excepthook、HookTimeoutError
├── _gateway_patch_redirect: install_redirect（monkeypatch 重定向）
├── _redaction:           redact（共享脱敏）
├── memory_hook_config:   CoreConfig
├── memory_hook_core:     build_context_package_core / build_context_package_from_config
└── memory_hook_impls:    ArtifactWriter
```

模块加载完成后的两个副作用：

1. `sys.excepthook = _gateway_excepthook`（未捕获异常落 `metrics.jsonl` 的 `hook_error` 记录，再交回 `sys.__excepthook__`）
2. `install_redirect(sys.modules[__name__])`：把对门面符号的 `monkeypatch` / `patch.object` 写入重定向到实际查找该符号的子模块（旧测试语义不变）

### 2.3 Adapter 配置存储（替代 globals().update）

**旧机制已废弃**：早期版本在 import 期 `globals().update(profile)` 注入 30+ 全局变量，现已改为显式配置存储：

```python
_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "default")
_adapter_config: dict[str, Any] = {}          # + threading.Lock 保护
get_config(key, default)                       # 线程安全读
get_config_dict()                              # 浅拷贝快照（安全迭代）
load_adapter_config(profile) / reload_adapter()  # 装载 / 重载
```

模块加载时即执行 `_load_adapter_profile(_ADAPTER_NAME, REPO_ROOT, WORKSPACE_ROOT)` 并装载（import 期副作用，测试可用 `reload_adapter` 替换）。

### 2.4 惰性单例（IF-5 门面，`_gateway_config`）

| 组件 | 可变引用（monkeypatch 目标） | 获取函数 |
|------|------------------------------|----------|
| PolicyRegistry | `_default_policy_registry` | `_get_policy_registry()` |
| RouteTargetPolicy | `_default_route_policy` | `_get_route_policy()` |
| WriteTargetPolicy | `_default_write_policy` | `_get_write_policy()` |
| ArtifactSink | —（每次新建） | `_get_artifact_sink()` |
| ErrorSink | —（每次新建） | `_get_error_sink()` |
| GatewayBusinessPolicy | —（每次按 config 新建） | `_get_gateway_business_policy()` |

`_get_gateway_business_policy()` 每次用当前 `_adapter_config` 构造 `GatewayBusinessPolicyConfig`，策略类取 `GATEWAY_POLICY_CLASS`（default profile 下为 `NeutralGatewayBusinessPolicy`）。

## 3. Adapter 注册表设计

### 3.1 注册表结构（`_gateway_config`）

```python
_ADAPTER_REGISTRY = {
    "default": (
        ".memory_hook_adapters.default_runtime_profile",
        "build_default_runtime_profile",
    ),
}
```

注册表仅含 **一个 adapter**：`default`（**已移除**：`workbot` 条目及 `workbot_runtime_profile.py` / `workbot_policy.py` 模块）。注册表结构仍为 `dict[str, tuple[str, str]]`，条目映射：

- **key**：adapter 名称（`MEMORY_HOOK_ADAPTER` 环境变量选择，默认 `"default"`；未知名称在 `_load_adapter_profile` 中抛 `KeyError`）
- **value**：`(模块路径, 函数名)` 元组

### 3.2 动态加载流程

1. 从注册表取出模块路径与函数名
2. `importlib.import_module(_mod_path, package="memory_core.tools")` 动态导入
3. `getattr(_mod, _fn_name)` 获取工厂函数
4. 调用 `_fn(repo_root, workspace_root)` 获取配置 dict（40+ 键）
5. `load_adapter_config()` 存入 `_adapter_config`（**不再** `globals().update()`）

### 3.3 扩展方式

要添加新 adapter：在 `memory_hook_adapters/` 下创建 `<name>_runtime_profile.py`，实现 `build_<name>_runtime_profile(repo_root, workspace_root) -> dict`，在 `_ADAPTER_REGISTRY` 注册条目，设置 `MEMORY_HOOK_ADAPTER=<name>`。当前实践是**不扩展**：新消费项目直接由 `memory-init` 生成的 `adapter.toml` 驱动 default profile，无需新 adapter 代码。

## 4. 配置注入机制

### 4.1 注入源

唯一注入源是 `build_default_runtime_profile()` 的返回值（`default_runtime_profile.py`，245 行），全部从目标项目 `memory/system/adapter.toml`（`load_adapter_toml`）派生，另含环境读取的 `CLAUDE_HOOK_STATE_FILE`。

### 4.2 注入后的分类使用（经 `get_config()` 消费）

**路径类**（canonical 验证、路由目标）：`PROJECT_MAP_ROOT`、`TRUTH_MODEL`、`PROJECT_MAP_FILES`、`PROJECT_MAP_GOVERNANCE`、`HOOK_CONTRACT_PATH`、`GLOBAL_RULE_PATH`、`MEMORY_SYSTEM_PATH`、`POLICY_PACK_PATH`、`REQUIRED_CANONICAL`、`GLOBAL_CANONICAL`、`REGISTRATION_GIT_SCOPE`、`LOWER_EVIDENCE_ROOTS`、`AUTHORITY_ALLOWED_PATHS`

**策略类**（业务决策）：`LEGALITY_SOURCE_POLICY`、`REGISTRATION_COMMIT_POLICY`、`REGISTRATION_COMMIT_PHASE`、`LEGAL_CORE_MARKERS`、`REQUIRED_REGISTRY_SCOPES`、`GOVERNANCE_BLOCKER_SCOPES`、`EVENT_CONTRACT_BLOCKER_SCOPES`（default profile 下 blocker scope 为空集，frozen tuple / event contract 校验默认关闭）

**映射类**（scope 解析）：`PROJECT_CANONICAL`、`PROJECT_RUNTIME_ROOT`、`PROJECT_DOC_REFS`、`PROJECT_DECISION_REFS`、`PROJECT_LESSON_REFS`、`SCOPE_MATCH_HINTS`、`DEFAULT_PROJECT_SCOPE`（取自 `adapter.toml [routing].project_scope`）、`ROUTE_PROJECT_RUNTIME_SCOPE`

**运行时类**：`GATEWAY_POLICY_CLASS`（`NeutralGatewayBusinessPolicy`）、`CLAUDE_HOOK_STATE_FILE`、`ARTIFACT_COMPACTION`（六 section 默认全包含）、`POLICY_ALLOWED_SCOPES`、`POLICY_SCOPE_INHERITS`

**全局 KB 类**（v0.8.0 新增）：`GLOBAL_KB_ROOT`、`GLOBAL_KB_ENABLED`（`[global_kb]` 段；传入 core 组装）

## 5. main() 事件处理流水线

`_gateway_handlers.main()` 的分支顺序（每个分支命中即短路返回）：

```
main()
  ├─ 1. _parse_args() / stdin → _read_payload() / _discover_cwd()
  ├─ 2. _handle_source_repo_check(cwd, host, event)      → readonly 包, exit 0
  ├─ 3. is_denied_project_root(cwd)                       → "{}", exit 0
  ├─ 4. _should_noop_for_external_context(payload)        → noop 响应
  ├─ 5. _handle_pretooluse_guard(...)                     → guard 输出, exit 0/2
  ├─ 6. event == session-start → _handle_session_start_setup(cwd)
  ├─ 7. event == prompt-submit → _handle_prompt_submit_logging(cwd, payload)
  ├─ 8. event ∈ NON_INJECTION_EVENTS → fast path          → suppressOutput, exit 0
  └─ 9. 注入事件全路径：
        ├─ _record_project_lifecycle_event()（env 门控）
        ├─ ArtifactWriter + build_context_package()
        ├─ session-start: _inject_health_alert() + _handle_integrity_check()
        ├─ _write_artifacts_and_emit_metrics()
        ├─ _compute_exit_code()（status != ok → exit 1）
        └─ _dispatch_output()（--no-delegate JSON / _execute_delegate）
```

### 5.1 source repo readonly 分支

`is_memory_core_source_repo(cwd)` 且 `get_source_repo_mode(cwd) != "develop"` 时，`_build_readonly_source_repo_package()`（`_gateway_artifacts`）构造 `package_kind: "source-repo-rules"` 的上下文包：`mode: "read-only"`、`allowed_writes: {}`、`rules.ownership_domains`（`DEFAULT_OWNERSHIP_DOMAINS` + source repo 专属 `docs/`、`.factory/` critical 域）、`rules.protected_paths`（memory/docs、memory/kb、memory/system、memory/project-map、AGENTS.md）。该包直接输出 stdout，exit 0——防 self-pollution。

### 5.2 PreToolUse guard 分支

仅 `event == "pre-tool-use"`。以 `sys.executable -m memory_core.tools.pretooluse_guard` 子进程执行（`-m` 模式保证绝对导入；`MEMORY_HOOK_ORIGINAL_CWD` 注入项目根；timeout 5s）：

- **成功**：guard stdout/stderr 原样透传（`{"decision": "allow"|"block", "reason": ...}` 旧格式 + `hookSpecificOutput.permissionDecision` 官方格式双写；block → exit 2），随后 `_emit_pretooluse_metrics`
- **失败**（TimeoutExpired / 任意异常）：解析 payload 判 `is_protected_path_target()` → **fail-closed**：保护路径输出 deny（exit 2）；非保护 / 不可解析 → **fail-open**：allow（exit 0）。两种兜底均写脱敏错误日志（payload 前 500 字符经 `redact()`）

### 5.3 session-start 副作用

`_handle_session_start_setup(cwd)`：

1. `_launch_async_health_check(cwd)`：后台线程跑项目健康检查（下次 session-start 经 `_inject_health_alert` 注入 package）
2. `_update_state_dynamic_fields(cwd, project_scope)`
3. `_maybe_sync_telemetry(ARTIFACT_ROOT)`：遥测批量同步（见 §9）
4. **自动版本跟随**（v0.40.1+ / M3 引擎化）：`set_resign_hook(_memory_core_resign_wrapper)`（包装本仓 `load_key` + `sign_project_incremental`，升级门放行后对三文件重签）→ `probe_version_and_sync(cwd, CURRENT_MEMORY_VERSION)`（infra-core 引擎：regex 读 `memory.lock` 的 `memory_version`，不一致时进程内单项目同步 `memory.lock` / `adapter.toml` / `ownership.toml`，tmp + `os.replace` 原子写 + `.sync.lock` 并发防护；major 跳变 / Schema 变更 / 降级仅记警告）。整链 try/except，任何异常不阻塞 hook（exit 0 语义）

### 5.4 非注入事件 fast path

`NON_INJECTION_EVENTS = {stop, notification, post-tool-use, subagent-stop, pre-compact, session-end}` 且 host ∈ SUPPORTED_HOSTS：跳过昂贵的 `build_context_package`，仅做生命周期记录（env 门控 `MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE=1`）+ `_emit_fast_path_metrics`（`fast_path: true` 最小记录）+ `_record_event_log_minimal`，输出 `{"suppressOutput": true}`，exit 0。

### 5.5 注入事件全路径（session-start / prompt-submit）

1. `_record_project_lifecycle_event()`（env 门控；失败仅记错误日志）
2. `ArtifactWriter(CONTEXT_ROOT, ERROR_LOG)` + `build_context_package(host, event, payload, lifecycle_record=...)`
3. session-start 专属：`_inject_health_alert(cwd, package)`；`_handle_integrity_check()`（`_integrity_verify` manifest 验证，失败 → `status="blocked"` + `validation_errors` 追加 `integrity-check-failed` 与明细；密钥缺失跳过保护）
4. `_write_artifacts_and_emit_metrics()`：写入（失败记错误日志）→ 成功后 `_integrity_sign(cwd)` 增量重签 → `emit_metrics`
5. `_compute_exit_code()`：`status != "ok"` → 错误日志 + stderr 摘要（missing paths / validation errors）→ exit 1
6. `_dispatch_output()`：`--no-delegate` → stdout 输出完整 package JSON + exit code；否则 `_execute_delegate()`

## 6. 上下文包构建与 CoreConfig

### 6.1 build_context_package 流程（`_gateway_policy`）

```
build_context_package(host, event, payload, lifecycle_record=None)
  ├─ _discover_cwd(payload)
  ├─ lifecycle_record 为 None 时补 _record_project_lifecycle_event()
  ├─ determine_project_scope(cwd)
  ├─ _get_gateway_business_policy()
  ├─ 构造 CoreConfig（见 6.2）
  ├─ requested = env MEMORY_HOOK_CORE_PROVIDER（默认 legacy）
  ├─ _resolve_core_builder(requested, allow_fallback=True)
  │    ├─ external-core → _load_external_core_builder()（动态导入）
  │    │    失败 → fallback legacy + fallback_errors
  │    └─ legacy → build_context_package_from_config
  ├─ provider_builder(config)
  ├─ source repo（任意模式）：status 强制 ok、清空验证错误、
  │    system_context.source_repo_skip_validation = true
  ├─ system_context 注入：core_provider / core_provider_requested /
  │    project_lifecycle / core_provider_fallback_errors
  ├─ provider_errors 非空且非 source repo → validation_errors 扩展 +
  │    status 降级 degraded
  ├─ MEMORY_HOOK_SHADOW_RUN → 对端 provider 对比（结果入 system_context.shadow_run）
  └─ _apply_artifact_compaction(package)（ARTIFACT_COMPACTION 策略裁剪）
```

另有简化入口 `build_context_package_simple(host, event, payload=None, *, adapter=None, schema="context-package-v1")`：构建 v2 后经 `memory_hook_schema` 转为 `context-package-v1`（或 `memory-v1`）。

### 6.2 CoreConfig 参数来源（原 37 参数 dict 已收拢为 dataclass）

早期版本的 37 个 `core_kwargs` 已收拢为 `memory_hook_config.CoreConfig`（262 行 dataclass），`build_context_package` 逐字段填充后整体传给 `build_context_package_from_config`。参数分类：

- **直接值**：host / event / payload / cwd / project_scope / workspace_root / repo_root / event_log / project_map_governance / hook_contract_path / surface_id（env `CMUX_SURFACE_ID`）/ workspace_id（env `CMUX_WORKSPACE_ID`）
- **策略查询**（business policy 实例方法）：required_canonical / project_canonical / project_runtime_root / global_canonical / project_map_refs
- **adapter 配置**（`get_config()`）：legality_source_policy / registration_commit_policy / registration_commit_phase / governance_blocker_scopes / event_contract_blocker_scopes / core_evidence_refs
- **回调函数**（core 组装期调用）：`extract_excerpt_fn` / `now_iso_fn` / `write_targets_fn` / `validate_project_map_fn` / `validate_unique_legal_system_contract_fn` / `policy_validate_fn` / `get_policy_pack_fn` / `governance_frozen_tuple_errors_fn` / `event_contract_blocker_errors_fn` / `git_registration_probe_fn` / `truth_basis_for_scope_fn` / `decision_refs_for_scope_fn` / `lesson_refs_for_scope_fn` / `docs_refs_for_scope_fn`

core 侧（`memory_hook_core`）支持两种等价入口：`build_context_package_from_config(config)`（推荐）与 `build_context_package_core(**kwargs)`（keyword-only，约 39 参数，含 `global_kb_root` / `global_kb_enabled`）；`_resolve_callbacks` 兼容从复合接口对象或扁平回调字段解析回调。

## 7. Host Delegate 分派逻辑

### 7.1 委派实现（`memory_hook_impls`，行号实测）

| 类 / 函数 | 起始行 | 行为 |
|-----------|--------|------|
| `FactoryDelegate` | L125 | factory/zcode 中性委派：`can_handle()` 恒 True；`execute()` 直接返回 `noop_response()`（`{}\n`，exit 0）；`host_unavailable` False |
| `NoopHostDelegate` | L152 | 兜底委派：输出 `{"host_unavailable": true, "policy_decision": "no_host"}`；`host_unavailable` True |
| `resolve_host_delegate(host, mode="auto")` | L194 | host ∈ SUPPORTED_HOSTS → FactoryDelegate（mode `"noop"` 强制 Noop；`"cmux"` 强制 Factory）；其余 host → NoopHostDelegate |

**已移除**：`CodexDelegate` / `ClaudeDelegate`（cmux codex-hook / claude-hook 执行协议、state file 注入、`cmux identify` canonicalization）已删除。`_gateway_dispatch` 保留 `_canonicalize_cmux_refs`（`cmux identify` 包装）与 `_delegate_codex` / `_delegate_claude` 两个历史函数，但 CLI `--host` choices 限定 factory/zcode，这两个分支不可达。

### 7.2 分派执行（`_execute_delegate`）

```
_execute_delegate(args, raw_payload, payload, cwd, package)
  ├─ host == "codex" / "claude"：历史分支（CLI 不可达）
  ├─ RuntimeError（如 _require_env 缺 env）→ append_error_log +
  │    _build_degraded_package_with_error() 降级包输出, return 0
  ├─ proc.returncode != 0 → append_error_log（含 stdout/stderr）
  ├─ proc.stdout 透传；无 stdout → delegate.noop_response() 兜底
  └─ 其余 host（factory/zcode）：package 存在时输出
     _build_factory_hook_output(package, event), return 0
```

### 7.3 Factory 官方 hook 输出（`_build_factory_hook_output`）

| 事件 | 输出 |
|------|------|
| session-start | `hookSpecificOutput.hookEventName = "SessionStart"`，`additionalContext` 为 `## Memory Context` Markdown（Allowed Reads / Allowed Writes / Validation Warnings 三节，来自 package 字段），`suppressOutput: true` |
| prompt-submit | 同上，`hookEventName = "UserPromptSubmit"` |
| 其他事件 | status ok → `{"suppressOutput": true}`；否则 `{}` |

`--no-delegate` 模式：直接输出完整 context package JSON，exit code 取 `_compute_exit_code`。

### 7.4 Noop 响应（外部上下文）

`_should_noop_for_external_context()`（`_gateway_dispatch`）：`MEMORY_HOOK_FORCE` / `WORKBOT_FORCE_HOOK`（历史别名）/ `_FORCE_HOOK` 任一命中则不 noop；否则 payload cwd、env PWD、`MEMORY_HOOK_ORIGINAL_CWD` 三者均不在仓库内才 noop。noop 时 `_delegate_noop_response(host)` 取 `resolve_host_delegate` 的 `noop_response()` 输出（FactoryDelegate → `{}\n`）。

### 7.5 CWD 发现（`_discover_cwd`）

优先级：`MEMORY_HOOK_PREFER_EXTERNAL_CWD` + `MEMORY_HOOK_ORIGINAL_CWD` → payload.cwd（在仓库内时）→ env PWD（在仓库内时）→ env PWD（仓库外）→ payload.cwd → `REPO_ROOT`。根常量由 `memory_root_discovery.discover_roots()` 发现（种子：`MEMORY_HOOK_PROJECT_CWD` 或 `Path.cwd()`）。

## 8. SessionEnd 防护（v0.15.6 引入，现行有效）

SessionEnd hook 运行在 Factory 会话关闭的最后时刻，需在严格超时窗口内干净退出。四层防护：

| 层 | 载体 | 机制 |
|----|------|------|
| 1. 引导守卫 | `hook_runtime_guard.py` | console 入口 import 重量级模块前安装 SIGALRM(8s) + SIGINT → `os._exit(0)`（早于 Factory 10s 硬超时；仅 console 上下文，pytest import 不触发定时器） |
| 2. 日志确定性预算扫描 | `session_end_logger.py` | `_extract_session_info_streaming` 双预算扫描：TIME_BUDGET 1.8s / BYTE_BUDGET 8MB / CHUNK_SIZE 64KB / MAX_LINE 1MB；达预算即停并写 `truncated: true` |
| 3. Git 子进程超时 + CWD 复用 | `memory_core/ownership.py` | `discover_project_root` 的 `git rev-parse` 加 `timeout=2`；优先复用 wrapper 注入的 `MEMORY_HOOK_PROJECT_CWD`，减少冗余子进程 |
| 4. Wrapper 绝对路径解析 | `factory_global_hooks.py` | `render_wrapper()` 安装期用 `shutil.which()` 把裸 `memory-hook-gateway` 解析为绝对路径写入 wrapper，规避 daemon 执行上下文 PATH 未展开 |

## 9. 遥测挂点

- **每次调用**：`_write_artifacts_and_emit_metrics` / `_emit_pretooluse_metrics` / `_emit_fast_path_metrics` / guard 侧 emit → `memory_hook_metrics.emit_metrics` 追加本地 `metrics.jsonl`（微秒级，零网络；`MEMORY_HOOK_METRICS_DISABLED=1` 可禁用）
- **session-start 批量同步**：`_maybe_sync_telemetry(ARTIFACT_ROOT)`（`_gateway_telemetry`）：
  1. 小时窗口判定（上次成功后 3600s 内跳过；上次尝试后 300s 内 backoff）
  2. `POSTHOG_HOST` 归一化（app/us → `us.i.posthog.com`、eu → `eu.i.posthog.com`）后 socket 443 探测（2s 超时）
  3. 经 `.offset` 伴车文件批量发送未投递记录（BATCH_SIZE=500），成功后推进 offset 并从 JSONL 截断已同步记录
- **prompt-submit 实时日志**：`_log_prompt_submit`（SIGALRM 超时保护，`_PromptLogTimeoutError`），消息内容经 `_sanitize_for_log` 脱敏
- **未捕获异常**：`_gateway_excepthook` 落 `hook_error` 记录（error_type / error_message 前 500 字符 / duration_ms）
- **共享脱敏**：所有日志/指标通道委托 `memory_core/tools/_redaction.py` 的 `redact()` / `redact_dict()`（API token、JWT、认证头、密码参数、私有 IP、home 路径）

## 附录 A：关键路径常量（`_gateway_config`，实测）

| 常量 | 值 | 说明 |
|------|-----|------|
| `REPO_ROOT` / `WORKSPACE_ROOT` | `memory_root_discovery.discover_roots(seed)` | 种子 = `MEMORY_HOOK_PROJECT_CWD` env 或 `Path.cwd()` |
| `ARTIFACT_ROOT` | env `MEMORY_HOOK_ARTIFACT_ROOT` 覆盖；默认 `<workspace>/memory/artifacts/memory-hook` | 消费项目默认从旧 `workspace_root/artifacts` 迁移为 `memory/artifacts` |
| `CONTEXT_ROOT` | `ARTIFACT_ROOT / "contexts"` | snapshot + latest 存放处（含按日子目录） |
| `EVENT_LOG` | `ARTIFACT_ROOT / "events.jsonl"` | legacy 事件日志（同步写按日 `events/<date>.jsonl`） |
| `ERROR_LOG` | env `MEMORY_HOOK_ERROR_LOG` 覆盖；默认 `<workspace>/memory/system/errors.log` | 错误日志（同步写按日 `errors/<date>.log`） |
| `PROJECT_LIFECYCLE_ROOT` | env `MEMORY_HOOK_GLOBAL_STATE_ROOT` → `<root>/project-lifecycle`；默认 `<workspace>/memory/artifacts/memory-hook/project-lifecycle` | Layer 1 生命周期 registry |
| `BATCH_SIZE` | 500 | 遥测批量同步批大小 |

## 附录 B：公开函数索引（按子模块，函数名定位）

**`_gateway_config`**：`get_config` / `get_config_dict` / `load_adapter_config` / `reload_adapter` / `_load_adapter_profile` / `_get_gateway_business_policy` / `_get_policy_registry` / `_get_route_policy` / `_get_write_policy` / `_get_artifact_sink` / `_get_error_sink` / `_resolve_route_target_via_policy` / `_write_targets_via_policy` / `_apply_hook_runtime_write_targets` / `_get_policy_pack_via_registry` / `_resolve_policy_conflict_via_registry` / `_integrity_sign` / `_integrity_verify` / `_collect_changed_paths` / `now_iso` / `exclusive_lock` / `is_memory_core_source_repo` / `get_source_repo_mode` / `is_denied_project_root` / `record_project_lifecycle`

**`_gateway_policy`**：`build_context_package` / `build_context_package_simple` / `_resolve_core_builder` / `_load_external_core_builder` / `_apply_artifact_compaction` / `determine_project_scope` / `project_map_refs` / `validate_project_map_files` / `validate_unique_legal_system_contract` / `decision_refs_for_scope` / `lesson_refs_for_scope` / `docs_refs_for_scope` / `truth_basis_for_scope` / `write_targets` / `resolve_route_target` / `governance_frozen_tuple_blocker_errors` / `event_contract_blocker_errors` / `_git_registration_probe` / `_write_artifacts_via_sink` / `_append_error_log_via_sink`

**`_gateway_dispatch`**：`_parse_args` / `_read_payload` / `_payload_cwd` / `_environment_cwd` / `_original_cwd` / `_path_within_repo` / `_discover_cwd` / `_require_env` / `_canonicalize_cmux_refs` / `_execute_delegate_via_facade` / `_delegate_codex` / `_delegate_claude` / `_should_noop_for_external_context` / `_delegate_noop_response` / `_build_degraded_package_with_error` / `_build_factory_hook_output` / `_execute_delegate` / `_record_project_lifecycle_event` / `_emit_fast_path_metrics` / `_record_event_log_minimal` / `_get_host_delegate`

**`_gateway_handlers`**：`main` / `_handle_source_repo_check` / `_handle_pretooluse_guard` / `_handle_session_start_setup` / `_handle_prompt_submit_logging` / `_handle_integrity_check` / `_write_artifacts_and_emit_metrics` / `_compute_exit_code` / `_dispatch_output` / `_gateway_excepthook` / `HookTimeoutError`

**`_gateway_artifacts`**：`write_artifacts` / `append_error_log` / `_ensure_artifact_dirs` / `_build_readonly_source_repo_package` / `_launch_async_health_check` / `_inject_health_alert` / `_update_state_dynamic_fields`

**`_gateway_telemetry`**：`_maybe_sync_telemetry` / `_write_sync_status` / `_read_last_user_message_from_transcript` / `_log_prompt_submit` / `_sanitize_for_log`

**`hook_runtime_guard`**：`install_guard` / `gateway_main`

---

*文档基于代码实际阅读整理；行数与模块名为 2026-09-05 实测，对应 v0.45.6（commit `6ac1cdb`）。接口签名以源码为准。*
