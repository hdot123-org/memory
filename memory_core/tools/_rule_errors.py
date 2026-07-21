# -*- coding: utf-8 -*-
"""
Unified exception hierarchy for memory-core domain errors.

Replaces ValueError catch-all with specific domain exceptions that
consumer projects can precisely catch.

Part of REF-001 strangler fig scaffold phase.
"""



class MemoryCoreError(Exception):
    """Base class for all memory-core domain exceptions.

    Consumer projects can catch this base to capture all memory-core
    business exceptions.
    """


# --- Configuration domain exceptions ---


class UnsupportedScopeError(MemoryCoreError):
    """Unsupported scope (replaces ValueError)."""


class UnknownHostError(MemoryCoreError):
    """Unknown host (replaces ValueError)."""


class UnknownRouteKindError(MemoryCoreError):
    """Unsupported route kind (replaces ValueError)."""
