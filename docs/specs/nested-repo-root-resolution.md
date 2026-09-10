# 规格 v2：memory-core 嵌套仓库根目录解析修复与记忆单一性硬化

> **状态**：设计定稿（M0 合并规格），待 M1 实施
> **日期**：2026-09-10
> **性质**：单一权威实施规格——合并 Qwen 基线方案 + GLM 审查 9 项必修 + 用户四项裁决 + 查漏三项必修
> **仓库**：memory-core（source-repo-readonly，本规格只设计不改码）
> **消费现场**：mencbo（workspace 壳 + 内嵌 git 仓库布局）

---

## 头部声明

> **GLM 方案降级为参考，三处不可照抄：**
> 1. A 层门控以 `memory/system` 存在性为谓词（与 consent 语义冲突——见 §3.3），缺 `memory/system` 条件导致合法非 git 项目被劫持；
> 2. 缺 zcode wrapper 人工同步步骤（zcode 收益唯一依赖手工移植，非 B 层兜底）；
> 3. 0 候选行为为 exit 1（与用户裁决「0 候选 noop + session-start 日志」冲突）。
>
> GLM 方案的 A 层探测块设计（HOME 守卫后、export 前）、set -eu 安全论证、行为矩阵达成逻辑经修正后采纳。

---

## 0. 文档用途与阅读指引

本文档是 M1-M5 全部实施的唯一权威规格。所有设计争议已在本文定稿，实施与本文冲突 = 实施错误。

**阅读路径**：
- 实施者：§1（问题与目标）→ §2（核心架构）→ §3（组件设计）→ §4（里程碑与功能分解）→ §5（测试策略）
- 验证者：validation-contract.md 是行为化验收权威；本文件 §6 是验证面索引
- 考古关注：附录 A 是外层层树诞生机制的考古闭环结论

---

## 1. 问题与目标

### 1.1 缺陷现象

Factory 会话开在「非 git 父目录 + 内嵌 git 仓库」布局时，wrapper 只向上 `git rev-parse`（`memory_core/tools/factory_global_hooks.py` render_wrapper 模板 L151-157），`PROJECT_CWD` 原样保留为非 git 外层，`memory-init` 在外层误建记忆树（或存量 split-brain 持续）；gateway（`memory_core/tools/_gateway_config.py:80-88`）无条件信任 wrapper 传值，无二次校验。

**消费现场**：mencbo（外层 = 非 git 事故树 + 内层 = pnpm monorepo git 仓库，split-brain 活跃中）。

### 1.2 目标

把「单一性」升格为硬不变量——**一个项目 = 一个 git 治理的记忆根 = 一棵记忆树**。任何布局下系统要么确定性路由、要么显式拒绝，永不静默猜错。

### 1.3 根因链（file:line 核实）

1. **wrapper 模板只有向上归一化**（`factory_global_hooks.py` render_wrapper L151-157）：CWD 非 git 时 `GIT_ROOT` 为空，`PROJECT_CWD` 原样保留外层。
2. **gateway 无条件信任 env 种子**（`_gateway_config.py:80-88`）：`MEMORY_HOOK_PROJECT_CWD` 直接作 `discover_roots` 种子。
3. **Python 发现逻辑纯向上**（`memory_root_discovery.py` L29-73）：`_MAX_UPWARD_DEPTH=8`，`memory/system/` 为标记，无向下解析。
4. **ownership env 捷径**（`ownership.py:723-729`）：env 与 resolved 一致时直接当 git 根，不校验。
5. **gateway cwd 致命项**（`_gateway_dispatch.py` `_discover_cwd`）：`PREFER_EXTERNAL_CWD=1` 下优先 `ORIGINAL_CWD`（外层），导致 integrity sign/verify 在外层重建 `memory/system/`——**修复自我拆台**。

---

## 2. 核心架构：四级路由优先级

```
1. git 向上归一化        —— 仓库内会话，行为不变（回归保护）
2. 项目根硬化配置        —— memory-project.toml 声明即真理（Phase 2 / M4）
3. 启发式向下探测        —— 限深 1，唯一有效子仓库（Phase 1 / M1）
4. 显式拒绝             —— 歧义/无效：noop + stderr 可见 + errors.log
```

