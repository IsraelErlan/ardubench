import os
import pprint
import time
from pathlib import Path

from dotenv import load_dotenv

from format_manager import FormatManager
from log_parser import LogParser

load_dotenv(Path(__file__).parent.parent / '.env')
PATH = os.environ['LOG_FILE_PATH']


def main():
    # --- FormatManager ---
    t0 = time.perf_counter()
    fmt_manager = FormatManager(PATH)
    load_time = time.perf_counter() - t0
    print(f'FormatManager: {len(fmt_manager._type_registry)} definitions loaded in {load_time:.3f}s')
    print(f'Data stream starts at byte offset: {fmt_manager.data_start_offset}\n')

    parser = LogParser(fmt_manager)

    # --- Full parse ---
    t0 = time.perf_counter()
    all_messages = parser.parse()
    full_parse_time = time.perf_counter() - t0
    print(f'Full parse    : {len(all_messages):>10,} messages in {full_parse_time:.3f}s')

    # --- GPS only ---
    t0 = time.perf_counter()
    gps_messages = parser.parse('GPS')
    selective_time = time.perf_counter() - t0
    print(f'GPS only      : {len(gps_messages):>10,} messages in {selective_time:.3f}s')

    # --- GPS + ATT ---
    t0 = time.perf_counter()
    gps_att_messages = parser.parse(['GPS', 'ATT'])
    multi_time = time.perf_counter() - t0
    print(f'GPS + ATT     : {len(gps_att_messages):>10,} messages in {multi_time:.3f}s')

    speedup = full_parse_time / selective_time if selective_time > 0 else float('inf')
    print(f'\nGPS-only was {speedup:.1f}x faster than full parse.\n')

    if gps_messages:
        print('First GPS message:')
        pprint.pprint(gps_messages[0])


if __name__ == '__main__':
    main()
