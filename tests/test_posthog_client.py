"""Tests for PostHog client."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_posthog_client_exists():
    """Test that posthog_client.py exists and can be imported."""
    client_file = Path(__file__).parent.parent / "memory_core" / "tools" / "posthog_client.py"
    assert client_file.exists(), "posthog_client.py must exist"

    from memory_core.tools import posthog_client
    assert posthog_client is not None


def test_default_posthog_key_file_exists():
    """Test that default_posthog_key.txt exists and contains valid key."""
    key_file = Path(__file__).parent.parent / "memory_core" / "default_posthog_key.txt"
    assert key_file.exists(), "default_posthog_key.txt must exist"

    content = key_file.read_text().strip()
    assert content.startswith("phc_"), "Key must start with phc_"
    assert len(content) > 10, "Key must be at least 10 characters"


def test_load_default_key():
    """Test _load_default_key() reads from data file."""
    from memory_core.tools.posthog_client import _load_default_key

    key = _load_default_key()
    assert key.startswith("phc_"), "Default key must start with phc_"
    assert len(key) > 10, "Default key must be valid length"


def test_posthog_analytics_singleton():
    """Test PostHogAnalytics is a singleton."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    a1 = PostHogAnalytics()
    a2 = PostHogAnalytics()

    assert a1 is a2, "PostHogAnalytics must be singleton"

    # Cleanup
    PostHogAnalytics._instance = None


def test_posthog_analytics_disabled_when_sdk_missing():
    """Test analytics is disabled when posthog SDK not installed."""
    from memory_core.tools import posthog_client
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    # Mock SDK unavailable
    with patch.object(posthog_client, "_POSTHOG_AVAILABLE", False):
        analytics = PostHogAnalytics()
        assert not analytics._enabled, "Should be disabled when SDK missing"
        assert analytics._client is None

    # Cleanup
    PostHogAnalytics._instance = None


def test_posthog_analytics_disabled_when_key_empty():
    """Test analytics is disabled when POSTHOG_API_KEY is explicitly empty."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    # Set empty key
    old_val = os.environ.get("POSTHOG_API_KEY")
    os.environ["POSTHOG_API_KEY"] = ""

    try:
        analytics = PostHogAnalytics()
        assert not analytics._enabled, "Should be disabled when key is empty"
        assert analytics._client is None
    finally:
        # Restore
        if old_val is None:
            os.environ.pop("POSTHOG_API_KEY", None)
        else:
            os.environ["POSTHOG_API_KEY"] = old_val
        PostHogAnalytics._instance = None


def test_posthog_analytics_uses_default_key():
    """Test analytics uses default key when POSTHOG_API_KEY not set."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    # Ensure POSTHOG_API_KEY not set
    old_val = os.environ.pop("POSTHOG_API_KEY", None)

    try:
        # Mock posthog SDK
        mock_posthog = MagicMock()
        mock_client = MagicMock()
        mock_posthog.Posthog.return_value = mock_client

        with patch("memory_core.tools.posthog_client.posthog", mock_posthog):
            with patch("memory_core.tools.posthog_client._POSTHOG_AVAILABLE", True):
                analytics = PostHogAnalytics()

                # Should have loaded default key
                assert analytics._enabled, "Should be enabled with default key"
                mock_posthog.Posthog.assert_called_once()
                call_args = mock_posthog.Posthog.call_args
                assert "project_api_key" in call_args.kwargs
                assert call_args.kwargs["project_api_key"].startswith("phc_")
    finally:
        if old_val is not None:
            os.environ["POSTHOG_API_KEY"] = old_val
        PostHogAnalytics._instance = None


