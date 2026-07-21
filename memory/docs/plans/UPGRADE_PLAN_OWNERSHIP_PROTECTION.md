# memory-core 文档路径保护升级计划 v3（合并版）

> 状态：待审批  
> 项目路径：`/Users/busiji/memory`  
> 合并来源：
>
> - 计划 A：`docs/UPGRADE_PLAN_OWNERSHIP_PROTECTION.md`（v2）
> - 计划 B：GPT-5.5 方案（会话 b6838a9e）
> - 10 个子代理审查结论

---

## 1. 背景

在前序会话中，Agent 未经用户批准派发子代理执行文档迁移，试图将 memory-core 源码仓库中的规范受保护文档，例如：

- `memory/docs/design/*.md`
- `memory/kb/**`
- `memory/docs/**`

搬迁到自创目录，例如：

- `docs/specs/`
- `docs/design/`

该行为违反了 memory-core 现有规范约束：

- `docs/DOT_MEMORY_SPEC.md`
- `docs/BOUNDARY.md`
- `memory/docs/INDEX.md`
- memory-core 源码仓库边界规则
- "不得未经审批迁移规范文档路径"的项目治理约束

本次升级计划的目标是：将 memory-core 的保护模型从"列举若干受保护文件"升级为"基于 Ownership Domain 的整体管辖域保护模型"，并在工具调用入口、初始化流程、校验审计、hook 注入、完整性签名、子代理 policy 和旧项目迁移层面形成闭环。

---

## 2. 根因分析

### 2.1 保护模型过窄

现有保护主要依赖 `FORBIDDEN_OVERWRITE_PATTERNS` 或局部硬编码路径，重点保护：

- `AGENTS.md`
- `INDEX.md`
- `CLAUDE.md`
- `project-map/**`

但没有将以下路径视为整体受保护管辖域：

- `memory/**`
- `memory/docs/**`
- `memory/kb/**`
- `.memory/**`
- `project-map/**`
- memory-core 源码仓库中的规范文档映射路径

导致新增文件、深层文档、索引文件和 KB 文件可被 Agent 直接移动、删除或覆盖。

### 2.2 Hook anti-pollution 对源码仓库一刀切短路

memory-core 源码仓库被识别后，Factory/Codex hook 可能直接输出 `{}` 或进入 noop/degraded 路径，以避免源码仓库被自身 memory runtime 污染。

这虽然避免了 runtime 写入，但同时造成：

- 规则不注入；
- 上下文保护不生效；
- 源码仓库成为 policy 盲区；
- 子代理无法继承 DOT_MEMORY_SPEC / BOUNDARY / INDEX 约束。

正确策略应是：源码仓库不初始化、不写 runtime，但必须注入只读 context-package。

### 2.3 缺少 PreToolUse 写入拦截

现有保护主要发生在：

- init；
- validate；
- audit；
- session-start hook；
- integrity verify；

但 Agent 可以通过以下方式绕过：

- `Write`
- `Edit`
- `MultiEdit`
- `NotebookEdit`
- `Execute`
- `Task` 子代理
- `git mv`
- `mv`
- `rm`
- `cp`
- shell redirect
- `python -c`
- 外部 MCP 写入工具

缺少 Factory `PreToolUse` 层面的统一写入拦截，是事故能够发生的根本缺口。

### 2.4 子代理不继承主会话 policy

Task 子代理可能：

- 在不同 cwd 下运行；
- 未接收主会话的 memory policy；
- 不知道哪些路径受保护；
- 仅依据任务描述执行"迁移/整理/重构"；
- 使用 Execute 或文件编辑工具绕过主代理的判断。

因此，必须在 Task payload 中注入 ownership policy，并通过 PreToolUse 对 Task 本身和子代理后续工具调用进行保护。

### 2.5 integrity / delegate / hook 失败语义过弱

现有系统中部分失败可能表现为：

- silent noop；
- degraded 但继续执行；
- verify 失败后 auto re-sign；
- delegate preflight 异常被吞掉；
- NoopHostDelegate 返回假成功；
- 初始化失败 `|| true` 被吞。

这些行为会把安全失败转化为"看似成功"，使保护机制无法形成阻断。

### 2.6 `--force` 和环境变量可能成为绕过通道

以下机制存在被滥用风险：

- `memory-init --force`
- `MEMORY_HOOK_FORCE`
- 外部 core builder override
- 裸环境变量 escape hatch
- hook runtime 自动升级/自动 re-sign

升级后必须确保：

- `--force` 不能覆盖 owned domain；
- `MEMORY_HOOK_FORCE` 不可绕过 ownership guard；
- escape hatch 必须绑定维护 CLI、审批 token、reason 和 audit；
- verify 失败后禁止 hook 自动 re-sign。

---

## 3. 绕过点清单

### 3.1 Critical 绕过点

| 编号 | 绕过点 | 问题 | 解决方向 |
|---|---|---|---|
| C1 | `memory/docs/**`、`memory/kb/**` 不在保护范围 | 文档与 KB 可被任意迁移/删除 | 将 `memory/` 整体纳入 protected ownership domain |
| C2 | `memory-init --force` 可覆盖保护内容 | force 成为绕过保护入口 | `--force` ownership-aware，owned path 默认不可覆盖 |

### 3.2 High 绕过点

| 编号 | 绕过点 | 问题 | 解决方向 |
|---|---|---|---|
| H1 | Factory hook anti-pollution 短路 | 源码仓库规则不注入 | source repo readonly context-package |
| H2 | Codex hook anti-pollution 短路 | 同上 | 同步 Factory 策略 |
| H3 | gateway source repo 分支输出 `{}` | 规则盲区 | readonly context-package |
| H4 | wrapper 初始化失败被吞 | 失败不可见 | structured error / degraded / block |
| H5 | `MEMORY_HOOK_FORCE` 绕过 | 裸 env 可能 bypass | FORCE 不得绕过 ownership guard |
| H6 | 外部 core builder override | 可替换保护逻辑 | guard 禁止外部 builder 替换 |
| H7 | integrity 非阻断 | 篡改不阻断 | verify fail 默认 block，禁止 auto re-sign |
| H8 | NoopHostDelegate 吞掉执行 | 假成功 | policy decision 与 delegate availability 分离 |
| H9 | delegate preflight 异常 noop | 异常被吞 | 返回 degraded/block，携带错误 |
| H10 | validate 读失败 continue | 损坏/缺失漏检 | owned critical/protected 读失败必须 error |

### 3.3 根本性缺口

| 编号 | 缺口 | 解决方向 |
|---|---|---|
| F1 | 无 PreToolUse 写入拦截 | M5a 前置最小 P0 guard |
| F2 | 子代理不继承 policy | M5b Task policy 注入 + cwd 固定 |
| F3 | 外部 MCP / Execute 可绕过 | PreToolUse 覆盖 Execute/Task/写入类工具 |
| F4 | integrity 失败不阻断 | M4 ownership-aware integrity |
| F5 | 源码仓库 readonly 与规则注入冲突 | M3 读写分离 |

---

## 4. 核心设计原则

### 4.1 从文件清单保护升级为管辖域保护

保护模型从：

```text
保护 AGENTS.md / INDEX.md / CLAUDE.md / project-map/**
```

升级为：

```text
memory-init 接管的整个 memory 管辖区默认受保护
```

管辖域内新增文件自动受保护，不需要逐个声明。

### 4.2 默认三大管辖域

| 域 | 根路径 | 保护级别 | 说明 |
|---|---|---:|---|
| dot-memory | `.memory/` | critical | 控制平面：lock、adapter、manifest、ownership、canonical state |
| memory | `memory/` | protected | 知识与文档平面：KB、docs、system、inbox |
| project-map | `project-map/` | critical | 合法性地图、registry、项目索引 |

