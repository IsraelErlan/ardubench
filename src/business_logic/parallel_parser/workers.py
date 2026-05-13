"""
Worker function for ParallelParser.

Must be defined at module level so ProcessPoolExecutor can pickle it.
Each worker receives an offset range and decodes all messages within it.
"""

import mmap
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.buffer_parser import parse_buffer
from utils.shared.format_manager import FormatManager
from utils.shared.logger import get_logger
from utils.shared.timestamp_clock import TimestampClock

_log = get_logger(__name__)


def parse_chunk(
    file_path: str,
    fmt: FormatManager,
    start_offset: int,
    end_offset: Optional[int],
    target_ids: Optional[Set[int]],
    clock: Optional[TimestampClock] = None,
) -> List[Dict[str, Any]]:
    _log.debug("chunk [%d:%s] start", start_offset, end_offset)
    try:
        chunk_clock = clock.copy() if clock is not None else None
        with open(file_path, "rb") as file:
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                messages = parse_buffer(buffer, fmt, target_ids, start_offset, end_offset, chunk_clock)
        _log.debug("chunk [%d:%s] -> %d messages", start_offset, end_offset, len(messages))
        return messages
    except Exception as error:
        _log.error("chunk [%d:%s] failed: %s", start_offset, end_offset, error)
        raise
