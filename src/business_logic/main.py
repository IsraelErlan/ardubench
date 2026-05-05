import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sequential_parser.main import main as sequential_main
from parallel_parser.main import main as parallel_main
from threaded_parser.main import main as threaded_main
from asyncio_parser.main import main as asyncio_main
from mavlink_parser.main import main as mavlink_main


def main():
    sequential_main()
    parallel_main()
    threaded_main()
    asyncio_main()
    mavlink_main()


if __name__ == '__main__':
    main()
