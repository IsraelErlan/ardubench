"""Worker function for ThreadedParser.

Each worker receives the shared mmap buffer and an offset range.
Threads share memory — no per-thread file open needed.
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

_log = get_logger(__name__)


def parse_chunk(
    buffer: mmap.mmap,
    fmt: FormatManager,
    start_offset: int,
    end_offset: Optional[int],
    target_ids: Optional[Set[int]],
) -> List[Dict[str, Any]]:
    _log.debug("chunk [%d:%s] start", start_offset, end_offset)
    try:
        messages = parse_buffer(buffer, fmt, target_ids, start_offset, end_offset)
        _log.debug("chunk [%d:%s] -> %d messages", start_offset, end_offset, len(messages))
        return messages
    except Exception as error:
        _log.error("chunk [%d:%s] failed: %s", start_offset, end_offset, error)
        raise
