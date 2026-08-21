"""Planning and state tracking templates."""

import logging
from datetime import UTC

logger = logging.getLogger(__name__)

def _now_iso() -> str:
    """Return current date in ISO format (YYYY-MM-DD)."""
    from datetime import datetime
    return datetime.now(UTC).strftime("%Y-%m-%d")


def template_plan_md(project_name: str) -> tuple[str, list[str]]:
    """Generate PLAN.md content — project plan file.

    Records current iteration/task execution plan, milestones, acceptance criteria.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    now = _now_iso()
    try:
        content = f"""\
# PLAN.md — 项目计划文件
# 作用：记录当前迭代/任务的执行计划、里程碑、验收标准

## 任务概述

- **任务 ID**：{{TASK_ID}}
- **任务名称**：{{TASK_NAME}}
- **优先级**：{{PRIORITY}}
- **创建日期**：{now}

## 目标

{{GOALS}}

## 执行计划

| 步骤 | 描述 | 状态 | 完成日期 |
|------|------|------|----------|
| 1    | {{STEP_1}} | pending | - |
| 2    | {{STEP_2}} | pending | - |

## 验收标准

{{ACCEPTANCE_CRITERIA}}

## 风险与依赖

{{RISK_AND_DEPENDENCIES}}

## 状态

- **当前状态**：planning
- **上次更新**：{now}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in PLAN.md: {exc}")
        warnings.append(f"template_plan_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# PLAN.md — 项目计划文件

## 任务概述

- **任务 ID**：{{TASK_ID}}
- **任务名称**：{{TASK_NAME}}
- **优先级**：{{PRIORITY}}
- **创建日期**：{{CREATED_AT}}

## 目标

{{GOALS}}

## 执行计划

| 步骤 | 描述 | 状态 | 完成日期 |
|------|------|------|----------|
| 1    | {{STEP_1}} | pending | - |
| 2    | {{STEP_2}} | pending | - |

## 验收标准

{{ACCEPTANCE_CRITERIA}}

## 风险与依赖

{{RISK_AND_DEPENDENCIES}}

## 状态

- **当前状态**：planning
- **上次更新**：{{UPDATED_AT}}
"""
    return content, warnings


def template_state_md(project_name: str) -> tuple[str, list[str]]:
    """Generate STATE.md content — project state file.

    Records current state, context summary, key decisions.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    now = _now_iso()
    try:
        content = f"""\
# STATE.md — 项目状态文件
# 作用：记录业务项目的当前状态、上下文摘要、关键决策

## 项目状态

- **状态**：{{STATUS}}
- **最后更新**：{now}
- **健康度**：{{HEALTH}}

## 上下文摘要

{{CONTEXT_SUMMARY}}

## 关键决策

| 日期 | 决策 | 理由 |
|------|------|------|
| {now} | {{DECISION}} | {{RATIONALE}} |

## 当前工作区

{{CURRENT_WORKSPACE}}

## 待处理事项

{{PENDING_ITEMS}}

## 已完成的里程碑

{{COMPLETED_MILESTONES}}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in STATE.md: {exc}")
        warnings.append(f"template_state_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# STATE.md — 项目状态文件

## 项目状态

- **状态**：{{STATUS}}
- **最后更新**：{{LAST_UPDATED}}
- **健康度**：{{HEALTH}}

## 上下文摘要

{{CONTEXT_SUMMARY}}

## 关键决策

| 日期 | 决策 | 理由 |
|------|------|------|
| {{DATE}} | {{DECISION}} | {{RATIONALE}} |

## 当前工作区

{{CURRENT_WORKSPACE}}

## 待处理事项

{{PENDING_ITEMS}}

## 已完成的里程碑

{{COMPLETED_MILESTONES}}
"""
    return content, warnings


def template_tasks_md(project_name: str) -> tuple[str, list[str]]:
    """Generate TASKS.md content — task list file.

    Tracks all tasks, subtasks, and statuses for the current project.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        content = """\
# TASKS.md — 任务清单文件
# 作用：跟踪当前项目下的所有任务、子任务、状态

## 活跃任务

| ID | 任务 | 优先级 | 状态 | 负责人 | 截止日期 |
|----|------|--------|------|--------|----------|
| T-001 | {{TASK_1}} | P2 | pending | {{ASSIGNEE}} | {{DUE}} |

## 已完成任务

| ID | 任务 | 完成日期 | 备注 |
|----|------|----------|------|
| - | - | - | - |

## 已取消任务

| ID | 任务 | 取消原因 |
|----|------|----------|
| - | - | - |

## 阻塞项

{{BLOCKERS}}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in TASKS.md: {exc}")
        warnings.append(f"template_tasks_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# TASKS.md — 任务清单文件

## 活跃任务

| ID | 任务 | 优先级 | 状态 | 负责人 | 截止日期 |
|----|------|--------|------|--------|----------|
| T-001 | {{TASK_1}} | P2 | pending | {{ASSIGNEE}} | {{DUE}} |

## 已完成任务

| ID | 任务 | 完成日期 | 备注 |
|----|------|----------|------|
| - | - | - | - |

## 已取消任务

| ID | 任务 | 取消原因 |
|----|------|----------|
| - | - | - |

## 阻塞项

{{BLOCKERS}}
"""
    return content, warnings


def template_now_md(project_name: str) -> tuple[str, list[str]]:
    """Generate NOW.md content — current workspace status file.

    Provides a snapshot of current mission, today's work, next actions, and blockers.

    Returns:
        Tuple of (content, warnings_list)
    """
    warnings: list[str] = []
    try:
        content = """\
# NOW.md

## Mission
- {{MISSION}}

## Today
- {{TODAY}}

## Next 3 Actions
1. {{ACTION_1}}
2. {{ACTION_2}}
3. {{ACTION_3}}

## Blockers
- {{BLOCKERS}}
"""
    except (ValueError, TypeError) as exc:
        logger.warning(f"Template render error in NOW.md: {exc}")
        warnings.append(f"template_now_md: {exc}")
        content = """\
# RENDERING-INCOMPLETE: 见 warnings 列表 / FAILED_RENDER
# NOW.md

## Mission
- {{MISSION}}

## Today
- {{TODAY}}

## Next 3 Actions
1. {{ACTION_1}}
2. {{ACTION_2}}
3. {{ACTION_3}}

## Blockers
- {{BLOCKERS}}
"""
    return content, warnings


