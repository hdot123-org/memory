# No workbot deprecation filter needed — workbot adapter has been archived.


import pytest


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
