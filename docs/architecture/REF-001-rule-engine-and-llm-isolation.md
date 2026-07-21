---
type: "[DOC:ARCHITECTURE]"
title: "规则引擎统一与 LLM 隔离设计"
shortname: REF-001
status: 可评审
scope: default
created: 2026-07-16
updated: 2026-07-16
source: architecture-audit-ref-000
confidence: high
tags: [rule-engine, llm-isolation, refactoring, architecture]
related: [DES-001, DES-004, DES-007, DES-011, REF-000]
---

> 文档编号：REF-001 | 基于 REF-000 的 157 项审计发现

# 规则引擎统一与 LLM 隔离设计

## 1. 问题陈述

memory-core 当前有三种职责纠缠在一起：

1. **确定性规则判断**（路径所有权、工具拦截、业务策略、文档分类）- 6 种互不兼容的规则模式散落 9 个文件，无统一抽象。
2. **LLM 推理**（每日总结分类）- 仅 1 处调用，但与确定性逻辑共享模块空间。
3. **Hook 编排**（事件路由、adapter 解析、context package 组装）- 已有较好的接口层（8 ABC + 3 Protocol），但实现层双轨并存。

目标：让规则引擎干规则引擎的事，LLM 干 LLM 的事，两者彻底解耦。

## 2. 设计原则

### 2.1 演进而非重建

**不新建 rule_engine/ 包另起炉灶。** 现有 `memory_hook_interfaces.py` 的 PolicyRegistry / GatewayBusinessPolicy / RouteTargetPolicy / WriteTargetPolicy 已经是规则抽象的雏形。规则引擎统一是**收敛这些分散实现**，不是创建第二套并行体系。

### 2.2 LLM 完全可选

`pip install memory-core` 不安装任何 LLM 依赖。LLM 功能通过 `memory-core[llm]` 可选安装。核心系统在无 LLM 时通过确定性降级正常工作。

### 2.3 零破坏兼容

所有现有导入路径（`from memory_core.tools.xxx import Y`）、CLI 入口点（16 个 console_scripts）、公共 API（4 个符号）、状态文件格式保持不变。

## 3. 现有架构资产（必须理解再动手）

### 3.1 接口层全貌

```
memory_hook_interfaces.py (390行, 不可删除)
├── HostDelegate(ABC)              — 事件委派（Codex/Claude/Factory/Noop）
├── PolicyRegistry(ABC)            — 策略查询+校验+冲突消解（13个抽象方法）
├── PolicyQueryProvider(Protocol)  — 细粒度策略查询
├── GovernanceChecker(Protocol)    — 治理校验
├── TruthBasisProvider(Protocol)   — 事实基准
├── RouteTargetPolicy(ABC)         — 路由目标解析
├── WriteTargetPolicy(ABC)         — 写入目标解析
├── GatewayBusinessPolicy(ABC)     — 宿主/业务策略（16个抽象方法）
├── ArtifactSink(ABC)              — 产物输出
├── ErrorSink(ABC)                 — 错误日志
├── PathUtils(ABC)                 — 路径工具
├── TruthBasis(TypedDict)          — truth-basis 数据契约
└── RegistrationCommitGate(TypedDict) — 注册门控数据契约
```

### 3.2 配置中枢

```
CoreConfig (memory_hook_config.py, 37字段)
├── 环境(7): host, event, payload, cwd, project_scope, workspace_root, repo_root
├── 路径(7): required_canonical, project_canonical, ...
├── 策略(9): legality_source_policy, registration_commit_policy, ...
├── 回调(13): extract_excerpt_fn, now_iso_fn, validate_project_map_fn, ...
└── 接口(4): policy_registry, path_utils, governance_blocker_scopes, ...
```

### 3.3 双轨业务策略（B-01, 必须消除）

| 路径 | 类 | 状态 |
|------|-----|------|
| memory_hook_impls.py:667 | GatewayBusinessPolicyImpl(1500行) | **生产路径**，marker用硬编码中文 |
| business_policy_checks.py | ProjectMapValidator + 5个类 | **测试路径**，marker用MKR_*常量 |

NeutralGatewayBusinessPolicy 继承旧类 → 生产走旧路径 → marker 修改只更新新类时静默失效。

