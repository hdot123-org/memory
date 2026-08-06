---
type: [KB:LESSON]
title: "纵深安全 vs 扁平规则：信任根是安全体系的锚点"
shortname: DEFENSE-IN-DEPTH-SECURITY
status: accepted
created: 2026-08-03
updated: 2026-08-03
source: local-canonical
confidence: high
tags: [lesson, security, trust, defense-in-depth, folder-trust, guard]
related: [pretooluse-guard-coverage-gap, D-007-doc-routing-engine]

---

# 纵深安全 vs 扁平规则：信任根是安全体系的锚点

## 经验来源

oh-my-cli vs memory-core 工程对比分析（维度 03：分层安全 vs 单层 Guard）。oh-my-cli 实现五层纵深防御，memory-core 是单层 Guard + 扁平规则匹配。

## 核心教训

### 教训 1：信任根必须在用户侧，不可在项目内

oh-my-cli 的 `folder-trust.ts` 将信任存储在用户侧（`~/.oh-my-cli/trust.json`），而非项目本地。一个不被信任的仓库无法自我授权。这是整个安全体系的锚点。

memory-core 的 guard 没有信任根概念——只要 `memory/system/` 目录存在就进入分类逻辑，没有"这个工作区是否受信任"的判断。恶意仓库包含同名目录即可绕过隔离。

**原则**：安全体系的信任根必须存放在被保护对象无法篡改的位置。项目内的配置文件可以被恶意项目伪造，用户主目录的配置不能。

### 教训 2：安全层之间必须有从属关系，不能各自独立

oh-my-cli 的五层安全有明确的从属关系：

| 层 | 职责 | 从属关系 |
|----|------|---------|
| Folder Trust | 信任根：工作区是否可信 | 顶层锚点 |
| Command Policy | 命令分类：五维（network/write/credential/destructiveGit/pathEscape） | 不可被 approval mode 绕过 |
| Approval Mode | 审批模式：default/auto-edit/yolo | 从属于 folder trust |
| Unicode 防伪 | 字符防伪：零宽/双向控制符/形似引号 | 独立层 |
| Sandbox 白名单 | 网络出口：严格白名单 | 最后一道防线 |

关键属性：**Approval mode 从属于 folder trust**——yolo 模式不能在 untrusted 工作区上放宽边界。

memory-core 的 guard 是扁平的——`pretooluse_guard.py` 做路径→ownership 单维检查，`_guard_classify.py` 做分类，但没有层级关系。各规则独立生效，无组合语义。

**原则**：多层安全的有效性取决于层间关系，而非层的数量。没有从属关系的多层安全等于多个独立开关，攻击者只需绕过任一层。

### 教训 3：命令分类需要多维度，单维分类不够

oh-my-cli 的 `command-policy.ts`（约 25KB）做五维分类：`network` | `write` | `credential` | `destructiveGit` | `pathEscape`，配合六条拒绝规则（`destructive_git` | `credential_access` | `path_escape` | `destructive_removal` | `device_overwrite` | `remote_code_execution`）。

memory-core 的 `_guard_classify.py` 只做"路径→ownership"单维匹配——文件在受保护路径内就 block，不在就放行。无法识别 `curl | bash`（远程代码执行）、凭证路径访问、destructive git 操作。

**原则**：安全分类的维度应与威胁模型匹配。只做路径检查的安全系统无法防御命令注入、凭证窃取、管道攻击等向量。

### 教训 4：Fail-closed 必须贯穿全链路

oh-my-cli 的每一层安全都有 fail-closed 语义：
- Folder trust 未知 → `mutatingAllowed: false`
- Command policy 无法分类 → 拒绝（不可被 approval mode 绕过）
- Unicode 防伪 → 替换为 `[U+XXXX]` 可见标记，不静默放行

memory-core 的 guard 在 JSON 解析失败时 exit 0（放行），是 fail-open。`pretooluse-guard-coverage-gap.md` 记录的覆盖盲区也源于白名单设计（未列入即放行）。

**原则**：安全系统的默认行为必须是拒绝。无法判断时放行（fail-open）等于没有安全层。

## 迁移方向

| 建议 | 优先级 | 可行性 | 实施方向 |
|------|--------|--------|----------|
| 引入 folder trust 信任根 | 高 | 中 | 在 `~/.memory-core/` 下建 `trust.json`，guard 入口先检查信任状态 |
| Guard 改为 fail-closed | 高 | 高 | `pretooluse_guard.py` 解析失败时返回 block + reason，非 allow |
| 命令分类扩展为多维 | 中 | 中 | 在 `_guard_classify.py` 中增加 network/credential/destructive 维度 |
| Approval mode 从属于 trust | 中 | 中 | 定义 trust → approval 的从属关系，untrusted 工作区不允许 yolo |

## 关联

- 对比文档：oh-my-cli 安全架构分析文档（security.md）
- 差距总结：oh-my-cli 工程对比分析文档（gap-priorities.md）→ G-03-1, G-03-2, G-03-3, G-03-4, G-03-5
- 相关教训：`pretooluse-guard-coverage-gap.md`（白名单盲区的具体案例）
