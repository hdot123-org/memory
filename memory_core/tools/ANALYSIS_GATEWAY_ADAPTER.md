# Gateway 门面与 Adapter 适配器机制分析报告

## 一、Gateway 作为门面：函数功能分组

Gateway 模块共 **69 个函数**（约 68 个），按功能可分为 **10 个功能组**：

### 1. Adapter 配置加载（2 个）
| 函数 | 作用 |
|------|------|
| `load_adapter_config` | 将 Runtime Profile 注入到 `_adapter_config` 字典 + globals() |
| `_apply_artifact_compaction` | 按 Adapter 的压缩策略裁剪 context package 的 sections |

### 2. 策略门面 IF-5（7 个）
| 函数 | 作用 |
|------|------|
| `_resolve_route_target_via_policy` | 通过 RouteTargetPolicy 解析路由目标 |
| `_write_targets_via_policy` | 通过 WriteTargetPolicy 获取写入目标 |
| `_get_policy_pack_via_registry` | 通过 PolicyRegistry 获取策略包 |
| `_resolve_policy_conflict_via_registry` | 通过 PolicyRegistry 解决策略冲突 |
| `_write_artifacts_via_sink` | 通过 ArtifactSink 写入制品 |
| `_append_error_log_via_sink` | 通过 ErrorSink 记录错误 |
| `_execute_delegate_via_facade` | 通过 HostDelegate 执行委托 |

### 3. 接口实例工厂（6 个）
| 函数 | 作用 |
|------|------|
| `_build_gateway_business_policy` | 构建 GatewayBusinessPolicy 实例 |
| `_get_gateway_business_policy` | 获取业务策略（不缓存，支持热替换） |
| `_get_policy_registry` | 获取 PolicyRegistry 单例 |
| `_get_route_policy` | 获取 RouteTargetPolicy 单例 |
| `_get_write_policy` | 获取 WriteTargetPolicy 单例 |
| `_get_artifact_sink` | 获取 ArtifactSink 实例 |
| `_get_error_sink` | 获取 ErrorSink 实例 |
| `_get_host_delegate` | 获取 HostDelegate 实例 |

### 4. Core Builder 解析（2 个）
| 函数 | 作用 |
|------|------|
| `_load_external_core_builder` | 从外部模块加载 Core 构建器 |
| `_resolve_core_builder` | 解析 provider（external-core vs legacy），支持 fallback |

### 5. CWD 发现与路径工具（8 个）
| 函数 | 作用 |
|------|------|
| `_payload_cwd` | 从 payload 提取 cwd |
| `_environment_cwd` | 从环境变量 PWD 提取 cwd |
| `_path_within_repo` | 检查路径是否在 repo 内 |
| `_discover_cwd` | 综合判定最终 cwd（payload > env > repo root） |
| `_should_noop_for_external_context` | 判断是否应在外部上下文 noop |
| `_path_is_under` | 检查路径是否在根目录下 |
| `_classify_truth_ref` | 分类 truth reference 的类型 |
| `_existing_paths` | 过滤存在的 Path 列表 |

### 6. Truth Basis 校验（5 个）
| 函数 | 作用 |
|------|------|
| `_truth_basis_sections_for` | 解析 truth basis 文件的 sections |
| `_truth_basis_errors_for` | 校验 truth basis 的完整性和一致性 |
| `_authority_ref_allowed` | 检查 authority ref 是否在允许路径中 |
| `_lower_evidence_ref` | 检查是否为下层证据引用 |
| `_normalize_repo_scope_entry` | 规范化 repo scope 路径 |

### 7. Git Registration Probe（4 个）
| 函数 | 作用 |
|------|------|
| `_registration_payload_paths` | 从 payload 提取 registration paths |
| `_git_name_only` | 运行 git 命令获取文件名 |
| `_path_matches_scope` | 匹配路径与 scope |
| `_git_registration_probe` | 探测 git 注册状态（pending/committed-coupled 等） |

### 8. 文本/JSON 解析工具（4 个）
| 函数 | 作用 |
|------|------|
| `_extract_excerpt` | 从文件提取前 N 行非空文本 |
| `_section_bullets` | 从 markdown 提取列表项 |
| `_section_body` | 从 markdown 提取 section 正文 |
| `_markdown_code_tokens` / `_json_string_values` / `_json_object_keys` | 解析 markdown code token、JSON 值/键 |

