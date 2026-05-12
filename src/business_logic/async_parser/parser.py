import asyncio
import mmap
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.format_manager import FormatManager, Names
from async_parser.workers import sync_parse
from utils.shared.logger import get_logger

_log = get_logger(__name__)


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
        file = open(self._fmt.file_path, 'rb')
        buffer = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            await asyncio.to_thread(self._fmt.load, buffer)

            target_ids = self._fmt.resolve_type_ids(names)
            if target_ids is not None and not target_ids:
                _log.warning('parse: no matching type for names=%r', names)
                return []

            result = await asyncio.to_thread(sync_parse, buffer, self._fmt, target_ids)
            _log.info('parse(%r) -> %d messages', names, len(result))
            return result
        except Exception as error:
            _log.error('parse failed: %s', error)
            raise
        finally:
            buffer.close()
            file.close()


