"""Checksum helpers for round-3 shard pipeline validation fixture."""


def fnv1a(data):
    """32-bit FNV-1a hash of a string."""
    h = 0x811C9DC5
    for byte in data.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def bucket(data, slots=16):
    """Map *data* into one of *slots* buckets via FNV-1a."""
    if slots <= 0:
        raise ValueError("slots must be positive")
    return fnv1a(data) % slots
