"""Regression tests for the vulture baseline in memory_core/tools/_gateway_telemetry.py.

PR #930 拆分时将 ``_write_handler`` 的信号参数从 ``_signum``/``_frame`` 改名为
``signum``/``frame``，触发 vulture ``unused variable`` 发现（exit 3），违反
VAL-LINT-011/022 门禁。本测试钉住下划线前缀约定，防止再次回归。
"""

from __future__ import annotations

import inspect

from memory_core.tools import _gateway_telemetry


def _prompt_log_source() -> str:
    return inspect.getsource(_gateway_telemetry._log_prompt_submit)


def test_write_handler_params_use_underscore_prefix() -> None:
    """_write_handler 信号参数必须以下划线前缀标记为有意未使用（vulture 口径）。"""
    source = _prompt_log_source()
    assert "def _write_handler(_signum" in source, (
        "_write_handler 首参数必须命名为 _signum（下划线前缀），"
        "否则 vulture --min-confidence 80 报 unused variable（VAL-LINT-011）"
    )
    assert "_frame" in source, (
        "_write_handler 次参数必须命名为 _frame（下划线前缀），"
        "否则 vulture --min-confidence 80 报 unused variable（VAL-LINT-011）"
    )


def test_write_handler_still_raises_timeout_error() -> None:
    """参数改名不得影响超时语义：处理器仍抛出 _PromptLogTimeoutError。"""
    source = _prompt_log_source()
    handler_block = source.split("def _write_handler", 1)[1]
    assert "_PromptLogTimeoutError" in handler_block, (
        "_write_handler 必须保持抛出 _PromptLogTimeoutError（PR #930 前语义）"
    )