**设计原则**：声明优先于探测，探测优先于拒绝，拒绝永远可见。逃生口 `MEMORY_HOOK_DISABLE_DOWNWARD_PROBE=1` 显式保留。

---

## 3. 组件详细设计

### 3.1 Wrapper（A 层决策点）

**改动文件**：`memory_core/tools/factory_global_hooks.py` render_wrapper 模板

#### 3.1.1 门控谓词（consent 语义，非 memory/system 存在性）

探测触发条件（**全部满足**才探测）：

| # | 条件 | 语义 |
|---|---|---|
| 1 | `GIT_ROOT` 为空 | 向上归一化未命中（CWD 不在任何 git 仓库内） |
| 2 | `[ ! -e "$PROJECT_CWD/.git" ]` | CWD 自身非 git（dataless/不可读 .git 的真仓库不探测） |
| 3 | 无 consent 标记 | 外层 `memory/system` 内 `allow_non_git=true` 不存在 |
| 4 | CWD 非 `$HOME` 精确命中 | HOME 守卫先行 |
| 5 | 未设逃生口 env | `MEMORY_HOOK_DISABLE_DOWNWARD_PROBE != 1` |

**关键变更（vs Qwen 基线）**：基线以 `[ ! -d "$PROJECT_CWD/memory/system" ]` 为门控谓词，这会劫持 `--allow-non-git` 建立的合法非 git 项目。本规格改为 **consent 标记存在性**（用户裁决 3）：

- 有 consent 标记 → 合法非 git 项目，passthrough 服务，不被探测劫持
- 无 consent 标记的非 git 树 → 事故残留 → 改路由子仓（单一性硬规则）

consent 标记检测命令：
```sh
CONSENT_MARKER=""
if [ -f "$PROJECT_CWD/memory/system/ownership.toml" ]; then
    grep -q '^[[:space:]]*allow_non_git[[:space:]]*=[[:space:]]*true' "$PROJECT_CWD/memory/system/ownership.toml" 2>/dev/null && CONSENT_MARKER="1"
fi
if [ -z "$CONSENT_MARKER" ] && [ -f "$PROJECT_CWD/memory/system/manifest.json" ]; then
    grep -q '"allow_non_git"[[:space:]]*:[[:space:]]*true' "$PROJECT_CWD/memory/system/manifest.json" 2>/dev/null && CONSENT_MARKER="1"
fi
```

#### 3.1.2 候选判定（stat 门控 + 唯一时 rev-parse 确认）

- **stat 门控**：`[ -e "$child/.git" ]`（文件或目录都算，兼容 worktree/submodule）
- **点目录过滤**：POSIX glob `*/` 天然跳过点目录（与 shell 行为一致）
- **symlink 跳过**：显式 `[ -L "$child" ]` 检测并跳过
- **候选数封顶**：计数到 2 即停（`break`），防 O(N) 开销
- **唯一候选时 rev-parse 确认**：`git -C "$child" rev-parse --show-toplevel`，失败（悬空/损坏 .git）则剔除，确认失败按 0 候选处理

```sh
NESTED_COUNT=0
NESTED_CANDIDATE=""
for _child in "$PROJECT_CWD"/*/; do
    [ -d "$_child" ] || continue
    [ -L "$_child" ] && continue          # symlink 跳过
    [ -e "$_child/.git" ] || continue     # stat 门控
    # rev-parse 确认（仅唯一候选时才执行——此处先计数）
    NESTED_COUNT=$((NESTED_COUNT + 1))
    NESTED_CANDIDATE="$_child"
    [ "$NESTED_COUNT" -lt 2 ] || break    # 封顶 2
done

# 唯一候选时 rev-parse 确认
if [ "$NESTED_COUNT" -eq 1 ]; then
    CONFIRMED_ROOT=$(git -C "$NESTED_CANDIDATE" rev-parse --show-toplevel 2>/dev/null || true)
    if [ -n "$CONFIRMED_ROOT" ]; then
        PROJECT_CWD="$CONFIRMED_ROOT"
    else
        NESTED_COUNT=0  # 悬空/损坏，降为 0 候选
    fi
fi
```

#### 3.1.3 三分支语义

