"""Simple FIFO queue for round-3 shard pipeline validation fixture."""
from collections import deque


class BoundedQueue:
    """A queue with an optional max size; push raises when full."""

    def __init__(self, maxsize=None):
        if maxsize is not None and maxsize <= 0:
            raise ValueError("maxsize must be positive or None")
        self._items = deque()
        self._maxsize = maxsize

    def push(self, item):
        if self._maxsize is not None and len(self._items) >= self._maxsize:
            raise OverflowError("queue is full")
        self._items.append(item)

    def pop(self):
        if not self._items:
            raise IndexError("pop from empty queue")
        return self._items.popleft()

    def __len__(self):
        return len(self._items)
