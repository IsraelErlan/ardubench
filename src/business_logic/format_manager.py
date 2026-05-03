"""FormatManager: reads FMT definitions from an ArduPilot .bin log file."""

import mmap
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure src/ is in sys.path so worker processes (ProcessPoolExecutor)
# can import this module without explicit path setup.
_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils._constants import (
    FMT_TYPE_ID, FMT_PAYLOAD_LEN,
    FORMAT_TO_STRUCT, FORMAT_SCALE, FMT_PAYLOAD_STRUCT,
)

_HEADER_B0 = 0xA3
_HEADER_B1 = 0x95


class FormatManager:
    """Scans the entire .bin file for FMT definitions and provides
    metadata for decoding every message type.

    ArduPilot can embed additional FMT messages anywhere in the data
    stream (not only at the beginning), so a full-file scan is required
    to collect all type definitions reliably.

    Public attributes
    -----------------
    file_path          : str  - path to the source .bin file
    data_start_offset  : int  - byte offset of the first non-FMT message
    """

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.data_start_offset: int = 0
        self._type_registry: Dict[int, dict] = {}
        self._name_to_type_id: Dict[str, int] = {}
        self._load_formats()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_formats(self) -> None:
        with open(self.file_path, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as buf:
                offset = 0
                end = len(buf)
                first_data_offset: Optional[int] = None

                while offset + 3 <= end:
                    if buf[offset] != _HEADER_B0 or buf[offset + 1] != _HEADER_B1:
                        break

                    msg_type_id = buf[offset + 2]
                    offset += 3

                    if msg_type_id == FMT_TYPE_ID:
                        if offset + FMT_PAYLOAD_LEN > end:
                            break
                        self._register_fmt(FMT_PAYLOAD_STRUCT.unpack_from(buf, offset))
                        offset += FMT_PAYLOAD_LEN
                    else:
                        if first_data_offset is None:
                            first_data_offset = offset - 3
                        total_length = self.get_length(msg_type_id)
                        if total_length is None:
                            break
                        offset += total_length - 3

        self.data_start_offset = first_data_offset if first_data_offset is not None else 0

    def _register_fmt(self, unpacked: tuple) -> None:
        type_id, total_length, name_raw, format_chars_raw, labels_raw = unpacked

        name = name_raw.decode('ascii', errors='ignore').strip('\x00')
        format_chars = format_chars_raw.decode('ascii', errors='ignore').strip('\x00')
        labels_str = labels_raw.decode('ascii', errors='ignore').strip('\x00')
        labels = [label.strip() for label in labels_str.split(',') if label.strip()]

        struct_format = '<' + ''.join(FORMAT_TO_STRUCT.get(c, '') for c in format_chars)
        scale_factors = [FORMAT_SCALE.get(c) for c in format_chars if c in FORMAT_TO_STRUCT]

        self._type_registry[type_id] = {
            'name': name,
            'total_length': total_length,
            'struct_format': struct_format,
            'labels': labels,
            'scale_factors': scale_factors,
        }
        self._name_to_type_id[name] = type_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_names(self) -> List[str]:
        """Return the names of all defined message types."""
        return list(self._name_to_type_id.keys())

    def get_id_by_name(self, name: str) -> Optional[int]:
        """Return the numeric type ID for a message name (e.g. 'GPS')."""
        return self._name_to_type_id.get(name)

    def get_length(self, type_id: int) -> Optional[int]:
        """Return the total byte length (header included) for a message type."""
        entry = self._type_registry.get(type_id)
        return entry['total_length'] if entry else None

    def decode(self, type_id: int, payload: bytes) -> Optional[Dict]:
        """Unpack a raw payload into a labelled dictionary."""
        entry = self._type_registry.get(type_id)
        if entry is None:
            return None

        try:
            raw_values = struct.unpack(entry['struct_format'], payload)
        except struct.error:
            return None

        decoded: Dict = {'_msg_type': entry['name']}
        for label, value, scale in zip(entry['labels'], raw_values, entry['scale_factors']):
            if isinstance(value, bytes):
                value = value.decode('ascii', errors='ignore').strip('\x00')
            elif scale is not None:
                value = round(value * scale, 10)
            decoded[label] = value
        return decoded
