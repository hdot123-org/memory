# 守卫复合命令逃逸 — 残余风险规范

## 概述

本文档记录 M1 守卫复合命令逃逸修复后仍存在的已知残余风险类别。这些残余是字符串层原理上不可拦截的攻击形态，已被用户裁定为"接受并文档化"。

纵深防御由 manifest SHA-256 完整性校验（audit 检查 1）+ 每日审计事后检测提供。

---

## 三类残余风险

### 1. 纯 cwd 语义（Pure cwd semantics）

**形态**：命令通过 `cd` 切换工作目录后，后续命令使用相对路径，路径字符串从不以完整 `memory/` 前缀出现。

**示例**：
```bash
cd memory && cd kb && rm -f x.md
cd memory && cd system && touch pwned
```

**为何残余**：
- 第一类形态（`cd memory && cd kb && rm -f x.md`）：`rm` 段文本无任何 owned 指示串，字符串层不可见
- 第二类形态（`cd memory && rm -f memory/system/x.md`）：后段含完整指示串，可被 Fix-1 兜底拦截

**当前实现**：
- 单段 `cd memory` 检测（`cd` 后直接跟 owned 目录名）
- 不做跨段 cwd 累积追踪（未来可实现累积收窄此残余）

**纵深防御**：
- manifest 完整性校验检测文件被删
- 每日审计事后检测异常操作

---

### 2. 变量拆散（Variable scattering）

**形态**：攻击者将 owned 路径拆分为多个变量，命令文本中无完整指示串。

**示例**：
```bash
d1="memo"; d2="ry/kb"; rm -rf "$d1/$d2"
d="memory"; b="kb"; find "$d/$b" -name x -delete
```

**为何残余**：
- 变量赋值段（`d1="memo"`）不含完整 `memory/` 指示串
- 使用段（`rm -rf "$d1/$d2"`）仅含变量引用，字符串层无法展开
- 需 shell 变量追踪或动态执行才能识别

**当前实现**：
- 字符串层检查完整指示串，无法展开变量
- 变量拆散形态 allow（已知接受残余）

**纵深防御**：
- manifest 完整性校验
- 每日审计检测异常删除模式

---

### 3. 编码路径（Encoded paths）

**形态**：攻击者通过 base64 或其他编码方式隐藏路径，运行时解码后使用。

**示例**：
```bash
echo bWVtb3J5L2ti | base64 -d | xargs rm -f
python3 -c "import base64,os; os.remove(base64.b64decode('bWVtb3J5L3N5c3RlbQ==').decode())"
```

**为何残余**：
- 命令文本仅含编码后的字符串（如 `bWVtb3J5L2ti`），无 `memory/` 明文
- 需运行时解码才能识别目标路径
- 字符串层检查无法识别编码内容

**当前实现**：
- 仅检查明文指示串
- 编码路径形态 allow（已知接受残余）

**纵深防御**：
- manifest 完整性校验
- 每日审计检测异常解码+删除模式

---

## 命令替换拦截说明（N2）

**设计原则**：命令替换 `$(...)` 或反引号 `` `...` `` 内含的动态内容无法静态分析，按 fail-closed 原则拦截。

**示例**（均 block）：
```bash
echo $(rm -rf memory/kb)
echo `touch memory/system/pwned`
cat $(find . -name "*.tmp" -delete)
```

**实现机制**：
- `_segment_has_write_intent` 在检查 readonly_commands 之前，先检测段中是否包含 `$(` 或反引号
- 若检测到命令替换模式，直接返回 True（有写意图），触发后续路径提取与分类
- 这是 fail-closed 策略：无法静态确定命令替换内容的安全性时，保守拦截

**边界**：
- 仅当段中包含命令替换语法时拦截
- 普通变量引用（`$VAR`）不在此规则范围内（变量拆散属残余类别）
- 命令替换检测优先于 readonly_commands 判定，确保 `echo $(rm ...)` 不被 echo 的只读属性放行

