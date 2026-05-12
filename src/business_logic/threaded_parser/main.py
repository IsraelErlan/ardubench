import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from threaded_parser import ThreadedParser

load_dotenv(Path(__file__).parents[3] / ".env")
PATH = os.environ["LOG_FILE_PATH"]


def _benchmark(label: str, fn: Callable[[], List[Any]]) -> None:
    start_time = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start_time
    print(f"  {label:<38} {len(result):>10,} rows   {elapsed:.2f}s")


def main() -> None:
    print("\n  -- ThreadedParser (threads) --")
    _benchmark("thr.parse()", lambda: ThreadedParser(PATH).parse())
    _benchmark('thr.parse("gps")', lambda: ThreadedParser(PATH).parse("gps"))
    _benchmark('thr.parse(["GPS","ATT"])', lambda: ThreadedParser(PATH).parse(["GPS", "ATT"]))


if __name__ == "__main__":
    main()