| 分支 | 行为 | 日志 | stderr |
|---|---|---|---|
| 恰 1 有效仓库 | `PROJECT_CWD` 指向它 | 无（成功路由静默） | 无 |
| 0 个有效仓库 | noop：`printf '{}\n'; exit 0` | 仅 session-start 记 errors.log +1 行 | 无 |
| ≥2 个有效仓库 | noop：`printf '{}\n'; exit 0` | 仅 session-start 记 errors.log +1 行（含候选清单） | **恰一行诊断**（含候选 + 出路） |

**用户裁决 1**：歧义形态为 noop + stderr 恰一行诊断 + session-start 记 errors.log。exit 0。

**用户裁决 2**：候选判定为 stat 门控 + 唯一时 rev-parse 确认；悬空/损坏剔除。

**stderr 一行诊断格式**（≥2 分支）：
```
memory-hook: ambiguous nested repos under <CWD>: <candidate1>, <candidate2> (+more) -> cd into a specific repo, or create memory-project.toml to declare membership
```

#### 3.1.4 事件门控（循环解析 --event 值）

**必修项 #1**（GLM 审查 R1）：Qwen 基线的 `case " $* "` 模式恒真 bug。

**正确实现**：循环解析 `--event` 值，兼容 `--event=<name>` 与 `--event <name>`。**注意**：wrapper 模板 shebang 为 `#!/bin/sh`（POSIX sh），**禁止使用 bash 数组语法**（`_args_remaining=("$@")`、`${#_args_remaining[@]}`）。必须使用 POSIX 兼容的 `for _arg in "$@"` 循环配合前参回看。

```sh
# 解析 --event 值（POSIX sh 兼容，wrapper shebang 为 #!/bin/sh）
EVENT_NAME=""
_prev_was_event=0
for _arg in "$@"; do
    case "$_arg" in
        --event=*)
            EVENT_NAME="${_arg#--event=}"
            ;;
        --event)
            _prev_was_event=1
            ;;
        *)
            if [ "$_prev_was_event" -eq 1 ]; then
                EVENT_NAME="$_arg"
            fi
            _prev_was_event=0
            ;;
    esac
done
```

**禁止位置参数判定**：`$2` 恒为 "factory"（hooks.json 实测形态 `$1=--host $2=factory $3=--event $4=<事件名>`）。

**日志仅 session-start 写入**：
```sh
if [ "$EVENT_NAME" = "session-start" ] || [ -z "$EVENT_NAME" ]; then
    printf '[%s] [memory-hook-wrapper] [warn] %s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%S%z')" "<场景描述>" \
        >>"$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system/errors.log" 2>/dev/null || true
fi
```

#### 3.1.5 探测触发 init 的特殊语义

- **adopt 模式**：不追加 AGENTS.md 注入块（不弄脏用户临时 clone）
- **denylist 降级**：init 被 denylist 拒（tmpdir/junk 等）→ 降级 noop，不 exit 1
- **并发安全**：套现成 `exclusive_lock`（`_file_utils.py:20-38`）
- **已初始化子仓优先**：即使有兄弟候选，带 `memory/system` 的子仓优先

#### 3.1.6 执行顺序

```
① 计算 PROJECT_CWD（向上归一化，不变）
② HOME 守卫（精确 $HOME 命中 → noop exit 0）
③ 源仓库只读保护（不变）
④ 嵌套仓库向下探测（新增，在 HOME 守卫后、export 前）
⑤ export MEMORY_HOOK_PROJECT_CWD（位置后移，VAL-ROOT-003 字面量不变）
⑥ init 块（作用于最终 PROJECT_CWD）
⑦ exec gateway
```

**必修项 #8 相关**：探测块必须放在 HOME 守卫之后（$HOME 下大量仓库会误报歧义）。

#### 3.1.7 set -eu 安全

- 所有命令替换带 `|| true` / `2>/dev/null` 兜底
- 循环内失败一律 `|| continue` 或显式 if
- 算术展开 `$(( ))` 不会因 0 失败
- glob 无匹配时字面量展开被 `[ -d ]` 判假后 `continue`
- **禁止裸 `[ ... ] && break` 形态**（假值触发 set -e 提前退出——经典陷阱）

### 3.2 Gateway（B 层消费侧）

#### 3.2.1 cwd 语义修复（致命项，查漏 #1）

