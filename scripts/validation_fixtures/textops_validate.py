"""Round-4 validation fixture: config-key validation helpers."""
import re

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def is_valid_key(key):
    """True when key looks like snake_case identifier."""
    return bool(_KEY_RE.match(key))


def find_invalid_keys(config):
    """Return sorted list of invalid keys in a flat config dict."""
    bad = [k for k in config if not is_valid_key(k)]
    return sorted(bad)


def merge_configs(base, override):
    """Merge override into base; nested dicts merged recursively."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    return merged
