# A2: Gateway 分析

**文件**: `workspace/tools/memory_hook_gateway.py`（1028 行，68 个函数）
**角色**: M2 IF-5 Gateway Facade —— 记忆系统的外部入口，协调策略、核心构建器、Artifact 写入和 Host Delegate 执行。

---

## 一、函数清单

### Public 函数（16 个）

| # | 函数名 | 参数 | 返回值 | 职责 |
|---|--------|------|--------|------|
| 1 | `now_iso()` | 无 | `str` | 生成带时区的 ISO 8601 时间戳 |
| 2 | `determine_project_scope(cwd)` | `cwd: Path` | `str` | 根据当前工作目录判定项目作用域（如 `workbot` / `AEdu`） |
| 3 | `governance_frozen_tuple_blocker_errors()` | 无 | `list[str]` | 检查治理冻结元组合规性，返回 blocker 错误列表 |
| 4 | `event_contract_blocker_errors()` | 无 | `list[str]` | 检查事件契约合规性，返回 blocker 错误列表 |
| 5 | `project_map_refs()` | 无 | `list[str]` | 获取 project-map 的引用路径列表 |
| 6 | `read_text_if_exists(path)` | `path: Path` | `str` | 安全读取文件内容，不存在时返回空字符串 |
| 7 | `validate_project_map_files()` | 无 | `list[str]` | 验证 project-map 文件列表，返回错误列表 |
| 8 | `validate_unique_legal_system_contract()` | 无 | `list[str]` | 验证 legal-system 契约唯一性，返回错误列表 |
| 9 | `decision_refs_for_scope(project_scope)` | `project_scope: str` | `list[str]` | 获取指定项目作用域的决策文档引用 |
| 10 | `lesson_refs_for_scope(project_scope)` | `project_scope: str` | `list[str]` | 获取指定项目作用域的经验教训引用 |
| 11 | `docs_refs_for_scope(project_scope)` | `project_scope: str` | `list[str]` | 获取指定项目作用域的文档引用 |
| 12 | `truth_basis_for_scope(project_scope)` | `project_scope: str` | `dict[str, Any]` | 获取指定项目作用域的真实性基础数据 |
| 13 | `write_targets()` | 无 | `dict[str, Any]` | 获取所有写入目标路径映射（含 fallback 默认值） |
| 14 | `resolve_route_target(kind)` | `kind: str` | `str` | 根据路由种类解析目标路径 |
| 15 | `build_context_package(host, event, payload)` | `host: str, event: str, payload: dict` | `dict[str, Any]` | **核心入口**：构建完整的上下文包（context package） |
| 16 | `build_context_package_simple(host, event, payload)` | `host, event, payload` + `adapter?` | `dict[str, Any]` | 简化版入口：调用 `build_context_package` 后转为 v1 格式 |
| 17 | `append_error_log(component, message, context)` | `component, message, context` | `None` | 追加错误日志（带 fallback） |
| 18 | `write_artifacts(package)` | `package: dict` | `dict[str, str]` | 写入 artifact 文件（带 fallback） |
| 19 | `main()` | 无 | `int` | CLI 入口：解析参数、构建上下文、执行 delegate |

### Private 函数（52 个）

**构造器 / 工厂（10 个）**

| # | 函数名 | 返回值 | 职责 |
|---|--------|--------|------|
| 20 | `_build_gateway_business_policy()` | `GatewayBusinessPolicy` | 实例化 Gateway 业务策略对象 |
| 21 | `_get_gateway_business_policy()` | `GatewayBusinessPolicy` | 获取 Gateway 业务策略（无单例，每次新建） |
| 22 | `_load_external_core_builder()` | `CoreBuilder` | 从环境变量指定的外部模块加载核心构建器 |
| 23 | `_resolve_core_builder(provider, allow_fallback)` | `tuple[str, CoreBuilder, list[str]]` | 解析核心构建器提供者，支持 fallback |
| 24 | `_get_policy_registry()` | `PolicyRegistry` | 获取策略注册表（单例） |
| 25 | `_get_route_policy()` | `RouteTargetPolicy` | 获取路由策略（单例） |
| 26 | `_get_write_policy()` | `WriteTargetPolicy` | 获取写入策略（单例） |
| 27 | `_get_artifact_sink()` | `ArtifactSink` | 获取 Artifact 写入器（无单例） |
| 28 | `_get_error_sink()` | `ErrorSink` | 获取错误日志写入器（无单例） |
| 29 | `_get_host_delegate(host)` | `HostDelegate` | 根据 host 名称获取对应的代理执行器 |

