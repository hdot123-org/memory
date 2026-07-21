# globals().update 动态注入导致 mypy 无法静态解析

> Type: [KB:LESSON]
> Title: gateway globals().update 动态注入导致 mypy name-defined errors
> Status: active
> Created: 2026-07-21
> Source: mypy 183→0 mission M2
> Confidence: high
> Tags: [lesson, mypy, globals, type-checking, dynamic-injection, gateway]
> Related: [D-005-mypy-type-safety-completion]

## 问题

`memory_hook_gateway.py` 在运行时通过 `globals().update(profile)` 动态注入 ~45 个常量名（如 `HOOK_VERSION`、`PROJECT_ROOT`、`MEMORY_ROOT` 等），mypy 无法静态追踪这些名字，报 **47 个 name-defined errors**：

```
memory_core/tools/memory_hook_gateway.py:234: error: Name "HOOK_VERSION" is not defined  [name-defined]
memory_core/tools/memory_hook_gateway.py:312: error: Name "PROJECT_ROOT" is not defined  [name-defined]
...
```

这些常量在运行时确实存在（由 `profile` 字典注入），但 mypy 在静态分析时看不到它们的定义。

## 根因

### 动态注入模式

```python
def _load_profile() -> dict:
    profile = {
        "HOOK_VERSION": "5.0",
        "PROJECT_ROOT": Path("/path/to/project"),
        "MEMORY_ROOT": Path("/path/to/memory"),
        # ... ~45 个常量
    }
    globals().update(profile)  # 动态注入到模块全局命名空间
```

### mypy 的静态分析限制

mypy 是静态类型检查器，无法追踪 `globals().update()` 这种运行时动态修改模块命名空间的操作。它需要在代码中看到变量的定义或声明，才能确认名字有效。

### 错误规模

- **47 个 name-defined errors**（占 M2 总量 84 errors 的 56%）
- 涉及 ~45 个常量名，散布在 gateway.py 的 100+ 处使用点
- 如果不正确处理，后续新增常量会继续产生 name-defined errors

## 解决方案

### 采用 TYPE_CHECKING 块声明常量类型

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 声明动态注入的常量类型，供 mypy 静态检查
    HOOK_VERSION: str
    PROJECT_ROOT: Path
    MEMORY_ROOT: Path
    # ... ~45 个常量类型声明
```

### 关键权衡：为什么不重构 globals().update

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| TYPE_CHECKING 块 | 零运行时改动，+58/-3 行 | 需要手动维护类型声明 | ✅ 采用 |
| 重构为显式 config store | 类型安全，静态可追踪 | 破坏性重构，影响 100+ 调用点 | ❌ 放弃 |
| 每个使用点 `# type: ignore` | 快速修复 | 47 个 ignore 散布，维护成本高 | ❌ 放弃 |

**选择理由**：
- **零运行时风险**：TYPE_CHECKING 块只在 mypy 检查时生效，运行时行为完全不变
- **最小改动量**：PR #177 仅 +58/-3 行，PR #178 修复剩余 37 errors 仅 +10/-11 行
- **集中管理**：所有类型声明集中在文件顶部，便于审计和更新

### 实施结果

- PR #177：修复 53 errors（主要是 name-defined）
- PR #178：修复剩余 37 errors（主要是 TypedDict 和 cast）
- **mypy 从 84 → 0 errors**（gateway.py 单文件归零）

## 教训

1. **globals().update 是 mypy 盲点**：任何通过 `globals().update()` 或 `globals()[name] = value` 动态注入的名字都会触发 name-defined errors。这是 mypy 的固有限制，无法通过配置绕过。

2. **TYPE_CHECKING 是标准解决方案**：对于无法重构的动态注入模式，TYPE_CHECKING 块是最小侵入的解决方案。它让 mypy 看到类型声明，同时保持运行时行为不变。

3. **避免大规模重构**：如果动态注入模式已经稳定（如 gateway.py 的 profile 加载），重构为显式 config store 的成本远大于收益。优先选择 TYPE_CHECKING 块，而非破坏性重构。

4. **集中管理类型声明**：将所有 TYPE_CHECKING 声明集中在文件顶部（或独立 `_types.py` 模块），便于审计和更新。避免 `# type: ignore` 散布在代码中。

5. **适用场景识别**：
   - ✅ 适用：动态注入的常量名字典、延迟加载的模块属性、运行时生成的配置
   - ❌ 不适用：静态可追踪的变量、函数参数、类属性

## 修复 PR

- PR #177: `fix: 修复 memory_hook_gateway.py name-defined 错误`（53 errors）
- PR #178: `fix: 修复 memory_hook_gateway.py 剩余 9 个 mypy errors`（37 errors）

## Verification Refs

- 类型声明位置：`memory_core/tools/memory_hook_gateway.py:1-60`（TYPE_CHECKING 块）
- 动态注入逻辑：`memory_core/tools/memory_hook_gateway.py:_load_profile()`
- 验证命令：`mypy memory_core/tools/memory_hook_gateway.py`（0 errors）
