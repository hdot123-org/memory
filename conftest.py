# No workbot deprecation filter needed — workbot adapter has been archived.


import pytest


@pytest.fixture(autouse=True)
def _cancel_pending_sigalrm():
    """Cancel any pending SIGALRM after each test to prevent cross-test signal leakage.

    session_end_logger._set_timeout() uses signal.alarm(2) for timeout handling.
    If a test triggers this and finishes before the alarm fires, the pending
    SIGALRM can fire during a later unrelated test, calling sys.exit(0) and
    causing a spurious SystemExit: 0 failure. Cancelling the alarm in teardown
    isolates each test from its predecessors' timeouts.
    """
    yield
    import contextlib
    import signal

    # Cancel any pending alarm
    with contextlib.suppress(ValueError, OSError, AttributeError):
        signal.alarm(0)


@pytest.fixture(autouse=True)
def neutralize_tmpdir_for_tests(monkeypatch, tmp_path):
    """Neutralize $TMPDIR during tests to prevent denylist from rejecting tmp_path.

    On macOS, $TMPDIR points to /var/folders/... where pytest creates tmp_path directories.
    The denylist correctly rejects paths under $TMPDIR, but this breaks test isolation.

    Solution: Enable denylist bypass for all tests except those explicitly testing
    the denylist logic. This allows existing tests to use tmp_path normally.
    """
    # Enable denylist bypass for all tests
    monkeypatch.setenv("MEMORY_CORE_BYPASS_DENYLIST", "1")


@pytest.fixture(autouse=True)
def _guard_load_key_not_patched():
    """Guard against cross-test patch leakage of load_key.

    Some tests (notably test_abc_layer_signing.py) need to mock
    memory_hook_integrity_keys.load_key for CI environments. If teardown
    fails to restore the original, subsequent tests that depend on the
    real load_key (e.g., test_integrity_resign.py::test_resign_no_key_fails)
    will see a patched function and fail spuriously.

    This fixture asserts that load_key is the original function after each
    test teardown. If a leak is detected, the assertion fails immediately
    with a clear message identifying the culprit test.
    """
    yield
    import memory_core.tools.memory_hook_integrity_keys as _key_module
    # Check if load_key has been patched (lambdas or closures have different __name__)
    if hasattr(_key_module.load_key, "__name__"):
        assert _key_module.load_key.__name__ == "load_key", (
            f"load_key was patched and not restored! "
            f"Current: {_key_module.load_key.__name__}. "
            f"This indicates a test in the previous run failed to restore load_key. "
            f"Use monkeypatch.setattr() instead of direct module attribute assignment."
        )



