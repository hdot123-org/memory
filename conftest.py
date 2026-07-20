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
    import signal
    try:
        signal.alarm(0)  # Cancel any pending alarm
    except (ValueError, OSError, AttributeError):
        pass


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
