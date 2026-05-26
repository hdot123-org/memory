# 指南 & 高级用户板块摘要

---

## Building 板块

### 1. Building Plugins（构建插件）
- **核心功能**：创建可共享的 Droid 插件，打包 skills、commands、hooks 和 MCP 配置
- **关键配置/用法**：
  - 插件清单 `.factory-plugin/plugin.json` 必须包含 `name`、`description`、`version`
  - Skills 放在 `skills/` 目录，用 frontmatter 定义 `name` 和 `description`
  - Commands 放在 `commands/` 目录，用 `$ARGUMENTS` 捕获用户输入
  - Hooks 通过 `hooks/hooks.json` 配置，支持 `PreToolUse`/`PostToolUse` 生命周期
  - MCP 服务器配置在 `mcp.json` 中
- **最佳实践**：保持插件聚焦单一目的；完整文档化所有命令和配置
- **注意事项**：Droid 通过 Git commit hash 追踪插件版本，不支持版本锁定；插件 hooks 不能通过 `/hooks import` 导入

### 2. Droid Exec Tutorial（Droid Exec 教程）
- **核心功能**：使用 Droid Exec headless 模式构建"与代码库对话"功能
- **关键配置/用法**：
  - `--output-format debug` 流式输出结构化事件（tool_call、assistant_chunk 等）
  - `-m` 选择模型（glm-4.7 默认、gpt-5-codex、claude-sonnet-4-5）
  - `-r` 控制推理深度（off|low|medium|high）
  - 通过 Server-Sent Events (SSE) 实现实时流式传输
  - 环境变量：`DROID_MODEL_ID`、`DROID_REASONING`、`PORT`
- **最佳实践**：用只读模式（不加 `--auto`）构建用户功能；设置超时
- **注意事项**：不要将未过滤的用户输入直接传给 CLI；避免在无沙箱环境中使用 `--auto medium/high`

### 3. Droid VPS Setup（VPS 部署）
- **核心功能**：在 VPS 上部署 Droid 实现远程访问和 headless 自动化
- **关键配置/用法**：
  - SSH 密钥对认证（`~/.ssh/config` 配置别名）
  - 安装：`curl -fsSL https://app.factory.ai/cli | sh`
  - 首次运行 `droid` 通过浏览器认证
  - 使用 Termius 实现 iOS/Android 移动 SSH 访问
- **最佳实践**：先在本地测试再部署到 VPS；用 `droid exec` 构建 cron 定时任务
- **注意事项**：VPS 成本约 $5-10/月；注意保护 SSH 私钥安全

---

## Droid Exec 板块

### 4. Automated Code Review（自动代码审查）
- **核心功能**：自动化 GitHub/GitLab PR/MR 审查，识别 bug 并发表内联评论
- **关键配置/用法**：
  - 通过 `/install-code-review` 命令引导设置
  - `review_depth`：`deep`（全面，默认）或 `shallow`（快速）
  - 自定义审查准则放在 `.factory/skills/review-guidelines/SKILL.md`
  - 支持 `automatic_review`、`review_model`、`reasoning_effort` 等 input 参数
- **最佳实践**：用 paths 过滤只审查关键代码；跳过 draft PR 和 bot PR
- **注意事项**：审查聚焦明确 bug，跳过风格和架构意见；安全审查需单独使用 security-review skill

### 5. Automated Documentation（自动文档更新）
- **核心功能**：代码合并到 main 后自动更新文档并创建 PR
- **关键配置/用法**：
  - GitHub Actions workflow，触发条件为 push to main
  - `droid exec --auto low` 执行文档更新，显式禁止 commit/push
  - Git 操作在单独步骤中完成（关注点分离）
  - 支持定期批量更新模式（cron schedule）
- **最佳实践**：精确限定触发路径；信任 Droid 自主发现文档
- **注意事项**：生成摘要供人类审查；高频仓库建议用定期批量更新避免频繁触发

### 6. GitHub Actions（GitHub Actions 工作流）
- **核心功能**：提供即用型 GitHub Actions 工作流示例
- **关键配置/用法**：
  - 示例1：PR 自动审查与修复（review-and-fix）
  - 示例2：每日文档和测试自动更新（Daily Maintenance）
  - 示例3：安全与依赖扫描（Security Scanner）
  - 需要 `FACTORY_API_KEY` 在 repository secrets 中
