"""Text operations for round-3 shard pipeline validation fixture."""


def word_counts(text):
    """Return a dict of word -> count, case-insensitive."""
    counts = {}
    for word in text.lower().split():
        word = word.strip(".,;:!?")
        if word:
            counts[word] = counts.get(word, 0) + 1
    return counts


def top_words(text, n=5):
    """Top-n words by frequency, ties broken alphabetically."""
    counts = word_counts(text)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ordered[:n]


def truncate_middle(text, keep=20):
    """Keep head and tail of *text*, ellipsis in the middle."""
    if len(text) <= keep * 2:
        return text
    return text[:keep] + "..." + text[-keep:]
