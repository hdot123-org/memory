"""Unified redaction module — all output channels must pass through this.

Covers:
- 6 API token formats (sk-, sk-ant-, ghp_, AKIA, lin_api_, glpat-)
- JWT-like tokens (eyJ...)
- Auth headers (Bearer, Basic)
- Password/secret key=value parameters
- Private IP addresses (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
- User home paths (/Users/<name>/, /home/<name>/)

Pattern ordering matters: sk-ant- before sk- to avoid partial match residue.
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# Pattern registry (order matters: most specific first)
# ---------------------------------------------------------------------------

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # API tokens — most specific patterns first
    (re.compile(r"sk-ant-[A-Za-z0-9\-]{10,}"), "[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9]{10,}"), "[REDACTED]"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "[REDACTED]"),
    (re.compile(r"AKIA[A-Za-z0-9]{12,}"), "[REDACTED]"),
    (re.compile(r"lin_api_[A-Za-z0-9]{10,}"), "[REDACTED]"),
    (re.compile(r"glpat-[A-Za-z0-9\-]{10,}"), "[REDACTED]"),
    # JWT-like tokens (three base64url segments separated by dots)
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "[REDACTED]",
    ),
    # Auth headers (case-insensitive)
    (re.compile(r"(Authorization:\s*Bearer\s+)[^\s\"']+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(Authorization:\s*Basic\s+)[^\s\"']+", re.I), r"\1[REDACTED]"),
    # Bare Bearer tokens (without Authorization: prefix) — catches log messages
    # that contain "Bearer <token>" outside of a full header line.
    # Placed AFTER the Authorization: patterns so the more specific match wins first.
    (re.compile(r"(Bearer\s+)\S+", re.I), r"\1[REDACTED]"),
    # Password parameters
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.I), r"\1=[REDACTED]"),
    # Generic key=value secrets (including compound keys like secret_key, api_key, etc.)
    # Exclude [ and ] to avoid matching already-redacted values
    (
        re.compile(
            r"(api[_-]?key|api[_-]?token|secret[_-]?key|access[_-]?token|auth[_-]?token|token|secret|credential)\s*[=:]\s*['\"]?[^\s'\",}\]\[]+",
            re.I,
        ),
        r"\1=[REDACTED]",
    ),
    # Private IPs
    (re.compile(r"192\.168\.\d{1,3}\.\d{1,3}"), "[REDACTED_IP]"),
    (re.compile(r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"), "[REDACTED_IP]"),
    (re.compile(r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"), "[REDACTED_IP]"),
]

# User home paths (separate so they can be toggled)
_USER_PATH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/Users/[^\s/]+/"), "/[USER_PATH]/"),
    (re.compile(r"/home/[^\s/]+/"), "/[USER_PATH]/"),
]


def redact(
    text: str,
    *,
    redact_user_paths: bool = True,
    max_len: int = 2000,
) -> str:
    """Redact secrets and optionally user paths from text.

    Args:
        text: Input text to redact.
        redact_user_paths: When True (default), also redact user home paths.
        max_len: Truncate input to this many characters before applying patterns.

    Returns:
        Redacted string.  Empty/None inputs pass through unchanged.
    """
    if not text:
        return text

    # Truncate first so output stays bounded
    text = text[:max_len]

    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)

    if redact_user_paths:
        for pattern, replacement in _USER_PATH_PATTERNS:
            text = pattern.sub(replacement, text)

    return text


def redact_dict(d: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Recursively redact all string values in a dict.

    Non-string values (int, float, bool, None) pass through without
    type coercion.  Nested dicts and lists are traversed.

    Args:
        d: Dictionary to redact.
        **kwargs: Forwarded to :func:`redact` (e.g. ``redact_user_paths``).

    Returns:
        A new dict with all string values redacted.
    """
    if not d:
        return d

    result: dict[str, Any] = {}
    for key, value in d.items():
        if isinstance(value, str):
            result[key] = redact(value, **kwargs)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, **kwargs)
        elif isinstance(value, list):
            result[key] = [
                redact(item, **kwargs)
                if isinstance(item, str)
                else redact_dict(item, **kwargs)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result
