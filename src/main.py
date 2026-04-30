import pprint
import time

from format_manager import FormatManager
from full_log_parser import FullLogParser
from selective_parser import SelectiveParser

PATH = r'C:\Users\adika\OneDrive\Desktop\israel_handover\part-b\data\log_file_test_01.bin'


def main():
    # --- FormatManager ---
    t0 = time.perf_counter()
    fmt = FormatManager(PATH)
    fmt_time = time.perf_counter() - t0
    print(f'FormatManager: {len(fmt._formats)} definitions loaded in {fmt_time:.3f}s')
    print(f'Data stream starts at byte offset: {fmt.data_start_offset}\n')

    # --- FullLogParser ---
    t0 = time.perf_counter()
    all_msgs = FullLogParser(fmt).parse()
    full_time = time.perf_counter() - t0
    print(f'FullLogParser : {len(all_msgs):>10,} messages in {full_time:.3f}s')

    # --- SelectiveParser (GPS only) ---
    t0 = time.perf_counter()
    gps_msgs = SelectiveParser(fmt).parse('GPS')
    sel_time = time.perf_counter() - t0
    print(f'SelectiveParser (GPS): {len(gps_msgs):>6,} messages in {sel_time:.3f}s')

    if full_time > 0:
        speedup = full_time / sel_time if sel_time > 0 else float('inf')
        print(f'\nSelectiveParser was {speedup:.1f}x faster than FullLogParser for GPS.\n')

    if gps_msgs:
        print('First GPS message:')
        pprint.pprint(gps_msgs[0])


if __name__ == '__main__':
    main()
