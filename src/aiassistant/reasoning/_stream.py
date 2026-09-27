"""Bridge a blocking iterator to an async iterator without stalling the loop.

Provider SDKs (ollama, openai) expose *synchronous* streaming iterators. Pulling
from them on the event loop would block every other module, which is exactly the
defect this refactor removes. Each ``next()`` is therefore run in a worker
thread, and items are handed back through a bounded queue so a slow consumer
applies backpressure instead of buffering an unbounded turn.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from typing import TypeVar

T = TypeVar("T")

_QUEUE_MAXSIZE = 128
_SENTINEL = object()
_EXHAUSTED = object()


def _next_or_sentinel(iterator: Iterator) -> object:
    try:
        return next(iterator)
    except StopIteration:
        return _EXHAUSTED


async def iter_blocking(factory: Callable[[], Iterator[T]]) -> AsyncIterator[T]:
    """Yield items from a blocking iterator factory, off the event loop.

    ``factory`` is called in a worker thread, so any connection setup it does is
    also off the loop. If the consumer stops early (a cancelled turn), the pump
    task is cancelled; the underlying SDK call returns at its own pace.

    Raises whatever the iterator raises, at the point the consumer awaits it.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)

    async def pump() -> None:
        try:
            iterator = await loop.run_in_executor(None, factory)
            while True:
                item = await loop.run_in_executor(None, _next_or_sentinel, iterator)
                if item is _EXHAUSTED:
                    break
                await queue.put(item)
        except Exception as exc:  # surfaced to the consumer below
            await queue.put(exc)
        finally:
            await queue.put(_SENTINEL)

    pump_task = asyncio.ensure_future(pump())
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        pump_task.cancel()
