import mmap
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.format_manager import FormatManager
from parallel_parser.workers import parse_chunk
from utils.shared._constants import MSG_HEADER
from utils.shared.logger import get_logger

_log = get_logger(__name__)

Names = Optional[Union[str, Iterable[str]]]


class ParallelParser:
    """Multi-process parser for ArduPilot .bin log files.

    Splits the file into equal chunks and decodes each chunk in a separate
    process. Fastest option for parsing all messages from large files.

    parser = ParallelParser('flight.bin')
    parser.parse()               # all messages
    parser.parse('GPS')          # one type
    parser.parse(['GPS', 'ATT']) # multiple types
    """

    def __init__(self, file_path: str) -> None:
        self._fmt = FormatManager(file_path)

    def parse(self, names: Names = None, n_workers: Optional[int] = None) -> List[Dict[str, Any]]:
        _log.debug('parse(names=%r)', names)
        try:
            num_workers = n_workers or os.cpu_count() or 4

            with open(self._fmt.file_path, 'rb') as file:
                with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                    self._fmt.load(buffer)

                    target_ids = _names_to_type_ids(self._fmt, names)
                    if target_ids is not None and not target_ids:
                        _log.warning('parse: no matching type for names=%r', names)
                        return []

                    splits = self._compute_byte_range_splits(num_workers, buffer)

            _log.debug('spawning %d worker processes', num_workers)
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [
                    executor.submit(parse_chunk, self._fmt.file_path, self._fmt, splits[i], splits[i + 1], target_ids)
                    for i in range(num_workers)
                ]
                chunks = [f.result() for f in futures]

            result = [message for chunk in chunks for message in chunk]
            _log.info('parse(%r) -> %d messages', names, len(result))
            return result
        except Exception as error:
            _log.error('parse failed: %s', error)
            raise

    def _compute_byte_range_splits(self, num_workers: int, buffer) -> List[int]:
        file_size = len(buffer)
        data_start = self._fmt.data_start_offset
        chunk_size = max(1, (file_size - data_start) // num_workers)

        splits = [data_start]
        for i in range(1, num_workers):
            pos = _find_message_start(buffer, data_start + i * chunk_size, self._fmt._registry)
            splits.append(pos if pos is not None else file_size)
        splits.append(file_size)
        return splits


def _find_message_start(buffer, offset: int, registry: dict) -> Optional[int]:
    scan_end = len(buffer)
    while offset + 3 <= scan_end:
        next_pos = buffer.find(MSG_HEADER, offset)
        if next_pos == -1 or next_pos + 3 > scan_end:
            return None
        if buffer[next_pos + 2] in registry:
            return next_pos
        offset = next_pos + 1
    return None


def _names_to_type_ids(fmt: FormatManager, names: Names) -> Optional[Set[int]]:
    if names is None:
        return None
    if isinstance(names, str):
        names = [names]
    type_ids = {fmt.get_id(name) for name in names}
    type_ids.discard(None)
    return type_ids
