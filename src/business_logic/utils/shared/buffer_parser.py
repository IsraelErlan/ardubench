"""Core buffer-scanning loop shared by all ArduPilot .bin log parsers."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_src_dir = str(Path(__file__).parent.parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared._constants import MSG_HEADER_B0, MSG_HEADER_B1, MSG_HEADER
from utils.shared.format_manager import FormatManager
from utils.shared.logger import get_logger

_log = get_logger(__name__)


def parse_buffer(
    buffer,
    fmt: FormatManager,
    target_ids: Optional[Set[int]],
    start_offset: int = 0,
    end_offset: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Parse messages from an open mmap buffer within a byte range."""
    messages: List[Dict[str, Any]] = []
    offset = start_offset
    scan_end = end_offset if end_offset is not None else len(buffer)

    while offset + 3 <= scan_end:
        if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
            _log.warning('invalid header at offset %d — stopping scan', offset)
            break
        type_id = buffer[offset + 2]
        offset += 3
        type_entry = fmt.get_entry(type_id)
        if type_entry is None:
            _log.warning('skipping unknown type_id=%d at offset=%d', type_id, offset - 3)
            next_pos = buffer.find(MSG_HEADER, offset)
            if next_pos == -1:
                break
            offset = next_pos
            continue
        payload_len = type_entry['total_length'] - 3
        if target_ids is not None and type_id not in target_ids:
            offset += payload_len
            continue
        if offset + payload_len > scan_end:
            _log.warning('truncated payload for type_id %d at offset %d', type_id, offset)
            break
        message = fmt.decode_from(buffer, offset, type_id)
        if message is not None:
            messages.append(message)
        offset += payload_len

    return messages
