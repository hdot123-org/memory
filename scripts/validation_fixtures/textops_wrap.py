"""Round-4 validation fixture: word wrapping helper."""


def wrap_text(text, width=80):
    """Wrap text to the given width, breaking on spaces."""
    if width <= 0:
        raise ValueError("width must be positive")
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = word if not current else current + " " + word
    if current:
        lines.append(current)
    return lines


def truncate_middle(text, keep=10):
    """Truncate long strings, keeping head and tail."""
    if len(text) <= keep * 2:
        return text
    return text[:keep] + "..." + text[-keep:]
