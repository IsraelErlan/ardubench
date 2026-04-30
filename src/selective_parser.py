"""SelectiveParser: fast extraction of a single message type from a .bin file."""

from typing import Dict, Iterator, List, Optional

from _constants import MSG_HEADER
from format_manager import FormatManager


class SelectiveParser:
    """Extracts only one message type, skipping all others via seek.

    For every non-matching message the file pointer is advanced by
    ``file.seek(payload_len, 1)`` instead of reading the bytes into
    memory, which avoids unnecessary I/O and keeps memory usage flat.
    This makes it significantly faster than FullLogParser when you only
    need one message type from a large file.
    """

    def __init__(self, fmt_manager: FormatManager) -> None:
        self._fmt = fmt_manager

    def iter_messages(self, name: str) -> Iterator[Dict]:
        """Yield only messages of the given type (e.g. ``'GPS'``)."""
        target_id: Optional[int] = self._fmt.get_id_by_name(name)
        if target_id is None:
            return

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

                payload_len = length - 3

                if msg_id != target_id:
                    f.seek(payload_len, 1)   # skip without reading
                    continue

                payload = f.read(payload_len)
                if len(payload) < payload_len:
                    break

                decoded = self._fmt.decode(msg_id, payload)
                if decoded is not None:
                    yield decoded

    def parse(self, name: str) -> List[Dict]:
        """Return a list of all decoded messages of the given type."""
        return list(self.iter_messages(name))
