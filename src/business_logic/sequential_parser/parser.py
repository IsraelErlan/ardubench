import mmap
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.buffer_parser import parse_buffer
from utils.shared.format_manager import FormatManager, Names
from utils.shared.logger import get_logger

_log = get_logger(__name__)


class SequentialParser:
    """Single-process parser for ArduPilot .bin log files.

    parser = SequentialParser('flight.bin')
    parser.parse()               # all messages
    parser.parse('GPS')          # one type
    parser.parse(['GPS', 'ATT']) # multiple types
    """

    def __init__(self, file_path: str) -> None:
        self._fmt = FormatManager(file_path)

    def parse(self, names: Names = None) -> List[Dict[str, Any]]:
        _log.debug("parse(names=%r)", names)
        try:
            with open(self._fmt.file_path, "rb") as file:
                with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                    self._fmt.load(buffer)

                    target_ids = self._fmt.resolve_type_ids(names)
                    if target_ids is not None and not target_ids:
                        _log.warning("parse: no matching type for names=%r", names)
                        return []

                    messages = parse_buffer(buffer, self._fmt, target_ids)

        except Exception as error:
            _log.error("parse failed: %s", error)
            raise

        _log.info("parse(%r) -> %d messages", names, len(messages))
        return messages
