"""Worker function for AsyncParser.

Runs synchronously inside asyncio.to_thread — receives the shared mmap buffer
directly, no file open needed.
"""

import mmap
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.format_manager import FormatManager
from utils.shared.buffer_parser import parse_buffer
from utils.shared.logger import get_logger

_log = get_logger(__name__)


def sync_parse(
    buffer: mmap.mmap,
    fmt: FormatManager,
    target_ids: Optional[Set[int]],
) -> List[Dict[str, Any]]:
    _log.debug('sync_parse start (target_ids=%r)', target_ids)
    try:
        messages = parse_buffer(buffer, fmt, target_ids)
        _log.debug('sync_parse -> %d messages', len(messages))
        return messages
    except Exception as error:
        _log.error('sync_parse failed: %s', error)
        raise
