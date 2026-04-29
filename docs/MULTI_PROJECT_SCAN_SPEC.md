---
type: "[SPEC]"
title: "多项目升级扫描：只读 registry 指针"
shortname: SPEC-012
status: 草稿
created: 2026-04-29
updated: 2026-04-29
source: Issue-#12
scope: default
tags: [scan,registry,readonly,multi-project]
---

> 文档编号：SPEC-012 | 版本：V1.0 | 日期：2026-04-29
> 维护人：P3-版本子代理
> 状态：草稿

# 多项目升级扫描：只读 registry 指针规范

## 1. 目的

定义多项目扫描的 registry 格式与输出规范，使主线程能够：

1. 扫描所有消费者项目的版本状态
2. 生成可执行的任务卡
3. 全程只读，不修改任何项目

## 2. registry 字段规范

### 2.1 什么是 registry

registry 是 memory-core 维护的消费者项目索引，记录每个项目的：

- 本地路径或远程仓库地址
- 当前 memory.lock 版本指针
- 与最新版本的差距

### 2.2 registry 格式

registry 是 TOML 格式的索引文件，位于 memory 仓库中：

```toml
# registry.toml

[[project]]
name = "workbot"
local_path = "/Users/busiji/tool/workbot"
repo = "https://github.com/hdot123/workbot"
memory_lock = { memory_version = "0.1.0", schema_version = "wb-hook-v2", adapter_version = "builtin" }

[[project]]
name = "axonhub"
local_path = "/Users/busiji/tool/axonhub"
repo = "https://github.com/hdot123/axonhub"
memory_lock = { memory_version = "0.1.0", schema_version = "context-package-v1", adapter_version = "builtin" }

[[project]]
name = "codex"
local_path = "/Users/busiji/.codex"
repo = "https://github.com/openai/codex"
memory_lock = { memory_version = "0.2.0", schema_version = "context-package-v1", adapter_version = "custom-adapter-v1" }
```

### 2.3 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 项目简称，唯一标识 |
| local_path | string | 否 | 本地文件系统路径 |
| repo | string | 否 | 远程仓库 URL |
| memory_lock | object | 是 | 版本指针（从 memory.lock 读取） |
| memory_lock.memory_version | SemVer | 是 | memory-core 版本 |
| memory_lock.schema_version | string | 是 | schema 版本 |
| memory_lock.adapter_version | string | 否 | adapter 版本，默认 builtin |

### 2.4 指针格式（memory_lock 对象）

memory_lock 是从各项目 memory.lock 文件提取的版本指针：

```toml
memory_lock = { memory_version = "0.1.0", schema_version = "wb-hook-v2", adapter_version = "builtin" }
```

### 2.5 registry 不包含的内容

registry **禁止**包含以下业务数据：

- 项目的 PLAN.md 正文
- 项目的 STATE.md 正文
- 项目的代码文件内容
- 项目的业务配置
- 项目的任务详情

registry 只包含：

- 项目位置（路径/repo）
- 版本指针（memory.lock 内容）

## 3. 扫描流程

### 3.1 扫描步骤

```
1. 读取 registry.toml
    |
2. 对每个项目：
    |   |
    |   +-- 读取项目 memory.lock（只读）
    |   +-- 提取版本指针
    |   +-- 对比 memory-core 最新版本
    |   +-- 判断升级类型（patch/minor/major）
    |   +-- 记录结果
    |
3. 生成扫描报告
```

### 3.2 只读保证

- 扫描过程只使用 `read` 操作
- 不写入任何项目文件
- 不修改任何 git 状态
- 不触发任何 CI/CD

## 4. 扫描输出格式

### 4.1 扫描报告

扫描报告是 JSON 格式，可直接转为主线程任务卡：