**IF-5 Facade 包装器（7 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 30 | `_resolve_route_target_via_policy(kind)` | 通过策略解析路由目标 |
| 31 | `_write_targets_via_policy()` | 通过策略获取写入目标 |
| 32 | `_get_policy_pack_via_registry(scope)` | 通过注册表获取策略包 |
| 33 | `_resolve_policy_conflict_via_policy(policy_key, values, strategy)` | 通过注册表解决策略冲突 |
| 34 | `_write_artifacts_via_sink(package)` | 通过 Sink 写入 artifact |
| 35 | `_append_error_log_via_sink(component, message, context)` | 通过 Sink 记录错误 |
| 36 | `_execute_delegate_via_facade(host, event, raw_payload, payload)` | 通过 Facade 执行 Host Delegate |

**CLI & 参数解析（2 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 37 | `_parse_args()` | 解析命令行参数（`--host`, `--event`, `--no-delegate`） |
| 38 | `_read_payload(raw_payload)` | 从 stdin 读取并解析 JSON payload |

**路径与工作目录（5 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 39 | `_payload_cwd(payload)` | 从 payload 提取 cwd |
| 40 | `_environment_cwd()` | 从 `$PWD` 环境变量提取 cwd |
| 41 | `_path_within_repo(path)` | 判断路径是否在仓库根目录内 |
| 42 | `_discover_cwd(payload)` | 综合 payload 和环境变量发现当前 cwd |
| 43 | `_path_is_under(path, root)` | 判断路径是否在指定根目录下 |

**No-op & 控制流（2 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 44 | `_should_noop_for_external_context(payload)` | 判断是否因外部上下文而跳过 hook |
| 45 | `_delegate_noop_response(host)` | 执行 delegate 的 no-op 响应 |

**Markdown & JSON 解析辅助（7 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 46 | `_extract_excerpt(path, max_lines)` | 从文件提取摘要行（跳过空行） |
| 47 | `_section_bullets(text, heading)` | 从 Markdown 提取指定标题下的列表项 |
| 48 | `_section_body(text, heading)` | 从 Markdown 提取指定标题下的正文内容 |
| 49 | `_markdown_code_tokens(text)` | 提取 Markdown 中的内联代码标记 |
| 50 | `_json_string_values(text, key)` | 从文本中提取指定 JSON key 的字符串值 |
| 51 | `_json_object_keys(text)` | 从文本中提取所有 JSON object key |
| 52 | `_existing_paths(paths)` | 过滤出实际存在的路径 |

**Truth Basis 验证（6 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 53 | `_classify_truth_ref(path)` | 对 truth 引用的路径分类（legal-core、project-canonical 等 15 类） |
| 54 | `_authority_ref_allowed(path)` | 判断 authority ref 是否在允许路径集中 |
| 55 | `_lower_evidence_ref(path)` | 判断路径是否属于 lower evidence root |
| 56 | `_truth_basis_sections_for(path)` | 解析 truth 文件的四个 section（source/authority/evidence/conflict） |
| 57 | `_truth_basis_errors_for(path)` | **验证 truth basis 文件完整性**，返回错误列表 |
| 58 | `_normalize_repo_scope_entry(value)` | 将路径标准化为相对于 REPO_ROOT 的 POSIX 路径 |

**Git & 注册探测（4 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 59 | `_registration_payload_paths(payload)` | 从 payload 提取并标准化 registration_paths |
| 60 | `_git_name_only(*args)` | 执行 git 命令并返回名称列表 |
| 61 | `_path_matches_scope(candidate, scope_entry)` | 判断路径是否匹配 scope 条目 |
| 62 | `_git_registration_probe(event, payload)` | **Git 注册状态探测**：检查项目 map 的 git 状态和提交历史 |

**Artifact & Delegate（4 个）**

