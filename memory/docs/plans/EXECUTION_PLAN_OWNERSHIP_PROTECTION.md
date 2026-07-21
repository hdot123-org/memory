# memory-core Ownership 保护升级 — 执行计划

> 状态：待审批
> 基于：UPGRADE_PLAN_OWNERSHIP_PROTECTION.md v3（合并版）
> 执行顺序：M1 → M5a → M2 → M3 → M4 → M5b → M6

---

## M1: Ownership 数据模型 + classify API + 默认域常量

### 步骤

| # | 动作 | 文件 | 具体改动 |
|---|------|------|----------|
| 1.1 | 新增模块 | `memory_core/ownership.py` | 创建文件，定义 `ProtectionLevel`/`OwnershipKind` 枚举、`OwnershipDomain`/`OwnershipResource`/`Owned`/`NotOwned`/`MemoryOwnership` 数据类、`DEFAULT_OWNERSHIP_DOMAINS`/`DEFAULT_OWNERSHIP_RESOURCES` 常量、`load_memory_ownership(project_root)` 加载函数、`classify_owned_path(rel_path, ...)` 分类函数、`validate_ownership_schema(ownership)` 防削弱校验函数 |
| 1.2 | 新增检测 | `memory_core/ownership.py` | 将 `_is_memory_core_source_repo()` 从 gateway/health/integrity 提取到此处作为共享 API，消除3处重复定义 |
| 1.3 | 新增测试 | `tests/test_ownership_model.py` | 测试：默认域 fallback、路径分类(owned/notOwned)、AGENTS.md block 判定5种场景、防削弱校验(删除/降级/非递归报错)、路径逃逸拒绝、source repo 检测准确 |
| 1.4 | 引用常量 | `memory_core/constants.py` | 新增 `OWNERSHIP_SCHEMA_VERSION = "memory-ownership-v1"` 常量 |

### 验收

```bash
python -m pytest tests/test_ownership_model.py -v
ruff check memory_core/ownership.py
```

### 解决绕过点

C1, H8(基础), H10(基础), 统一API缺失

---

## M5a: 最小 Factory PreToolUse P0 拦截

### 前置：M1 完成

### 步骤

| # | 动作 | 文件 | 具体改动 |
|---|------|------|----------|
| 5a.1 | 新增 guard | `memory_core/tools/pretooluse_guard.py` | 新建。读取 stdin payload → 解析 tool_name + target_path → 调用 `classify_owned_path()` → 输出 `{"decision":"block"/"allow","reason":"..."}` JSON |
| 5a.2 | 覆盖工具 | `memory_core/tools/pretooluse_guard.py` | Write/Edit/MultiEdit/NotebookEdit/Execute/Task 六种工具名解析逻辑。MultiEdit 逐路径检查任一 owned 则 block |
| 5a.3 | Execute 解析 | `memory_core/tools/pretooluse_guard.py` | 静态解析 mv/git mv/rm/cp/mkdir/touch/python -c/shell 重定向/heredoc/tee 命令中的目标路径，无法解析且含 owned root 字符串时 block |
| 5a.4 | AGENTS.md 判断 | `memory_core/tools/pretooluse_guard.py` | 5种场景表格逻辑：block内改→block, 删marker→block, block外追加→allow, 全覆盖无法判断→block, memory-init创建→allow |
| 5a.5 | 注册 hook | `memory_core/tools/factory_global_hooks.py` | 在 `install()` 函数中新增 PreToolUse hook 注册到 `~/.factory/settings.json`，保留已有 hooks |
| 5a.6 | 新增测试 | `tests/test_pretooluse_guard.py` | 测试：Write/Edit/MultiEdit 到 owned path block、Execute mv/rm/python block、AGENTS.md 5种场景、NotOwned 文件 allow、不确定路径 block、MEMORY_HOOK_FORCE 不放行 |
| 5a.7 | 更新测试 | `tests/test_factory_global_hooks.py` | 验证 settings.json 中 PreToolUse hook 注册，不影响已有 hooks |