- **最佳实践**：commit 消息包含 Co-authored-by 尾部；用 `--auto low` 仅做文件修改
- **注意事项**：工作流需要 `contents: write` 和 `pull-requests: write` 权限

### 7. Refactor Error Messages（改进错误消息）
- **核心功能**：自动批量改进代码库中 ResponseError 消息的可读性和可操作性
- **关键配置/用法**：
  - 脚本搜索含 ResponseError 的 .ts/.tsx 文件
  - 支持 `DRY_RUN=true` 预览模式
  - `CONCURRENCY` 控制并行处理数
  - 按模块增量处理，每步单独 commit
- **最佳实践**：先用 dry run 评估范围；按应用逐步处理
- **注意事项**：仅在 dry run 满意后再执行实际修改；执行后运行 typecheck 和 test

### 8. Automated Lint Fixes（自动 Lint 修复）
- **核心功能**：自动修复 ESLint 规则违规（以 NextJS API 路由中间件为例）
- **关键配置/用法**：
  - 基于 ESLint 规则名定位违规文件
  - 根据路由路径自动判断中间件类型（authenticated/public/cron/admin）
  - 支持 `DRY_RUN` 和 `CONCURRENCY` 配置
  - Prompt 中包含具体的 before/after 代码示例
- **最佳实践**：在 prompt 中提供具体的代码转换示例可大幅提高准确性
- **注意事项**：**关键成功要素**：定制脚本时务必包含 before/after 代码示例

### 9. Organize Imports（整理导入语句）
- **核心功能**：批量重构 import 语句——分组、排序、去重、移除未使用
- **关键配置/用法**：
  - 搜索 .js/.jsx/.ts/.tsx 文件
  - 分组顺序：外部包 → 内部导入 → 相对导入
  - 将 `require()` 转为 ES6 import，合并同模块导入
  - 支持 `DRY_RUN` 和 `CONCURRENCY`
- **最佳实践**：从小范围开始测试再扩展到整个代码库
- **注意事项**：按包/模块分批处理并分别 commit，便于审查

---

## Hooks 板块

### 10. Auto-formatting Code（自动格式化）
- **核心功能**：Droid 编辑文件后自动运行代码格式化工具
- **关键配置/用法**：
  - `PostToolUse` hook，matcher 为 `Create|Edit|ApplyPatch`
  - 支持多语言：Prettier（JS/TS）、Black+isort（Python）、gofmt（Go）、rustfmt（Rust）
  - 可在 `.factory/settings.json` 中配置或使用独立脚本
  - 支持条件格式化（仅格式化特定目录）
- **最佳实践**：配置文件纳入版本控制；设置合理的 timeout
- **注意事项**：格式化工具可能引入微妙 bug，提交前务必审查

### 11. Code Validation Hooks（代码验证钩子）
- **核心功能**：通过 hooks 执行代码验证、安全策略执行和最佳实践检查
- **关键配置/用法**：
  - `PreToolUse` 阻止敏感文件修改（exit code 2 阻止操作）
  - `PostToolUse` 执行 lint、TypeScript 类型检查、安全扫描
  - 密钥检测模式（AWS Key、Google API Key、GitHub Token 等）
  - 依赖安全审计（npm audit、pip-audit、cargo audit）
  - 架构合规检查（前端不导入后端等）
- **最佳实践**：提供清晰的错误信息和修复建议；用 exit 2 阻止，exit 0 警告
- **注意事项**：保持验证快速；使规则可配置

### 12. Git Workflow Hooks（Git 工作流钩子）
- **核心功能**：通过 hooks 执行 Git 工作流——提交验证、分支保护、自动 changelog
- **关键配置/用法**：
  - Conventional Commits 格式验证（feat/fix/docs/refactor/...）
  - 分支保护（阻止直接提交到 main/master/production）
  - 分支命名规范（feature/ISSUE-123-description）
  - 自动生成 CHANGELOG.md 条目
  - 推送前验证（lint + test + 冲突标记检查）
  - 推送新分支自动创建 PR
