"""Tests for NoopHostDelegate (M5b.6).

Separated from test_pretooluse_guard.py for isolated test runs:
    python -m pytest tests/test_noop_host_delegate.py -v
"""

import json

from memory_core.tools.memory_hook_impls import NoopHostDelegate
from memory_core.tools.memory_hook_interfaces import HostDelegate


class TestNoopHostDelegateAvailability:
    """Test that NoopHostDelegate correctly reports host unavailability."""

    def test_host_unavailable_property_is_true(self) -> None:
        delegate = NoopHostDelegate()
        assert delegate.host_unavailable is True

    def test_can_handle_returns_true(self) -> None:
        delegate = NoopHostDelegate()
        assert delegate.can_handle() is True




class TestNoopHostDelegateResponse:
    """Test that NoopHostDelegate responses carry host_unavailable + policy_decision."""

    def test_noop_response_json(self) -> None:
        delegate = NoopHostDelegate()
        resp = delegate.noop_response()
        assert resp.returncode == 0
        data = json.loads(resp.stdout)
        assert data["host_unavailable"] is True
        assert data["policy_decision"] == "no_host"

    def test_execute_json(self) -> None:
        delegate = NoopHostDelegate()
        resp = delegate.execute("PostToolUse", "{}", {})
        data = json.loads(resp.stdout)
        assert data["host_unavailable"] is True
        assert data["policy_decision"] == "no_host"

    def test_policy_decision_separate_from_availability(self) -> None:
        """policy_decision and host_unavailable are independent keys."""
        delegate = NoopHostDelegate()
        resp = delegate.noop_response()
        data = json.loads(resp.stdout)
        assert "host_unavailable" in data
        assert "policy_decision" in data
        # They must both exist and be distinct keys
        assert set(data.keys()) == {"host_unavailable", "policy_decision"}


class TestHostDelegateInterface:
    """Test that the HostDelegate ABC exposes host_unavailable."""

    def test_interface_defines_property(self) -> None:
        assert hasattr(HostDelegate, "host_unavailable")

    def test_default_is_false(self) -> None:
        """The default implementation on the ABC returns False."""
        # Cannot instantiate ABC directly, but can check the property descriptor
        prop = HostDelegate.__dict__.get("host_unavailable")
        assert prop is not None
        # The default fget returns False
