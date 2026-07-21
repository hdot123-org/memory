# Lessons KB

Active lessons from project experience.

## Files

| File | Summary |
|------|---------|
| `cmux-project-venv-mandatory.md` | CMUX project virtualenv is mandatory for all Python runtime |
| `cmux-single-foreground-guard.md` | CMUX enforces single runtime and foreground guard |
| `pm-bot-global-binding-and-legacy-fence.md` | PM bot global binding rules and legacy fence |
| `tmux-retired-cmux-only.md` | tmux retired; only cmux allowed for workbot runtime |
| `audit-verification-methodology.md` | 代码审计核查的 4 个系统性盲区（范围锚定/命令漂移/AST bug/工具信任） |
| `pretooluse-guard-coverage-gap.md` | [技术债 P1] PreToolUse Guard 白名单盲区：未消费 CLASSIFICATION.md，根目录 deny patterns 缺失 |
| `pytest-fixture-finalizer-leak.md` | Python 3.11 CI 中 pytest-rerunfailures + pytest 8.x 的 fixture finalizer 泄漏问题（全局 --reruns 是反模式） |
| `gateway-globals-injection-mypy.md` | globals().update 动态注入导致 mypy name-defined errors（TYPE_CHECKING 解决方案） |
| `webhook-session-routing.md` | CI webhook session_id 路由失效（mtime scan 猜测 vs sessions-index.json 精确查找） |
