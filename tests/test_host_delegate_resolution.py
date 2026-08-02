"""Tests for resolve_host_delegate host delegation resolution (INFRA-3).

验证团队项目内委派给 Factory 的解析链路。覆盖 factory 主机的
auto / noop / cmux 模式解析，以及非 factory 主机的 fallback 路径。

运行:
    python -m pytest tests/test_host_delegate_resolution.py -v
"""

import inspect

from memory_core.tools.memory_hook_impls import (
    FactoryDelegate,
    NoopHostDelegate,
    resolve_host_delegate,
)
from memory_core.tools.memory_hook_interfaces import HostDelegate


class TestResolveHostDelegateFactoryHost:
    """解析 factory 主机的 delegate。"""

    def test_factory_auto_mode_returns_factory_delegate(self) -> None:
        """factory + auto 模式返回 FactoryDelegate（can_handle 为 True）。"""
        delegate = resolve_host_delegate("factory", mode="auto")
        assert isinstance(delegate, FactoryDelegate)
        assert delegate.host_unavailable is False

    def test_factory_default_mode_is_auto(self) -> None:
        """不显式传 mode 时，默认行为等价于 auto，返回 FactoryDelegate。"""
        delegate = resolve_host_delegate("factory")
        assert isinstance(delegate, FactoryDelegate)
        assert delegate.host_unavailable is False

    def test_factory_noop_mode_returns_noop_delegate(self) -> None:
        """factory + noop 模式强制返回 NoopHostDelegate。"""
        delegate = resolve_host_delegate("factory", mode="noop")
        assert isinstance(delegate, NoopHostDelegate)
        assert delegate.host_unavailable is True

    def test_factory_cmux_mode_returns_factory_delegate(self) -> None:
        """factory + cmux 模式返回 FactoryDelegate。"""
        delegate = resolve_host_delegate("factory", mode="cmux")
        assert isinstance(delegate, FactoryDelegate)
        assert delegate.host_unavailable is False

    def test_factory_unknown_mode_behaves_like_auto(self) -> None:
        """factory + 未知 mode 字符串回退到 auto 行为，返回 FactoryDelegate。"""
        delegate = resolve_host_delegate("factory", mode="totally-unknown-mode")
        assert isinstance(delegate, FactoryDelegate)
        assert delegate.host_unavailable is False


class TestResolveHostDelegateNonFactoryHost:
    """非 factory 主机一律 fallback 到 NoopHostDelegate。"""

    def test_non_factory_host_codex_returns_noop(self) -> None:
        delegate = resolve_host_delegate("codex")
        assert isinstance(delegate, NoopHostDelegate)
        assert delegate.host_unavailable is True

    def test_non_factory_host_empty_string_returns_noop(self) -> None:
        delegate = resolve_host_delegate("")
        assert isinstance(delegate, NoopHostDelegate)

    def test_non_factory_host_with_explicit_auto_still_noop(self) -> None:
        """即使显式请求 auto 模式，非 factory 主机仍然 fallback。"""
        delegate = resolve_host_delegate("claude", mode="auto")
        assert isinstance(delegate, NoopHostDelegate)


class TestResolveHostDelegateSignature:
    """验证函数签名契约。"""

    def test_mode_parameter_defaults_to_auto(self) -> None:
        """mode 参数默认值必须是 'auto'。"""
        signature = inspect.signature(resolve_host_delegate)
        mode_param = signature.parameters.get("mode")
        assert mode_param is not None
        assert mode_param.default == "auto"

    def test_return_value_is_host_delegate(self) -> None:
        """所有解析结果都必须是 HostDelegate 实例。"""
        for host, mode in [("factory", "auto"), ("factory", "noop"), ("codex", "auto")]:
            assert isinstance(resolve_host_delegate(host, mode=mode), HostDelegate)