**现状**：`_gateway_dispatch.py` 的 `_discover_cwd` 在 `PREFER_EXTERNAL_CWD=1` 下优先 `MEMORY_HOOK_ORIGINAL_CWD`（外层），导致：
- integrity sign/verify（`memory_hook_integrity_manifest.py:491-495` 的 `mkdir(parents=True)`）在外层重建 `memory/system/`
- 异步 health-check 落外层
- 版本同步面向外层

**修复**：memory-root 语义调用点（4 处：integrity sign、integrity verify、health-check、version-sync）改用 `REPO_ROOT`（探测路由后的项目根）。

**影响**：消除「修复自我拆台」——修复后 integrity 签名落内层，外层零 mkdir。

#### 3.2.2 B 层种子精炼

**改动文件**：`memory_core/tools/memory_root_discovery.py` 或 `_gateway_config.py`

新增非 git 种子精炼函数（不改 `discover_project_root` 契约）：

- 种子自带 `.git` → passthrough
- 非 git 种子 + 无 consent + 唯一有效子仓（`.git` 存在性，点目录过滤 `not name.startswith(".")`）→ `REPO_ROOT`=子仓
- ≥2 子仓 → 不静默择一，保持 seed 原样 + warning 日志
- 0 子仓 → 保持 seed 原样

**关键约束**：
- 纯文件系统操作（无 git 子进程）——保持 discovery 模块「无子进程的纯函数」特性
- 点目录过滤与 shell glob 对齐（必修项 #4，GLM 审查 R4）
- **必修项 #2 修正**：B 层论证定位为「防御纵深 + 语义一致性」，不救陈旧 wrapper（GLM 审查 R2）
- **影响面声明**（必修项 #5，GLM 审查 R5）：所有 import `_gateway_config` 的 CLI（含 mcp_server）受种子精炼影响

**影响文件清单**（grep `from.*_gateway_config import\|import.*_gateway_config` 确认）：
- `mcp_server.py`
- `memory_health_report.py`
- 约 20 个文件——需文档声明

### 3.3 memory-init（consent 生产者）

**改动文件**：`memory_core/tools/init_project_memory.py`、`_init_pipeline.py`

#### 3.3.1 --allow-non-git consent 落盘

`memory-init --allow-non-git` 建树时落 consent 标记（用户裁决 3）：

- 落盘位置：`memory/system/ownership.toml`（[policy] 段）和/或 `manifest.json`
- 标记内容：`allow_non_git = true`（token 形式）
- **约束**：git 仓库内不带 flag 的 init 零落盘（阴性对照）

#### 3.3.2 adopt 模式强化

- 不追加 AGENTS.md 注入块
- 保留业务文件（README/业务 INDEX sha 不变）
- 对缺失骨架仍补建（manifest、ownership.toml、系统文件）

#### 3.3.3 并发安全

scaffold 阶段套现成 `exclusive_lock`（`_file_utils.py:20-38`，现未用）防并发交错。

### 3.4 安装器（factory_global_hooks.py install_factory_hooks）

**改动**：

1. **wrapper 自动备份**（必修项：GLM 审查 R8 相关）：现状只备份 settings.json，wrapper 直接 `write_text` 零备份。补 `if wrapper.exists(): backup(wrapper)`
2. **hooks.json 意识**：hooks 真实注册处是 `~/.factory/hooks.json`（settings.json hooks 键 2026-08-17 起废弃）；install 不再往 settings.json 注入死键

### 3.5 Phase 2 硬化配置（memory-project.toml）

```toml
project = "mencbo"          # 项目身份
memory_root = "./mencbo"     # 指针：唯一记忆根在 git 仓库内
members  = ["./mencbo"]      # 成员仓声明
```

- wrapper 只查存在性（env 透传 `MEMORY_HOOK_PROJECT_CONFIG`），gateway 解析（tomllib）
- 安全校验：realpath + containment（拒绝 `..` 穿越与越界绝对指针）
- deny 名单：`$HOME`/系统目录/memory-core 源仓根
- world-writable（666）降级忽略 + 告警
- 唯一性冲突校验：成员解析后绝对路径重叠 → 拒绝
- 查找范围：种子自身优先，祖先兜底，就近原则
- git 向上命中与配置冲突 → preserve-and-escalate 留痕

---

## 4. 里程碑与功能分解

### M0：合并规格 v2（本文档）