### 验收

```bash
python -m pytest tests/test_pretooluse_guard.py tests/test_factory_global_hooks.py -v
echo '{"tool_name":"Edit","file_path":"memory/docs/INDEX.md"}' | python -m memory_core.tools.pretooluse_guard
# 预期输出: {"decision":"block","reason":"..."}
```

### 解决绕过点

F1(PreToolUse), C1(memory整域block), C2(force先被guard阻断), F2(Task payload检查), F3(Execute覆盖), H5, H6, H8/H9

---

## M2: memory-init ownership.toml + validate/audit 迁移

### 前置：M1 + M5a 完成

### 步骤

| # | 动作 | 文件 | 具体改动 |
|---|------|------|----------|
| 2.1 | init 生成 ownership | `memory_core/tools/init_project_memory.py` | create/adopt/update/repair 模式末尾新增：调用 `load_memory_ownership()` 获取当前 ownership → 写入 `.memory/ownership.toml`（TOML格式，含 schema_version/memory_version/domains/resources/policy） |
| 2.2 | 收紧 --force | `memory_core/tools/init_project_memory.py` | `--force` 分支增加：对每个待写路径调用 `classify_owned_path()`，owned 且非 authorized maintenance 则拒绝并报错 |
| 2.3 | validate 新增检查 | `memory_core/tools/validate_project_memory.py` | 新增 `check_ownership_declaration()`：校验 ownership.toml 存在 + schema 合法 + 默认域未删除/降级 |
| 2.4 | validate domain | `memory_core/tools/validate_project_memory.py` | 新增 `check_domain_integrity()`：校验 .memory/memory/project-map 存在、未逃逸、非 symlink |
| 2.5 | validate docs | `memory_core/tools/validate_project_memory.py` | 新增 `check_document_paths()`：校验 memory/docs/INDEX.md、memory/kb/INDEX.md、project-map/INDEX.md 索引一致性 |
| 2.6 | validate shared | `memory_core/tools/validate_project_memory.py` | 新增 `check_shared_resources()`：校验 AGENTS.md marker 成对、.claude/hooks.json 条目完整 |
| 2.7 | 读失败处理 | `memory_core/tools/validate_project_memory.py` | 将 owned critical/protected 文件读失败从 `continue` 改为记录 error |
| 2.8 | audit ownership | `memory_core/tools/audit_project_layout.py` | 将 `FORBIDDEN_OVERWRITE_PATTERNS` 硬编码列表替换为 `classify_owned_path()` 调用；新增 ownership findings：`ownership_missing`/`domain_missing`/`domain_weakened`/`marker_tampered`/`index_inconsistent`/`owned_file_unreadable` |
| 2.9 | apply 改用 API | `memory_core/tools/apply_residue_plan.py` | 将 `FORBIDDEN_OVERWRITE_PATTERNS` + `_is_forbidden_path()` 替换为 `classify_owned_path()` |
| 2.10 | 新增测试 | `tests/test_ownership_model.py` 扩展 + `tests/test_init_ownership.py` 新增 | init 生成 ownership.toml 测试、force 限制测试、validate 4类检查测试、audit ownership findings 测试、apply ownership-aware 测试 |

### 验收

```bash
python -m pytest tests/test_init_ownership.py tests/test_validate_project_memory_direct.py tests/test_audit_project_layout.py tests/test_apply_residue_plan.py -v
```

### 解决绕过点

C2(force限制), H10(validate不静默跳过), hard-coded forbidden分散

---

## M3: Hook 读写分离 — source repo readonly context-package

### 前置：M1 完成

### 步骤