- **最佳实践**：PreToolUse 用于阻止，PostToolUse 用于自动化
- **注意事项**：提供清晰的错误信息；允许 WIP 前缀绕过；协调 Droid hooks 和 .git/hooks

### 13. Logging and Analytics（日志与分析）
- **核心功能**：追踪 Droid 使用情况、收集指标、分析开发模式
- **关键配置/用法**：
  - 命令日志（JSONL 格式）和文件修改追踪（SQLite）
  - 会话时长追踪（SessionStart/SessionEnd）
  - 工具使用统计、性能指标监控
  - Token 成本追踪
  - 周报生成
- **最佳实践**：使用结构化日志（JSON/SQLite）；最小化性能影响；保护敏感数据
- **注意事项**：实现日志轮转；尊重用户隐私（opt-in）

### 14. Custom Notifications（自定义通知）
- **核心功能**：Droid 等待输入或任务完成时发送桌面/Slack/邮件/webhook 通知
- **关键配置/用法**：
  - 桌面通知：macOS（osascript）、Linux（notify-send）、Windows（BurntToast）
  - Slack 集成（Webhook URL）
  - 邮件通知（sendmail/mail）
  - 支持 Notification、Stop、SubagentStop、SessionEnd 事件
  - 智能通知（仅空闲时通知）
- **最佳实践**：保持通知脚本快速（timeout ≤ 5s）；失败不阻塞 Droid
- **注意事项**：设置速率限制避免通知轰炸；检查系统通知权限

### 15. Session Automation（会话自动化）
- **核心功能**：自动加载项目上下文、配置环境和检查依赖
- **关键配置/用法**：
  - `SessionStart` hook 加载 README、git 日志、package.json 信息
  - 环境配置：Node.js 版本切换、Python venv 激活、PATH 设置
  - 使用 `DROID_ENV_FILE` 持久化环境变量
  - 基于 Git 分支加载不同上下文（main → 谨慎，feature → 相关 issue）
  - 自动检查依赖是否最新
- **最佳实践**：保持上下文简洁（摘要而非全文）；缓存昂贵操作
- **注意事项**：用 `DROID_ENV_FILE` 而非直接 export；检查工具是否安装后再使用

### 16. Testing Automation（测试自动化）
- **核心功能**：自动运行测试、追踪覆盖率、验证测试结果
- **关键配置/用法**：
  - `PostToolUse` hook 在文件修改后自动运行相关测试
  - 覆盖率阈值检查（`DROID_MIN_COVERAGE` 环境变量）
  - 新文件测试要求检查
  - 智能测试选择（仅运行受影响的测试）
  - 快照测试验证、测试性能监控、测试不稳定性检测
- **最佳实践**：尽可能异步运行测试；设置合理超时；缓存测试结果
- **注意事项**：确保 hook 环境与手动运行一致（NODE_ENV=test、CI=true）

---

## Power User 板块

### 17. Memory and Context Management（记忆与上下文管理）
- **核心功能**：构建持久化记忆系统让 Droid 跨会话记住偏好、决策和项目历史
- **关键配置/用法**：
  - 三层架构：个人记忆（`~/.factory/memories.md`）、项目记忆（`.factory/memories.md`）、规则（`.factory/rules/`）
  - 自动记忆捕获：`#` 前缀或 "remember this:" 短语触发
  - 也可用 skill 或 slash command (`/remember`) 实现手动捕获
  - 记忆分为偏好、决策、上下文、历史四个类别
- **最佳实践**：定期审查和归档旧记忆；在 AGENTS.md 中引用记忆文件
- **注意事项**：记忆文件需要定期维护，去除过时信息

### 18. Prompt Crafting（提示词技巧）
- **核心功能**：针对不同 AI 模型（Claude/GPT/Gemini）的模型特定提示词优化技巧
- **关键配置/用法**：
  - Claude：使用 XML 标签组织结构（`<context>`、`<task>`、`<requirements>`）；"Think through..." 触发推理
  - GPT：明确角色定义（"You are a..."）；使用编号步骤；明确输出格式
  - Gemini：充分利用长上下文；合理选择 reasoning level
  - 提供了 Claude 和 GPT 的 prompt refiner skill 模板
  - 模型选择策略表（按任务类型推荐模型和推理等级）
