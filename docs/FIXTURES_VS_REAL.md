# Fixture 与真实项目状态区分规则

> 版本：v1.0 / 2026-04-29
> 本文档说明 memory 仓库中 example/fixture 数据与真实业务项目状态的区分规则。

---

## 1. 定义

### Fixture（示例/夹具）

Fixture 是**虚构的、最小化的、用于演示或测试的数据**，存放在 memory 仓库中。

**特征：**
- 文件名带 `demo-` 或 `fixture-` 前缀
- 数据是虚构的，不指向任何真实业务上下文
- 规模最小化（仅够展示结构或用于测试）
- 不包含真实的项目 URL、本地路径、GitHub Project 链接
- 不引用真实人员、团队、业务线

### 真实项目状态

真实项目状态是**具体业务项目的实际执行数据**，存放在业务项目自身的 `.memory/` 目录下。

**特征：**
- 文件名是标准的 `PLAN.md`、`STATE.md`、`CANONICAL.md`、`NOW.md`
- 包含真实的项目名称、仓库路径、URL、Issue/Project 链接
- 有真实的任务分派、执行进度、阻塞记录
- 引用真实的本地文件系统路径
- 包含具体的业务上下文

---

## 2. 存放位置对照

| 数据类型 | 存放位置 | 示例路径 |
|----------|----------|----------|
| Demo Fixture | `memory` 仓库的 `examples/` 或 `workspace/memory/kb/fixtures/` | `examples/demo-project/PLAN.md` |
| 真实项目状态 | 业务项目自身的 `.memory/` | `<业务项目>/.memory/kb/projects/axonhub-rebase/PLAN.md` |
| 通用规范模板 | `memory` 仓库的 `workspace/memory/kb/global/` | `workspace/memory/kb/global/projects-spec.md` |

---

## 3. 命名规则

### Fixture 命名

```
examples/
├── demo-simple-project/
│   ├── PLAN.md          # ✅ 允许：demo 前缀目录
│   ├── STATE.md         # ✅ 允许：仅作为示例
│   └── CANONICAL.md     # ✅ 允许：虚构数据
└── fixture-complex/
    ├── PLAN.md          # ✅ 允许：fixture 前缀目录
    └── STATE.md         # ✅ 允许：仅作为示例
```

### 真实项目命名（不在 memory 仓库中）

```
<业务项目仓库>/
└── .memory/
    └── kb/
        └── projects/
            └── axonhub-rebase/
                ├── PLAN.md       # 真实业务数据
                ├── STATE.md      # 真实业务数据
                └── CANONICAL.md  # 真实业务数据
```

---

## 4. 内容检查清单

判断一个文件是 fixture 还是真实状态，检查以下维度：

| 检查项 | Fixture | 真实状态 |
|--------|---------|----------|
| 项目名称 | 虚构名称（如 "Example Project"） | 真实项目名称（如 "AxonHub"） |
| GitHub 链接 | 无或指向示例仓库 | 指向真实仓库/Project |
| 本地路径 | 无 | 如 `/Users/xxx/tool/project` |
| 任务内容 | 通用演示任务 | 具体业务任务 |
| 执行进度 | 静态示例数据 | 动态真实进度 |
| 人员引用 | 无或虚构 | 真实开发者/团队 |
| 文件大小 | 小（通常 < 50 行） | 可能很大（数百行） |

---

## 5. 迁移规则

当在 memory 仓库中发现真实项目状态时：

1. **识别归属项目**：从文件内容中找到对应的业务项目
2. **迁移到业务项目**：将文件移动到 `<业务项目>/.memory/kb/projects/<name>/` 下
3. **如需保留示例**：将内容脱敏、最小化后，以 `demo-` 或 `fixture-` 前缀重新创建
4. **从 memory 仓库删除**：确保原真实数据文件不再存在于 memory 仓库中

---

## 6. `.gitignore` 防护

`.gitignore` 已配置规则，防止以下模式被提交到 memory 仓库：

```gitignore
# 禁止真实业务项目状态文件
**/STATE.md
**/PLAN.md
**/CANONICAL.md
**/NOW.md
```

如需在 memory 仓库中添加 fixture，使用显式 `git add -f` 并附带 demo/fixture 前缀。

---

## 7. 业务项目 `.memory/` 是项目状态归属地

**核心规则：业务项目的 PLAN / STATE / CANONICAL / NOW.md 只能在业务项目自身的 `.memory/` 目录下存在。**

memory 仓库的职责是提供：
- 数据结构定义（Schema）
- 校验工具（Validator）
- 通用模板（Templates）
- 示例数据（Fixtures）

而不是承载任何真实项目的执行状态。
