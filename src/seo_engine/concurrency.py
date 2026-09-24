"""Small parallel helper shared by tools (docs/ARCHITECTURE.md §7: ~8 calls at a time)."""

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor


def pmap[T, R](fn: Callable[[T], R], items: Iterable[T], workers: int) -> list[R]:
    """Parallel map with at most `workers` calls in flight, order preserved."""
    items = list(items)
    if len(items) <= 1 or workers <= 1:
        return [fn(i) for i in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))