| # | 函数名 | 职责 |
|---|--------|------|
| 63 | `_apply_artifact_compaction(package)` | 根据 adapter 的压缩策略裁剪 context package 的 sections |
| 64 | `_require_env(name)` | 获取环境变量，缺失时抛出 RuntimeError |
| 65 | `_canonicalize_cmux_refs(workspace_ref, surface_ref)` | 通过 `cmux identify` 命令规范化 cmux 引用 |
| 66 | `_delegate_codex(event, raw_payload)` | 执行 Codex delegate |
| 67 | `_delegate_claude(event, raw_payload, payload)` | 执行 Claude delegate |

---

## 二、`build_context_package()` 执行流程图

```
build_context_package(host, event, payload)
│
├─ 1. _discover_cwd(payload)           → cwd
│   ├─ 优先取 payload["cwd"]（若在 repo 内）
│   ├─ 其次取 $PWD（若在 repo 内）
│   ├─ 再次取 $PWD（任意）
│   ├─ 再次取 payload["cwd"]（任意）
│   └─ 兜底 → REPO_ROOT
│
├─ 2. determine_project_scope(cwd)     → project_scope
│   └─ 委托 GatewayBusinessPolicy.determine_project_scope()
│
├─ 3. _get_gateway_business_policy()   → business_policy
│
├─ 4. 构建 CoreConfig（约 30+ 字段）
│   ├─ 直接赋值基本参数
│   ├─ 注入 business_policy 提供的各种路径/引用
│   ├─ 注入函数回调（policy_validate、get_policy_pack、git_probe 等）
│   └─ 注入环境变量（surface_id、workspace_id）
│
├─ 5. _resolve_core_builder(provider)  → (provider_name, builder, errors)
│   ├─ 默认 provider = "legacy"
│   ├─ 若 "external-core" → 尝试动态加载外部模块
│   ├─ 失败则 fallback 到 legacy
│   └─ 返回 (名称, 构建器, 错误列表)
│
├─ 6. build_context_package_from_config(config) → package
│   └─ 调用 core 模块完成实际构建
│
├─ 7. 注入 provider 元信息到 system_context
│   ├─ system_context["core_provider"] = provider_name
│   ├─ system_context["core_provider_requested"] = requested_provider
│   └─ 如有 fallback errors → system_context["core_provider_fallback_errors"]
│
├─ 8. 处理 provider errors（如果有）
│   ├─ 追加到 package["validation_errors"]
│   └─ 若状态为 "ok" → 降级为 "degraded"
│
├─ 9. Shadow Run（如果 MEMORY_HOOK_SHADOW_RUN 环境变量设置）
│   ├─ 使用对侧 provider 构建 shadow_package
│   ├─ 比对结果
│   └─ 将 shadow_result 写入 system_context["shadow_run"]
│
├─ 10. _apply_artifact_compaction(package)
│    └─ 按 adapter 的 ARTIFACT_COMPACTION 策略裁剪 sections
│
└─ 11. return package
```

**关键决策点**：
- Step 5 的 provider 解析支持热插拔核心构建器，失败自动 fallback
- Step 9 的 shadow run 是双轨对比模式，用于 provider 迁移验证
- 整个流程无状态依赖（除全局单例 policy registry），可重复调用

---

## 三、错误处理分析

### 异常类型与捕获策略

| 异常类型 | 捕获位置 | 策略 | 日志记录 |
|----------|---------|------|---------|
| `ImportError` | 文件顶部 try/except 块 | 相对导入失败 → 回退到绝对导入 | 无（静默回退） |
| `ImportError` | `_ADAPTER_REGISTRY` 加载 | `importlib.import_module` 失败 → 直接导入 fallback | 无 |
| `TypeError` | `_load_external_core_builder()` | 外部构建器不可调用 → 抛出 | 无 |
| `Exception` | `_resolve_core_builder()` | 外部模块加载失败 → fallback 到 legacy | 错误写入 `provider_errors` 列表 |
| `ValueError` | `resolve_route_target()` fallback | 不支持的 route kind → 重新抛出（带链式异常） | 无 |
| `RuntimeError` | `_ensure_artifact_dirs()` / `append_error_log()` / `write_artifacts()` | Sink 失败 → 执行裸文件系统 fallback | 无 |
| `json.JSONDecodeError` | `_read_payload()` | JSON 解析失败 → 返回空 dict | 无 |
| `KeyError` | `resolve_route_target()` | route kind 不在 map 中 → 转为 `ValueError` | 无 |
| `RuntimeError` | `_require_env()` | 环境变量缺失 → 抛出 | 无 |
| `json.JSONDecodeError` | `_canonicalize_cmux_refs()` | cmux 命令输出非 JSON → 返回原始引用 | 无 |