### 9. Gateway 公开 API（10 个）
| 函数 | 作用 |
|------|------|
| `determine_project_scope` | 根据 cwd 决定项目 scope |
| `governance_frozen_tuple_blocker_errors` | 治理冻结元组阻断检查 |
| `event_contract_blocker_errors` | 事件契约阻断检查 |
| `project_map_refs` | 获取 project-map 引用路径 |
| `validate_project_map_files` | 验证 project-map 文件 |
| `validate_unique_legal_system_contract` | 验证唯一合法系统契约 |
| `decision_refs_for_scope` | 获取决策引用 |
| `lesson_refs_for_scope` | 获取经验引用 |
| `docs_refs_for_scope` | 获取文档引用 |
| `truth_basis_for_scope` | 获取事实基准包 |
| `write_targets` | 获取写入目标（含 fallback） |
| `resolve_route_target` | 解析路由目标（含 fallback） |
| `read_text_if_exists` | 安全读取文件 |
| `build_context_package` | **核心入口**：构建 context package |
| `build_context_package_simple` | 简化入口：3 参数调用，支持 schema 转换 |
| `append_error_log` | 追加错误日志 |
| `write_artifacts` | 写入 artifacts |
| `now_iso` | 获取当前 ISO 时间 |

### 10. 委托与 CLI 入口（5 个）
| 函数 | 作用 |
|------|------|
| `_parse_args` | 解析 CLI 参数（--host, --event, --no-delegate） |
| `_read_payload` | 读取 stdin 为 JSON payload |
| `_delegate_noop_response` | 委托的 noop 响应 |
| `_delegate_codex` / `_delegate_claude` | 分别执行 Codex/Claude 委托 |
| `main` | **程序入口**：完整触发链 |

---

## 二、Adapter 是什么？Neutral vs Workbot 的区别

### Adapter 的定义

Adapter（适配器）是 **项目级别的配置与策略抽象层**。它负责：
1. **Runtime Profile**：将项目特定的路径、策略、策略类等全部打包为一个 dict
2. **Business Policy**：实现项目特定的业务规则（如合法性来源、注册策略）
3. **解耦 Gateway Core**：Gateway 代码不硬编码任何项目路径或策略

### Neutral Adapter（中性适配器）

文件：`neutral_policy.py`

```
NeutralGatewayBusinessPolicy → GatewayBusinessPolicyImpl
```

- **定位**：宿主无关的默认业务策略基类
- **特点**：
  - 无任何项目特定路径绑定
  - 从 `.memory/adapter.toml` 读取配置
  - 适用于新项目快速接入
- **Runtime Profile**：`default_runtime_profile.py` 从 `adapter.toml` 构建通用配置

### Workbot Adapter（Workbot 专用适配器）

文件：`workbot_policy.py` + `workbot_runtime_profile.py`

```
WorkbotGatewayBusinessPolicy → NeutralGatewayBusinessPolicy → GatewayBusinessPolicyImpl
```

- **定位**：当前项目的具体业务策略实现
- **特点**：
  - 继承 Neutral，注入 Workbot 特定策略覆盖
  - 定义 3 个 scope：`workbot`、`AEdu`、`platform-capabilities`
  - 注入 `ADAPTER_POLICIES`（合法性来源、注册策略等）
  - 从 policy-pack JSON 文件动态加载策略
  - scope 继承关系：`AEdu → workbot`，`platform-capabilities → workbot`

### 两者的继承链

```
GatewayBusinessPolicy (ABC接口)
  ↑
GatewayBusinessPolicyImpl (基础实现，在 memory_hook_impls.py)
  ↑
NeutralGatewayBusinessPolicy (中性适配)
  ↑
WorkbotGatewayBusinessPolicy (Workbot 适配，注入项目特定策略)
```

---

## 三、Runtime Profile 是什么？它定义了什么？

### 定义

Runtime Profile 是一个 **巨大的 dict**（约 40+ 个键），包含了 Gateway 运行所需的全部配置。由 `_fn(REPO_ROOT, WORKSPACE_ROOT)` 在模块导入时一次性构建。

### 它定义的内容