### 3.4 规则模式现状（B-03, 必须统一）

| 模块 | 规则模式 | 配置来源 |
|------|----------|----------|
| ownership.py | fnmatch + 前缀比较 + 正则 | TOML + 硬编码 |
| denylist.py | 预编译正则列表 | 硬编码常量 |
| pretooluse_guard.py | 正则字面量 + frozenset | 全部硬编码 |
| business_policy_checks.py | 字符串包含 + 正则finditer | _validation_constants.py |
| consistency_check.py | 20+处正则源码扫描 | 硬编码 |
| hook_event.py | 字典映射 + 集合判断 | 模块级常量 |

## 4. 目标设计

### 4.1 不新增顶层包

**不创建 `rule_engine/` 或 `rules/` 新包。** 这会破坏现有导入路径并创建导航混乱。

而是在 `memory_core/tools/` 内部通过**模块合并和接口收敛**实现统一：

```
memory_core/tools/
├── memory_hook_interfaces.py     ← 保持不变（接口层）
├── memory_hook_config.py         ← 保持不变（CoreConfig）
├── business_policy_checks.py     ← 成为唯一业务策略实现（消除双轨）
├── _rule_helpers.py              ← 新文件：提取8个三复制工具函数
├── ownership.py(包顶层)          ← 保持位置（7+模块依赖）
├── denylist.py                   ← 保持位置
├── pretooluse_guard.py           ← 拆分为 guard_classify + guard_metrics
├── daily_summary_generator.py    ← LLM调用提取为可选
└── ... 其余不变
```

### 4.2 消除双轨（解决 B-01）

**策略：旧类委托给新类。**

```python
# memory_hook_impls.py 中的 GatewayBusinessPolicyImpl
# 改为内部委托 business_policy_checks.* 的类

class GatewayBusinessPolicyImpl(GatewayBusinessPolicy):
    """生产路径 — 委托给 business_policy_checks 实现。"""

    def __init__(self, config):
        self._config = config
        self._map_validator = ProjectMapValidator(config)
        self._frozen_checker = FrozenTupleChecker(config)
        self._event_checker = EventContractChecker(config)
        self._truth_resolver = TruthBasisResolver(config)

    def validate_project_map_files(self):
        return self._map_validator.validate_project_map()

    # ... 其余方法委托
```

**效果：** 生产路径和测试路径走同一套代码，marker 修改只需改一处。

### 4.3 提取共享工具函数（解决 B-02）

创建 `_rule_helpers.py`，集中 8 个三复制函数：

```python
# memory_core/tools/_rule_helpers.py

def path_is_under(path: Path, root: Path) -> bool: ...
def path_is_under_lexical(path: str, root: str) -> bool: ...
def section_bullets(content: str, section_header: str) -> list[str]: ...
def section_body(content: str, section_header: str) -> str: ...
def markdown_code_tokens(text: str) -> list[str]: ...
def json_string_values(text: str) -> list[str]: ...
def json_object_keys(text: str) -> list[str]: ...
def existing_paths(paths: list[str], root: Path) -> list[Path]: ...
```

business_policy_checks.py、memory_hook_impls.py、memory_hook_gateway.py 全部改为 `from _rule_helpers import ...`。

### 4.4 规则逻辑与 I/O 分离（解决 B-06）

当前规则函数内嵌 `path.read_text()` 和 `subprocess.run(["git",...])`。

**改造：** 规则函数只接受字符串/数据输入，I/O 由调用方负责。

```python
# 之前（business_policy_checks.py）
def _truth_basis_errors_for(self, scope: str) -> list[str]:
    content = path.read_text()  # I/O 内嵌
    return self._check_markers(content)

# 之后
def _check_markers(self, content: str, scope: str) -> list[str]:  # 纯函数
    return [...]

# I/O 由调用方负责
content = path.read_text()
errors = checker._check_markers(content, scope)
```

### 4.5 LLM 隔离设计

#### 现状

`daily_summary_generator.py` 是唯一 LLM 调用点：
- curl 子进程调 GLM-5.1（非 SDK）
- API Key 从 Factory settings.json 提取
- 失败时降级为纯统计报告（已实现）

#### 改造

**不提取为独立包。** 仅做接口边界明确化：

