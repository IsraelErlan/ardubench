import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import parallel_parser.parser as _mod
from parallel_parser import ParallelParser

load_dotenv(Path(__file__).parents[3] / '.env')
PATH = os.environ['LOG_FILE_PATH']

CHUNK_SIZES_MB = [0.25, 0.5, 1, 2, 4, 8, 16]

def main():
    file_mb = os.path.getsize(PATH) / (1024 * 1024)
    print(f'\n  File: {Path(PATH).name}  ({file_mb:.1f} MB)\n')
    print(f'  {"Chunk size":<14} {"Chunks":>8} {"Time":>8}')
    print(f'  {"-"*14} {"-"*8} {"-"*8}')

    for mb in CHUNK_SIZES_MB:
        _mod._CHUNK_SIZE = int(mb * 1024 * 1024)
        parser = ParallelParser(PATH)
        start = time.perf_counter()
        result = parser.parse()
        elapsed = time.perf_counter() - start
        import mmap
        file_size = os.path.getsize(PATH)
        import os as _os
        n_workers = _os.cpu_count() or 4
        n_chunks = max(n_workers, file_size // _mod._CHUNK_SIZE)
        print(f'  {mb:<10.2f} MB   {n_chunks:>8}   {elapsed:>7.2f}s')

    # restore default
    _mod._CHUNK_SIZE = 1024 * 1024


if __name__ == '__main__':
    main()
