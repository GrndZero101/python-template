# Concurrency: always a switchable sequential path

Read before fanning work out over many items.

Any fan-out gets a `--concurrency N` option, where **`N=1` takes a genuinely sequential code
path** — not a `TaskGroup` with a semaphore of 1:

```python
async def map_limited(
    items: Sequence[T],
    call: Callable[[T], Awaitable[R]],
    *,
    concurrency: int,
) -> list[R]:
    """Apply `call` to every item, strictly sequentially when concurrency == 1."""
    if concurrency == 1:
        results: list[R] = []
        for item in items:
            results.append(await call(item))  # noqa: PERF401
        return results
    return await _map_concurrent(items, call, limit=concurrency)
```

The explicit loop is the point, so `PERF401` gets suppressed here rather than obeyed. Why `N=1` must
be a separate path:

- A semaphore of 1 still interleaves task switches, so logs from different items still braid
  together and the order shifts between runs.
- `TaskGroup` wraps failures in an **`ExceptionGroup`**, so `except SomeError` stops matching and you
  need `except*`. The sequential path raises the bare exception, with one frame stack that leads
  straight to the failing item.
- A traceback through `gather` tells you a task failed; a traceback through the loop tells you *which
  input* failed.

Make `1` easy to reach and say so in the `--concurrency` help text. One knob, not a separate
`--sequential` flag that can contradict it.

Use `asyncio` for I/O-bound API calls and `concurrent.futures.ThreadPoolExecutor` for blocking
libraries. Never call a blocking client from inside a coroutine — `asyncio.to_thread` if you must.