```python
# daily_summary_generator.py 内部结构（不改变文件位置）

# --- LLM 相关（可选依赖区域）---
def _get_factory_api_key(project_root: str) -> str: ...  # 保持不变
def _call_llm(prompt: str, project_root: str) -> str | None: ...  # 保持不变
def _build_llm_prompt(session_data: list[dict]) -> str: ...  # 保持不变

# --- 确定性区域（零 LLM 依赖）---
def _read_a_layer(project_root: Path, date: str) -> list[dict] | None: ...  # 纯 I/O
def _generate_fallback_report(sessions: list[dict], date: str) -> str: ...  # 纯计算
def _write_daily_log(...) -> Path: ...  # 纯 I/O

# --- 编排 ---
def process_project(...):
    a_sessions = _read_a_layer(...)
    enriched = _enrich_with_b_layer(...)
    # LLM 调用是唯一可选点
    llm_summary = _call_llm(...)  # 返回 None 时降级
    _write_daily_log(..., llm_summary, ...)
```

**隔离措施：**

1. **pyproject.toml 不新增 LLM 依赖。** curl 子进程模式不需要 openai/anthropic SDK。
2. **_call_llm 是唯一 LLM 出口。** 所有 LLM 相关代码集中在 daily_summary_generator.py 的 3 个函数内。
3. **确定性降级路径已存在且完善。** `_generate_fallback_report()` 生成纯统计报告，无需 LLM。
4. **未来可选：** 如果需要 SDK 模式，添加 `[project.optional-dependencies] llm = ["openai>=1.0"]`，_call_llm 内检测 SDK 可用性。

### 4.6 pretooluse_guard 拆分（解决 B-07/C-08）

当前单文件 700 行 6 职责。拆为：

- `pretooluse_guard.py` — 保留 CLI 入口 + 主编排，import 其他模块
- `_guard_classify.py` — 工具分类逻辑（_classify_tool_use 6 工具 if-elif）
- `_guard_patterns.py` — 正则模式 + FORBIDDEN_SUFFIXES + FORBIDDEN_DIRS（可配置化）

**不拆为子包。** 用下划线前缀模块表示内部拆分，保持 `memory_core.tools.` 平铺结构不变。

### 4.7 统一 Rule 抽象（解决 B-03 核心缺口）

**方法论：API and Interface Design** — 契约先行 / 可演进 / 明确边界 / 一致性 / 边设计边记录。

#### 问题

6 种互不兼容的规则模式散落 9 个文件，无公共基类。这不是需要"规则引擎库"，而是需要**统一的求值契约**，让所有规则函数遵循相同的输入输出格式。

#### 契约定义（契约先行）

```python
# memory_core/tools/_rule_types.py （新文件，仅类型定义）

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RuleResult:
    """所有规则求值的统一返回类型。"""
    matched: bool                    # 规则是否命中
    severity: str = "info"           # info | warning | error | block
    message: str = ""                # 人可读描述
    detail: dict[str, Any] = field(default_factory=dict)  # 机器可读补充


@dataclass
class RuleContext:
    """规则求值的统一输入 — 替代散落的 dict[str, Any] 和裸字符串参数。

    调用方按需填充字段，规则函数只读自己需要的字段。
    """
    path: Path | None = None         # 路径类规则（ownership/denylist/guard）
    content: str | None = None       # 内容类规则（business_policy/consistency）
    tool_name: str | None = None     # 工具拦截规则（pretooluse_guard）
    event_type: str | None = None    # 事件映射规则（hook_event）
    project_root: Path | None = None # 项目上下文
    extra: dict[str, Any] = field(default_factory=dict)  # 扩展槽


class RuleEvaluator(Protocol):
    """规则求值协议 — 所有规则实现的统一接口。

    演进自 PolicyRegistry.validate(context) — 但 validate 是一个巨型方法
    包含所有校验逻辑，RuleEvaluator 将其拆为独立可组合的单元。
    """

    @property
    def rule_name(self) -> str:
        """稳定标识符，用于 metrics/logging。"""
        ...

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        """对给定上下文求值，返回结果。纯函数，不执行 I/O。"""
        ...
```

#### 边界设计（明确边界）