### 4.3 默认入口资源

| 资源 | 路径 | 保护方式 |
|---|---|---|
| 状态快照 | `NOW.md` | whole-file |
| 根索引 | `INDEX.md` | whole-file-if-memory-generated |
| Agent 入口 | `AGENTS.md` | marked-block |
| Claude hook 配置 | `.claude/hooks.json` | memory-hook-entries / critical file |

### 4.4 唯一路径分类 API

所有工具链必须复用统一 API：

```python
classify_owned_path(path, project_root, ownership, ...)
```

使用方包括：

- `memory-init`
- `memory-validate`
- `memory-audit-layout`
- `memory-apply-residue-plan`
- Factory PreToolUse guard
- hook gateway
- integrity manifest
- 子代理 policy injection
- hook upgrade / migration CLI

禁止继续散落维护独立 forbidden path 列表。

### 4.5 无交互默认 block

在 Exec Mode、hook、PreToolUse、子代理、CI 等无交互场景中：

- 无法判断是否安全：block；
- ownership.toml 缺失：fallback 默认三域，不放行；
- ownership.toml 解析失败：block；
- verify 失败：block；
- delegate 不可用：不得视为 allow；
- Execute 无法解析但疑似写 owned path：block。

---

## 5. Ownership 数据模型

### 5.1 核心类型

建议新增模块：

```text
memory_core/ownership.py
```

核心数据结构：

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal


class ProtectionLevel(str, Enum):
    CRITICAL = "critical"
    PROTECTED = "protected"
    MANAGED_RUNTIME = "managed-runtime"


class OwnershipKind(str, Enum):
    DOMAIN = "domain"
    RESOURCE = "resource"
    SHARED_RESOURCE_BLOCK = "shared-resource-block"


@dataclass(frozen=True)
class OwnershipDomain:
    id: str
    path: PurePosixPath
    level: ProtectionLevel
    immutable_default: bool
    recursive: bool = True
    description: str = ""


@dataclass(frozen=True)
class OwnershipResource:
    id: str
    path: PurePosixPath
    level: ProtectionLevel
    kind: OwnershipKind
    marker_begin: str | None = None
    marker_end: str | None = None
    immutable_default: bool = False
    description: str = ""


@dataclass(frozen=True)
class Owned:
    owner_id: str
    owner_path: PurePosixPath
    level: ProtectionLevel
    kind: OwnershipKind
    shared_block_only: bool = False
    reason: str = ""


@dataclass(frozen=True)
class NotOwned:
    reason: str = "not-owned"


PathClassification = Owned | NotOwned


@dataclass(frozen=True)
class MemoryOwnership:
    schema_version: str
    memory_version: str
    domains: tuple[OwnershipDomain, ...]
    resources: tuple[OwnershipResource, ...]
    source: Literal["ownership.toml", "default-fallback"]
```

### 5.2 默认域常量

```python
DEFAULT_OWNERSHIP_DOMAINS = (
    OwnershipDomain(
        id="dot-memory",
        path=PurePosixPath(".memory"),
        level=ProtectionLevel.CRITICAL,
        immutable_default=True,
        recursive=True,
        description="Project-local memory metadata and governance state",
    ),
    OwnershipDomain(
        id="memory",
        path=PurePosixPath("memory"),
        level=ProtectionLevel.PROTECTED,
        immutable_default=True,
        recursive=True,
        description="Project memory KB/docs/system runtime area",
    ),
    OwnershipDomain(
        id="project-map",
        path=PurePosixPath("project-map"),
        level=ProtectionLevel.CRITICAL,
        immutable_default=True,
        recursive=True,
        description="Legal directory map and ingestion registry",
    ),
)
```

### 5.3 默认资源常量

```python
DEFAULT_OWNERSHIP_RESOURCES = (
    OwnershipResource(
        id="now-md",
        path=PurePosixPath("NOW.md"),
        level=ProtectionLevel.PROTECTED,
        kind=OwnershipKind.RESOURCE,
        immutable_default=True,
    ),
    OwnershipResource(
        id="index-md",
        path=PurePosixPath("INDEX.md"),
        level=ProtectionLevel.PROTECTED,
        kind=OwnershipKind.RESOURCE,
        immutable_default=True,
    ),
    OwnershipResource(
        id="agents-md-memory-hook-block",
        path=PurePosixPath("AGENTS.md"),
        level=ProtectionLevel.PROTECTED,
        kind=OwnershipKind.SHARED_RESOURCE_BLOCK,
        marker_begin="<!-- MEMORY_HOOK_BEGIN -->",
        marker_end="<!-- MEMORY_HOOK_END -->",
        immutable_default=True,
    ),
    OwnershipResource(
        id="claude-hooks-json",
        path=PurePosixPath(".claude/hooks.json"),
        level=ProtectionLevel.CRITICAL,
        kind=OwnershipKind.RESOURCE,
        immutable_default=True,
    ),
)
```

### 5.4 `classify_owned_path()` 语义

```python
def load_memory_ownership(project_root: Path) -> MemoryOwnership:
    """
    1. 如果 .memory/ownership.toml 存在，加载并校验；
    2. 如果不存在，按默认三域 + 默认入口资源 fallback；
    3. 如果 TOML 存在但 schema 削弱默认域，raise OwnershipSchemaError；
    4. 如果 TOML 解析失败，无交互场景默认 block。
    """


def classify_owned_path(
    rel_path: str | PurePosixPath,
    *,
    project_root: Path,
    ownership: MemoryOwnership | None = None,
    content_before: str | None = None,
    content_after: str | None = None,
    operation: str | None = None,
) -> PathClassification:
    """
    返回 Owned 或 NotOwned。

    规则：
    - rel_path 规范化为 POSIX 相对路径；
    - 禁止绝对路径、.. escape、symlink escape；
    - domain 匹配 path == domain.path 或 path 是其后代；
    - resource 匹配 exact path；
    - AGENTS.md marked block 按 patch/diff 判断；
    - 无法判断 shared block 是否被触碰时，保守返回 Owned；
    - ownership.toml 缺失不是放行理由，使用默认 fallback；
    - ownership.toml 损坏时抛出 schema error，由调用方 block。
    """
```

### 5.5 AGENTS.md 共享文件子资源规则

`AGENTS.md` 不应整文件锁死，只保护 memory-core 管理的 marked block：

```text
<!-- MEMORY_HOOK_BEGIN -->
...
<!-- MEMORY_HOOK_END -->
```

判断规则：

| 场景 | 分类结果 | 行为 |
|---|---|---|
| 修改 block 内文本 | Owned / protected / block | 默认阻断，除非维护 CLI |
| 删除 begin/end marker | Owned / critical-like violation | 阻断并 validate error |
| 追加 block 外业务说明 | NotOwned | 允许 |
| 全文件 overwrite 且无法证明保留 block | Owned | 默认阻断 |
| 文件不存在时由 memory-init 创建 block | Owned but authorized maintenance | 仅 memory-init/update 允许 |

---

## 6. `.memory/ownership.toml` Schema

### 6.1 示例

```toml
schema_version = "memory-ownership-v1"
memory_version = "0.5.0"
generated_by = "memory-init"
generated_at = "2026-05-14T00:00:00Z"

[policy]
default_action_for_owned_write = "block"
default_action_when_uncertain = "block"
allow_default_domain_removal = false
requires_memory_init_update_for_schema_changes = true
source_repo_strategy = "readonly-context-package"
allow_verify_failure_resign = false

