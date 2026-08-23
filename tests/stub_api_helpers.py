"""Shared stub Sessions API server helpers (INFRA-529 dedup).

INFRA-529: module-scoped ``stub_api_server`` fixtures in
test_trigger_ci_droid_fallback.py and test_write_pending_ci_hardening.py
had 97% AST similarity (HTTPServer bind + daemon thread + shutdown
boilerplate; only the yielded URL suffix differed). Both variants are
folded into ``run_stub_api_server``; each test module keeps a thin
fixture bound to its own handler class and URL suffix.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer


def run_stub_api_server(handler: type[BaseHTTPRequestHandler], *, url_prefix: str = "") -> Iterator[str]:
    """Start a stub Sessions API HTTP server on an ephemeral port.

    INFRA-529: extracted from 2 near-identical module-scoped
    ``stub_api_server`` fixture bodies (97% AST similarity,
    7 lines / 67 tokens vs 6 lines / 66 tokens). Binds ``127.0.0.1:0``,
    serves on a daemon thread, yields the base URL, and shuts the
    server down afterwards.

    Args:
        handler: Request handler class (e.g. ``StubSessionsAPIHandler``).
        url_prefix: Suffix appended to the yielded base URL (e.g. ``/api/v0``).

    Yields:
        The stub server base URL (``http://127.0.0.1:{port}{url_prefix}``).
    """
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}{url_prefix}"
    server.shutdown()