6 种现有规则模式映射为 4 种 RuleEvaluator 实现：

| 现有模式 | 来源文件 | RuleEvaluator 实现 | 可配置？ |
|----------|----------|-------------------|----------|
| fnmatch + 前缀比较 | ownership.py | `PathRule` | 是（TOML 已支持） |
| 预编译正则列表 | denylist.py, consistency_check.py | `PatternRule` | 是（正则列表可外部化） |
| 字符串包含 + frozenset | pretooluse_guard.py, business_policy_checks.py | `KeywordRule` | 部分（suffixes 可配置，markers 是文件格式契约不可改） |
| 字典映射 + 集合判断 | hook_event.py | **不抽象** | 否（结构常量，3个值，不会变） |

**关键决策：不抽象一切。** hook_event.py 的事件映射是 3 个值的静态字典，抽象为 RuleEvaluator 是过度设计。RuleEvaluator 只用于**模式会扩展**的规则（路径规则会加新模式、denylist 会加新垃圾目录、guard 会加新后缀）。

#### 可配置 vs 硬编码分界

| 规则域 | 决策 | 理由 |
|--------|------|------|
| ownership 路径模式 | **可配置** | 已有 TOML 支持，marker 正则需从函数体提取到配置 |
| denylist 垃圾目录 | **可配置** | JUNK_DIR_PATTERNS 从硬编码 tuple 提取到常量模块或 TOML |
| guard FORBIDDEN_SUFFIXES | **可配置** | 新文件类型禁止规则会随业务变化 |
| business_policy MKR_* markers | **硬编码** | 中文 marker 是消费项目文件中的格式契约，不可配置化 |
| hook_event 事件映射 | **硬编码** | 3 个值的静态映射，抽象收益为零 |
| consistency_check 源码扫描 | **硬编码** | 扫描的是 memory-core 自身代码模式，不会外部配置化 |

#### 演进策略（可演进）

**不修改 PolicyRegistry / GatewayBusinessPolicy 现有 ABC。** 而是让具体规则类**同时实现** RuleEvaluator Protocol 和现有 ABC 方法：

```python
# business_policy_checks.py 中的 ProjectMapValidator 演进

class ProjectMapValidator:
    """同时满足：现有 GatewayBusinessPolicy 调用方 + RuleEvaluator 协议。"""

    # 现有方法保持不变（向后兼容）
    def validate_project_map(self) -> list[str]:
        content = self._config.project_map_path.read_text()
        return self._check_map_markers(content)

    # 新增 RuleEvaluator 协议实现（渐进式，不破坏现有调用）
    @property
    def rule_name(self) -> str:
        return "project_map_validation"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        if ctx.content is None:
            return RuleResult(matched=False, severity="error", message="no content provided")
        errors = self._check_map_markers(ctx.content)  # 复用现有纯函数
        return RuleResult(
            matched=len(errors) > 0,
            severity="error" if errors else "info",
            message="; ".join(errors) if errors else "project map valid",
        )
```

**效果：** 现有调用方走 `validate_project_map()` 不受影响。新增的批量求值场景走 `evaluate(ctx)`。两种调用方式共享底层 `_check_map_markers()` 纯函数。

#### 注册机制

**命令式注册，不用装饰器。** memory-core 的模块加载顺序敏感（双导入模式），装饰器注册的时机不可控。

```python
# 编排层（gateway/guard/CLI）按需构建规则列表
def build_rule_chain(config) -> list[RuleEvaluator]:
    """根据配置构建规则链。调用方显式组装。"""
    rules: list[RuleEvaluator] = []
    if config.enable_ownership:
        rules.append(PathRule(config.ownership_patterns))
    if config.enable_denylist:
        rules.append(PatternRule(config.denylist_patterns))
    if config.enable_guard:
        rules.extend([
            KeywordRule("forbidden_suffix", config.forbidden_suffixes),
            KeywordRule("forbidden_dir", config.forbidden_dirs),
        ])
    return rules

# 批量求值
def evaluate_rules(rules: list[RuleEvaluator], ctx: RuleContext) -> list[RuleResult]:
    return [r.evaluate(ctx) for r in rules]
```

#### 不做什么

