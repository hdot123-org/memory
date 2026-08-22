"""Shared telemetry-sync artifact test helpers (INFRA-304 dedup).

INFRA-304: Function '_setup_sync_artifacts' had 100% AST similarity across
test files (test_gateway_telemetry_health_coverage, test_synced_lines_tracking;
15 lines / 149 tokens each). Both variants created an artifact root containing
metrics.jsonl plus the .offset / .last_sync_success / .last_sync_attempt
sidecar files used by _maybe_sync_telemetry tests.

Consolidated into a single helper; each test module imports it under its
historical local name via aliased import, so existing call sites stay unchanged.
Public test names and assertions are preserved.
"""

from __future__ import annotations

from pathlib import Path


def setup_sync_artifacts(
    tmp_path: Path,
    *,
    metrics_lines: list[str] | None = None,
    offset: int = 0,
    last_sync_success: float = 0.0,
    last_sync_attempt: float = 0.0,
) -> Path:
    """Create artifact root with metrics.jsonl and sidecar files for sync tests.

    INFRA-304: extracted from 2 identical _setup_sync_artifacts bodies
    (100% AST similarity). Returns the created artifact root so tests can
    assert on sidecar state after invoking _maybe_sync_telemetry.
    """
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    metrics_file = artifact_root / "metrics.jsonl"
    if metrics_lines is not None:
        metrics_file.write_text("".join(metrics_lines), encoding="utf-8")
    else:
        metrics_file.write_text("", encoding="utf-8")

    offset_file = artifact_root / ".offset"
    offset_file.write_text(str(offset), encoding="utf-8")

    last_sync_success_file = artifact_root / ".last_sync_success"
    last_sync_success_file.write_text(str(last_sync_success), encoding="utf-8")

    last_sync_attempt_file = artifact_root / ".last_sync_attempt"
    last_sync_attempt_file.write_text(str(last_sync_attempt), encoding="utf-8")

    return artifact_root