**产物**：`docs/specs/nested-repo-root-resolution.md`（feature 分支 + PR）

**验收**：
- [x] 9 项必修逐条有吸收位置（见 §7 映射表）
- [x] 门控谓词为 consent 语义（§3.1.1）
- [x] 纯文档改动，wrapper 专项测试仍 23 passed，ruff 绿
- [x] 考古结论为证实或显式不可溯源声明（附录 A）

### M1：Phase 1 实施（feature 分支 + PR）

| 功能 ID | 描述 | 验证断言 |
|---|---|---|
| init-consent-and-adopt | memory-init 三项强化（consent 落盘 + adopt 模式 + exclusive_lock） | VAL-INIT-001~008 |
| wrapper-probe-implementation | wrapper 探测层实现（五条件门控 + 三分支 + 事件解析 + adopt + denylist 降级） | VAL-WRAP-001~022 |
| gateway-cwd-semantics-fix | gateway cwd 语义修复（4 处 memory-root 调用点改用 REPO_ROOT） | VAL-GTW-001~005 |
| b-layer-seed-refinement | B 层种子精炼（纯 FS 无子进程 + 点目录过滤 + 影响面文档） | VAL-GTW-006~015 |
| install-hardening | install 补 wrapper 备份 + hooks.json 意识 | VAL-REL-006, VAL-REL-012 |

**CI 门禁**：`ruff check .` + `ruff format --check .` + `mypy --strict memory_core/` + `mypy --strict scripts/` + `pytest -q tests -n 0 --cov`

### M2：发布与双 host 同步

1. 手动备份 wrapper（`cp` + `cmp` 逐字节验证）
2. `memory-factory-hooks install` 重渲染
3. grep 验证探测标记 + `sh -n` 语法校验
4. hooks.json sha 前后一致核验
5. **zcode wrapper 人工移植**（保两个 delta + 探测块位于守卫后 export 前）
6. stub 干跑验证（mencbo 外层 → ROUTED_TO=内层）
7. 回滚演练（M3 前必须做）
8. /hooks 菜单确认

### M3：mencbo 存量清理

**前置门**：
1. M2 全部通过
2. 外层 `memory/artifacts/memory-hook/contexts/` 无当日新写入（活跃会话静默窗口）
3. lsof 无活跃会话

**执行**：
1. 全量 `cp -a` 备份外层树
2. read-first-CRUD 合并（零覆盖，分歧归档）
3. 3 份 integrity 异常文件 escalate
4. 影子骨架清退（含 AGENTS.md）
5. MERGE-REPORT 落档
6. 路由复验

### M4：Phase 2 硬化配置实施

- 核心路由（配置解析 + 四级优先 + 查找范围）
- 安全面（containment + deny + 权限降级 + 冲突校验）
- mencbo 首份配置样板

### M5：知识沉淀与收尾

- 决策记录 ×4
- hook-contract 全局 kb 更新
- docs B 层影响面声明
- 考古 lesson
- known-issue ×2

---

## 5. 测试策略

### 5.1 测试层级

| 层级 | 工具 | 覆盖区域 |
|---|---|---|
| 单元/组件 | pytest | 模板字符串断言 + wrapper 子进程行为 + Python 发现逻辑 + 配置解析 |
| 集成 | CI 全量 | `pytest -n 0 --cov` + mypy + ruff |
| 端到端 | stub gateway 干跑 | 路由结果 + 零写入快照 |
| 用户测试面 | 手动 hook 调用 + 沙箱矩阵 | 无浏览器面 |

### 5.2 基线与回归

- **基线**：`uv run pytest tests/test_factory_global_hooks.py -x -q --no-cov` = 23 passed（2026-09-10 实测）
- **3 个现存测试改基**（必修项 #6）：
  - `test_wrapper_skips_exact_home_project_root_but_allows_child`
  - `test_wrapper_initializes_project_memory_with_factory_host`
  - `test_wrapper_uses_factory_project_dir`
  - 改基方式：fixture 加 `git init` 或断言改 noop
- **wrapper 专项测试 ≥23 只增不减**

### 5.3 新增测试矩阵

