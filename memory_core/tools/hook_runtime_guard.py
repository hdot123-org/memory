"""Bootstrap guard for memory-core hooks.

Installs SIGALRM + SIGINT handlers BEFORE heavy imports to ensure
clean exit under Factory's 10s timeout. Console-script entry point
only — pytest collection and in-process main() calls are unaffected.
"""
import os
import signal
import sys

_BOOT_SECONDS = 8  # < Factory's 10s timeout


def _exit0_handler(signum: int, frame: object) -> None:
    """Clean exit handler for SIGINT/SIGALRM.

    Uses os._exit(0) to skip atexit callbacks (telemetry PostHog
    Client.join) that would otherwise raise a Traceback on stderr
    during interpreter shutdown.
    """
    os._exit(0)


def install_guard(boot_seconds: int = _BOOT_SECONDS) -> None:
    """Install SIGALRM and SIGINT handlers that exit 0.

    Called by gateway_main() before heavy imports.
    Safe to call multiple times (idempotent).
    """
    signal.signal(signal.SIGALRM, _exit0_handler)
    signal.signal(signal.SIGINT, _exit0_handler)
    signal.alarm(boot_seconds)


def gateway_main() -> int:
    """Console-script entry: guard first, then gateway main()."""
    install_guard()
    from memory_core.tools.memory_hook_gateway import main
    return main()
