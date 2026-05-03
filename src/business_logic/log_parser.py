"""LogParser: sequential and parallel parser for ArduPilot .bin log files."""

import mmap
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Union

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from business_logic.format_manager import FormatManager

Names = Optional[Union[str, Iterable[str]]]

_HEADER_B0 = 0xA3
_HEADER_B1 = 0x95


# Module-level worker required by ProcessPoolExecutor (must be picklable).
def _parse_worker(args: tuple) -> tuple:
    file_path, name = args
    fmt_manager = FormatManager(file_path)
    messages = LogParser(fmt_manager).parse(name)
    return name, messages


class LogParser:
    """Parses an ArduPilot .bin log file with optional message-type filtering.

    Sequential API
    --------------
    parser.parse()                   # all messages (buffered I/O)
    parser.parse('GPS')              # one type    (mmap + skip)
    parser.parse(['GPS', 'ATT'])     # n types     (mmap + skip, single pass)

    Parallel API
    ------------
    parser.parse_parallel(['GPS', 'ATT', 'IMU'])
        Spawns one process per type via ProcessPoolExecutor.
        Returns {name: [messages]} instead of a flat list.
        Recommended when extracting 3+ types simultaneously.
    """

    def __init__(self, fmt_manager: FormatManager) -> None:
        self._fmt_manager = fmt_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def iter_messages(self, names: Names = None) -> Iterator[Dict]:
        """Yield decoded messages, optionally filtered by type name(s)."""
        target_ids = self._resolve_target_ids(names)
        if target_ids is not None and len(target_ids) == 0:
            return

        for type_id, payload in self._read_raw(target_ids):
            decoded = self._fmt_manager.decode(type_id, payload)
            if decoded is not None:
                yield decoded

    def parse(self, names: Names = None) -> List[Dict]:
        """Return a flat list of decoded messages (single sequential pass)."""
        return list(self.iter_messages(names))

    def parse_parallel(
        self,
        names: List[str],
        max_workers: Optional[int] = None,
    ) -> Dict[str, List[Dict]]:
        """Parse multiple message types in parallel using separate processes.

        Returns {type_name: [decoded_messages]}.
        Use when extracting 3+ types — speedup outweighs per-process overhead.
        """
        file_path = self._fmt_manager.file_path
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            pairs = executor.map(_parse_worker, [(file_path, n) for n in names])
        return dict(pairs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_raw(self, target_ids: Optional[Set[int]]) -> Iterator[tuple]:
        if target_ids is not None:
            yield from self._read_raw_mmap(target_ids)
        else:
            yield from self._read_raw_buffered()

    def _read_raw_mmap(self, target_ids: Set[int]) -> Iterator[tuple]:
        with open(self._fmt_manager.file_path, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as buf:
                offset = self._fmt_manager.data_start_offset
                end = len(buf)

                while offset + 3 <= end:
                    if buf[offset] != _HEADER_B0 or buf[offset + 1] != _HEADER_B1:
                        break

                    type_id = buf[offset + 2]
                    offset += 3

                    total_length = self._fmt_manager.get_length(type_id)
                    if total_length is None:
                        break

                    payload_len = total_length - 3

                    if type_id not in target_ids:
                        offset += payload_len
                        continue

                    if offset + payload_len > end:
                        break

                    yield type_id, buf[offset:offset + payload_len]
                    offset += payload_len

    def _read_raw_buffered(self) -> Iterator[tuple]:
        with open(self._fmt_manager.file_path, 'rb') as f:
            f.seek(self._fmt_manager.data_start_offset)
            while True:
                header = f.read(3)
                if len(header) < 3 or header[0] != _HEADER_B0 or header[1] != _HEADER_B1:
                    break

                type_id = header[2]
                total_length = self._fmt_manager.get_length(type_id)
                if total_length is None:
                    break

                payload_len = total_length - 3
                payload = f.read(payload_len)
                if len(payload) < payload_len:
                    break

                yield type_id, payload

    def _resolve_target_ids(self, names: Names) -> Optional[Set[int]]:
        if names is None:
            return None
        if isinstance(names, str):
            names = [names]
        ids = {self._fmt_manager.get_id_by_name(n) for n in names}
        ids.discard(None)
        return ids