| 测试场景 | 验证要点 |
|---|---|
| 唯一子仓路由 | ROUTED_TO=子仓；外层零建树 |
| ≥2 子仓 noop+stderr | stdout `{}`；stderr 恰一行；errors.log +1 |
| 0 候选 noop | stdout `{}`；errors.log +1（session-start） |
| worktree 子仓 | .git 文件形态被识别 |
| 悬空 .git | 被 rev-parse 剔除 |
| dataless .git | 门控挡下不探测 |
| HOME 守卫 | $HOME 精确命中 → noop |
| consent passthrough | 有标记 → 不被劫持 |
| 无标记存量树 + 唯一子仓 | 改路由子仓（单一性硬规则） |
| symlink 跳过 | 不计入候选 |
| 已初始化子仓优先 | 带 memory/system 的子仓优先 |
| 并发 init | 8 并发终态一致 |
| CWD 不存在 | 零副作用 |
| FACTORY_PROJECT_DIR 优先 | 驱动路由而非 PWD |

### 5.4 验证工具

- **stub gateway 干跑法**：`MEMORY_HOOK_GATEWAY=<stub> MEMORY_HOOK_PROJECT_INIT=/usr/bin/true`
- **B 层干跑**：`MEMORY_HOOK_PROJECT_CWD=<path> python3 -c "from memory_core.tools import _gateway_config as c; print(c.REPO_ROOT)"`
- **no-op init**：`/usr/bin/true`（本机无 `/bin/true`）

---

## 6. 验证面索引

全部断言可通过 shell（Execute）验证——本项目无浏览器面。

| 区域 | 断言数 | 验证工具 |
|---|---|---|
| WRAPPER | 22 | stub gateway 干跑 + errors.log 检查 |
| INIT | 8 | memory-init CLI + 目录树检查 |
| GATEWAY | 15 | gateway 会话干跑 + import 干跑 |
| CONFIG | 19 | B 层解析 + 配置解析 |
| RELEASE | 12 | grep/sha/cmp/diff + 干跑 |
| CLEANUP | 8 | 干跑 + find/marker + git status |
| CROSS | 9 | 端到端 + 沙箱矩阵 |

完整断言见 `validation-contract.md`；可执行细节见 `contract-work/`。

---

## 7. 必修项吸收映射表

### 7.1 GLM 审查 9 项必修

| # | 必修项 | 规格吸收位置 |
|---|---|---|
| 1 | case 事件门控恒真 bug → 循环解析 `--event` 值 | §3.1.4 事件门控 |
| 2 | B 层论证改写（仅防御纵深，不救陈旧 wrapper）+ zcode 同步升级为发布阻断步骤 | §3.2.2 B 层种子精炼 + §4 M2 |
| 3 | 考古结论降级（"errors.log 零记录"不构成证据；表述"高度可能"） | 附录 A 考古闭环 |
| 4 | Python 点目录过滤（`not name.startswith(".")`） | §3.2.2 B 层种子精炼 |
| 5 | 6 个直接 import gateway 的测试文件影响审计 + 全量 pytest 验收 | §3.2.2 影响面声明 + §5.2 |
| 6 | 0 候选分支补 session-start 日志 | §3.1.3 三分支语义 |
| 7 | 清退清单补外层 AGENTS.md + 清理顺序修正 | §4 M3 |
| 8 | 发布前确认 wrapper 实际调用链 → **已闭环：hooks.json** | library/environment.md |
| 9 | /bin/true → /usr/bin/true | §5.4 验证工具 |

### 7.2 用户四项裁决

| # | 裁决 | 规格吸收位置 |
|---|---|---|
| 1 | 歧义形态：noop + stderr 恰一行 + session-start errors.log | §3.1.3 三分支语义 |
| 2 | 候选判定：stat 门控 + 唯一时 rev-parse 确认 | §3.1.2 候选判定 |
| 3 | 过渡 consent：--allow-non-git 落盘标记 | §3.1.1 门控谓词 + §3.3.1 |
| 4 | 范围：M0-M5 全做 | §4 里程碑 |

### 7.3 查漏三项必修

| # | 必修项 | 规格吸收位置 |
|---|---|---|
| 1 | gateway cwd 语义修复（致命项） | §3.2.1 cwd 语义修复 |
| 2 | 3 个现存 wrapper 测试改基 | §5.2 基线与回归 |
| 3 | A 层门控补 `.git` 存在性检查 | §3.1.1 门控谓词条件 #2 |

