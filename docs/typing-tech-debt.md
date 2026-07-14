# Typing Technical Debt Tracker

> mypy --strict 技术债务追踪与迁移路线图
> 
> Last updated: 2026-07-14

## Baseline Status

**Initial baseline (v0.9.0):** 220 errors across 36 files  
**Current error count:** 193 errors in 19 files  
**Progress:** 27 errors fixed (12% reduction)  
**Strict overrides:** 18 modules configured with `strict = true`

## Strategy

采用分阶段迁移策略，优先修复最简单的文件（unused-ignore、no-any-return 模式），逐步增加严格检查覆盖。

### Phase 1 (已完成 - v0.9.0)

✅ 添加 advisory-typing CI job (continue-on-error，不阻塞合并)  
✅ 建立基线：220 errors  
✅ 修复 18 个最简单文件：
- 移除无效的 `# type: ignore` 注释 (unused-ignore)
- 修复返回类型声明 (no-any-return)
- 添加显式类型注解 (no-untyped-def)

✅ 为 18 个已修复模块添加 `[[tool.mypy.overrides]]` 严格配置

**已修复模块列表 (18个):**
```
memory_core.tools
memory_core.tools.adapter_toml_schema
memory_core.tools.apply_residue_plan
memory_core.tools.auto_capture
memory_core.tools.business_policy_checks
memory_core.tools.error_logger
memory_core.tools.global_kb_init
memory_core.tools.hook_event_stats
memory_core.tools.memory_health_report
memory_core.tools.memory_hook_adapters.default_runtime_profile
memory_core.tools.memory_hook_adapters.neutral_policy
memory_core.tools.memory_hook_integrity_verify
memory_core.tools.resilient_orchestrator
memory_core.tools.session_end_logger
memory_core.tools.task_dispatcher
memory_core.tools.telemetry_bridge
memory_core.tools.verify_consumer
memory_core.tools.version_sync
```

## Phase 2: 中等难度文件 (v0.10.0 目标)

**目标:** 修复 10-15 个中等复杂度文件，将错误数降至 <150

### 待修复文件 (按错误数排序)

| 文件 | 错误数 | 主要错误类型 | 优先级 | 目标日期 |
|------|--------|------------|--------|---------|
| `tools/memory_hook_gateway.py` | 69 | name-defined (动态导入), type-arg | P2 | 2026-08-15 |
| `tools/denylist.py` | 19 | no-any-return | P2 | 2026-08-01 |
| `tools/consistency_check.py` | 19 | name-defined, type-arg | P2 | 2026-08-01 |
| `tools/validate_memory_system.py` | 15 | unused-ignore | P2 | 2026-07-25 |
| `tools/audit_project_layout.py` | 8 | name-defined, attr-defined | P2 | 2026-07-25 |
| `tools/memory_hook_schema.py` | 7 | name-defined | P2 | 2026-07-25 |
| `tools/posthog_client.py` | 6 | arg-type, attr-defined | P3 | 2026-08-15 |
| `tools/project_probe.py` | 5 | name-defined | P3 | 2026-08-15 |
| `tools/memory_hook_integrity_manifest.py` | 5 | name-defined | P3 | 2026-08-15 |
| `tools/daily_summary_generator.py` | 5 | no-any-return, unused-ignore | P3 | 2026-08-01 |

**预计修复后:** 193 - 163 = 30 errors remaining

### 技术难点

#### 1. 动态导入模式 (name-defined)

`memory_hook_gateway.py` 使用动态导入加载 hook 实现，导致 mypy 无法静态分析：

```python
# 当前模式
module = importlib.import_module(f"memory_hook_{hook_type}")
handler = getattr(module, "handle")  # mypy: name-defined
```

**解决方案:**
- 使用 `Protocol` 定义 hook 接口
- 添加 `TYPE_CHECKING` 条件导入提供类型提示
- 或使用 `cast()` 显式声明返回类型

#### 2. 泛型类型参数缺失 (type-arg)

多个文件使用 `list`, `dict` 等泛型容器但未指定类型参数：

```python
# 当前
def process(items: list) -> None:  # mypy: type-arg

# 修复
def process(items: list[str]) -> None:
```

#### 3. 返回 Any 类型 (no-any-return)

函数返回动态获取的值（如 JSON 解析结果），需要显式类型转换：