[[domains]]
id = "dot-memory"
path = ".memory/"
level = "critical"
immutable_default = true
recursive = true
description = "Project-local memory metadata and governance state"

[[domains]]
id = "memory"
path = "memory/"
level = "protected"
immutable_default = true
recursive = true
description = "Project memory KB/docs/system runtime area"

[[domains]]
id = "project-map"
path = "project-map/"
level = "critical"
immutable_default = true
recursive = true
description = "Legal directory map and ingestion registry"

[[resources]]
id = "now-md"
path = "NOW.md"
level = "protected"
kind = "file"
immutable_default = true

[[resources]]
id = "index-md"
path = "INDEX.md"
level = "protected"
kind = "file"
immutable_default = true

[[resources]]
id = "agents-md-memory-hook-block"
path = "AGENTS.md"
level = "protected"
kind = "marked-block"
marker_begin = "<!-- MEMORY_HOOK_BEGIN -->"
marker_end = "<!-- MEMORY_HOOK_END -->"
immutable_default = true

[[resources]]
id = "claude-hooks-json"
path = ".claude/hooks.json"
level = "critical"
kind = "file"
immutable_default = true
```

### 6.2 防削弱规则

`.memory/ownership.toml` 自身位于 `.memory/` critical domain，必须受最强保护。

规则：

1. 默认三域不可删除：
   - `.memory/`
   - `memory/`
   - `project-map/`
2. 默认三域不可降级：
   - `.memory/` 必须是 `critical`
   - `project-map/` 必须是 `critical`
   - `memory/` 必须至少是 `protected`
3. 默认三域不可改为非递归。
4. 默认域 root 不可改成更窄范围。
5. 默认入口资源不可删除，除非通过兼容 migration。
6. `ownership.toml` schema 变更只能通过：
   - `memory-init update`
   - 专用 ownership maintenance CLI
7. PreToolUse 默认阻断对 `.memory/ownership.toml` 的直接修改。
8. TOML 缺失时 fallback 默认三域，不放行。
9. TOML 解析失败时 validate critical error，hook 无交互默认 block。
10. ownership.toml 必须纳入 integrity 签名链。

### 6.3 fallback 规则

无 `.memory/ownership.toml` 时：

```text
load_memory_ownership(project_root)
  -> source = "default-fallback"
  -> domains = DEFAULT_OWNERSHIP_DOMAINS
  -> resources = DEFAULT_OWNERSHIP_RESOURCES
  -> warning = "ownership.toml missing; using default ownership fallback"