---

## 8. 部署拓扑

```
Factory 会话 (任意目录)
  → ~/.factory/hooks.json 注册（settings.json hooks 键已废弃）
  → ~/.factory/bin/memory-hook（wrapper，四级路由）
      → hooks.json 注册（settings.json 已废弃）
      → memory-init（scaffold：denylist + consent 标记 + adopt + 锁）
      → memory-hook-gateway（editable 安装，pull 即生效）
          → _gateway_config（种子精炼 → REPO_ROOT）
          → integrity/health/version-sync（改用 REPO_ROOT）★ M1 修复
  → ~/.zcode/bin/memory-hook（手工克隆，M2 人工移植，保两个 delta）
记忆树：git 仓库根/memory/（唯一合法位置）
```

**发布顺序（硬约束）**：
1. 手动备份 wrapper
2. PR 合并（异步，write-pending-ci 后不阻塞）
3. `memory-factory-hooks install` 重渲染
4. grep 验证 + `sh -n` 语法校验
5. zcode 人工同步
6. stub 干跑验证
7. **然后才可** mencbo 清理（M3 必须晚于 M2 且避开活跃会话）

---

## 9. 环境与基础设施

- **主仓库**：memory-core（editable 安装，pip shim → 源码 pull 即生效）
- **消费现场**：mencbo（M3 前只读）
- **无需服务/端口**：纯 CLI/hook 库 mission
- **工具链**：uv、pytest、ruff 0.16.1、mypy 2.3.0、`memory-factory-hooks install`
- **本机无 /bin/true**：no-op init 用 `/usr/bin/true`

---

## 10. 边界与非目标

- **不在本 mission**：lifecycle 身份观测 wart（follow-up）；`_has_git_not_memory` `.is_dir()` quirk（仅新门控用 `.exists()` 规避）；zcode wrapper 纳入渲染管线
- **known-issue 登记**：破损 gitfile 子仓降级 scope；lone surrogate 编码
- **回归保护**：仓库根/子目录行为不变（VAL-WRAP-001/002）；memory-core 自仓 READONLY 逻辑不变（VAL-CROSS-002）；consent 合法项目 passthrough（VAL-CROSS-003）

---

## 11. 风险与回滚

### 11.1 风险清单

| # | 风险 | 缓解 |
|---|---|---|
| 1 | 合法非 git 项目 + 内嵌 vendored 仓库被误路由 | consent 标记 passthrough + 逃生口 env |
| 2 | shell 探测边缘环境误行为 | stat-only + `|| true` + `sh -n` + 25 个行为测试 |
| 3 | 0 候选从 exit 1 变 noop 信号丢失 | errors.log session-start 留痕 |
| 4 | zcode wrapper 忘同步 | M2 发布阻断步骤 + B 层防御纵深 |
| 5 | 存量清理竞态（G3） | M3 必须晚于 M2 + 活跃会话静默窗口前置门 |

### 11.2 回滚总闸

| 层面 | 回滚动作 |
|---|---|
| shell | `cp ~/.factory/bin/memory-hook.bak-* ~/.factory/bin/memory-hook` |
| Python | `git revert <merge-commit>`（editable 即时生效） |
| 现场 | 恢复 `memory.pre-merge-backup-*` |

---

## 12. 非功能需求

- wrapper 探测延迟：仅非 git 路径触发，stat-only 毫秒级（无子进程，封顶 2 次 rev-parse ≈ 10-20ms）
- 一切拒绝可见化：errors.log + stderr，禁止静默失败
- 回滚可行：wrapper 手动备份 + mencbo 全量备份 + git revert + 干跑复验

---

## 附录 A：考古闭环——外层树诞生机制

### A.1 调查方法

时间盒 30 分钟，调查以下证据源：
1. zsh history（`grep 'allow-non-git' ~/.zsh_history`）
2. `~/.zcode` 全局状态日志
3. 外层树 `migrations.log` / `manifest.json` 签名细节
4. 全局 errors.log 中 non_git/mencbo 记录

### A.2 调查结果