### 错误处理模式总结

**优点**：
- 三重防护：策略调用 → `except Exception` → 硬编码默认值（`write_targets`、`resolve_route_target`）
- Fallback 链设计明确：策略失败 → 默认值 → 文件系统直接操作
- Provider 错误不中断流程，而是标记为 `degraded` 状态

**缺点**：
- 多处 `except Exception` 吞掉了具体异常类型，调试信息有限
- `_read_payload()` 解析失败时静默返回 `{}`，调用方无法区分"空 payload"和"无效 JSON"
- `subprocess.run` 调用均 `check=False`，但错误检查依赖返回值，无统一异常包装
- 缺少集中式的错误日志记录机制，错误分散在 `print(file=sys.stderr)` 和 `append_error_log()` 两种路径

---

## 四、耦合分析

### 直接依赖模块

| 模块 | 依赖类型 | 说明 |
|------|---------|------|
| `memory_hook_core` | 核心依赖 | 上下文包构建逻辑 |
| `memory_hook_config` | 配置依赖 | `CoreConfig` 数据类 |
| `memory_hook_interfaces` | 接口依赖 | 7 个 Protocol/ABC 接口 |
| `memory_hook_impls` | 实现依赖 | 10 个实现类 |
| `memory_hook_schema` | 格式转换依赖 | `convert_to_v1` |
| `memory_hook_adapters.workbot_runtime_profile` | 适配器依赖 | 运行时配置注入 |
| `memory_hook_adapters.workbot_policy` | 策略适配器依赖 | `WorkbotGatewayBusinessPolicy` |
| `cmux_hook_state` | 外部依赖 | Claude hook 状态管理 |

### 标准库依赖

| 模块 | 用途 |
|------|------|
| `argparse` | CLI 参数解析 |
| `json` | 序列化/反序列化 |
| `os` | 环境变量、路径操作 |
| `re` | Markdown/JSON 文本正则解析 |
| `shutil` | `which()` 命令查找 |
| `subprocess` | 外部命令执行（git、cmux） |
| `sys` | 路径注入、stdin/stdout/stderr、退出 |
| `datetime` | 时间戳生成 |
| `pathlib.Path` | 路径操作 |
| `importlib` | 动态模块导入 |

### 耦合问题

**合理耦合**：
- 通过 Interface Protocol（`ArtifactSink`、`HostDelegate` 等）实现依赖倒置
- Adapter 模式解耦了运行时配置注入（`globals().update()`）
- 双 import 策略（relative → absolute）支持包模式和脚本模式

**值得关注的耦合**：
1. **cmux 外部命令**：`_canonicalize_cmux_refs()` 硬依赖 `cmux` CLI 二进制文件存在，若缺失则静默降级。这在无 cmux 环境中可能产生混淆行为
2. **动态 `globals().update()` 注入**：适配器将 40+ 个常量注入全局命名空间，这些常量的来源不透明，IDE 和 linter 无法静态分析
3. **Markdown 解析耦合**：`_section_bullets`、`_truth_basis_sections_for` 等函数直接解析 Markdown 文本结构，与文档格式强绑定
4. **Git 命令耦合**：`_git_registration_probe()` 和 `_git_name_only()` 直接调用 `git` 命令，而非使用 git 库

---

## 五、复杂度热点

### Top 5 最长函数

