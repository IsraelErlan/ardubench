"""FullLogParser: sequentially decodes every message in a .bin log file."""

from typing import Dict, Iterator, List

from _constants import MSG_HEADER
from format_manager import FormatManager


class FullLogParser:
    """Iterates through the entire data stream and decodes every message.

    Use this when you need a complete, chronological view of the log.
    For large files where only one message type matters, prefer
    SelectiveParser instead.
    """

    def __init__(self, fmt_manager: FormatManager) -> None:
        self._fmt = fmt_manager

    def iter_messages(self) -> Iterator[Dict]:
        """Yield every decoded message in chronological order."""
        with open(self._fmt.file_path, 'rb') as f:
            f.seek(self._fmt.data_start_offset)
            while True:
                header = f.read(3)
                if len(header) < 3 or header[:2] != MSG_HEADER:
                    break

                msg_id = header[2]
                length = self._fmt.get_length(msg_id)
                if length is None:
                    break

                payload = f.read(length - 3)
                if len(payload) < length - 3:
                    break

                decoded = self._fmt.decode(msg_id, payload)
                if decoded is not None:
                    yield decoded

    def parse(self) -> List[Dict]:
        """Return a list of all decoded messages."""
        return list(self.iter_messages())