- **不引入第三方规则引擎库。** 自有的正则/fnmatch/集合判断已足够。
- **不抽象 hook_event.py 的字典映射。** 3 个值的静态映射，抽象收益为零。
- **不把 MKR_* markers 配置化。** 中文 marker 是文件格式契约，配置化等于允许破坏消费项目。
- **不用装饰器注册。** 双导入模式下注册时机不可控。
- **不新建 RuleRegistry ABC。** 命令式 list 组装比 ABC 更灵活，且不污染 interfaces.py。

### 4.8 异常层次与错误传播（解决 B-08/B-09/B-10/B-11/B-13）

#### 问题

当前异常处理有三个公共面问题影响消费项目：

1. **B-10**：全代码库仅 1 个自定义异常（PromptTooLongError），所有领域错误用 ValueError，消费项目无法精确 catch。
2. **B-11**：多处 `except Exception: pass` 静默吞掉错误，消费项目无法感知 memory-core 内部失败。
3. **B-13**：ValueError 被 catch-all 使用（不支持的 scope / 未知 host / 路由 kind 错误都抛 ValueError），消费项目无法区分。

#### 异常层次设计（契约先行）

```python
# memory_core/tools/_rule_errors.py （新文件）

class MemoryCoreError(Exception):
    """所有 memory-core 领域异常的基类。

    消费项目可 catch 此基类捕获所有 memory-core 抛出的业务异常。
    """


# --- 规则域异常 ---

class RuleViolationError(MemoryCoreError):
    """规则校验失败（对应 RuleResult.severity='block'）。"""
    def __init__(self, rule_name: str, message: str, detail: dict | None = None):
        self.rule_name = rule_name
        self.detail = detail or {}
        super().__init__(f"[{rule_name}] {message}")


class OwnershipError(MemoryCoreError):
    """路径所有权违规（被保护路径被写入）。"""


class GuardBlockError(MemoryCoreError):
    """工具拦截（pretooluse_guard 拒绝操作）。"""
    def __init__(self, tool: str, reason: str, path: str = ""):
        self.tool = tool
        self.path = path
        super().__init__(f"blocked {tool}: {reason}")


class PolicyViolationError(MemoryCoreError):
    """业务策略违规（project-map / frozen-tuple / event-contract 校验失败）。"""


# --- 配置域异常 ---

class UnsupportedScopeError(MemoryCoreError):
    """不支持的 scope（替代 ValueError）。"""


class UnknownHostError(MemoryCoreError):
    """未知的 host（替代 ValueError）。"""


class UnknownRouteKindError(MemoryCoreError):
    """不支持的 route kind（替代 ValueError）。"""
```

#### 错误传播策略

当前 `except Exception: pass` 模式需要按**错误是否影响消费项目**分类处理：

| 错误类型 | 当前行为 | 目标行为 | 理由 |
|----------|----------|----------|------|
| 遥测上报失败 | except: pass | **保持 pass** | 遥测不影响功能，静默降级正确 |
| metrics JSONL 写入失败 | except: pass | **保持 pass**（+ warning log） | 指标丢失不影响功能 |
| 路径所有权违规 | 未捕获/被吞 | **上抛 OwnershipError** | 消费项目必须知道写入被拒绝 |
| 工具拦截判定 | 返回 stderr | **保持返回 stderr + 上抛 GuardBlockError**（双重：既有进程退出码又有异常） | hook 热路径须通过退出码通信 |
| 业务策略校验失败 | 返回 list[str] | **保持返回 list[str]**（不抛异常） | 批量校验语义，一个失败不阻断其余检查 |
| 配置解析错误 | ValueError | **上抛 MemoryCoreError 子类** | 消费项目可精确 catch |
| write_error_log 可选导入失败 | except: pass | **保持 pass**（+ stderr print） | error_logger 是可选依赖 |

**核心原则：** 规则求值函数（RuleEvaluator.evaluate）**不抛异常**，返回 RuleResult。编排层根据 severity 决定是否上抛。遥测/metrics 等辅助系统的失败保持静默降级。

#### 文件锁统一（解决 B-09）

当前 fcntl.flock 在 4 个模块各自实现。统一到 `_file_utils.py`：

