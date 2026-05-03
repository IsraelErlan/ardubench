"""Compare pymavlink vs custom parser: performance benchmarks and data validation."""

import math
import os
import pprint
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))  # src/

from dotenv import load_dotenv
from pymavlink import mavutil

from business_logic.format_manager import FormatManager
from business_logic.log_parser import LogParser

load_dotenv(Path(__file__).parent.parent.parent / '.env')
PATH = os.environ['LOG_FILE_PATH']

_TYPE_KEYS = {'mavpackettype', '_msg_type'}


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_mavlink_gps() -> List[Dict]:
    connection = mavutil.mavlink_connection(PATH)
    messages = []
    while True:
        msg = connection.recv_match(type='GPS', blocking=False)
        if msg is None:
            break
        messages.append(msg.to_dict())
    return messages


def collect_custom_gps(parser: LogParser) -> List[Dict]:
    return parser.parse('GPS')


# ---------------------------------------------------------------------------
# Data validation
# ---------------------------------------------------------------------------

def validate(mav_messages: List[Dict], custom_messages: List[Dict]) -> bool:
    """Compare every field of every GPS message between the two parsers."""
    print('\n--- Data Validation ---')

    if len(mav_messages) != len(custom_messages):
        print(f'  FAIL  message count differs: '
              f'pymavlink={len(mav_messages):,}  custom={len(custom_messages):,}')
        return False

    total_fields = 0
    mismatches: List[Tuple] = []

    for i, (mav_msg, custom_msg) in enumerate(zip(mav_messages, custom_messages)):
        mav_fields    = {k: v for k, v in mav_msg.items()    if k not in _TYPE_KEYS}
        custom_fields = {k: v for k, v in custom_msg.items() if k not in _TYPE_KEYS}

        for field, mav_val in mav_fields.items():
            if field not in custom_fields:
                mismatches.append((i, field, mav_val, '<missing>'))
                continue

            custom_val = custom_fields[field]
            total_fields += 1

            values_match = (
                math.isclose(mav_val, custom_val, rel_tol=1e-6, abs_tol=1e-9)
                if isinstance(mav_val, float) and isinstance(custom_val, float)
                else mav_val == custom_val
            )

            if not values_match:
                mismatches.append((i, field, mav_val, custom_val))

    if mismatches:
        print(f'  FAIL  {len(mismatches)} mismatches (out of {total_fields:,} fields):')
        for index, field, mav_val, custom_val in mismatches[:10]:
            print(f'    msg[{index}] {field!r}: pymavlink={mav_val!r}  custom={custom_val!r}')
        if len(mismatches) > 10:
            print(f'    ... and {len(mismatches) - 10} more')
        return False

    print(f'  OK    all {total_fields:,} fields across {len(mav_messages):,} messages are identical')
    return True


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def bench_full_parse(parser: LogParser):
    t0 = time.perf_counter()
    connection = mavutil.mavlink_connection(PATH)
    mav_count = sum(1 for _ in iter(connection.recv_msg, None))
    mav_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    custom_count = len(parser.parse())
    custom_time = time.perf_counter() - t0

    return mav_count, mav_time, custom_count, custom_time


def bench_gps_only(parser: LogParser):
    t0 = time.perf_counter()
    mav_messages = collect_mavlink_gps()
    mav_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    custom_messages = collect_custom_gps(parser)
    custom_time = time.perf_counter() - t0

    return mav_messages, mav_time, custom_messages, custom_time


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = LogParser(FormatManager(PATH))

    print('Running benchmarks — this may take a minute...\n')

    mav_full_count, mav_full_time, custom_full_count, custom_full_time = (
        bench_full_parse(parser)
    )
    mav_gps, mav_gps_time, custom_gps, custom_gps_time = bench_gps_only(parser)

    W = 62
    print('=' * W)
    print(f'{"Task":<28} {"pymavlink":>10} {"custom":>10} {"speedup":>10}')
    print('-' * W)
    print(f'{"Full parse  - messages":<28} {mav_full_count:>10,} {custom_full_count:>10,}')
    print(f'{"Full parse  - time":<28} {mav_full_time:>9.2f}s {custom_full_time:>9.2f}s '
          f'{mav_full_time / custom_full_time:>8.1f}x')
    print('-' * W)
    print(f'{"GPS only    - messages":<28} {len(mav_gps):>10,} {len(custom_gps):>10,}')
    print(f'{"GPS only    - time":<28} {mav_gps_time:>9.2f}s {custom_gps_time:>9.2f}s '
          f'{mav_gps_time / custom_gps_time:>8.1f}x')
    print('=' * W)

    validate(mav_gps, custom_gps)

    print('\nFirst GPS message - pymavlink:')
    pprint.pprint(mav_gps[0] if mav_gps else None)
    print('\nFirst GPS message - custom:')
    pprint.pprint(custom_gps[0] if custom_gps else None)


if __name__ == '__main__':
    main()