| 函数 | 行数 | 复杂度评估 |
|------|------|-----------|
| `build_context_package()` | 84 | **高**：核心编排函数，组装 30+ 字段的 Config，处理 provider 解析/注入/shadow run/compaction 四个子流程 |
| `main()` | 78 | **中高**：包含 noop 判断、构建、写入、delegate 执行、错误处理、stdout/stderr 转发等多个分支 |
| `_git_registration_probe()` | 50 | **中**：多次 git 调用 + 状态判定逻辑 |
| `_truth_basis_errors_for()` | 44 | **中**：解析 Markdown sections + 验证多个约束条件 |
| `_build_gateway_business_policy()` | 41 | **低**：纯构造器，只是参数很多（26 个 config 字段） |

### 其他复杂度观察

1. **`_classify_truth_ref()`**（34 行，15 个 if-elif 分支）：路径分类函数，分支多但每个分支简单。可考虑用查找表替代
2. **`_truth_basis_errors_for()`** 中有 3 行超长列表推导式（解析 source/authority/evidence paths），可读性差
3. **重复的路径检查逻辑**：`_path_within_repo()` 和 `_path_is_under()` 本质相同，但实现分散
4. **`_discover_cwd()`** 的 6 层 fallback 优先级链逻辑正确，但可读性一般

### Cyclomatic 复杂度估计（定性）

- `main()`: ~12 个分支（host 选择、noop、write_ok、status、no_delegate、delegate try/except、returncode、stdout/stdout）
- `build_context_package()`: ~8 个分支（provider 选择、errors、shadow run、compaction）
- `_git_registration_probe()`: ~8 个分支（status 4 种 + 多个 boolean 判定）
- `_classify_truth_ref()`: 15 个分支（直接计数）

---

## 六、代码质量评分

### 评分：**7 / 10**

### 理由

**做得好的方面（+）**：

1. **分层清晰**：Gateway 作为 Facade 层，职责边界明确——不直接实现业务逻辑，而是协调 Policy、Core、Sink、Delegate
2. **接口驱动设计**：通过 Protocol 接口（`ArtifactSink`、`HostDelegate`、`PolicyRegistry` 等）实现依赖倒置
3. **Adapter 模式**：运行时配置通过 adapter profile 动态注入，支持多项目（workbot / AEdu / platform-capabilities）
4. **Fallback 链**：关键路径均有降级策略（策略失败 → 默认值 → 文件系统直写）
5. **Provider 热插拔**：`_resolve_core_builder()` 支持外部核心构建器加载 + 自动 fallback + shadow run 双轨对比
6. **单一入口**：`__all__` 明确导出 4 个符号，内部函数命名规范

**需要改进的方面（-）**：

1. **全局命名空间污染**：`globals().update(_fn(...))` 注入 40+ 个常量，静态分析工具无法追踪，IDE 无自动补全，测试时 monkeypatch 困难
2. **双 import 策略**：文件顶部两层 try/except（relative → absolute），加上 adapter 的第三层 fallback，使导入路径难以追踪。建议统一为一种策略
3. **静默错误**：`_read_payload()` 在 JSON 解析失败时返回 `{}`，调用方无法区分"用户给了空 payload"和"用户给了无效 JSON"——这在调试时容易造成误导
4. **`except Exception` 过宽**：多处使用 `except Exception` 吞掉所有异常类型，应改为更精确的异常处理
5. **Markdown 解析脆弱**：`_section_bullets()` 和 `_truth_basis_errors_for()` 直接解析 Markdown 文本，对格式变化敏感
6. **函数过多**：68 个函数中约 12 个是 IF-5 Facade 包装器（如 `_resolve_route_target_via_policy`），这些函数体只有一行调用，可以内联或用 `functools.partial` 替代
7. **常量散列**：40+ 个全局常量通过 `globals().update()` 注入，缺乏统一的常量配置类或 dataclass

---

## 七、总结

`memory_hook_gateway.py` 是整个记忆系统的**中央调度器**，它的设计思路正确：通过接口抽象、策略模式和适配层实现可扩展性。主要问题在于**过度间接**——IF-5 Facade 包装器、全局常量注入、双 import 策略等机制增加了理解成本，但带来的收益（主要是测试时的 monkeypatch 能力）与代价不完全匹配。

核心函数 `build_context_package()` 的执行流程清晰，但 84 行的长度和多个子流程可以进一步拆分。整体代码质量良好，值得在此基础上做渐进式改进。
