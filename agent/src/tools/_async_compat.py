"""Async-to-sync bridge for datasource tools.

Tool execute() runs in ThreadPoolExecutor worker threads where no event
loop exists, so asyncio.run() is safe.
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)
