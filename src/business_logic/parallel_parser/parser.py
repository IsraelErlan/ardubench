import mmap
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from parallel_parser.workers import _init_worker, parse_chunk
from utils.shared._constants import MSG_HEADER
from utils.shared.format_manager import FormatManager, Names
from utils.shared.logger import get_logger
from utils.shared.timestamp_clock import TimestampClock, init_clock

_log = get_logger(__name__)


_CHUNK_SIZE = 1024 * 1024  # 1 MB per chunk


class ParallelParser:
    """Multi-process parser for ArduPilot .bin log files.

    Splits the file into 1 MB chunks distributed across a fixed worker pool.
    Each worker processes multiple chunks, improving load balancing when
    message density varies across the file.

    parser = ParallelParser('flight.bin')
    parser.parse()               # all messages
    parser.parse('GPS')          # one type
    parser.parse(['GPS', 'ATT']) # multiple types
    """

    def __init__(self, file_path: str) -> None:
        self._fmt = FormatManager(file_path)

    def parse(self, names: Names = None, n_workers: Optional[int] = None) -> List[Dict[str, Any]]:
        _log.debug("parse(names=%r)", names)
        if n_workers is not None and n_workers < 1:
            raise ValueError(f"n_workers must be >= 1, got {n_workers}")
        try:
            num_workers = n_workers if n_workers is not None else (getattr(os, "process_cpu_count", lambda: None)() or os.cpu_count() or 4)

            with open(self._fmt.file_path, "rb") as file:
                with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                    self._fmt.load(buffer)

                    target_ids = self._fmt.resolve_type_ids(names)
                    if target_ids is not None and not target_ids:
                        _log.warning("parse: no matching type for names=%r", names)
                        return []

                    clock = init_clock(buffer, self._fmt)
                    n_chunks = max(num_workers, len(buffer) // _CHUNK_SIZE)
                    splits = self._compute_byte_range_splits(n_chunks, buffer)

            n_chunks = len(splits) - 1
            _log.debug("spawning %d workers across %d chunks", num_workers, n_chunks)
            with ProcessPoolExecutor(max_workers=num_workers, initializer=_init_worker, initargs=(self._fmt,)) as executor:
                futures = [
                    executor.submit(parse_chunk, self._fmt.file_path, splits[i], splits[i + 1], target_ids, clock)
                    for i in range(n_chunks)
                ]
                chunks = [f.result() for f in futures]

            result = [message for chunk in chunks for message in chunk]
            _log.info("parse(%r) -> %d messages", names, len(result))
            return result
        except Exception as error:
            _log.error("parse failed: %s", error)
            raise

    def _compute_byte_range_splits(self, n_chunks: int, buffer: mmap.mmap) -> List[int]:
        """Divide the file into n_chunks byte ranges, each starting on a message boundary.

        Naive byte splits would land in the middle of a payload, so each split
        point is nudged forward to the next valid message header.
        Duplicate split points (e.g. near EOF) are removed via dict.fromkeys.
        """
        file_size = len(buffer)
        chunk_size = file_size // n_chunks

        splits = [0]
        for i in range(1, n_chunks):
            pos = _find_message_start(buffer, i * chunk_size, self._fmt)
            splits.append(pos if pos is not None else file_size)
        splits.append(file_size)
        return list(dict.fromkeys(splits))


def _find_message_start(buffer: mmap.mmap, offset: int, fmt: FormatManager) -> Optional[int]:
    """Return the byte offset of the next valid message at or after *offset*.

    Skips false-positive header matches (bytes 0xA3 0x95 that appear inside a
    payload) by requiring that the type_id byte is a known FMT entry.
    """
    scan_end = len(buffer)
    while offset + 3 <= scan_end:
        next_pos = buffer.find(MSG_HEADER, offset)
        if next_pos == -1 or next_pos + 3 > scan_end:
            return None
        if fmt.get_entry(buffer[next_pos + 2]) is not None:
            return next_pos
        offset = next_pos + 1
    return None
