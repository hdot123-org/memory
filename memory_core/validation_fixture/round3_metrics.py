"""Metric helpers for round-3 shard pipeline validation fixture."""
from math import sqrt


def mean(values):
    """Arithmetic mean; raises on empty input."""
    if not values:
        raise ValueError("mean() requires at least one value")
    return sum(values) / len(values)


def stddev(values):
    """Population standard deviation."""
    if not values:
        raise ValueError("stddev() requires at least one value")
    m = mean(values)
    return sqrt(sum((v - m) ** 2 for v in values) / len(values))


def percentile(values, pct):
    """Nearest-rank percentile (pct in [0, 100])."""
    if not values:
        raise ValueError("percentile() requires at least one value")
    if not 0 <= pct <= 100:
        raise ValueError("pct must be within [0, 100]")
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered)))
    return ordered[rank - 1]
