"""Small helpers for round-3 shard pipeline validation.

Fixture-only code: exercises ~4-8 file coverage with small per-file diffs
so the shard planner produces a multi-shard plan on the rig PR.
"""


def clamp(value, low, high):
    """Clamp *value* into [low, high]."""
    if low > high:
        low, high = high, low
    return max(low, min(high, value))


def slugify(name):
    """Turn an arbitrary label into a filesystem-safe slug."""
    cleaned = "".join(c if c.isalnum() else "-" for c in name.lower())
    parts = [p for p in cleaned.split("-") if p]
    return "-".join(parts) or "unnamed"


def merge_ranges(ranges):
    """Merge overlapping inclusive ranges; input list of (start, end)."""
    ordered = sorted(ranges)
    merged = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