```

该 fallback 用于旧项目升级前保护，不得成为放行理由。

---

## 7. 消费者项目与 memory-core 源码仓库分离

### 7.1 消费者项目策略

当：

```python
_is_memory_core_source_repo(project_root) is False
```

行为：

- `memory-init` 可创建/更新：
  - `.memory/`
  - `memory/`
  - `project-map/`
  - `NOW.md`
  - `INDEX.md`
  - `AGENTS.md` marked block
  - `.claude/hooks.json`
  - `.memory/ownership.toml`
- PreToolUse 拦截非授权写入。
- validate/audit/integrity 全部 ownership-aware。
- 子代理与外部 MCP 不依赖模型自觉遵守 policy，而通过 PreToolUse 兜底。

### 7.2 memory-core 源码仓库策略

当：

```python
_is_memory_core_source_repo(project_root) is True
```

检测 marker 可包括：

- `memory_core/tools/memory_hook_gateway.py`
- `memory_core/tools/factory_global_hooks.py`
- `memory_core/tools/codex_global_hooks.py`
- `pyproject.toml` 中包名为 memory-core
- git root 下存在 memory-core 源码结构

行为：

- 不执行 `memory-init`。
- 不自动写入源码仓库 `.memory/`、`memory/`、`project-map/`。
- 不写 artifact、health-report、manifest、lifecycle、integrity cache。
- Hook 只注入 readonly context-package。
- READONLY 必须严格零副作用。
- 源码仓库自身保护依赖：
  - git diff；
  - code review；
  - `scripts/check_boundary.py`；
  - unit tests；
  - 文档索引一致性；
  - source repo readonly side-effect tests。

### 7.3 source repo readonly context-package 内容

source repo hook 输出 context-package：

```json
{
  "package_kind": "source-repo-rules",
  "mode": "read-only",
  "allowed_writes": {},
  "rules": {
    "dot_memory_spec": "...",
    "boundary": "...",
    "docs_index": "..."
  }
}
```

必须注入内容：

- `DOT_MEMORY_SPEC.md`
- `BOUNDARY.md`
- `memory/docs/INDEX.md`
- ownership 默认域说明
- 源码仓库只读规则
- 禁止未经审批迁移 `memory/docs/**`、`memory/kb/**`

---

# 8. 里程碑计划

执行顺序采用合并审查建议：

```text
M1 → M5a → M2 → M3 → M4 → M5b → M6
```

该顺序的原因：

1. M1 先提供统一 ownership 数据模型和分类 API。
2. M5a 立即前置最小 PreToolUse P0，尽早封住事故复现路径。
3. M2 再让 init/validate/audit 接入 ownership。
4. M3 修复 source repo readonly 和 hook 读写分离。
5. M4 修复 integrity 签名链和 re-sign 语义。
6. M5b 完善子代理、cwd、Execute、P1 语义。
7. M6 最后处理旧项目迁移、hook 升级和治理流程。

---

## M1：Ownership 数据模型 + classify API + 默认域常量

### 目标

建立单一事实源：所有路径保护判断都调用统一 ownership API，不再分散写死 forbidden 文件列表。

### 交付物

- 新增 ownership 数据模型：
  - `MemoryOwnership`
  - `OwnershipDomain`
  - `OwnershipResource`
  - `Owned`
  - `NotOwned`
  - `ProtectionLevel`
  - `OwnershipKind`
- 定义默认三大管辖域：
  - `.memory/` critical
  - `memory/` protected
  - `project-map/` critical
- 定义默认入口资源：
  - `NOW.md`
  - `INDEX.md`
  - `AGENTS.md` marked block
  - `.claude/hooks.json`
- 新增：
  - `load_memory_ownership(project_root)`
  - `classify_owned_path(...)`
  - ownership TOML loader
  - fallback 默认三域逻辑
  - ownership schema 防削弱基础 validator
- 新增 memory-core source repo detection API：
  - `_is_memory_core_source_repo(project_root)`
- AGENTS.md block 语义判定：
  - block 内修改 protected；
  - marker 删除 critical-like；
  - block 外业务内容允许；
  - 无法判断时 block。

### 解决的绕过点

| 绕过点 | 解决方式 |
|---|---|
| C1：文档路径不在保护范围 | `memory/` 整体 recursive protected |
| H8：NoopHostDelegate 假成功基础缺口 | 后续 delegate 统一引用 classification，不再自行 allow |
| H10：validate 静默跳过 | M1 提供 classification，M2/M3 接入 strict 判断 |
| 统一 API 缺失 | `classify_owned_path()` 成为唯一入口 |
| ownership schema 可被削弱 | M1 建立基础防削弱规则 |

### 验收标准

- 无 `.memory/ownership.toml` 时 fallback 默认三域。
- 以下路径均分类为 Owned：
  - `.memory/ownership.toml`
  - `.memory/manifest.json`
  - `memory/docs/INDEX.md`
  - `memory/docs/design/x.md`
  - `memory/kb/INDEX.md`
  - `memory/kb/x.md`
  - `project-map/INDEX.md`
- `AGENTS.md` block 内修改分类为 Owned。
- `AGENTS.md` block 外追加业务内容分类为 NotOwned。
- 无法判断是否触碰 AGENTS.md block 时默认 Owned。
- 删除默认域、降级默认域、改非递归必须 schema error。
- 路径 traversal、绝对路径、symlink escape 不得被放行。
- memory-core 源码仓库检测准确，不误判普通消费者项目。

### 需修改的源文件

| 文件 | 改动 |
|---|---|
| `memory_core/ownership.py` | 新增 ownership 数据模型、loader、classification API |
| `memory_core/constants.py` | 增加默认 ownership domains/resources 常量 |
| `memory_core/tools/source_repo_detection.py` | 新增源码仓库检测 API，或合入 ownership 模块 |
| `tests/test_memory_ownership.py` | 新增 ownership 模型与路径分类测试 |
| `tests/test_source_repo_detection.py` | 新增 source repo detection 测试 |

---

## M5a：最小 Factory PreToolUse P0 拦截（前置）

### 目标

在完整迁移前，先部署最小可用写入拦截，阻断事故复现路径。

P0 阶段按"实现成熟度"划分，不按路径削弱保护：

- owned path 写入默认 block；
- `.memory/`、`memory/`、`project-map/` 都默认受保护；
- `memory/` 不再只是"破坏性操作才 block"，而是在 P0 对所有直接写入默认 block；
- Execute 解析不确定时默认 block。

### 交付物

- 新增 Factory `PreToolUse` guard。
- 支持读取 Factory PreToolUse payload。
- 识别工具名和目标路径。
- 调用 `classify_owned_path()`。
- Owned 写入默认 block。
- 覆盖工具：
  - `Write`
  - `Edit`
  - `MultiEdit`
  - `NotebookEdit`
  - `Execute`
  - `Task`
- 支持结构化返回：
  - `decision: "block"`
  - denial reason
  - owned domain/resource
  - protection level
- 合法维护 escape hatch 最小实现，但不得裸 env 放行。
- Factory settings 安装/注册 PreToolUse hook，并保留已有 hooks。

### P0 拦截规则

默认阻断：

- 写 `.memory/**`
- 写 `memory/**`
- 写 `project-map/**`
- 写 `.memory/ownership.toml`
- 写 `.claude/hooks.json`
- 覆盖 memory-managed `INDEX.md`
- 修改 `AGENTS.md` marked block
- 删除 AGENTS.md marker
- Task payload 要求迁移/移动/删除 owned path
- Execute 中出现 owned path 写入意图

Execute P0 覆盖：

- `mv`
- `git mv`
- `rm`
- `cp`
- `mkdir`
- `touch`
- shell redirect `>`
- `>>`
- `tee`
- heredoc
- `python -c 'open(..., "w")'`
- `python -c 'Path(...).write_text(...)'`

无法解析但命令中包含 owned root 字符串时，默认 block。

### AGENTS.md 5 种场景判断

| 场景 | 结果 |
|---|---|
| 修改 MEMORY_HOOK block 内文本 | block |
| 删除 begin/end marker | block |
| 追加 block 外业务说明 | allow |
| 全文件 overwrite 且无法证明保留 block | block |
| memory-init 创建缺失 block | allow only authorized maintenance |

### escape hatch 约束

不得允许：

```bash
MEMORY_HOOK_FORCE=1
```

直接绕过 ownership guard。

允许的维护路径必须满足：

- 通过 `memory-init update` 或专用 maintenance CLI；
- 有明确 reason；
- 有 session-scoped token 或显式 CLI flag；
- cwd 是目标项目根；
- 写 audit event；
- 不允许削弱默认三域；
- 不允许 hook runtime 自动设置后绕过。

### 解决的绕过点

| 绕过点 | 解决方式 |
|---|---|
| F1：无 PreToolUse | 新增 Factory PreToolUse P0 |
| C1：文档路径裸露 | `memory/` 整域 block |
| C2：外部触发 force 覆盖 | owned path 写入先被 guard 阻断 |
| F2：子代理绕过 | Task payload 进入 P0 检查 |
| F3：Execute / 外部工具绕过 | Execute 命令静态解析 + 不确定 block |
| H5：`MEMORY_HOOK_FORCE` | FORCE 不再 bypass ownership |
| H6：外部 builder | guard 不允许外部 builder 替换保护逻辑 |
| H8/H9：delegate noop | PreToolUse 不依赖 delegate allow |

### 验收标准

- `Write` 到 `memory/docs/INDEX.md` 被 block。
- `Edit` 到 `memory/kb/INDEX.md` 被 block。
- `MultiEdit` 任一编辑触碰 owned path 时整体 block。
- `NotebookEdit` 触碰 owned path 时 block。
- `Execute "mv memory/kb tmp/"` 被 block。
- `Execute "git mv memory/docs/design/a.md docs/a.md"` 被 block。
- `Execute "python -c 'open(\"memory/docs/INDEX.md\",\"w\").write(\"x\")'"` 被 block。
- `Task` 描述中要求移动 `memory/kb/**` 被 block 或注入拒绝 policy。
- `MEMORY_HOOK_FORCE=1` 不放行 owned write。
- `src/app.py` 等 NotOwned 普通文件写入允许。
- 不确定路径默认 block。
- settings 注册 PreToolUse 时保留用户已有 hooks。

### 需修改的源文件

| 文件 | 改动 |
|---|---|
| `memory_core/tools/factory_pretooluse_guard.py` | 新增 PreToolUse guard |
| `memory_core/tools/factory_global_hooks.py` | 安装/注册 PreToolUse hook |
| `memory_core/tools/execute_command_guard.py` | 可新增 Execute 路径解析器 |
| `tests/test_factory_pretooluse_guard.py` | 新增 P0 guard 测试 |
| `tests/test_execute_command_guard.py` | 新增 Execute 覆盖测试 |
| `tests/test_factory_global_hooks.py` | 更新 hook 安装测试 |

---

## M2：memory-init ownership.toml + validate/audit 迁移

### 目标

让消费者项目拥有显式 ownership 声明，并让 init、validate、audit、apply-residue-plan 统一使用 ownership API。

### 交付物

- `memory-init` 在以下模式生成或修复 `.memory/ownership.toml`：
  - create
  - adopt
  - update
  - repair
- `memory-init --force` 改为 ownership-aware：
  - 不可覆盖 owned domain 内已有内容；
  - 不可覆盖用户文档；
  - 不可削弱 ownership；
  - 仅 maintenance/update 流程可变更 owned content。
- `memory-validate` 新增四类核心检查：
  1. `check_ownership_declaration()`
  2. `check_domain_integrity()`
  3. `check_document_paths()`
  4. `check_shared_resources()`
- 吸收扩展索引一致性检查：
  - `memory/docs/INDEX.md`
  - `memory/kb/INDEX.md`
  - `project-map/INDEX.md`
- `memory-audit-layout` 输出 ownership findings。
- `memory-apply-residue-plan` 使用 `classify_owned_path()` 替代 `_is_forbidden_path()`。
- 旧项目无 ownership.toml 时：
  - fallback 默认三域；
  - validate warning；
  - repair/update 可补齐。

### validate 四类检查

#### 1. ownership declaration

- `.memory/ownership.toml` 存在或 fallback。
- schema 合法。
- 默认域未删除。
- 默认域未降级。
- 默认域 recursive 未关闭。
- 默认资源未删除。
- ownership.toml 解析失败为 critical error。

#### 2. domain integrity

- `.memory/` 存在且未逃逸。
- `memory/` 存在且未逃逸。
- `project-map/` 存在且未逃逸。
- domain root 不能是 symlink escape。
- owned critical/protected 文件读失败不得 silent continue。

#### 3. document paths

- `memory/docs/INDEX.md` 索引的文档存在。
- `memory/docs/**` 中关键文档位置正确。
- `memory/kb/INDEX.md` 索引 KB 子树。
- `project-map/INDEX.md` 与 project-map 入口一致。
- 索引缺失、断链、路径漂移报告 error 或 strict error。

#### 4. shared resources

- `AGENTS.md` marker 成对。
- `AGENTS.md` marked block 未损坏。
- `.claude/hooks.json` 中 memory hook 条目完整。
- root `INDEX.md` 如果 memory-managed，则不得被覆盖或漂移。

### audit findings

新增 findings：

- `ownership_missing`
- `ownership_schema_invalid`
- `domain_missing`
- `domain_weakened`
- `unmanaged_memory_path`
- `marker_tampered`
- `hooks_entry_missing`
- `index_inconsistent`
- `conflict_business_entry`
- `owned_file_unreadable`

### 解决的绕过点

| 绕过点 | 解决方式 |
|---|---|
| C2：`--force` 覆盖 | ownership-aware force 限制 |
| H10：validate 静默跳过 | owned 读失败 error |
| A 缺失：索引一致性 | 加入 docs/kb/project-map INDEX checks |
| B 缺失：AGENTS marker / hooks 条目 | shared resources 检查 |
| ownership 默认域被削弱 | validate critical error |
| hard-coded forbidden 分散 | audit/apply 使用 classify API |

### 验收标准

- 新项目 init 后存在 `.memory/ownership.toml`。
- adopt/update/repair 不覆盖 owned path 中已有用户内容。
- `memory-init --force` 不得覆盖：
  - `memory/docs/INDEX.md`
  - `memory/kb/**`
  - `project-map/**`
  - `.memory/ownership.toml`
- ownership.toml 缺失时 validate warning + fallback。
- ownership.toml 被削弱时 validate error。
- AGENTS marker 缺失/不成对时 validate error。
- `.claude/hooks.json` memory hook 条目缺失时 validate error/warning。
- `memory/docs/INDEX.md`、`memory/kb/INDEX.md`、`project-map/INDEX.md` 不一致时 validate error。
- root INDEX 读失败不得 pass。
- pollution scan 读失败不得 silent continue。
- audit 输出 ownership findings。
- apply residue plan 不允许移动/删除 owned paths。

### 需修改的源文件

| 文件 | 改动 |
|---|---|
| `memory_core/tools/init_project_memory.py` | 生成 ownership.toml，收紧 force |
| `memory_core/tools/validate_project_memory.py` | 新增 ownership/domain/document/shared checks |
| `memory_core/tools/audit_project_layout.py` | ownership findings，forbidden 改 ownership-derived |
| `memory_core/tools/apply_residue_plan.py` | 使用 classify_owned_path |
| `memory_core/tools/memory_health_report.py` | health report 纳入 ownership 状态 |
| `memory_core/constants.py` | 引用默认 ownership 常量 |
| `tests/test_init_ownership.py` | init ownership 测试 |
| `tests/test_validate_ownership.py` | validate ownership 测试 |
| `tests/test_audit_project_layout.py` | audit ownership 测试 |
| `tests/test_init_force_mode.py` | force 限制测试 |

---

## M3：Hook 读写分离：source repo readonly context-package

### 目标

修复 memory-core 源码仓库因 anti-pollution 而变成规则盲区的问题。

源码仓库必须：

- 不被 memory-init takeover；
- 不写 runtime artifact；
- 不写 manifest；
- 不写 health report；
- 但必须接收只读规则上下文。

### 交付物

- Hook runtime 三模式：
  1. `consumer-project`
  2. `source-repo-readonly`
  3. `noop`
- `_is_memory_core_source_repo()` 抽为共享 API。
- Factory wrapper source repo 分支不再输出裸 `{}`。
- Codex wrapper 同步。
- Claude wrapper 覆盖。
- gateway source repo 分支构建 readonly context-package。
- readonly context-package 注入：
  - `package_kind = "source-repo-rules"`
  - `mode = "read-only"`
  - `allowed_writes = {}`
  - DOT_MEMORY_SPEC
  - BOUNDARY
  - docs INDEX
  - ownership 默认域说明
- READONLY 严格零副作用：
  - 不 mkdir；
  - 不写 artifacts；
  - 不写 manifest；
  - 不写 health-report；
  - 不写 lifecycle；
  - 不 auto sign；
  - 不 repair；
  - 不 upgrade hooks。
- wrapper 初始化失败不再 `|| true` 静默成功。

### 三模式语义

| 模式 | 适用 | 写入 | 输出 |
|---|---|---:|---|
| consumer-project | 普通消费者项目 | 允许授权 runtime 写入 | full context + artifacts |
| source-repo-readonly | memory-core 源码仓库 | repo 内零写入 | readonly context-package |
| noop | 无法识别或不可处理 | 无写入 | structured noop reason |

`noop` 不得表示 policy allow，只能表示 host/runtime unavailable。

### 解决的绕过点

| 绕过点 | 解决方式 |
|---|---|
| H1：Factory anti-pollution 短路 | source repo readonly context-package |
| H2：Codex anti-pollution 短路 | 同步改造 |
| H3：gateway 输出 `{}` | 改为规则 package |
| H4：初始化失败被吞 | structured error / degraded |
| H8：NoopHostDelegate | noop 与 allow 分离 |
| H9：delegate preflight 异常 | 返回 degraded/block，不假成功 |
| A 遗漏 Claude wrapper | Claude wrapper 同步覆盖 |
| B 遗漏注入内容 | 注入 DOT_MEMORY_SPEC + BOUNDARY + INDEX |

### 验收标准

- 在 memory-core 源码 fixture 中触发 hook：
  - 输出 readonly context-package；
  - 包含 DOT_MEMORY_SPEC / BOUNDARY / INDEX；
  - `allowed_writes = {}`；
  - `mode = read-only`；
  - repo 内无新文件；
  - git status 不变化；
  - 关键文件 mtime 不变化。
- 消费者项目 hook 仍正常生成 context/artifacts。
- Factory/Codex/Claude wrapper source repo 行为一致。
- wrapper 初始化失败不被吞。
- NoopHostDelegate 不返回 policy allow。
- delegate preflight 异常包含错误信息。

### 需修改的源文件

| 文件 | 改动 |
|---|---|
| `memory_core/tools/source_repo_detection.py` | 共享源码仓库检测 |
| `memory_core/tools/factory_global_hooks.py` | source repo readonly + PreToolUse 保留 |
| `memory_core/tools/codex_global_hooks.py` | 同步 readonly |
| `memory_core/tools/claude_global_hooks.py` | 新增/更新 Claude wrapper 覆盖 |
| `memory_core/tools/memory_hook_gateway.py` | 三模式 runtime + readonly context-package |
| `memory_core/tools/memory_hook_impls.py` | delegate 失败语义修正 |
| `memory_core/tools/memory_hook_interfaces.py` | policy/delegate 语义分离 |
| `tests/test_source_repo_readonly_hooks.py` | readonly 零副作用测试 |
| `tests/test_factory_global_hooks.py` | Factory wrapper 测试 |
| `tests/test_codex_global_hooks.py` | Codex wrapper 测试 |
| `tests/test_claude_global_hooks.py` | Claude wrapper 测试 |
| `tests/test_noop_host_delegate.py` | Noop delegate 语义测试 |

---

## M4：Integrity ownership-aware + 禁止 verify 失败后 auto re-sign

### 目标

完整性层从固定 canonical patterns 升级为 ownership-aware，并修复"verify 失败后自动 re-sign 掩盖篡改"的严重问题。

### 交付物

- integrity manifest schema 升级到 v2：
  - `integrity-manifest-v2`
- manifest 签名范围改为 ownership-derived。
- `ownership.toml` 纳入签名链。
- critical domain metadata 必签。
- manifest entry 增加：
  - `ownership_id`
  - `protection_level`
  - `classification_source`
  - `path`
  - `digest`
- verify 失败后：
  - 不 auto re-sign；
  - 不覆盖 manifest；
  - 不写新签名；
  - 返回 degraded/block；
  - 无交互默认 block。
- source repo readonly 下 integrity 零副作用。
- 新增专用 re-sign CLI：
  - `memory-integrity-resign`
  - 或 `memory integrity resign`
- re-sign CLI 必须执行安全规则。

### 签名范围

至少包括：

- `.memory/ownership.toml`
- `.memory/memory.lock`
- `.memory/adapter.toml`
- `.memory/manifest.json` 的可签部分或 manifest chain metadata
- `memory/docs/INDEX.md`
- `memory/kb/INDEX.md`
- `project-map/INDEX.md`
- `AGENTS.md` memory marked block hash
- `.claude/hooks.json` memory hook entries hash

可分层签名：

- critical：必须阻断；
- protected：默认阻断，可维护审批；
- managed-runtime：可 degraded，不作为治理文档阻断。

### re-sign 安全规则

禁止：

- hook runtime 自动 re-sign；
- verify failure fallback re-sign；
- Noop delegate re-sign；
- init failure re-sign；
- source repo readonly re-sign。

允许 re-sign 必须满足：

1. 使用专用 CLI；
2. 提供 reason；
3. `memory-validate --strict` 通过；
4. ownership schema 未削弱；
5. verify 当前状态并显示差异；
6. critical tamper 需要显式 flag，例如：
   - `--accept-current-owned-state`
7. 写 audit event；
8. 非交互场景需要审批 token；
9. 新写 manifest schema v2；
10. v1 manifest 可兼容读取，但新写 v2。

### 解决的绕过点

| 绕过点 | 解决方式 |
|---|---|
| H7：integrity 非阻断 | verify fail 默认 block |
| verify fail 后 auto re-sign | 明确禁止 |
| ownership.toml 可被削弱 | 纳入签名链 |
| delegate degraded 语义弱 | 携带错误，critical 默认 block |
| source repo readonly 副作用 | readonly 下不读写 manifest/signature |

### 验收标准

- 修改 `memory/kb/INDEX.md` 后 verify fail。
- 修改 `.memory/ownership.toml` 后 verify fail。
- 删除默认域并 re-sign 不得成功。
- verify fail 后 hook 不 re-sign。
- verify fail 后 manifest 不被覆盖。
- dedicated re-sign CLI 在 validate 通过时成功。
- critical tamper 未提供 `--accept-current-owned-state` 时 re-sign 拒绝。
- source repo readonly 下 integrity 不写任何文件。
- v1 manifest 可读，新写 manifest 为 v2。
- 无交互 verify fail 默认 block。

### 需修改的源文件

| 文件 | 改动 |
|---|---|
| `memory_core/tools/memory_hook_integrity_manifest.py` | ownership-derived 签名范围，schema v2 |
| `memory_core/tools/memory_hook_integrity_verify.py` | verify fail 不 re-sign，返回 block/degraded |
| `memory_core/tools/memory_hook_gateway.py` | integrity 失败语义接入 |
| `memory_core/tools/memory_hook_integrity_keys.py` | v2 key/manifest 支持 |
| `memory_core/tools/memory_integrity_resign.py` | 新增专用 re-sign CLI |
| `tests/test_l2_integrity_ownership.py` | ownership integrity 测试 |
| `tests/test_integrity_resign.py` | re-sign 安全规则测试 |
| `tests/test_source_repo_readonly_hooks.py` | readonly integrity 零副作用测试 |

---

## M5b：子代理 policy 注入 + cwd 固定 + P1 语义

### 目标

在 M5a P0 基础上完善语义：

- 子代理必须继承 ownership policy；
- cwd/project root 固定；
- Execute 解析增强；
- AGENTS.md block diff-aware；
- MultiEdit 多路径逐项分类；
- NoopHostDelegate 不吞失败；
- 外部 MCP 写入默认保守。

### 交付物

- Task payload policy injection。
- 子代理任务中自动注入 ownership policy block。
- 子代理 cwd 固定到项目 git root。
- PreToolUse 使用同一 project_root。
- P1 Execute 解析增强：
  - `mv`
  - `git mv`
  - `rm`
  - `cp`
  - `rsync`
  - redirect
  - heredoc
  - `tee`
  - `python -c`
  - `node -e`
  - shell glob
  - 相对路径
- AGENTS.md diff-aware marked block 判断。
- MultiEdit 多路径逐项分类。
- structured denial reason。
- NoopHostDelegate 策略修正：
  - host unavailable ≠ policy allow；
  - delegate exception ≠ success。
- `MEMORY_HOOK_FORCE` 不得 bypass ownership guard。
- 外部 core builder 不得替换 protection guard。
- 外部 MCP 写入类工具：
  - 目标 path owned：block；
  - 目标 path 不可见：默认 block；
  - read-only MCP 不阻断。

### 子代理 policy block

注入内容示例：

```text
Memory ownership policy is active.

Protected ownership domains:
- .memory/**: critical
- memory/**: protected
- project-map/**: critical

Protected resources:
- NOW.md
- INDEX.md if memory-managed
- AGENTS.md MEMORY_HOOK marked block
- .claude/hooks.json memory hook entries

You must not write, move, delete, overwrite, rename, migrate, or reorganize owned paths unless the parent explicitly provides an authorized maintenance token.

If asked to modify owned paths without authorization, report the block instead of attempting alternate tools.
```

### 解决的绕过点

| 绕过点 | 解决方式 |
|---|---|
| F2：子代理不继承 policy | Task payload 注入 |
| F3：外部 MCP/Execute | P1 Execute + MCP 写入保守策略 |
| H5：`MEMORY_HOOK_FORCE` | 不允许绕过 guard |
| H6：外部 builder | guard 不可替换 |
| H8：NoopHostDelegate | policy 与 delegate 分离 |
| H9：preflight 异常 | structured degraded/block |
| 子代理 cwd 漂移 | 固定 repo root |

### 验收标准

- Task 子代理 payload 包含 ownership policy。
- 子代理 cwd 固定为项目根或明确 safe cwd。
- Task 描述要求移动 `memory/kb/**` 时被 block 或 policy 明确拒绝。
- Execute 以下命令被 block：
  - `mv memory/kb tmp/`
  - `git mv memory/docs/design/a.md docs/a.md`
  - `cp x.md project-map/x.md`
  - `cat > memory/docs/INDEX.md`
  - `python -c 'Path("memory/kb/x.md").write_text("x")'`
  - heredoc 到 owned path
- `MEMORY_HOOK_FORCE=1` 不放行。
- delegate preflight exception 不返回假成功。
- Noop delegate 只表示 host unavailable，不表示 allow。
- MultiEdit 任一路径 owned 时阻断或按 policy 精确阻断。
- AGENTS.md block 外业务追加允许，block 内修改阻断。
- 未知 MCP 写操作默认 block。

### 需修改的源文件

| 文件 | 改动 |
|---|---|
| `memory_core/tools/factory_pretooluse_guard.py` | P1 语义、Task/MultiEdit/AGENTS diff-aware |
| `memory_core/tools/execute_command_guard.py` | Execute 解析增强 |
| `memory_core/tools/factory_global_hooks.py` | cwd/project root 固定 |
| `memory_core/tools/memory_hook_gateway.py` | policy injection |
| `memory_core/tools/memory_hook_impls.py` | delegate 失败语义 |
| `memory_core/tools/memory_hook_interfaces.py` | Noop/Delegate contract |
| `tests/test_factory_pretooluse_task_payload.py` | Task payload 测试 |
| `tests/test_execute_command_guard.py` | Execute P1 测试 |
| `tests/test_noop_host_delegate.py` | Noop delegate 测试 |
| `tests/test_subagent_cwd_policy.py` | cwd 固定测试 |

---

## M6：管辖域变更流程 + 旧项目迁移 + hook 升级策略

### 目标

把 ownership 架构落为可升级、可维护、可回滚、可审计的长期治理流程。

### 交付物

- 管辖域变更 CLI：
  - `memory-ownership show`
  - `memory-ownership validate`
  - `memory-ownership plan-update`
  - `memory-ownership apply-update`
- 或统一到：
  - `memory ownership show`
  - `memory ownership validate`
  - `memory ownership plan`
  - `memory ownership apply`
- 旧项目迁移：
  - 无 ownership.toml → 生成默认；
  - 旧 hooks → 升级到带 PreToolUse 的 wrapper/settings；
  - 旧 manifest v1 → 可读，下一次 authorized sign 写 v2。
- 旧 hook 升级策略：
  - 检测旧 wrapper；
  - 检测缺少 PreToolUse；
  - 检测 `|| true`；
  - 检测 `MEMORY_HOOK_FORCE` 直接 noop；
  - 检测 verify fail auto re-sign；
  - 生成 upgrade plan；
  - preserve unrelated hooks；
  - backup settings；
  - dry-run 默认；
  - apply 需要用户审批。
- 版本/兼容矩阵：
  - memory-core version；
  - ownership schema version；
  - hook schema version；
  - integrity manifest version；
  - minimum compatible hook installer version。
- 管辖域变更流程：
  1. plan；
  2. 用户授权；
  3. apply；
  4. 写 migrations.log / audit；
  5. validate；
  6. audit；
  7. integrity sign。
- 回滚策略：
  - settings backup restore；
  - ownership.toml backup；
  - manifest backup。
- release gate：
  - docs index consistency；
  - boundary check；
  - tests；
  - validate/audit。

### 旧项目迁移策略

旧项目状态：

| 项目状态 | ownership.toml | hook | 行为 |
|---|---:|---:|---|
| 新消费者项目 | 有 | 新 | full protection |
| 旧消费者项目 | 无 | 旧 | fallback block + migration plan |
| 旧消费者项目 | 无 | 无 | memory-init update 生成 ownership |
| memory-core 源码仓库 | 无 | readonly | context only，零写入 |
| unknown repo | 无 | unknown | memory-like paths 保守 block |

迁移流程：

1. `memory-ownership plan-update --target <project>`
2. 输出将新增/保护/签名的路径。
3. 不写文件。
4. 用户审批。
5. `memory-ownership apply-update`
6. 生成 `.memory/ownership.toml`
7. validate strict。
8. audit ownership。
9. integrity sign v2。

### hook 升级策略

检测：

- bare `memory-hook-gateway`
- 缺少 PreToolUse
- settings corrupt
- hook 文件缺失
- hook 版本低
- hook 中存在 `|| true`
- hook 中允许 `MEMORY_HOOK_FORCE` 直接绕过
- hook 中存在 verify fail auto re-sign
- Factory/Codex/Claude wrapper 不一致

升级：

1. inspect；
2. plan-upgrade；
3. backup；
4. preserve unrelated hooks；
5. apply；
6. validate settings；
7. run hook self-test；
8. audit。

禁止：

- hook runtime 静默自改；
- source repo readonly 自动升级；
- 覆盖 unrelated user hooks；
- 无 backup apply。

### 解决的绕过点

| 绕过点 | 解决方式 |
|---|---|
| 旧 hook 保留绕过 | inspect + plan/apply upgrade |
| 旧项目无 ownership | migration 生成 ownership |
| 版本不兼容 | compat matrix |
| escape hatch 混乱 | maintenance CLI + audit |
| 管辖域变更无流程 | plan → approve → apply → validate → audit |
| hook settings 覆盖风险 | preserve + backup + dry-run |
| source repo 被自动改写 | readonly 禁止 auto-upgrade |

### 验收标准

- 旧项目无 ownership.toml 时可生成 migration plan。
- migration plan 不写文件。
- apply 后生成默认 ownership。
- apply 后 validate strict 通过。
- 旧 Factory settings 可检测缺少 PreToolUse。
- hook upgrade plan 保留 unrelated hooks。
- apply-upgrade 前创建 backup。
- corrupt settings 不覆盖，报告 error。
- source repo readonly 下不 auto-upgrade。
- old manifest v1 可读，新 sign 写 v2。
- compat matrix fixtures 全覆盖。
- rollback 后 settings 与 backup 一致。

### 需修改的源文件

| 文件 | 改动 |
|---|---|
| `memory_core/tools/memory_ownership_cli.py` | 新增 ownership 管理 CLI |
| `memory_core/tools/hook_upgrade_plan.py` | 新增 hook inspect/plan/apply |
| `memory_core/tools/migrate_project_memory.py` | 迁移 ownership/hook/manifest |
| `memory_core/tools/factory_global_hooks.py` | hook upgrade 支持 |
| `memory_core/tools/codex_global_hooks.py` | hook upgrade 支持 |
| `memory_core/tools/claude_global_hooks.py` | hook upgrade 支持 |
| `tests/test_hook_upgrade_strategy.py` | hook upgrade 测试 |
| `tests/test_ownership_migration.py` | ownership migration 测试 |
| `tests/test_compat_matrix.py` | 兼容矩阵测试 |
| `tests/test_cli_migrate.py` | CLI migration 测试 |

---

# 9. 里程碑依赖关系图

```text
M1 Ownership model + classify API + defaults
  │
  ├──> M5a Factory PreToolUse P0 guard
  │       │
  │       ├──> M2 memory-init ownership.toml + validate/audit
  │       │       │
  │       │       └──> M4 ownership-aware integrity
  │       │
  │       └──> M5b subagent policy + cwd + Execute P1
  │
  └──> M3 source repo readonly context-package
          │
          ├──> M4 source repo no integrity side effects
          └──> M6 migration + hook upgrade + compat matrix
```

推荐执行顺序：

```text
M1 → M5a → M2 → M3 → M4 → M5b → M6
```

---

# 10. 总体风险矩阵

| 风险 | 等级 | 影响 | 缓解 |
|---|---:|---|---|
| Execute 命令解析不完整 | 高 | 通过 shell 间接写 owned path | P0/P1 均采用"不确定则 block"；覆盖 mv/cp/rm/git mv/python/redirection/heredoc |
| 裸环境变量 escape hatch 重现 H5 | 高 | 任意绕过保护 | escape hatch 必须绑定 maintenance CLI + reason + token + audit |
| source repo readonly 仍产生副作用 | 高 | 污染 memory-core 源码仓库 | M3 增加 git status、mtime、no-new-file 测试 |
| verify fail 后 auto re-sign | Critical | 篡改被合法化 | M4 禁止 hook 自动 re-sign，专用 CLI 显式确认 |
| ownership.toml 被削弱 | Critical | 保护域被删除或降级 | schema 防削弱 + PreToolUse block + validate error + integrity 签名 |
| AGENTS.md 共享文件误伤 | 中 | 阻止业务内容修改 | block-level diff 判断；无法判断时仅无交互保守 block |
| 旧项目无 ownership.toml | 中 | 升级误报或漏保 | 默认 fallback 三域保护，M6 migration 生成 |
| Factory settings 升级覆盖用户 hooks | 高 | 破坏用户配置 | merge preserve unrelated hooks + backup + dry-run |
| NoopHostDelegate 吞掉失败 | 高 | 假成功 | policy decision 与 delegate availability 分离 |
| 外部 core builder 替换保护逻辑 | 高 | 绕过 guard | ownership guard 不允许外部 provider 替换 |
| validate 读失败 continue | 中 | 漏检保护文件损坏 | owned critical/protected 读失败 error |
| 子代理不继承 policy | 高 | 重演事故 | PreToolUse 拦截 Task payload + policy injection + cwd 固定 |
| 外部 MCP 写入不可见 | 高 | 绕过 memory policy | 未知写入默认 block；路径不可见需审批 |
| memory-core 源码仓库误判为消费者项目 | 高 | 错误 takeover | 多条件 source repo detection + readonly side-effect tests |
| 旧 hook 静默继续运行 | 高 | 旧绕过点保留 | inspect/plan/apply upgrade + validate 检测旧模式 |
| docs/kb/project-map INDEX 漂移 | 中 | 文档治理失效 | validate/audit index consistency checks |
| 签名范围过大导致误报 | 中 | 频繁阻断正常 runtime | 区分 critical/protected/managed-runtime，先签治理关键文件 |

---

# 11. 总体验收标准

## 11.1 架构验收

- 存在统一 `classify_owned_path()` API。
- 所有保护判断复用该 API。
- `.memory/`、`memory/`、`project-map/` 三个默认管辖域递归受保护。
- `AGENTS.md` 仅保护 marked block，而非整文件。
- `.memory/ownership.toml` 有 schema 校验、防削弱、fallback。
- ownership.toml 纳入 integrity 签名链。
- 消费者项目和 memory-core 源码仓库策略分离明确。
- source repo readonly context-package 包含 DOT_MEMORY_SPEC、BOUNDARY、INDEX。
- READONLY 模式严格零副作用。

## 11.2 安全验收

- 非授权写入 owned paths 默认 block。
- 无交互场景不请求确认，默认 block。
- `MEMORY_HOOK_FORCE` 不可绕过 ownership guard。
- 外部 core builder 不可替换 protection guard。
- integrity verify fail 后不会自动 re-sign。
- 合法维护必须通过专用 CLI/flag，并记录 audit。
- 子代理 Task payload 涉及 owned paths 时被拦截或注入禁止策略。
- Execute 命令写入 owned paths 有覆盖测试。
- NoopHostDelegate 不再表示 policy allow。
- delegate preflight 异常不返回假成功。
- 外部 MCP 写入 owned path 默认 block。

## 11.3 工具链验收

- `memory-init` 生成 `.memory/ownership.toml`。
- `memory-init --force` 不再覆盖 owned domain 内容。
- `memory-validate` ownership-aware。
- `memory-audit-layout` ownership-aware。
- `memory-apply-residue-plan` ownership-aware。
- Hook installer 添加/升级 PreToolUse。
- 旧 hook 可 dry-run 生成升级计划。
- source repo readonly hook 严格零副作用。
- `.claude/hooks.json` memory hook 条目被 validate。
- `memory/docs/INDEX.md`、`memory/kb/INDEX.md`、`project-map/INDEX.md` 一致性被 validate/audit。

## 11.4 测试验收

完整验证建议：

```bash
ruff check .
python -m pytest tests/
python3 scripts/check_boundary.py
memory-validate --target /path/to/fixture --json
memory-audit-layout --target /path/to/fixture --json
```

分阶段关键测试：

```bash
python -m pytest tests/test_memory_ownership.py -q
python -m pytest tests/test_source_repo_detection.py -q
python -m pytest tests/test_factory_pretooluse_guard.py -q
python -m pytest tests/test_execute_command_guard.py -q
python -m pytest tests/test_init_ownership.py tests/test_validate_ownership.py -q
python -m pytest tests/test_audit_project_layout.py -q
python -m pytest tests/test_source_repo_readonly_hooks.py -q
python -m pytest tests/test_l2_integrity_ownership.py tests/test_integrity_resign.py -q
python -m pytest tests/test_factory_pretooluse_task_payload.py tests/test_noop_host_delegate.py -q
python -m pytest tests/test_hook_upgrade_strategy.py tests/test_ownership_migration.py tests/test_compat_matrix.py -q
```

## 11.5 事故复现验收

以下行为必须被阻止或明确 degraded：

1. 子代理尝试移动：
   - `memory/docs/design/*.md`
   - `memory/kb/**`
2. 消费者项目中尝试覆盖：
   - `memory/docs/INDEX.md`
   - `memory/kb/INDEX.md`
   - `project-map/INDEX.md`
   - `.memory/ownership.toml`
3. Execute 执行：
   - `mv memory/kb tmp/`
   - `git mv memory/docs/design/a.md docs/a.md`
   - `cp x.md project-map/x.md`
   - `python -c 'open("memory/docs/INDEX.md","w").write("x")'`
4. `memory-init --force` 覆盖 owned files。
5. `MEMORY_HOOK_FORCE=1` 尝试绕过 owned write。
6. integrity verify failed 后 hook 自动 re-sign。
7. source repo readonly hook 试图写 artifact/manifest/health-report。
8. NoopHostDelegate 吞掉 policy failure。

预期结果：

- 默认 block；
- 非零退出或 structured denial；
- 不 silent success；
- 不 auto repair；
- 不 auto re-sign；
- 不产生源码仓库副作用。

---

# 12. 最终执行规则

1. 严格按以下顺序执行：

   ```text
   M1 → M5a → M2 → M3 → M4 → M5b → M6
   ```

2. 每个里程碑开始前必须获得用户明确审批。

3. 每个里程碑必须独立可验证，不能依赖后续里程碑补救当前安全缺口。

4. M5a 必须前置到 M1 之后立即执行，不能放到后期。

5. PreToolUse 是强制安全门，不得依赖模型自觉遵守 policy。

6. 无交互场景一律默认 block，不得默认 allow。

7. `MEMORY_HOOK_FORCE` 不得绕过 ownership guard。

8. 合法维护必须通过：

   - dedicated maintenance CLI；
   - explicit reason；
   - scoped token 或显式审批 flag；
   - audit event；
   - validate；
   - audit；
   - integrity sign。

9. verify 失败后禁止 hook runtime 自动 re-sign。

10. source repo readonly 模式必须零副作用：

    - 不创建文件；
    - 不修改文件；
    - 不更新 mtime；
    - 不写 artifact；
    - 不写 manifest；
    - 不写 health-report；
    - 不 upgrade hooks；
    - 不 re-sign。

11. 子代理必须注入 ownership policy，并固定 cwd/project root。

12. 外部 MCP 写入工具如无法提供目标 path，默认 block。

13. `memory-init --force` 不再是通用覆盖开关，对 owned domain 无默认覆盖权。

14. `AGENTS.md` 采用 marked block 子资源保护，不锁死业务内容。

15. 旧项目迁移和 hook 升级必须 plan/apply 分离：

    - plan 不写文件；
    - apply 需要审批；
    - apply 前 backup；
    - preserve unrelated user hooks。

16. 每个里程碑完成后至少运行对应单测和 lint。

17. 全部完成后运行：

    ```bash
    ruff check .
    python -m pytest tests/
    python3 scripts/check_boundary.py
    ```

18. 所有变更完成后再统一提交，避免中间态作为长期状态存在。

19. 不得在本计划之外额外迁移、重排或重写文档路径。

20. 不得在未获明确授权时修改 README、docs 或规范文档；文档更新应作为单独审批事项执行。
