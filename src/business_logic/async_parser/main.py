import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from async_parser import AsyncParser
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[3] / ".env")
PATH = os.environ["LOG_FILE_PATH"]


async def _benchmark(label: str, fn: Callable[[], Awaitable[List[Any]]]) -> None:
    start_time = time.perf_counter()
    result = await fn()
    elapsed = time.perf_counter() - start_time
    print(f"  {label:<38} {len(result):>10,} rows   {elapsed:.2f}s")


async def _run() -> None:
    await _benchmark("aio.parse()", lambda: AsyncParser(PATH).parse())
    await _benchmark('aio.parse("gps")', lambda: AsyncParser(PATH).parse("gps"))
    await _benchmark('aio.parse(["GPS","ATT"])', lambda: AsyncParser(PATH).parse(["GPS", "ATT"]))


def main() -> None:
    print("\n  -- AsyncParser (asyncio) --")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
