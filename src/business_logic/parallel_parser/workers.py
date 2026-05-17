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

_worker_fmt: Optional[FormatManager] = None


def _init_worker(fmt: FormatManager) -> None:
    """Store fmt once per worker process; avoids pickling it with every task."""
    global _worker_fmt
    _worker_fmt = fmt


def parse_chunk(
    file_path: str,
    start_offset: int,
    end_offset: Optional[int],
    target_ids: Optional[Set[int]],
    clock: Optional[TimestampClock] = None,
) -> List[Dict[str, Any]]:
    """Open the file, parse the assigned byte range, and return decoded messages."""
    fmt = _worker_fmt
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
