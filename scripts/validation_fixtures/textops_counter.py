"""Round-4 validation fixture: word frequency counter."""
from collections import Counter

_STOPWORDS = {"the", "a", "an", "and", "or", "but", "is", "are"}


def word_frequencies(text, drop_stopwords=True):
    """Count word occurrences, optionally dropping stopwords."""
    words = [w.strip(".,!?;:()[]\"'").lower() for w in text.split()]
    words = [w for w in words if w]
    if drop_stopwords:
        words = [w for w in words if w not in _STOPWORDS]
    return Counter(words)


def top_words(text, n=5):
    """The n most frequent words, ties broken alphabetically."""
    freqs = word_frequencies(text)
    ranked = sorted(freqs.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:n]