```python
# memory_core/tools/_file_utils.py

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import IO

@contextmanager
def exclusive_lock(file_obj: IO, *, label: str = ""):
    """POSIX 独占文件锁上下文管理器。

    用法:
        with open(path, "a") as f:
            with exclusive_lock(f, label="metrics"):
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
    """
    fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def now_iso() -> str:
    """统一的 ISO 时间戳（解决 8 处 _now_iso 复制）。"""
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")
```

4 个模块（integrity_manifest / migrate / cmux_hook_state / metrics）改为 `from _file_utils import exclusive_lock`。

**跨平台说明：** fcntl 是 POSIX-only。当前在 Windows 上会 ImportError。本设计**不新增 Windows 支持**（memory-core 从未支持 Windows），但在 `_file_utils.py` 中留注释标注此限制。

#### 错误日志统一（解决 B-08）

当前 `write_error_log` 在 5+ 模块通过 try/except import，可能静默丢失。

统一为：编排层通过 CoreConfig 注入 ErrorSink（已有 ABC）。规则函数和 CLI 不直接 import error_logger，而是通过注入的 sink 写错误。

```python
# 编排层（如 daily_summary_generator）
def process_project(project_root: Path, error_sink: ErrorSink | None = None):
    try:
        ...
    except Exception as e:
        if error_sink:
            error_sink.log("daily_summary", str(e), {"project": str(project_root)})
        else:
            # 无 sink 时降级到 stderr（不静默吞掉）
            import sys
            print(f"[ERROR] daily_summary: {e}", file=sys.stderr)
```

**效果：** 错误不丢失（有 sink 走 sink，无 sink 走 stderr），消费项目可通过注入自定义 ErrorSink 接管错误处理。

## 5. 监控集成（复用现有管线，不新建）

memory-core 已有完整的三层监控基础设施，规则引擎统一后**直接复用**，不新增任何监控组件。

### 5.1 现有监控管线

| 层 | 模块 | 职责 |
|----|------|------|
| 本地指标 | `memory_hook_metrics.py` | JSONL 指标写入（fcntl 文件锁 + duration_ms） |
| 可观测性 | `observability.py` | TraceContext / MetricsRegistry / ErrorTracker |
| 遥测上报 | `telemetry_bridge.py` | PostHog 批量上报（hourly 窗口 + 路径脱敏） |
| SDK 封装 | `posthog_client.py` | PostHog 客户端 + 优雅降级（API Key 为空时 no-op） |

### 5.2 规则引擎接入点

规则引擎不引入新的监控依赖，而是通过 CoreConfig 现有回调接入：

- **执行耗时：** 规则校验函数的 duration_ms 通过 `memory_hook_metrics.collect_metrics()` 记录到 JSONL，与 gateway/guard 现有链路一致。
- **错误追踪：** 规则校验失败的错误通过 `error_logger.write_error_log()` 写入 C 层错误日志，与 daily_summary_generator / session_end_logger 现有链路一致。
- **降级事件：** LLM 降级事件通过现有 `telemetry_bridge` 上报到 PostHog，无需新增事件类型。

### 5.3 不做的事

- 不为规则引擎新建 MetricsRegistry 实例（复用 observability.py 的）
- 不新增 PostHog 事件类型（复用现有 `memory.hook.execute` 事件的 properties）
- 不在规则函数内部内嵌监控调用（监控由编排层负责，规则函数保持纯函数 — 见 4.4 节）

## 6. 约束条件（设计不可违反）

### 6.1 向后兼容（D 类约束）

| 约束 | 要求 |
|------|------|
| 16个CLI入口点 | `pyproject.toml` 的 `[project.scripts]` 保持不变 |
| 4个公共API符号 | `memory_core/__init__.py` 的 `__getattr__` 保持不变 |
| `from memory_core.tools.X import Y` | 所有现有导入路径通过原文件 re-export 保持可用 |
| 双导入模式 | `try: from .X import Y / except: from memory_core.tools.X import Y` 保持可用 |
| CoreConfig 37字段 | 不删除字段，只新增（新字段必须有默认值） |
| PolicyRegistry 13方法 | 接口方法不删除，只新增 |

### 6.2 数据契约（F 类约束）

