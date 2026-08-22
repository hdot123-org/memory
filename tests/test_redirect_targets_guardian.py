"""Guardian test for _REDIRECT_TARGETS coverage (M3-post-scrutiny).

Ensures that all facade-level monkeypatch targets used by tests are
registered in _REDIRECT_TARGETS, so setattr propagation works correctly.

This prevents the regression where new constants/imports consumed by
split modules are added to the facade but not to the redirect table,
causing monkeypatch.setattr(gw, 'X', mock) to silently fail.
"""


def test_redirect_targets_covers_high_frequency_monkeypatch_targets():
    """VAL-REDIRECT-001: _REDIRECT_TARGETS must cover all facade monkeypatch targets.

    Tests historically use monkeypatch.setattr(gateway_module, 'X', mock) to stub
    constants and imports. After the M3 gateway split, these must be registered
    in _REDIRECT_TARGETS to propagate to the actual consumer modules.

    This test asserts that all known high-frequency monkeypatch targets are present.
    """
    from memory_core.tools._gateway_patch_redirect import _REDIRECT_TARGETS

    # These are the constants/imports that tests monkeypatch on the facade.
    # If you add a new one here and the test fails, you need to register it
    # in _REDIRECT_TARGETS with the correct target modules.
    required_targets = {
        # Path constants (defined in _gateway_config, consumed by multiple modules)
        "ARTIFACT_ROOT",
        "CONTEXT_ROOT",
        "ERROR_LOG",
        "EVENT_LOG",
        "REPO_ROOT",
        "WORKSPACE_ROOT",
        "PROJECT_LIFECYCLE_ROOT",
        # Internal constants
        "_FORCE_HOOK",
        # Re-exported stdlib modules (test patch targets)
        "socket",
        "datetime",
        # Functions commonly stubbed in tests
        "append_error_log",
        "_get_error_sink",
        "_launch_async_health_check",
        "_update_state_dynamic_fields",
        "_maybe_sync_telemetry",
        "_log_prompt_submit",
        "_integrity_verify",
        "_integrity_sign",
        "_execute_delegate_via_facade",
        "_get_host_delegate",
    }

    missing = required_targets - set(_REDIRECT_TARGETS.keys())
    assert not missing, (
        f"_REDIRECT_TARGETS is missing {len(missing)} high-frequency monkeypatch targets: {sorted(missing)}. "
        "Add them to _gateway_patch_redirect.py with the correct target modules."
    )


def test_redirect_propagation_for_newly_added_entries():
    """VAL-REDIRECT-002: Verify setattr propagation for newly added redirect entries.

    After M3-post-scrutiny, the following entries were added to _REDIRECT_TARGETS:
    - REPO_ROOT → (_gateway_config, _gateway_dispatch)
    - _FORCE_HOOK → (_gateway_config, _gateway_dispatch)
    - EVENT_LOG → added _gateway_artifacts target
    - datetime → added _gateway_artifacts target

    This test verifies that setattr on the facade correctly propagates to all
    target modules.
    """
    from memory_core.tools import _gateway_artifacts, _gateway_config, _gateway_dispatch
    from memory_core.tools import memory_hook_gateway as gw

    # Test REPO_ROOT propagation
    test_repo_root = "/test/repo/root"
    original_repo_root = gw.REPO_ROOT
    try:
        gw.REPO_ROOT = test_repo_root
        assert test_repo_root == _gateway_config.REPO_ROOT, "REPO_ROOT did not propagate to _gateway_config"
        assert test_repo_root == _gateway_dispatch.REPO_ROOT, "REPO_ROOT did not propagate to _gateway_dispatch"
    finally:
        gw.REPO_ROOT = original_repo_root

    # Test _FORCE_HOOK propagation
    test_force_hook = True
    original_force_hook = gw._FORCE_HOOK
    try:
        gw._FORCE_HOOK = test_force_hook
        assert test_force_hook == _gateway_config._FORCE_HOOK, "_FORCE_HOOK did not propagate to _gateway_config"
        assert test_force_hook == _gateway_dispatch._FORCE_HOOK, "_FORCE_HOOK did not propagate to _gateway_dispatch"
    finally:
        gw._FORCE_HOOK = original_force_hook

    # Test EVENT_LOG propagation to _gateway_artifacts
    from pathlib import Path

    test_event_log = Path("/test/event.log")
    original_event_log = gw.EVENT_LOG
    try:
        gw.EVENT_LOG = test_event_log
        assert test_event_log == _gateway_artifacts.EVENT_LOG, "EVENT_LOG did not propagate to _gateway_artifacts"
    finally:
        gw.EVENT_LOG = original_event_log

    # Test datetime propagation to _gateway_artifacts
    class MockDatetime:
        pass

    original_datetime = gw.datetime
    try:
        gw.datetime = MockDatetime
        assert _gateway_artifacts.datetime is MockDatetime, "datetime did not propagate to _gateway_artifacts"
    finally:
        gw.datetime = original_datetime
