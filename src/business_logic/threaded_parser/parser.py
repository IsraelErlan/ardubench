import mmap
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared.format_manager import FormatManager, Names
from threaded_parser.workers import parse_chunk
from utils.shared._constants import MSG_HEADER_B0, MSG_HEADER_B1, MSG_HEADER
from utils.shared.logger import get_logger

_log = get_logger(__name__)


class ThreadedParser:
    """Thread-pool parser for ArduPilot .bin log files.

    Same chunk-split strategy as ParallelParser but uses threads instead of
    processes. No pickling overhead, but the GIL limits CPU parallelism.
    Threads share the mmap buffer — no per-thread file open needed.

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
            num_threads = n_threads or self._n_threads

            with open(self._fmt.file_path, 'rb') as file:
                with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                    self._fmt.load(buffer)

                    target_ids = self._fmt.resolve_type_ids(names)
                    if target_ids is not None and not target_ids:
                        _log.warning('parse: no matching type for names=%r', names)
                        return []

                    splits = self._compute_chunk_offsets(num_threads, buffer)

                    _log.debug('spawning %d worker threads', num_threads)
                    with ThreadPoolExecutor(max_workers=num_threads) as executor:
                        futures = [
                            executor.submit(parse_chunk, buffer, self._fmt, splits[i], splits[i + 1], target_ids)
                            for i in range(len(splits) - 1)
                        ]
                        chunks = [f.result() for f in futures]

            result = [message for chunk in chunks for message in chunk]
            _log.info('parse(%r) -> %d messages', names, len(result))
            return result
        except Exception as error:
            _log.error('parse failed: %s', error)
            raise

    def _compute_chunk_offsets(self, num_workers: int, buffer) -> List[Optional[int]]:
        message_offsets = []
        offset = 0
        scan_end = len(buffer)

        while offset + 3 <= scan_end:
            if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
                raise ValueError(f'invalid header at offset {offset}')
            type_id = buffer[offset + 2]
            type_entry = self._fmt.get_entry(type_id)
            if type_entry is None:
                _log.warning('skipping unknown type_id=%d at offset=%d', type_id, offset)
                next_pos = buffer.find(MSG_HEADER, offset + 1)
                if next_pos == -1:
                    break
                offset = next_pos
                continue
            message_offsets.append(offset)
            offset += type_entry['total_length']

        if not message_offsets:
            return [None]

        step = max(1, len(message_offsets) // num_workers)
        splits: List[Optional[int]] = [
            message_offsets[i * step]
            for i in range(num_workers)
            if i * step < len(message_offsets)
        ]
        splits.append(None)
        return splits


