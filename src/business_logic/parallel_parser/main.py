import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from parallel_parser import ParallelParser

load_dotenv(Path(__file__).parents[3] / '.env')
PATH = os.environ['LOG_FILE_PATH']


def _benchmark(label: str, fn):
    start_time = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start_time
    print(f'  {label:<38} {len(result):>10,} rows   {elapsed:.2f}s')


def main():
    print('\n  -- ParallelParser (processes) --')
    _benchmark('par.parse()',                lambda: ParallelParser(PATH).parse())
    _benchmark('par.parse("gps")',           lambda: ParallelParser(PATH).parse('gps'))
    _benchmark('par.parse(["GPS","ATT"])',   lambda: ParallelParser(PATH).parse(['GPS', 'ATT']))


if __name__ == '__main__':
    main()