| # | 动作 | 文件 | 具体改动 |
|---|------|------|----------|
| 3.1 | 三模式 runtime | `memory_core/tools/memory_hook_gateway.py` | 将 `main()` 中 `_is_memory_core_source_repo()` 后的 `{}` 短路分支改为：构建 readonly context-package（package_kind=source-repo-rules, mode=read-only, allowed_writes={}, rules=注入DOT_MEMORY_SPEC+BOUNDARY+INDEX+ownership说明）|
| 3.2 | 删除重复定义 | `memory_core/tools/memory_hook_gateway.py` | 删除本地 `_is_memory_core_source_repo()` 改为 `from memory_core.ownership import is_memory_core_source_repo` |
| 3.3 | Factory wrapper | `memory_core/tools/factory_global_hooks.py` | source repo 分支不再 `{}`，改为 `READONLY=1` + exec gateway |
| 3.4 | Codex wrapper | `memory_core/tools/codex_global_hooks.py` | 同步 Factory 策略 |
| 3.5 | Claude wrapper | `memory_core/tools/claude_global_hooks.py` | 新增/更新 source repo readonly 覆盖 |
| 3.6 | 删除重复定义 | `memory_core/tools/memory_hook_integrity_manifest.py` | 删除本地 `_is_memory_core_source_repo()` 改为 import |
| 3.7 | 删除重复定义 | `memory_core/tools/memory_health_report.py` | 删除本地 `_is_memory_core_source_repo()` 改为 import |
| 3.8 | delegate 语义 | `memory_core/tools/memory_hook_impls.py` | delegate preflight 异常不再返回 noop 成功，改为返回 degraded package 含错误信息 |
| 3.9 | wrapper 失败可见 | `memory_core/tools/factory_global_hooks.py` + `codex_global_hooks.py` | 删除 `|| true`，初始化失败输出 structured error |
| 3.10 | 新增测试 | `tests/test_source_repo_readonly.py` | 测试：source repo fixture → hook 输出 readonly context-package → 包含规则 → git status 无变化 → mtime 无变化 |

### 验收

```bash
python -m pytest tests/test_source_repo_readonly.py tests/test_factory_global_hooks.py tests/test_codex_global_hooks.py tests/test_claude_global_hooks.py -v
```

### 解决绕过点

H1, H2, H3, H4, H8(NoopHostDelegate分离), H9

---

## M4: Integrity ownership-aware + 禁止 auto re-sign

### 前置：M2 + M3 完成

### 步骤

| # | 动作 | 文件 | 具体改动 |
|---|------|------|----------|
| 4.1 | 签名范围 | `memory_core/tools/memory_hook_integrity_manifest.py` | `sign()` 函数：签名范围从固定 canonical patterns 改为调用 `load_memory_ownership()` → 遍历 owned domains/resources 计算 digest。新增 ownership.toml 到签名链 |
| 4.2 | manifest v2 | `memory_core/tools/memory_hook_integrity_manifest.py` | manifest entry 新增字段：ownership_id, protection_level, classification_source |
| 4.3 | 禁止 auto re-sign | `memory_core/tools/memory_hook_integrity_verify.py` | `verify()` 失败后删除任何 re-sign 逻辑，改为返回 (ok=False, errors=[...]) |
| 4.4 | verify fail 语义 | `memory_core/tools/memory_hook_gateway.py` | verify 失败分支：无交互场景默认 block，不再 degraded |
| 4.5 | readonly 零副作用 | `memory_core/tools/memory_hook_integrity_manifest.py` | source repo readonly 下 sign/verify 不读写任何文件 |
| 4.6 | re-sign CLI | `memory_core/tools/memory_integrity_resign.py` | 新增：解析 args → validate --strict → verify 显示差异 → 需 reason + token/flag → 写 audit → sign v2 |
| 4.7 | 新增测试 | `tests/test_integrity_ownership.py` + `tests/test_integrity_resign.py` | 测试：ownership-derived签名、verify fail不re-sign、re-sign CLI安全规则、readonly零副作用、v1兼容 |

### 验收

