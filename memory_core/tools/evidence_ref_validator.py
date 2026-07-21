"""Evidence ref disk existence validation.

Reusable function for checking that KB files' evidence refs point to
files that actually exist on disk. Used by:
- validate_project_memory.py (post-validation)
- init_project_memory.py (post-write check)
- migrate_project_memory.py (post-migration check)

This module is the single source of truth for evidence ref validation.
"""

from pathlib import Path
from typing import NamedTuple


class EvidenceRefError(NamedTuple):
    kb_file: str  # relative path to the KB file
    missing_refs: list[str]  # refs that don't exist on disk


def _heading_level(heading: str) -> int:
    """Return the markdown heading level (number of leading # chars).

    e.g. "# Foo" -> 1, "### Bar" -> 3, "Not a heading" -> 0.
    """
    stripped = heading.lstrip()
    level = 0
    for ch in stripped:
        if ch == "#":
            level += 1
        else:
            break
    return level


def extract_section_bullets(text: str, heading: str) -> list[str]:
    """Extract bullet items under a markdown heading (### Evidence Refs etc.).

    Args:
        text: Full markdown file content.
        heading: Exact heading to match (e.g. "### Evidence Refs").

    Returns:
        List of bullet values (without leading dash or backticks).
    """
    lines = text.split("\n")
    bullets: list[str] = []
    in_section = False
    target_level = _heading_level(heading)

    for line in lines:
        stripped = line.strip()
        if in_section:
            # Terminate on a heading at the same or higher level (fewer #)
            if stripped.startswith("#") and not stripped.startswith("# " * 10):
                current_level = _heading_level(stripped)
                if 0 < current_level <= target_level:
                    break
            if stripped.startswith("- "):
                value = stripped[2:].strip().strip("`")
                bullets.append(value)
        else:
            # Find the target heading
            stripped_for_match = line.rstrip()
            if stripped_for_match == heading:
                in_section = True
            elif stripped_for_match.lstrip() == heading:
                # Handle leading whitespace variants
                stripped_line = stripped_for_match.lstrip()
                if stripped_line.startswith("#") and _heading_level(stripped_line) == target_level:
                    in_section = True
    return bullets


def validate_evidence_refs_on_disk(
    project_root: Path,
    *,
    kb_dirs: list[Path] | None = None,
    skip_patterns: tuple[str, ...] = ("http://", "https://", "*", "?"),
) -> list[EvidenceRefError]:
    """Check all KB evidence refs point to files that exist on disk.

    Args:
        project_root: The project root directory.
        kb_dirs: Directories to scan for KB .md files.
                 Defaults to [project_root/memory/kb, project_root/memory/system/kb].
        skip_patterns: Prefixes/patterns that indicate non-file refs to skip.

    Returns:
        List of EvidenceRefError for any KB files with missing evidence refs.
        Empty list means all refs are valid.
    """
    if kb_dirs is None:
        kb_dirs = [
            project_root / "memory" / "kb",
            project_root / "memory" / "system" / "kb",
        ]

    errors: list[EvidenceRefError] = []

    for kb_dir in kb_dirs:
        if not kb_dir.is_dir():
            continue
        for md_file in sorted(kb_dir.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if "Evidence Refs" not in text:
                continue
            evidence_refs = extract_section_bullets(text, "### Evidence Refs")
            if not evidence_refs:
                continue

            missing: list[str] = []
            for ref in evidence_refs:
                # Skip URLs, globs, patterns
                if any(ref.startswith(p) or p in ref for p in skip_patterns):
                    continue

                # Resolve relative to project root
                ref_path = (project_root / ref).resolve()
                try:
                    ref_path.relative_to(project_root.resolve())
                except ValueError:
                    # Ref escapes project root -- skip (not our jurisdiction)
                    continue

                if not ref_path.exists():
                    missing.append(ref)

            if missing:
                try:
                    rel = str(md_file.relative_to(project_root))
                except ValueError:
                    rel = str(md_file)
                errors.append(EvidenceRefError(kb_file=rel, missing_refs=missing))

    return errors