**读语义例外（NB-1，R3 收尾补记）**：

当前一刀切 block 策略存在已知过度拦截：命令替换内为只读命令且重定向目标非受保护域的场景被误拦。

**示例**（当前 block，属已知过度拦截）：
```bash
echo "built $(date) for memory/kb" > /tmp/out.txt
echo "$(cat memory/docs/README.md)" > /tmp/note.txt
```

**为何当前拦截**：
- `_segment_has_write_intent` 检测到 `$(` 即返回 True，不评估命令替换内容
- 后续路径提取发现 `memory/kb` 字面量，触发 fail-closed 拦截
- 即使重定向目标 `/tmp/out.txt` 完全在受保护域外

**放行条件**（架构上可行但当前未实现）：
- 命令替换内为只读命令（`date`/`cat`/`echo`/`grep`/`head`/`tail`/`wc`/`awk`/`sed -n` 等）
- 重定向目标非受保护域（`/tmp/`、`/var/log/`、`~/Downloads/` 等）
- 无写意图段（整个命令仅为输出/日志记录）

**为何当前接受残余**：
- 静态分析命令替换内容需 shell 语法解析（嵌套引号、变量展开、多行命令）
- 边界案例复杂：`$(grep -l "pattern" memory/kb/*)` 的 `-l` 输出路径可能被后续命令使用
- 纵深防御（manifest + 审计）可事后检测异常，当前 fail-closed 策略安全性足够
- 读语义误拦频率低（真实场景多为写操作），优先级低于其他残余修复

**未来改进方向**（可选，非阻塞）：
- 命令替换内容白名单：仅允许已知只读命令（`date`/`cat`/`echo` 等）放行
- 重定向目标白名单：`/tmp/`、`/var/log/` 等非受保护域自动放行
- 需评估安全风险：攻击者可能构造 `$(cat /etc/passwd) > /tmp/out` 等绕过场景

**当前策略**：接受过度拦截残余，文档化例外场景，优先级低。

---

## 读语义放行说明

**设计原则**：只读命令提及 owned 字面量属于防误拦设计，非逃逸。

**示例**（均 allow）：
```bash
grep "memory/kb" src/app.py > /tmp/out.txt
git commit -m "docs: update memory/kb notes"
echo "see memory/system for details" > /tmp/note.txt
```

**实现机制**：
- `_segment_has_write_intent` 对 `grep`/`cat`/`echo`/`git` 等只读命令返回 False
- 即使段文本含 `memory/` 字面量，无写意图段不触发 Fix-1 兜底
- 重定向目标非 owned 时，只读命令放行

**边界**：
- 只读命令重定向到 owned 路径时会被拦截（`echo x > memory/kb/file`）
- 写命令提及 owned 字面量时会被拦截（`mv x memory/system/y`）

---

## 纵深防御机制

### 1. Manifest SHA-256 完整性校验

- audit 检查 1：`check_manifest_integrity` 对比 manifest 哈希
- 任何文件被删/改/新增均会被检出
- 提供事后检测能力，弥补字符串层盲区

### 2. 每日审计

- `daily_kb_audit` 入口调用 `check_manifest_integrity`
- 检测异常操作模式（如大文件、数据库文件、backups 目录）
- 生成审计报告供人工复核

### 3. 审计日志

- 所有 guard 拦截/放行决策记录到审计日志
- 可追溯异常操作序列
- 支持事后分析攻击模式

---

## 用户裁定

**2026-08-24 裁定**：三类残余（cwd 语义/变量拆散/编码路径）为已知接受风险，字符串层原理上不可拦截，不深修。纵深防御（manifest + 审计）提供足够安全保障。

**未来改进方向**：
- 跨段 cwd 累积追踪（收窄 cwd 语义残余）
- shell 变量追踪（收窄变量拆散残余）
- 编码检测启发式（如检测 base64 解码模式）

**当前优先级**：低。纵深防御已覆盖，残余风险可控。