| 契约 | 要求 |
|------|------|
| memory.lock 5字段 | 不改变 TOML schema |
| manifest.json v2 | SHA-256+HMAC 签名格式不变 |
| adapter.toml 三段式 | [core]/[policy]/[routing] 结构不变 |
| policy-pack.json | m3-policy-pack-v1 schema 不变 |
| _validation_constants.py | MKR_* 常量值不变（中文marker是文件格式契约） |

### 6.3 安全（J 类约束）

| 约束 | 要求 |
|------|------|
| SanitizingFilter | log_utils.py 的日志脱敏保持不变 |
| 遥测脱敏 | telemetry_bridge.py 的路径替换为 basename 保持不变 |
| BOUNDARY.md 规则 | 业务项目状态不进入 memory-core 的分离原则保持不变 |

## 7. 分阶段迁移路线

### 7.1 阶段 1：消除双轨（最高优先级）

**目标：** 让生产路径和测试路径走同一套代码。

1. `memory_hook_impls.py` 的 `GatewayBusinessPolicyImpl` 改为委托 `business_policy_checks.*`
2. 确认 `NeutralGatewayBusinessPolicy` 继承链走新路径
3. 运行全部测试确认行为不变
4. 不删除旧方法体（保留为委托调用的兼容层）

**验证：** 全部 125 个测试通过 + marker 修改测试（改一处 MKR_* 常量，确认生产路径生效）。

### 7.2 阶段 2：提取共享工具函数

**目标：** 消除 8 个三复制函数。

1. 创建 `_rule_helpers.py`
2. 三个文件改为 import
3. 删除各自的本地副本
4. 运行全部测试

**验证：** pylint R0801 重复检测项减少。

### 7.3 阶段 3：规则逻辑与 I/O 分离

**目标：** 规则函数变为纯函数。

1. business_policy_checks.py 的 `TruthBasisResolver` 方法改为接受字符串参数
2. ownership.py 的 `is_memory_core_source_repo` 的 git 调用提取为可注入回调
3. 调用方负责 I/O
4. 运行全部测试

**验证：** 规则函数可用纯字符串输入测试，无需 mock read_text/subprocess。

### 7.4 阶段 4：pretooluse_guard 拆分

**目标：** 消除 700 行单文件 6 职责。

1. 提取 `_guard_classify.py`（分类逻辑）
2. 提取 `_guard_patterns.py`（模式定义）
3. pretooluse_guard.py 保留入口和编排
4. 运行全部测试

**验证：** ruff C901 复杂度抑制可移除。

### 7.5 阶段 5：异常层次与错误传播

**目标：** 让消费项目能精确 catch memory-core 异常。

1. 创建 `_rule_errors.py`（7 个异常类层次）
2. 创建 `_file_utils.py`（exclusive_lock + now_iso）
3. 4 个 fcntl 模块改为 import _file_utils
4. 8 处 _now_iso 复制改为 import now_iso
5. 将 ValueError catch-all（不支持的 scope / 未知 host / 路由 kind）替换为对应 MemoryCoreError 子类
6. 区分"可吞掉的遥测失败"vs"必须上抛的规则失败"（按 4.8 错误传播策略表）
7. write_error_log 可选 import 改为 CoreConfig 注入 ErrorSink
8. 运行全部测试

**验证：** 消费项目可 `catch MemoryCoreError` 捕获所有业务异常；遥测失败仍静默降级。

### 7.6 阶段 6：LLM 边界明确化

**目标：** 确认 LLM 隔离的完整性。

1. 审计 daily_summary_generator.py 确认 _call_llm 是唯一 LLM 出口
2. 确认降级路径在无 API Key 时正常工作
3. 文档标注 LLM 可选依赖区域
4. 无代码变更（仅审计和文档）

**验证：** `GLM_API_KEY=` 空 + `MEMORY_LLM_ENDPOINT=` 空时，daily summary 生成纯统计报告。

## 8. 不做什么

明确列出**不在本次重构范围内**的事项：

