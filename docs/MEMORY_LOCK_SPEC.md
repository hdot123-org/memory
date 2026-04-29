---
type: "[SPEC]"
title: "memory.lock 与版本兼容矩阵"
shortname: SPEC-010
status: 草稿
created: 2026-04-29
updated: 2026-04-29
source: Issue-#10
scope: default
tags: [lock,version,compatibility]
---

> 文档编号：SPEC-010 | 版本：V1.0 | 日期：2026-04-29
> 维护人：P3-版本子代理
> 状态：草稿

# memory.lock 与版本兼容矩阵规范

## 1. 目的

为 memory-core 消费者项目提供统一的版本声明与兼容性判断机制，
使主线程能够：

1. 快速判断项目是否落后于 memory-core 当前发布版本
2. 识别升级类型（patch / minor / major）
3. 不读取项目真实 STATE/PLAN 正文即可做出决策

## 2. memory.lock Schema

### 2.1 文件位置

每个消费者项目根目录或 .memory/ 下必须存在一个 memory.lock 文件。

### 2.2 字段定义

memory.lock 是 TOML 格式文件，包含以下字段：

```toml
# memory.lock -- 项目与 memory-core 的版本绑定文件

[memory]
# memory-core 发布版本号（SemVer），项目当前集成的版本
memory_version = "0.1.0"

# 项目使用的 memory hook schema 版本标识符
# 与 memory-core 内部 schema 版本号对应
schema_version = "wb-hook-v2"

# adapter 版本号（如果项目使用自定义 adapter）
# 不使用自定义 adapter 时可省略或设为 "builtin"
adapter_version = "builtin"

# 锁定时间（UTC ISO-8601）
locked_at = "2026-04-29T00:00:00Z"

# 锁定原因（可选）：首次集成 / 升级 / 降级
lock_reason = "initial"
```

### 2.3 字段详解

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| memory_version | SemVer string | 是 | memory-core 的发布版本，如 0.1.0 |
| schema_version | string | 是 | hook/schema 版本标识，如 wb-hook-v2、context-package-v1 |
| adapter_version | string | 否 | adapter 版本，默认 builtin |
| locked_at | ISO-8601 | 否 | 最后锁定/升级时间 |
| lock_reason | string | 否 | 锁定原因枚举 |

### 2.4 版本约束

- memory_version 必须严格遵循 SemVer：MAJOR.MINOR.PATCH
- schema_version 必须是 memory-core 已发布的合法 schema 标识
- adapter_version 如果是自定义 adapter，格式为 <adapter-name>-<version>

## 3. 兼容矩阵

### 3.1 矩阵格式

兼容矩阵以 TOML 形式维护，可在 memory 仓库的 docs/COMPATIBILITY_MATRIX.md 中。

```toml
# 兼容矩阵示例

[[compat]]
memory_version = "0.1.0"
schema_versions = ["wb-hook-v2", "context-package-v1"]
adapter_versions = ["builtin"]
status = "stable"

[[compat]]
memory_version = "0.2.0"
schema_versions = ["context-package-v1"]
adapter_versions = ["builtin", "custom-adapter-v1"]
status = "stable"

[[compat]]
memory_version = "1.0.0"
schema_versions = ["context-package-v2"]
adapter_versions = ["builtin", "custom-adapter-v1", "custom-adapter-v2"]
status = "beta"
```

### 3.2 状态枚举

| status | 含义 |
|--------|------|
| stable | 生产可用，向后兼容 |
| beta | 可用但可能有 breaking change |
| deprecated | 已弃用，应尽快升级 |
| incompatible | 不兼容，必须升级 |

### 3.3 兼容性判断规则

```
给定项目 lock 文件 (M_lock, S_lock, A_lock)
和 memory-core 当前发布 (M_cur, S_cur, A_cur)：

1. 完全兼容：M_lock == M_cur 且 S_lock in S_cur 且 A_lock in A_cur
2. 可升级：M_lock < M_cur（SemVer 比较）
3. 不兼容：S_lock not in S_cur 或 A_lock not in A_cur
4. 落后：M_lock < M_cur
```

## 4. 判断项目是否落后

### 4.1 判断逻辑

```python
def is_behind(project_lock: dict, latest_release: str) -> bool:
    """判断项目是否落后于最新版本。
    仅比较 memory_version 的 SemVer，不读取项目任何业务文件。
    """
    from packaging.version import Version
    return Version(project_lock["memory_version"]) < Version(latest_release)
```

### 4.2 操作步骤

1. 读取项目 memory.lock 获取 memory_version
2. 查询 memory-core 最新发布版本（git tag 或 PyPI）
3. SemVer 比较：项目版本 < 最新版本 -> 落后

### 4.3 不读取项目正文

整个判断过程只读取 memory.lock 文件，
不读取 PLAN.md、STATE.md、代码文件或任何业务数据。

## 5. 判断升级类型

### 5.1 SemVer 升级分类

```python
def classify_upgrade(current: str, target: str) -> str:
    """返回 patch / minor / major 升级类型。"""
    from packaging.version import Version
    c, t = Version(current), Version(target)
    if t.major > c.major:
        return "major"
    if t.minor > c.minor:
        return "minor"
    if t.micro > c.micro:
        return "patch"
    return "none"
```

### 5.2 升级类型与行为

| 类型 | 含义 | 预期行为 |
|------|------|----------|
| patch | bug 修复 | 直接替换，无需 migration |
| minor | 向后兼容的功能增加 | 可能需要可选 migration |
| major | breaking change | 必须执行 migration，需要测试 |

### 5.3 升级决策树

```
memory.lock -> 对比最新版本
    |
    +-- none -> 无需操作
    |
    +-- patch -> 直接更新 memory_version
    |             更新 locked_at
    |
    +-- minor -> 检查 schema_version 是否变化
    |             +-- 未变 -> 更新 memory_version + locked_at
    |             +-- 变化 -> 需要 migration（见 MIGRATION_FORMAT_SPEC.md）
    |
    +-- major -> 必须执行 migration
                  更新所有三个版本字段
                  需要运行完整测试
```

## 6. templates/.memory/memory.lock 模板

模板文件位于 templates/.memory/memory.lock，内容如下：

```toml
# memory.lock -- 项目与 memory-core 的版本绑定
# 复制此文件到项目根目录或 .memory/ 目录下
# 然后根据实际集成的版本修改各字段

[memory]
memory_version = "0.0.0"
schema_version = ""
adapter_version = "builtin"
locked_at = ""
lock_reason = ""
```

## 7. 发布流程（不读取项目真实 STATE）

当 memory-core 发布新版本时：

1. 更新兼容矩阵：在矩阵中添加新版本行
2. 更新模板：如有新字段则更新模板
3. 生成升级卡片：扫描所有项目 memory.lock，生成升级任务卡
4. 不读取任何项目的 PLAN.md、STATE.md 或代码

发布决策完全基于 memory.lock 和兼容矩阵。

## 8. 验收标准

- [x] 能通过读取 memory.lock 判断项目是否落后
- [x] 能通过 SemVer 比较判断升级类型（patch/minor/major）
- [x] 判断过程不读取项目真实 STATE/PLAN 正文
- [x] 模板文件已更新匹配 schema
- [x] 兼容矩阵格式明确
