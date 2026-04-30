# Lesson: tmux retired, cmux only

Status: active

## Rule

- `workbot` 运行时只允许 `cmux`。
- `tmux` 仅保留历史材料，不允许作为执行入口。

## Enforcement

- `skills/tmux-skills/scripts/start_formal_runtime_chain.py` 默认阻断执行。
- `skills/tmux-runtime/scripts/start_formal_runtime_chain.py` 默认阻断执行。
- `skills/tmux-skills/scripts/run_script.py` 与 `skills/tmux-runtime/scripts/run_script.py` 默认阻断执行（`--list` 仅历史查看）。
- `scripts/start-day.sh` 默认阻断，并提示 `cmux` 引导脚本。

## Recovery path

- 正式入口：`<cmux-skills-dir>/scripts/bootstrap_claude_runtime.py`
