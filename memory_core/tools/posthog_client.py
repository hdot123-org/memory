"""PostHog Analytics Client for memory-core telemetry.

This module provides a lightweight wrapper around the PostHog SDK for analytics tracking.
Features:
- Graceful degradation when posthog SDK is not installed
- Default disabled (no-op) when POSTHOG_API_KEY is empty
- Singleton pattern for global instance
- Data file-based key loading (not hardcoded in source)
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_default_key() -> str:
    """Load the default PostHog public key from package data file.

    The key is stored in memory_core/default_posthog_key.txt as plain text.
    This avoids hardcoding sensitive values in Python source files.

    Returns:
        The API key string, or empty string if file not found or unreadable.
    """
    try:
        key_file = Path(__file__).parent.parent / "default_posthog_key.txt"
        if key_file.exists():
            return key_file.read_text().strip()
    except Exception as e:
        logger.warning(f"Failed to load default PostHog key: {e}")
    return ""


# Try to import posthog SDK
try:
    import posthog
    _POSTHOG_AVAILABLE = True
except ImportError:
    posthog = None  # type: ignore[assignment]
    _POSTHOG_AVAILABLE = False
    logger.debug("posthog SDK not installed, analytics will be no-op")


class PostHogAnalytics:
    """Singleton PostHog analytics client.

    Provides safe, no-op behavior when:
    - posthog SDK is not installed
    - POSTHOG_API_KEY environment variable is empty
    - Initialization fails for any reason

    Usage:
        analytics = PostHogAnalytics()
        analytics.capture('event_name', {'property': 'value'}, distinct_id='user123')
        analytics.shutdown()  # Flush pending events
    """

    _instance: "PostHogAnalytics | None" = None
    _initialized: bool
    _enabled: bool
    _client: Any | None

    def __new__(cls) -> "PostHogAnalytics":
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the analytics client.

        Reads POSTHOG_API_KEY from environment, falling back to default key from data file.
        If key is empty or SDK unavailable, client becomes a no-op.
        """
        if self._initialized:
            return

        self._initialized = True
        self._enabled = False
        self._client = None

        # Check if SDK is available
        if not _POSTHOG_AVAILABLE:
            logger.warning("posthog SDK not installed, analytics disabled")
            return

        # Three-state key resolution:
        # 1. POSTHOG_API_KEY set (including '') -> user intent overrides default
        # 2. POSTHOG_API_KEY not set -> load default from data file
        # 3. Both empty -> disabled (no-op)
        if "POSTHOG_API_KEY" in os.environ:
            api_key = os.environ["POSTHOG_API_KEY"].strip()
        else:
            api_key = _load_default_key()

        if not api_key:
            logger.info("POSTHOG_API_KEY is empty, analytics disabled")
            return

        # Load host (optional, defaults to PostHog US cloud)
        host = os.environ.get("POSTHOG_HOST", "https://us.posthog.com").strip()

        try:
            self._client = posthog.Posthog(  # type: ignore[no-untyped-call]
                api_key=api_key,
                host=host,
                on_error=lambda e: logger.debug(f"PostHog error: {e}"),
            )
            self._enabled = True
            logger.debug(f"PostHog analytics initialized with host: {host}")
        except Exception as e:
            logger.warning(f"Failed to initialize PostHog client: {e}")

    def capture(
        self,
        event_name: str,
        properties: dict[str, Any] | None = None,
        distinct_id: str = "memory-core",
    ) -> None:
        """Capture an analytics event.

        Args:
            event_name: Name of the event (e.g., 'session_start', 'hook_triggered')
            properties: Optional dictionary of event properties
            distinct_id: User/project identifier (default: 'memory-core')

        No-op behavior:
            - If SDK not installed
            - If API key is empty
            - If initialization failed
            - If capture raises an exception (logged but not propagated)
        """
        if not self._enabled or self._client is None:
            return

        try:
            self._client.capture(
                distinct_id=distinct_id,
                event=event_name,
                properties=properties or {},
            )
        except Exception as e:
            # Fail silently - analytics should never break application flow
            logger.debug(f"Failed to capture event '{event_name}': {e}")

    def shutdown(self) -> None:
        """Shutdown the analytics client and flush pending events.

        Safe to call multiple times. No-op if client not initialized.
        """
        if self._client is not None:
            try:
                self._client.shutdown()
                logger.debug("PostHog client shutdown")
            except Exception as e:
                logger.debug(f"Error during PostHog shutdown: {e}")


# Module-level singleton instance
analytics = PostHogAnalytics()
