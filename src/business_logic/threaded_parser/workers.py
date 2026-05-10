"""
Worker function for ThreadedParser.

Each worker receives an offset range and decodes all messages within it.
Threads share memory, so no pickling constraints — but the GIL still applies.
"""

import mmap
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared._constants import MSG_HEADER_B0, MSG_HEADER_B1
from utils.shared.logger import get_logger

_log = get_logger(__name__)


def parse_chunk(
    file_path: str,
    fmt,
    start_offset: int,
    end_offset: Optional[int],
    target_ids: Optional[Set[int]],
) -> List[Dict[str, Any]]:
    _log.debug('chunk [%d:%s] start', start_offset, end_offset)
    try:
        messages: List[Dict[str, Any]] = []
        with open(file_path, 'rb') as file:
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                offset = start_offset
                scan_end = end_offset if end_offset is not None else len(buffer)
                registry = fmt._registry

                while offset + 3 <= scan_end:
                    if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
                        raise ValueError(f'invalid header at offset {offset}')
                    type_id = buffer[offset + 2]
                    offset += 3
                    type_entry = registry.get(type_id)
                    if type_entry is None:
                        raise ValueError(f'unregistered type_id {type_id} at offset {offset - 3}')
                    payload_len = type_entry['total_length'] - 3
                    if target_ids is not None and type_id not in target_ids:
                        offset += payload_len
                        continue
                    if offset + payload_len > scan_end:
                        raise ValueError(f'truncated payload for type_id {type_id} at offset {offset}')
                    message = fmt.decode_from(buffer, offset, type_id)
                    if message is not None:
                        messages.append(message)
                    offset += payload_len

        _log.debug('chunk [%d:%s] -> %d messages', start_offset, end_offset, len(messages))
        return messages
    except Exception as error:
        _log.error('chunk [%d:%s] failed: %s', start_offset, end_offset, error)
        raise
