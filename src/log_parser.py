"""LogParser: sequential parser for ArduPilot .bin log files.

Supports full-log decoding and filtered extraction (one or more message
types). The internal split between _read_raw and decode is intentional:
it makes a future producer/consumer threading model easy to add without
changing the public API or the core logic.
"""

from typing import Dict, Iterable, Iterator, List, Optional, Set, Union

from _constants import MSG_HEADER
from format_manager import FormatManager

# Type alias for the names parameter accepted by the public API
Names = Optional[Union[str, Iterable[str]]]


class LogParser:
    """Parses an ArduPilot .bin log file with optional message-type filtering.

    Usage
    -----
    parser = LogParser(fmt_manager)

    parser.parse()                      # all messages
    parser.parse('GPS')                 # GPS only  (seek-skips everything else)
    parser.parse(['GPS', 'ATT'])        # GPS + ATT (seek-skips everything else)
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
            return  # all requested names were unknown — nothing to yield

        for type_id, payload in self._read_raw(target_ids):
            decoded = self._fmt_manager.decode(type_id, payload)
            if decoded is not None:
                yield decoded

    def parse(self, names: Names = None) -> List[Dict]:
        """Return a list of decoded messages, optionally filtered by type name(s)."""
        return list(self.iter_messages(names))

    # ------------------------------------------------------------------
    # Internal helpers  (split here enables threading later)
    # ------------------------------------------------------------------

    def _read_raw(
        self, target_ids: Optional[Set[int]]
    ) -> Iterator[tuple]:
        """Yield (type_id, raw_payload) for every message that passes the filter.

        Non-matching messages are skipped via seek — no payload bytes are read
        for them. When target_ids is None every message is yielded.
        """
        with open(self._fmt_manager.file_path, 'rb') as f:
            f.seek(self._fmt_manager.data_start_offset)
            while True:
                header = f.read(3)
                if len(header) < 3 or header[:2] != MSG_HEADER:
                    break

                type_id = header[2]
                total_length = self._fmt_manager.get_length(type_id)
                if total_length is None:
                    break

                payload_len = total_length - 3

                if target_ids is not None and type_id not in target_ids:
                    f.seek(payload_len, 1)   # skip without reading
                    continue

                payload = f.read(payload_len)
                if len(payload) < payload_len:
                    break

                yield type_id, payload

    def _resolve_target_ids(self, names: Names) -> Optional[Set[int]]:
        """Convert name(s) to a set of type IDs, or None for no filter."""
        if names is None:
            return None
        if isinstance(names, str):
            names = [names]
        ids = {self._fmt_manager.get_id_by_name(n) for n in names}
        ids.discard(None)
        return ids