- **最佳实践**：具体描述结果；先给上下文再给指令；包含验收标准
- **注意事项**：不要用 Opus 处理简单编辑；高推理等级消耗更多 token 但减少重试

### 19. Rules and Conventions（规则与约定）
- **核心功能**：将编码标准文档化让 Droid 每次都遵循
- **关键配置/用法**：
  - 规则目录：`.factory/rules/`（项目级）和 `~/.factory/rules/`（个人级）
  - 规则模板：名称、适用范围、规则、示例、理由
  - 示例规则文件：TypeScript（interface 优先、禁 any、早返回）、React（函数组件、Props 命名）、Testing（测试命名、mock 边界）、Security（Zod 验证、不暴露内部错误）
  - 团队规则分层：`_base/`、`frontend/`、`backend/`、`testing/`
- **最佳实践**：规则要具体、可操作、含代码示例；用 hooks 自动执行规则
- **注意事项**：目前不支持基于文件模式的条件规则应用；不要重复 linter 已覆盖的规则

### 20. Token Efficiency（Token 效率）
- **核心功能**：通过项目配置、模型选择和工作流优化减少 token 消耗
- **关键配置/用法**：
  - 快速可靠的测试是减少 token 浪费的首要因素
  - 配置 lint 和 typecheck 让 Droid 在同一轮修复错误
  - 模型选择策略：Haiku（简单编辑）→ Sonnet/Codex（标准实现）→ Opus（复杂架构）
  - Spec Mode 用于复杂任务防止错误尝试
  - IDE 插件消除上下文收集的工具调用
  - 批量处理相似工作减少上下文重建
- **最佳实践**：用 `/cost` 监控使用量；具体优于泛化；匹配模型到任务
- **注意事项**：Token 浪费信号：高读取数、多次 grep、重复类似编辑、过长对话

### 21. Setup Checklist（设置清单）
- **核心功能**：完整的高级用户配置清单，分 5 个层级逐步优化 Droid
- **关键配置/用法**：
  - Level 1 基础：安装 IDE 插件、创建 AGENTS.md、配置默认模型
  - Level 2 记忆：创建 `memories.md`（个人+项目）、在 AGENTS.md 中引用
  - Level 3 规则：创建 `.factory/rules/` 目录、编写 TypeScript/Testing/Security 规则
  - Level 4 自动化：创建 prompt refiner skill、配置自动格式化和测试 hooks
  - Level 5 优化：启用 Spec Mode、配置模型切换、运行 readiness report
- **最佳实践**：按顺序完成各层级；每层有 checkpoint 验证
- **注意事项**：验证清单：IDE 连接、AGENTS.md 存在、memories 创建、rules 目录、skill 创建、hook 配置

### 22. Evaluating Context Compression（上下文压缩评估）
- **核心功能**：Factory Research 对上下文压缩策略的评估总结
- **关键配置/用法**：
  - 关键指标是 **tokens per task**（不是 tokens per request）
  - 评估了三种方案：Factory（结构化持久摘要）、OpenAI `/responses/compact`（不透明压缩）、Anthropic SDK（详细摘要但可能漂移）
  - Factory 的结构化方法整体得分最高（3.70/5 vs 3.44 vs 3.35）
  - 压缩率相似（约 98.6-99.3%），但 Factory 保留了更多关键细节
- **最佳实践**：优化 tokens per task 而非压缩率；结构化摘要优于不透明压缩
- **注意事项**：文件追踪是所有方法的弱项（最高仅 2.45/5）；probe-based 评估比文本相似度更贴近实际

---

## Skills 板块

### 23. Browser Automation（浏览器自动化）
- **核心功能**：轻量级 Chrome DevTools Protocol 工具集，让 Droid 操控浏览器
- **关键配置/用法**：
  - 5 个脚本：`start.js`（启动 Chrome）、`nav.js`（导航）、`eval.js`（执行 JS）、`screenshot.js`（截图）、`pick.js`（DOM 元素选取）
  - 安装：`npm install puppeteer-core`，放在 `.factory/skills/browser/`
  - `--profile` 标志同步真实 Chrome profile（含登录态）
  - 所有操作本地运行，凭证不离机器
