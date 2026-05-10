import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.format_manager import FormatManager
from async_parser.workers import sync_parse
from utils.shared.logger import get_logger

_log = get_logger(__name__)

Names = Optional[Union[str, Iterable[str]]]


class AsyncParser:
    """Asyncio-friendly ArduPilot .bin log parser.

    Runs the synchronous file scan in a thread pool via asyncio.to_thread,
    so it never blocks the event loop. Ideal for use inside FastAPI, aiohttp,
    or any other async application.

    parser = AsyncParser('flight.bin')
    gps = await parser.parse('GPS')            # one type
    all_ = await parser.parse()                # all messages
    multi = await parser.parse(['GPS', 'ATT']) # multiple types
    """

    def __init__(self, file_path: str) -> None:
        self._fmt = FormatManager(file_path)

    async def parse(self, names: Names = None) -> List[Dict[str, Any]]:
        _log.debug('parse(names=%r)', names)
        try:
            target_ids = _names_to_type_ids(self._fmt, names)
            if target_ids is not None and not target_ids:
                _log.warning('parse: no matching type for names=%r', names)
                return []
            result = await asyncio.to_thread(sync_parse, self._fmt.file_path, self._fmt, target_ids)
            _log.info('parse(%r) -> %d messages', names, len(result))
            return result
        except Exception as error:
            _log.error('parse failed: %s', error)
            raise


def _names_to_type_ids(fmt: FormatManager, names: Names) -> Optional[Set[int]]:
    if names is None:
        return None
    if isinstance(names, str):
        names = [names]
    type_ids = {fmt.get_id(name) for name in names}
    type_ids.discard(None)
    return type_ids
