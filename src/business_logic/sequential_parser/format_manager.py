"""Loads and caches FMT definitions from an ArduPilot .bin log file."""

import struct
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared._constants import (
    FMT_TYPE_ID, FMT_PAYLOAD_LEN, FMT_PAYLOAD_STRUCT,
    FORMAT_TO_STRUCT, FORMAT_SCALE,
    MSG_HEADER_B0, MSG_HEADER_B1,
)
from utils.shared.logger import get_logger

_log = get_logger(__name__)


class FormatManager:
    """Exposes per-type decode metadata for ArduPilot .bin log files.

    Does not open the file itself — call _load_from_buffer(buffer) once
    the caller has opened the file, so the file handle is shared.
    """

    def __init__(self, file_path: str) -> None:
        if not Path(file_path).is_file():
            raise FileNotFoundError(f'Log file not found: {file_path}')
        self.file_path = file_path
        self.data_start_offset: int = 0
        self._registry: Dict[int, Dict[str, Any]] = {}
        self._name_to_id: Dict[str, int] = {}

    def _load_from_buffer(self, buffer) -> None:
        """Scan FMT records from an already-open mmap buffer."""
        if self._registry:
            return

        offset, scan_end = 0, len(buffer)
        while offset + 3 <= scan_end:
            if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
                break
            type_id = buffer[offset + 2]
            offset += 3
            if type_id == FMT_TYPE_ID:
                if offset + FMT_PAYLOAD_LEN > scan_end:
                    break
                self._register_type(FMT_PAYLOAD_STRUCT.unpack_from(buffer, offset))
                offset += FMT_PAYLOAD_LEN
            else:
                self.data_start_offset = offset - 3
                break

        _log.info('loaded %s  [%d types, data offset: %d]',
                  Path(self.file_path).name, len(self._registry), self.data_start_offset)

    def get_id(self, name: str) -> Optional[int]:
        return self._name_to_id.get(name.upper())

    def get_length(self, type_id: int) -> Optional[int]:
        type_entry = self._registry.get(type_id)
        return type_entry['total_length'] if type_entry else None

    def decode_from(self, buffer, offset: int, type_id: int) -> Optional[Dict[str, Any]]:
        type_entry = self._registry.get(type_id)
        if type_entry is None:
            return None
        try:
            unpacked = type_entry['struct'].unpack_from(buffer, offset)
        except struct.error:
            return None
        return self._build_message(type_entry, unpacked)

    def _register_type(self, unpacked: tuple) -> None:
        type_id, total_length, name_raw, fmt_raw, labels_raw = unpacked
        name = name_raw.decode('ascii', errors='ignore').strip('\x00')
        fmt_chars = fmt_raw.decode('ascii', errors='ignore').strip('\x00')
        labels = [label.strip() for label in labels_raw.decode('ascii', errors='ignore').strip('\x00').split(',') if label.strip()]
        scales = [FORMAT_SCALE.get(c) for c in fmt_chars if c in FORMAT_TO_STRUCT]
        self._registry[type_id] = {
            'name': name,
            'total_length': total_length,
            'struct': struct.Struct('<' + ''.join(FORMAT_TO_STRUCT.get(c, '') for c in fmt_chars)),
            'labels': labels,
            'scales': scales,
        }
        self._name_to_id[name] = type_id

    def _build_message(self, type_entry: Dict[str, Any], unpacked: tuple) -> Dict[str, Any]:
        message: Dict[str, Any] = {'_msg_type': type_entry['name']}
        for label, value, scale in zip(type_entry['labels'], unpacked, type_entry['scales']):
            if isinstance(value, bytes):
                value = value.decode('ascii', errors='ignore').strip('\x00')
            elif scale is not None:
                value = round(value * scale, 10)
            message[label] = value
        return message