- **最佳实践**：先启动 Chrome 再使用其他工具；JS 评估保持单行
- **注意事项**：基于 puppeteer-core，需要本机 Chrome；`eval.js` 中多行代码需用 IIFE

### 24. Automated QA（自动化质量保证）
- **核心功能**：端到端自动化 QA 测试——像真实用户一样测试 Web/CLI/API
- **关键配置/用法**：
  - `/install-qa` 一次性设置：深度代码分析 → 交互式问卷 → 生成 QA skill
  - `/qa` 运行测试：读取 git diff → 映射受影响 app → 执行相关测试流
  - Web 测试用 `agent-browser`（真实浏览器）；CLI 测试用 `tuistory`（虚拟终端）
  - 生成结构化报告含截图/终端快照作为证据
  - 支持 CI 集成（GitHub Actions workflow）
  - 失败学习机制：suggest/auto-commit/open PR
- **最佳实践**：问卷阶段越详细，生成的 QA skill 越精准；明确描述成功标准
- **注意事项**：install-qa 过程较慢（深度分析）；CI workflow 需要配置 GitHub secrets

### 25. Data Querying（数据查询）
- **核心功能**：安全查询内部分析数据库和数据服务，产出可复现的查询产物
- **关键配置/用法**：
  - 放在 `.factory/skills/data-querying/SKILL.md`
  - 可选辅助文件：`metrics.md`、`examples.sql`、`data-governance.md`
  - 遵循数据治理策略：优先用语义层/dbt model 而非原始表
  - 产出必须包含可重跑的查询和简短分析摘要
- **最佳实践**：先在小时间窗口验证查询；检查 join/filter/聚合是否扭曲结果
- **注意事项**：涉及敏感数据时确认目标位置合规；发现数据质量问题需提交 ticket

### 26. Vibe Coding（氛围编程）
- **核心功能**：快速原型开发现代 Web 应用，类似 Lovable/Bolt/v0 但完全本地
- **关键配置/用法**：
  - 放在 `.factory/skills/vibe-coding/SKILL.md`
  - 支持 React/Next.js/Vue/Svelte 等现代框架
  - 实现清单：发现规划 → 项目初始化 → 设计系统 → 功能实现 → 质量打磨 → 文档部署
  - 强调：总是先搜索最新官方文档再实现
  - 自动处理 SEO、Core Web Vitals、可访问性
- **最佳实践**：TypeScript 默认；mobile-first 响应式；组件化架构
- **注意事项**：不负责生产基础设施管理；不适用于移动原生开发

---

## 整体总结

**Building 板块**涵盖插件开发、headless CLI 集成和 VPS 部署三个核心场景，为开发者提供了将 Droid 能力打包分享和远程运行的基础设施。

**Droid Exec 板块**是一组生产级 CI/CD cookbook，展示了如何用 `droid exec --auto` 实现代码审查、文档更新、安全扫描、批量重构（错误消息/lint/import）等自动化工作流，所有脚本均遵循 dry-run → 增量处理 → commit 的安全模式。

**Hooks 板块**提供了六大类 hook 配方（格式化、验证、Git 工作流、日志分析、通知、会话自动化、测试），覆盖了从编辑后自动格式化到推送前完整验证的全部开发生命周期，核心模式是 `PreToolUse` 阻止 + `PostToolUse` 自动化。

**Power User 板块**是效率优化核心：记忆系统让 Droid 跨会话保持上下文，规则系统确保编码标准一致，提示词技巧针对不同模型优化，token 效率策略从项目配置到工作流模式全方位降低成本。Setup Checklist 将所有配置组织为 5 个递进层级。上下文压缩评估从研究角度论证了结构化摘要优于简单压缩。

**Skills 板块**提供了三个可直接使用的 skill 模板：浏览器自动化用于真实浏览器交互，自动化 QA 提供完整的端到端测试流水线，数据查询用于安全查询内部数据，Vibe Coding 则让 Droid 成为快速的本地 Web 应用原型构建伙伴。