```bash
python -m pytest tests/test_integrity_ownership.py tests/test_integrity_resign.py tests/test_l2_integrity.py -v
```

### 解决绕过点

H7, verify fail auto re-sign, ownership削弱, delegate语义

---

## M5b: 子代理 policy 注入 + cwd 固定 + P1 语义

### 前置：M5a 完成

### 步骤

| # | 动作 | 文件 | 具体改动 |
|---|------|------|----------|
| 5b.1 | policy 注入 | `memory_core/tools/pretooluse_guard.py` | Task 工具处理：解析 payload 中的 task prompt → 注入 ownership policy block（列出 protected domains + resources + 禁止指令）|
| 5b.2 | cwd 固定 | `memory_core/tools/pretooluse_guard.py` | Task 工具处理：固定 cwd 为 project_root，不随 PWD 变化 |
| 5b.3 | Execute P1 | `memory_core/tools/pretooluse_guard.py` | 扩展 Execute 解析：rsync/node -e/shell glob/相对路径/环境变量展开 |
| 5b.4 | AGENTS diff-aware | `memory_core/tools/pretooluse_guard.py` | Edit/MultiEdit 对 AGENTS.md 使用 content_before/after 判断是否触碰 block |
| 5b.5 | MultiEdit 逐项 | `memory_core/tools/pretooluse_guard.py` | MultiEdit 多路径逐项 classify，输出每项的分类结果 |
| 5b.6 | NoopHostDelegate | `memory_core/tools/memory_hook_impls.py` + `memory_hook_interfaces.py` | `NoopHostDelegate` 返回值明确标注 host_unavailable=True，policy_decision 与 delegate availability 分离 |
| 5b.7 | 新增测试 | `tests/test_pretooluse_guard.py` 扩展 | Task payload 注入测试、cwd 固定测试、Execute P1 覆盖测试、AGENTS diff-aware 测试 |

### 验收

```bash
python -m pytest tests/test_pretooluse_guard.py tests/test_noop_host_delegate.py -v
```

### 解决绕过点

F2(子代理policy), F3(MCP/Execute P1), H5, H6, H8, H9, cwd漂移

---

## M6: 管辖域变更流程 + 旧项目迁移 + hook 升级策略

### 前置：M2 + M3 + M4 + M5b 完成

### 步骤

| # | 动作 | 文件 | 具体改动 |
|---|------|------|----------|
| 6.1 | ownership CLI | `memory_core/tools/ownership_cli.py` | 新增：show（显示当前 ownership）、validate（校验 schema）、plan-update（生成迁移计划不写文件）、apply-update（执行需审批）|
| 6.2 | hook 升级 | `memory_core/tools/hook_upgrade.py` | 新增：inspect（检测旧 wrapper/缺 PreToolUse/|| true/FORCE noop）、plan-upgrade（生成升级计划）、apply-upgrade（backup + preserve unrelated + apply）|
| 6.3 | 迁移 | `memory_core/tools/migrate_project_memory.py` | 扩展：旧项目无 ownership.toml → 生成默认；旧 manifest v1 → 可读，新 sign 写 v2 |
| 6.4 | 兼容矩阵 | `memory_core/compat.py` | 新增：memory-core version / ownership schema / hook schema / manifest version / min installer version 的兼容性检查 |
| 6.5 | 新增测试 | `tests/test_ownership_cli.py` + `tests/test_hook_upgrade.py` + `tests/test_compat.py` | CLI 测试、hook 升级测试、兼容矩阵测试 |

### 验收

```bash
python -m pytest tests/test_ownership_cli.py tests/test_hook_upgrade.py tests/test_compat.py -v
```

### 解决绕过点

旧hook绕过、旧项目无ownership、版本不兼容、escape hatch混乱

---

## 全局验收

全部里程碑完成后运行：

```bash
ruff check memory_core/ tests/
python -m pytest tests/ -v
python3 scripts/check_boundary.py 2>/dev/null || true
```