```json
{
  "scan_id": "SCAN-20260429-001",
  "scanned_at": "2026-04-29T12:00:00Z",
  "memory_core_latest": "0.2.0",
  "compat_matrix_version": "v1.0",
  "projects": [
    {
      "name": "workbot",
      "local_path": "/Users/busiji/tool/workbot",
      "repo": "https://github.com/hdot123/workbot",
      "current": {
        "memory_version": "0.1.0",
        "schema_version": "wb-hook-v2",
        "adapter_version": "builtin"
      },
      "status": "behind",
      "upgrade_type": "minor",
      "compat_status": "compatible",
      "requires_migration": true,
      "task_card": {
        "title": "升级 workbot memory-core 0.1.0 -> 0.2.0",
        "priority": "P3",
        "type": "minor-upgrade",
        "actions": ["execute migration 002", "update memory.lock", "run tests"]
      }
    },
    {
      "name": "axonhub",
      "local_path": "/Users/busiji/tool/axonhub",
      "repo": "https://github.com/hdot123/axonhub",
      "current": {
        "memory_version": "0.1.0",
        "schema_version": "context-package-v1",
        "adapter_version": "builtin"
      },
      "status": "behind",
      "upgrade_type": "minor",
      "compat_status": "compatible",
      "requires_migration": false,
      "task_card": {
        "title": "升级 axonhub memory-core 0.1.0 -> 0.2.0",
        "priority": "P3",
        "type": "minor-upgrade",
        "actions": ["update memory.lock", "run tests"]
      }
    },
    {
      "name": "codex",
      "local_path": "/Users/busiji/.codex",
      "repo": "https://github.com/openai/codex",
      "current": {
        "memory_version": "0.2.0",
        "schema_version": "context-package-v1",
        "adapter_version": "custom-adapter-v1"
      },
      "status": "current",
      "upgrade_type": "none",
      "compat_status": "stable",
      "requires_migration": false,
      "task_card": null
    }
  ]
}
```

### 4.2 输出字段

| 字段 | 说明 |
|------|------|
| scan_id | 扫描唯一标识 |
| scanned_at | 扫描时间 |
| memory_core_latest | memory-core 最新版本 |
| compat_matrix_version | 兼容矩阵版本 |
| projects[] | 项目列表 |
| projects[].status | current/behind/deprecated/incompatible |
| projects[].upgrade_type | none/patch/minor/major |
| projects[].compat_status | stable/beta/deprecated/incompatible |
| projects[].requires_migration | 是否需要 migration |
| projects[].task_card | 可转为主线程任务卡的格式（无需升级时为 null） |

### 4.3 任务卡格式

task_card 是可以直接交给主线程分派的任务描述：

```json
{
  "title": "升级 <project> memory-core <current> -> <target>",
  "priority": "P3",
  "type": "<upgrade-type>-upgrade",
  "branch_from": "branch-1",
  "project_path": "<local_path>",
  "actions": [
    "从 branch-1 创建 branch-2",
    "执行必要的 migration",
    "更新 memory.lock",
    "运行测试",
    "合并到 branch-1",
    "删除 branch-2"
  ]
}
```

## 5. 扫描输出模式

### 5.1 表格模式（人类可读）

```
Project   | Version | Status | Upgrade | Migration | Task
----------|---------|--------|---------|-----------|------
workbot   | 0.1.0   | behind | minor   | yes       | 创建任务卡
axonhub   | 0.1.0   | behind | minor   | no        | 创建任务卡
codex     | 0.2.0   | current| none    | no        | -
```

### 5.2 JSON 模式（机器可读）

完整的扫描报告 JSON，可被主线程解析并自动分派任务。

### 5.3 卡片模式（主线程分派）

每个需要升级的项目生成一张任务卡，格式同 4.3 的 task_card。

## 6. 验收标准

- [x] registry 字段规范明确
- [x] registry 不包含业务项目 PLAN/STATE 正文
- [x] 扫描只读，不修改任何项目
- [x] 输出格式可转为主线程任务卡
- [x] 支持表格/JSON/卡片三种输出模式

## 7. registry 维护

### 7.1 添加项目

在 registry.toml 中添加新的 `[[project]]` 条目：

```toml
[[project]]
name = "new-project"
local_path = "/path/to/project"
repo = "https://github.com/org/new-project"
memory_lock = { memory_version = "0.1.0", schema_version = "wb-hook-v2", adapter_version = "builtin" }
```

### 7.2 移除项目

从 registry.toml 中删除对应的 `[[project]]` 条目。
被移除的项目不再被扫描。

### 7.3 更新指针

指针更新通过扫描自动完成，不手动编辑 registry.toml 中的 memory_lock。
