import mmap
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from parallel_parser.format_manager import FormatManager
from parallel_parser.workers import parse_chunk
from utils.shared._constants import MSG_HEADER_B0, MSG_HEADER_B1
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
        target_ids = _names_to_type_ids(self._fmt, names)
        if target_ids is not None and not target_ids:
            _log.warning('parse: no matching type for names=%r', names)
            return []

        num_workers = n_workers or os.cpu_count() or 4
        _log.debug('spawning %d worker processes', num_workers)
        tasks = self._build_worker_tasks(num_workers, target_ids)

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(parse_chunk, *task) for task in tasks]
            chunks = [future.result() for future in futures]

        result = [message for chunk in chunks for message in chunk]
        _log.info('parse(%r) â†’ %d messages', names, len(result))
        return result

    def _build_worker_tasks(self, num_workers: int, target_ids: Optional[Set[int]]) -> List[tuple]:
        split_offsets = self._compute_chunk_offsets(num_workers)
        return [
            (self._fmt.file_path, self._fmt, split_offsets[i], split_offsets[i + 1], target_ids)
            for i in range(len(split_offsets) - 1)
        ]

    def _compute_chunk_offsets(self, num_chunks: int) -> List[Optional[int]]:
        message_offsets = []
        with open(self._fmt.file_path, 'rb') as file:
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                offset = self._fmt.data_start_offset
                scan_end = len(buffer)
                registry = self._fmt._registry

                while offset + 3 <= scan_end:
                    if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
                        break
                    type_id = buffer[offset + 2]
                    type_entry = registry.get(type_id)
                    if type_entry is None:
                        break
                    message_offsets.append(offset)
                    offset += type_entry['total_length']

        step = max(1, len(message_offsets) // num_chunks)
        split_offsets: List[Optional[int]] = [message_offsets[i * step] for i in range(num_chunks)]
        split_offsets.append(None)
        return split_offsets


def _names_to_type_ids(fmt: FormatManager, names: Names) -> Optional[Set[int]]:
    if names is None:
        return None
    if isinstance(names, str):
        names = [names]
    type_ids = {fmt.get_id(name) for name in names}
    type_ids.discard(None)
    return type_ids
