import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sequential_parser import SequentialParser

load_dotenv(Path(__file__).parents[3] / ".env")
PATH = os.environ["LOG_FILE_PATH"]


def _benchmark(label: str, fn: Callable[[], List[Any]]) -> None:
    start_time = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start_time
    print(f"  {label:<38} {len(result):>10,} rows   {elapsed:.2f}s")


def main() -> None:
    print("\n  -- SequentialParser --")
    _benchmark("seq.parse()", lambda: SequentialParser(PATH).parse())
    _benchmark('seq.parse("gps")', lambda: SequentialParser(PATH).parse("gps"))
    _benchmark('seq.parse(["GPS","ATT"])', lambda: SequentialParser(PATH).parse(["GPS", "ATT"]))


if __name__ == "__main__":
    main()