```python
# 当前
def get_config() -> dict:
    return json.loads(data)  # mypy: no-any-return

# 修复
def get_config() -> dict:
    result = json.loads(data)
    assert isinstance(result, dict)
    return result
```

## Phase 3: 复杂文件 (v0.11.0 目标)

**目标:** 修复剩余高错误数文件，错误数 <50

### 待修复文件

| 文件 | 错误数 | 主要挑战 | 目标日期 |
|------|--------|---------|---------|
| `tools/cmux_hook_state.py` | 5 | 复杂状态管理 | 2026-09-01 |
| `ownership.py` | 5 | 所有权逻辑复杂 | 2026-09-01 |
| `tools/ownership_cli.py` | 4 | CLI 参数类型 | 2026-09-01 |
| `tools/observability.py` | 4 | 观测性数据结构 | 2026-09-01 |
| `tools/migrate_project_memory.py` | 4 | 迁移逻辑复杂 | 2026-09-01 |
| `tools/memory_hook_core.py` | 4 | 核心逻辑 | 2026-09-01 |
| `tools/daily_kb_audit.py` | 4 | 审计逻辑 | 2026-09-01 |
| `tools/init_project_memory.py` | 3 | 初始化流程 | 2026-09-01 |
| `tools/memory_hook_impls.py` | 2 | 实现细节 | 2026-09-01 |

**预计修复后:** 30 - 36 = 0 errors (全部清零)

## Error Type Breakdown

当前 193 个错误的类型分布：

| 错误类型 | 数量 | 说明 | 修复难度 |
|---------|------|------|---------|
| name-defined | 61 | 动态导入/运行时定义的符号 | 中 |
| type-arg | 32 | 泛型容器缺少类型参数 | 低 |
| unused-ignore | 21 | 无效的 `# type: ignore` 注释 | 低 |
| no-any-return | 13 | 返回 Any 类型 | 低-中 |
| assignment | 10 | 类型不兼容的赋值 | 中 |
| arg-type | 10 | 函数参数类型不匹配 | 中 |
| no-untyped-def | 9 | 函数缺少类型注解 | 低 |
| attr-defined | 8 | 访问未定义的属性 | 中 |
| misc | 7 | 其他杂项错误 | 变化 |
| operator | 6 | 运算符类型不兼容 | 中 |
| no-untyped-call | 5 | 调用未类型化的函数 | 低 |
| dict-item | 5 | 字典值类型不匹配 | 中 |
| has-type | 2 | 类型推断冲突 | 低 |
| union-attr | 1 | Union 类型属性访问 | 低 |
| str-unpack | 1 | 字符串解包错误 | 低 |
| return-value | 1 | 返回值类型不匹配 | 低 |
| no-redef | 1 | 重复定义 | 低 |

## Monitoring

### CI 集成

- `advisory-typing` job 每次 PR 运行 `mypy --strict memory_core/`
- 使用 `continue-on-error: true` 确保不阻塞合并
- 错误报告写入 `mypy-report.txt` artifact

### 进度追踪

每个 Phase 完成后更新：
- 本文档的 "Baseline Status" 部分
- 修复模块列表
- 错误数统计

### 验证命令

```bash
# 检查当前错误数
python3 -m mypy --strict memory_core/ 2>&1 | grep -cE 'error:'

# 检查特定模块是否通过严格检查
python3 -m mypy --strict memory_core/tools/denylist.py

# 查看已配置严格模式的模块
python3 -c "
import tomllib
with open('pyproject.toml','rb') as f:
    d = tomllib.load(f)
for o in d.get('tool',{}).get('mypy',{}).get('overrides',[]):
    if o.get('strict') or any(k.startswith('disallow') for k in o):
        print(o.get('module', o.get('modules', [])))
"
```

## Rollback Plan

如果严格模式导致 CI 不稳定：

1. 移除 `pyproject.toml` 中的 `[[tool.mypy.overrides]]` 部分
2. 删除 `.github/workflows/ci.yml` 中的 `advisory-typing` job
3. 恢复到 v0.8.0 的非严格 mypy 配置

## References

- mypy 文档: https://mypy.readthedocs.io/
- Python 类型提示 PEP: PEP 484, PEP 526, PEP 586
- 项目 mypy 配置: `pyproject.toml` [tool.mypy]
- CI 配置: `.github/workflows/ci.yml` advisory-typing job
