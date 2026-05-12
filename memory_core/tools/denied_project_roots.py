from __future__ import annotations

import os
from pathlib import Path


def denied_project_roots() -> list[Path]:
    """Return exact project roots that memory hooks must never manage."""
    roots: list[Path] = []
    try:
        roots.append(Path.home())
    except RuntimeError:
        pass

    configured = os.environ.get("MEMORY_HOOK_DENY_PROJECT_ROOTS", "")
    for raw in configured.split(os.pathsep):
        value = raw.strip()
        if value:
            roots.append(Path(value).expanduser())

    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def is_denied_project_root(path: Path) -> bool:
    """Return True only when path exactly matches a denied project root."""
    resolved = path.expanduser().resolve(strict=False)
    return any(resolved == denied for denied in denied_project_roots())
