# PreToolUse 守卫契约（工具覆盖 × 放行通道 × parser 行为）

> 契约版本：R2'（与债 7a 的 Create-on-existing 拦截、债 7b 的 memory-amend
> 追加通道同窗生效）。实现载体：`memory_core/tools/_guard_classify.py`（分类）、
> `memory_core/tools/pretooluse_guard.py`（入口）、
> `memory_core/tools/memory_amend.py`（sanctioned 追加工具）。

## 1. 工具覆盖表

| 工具 | 行为 | 说明 |
|------|------|------|
| Write | 按路径分类 | 命中 owned 域（memory/kb、memory/log、memory/system 等）→ **block**；AGENTS.md 走 diff-aware 分类；文件类型黑名单与文档路由校验前置 |
| Edit | 按路径分类 | 同 Write（`_classify_write_edit` 共用处理器） |
| MultiEdit | 逐 item 分类 | 任一 edit item 命中 owned / 黑名单 / 未注册文档目录 → 整体 **block** |
| NotebookEdit | 按路径分类 | notebook_path 命中 owned → **block** |
| Execute | 分段写意图门 | 复合命令按 `&&`/`;`/`\|`/`&`/换行 分段；段级（写意图 × owned 引用）命中 → **block**；legacy 路径提取对写意图段兜底；例外见 §2 sanctioned 通道 |
| Task | 放行 + 策略注入 | 不因 prompt 含受保护路径字串拦截（文件级保护由 Write/Edit 处理器兜底），注入 ownership 策略块 |
| **Create** | Create-on-existing-owned → **block** | 债 7a（PR #1122）：目标为 owned 路径且文件已存在 → 视为整文件覆盖，block（理由文案：`Create-on-existing owned path: overwrite denied (kb_policy overwrite_allowed=False; sanctioned amendment channel pending)` → R2' 起后半句已兑现，见 §2）。owned 路径但文件不存在（合法新建流）与非 owned 路径 → 放行 |

## 2. Sanctioned 追加通道：`memory-amend`

Create 命中既有 owned 路径被拦后，合法的增量更正**统一走 `memory-amend`**：

```bash
memory-amend <path> [--header "<标题>"]   # 追加块从 stdin 读
```

- **append-only 语义（服务端强制）**：新内容 = 旧内容 + 追加块，并显式断言
  旧内容是新内容的逐字节前缀；任何改写既有字节的路径（如 `--edit`）不存在。
  原子写入（同目录 tmp + rename），失败不污染原文件。
- 目标文件必须已存在（新建走 Create 合法流）；父目录不存在 → 报错。
- `--header` 自动生成日期化更正段头行
  `> ⚠️ 更正段 #N（YYYY-MM-DD，append-only）：<标题>`，
  N 由文件内既有更正段最大编号推断（无则 #1）。

**守卫放行规则（Execute 处理器）**：命令段的**首 token 精确等于**裸命令名
`memory-amend` 或其绝对安装路径（守卫进程内 `shutil.which` 解析一次并缓存）
→ 该段视为 sanctioned 写，放行该段。

- **禁止子串匹配**：`echo memory-amend …` 的首 token 是 echo，不获放行
  （echo 自身按 readonly + 重定向目标检查）。
- **放行不跨段**：`memory-amend x; rm -rf …` 中 rm 段照常过检；rm 段命中
  owned 引用仍被拦截。

## 3. 过渡机制日落声明

旧的 **"Create-with-verbatim-preservation + 披露"** 过渡机制（对既有 owned
文件用 Create 整文件重写、要求逐字保留旧内容并披露 diff）**自本契约生效起
废止**。未来对既有 owned 文件的更正一律走 `memory-amend`（append-only）；
新建文件走 Create 合法流（owned 路径且文件不存在时放行）。

## 4. Parser 行为（R2' 三处误拦修复）

1. **git 全局 flag**：解析 git 子命令前先跳过已知全局项（`-C <dir>`、
   `-c <k>=<v>`、`--git-dir[=<path>]`、`--work-tree[=<path>]`、
   `--namespace`、`--super-prefix`、`--chdir`、`--no-pager`、`--paginate`、
   `--bare` 等），再取真正的子命令判 readonly。修复 `git -C /repo log` 被
   误判为写；`git -C /repo push` 仍判写。
2. **shell 复合结构**：循环/条件关键字（for/in/do/done/while/until/if/
   then/elif/else/fi/`{`/`}`/`!`/time）本身不构成写意图；剥离关键字后对
   真实命令递归检查，循环头 `for <var> in <词表>` 的词表视为数据（命令替换
   `$(…)` 检查保持在先行位置不被绕过）。仅对真正未知的命令 token 保持
   fail-closed（如算术 for 头）。只读循环体放行，写循环体（如
   `>> memory/…` 重定向）仍拦。
3. **legacy 路径涂抹收紧**：某段判写但无可提取路径时，不再因整条命令任意
   位置含 `memory/` 字串而拦截（该段若自身含 owned 引用已被段级门拦截）；
   只有可归一化且确实命中 owned 域的路径才算数，子串出现不算。uncertain
   路径（通配/变量）+ owned 上下文的 B1 语义保持不变。

## 5. 整体姿态

一紧：Create 命中既有 owned 路径 → 拦截（债 7a 已上线）。
一松：真只读（git -C readonly 子命令、只读循环体、无 owned 命中的复合命令）
不再误拦；合法追加收敛到 `memory-amend` 单点通道，未引入新的放行面。
