import mmap
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.format_manager import FormatManager
from utils.shared._constants import MSG_HEADER_B0, MSG_HEADER_B1
from utils.shared.logger import get_logger

_log = get_logger(__name__)

Names = Optional[Union[str, Iterable[str]]]


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
        _log.debug('parse(names=%r)', names)

        target_ids = _names_to_type_ids(self._fmt, names)
        if target_ids is not None and not target_ids:
            _log.warning('parse: no matching type for names=%r', names)
            return []

        messages: List[Dict[str, Any]] = []

        try:
            with open(self._fmt.file_path, 'rb') as file:
                with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                    offset = self._fmt.data_start_offset
                    scan_end = len(buffer)

                    while offset + 3 <= scan_end:
                        if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
                            raise ValueError(f'invalid header at offset {offset}')
                        type_id = buffer[offset + 2]
                        offset += 3

                        length = self._fmt.get_length(type_id)
                        if length is None:
                            raise ValueError(f'unregistered type_id {type_id} at offset {offset - 3}')
                        payload_len = length - 3

                        if target_ids is None or type_id in target_ids:
                            if offset + payload_len > scan_end:
                                raise ValueError(f'truncated payload for type_id {type_id} at offset {offset}')
                            message = self._fmt.decode_from(buffer, offset, type_id)
                            if message is not None:
                                messages.append(message)

                        offset += payload_len

        except Exception as error:
            _log.error('parse failed: %s', error)
            raise

        _log.info('parse(%r) -> %d messages', names, len(messages))
        return messages


def _names_to_type_ids(fmt: FormatManager, names: Names) -> Optional[Set[int]]:
    if names is None:
        return None
    if isinstance(names, str):
        names = [names]
    type_ids = {fmt.get_id(name) for name in names}
    type_ids.discard(None)
    return type_ids
