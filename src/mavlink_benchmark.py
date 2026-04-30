"""Compare pymavlink vs custom parser: full log parse and GPS-only extraction."""

import pprint
import time

from pymavlink import mavutil

from format_manager import FormatManager
from full_log_parser import FullLogParser
from selective_parser import SelectiveParser

PATH = r'C:\Users\adika\OneDrive\Desktop\israel_handover\part-b\data\log_file_test_01.bin'


# ---------------------------------------------------------------------------
# pymavlink runners
# ---------------------------------------------------------------------------

def mavlink_full_parse():
    conn = mavutil.mavlink_connection(PATH)
    count = 0
    first_gps = None
    while True:
        msg = conn.recv_msg()
        if msg is None:
            break
        count += 1
        if first_gps is None and msg.get_type() == 'GPS':
            first_gps = msg.to_dict()
    return count, first_gps


def mavlink_gps_only():
    conn = mavutil.mavlink_connection(PATH)
    count = 0
    first_gps = None
    while True:
        msg = conn.recv_match(type='GPS', blocking=False)
        if msg is None:
            break
        count += 1
        if first_gps is None:
            first_gps = msg.to_dict()
    return count, first_gps


# ---------------------------------------------------------------------------
# Custom parser runners
# ---------------------------------------------------------------------------

def custom_full_parse(fmt: FormatManager):
    msgs = FullLogParser(fmt).parse()
    gps = next((m for m in msgs if m['_msg_type'] == 'GPS'), None)
    return len(msgs), gps


def custom_gps_only(fmt: FormatManager):
    msgs = SelectiveParser(fmt).parse('GPS')
    return len(msgs), msgs[0] if msgs else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    fmt = FormatManager(PATH)

    print('Running benchmarks — this may take a minute...\n')

    t0 = time.perf_counter()
    mav_full_n, mav_first_gps = mavlink_full_parse()
    mav_full_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    mav_gps_n, _ = mavlink_gps_only()
    mav_gps_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    custom_full_n, custom_first_gps = custom_full_parse(fmt)
    custom_full_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    custom_gps_n, _ = custom_gps_only(fmt)
    custom_gps_t = time.perf_counter() - t0

    # --- comparison table ---
    W = 62
    print('=' * W)
    print(f'{"Task":<28} {"pymavlink":>10} {"custom":>10} {"speedup":>10}')
    print('-' * W)
    print(f'{"Full parse  — messages":<28} {mav_full_n:>10,} {custom_full_n:>10,}')
    print(f'{"Full parse  — time":<28} {mav_full_t:>9.2f}s {custom_full_t:>9.2f}s '
          f'{mav_full_t / custom_full_t:>8.1f}x')
    print('-' * W)
    print(f'{"GPS only    — messages":<28} {mav_gps_n:>10,} {custom_gps_n:>10,}')
    print(f'{"GPS only    — time":<28} {mav_gps_t:>9.2f}s {custom_gps_t:>9.2f}s '
          f'{mav_gps_t / custom_gps_t:>8.1f}x')
    print('=' * W)

    print('\nFirst GPS message — pymavlink:')
    pprint.pprint(mav_first_gps)

    print('\nFirst GPS message — custom:')
    pprint.pprint(custom_first_gps)


if __name__ == '__main__':
    main()
