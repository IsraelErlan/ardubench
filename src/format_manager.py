"""FormatManager: reads FMT definitions from an ArduPilot .bin log file."""

import struct
from typing import Dict, Optional

from _constants import (
    MSG_HEADER, FMT_TYPE_ID, FMT_PAYLOAD_LEN,
    FORMAT_TO_STRUCT, FORMAT_SCALE, FMT_PAYLOAD_STRUCT,
)


class FormatManager:
    """Scans the entire .bin file for FMT definitions and provides
    metadata for decoding every message type.

    ArduPilot can embed additional FMT messages anywhere in the data
    stream (not only at the beginning), so a full-file scan is required
    to collect all type definitions reliably.

    Public attributes
    -----------------
    file_path          : str  – path to the source .bin file
    data_start_offset  : int  – byte offset of the first non-FMT message
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
        # Walks the entire file: parses every FMT message it finds and
        # seeks past all other messages using already-known lengths.
        with open(self.file_path, 'rb') as f:
            first_data_offset: Optional[int] = None

            while True:
                current_pos = f.tell()
                header = f.read(3)

                if len(header) < 3 or header[:2] != MSG_HEADER:
                    break

                msg_type_id = header[2]

                if msg_type_id == FMT_TYPE_ID:
                    payload = f.read(FMT_PAYLOAD_LEN)
                    if len(payload) < FMT_PAYLOAD_LEN:
                        break
                    self._register_fmt(payload)
                else:
                    if first_data_offset is None:
                        first_data_offset = current_pos
                    total_length = self.get_length(msg_type_id)
                    if total_length is None:
                        break  # unknown type; cannot determine how many bytes to skip
                    f.seek(total_length - 3, 1)

        self.data_start_offset = first_data_offset if first_data_offset is not None else 0

    def _register_fmt(self, payload: bytes) -> None:
        type_id, total_length, name_raw, format_chars_raw, labels_raw = (
            FMT_PAYLOAD_STRUCT.unpack(payload)
        )

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

    def get_id_by_name(self, name: str) -> Optional[int]:
        """Return the numeric type ID for a message name (e.g. 'GPS')."""
        return self._name_to_type_id.get(name)

    def get_length(self, type_id: int) -> Optional[int]:
        """Return the total byte length (header included) for a message type."""
        entry = self._type_registry.get(type_id)
        return entry['total_length'] if entry else None

    def decode(self, type_id: int, payload: bytes) -> Optional[Dict]:
        """Unpack a raw payload into a labelled dictionary.

        Returns None if the type is unknown or the payload is malformed.
        """
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