| 类别 | 键示例 | 含义 |
|------|--------|------|
| **路径配置** | `PROJECT_MAP_ROOT`, `TRUTH_MODEL`, `HOOK_CONTRACT_PATH` | 系统文件路径 |
| **Canonical 文件** | `REQUIRED_CANONICAL`, `GLOBAL_CANONICAL`, `PROJECT_CANONICAL` | 必须存在的规范文件 |
| **策略路径** | `POLICY_PACK_PATH`, `GLOBAL_RULE_PATH` | 策略文件位置 |
| **策略值** | `LEGALITY_SOURCE_POLICY`, `REGISTRATION_COMMIT_POLICY` | 策略开关值 |
| **Scope 配置** | `DEFAULT_PROJECT_SCOPE`, `POLICY_ALLOWED_SCOPES`, `POLICY_SCOPE_INHERITS` | 项目作用域 |
| **治理** | `GOVERNANCE_FROZEN_TUPLE_FILES`, `EVENT_CONTRACT_FILES`, `FROZEN_TUPLE_EXPECTED` | 治理规则 |
| **事件规范** | `FORMAL_SOURCE_TYPES`, `FORMAL_EVENT_TYPES`, `FORMAL_FIELD_KEYS` | 事件格式 |
| **压缩策略** | `ARTIFACT_COMPACTION` | 制品输出裁剪规则 |
| **策略类** | `GATEWAY_POLICY_CLASS` | 使用的 BusinessPolicy 类 |

### 加载机制

```python
# 模块级别，import 时即执行
_adapter_profile = _fn(REPO_ROOT, WORKSPACE_ROOT)  # 调用 build_workbot_runtime_profile
load_adapter_config(_adapter_profile)               # 注入 _adapter_config + globals()
```

Adapter Registry 支持通过 `MEMORY_HOOK_ADAPTER` 环境变量切换（当前只注册了 `workbot`）。

---

## 四、Policy-pack 是什么？如何热切换？

### Policy-pack 定义

Policy-pack 是一个 **JSON 文件**（位于 `memory/kb/global/memory-hook-policy-pack.json`），定义了：

```json
{
  "schema_version": "m3-policy-pack-v1",
  "scope": "default",
  "policies": {
    "legality_source": "active-legal-map-only",
    "registration_commit": "required-after-absorption-complete",
    ...
  },
  "conflict_strategies": {
    "legality_source": "fail-fast",
    "registration_commit": "preserve-and-escalate",
    ...
  },
  "adapter_scope": true
}
```

- **schema_version**：版本标识，支持未来升级
- **policies**：键值对策略，如合法性来源、注册阶段、KB 写入模式
- **conflict_strategies**：每个策略冲突时的解决策略（fail-fast / prefer-strict / preserve-and-escalate）
- **adapter_scope**：标记是否由 adapter 管理

### 热切换机制

Policy-pack 支持 **3 层解析优先级**：

```
1. Adapter 硬编码策略 (ADAPTER_POLICIES dict)     ← 最高优先级
2. Policy-pack JSON 文件内容
3. PolicyRegistryImpl.DEFAULT_POLICIES 内置默认值   ← 最低优先级
```

**热切换方式：**
1. **修改 JSON 文件**：直接编辑 `memory-hook-policy-pack.json`，下次 Gateway 调用时自动生效（每次运行时重新读取）
2. **环境变量覆盖**：`MEMORY_HOOK_POLICY_PACK_PATH` 指向不同的 JSON 文件
3. **Adapter 切换**：`MEMORY_HOOK_ADAPTER=neutral` 切换到中性策略（无需改代码）
4. **Core Provider 切换**：`MEMORY_HOOK_EXTERNAL_CORE_MODULE` 切换 Core 构建器

**关键设计点**：Gateway 中的 `_get_gateway_business_policy()` **不缓存**，每次都新建实例，确保策略修改后立即生效。

---

## 五、完整调用链：宿主触发 → Gateway → Adapter → Core → 写入