- **不重组 tools/ 目录为子包。** 54 个文件平铺是历史产物，重组破坏面太大（CLI/导入/测试/CI），收益不明确。
- **不新建 rule_engine/ 包。** 在现有结构内收敛即可。
- **不引入第三方规则引擎库。** 自有的正则/fnmatch/字典映射已经足够，不需要 `pyknow` / `python-rule-engine` 等外部依赖。
- **不改 compat.py 版本矩阵。** 本次重构不引入新 schema 版本。
- **不处理 God 模块（init_project_memory.py 2647行等）。** 这些模块职责复杂但不涉及规则/LLM 混乱。
- **不处理全局知识库缺口。** 25 个知识领域缺口由后续单独处理。
- **不改测试基础设施。** conftest.py / fixtures / coverage 配置保持不变。
- **不改 CI/CD 工作流。** ci.yml / release-and-dispatch.yml 保持不变。

## 9. 成功标准

| 标准 | 验证方法 |
|------|----------|
| 生产路径和测试路径走同一套业务策略代码 | marker 修改测试 |
| 8 个三复制函数集中到一处 | pylint R0801 检测 |
| 规则函数可用纯字符串输入测试 | 单元测试无需 mock I/O |
| pretooluse_guard 复杂度降至阈值以下 | ruff C901 无抑制 |
| LLM 调用集中在 daily_summary_generator.py 的 3 个函数 | grep 确认无其他 LLM 出口 |
| 无 LLM 依赖时核心系统正常工作 | 空 API Key 降级测试 |
| 领域异常层次建立 | 消费项目可 catch MemoryCoreError |
| 4 处 fcntl 锁统一 | grep 确认仅 _file_utils.py 有 fcntl |
| _now_iso 不再复制 | grep 确认仅 _file_utils.py 有 datetime.now().astimezone |
| 遥测失败仍静默降级 | 空 POSTHOG_API_KEY 时无异常抛出 |
| 全部 125 个测试通过 | pytest |
| 16 个 CLI 入口不变 | pyproject.toml diff |
| 4 个公共 API 符号不变 | memory_core.__init__.py diff |
| 覆盖率不低于 15% | pytest --cov-fail-under=15 |

---

## 10. Agent-as-LLM：daily_summary_generator 彻底消除 LLM 调用

### 10.1 架构洞察

memory-core 跑在 AI Agent（如 Droid）上下文里，**Agent 就是 LLM**。当前 `daily_summary_generator.py` 通过 `curl` 调用远端 GLM API，本质上是"LLM 里再调一个 LLM"。

这带来三个问题：
1. **冗余推理**：Agent 本身已有 LLM 推理能力，工具内部再发 HTTP 调另一个 LLM 是多此一举
2. **延迟叠加**：curl 请求 + 远端推理 = 120s 超时，而 Agent 可以直接读数据生成摘要
3. **配置耦合**：需要 `GLM_API_KEY`、`MEMORY_LLM_ENDPOINT` 环境变量和 `~/.factory/settings.json` 解析逻辑

### 10.2 改造方案

**daily_summary_generator 变为纯数据工具**：只负责收集和结构化输出 session 数据，不做推理。

| 原函数 | 处理方式 |
|--------|----------|
| `_call_llm` | **删除** |
| `_get_factory_api_key` | **删除** |
| `_build_llm_prompt` | **删除**（prompt 构建交给 Agent） |
| `_generate_fallback_report` | **改造为 `_generate_data_report`**，成为唯一输出格式，包含 A+B 层完整数据 |
| `LLM_ENDPOINT` / `LLM_MODEL` / `LLM_TIMEOUT` | **删除** |
| `process_project` 中的 LLM 调用步骤 | **移除**，直接输出数据报告 |
| `_fallback_check` 中的 LLM 调用 | **移除** |

### 10.3 输出格式

输出 Markdown 报告，包含足够结构化数据供 Agent 直接推理：
- 统计概览（session 数、token 总量）
- 每个 session 的 A 层数据（标题、模型、时长、token、工具调用、用户意图、助手摘要）
- 每个 session 的 B 层增强数据（用户消息摘录、助手消息摘录、工具列表）

Agent 读取此报告后，可直接用自己的推理能力生成主题分类和经验总结。

### 10.4 验证

- `grep -rn 'curl\|glm\|api_key\|LLM_ENDPOINT\|LLM_MODEL\|_call_llm' memory_core/tools/daily_summary_generator.py` 返回空
- `daily_summary_generator --today --dry-run` 输出包含 session 数据的报告（无需任何 API key）
- 全部测试通过