| 证据源 | 结果 |
|---|---|
| zsh history `allow-non-git` | **0 匹配** |
| zsh history `mencbo` / `non_git` / `BYPASS_DENYLIST` | **0 匹配** |
| `~/.zcode/state.json` | **不存在**（~/.zcode 目录存在但无全局状态文件） |
| `migrations.log` 首行 | `2026-09-06T00:00:00Z \| none \| 0.45.6 \| applied \| initial scaffold`（签名匹配 `_init_templates_misc.py:31` 模板，确认 v0.45.6 创建） |
| `manifest.json` | `project_root: "<outer>"`，`generated_at: "2026-09-10T00:17:44+00:00"`（最近签名，证明活跃） |
| 外层时间戳 | INDEX.md/NOW.md/migrations.log = 2026-09-06 11:41:59；AGENTS.md = 2026-09-06 11:42:00 |
| 全局 errors.log | 443 行，**0 条** non_git/mencbo 记录 |

### A.3 结论

**外层树由 memory-init v0.45.6 创建（已证实）**：migrations.log 签名逐字匹配模板，时间戳一致。

**具体创建命令/执行者不可溯源（显式了结）**：
- zsh history 零相关记录（可能原因：命令在其他 shell 执行、history 被清理、通过 agent/session 执行不经过 zsh）
- 全局 errors.log 零 non_git 记录（denylist 拒绝输出只走 stdout 进 /dev/null，结构性无痕——GLM 审查 R3 已证实）
- 无 zcode 全局状态日志可查
- 可能路径（均无法排除也无法确认）：
  1. `memory-init --target <outer> --allow-non-git`（CLI 显式覆盖）
  2. `MEMORY_CORE_BYPASS_DENYLIST=1`（环境变量绕过）
  3. 直接 Python API 调用 `init_project_memory(..., allow_non_git=True)`
  4. 创建时外层存在 `.git`（init 合法放行后 `.git` 被移走）

**论证强度**：「高度可能由显式覆盖或等效旁路建成」——但不构成确定性结论。本规格不基于考古结论做任何设计决策（修复不依赖考古结论）。

### A.4 当代行为矩阵

| 会话 CWD | 现状 |
|---|---|
| 仓库根 / 仓库内子目录 | 正确（向上归一化命中） |
| 非 git 父目录，外层树**已存在**（mencbo 现场） | split-brain 持续：wrapper 导出外层 → gateway depth 0 命中外层 `memory/system/` |
| 非 git 父目录，外层树**不存在**（新现场） | init 被 non_git 拒绝 → wrapper exit 1 → hook 每事件硬失败 |

---

## 附录 B：GLM 方案降级参考声明

GLM 方案（`memory/artifacts/2026-09-10-nested-repo-root-resolution-solution-glm.md`）的以下内容经修正后采纳：
- A 层探测块位置（HOME 守卫后、export 前）
- set -eu 安全论证（禁止裸 `[ ... ] && break`）
- 行为矩阵达成逻辑
- 回滚三层设计

以下内容**不可照抄**：
1. A 层门控以 `memory/system` 存在性为谓词 → 本规格改为 consent 标记（§3.1.1）
2. 0 候选行为为 exit 1 + stderr JSON → 本规格改为 noop + session-start 日志（§3.1.3）
3. 歧义行为为 exit 1 + stderr JSON → 本规格改为 noop + stderr 一行 + session-start 日志（§3.1.3，用户裁决 1）
4. B 层定位为「滞留 wrapper 兜底」→ 本规格改为「防御纵深 + 语义一致性」（§3.2.2）
5. 缺 zcode wrapper 人工同步步骤 → 本规格 M2 列为发布阻断步骤（§4）

---

## 附录 C：过时内容删除声明

以下内容从 Qwen 基线方案中删除或降级：

| 内容 | 处置 | 原因 |
|---|---|---|
| §2.2 考古强结论（"只能由显式覆盖建成"） | 降级为「高度可能」，附录 A 显式不可溯源了结 | GLM 审查 R3：errors.log 零记录不构成证据 |
| B 层"陈旧 wrapper 自愈"论证 | 改写为「防御纵深」 | GLM 审查 R2：老 wrapper 两路径均不可达 B 层 |
| §8"清理与重渲染先后皆可" | 修正为「清理必须晚于 wrapper 重渲染 + zcode 同步」 | GLM 审查 G3 竞态 |
| /bin/true | 全部改 /usr/bin/true | 本机无 /bin/true（macOS） |
