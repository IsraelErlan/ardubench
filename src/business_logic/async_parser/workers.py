"""Worker function for AsyncParser.

Runs synchronously inside asyncio.to_thread — receives the shared mmap buffer
directly, no file open needed.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared._constants import MSG_HEADER_B0, MSG_HEADER_B1
from utils.shared.logger import get_logger

_log = get_logger(__name__)


def sync_parse(
    buffer,
    fmt,
    target_ids: Optional[Set[int]],
) -> List[Dict[str, Any]]:
    _log.debug('sync_parse start (target_ids=%r)', target_ids)
    try:
        messages: List[Dict[str, Any]] = []
        offset = fmt.data_start_offset
        scan_end = len(buffer)
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

        _log.debug('sync_parse -> %d messages', len(messages))
        return messages
    except Exception as error:
        _log.error('sync_parse failed: %s', error)
        raise
