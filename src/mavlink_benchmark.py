"""Compare pymavlink vs custom parser: full log parse and GPS-only extraction."""

import os
import pprint
import time
from pathlib import Path

from dotenv import load_dotenv
from pymavlink import mavutil

from format_manager import FormatManager
from log_parser import LogParser

load_dotenv(Path(__file__).parent.parent / '.env')
PATH = os.environ['LOG_FILE_PATH']


# ---------------------------------------------------------------------------
# pymavlink runners
# ---------------------------------------------------------------------------

def mavlink_full_parse():
    connection = mavutil.mavlink_connection(PATH)
    total_count = 0
    first_gps_message = None
    while True:
        msg = connection.recv_msg()
        if msg is None:
            break
        total_count += 1
        if first_gps_message is None and msg.get_type() == 'GPS':
            first_gps_message = msg.to_dict()
    return total_count, first_gps_message


def mavlink_gps_only():
    connection = mavutil.mavlink_connection(PATH)
    gps_count = 0
    first_gps_message = None
    while True:
        msg = connection.recv_match(type='GPS', blocking=False)
        if msg is None:
            break
        gps_count += 1
        if first_gps_message is None:
            first_gps_message = msg.to_dict()
    return gps_count, first_gps_message


# ---------------------------------------------------------------------------
# Custom parser runners
# ---------------------------------------------------------------------------

def custom_full_parse(parser: LogParser):
    all_messages = parser.parse()
    first_gps_message = next(
        (m for m in all_messages if m['_msg_type'] == 'GPS'), None
    )
    return len(all_messages), first_gps_message


def custom_gps_only(parser: LogParser):
    gps_messages = parser.parse('GPS')
    return len(gps_messages), gps_messages[0] if gps_messages else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = LogParser(FormatManager(PATH))

    print('Running benchmarks — this may take a minute...\n')

    t0 = time.perf_counter()
    mav_full_count, mav_first_gps = mavlink_full_parse()
    mav_full_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    mav_gps_count, _ = mavlink_gps_only()
    mav_gps_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    custom_full_count, custom_first_gps = custom_full_parse(parser)
    custom_full_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    custom_gps_count, _ = custom_gps_only(parser)
    custom_gps_time = time.perf_counter() - t0

    # --- comparison table ---
    W = 62
    print('=' * W)
    print(f'{"Task":<28} {"pymavlink":>10} {"custom":>10} {"speedup":>10}')
    print('-' * W)
    print(f'{"Full parse  — messages":<28} {mav_full_count:>10,} {custom_full_count:>10,}')
    print(f'{"Full parse  — time":<28} {mav_full_time:>9.2f}s {custom_full_time:>9.2f}s '
          f'{mav_full_time / custom_full_time:>8.1f}x')
    print('-' * W)
    print(f'{"GPS only    — messages":<28} {mav_gps_count:>10,} {custom_gps_count:>10,}')
    print(f'{"GPS only    — time":<28} {mav_gps_time:>9.2f}s {custom_gps_time:>9.2f}s '
          f'{mav_gps_time / custom_gps_time:>8.1f}x')
    print('=' * W)

    print('\nFirst GPS message — pymavlink:')
    pprint.pprint(mav_first_gps)

    print('\nFirst GPS message — custom:')
    pprint.pprint(custom_first_gps)


if __name__ == '__main__':
    main()
