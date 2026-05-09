# Memory Module Workspace — 总控入口

> 工作区索引 | 最后更新：2026-04-27

---

## 快速入口

| 文件 | 用途 |
|------|------|
| [`NOW.md`](./NOW.md) | 当前状态与下一步任务 |
| [`memory/kb/INDEX.md`](../memory/kb/INDEX.md) | 知识库索引（真相层） |
| [`memory/docs/INDEX.md`](../memory/docs/INDEX.md) | 文档索引（资料层） |

---

## 核心目录

```
memory_core/
├── NOW.md              # 当前状态
├── INDEX.md            # 本文件
├── memory/
│   ├── kb/             # 知识库（真相层）
│   │   ├── global/     # 跨项目规则
│   │   ├── projects/   # 项目真相
│   │   ├── decisions/  # 决策记录
│   │   ├── lessons/    # 经验教训
│   │   └── longterm/   # 长期记忆
│   ├── docs/           # 文档库（研究资料）
│   ├── log/            # 每日日志（append-only）
│   └── actions/        # 临时任务
└── projects/           # 项目交付产物
```

---


## project-map 合同口径

- `project-map/INDEX.md` 是唯一合法入口。
- 只有被地图标为 `active-legal` 的条目或目录，才是合法资料；仅进入登记册不授予合法性。
- 目录登记和目录状态迁移必须与相关文件同次 `git commit` 才生效。
- 真相模型 canonical：`memory_core/memory/kb/global/truth-model.md` — 由各业务项目通过 adapter runtime profile 自行声明（参见仓库根 `README.md` 的 "Adapter Protocol" 与 "Runtime Capabilities" 两节）。memory-core 仓库不内建任何业务项目专属的真相模型文件。

## 核心规则

- `NOW.md` 是唯一允许覆写的入口文件
- `memory/kb/**` 使用 read-first CRUD，禁止覆盖或删除旧内容（只能标记 `superseded`）
- `memory/log/` 只追加，不覆写
- 路由细节、写入协议、冲突处理等见 `memory/kb/global/`

---

*简化版 v2.0 | 移除冗余路由表和协议细节，归位至 kb/global/*
