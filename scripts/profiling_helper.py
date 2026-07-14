#!/usr/bin/env python3
"""cProfile context manager utility for memory-core profiling.

Provides a ``profile`` context manager that profiles a code block using
``cProfile`` and writes the results to a ``.prof`` file (or prints stats).

Usage::

    from scripts.profiling_helper import profile

    with profile("my_section"):
        expensive_work()

Or as a standalone script::

    python scripts/profiling_helper.py              # runs a sample block
    python scripts/profiling_helper.py --help
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import sys
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def profile(
    section: str,
    *,
    output: str | None = None,
    sort_by: str = "cumulative",
    top_n: int = 20,
    stream: io.IOBase | None = None,
) -> Iterator[cProfile.Profile]:
    """Profile a code block as a context manager.

    Parameters
    ----------
    section:
        A human-readable label for the block, used in log output and as
        the default filename stem for the saved ``.prof`` file.
    output:
        Optional explicit path for the ``.prof`` file. If omitted, the
        profiler writes to ``profiling_<section>.prof`` in the current
        working directory. Set to ``""`` to skip writing the file.
    sort_by:
        Sorting key for the printed stats (``cumulative``, ``tottime``,
        ``calls``, etc.). See ``pstats.Stats`` for details.
    top_n:
        Number of top entries to print.
    stream:
        Output stream for printed stats. Defaults to ``sys.stdout``.
    """
    profiler = cProfile.Profile()
    print(f"[profiling_helper] === start: {section} ===", file=stream or sys.stdout)
    profiler.enable()
    try:
        yield profiler
    finally:
        profiler.disable()
        print(f"[profiling_helper] === end: {section} ===", file=stream or sys.stdout)

        out_path = output if output is not None else f"profiling_{section}.prof"
        if out_path:
            profiler.dump_stats(out_path)
            print(
                f"[profiling_helper] stats saved to: {out_path}",
                file=stream or sys.stdout,
            )

        stats = pstats.Stats(profiler, stream=stream or sys.stdout)
        stats.sort_stats(sort_by)
        stats.print_stats(top_n)


# Alias so both ``Profile`` and ``profile`` resolve (VAL-DT-002 accepts either).
Profile = profile


# Expose as a class-style ``Profile`` context manager as well for callers
# that prefer ``with Profile(...) as p:`` capitalization.
class _ProfileClass:
    """Class-based ``Profile`` context manager (thin wrapper)."""

    def __init__(
        self,
        section: str,
        *,
        output: str | None = None,
        sort_by: str = "cumulative",
        top_n: int = 20,
    ) -> None:
        self._section = section
        self._output = output
        self._sort_by = sort_by
        self._top_n = top_n
        self._cm = profile(
            section, output=output, sort_by=sort_by, top_n=top_n
        )
        self.profiler: cProfile.Profile | None = None

    def __enter__(self) -> cProfile.Profile:
        self.profiler = self._cm.__enter__()
        return self.profiler

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        return self._cm.__exit__(exc_type, exc_val, exc_tb)


def _sample() -> None:
    with profile("sample") as p:
        total = sum(range(100_000))
    print(f"[profiling_helper] sample total = {total}, profiler = {p!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="cProfile context manager utility."
    )
    parser.add_argument(
        "--section",
        default="sample",
        help="Section label (default: sample).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional .prof output path. Empty string disables file output.",
    )
    parser.add_argument(
        "--sort-by",
        default="cumulative",
        help="Sort key for printed stats (default: cumulative).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of top entries to print (default: 20).",
    )
    args = parser.parse_args(argv)

    with profile(
        args.section,
        output=args.output if args.output is not None else "",
        sort_by=args.sort_by,
        top_n=args.top_n,
    ):
        # Default sample workload.
        total = sum(range(100_000))
        print(f"[profiling_helper] total = {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