def test_capture_is_noop_when_disabled():
    """Test capture() is no-op when analytics disabled."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    analytics = PostHogAnalytics()
    # Don't enable it

    # Should not raise
    analytics.capture("test_event", {"key": "value"})
    analytics.capture("another_event", distinct_id="user123")


def test_capture_calls_posthog_when_enabled():
    """Test capture() calls posthog SDK when enabled."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    # Mock posthog SDK
    mock_client = MagicMock()

    analytics = PostHogAnalytics()
    analytics._enabled = True
    analytics._client = mock_client

    # Call capture
    analytics.capture("test_event", {"key": "value"}, distinct_id="user123")

    # Verify posthog.capture was called
    mock_client.capture.assert_called_once()
    call_args = mock_client.capture.call_args
    assert call_args.kwargs["distinct_id"] == "user123"
    assert call_args.kwargs["event"] == "test_event"
    assert call_args.kwargs["properties"] == {"key": "value"}

    # Cleanup
    PostHogAnalytics._instance = None


def test_capture_handles_exceptions():
    """Test capture() handles exceptions gracefully."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    # Mock client that raises
    mock_client = MagicMock()
    mock_client.capture.side_effect = Exception("Network error")

    analytics = PostHogAnalytics()
    analytics._enabled = True
    analytics._client = mock_client

    # Should not raise
    analytics.capture("test_event", {"key": "value"})

    # Cleanup
    PostHogAnalytics._instance = None


def test_shutdown_calls_posthog_shutdown():
    """Test shutdown() calls posthog client shutdown."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    # Mock client
    mock_client = MagicMock()

    analytics = PostHogAnalytics()
    analytics._client = mock_client

    # Call shutdown
    analytics.shutdown()

    # Verify shutdown was called
    mock_client.shutdown.assert_called_once()

    # Cleanup
    PostHogAnalytics._instance = None


def test_shutdown_handles_exceptions():
    """Test shutdown() handles exceptions gracefully."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    # Mock client that raises
    mock_client = MagicMock()
    mock_client.shutdown.side_effect = Exception("Shutdown error")

    analytics = PostHogAnalytics()
    analytics._client = mock_client

    # Should not raise
    analytics.shutdown()

    # Cleanup
    PostHogAnalytics._instance = None


def test_shutdown_noop_when_client_none():
    """Test shutdown() is no-op when client is None."""
    from memory_core.tools.posthog_client import PostHogAnalytics

    # Reset singleton
    PostHogAnalytics._instance = None

    analytics = PostHogAnalytics()
    analytics._client = None

    # Should not raise
    analytics.shutdown()

    # Cleanup
    PostHogAnalytics._instance = None


def test_manifest_includes_data_file():
    """Test MANIFEST.in includes default_posthog_key.txt."""
    manifest_file = Path(__file__).parent.parent / "MANIFEST.in"
    assert manifest_file.exists(), "MANIFEST.in must exist"

    content = manifest_file.read_text()
    assert "default_posthog_key.txt" in content, "MANIFEST.in must include data file"


def test_pyproject_includes_posthog_dependency():
    """Test pyproject.toml includes posthog in dependencies."""
    pyproject_file = Path(__file__).parent.parent / "pyproject.toml"
    assert pyproject_file.exists(), "pyproject.toml must exist"

    content = pyproject_file.read_text()
    assert "posthog" in content, "pyproject.toml must include posthog dependency"
    # Check it's in main dependencies, not optional
    lines = content.split("\n")
    in_dependencies = False
    found_posthog = False
    for line in lines:
        if line.strip() == "dependencies = [":
            in_dependencies = True
        elif in_dependencies and line.strip() == "]":
            in_dependencies = False
        elif in_dependencies and "posthog" in line:
            found_posthog = True
            break

    assert found_posthog, "posthog must be in main dependencies"


def test_no_hardcoded_phc_in_python_files():
    """Test that no .py files contain hardcoded phc_ keys."""
    import subprocess

    result = subprocess.run(
        ["grep", "-r", "phc_", "--include=*.py", "memory_core/"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    # grep returns 1 if no matches, which is what we want
    assert result.returncode == 1, (
        f"No .py files should contain hardcoded phc_ keys, found:\n{result.stdout}"
    )