```
┌─────────────────────────────────────────────────────────────────────┐
│ 宿主（Codex / Claude）触发                                          │
│   cmux codex-hook <event>  或  Claude hook 脚本                      │
│   stdin 传入 raw_payload (JSON)                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 1. main() — CLI 入口                                                │
│    - _parse_args()：解析 --host, --event, --no-delegate             │
│    - sys.stdin.read()：读取 raw_payload                             │
│    - _read_payload()：解析为 dict                                   │
│    - _discover_cwd()：确定当前工作目录                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Noop 判断                                                        │
│    - _should_noop_for_external_context()                            │
│      如果 cwd 不在 repo 内且无 FORCE 环境变量 → 直接 noop 返回        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. build_context_package(host, event, payload)                      │
│    ┌──────────────────────────────────────────────────────────────┐ │
│    │ a) _discover_cwd(payload) → cwd                              │ │
│    │ b) determine_project_scope(cwd) → project_scope               │ │
│    │    通过 _get_gateway_business_policy().determine_project_scope│ │
│    │    → WorkbotAdapter 根据 SCOPE_MATCH_HINTS 匹配路径           │ │
│    │                                                              │ │
│    │ c) 构建 CoreConfig（传入 business_policy 所有配置函数引用）     │ │
│    │                                                              │ │
│    │ d) _resolve_core_builder() → 选择 Core 构建器                 │ │
│    │    "legacy" → build_context_package_core                     │ │
│    │    "external-core" → 外部模块（支持 fallback）                 │ │
│    │                                                              │ │
│    │ e) build_context_package_from_config(config)                  │ │
│    │    → 调用 Core 逻辑，组装 system/project/task context        │ │
│    │    → 执行 policy 校验                                        │ │
│    │    → 执行 governance / event contract 检查                   │ │
│    │    → 执行 git registration probe                             │ │
│    │                                                              │ │
│    │ f) _apply_artifact_compaction(package)                       │ │
│    │    按 Adapter 压缩策略裁剪输出 sections                        │ │
│    └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. ArtifactWriter.write(host, event, package)                       │
│    - 写入 JSON snapshot 到 artifacts/memory-hook/contexts/           │
│    - 更新 latest-<host>-<event>.json 符号链接                        │
│    - 追加到 events.jsonl 事件日志                                    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. 状态检查与委托执行                                                │
│    - package["status"] != "ok" → 记录错误日志，返回 exit code 1     │
│    - args.no_delegate → 仅输出 JSON，不调用宿主                     │
│    - 否则执行委托：                                                 │
│      _delegate_codex(event, raw_payload)                            │
│        → cmux codex-hook <event> < raw_payload                      │
│      或 _delegate_claude(event, raw_payload, payload)               │
│        → cmux claude-hook + state recording                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 6. 结果输出                                                         │
│    - 委托 stdout → sys.stdout                                      │
│    - 委托 stderr → sys.stderr                                      │
│    - 返回 delegate returncode                                      │
│    - 失败时通过 _append_error_log_via_sink() 记录错误               │
└─────────────────────────────────────────────────────────────────────┘
```

### 调用链中的接口交互

```
Gateway 门面
  ├── HostDelegate (IF-1) → CodexDelegate / ClaudeDelegate → cmux 命令
  ├── PolicyRegistry (IF-2) → PolicyRegistryImpl → 策略查询/校验/冲突解决
  ├── RouteTargetPolicy (IF-3a) → RouteTargetPolicyImpl → 路由路径解析
  ├── WriteTargetPolicy (IF-3b) → WriteTargetPolicyImpl → 写入路径解析
  ├── ArtifactSink (IF-4a) → ArtifactSinkImpl → 文件写入
  ├── ErrorSink (IF-4b) → ErrorSinkImpl → 错误日志
  └── GatewayBusinessPolicy → WorkbotGatewayBusinessPolicy → 业务规则
        └── 继承 NeutralGatewayBusinessPolicy → GatewayBusinessPolicyImpl
```

### 关键设计模式总结

1. **Facade Pattern（门面模式）**：Gateway 作为统一入口，内部通过 IF-1~IF-6 接口调用各子系统
2. **Adapter Pattern（适配器模式）**：不同项目通过实现自己的 Runtime Profile + Business Policy 接入
3. **Strategy Pattern（策略模式）**：Policy-pack 支持运行时策略切换
4. **Dependency Injection（依赖注入）**：CoreConfig 传入所有策略函数引用，Core 不直接依赖 Gateway