### 事故复现验收清单

| # | 攻击场景 | 预期结果 |
|---|----------|----------|
| A1 | `Edit memory/docs/INDEX.md` | PreToolUse block |
| A2 | `Execute "mv memory/kb tmp/"` | PreToolUse block |
| A3 | `Execute "git mv memory/docs/design/a.md docs/a.md"` | PreToolUse block |
| A4 | `Task` 描述要求移动 `memory/kb/**` | PreToolUse block 或 policy 拒绝 |
| A5 | `memory-init --force` 覆盖 owned files | init 拒绝 |
| A6 | `MEMORY_HOOK_FORCE=1` 写 owned path | guard 不放行 |
| A7 | integrity verify fail 后 hook 自动 re-sign | 不 re-sign |
| A8 | source repo hook 尝试写 artifact | 零副作用 |
| A9 | NoopHostDelegate 吞 policy failure | 返回 host_unavailable |
| A10 | `python -c 'open("memory/docs/INDEX.md","w")'` | PreToolUse block |

---

## 文件变更汇总

| 文件 | 里程碑 | 操作 |
|------|--------|------|
| `memory_core/ownership.py` | M1 | **新建** |
| `memory_core/constants.py` | M1 | 修改 |
| `tests/test_ownership_model.py` | M1 | **新建** |
| `memory_core/tools/pretooluse_guard.py` | M5a | **新建** |
| `memory_core/tools/factory_global_hooks.py` | M5a+M3 | 修改 |
| `tests/test_pretooluse_guard.py` | M5a+M5b | **新建** |
| `memory_core/tools/init_project_memory.py` | M2 | 修改 |
| `memory_core/tools/validate_project_memory.py` | M2 | 修改 |
| `memory_core/tools/audit_project_layout.py` | M2 | 修改 |
| `memory_core/tools/apply_residue_plan.py` | M2 | 修改 |
| `tests/test_init_ownership.py` | M2 | **新建** |
| `memory_core/tools/memory_hook_gateway.py` | M3+M4 | 修改 |
| `memory_core/tools/codex_global_hooks.py` | M3 | 修改 |
| `memory_core/tools/claude_global_hooks.py` | M3 | 修改 |
| `memory_core/tools/memory_hook_integrity_manifest.py` | M3+M4 | 修改 |
| `memory_core/tools/memory_hook_integrity_verify.py` | M4 | 修改 |
| `memory_core/tools/memory_health_report.py` | M3 | 修改 |
| `memory_core/tools/memory_hook_impls.py` | M3+M5b | 修改 |
| `memory_core/tools/memory_hook_interfaces.py` | M5b | 修改 |
| `memory_core/tools/memory_integrity_resign.py` | M4 | **新建** |
| `tests/test_source_repo_readonly.py` | M3 | **新建** |
| `tests/test_integrity_ownership.py` | M4 | **新建** |
| `tests/test_integrity_resign.py` | M4 | **新建** |
| `memory_core/tools/ownership_cli.py` | M6 | **新建** |
| `memory_core/tools/hook_upgrade.py` | M6 | **新建** |
| `memory_core/tools/migrate_project_memory.py` | M6 | 修改 |
| `memory_core/compat.py` | M6 | **新建** |
| `tests/test_ownership_cli.py` | M6 | **新建** |
| `tests/test_hook_upgrade.py` | M6 | **新建** |
| `tests/test_compat.py` | M6 | **新建** |

**总计**：新建 14 个文件，修改 13 个文件

---

## 执行规则

1. 每个里程碑开始前需用户明确审批
2. 严格按 M1 → M5a → M2 → M3 → M4 → M5b → M6 顺序
3. 每个里程碑完成后运行对应测试
4. 所有变更完成后统一 commit
5. 不得在计划外修改本计划"文件变更汇总"表中列出的 owned 文件路径（ADR、决策记录、迁移指南等文档产出不受此限制）
