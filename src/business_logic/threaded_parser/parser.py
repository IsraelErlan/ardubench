import mmap
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.format_manager import FormatManager
from threaded_parser.workers import parse_chunk
from utils.shared._constants import MSG_HEADER_B0, MSG_HEADER_B1
from utils.shared.logger import get_logger

_log = get_logger(__name__)

Names = Optional[Union[str, Iterable[str]]]


class ThreadedParser:
    """Thread-pool parser for ArduPilot .bin log files.

    Same chunk-split strategy as ParallelParser but uses threads instead of
    processes. No pickling overhead, but the GIL limits CPU parallelism.
    Performs best when I/O is the bottleneck (e.g. network-mounted storage).

    parser = ThreadedParser('flight.bin')
    parser.parse()               # all messages
    parser.parse('GPS')          # one type
    parser.parse(['GPS', 'ATT']) # multiple types
    """

    def __init__(self, file_path: str, n_threads: int = 4) -> None:
        self._fmt = FormatManager(file_path)
        self._n_threads = n_threads

    def parse(self, names: Names = None, n_threads: Optional[int] = None) -> List[Dict[str, Any]]:
        _log.debug('parse(names=%r)', names)
        try:
            target_ids = _names_to_type_ids(self._fmt, names)
            if target_ids is not None and not target_ids:
                _log.warning('parse: no matching type for names=%r', names)
                return []

            num_threads = n_threads or self._n_threads
            _log.debug('spawning %d worker threads', num_threads)
            tasks = self._build_worker_tasks(num_threads, target_ids)

            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(parse_chunk, *task) for task in tasks]
                chunks = [future.result() for future in futures]

            result = [message for chunk in chunks for message in chunk]
            _log.info('parse(%r) -> %d messages', names, len(result))
            return result
        except Exception as error:
            _log.error('parse failed: %s', error)
            raise

    def _build_worker_tasks(self, num_threads: int, target_ids: Optional[Set[int]]) -> List[tuple]:
        split_offsets = self._compute_chunk_offsets(num_threads)
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
                        raise ValueError(f'invalid header at offset {offset}')
                    type_id = buffer[offset + 2]
                    type_entry = registry.get(type_id)
                    if type_entry is None:
                        raise ValueError(f'unregistered type_id {type_id} at offset {offset}')
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
