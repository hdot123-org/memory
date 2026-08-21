"""Round-4 validation fixture: line-diff index for short texts."""
import difflib


def changed_line_numbers(old_text, new_text):
    """Return (removed, added) line-number sets between two texts."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    removed, added = set(), set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            removed.update(range(i1 + 1, i2 + 1))
        if tag in ("insert", "replace"):
            added.update(range(j1 + 1, j2 + 1))
    return removed, added


def similarity(old_text, new_text):
    """Rough similarity ratio between two texts."""
    return difflib.SequenceMatcher(
        a=old_text.splitlines(), b=new_text.splitlines()
    ).ratio()
