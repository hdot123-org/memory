"""Regression tests for M3-F10 gateway injection refactor.

Verifies:
- globals().update is removed from load_adapter_config/reload_adapter
- get_config returns new values after reload
- Adapter hot-switch semantics work correctly
- VAL-CPLX-016 runtime probe behavior
"""

from pathlib import Path
from unittest.mock import patch


def test_no_globals_update_in_load_adapter_config():
    """Verify load_adapter_config does not use globals().update."""
    import inspect

    from memory_core.tools.memory_hook_gateway import load_adapter_config

    source = inspect.getsource(load_adapter_config)
    assert "globals().update" not in source, "load_adapter_config should not contain globals().update"


def test_no_globals_update_in_reload_adapter():
    """Verify reload_adapter does not use globals().update."""
    import inspect

    from memory_core.tools.memory_hook_gateway import reload_adapter

    source = inspect.getsource(reload_adapter)
    assert "globals().update" not in source, "reload_adapter should not contain globals().update"


def test_get_config_returns_new_value_after_reload():
    """VAL-CPLX-016: reload -> get_config returns new values."""
    from memory_core.tools import memory_hook_gateway as gw

    # Get original value and save original profile
    original_value = gw.get_config("PROJECT_MAP_ROOT")
    assert original_value is not None, "Initial config should have PROJECT_MAP_ROOT"
    original_profile = dict(gw._adapter_profile)

    # Simulate reload with modified profile
    test_value = Path("/tmp/test-project-map")
    new_profile = dict(original_profile)
    new_profile["PROJECT_MAP_ROOT"] = test_value

    # Reload with new profile
    with patch.object(gw, "_load_adapter_profile", return_value=new_profile):
        gw.reload_adapter("default")

    # Verify get_config returns new value
    new_value = gw.get_config("PROJECT_MAP_ROOT")
    assert new_value == test_value, f"get_config should return new value after reload, got {new_value}"

    # Restore original
    with patch.object(gw, "_load_adapter_profile", return_value=original_profile):
        gw.reload_adapter("default")

    # Verify fallback to original
    restored_value = gw.get_config("PROJECT_MAP_ROOT")
    assert restored_value == original_value, "get_config should return original value after second reload"


def test_adapter_hot_switch_semantics():
    """Test adapter hot-switch: config changes propagate immediately."""
    from memory_core.tools import memory_hook_gateway as gw

    # Get initial config
    initial_canonical = gw.get_config("PROJECT_CANONICAL")
    assert initial_canonical is not None

    # Create a modified profile with different PROJECT_CANONICAL
    test_canonical = {"test-project": Path("/tmp/test-canonical")}
    modified_profile = dict(gw._adapter_profile)
    modified_profile["PROJECT_CANONICAL"] = test_canonical

    # Hot-switch by reloading
    with patch.object(gw, "_load_adapter_profile", return_value=modified_profile):
        gw.reload_adapter("default")

    # Verify immediate propagation
    current_canonical = gw.get_config("PROJECT_CANONICAL")
    assert current_canonical == test_canonical, "Hot-switch should immediately propagate config changes"

    # Restore
    with patch.object(gw, "_load_adapter_profile", return_value=gw._adapter_profile):
        gw.reload_adapter("default")


def test_get_config_dict_returns_shallow_copy():
    """Verify get_config_dict returns a safe copy for iteration."""
    from memory_core.tools import memory_hook_gateway as gw

    config_dict = gw.get_config_dict()
    assert isinstance(config_dict, dict)

    # Modify the copy should not affect original
    config_dict["TEST_KEY"] = "test_value"
    assert gw.get_config("TEST_KEY") is None, "Modifying get_config_dict result should not affect original config"


def test_config_lock_thread_safety():
    """Verify config operations are thread-safe."""
    import threading

    from memory_core.tools import memory_hook_gateway as gw

    errors = []

    def reader():
        try:
            for _ in range(100):
                _ = gw.get_config("PROJECT_MAP_ROOT")
                _ = gw.get_config_dict()
        except Exception as e:
            errors.append(e)

    # Start multiple reader threads
    threads = [threading.Thread(target=reader) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread safety test failed with errors: {errors}"
