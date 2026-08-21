"""Round-4 validation fixture: slug generation with Unicode folding."""
import re
import unicodedata


def slugify(value):
    """Convert arbitrary text into a URL-safe slug."""
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value


def unique_slug(base, existing):
    """Return base slug, or base-2/base-3... avoiding collisions."""
    if base not in existing:
        return base
    counter = 2
    candidate = f"{base}-{counter}"
    while candidate in existing:
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate
