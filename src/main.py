import os
import pprint
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # src/

from dotenv import load_dotenv

from business_logic.format_manager import FormatManager
from business_logic.log_parser import LogParser

load_dotenv(Path(__file__).parent.parent / '.env')
PATH = os.environ['LOG_FILE_PATH']

MULTI_TARGETS = ['GPS', 'ATT', 'IMU', 'BARO', 'RCIN']


def main():
    fmt_manager = FormatManager(PATH)
    parser = LogParser(fmt_manager)

    print(f'Loaded {len(fmt_manager._type_registry)} definitions. '
          f'Data offset: {fmt_manager.data_start_offset}\n')

    # --- Single type (mmap, sequential) ---
    t0 = time.perf_counter()
    gps_messages = parser.parse('GPS')
    print(f'parse("GPS")           : {len(gps_messages):>8,} messages  '
          f'{time.perf_counter() - t0:.2f}s')

    # --- Multiple types, single pass (mmap, sequential) ---
    t0 = time.perf_counter()
    gps_att = parser.parse(['GPS', 'ATT'])
    print(f'parse(["GPS","ATT"])   : {len(gps_att):>8,} messages  '
          f'{time.perf_counter() - t0:.2f}s')

    # --- Multiple types in parallel (ProcessPoolExecutor) ---
    t0 = time.perf_counter()
    results = parser.parse_parallel(MULTI_TARGETS)
    parallel_time = time.perf_counter() - t0
    total = sum(len(v) for v in results.values())
    print(f'parse_parallel(5 types): {total:>8,} messages  {parallel_time:.2f}s')
    for name, msgs in results.items():
        print(f'  {name:<6} {len(msgs):>8,}')

    # --- Sequential equivalent for comparison ---
    t0 = time.perf_counter()
    seq_total = sum(len(parser.parse(n)) for n in MULTI_TARGETS)
    seq_time = time.perf_counter() - t0
    print(f'\nSequential (5 types)   : {seq_total:>8,} messages  {seq_time:.2f}s')
    print(f'Parallel speedup       : {seq_time / parallel_time:.1f}x\n')

    print('First GPS message:')
    pprint.pprint(gps_messages[0])


if __name__ == '__main__':
    main()
