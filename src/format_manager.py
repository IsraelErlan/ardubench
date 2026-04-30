"""FormatManager: reads FMT definitions from an ArduPilot .bin log file."""

import struct
from typing import Dict, Optional

from _constants import (
    MSG_HEADER, FMT_MSG_ID, FMT_PAYLOAD_LEN,
    AP_TO_STRUCT, AP_SCALE, FMT_STRUCT,
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
        self._formats: Dict[int, dict] = {}
        self._name_to_id: Dict[str, int] = {}
        self._load_formats()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_formats(self) -> None:
        # Two-pass strategy:
        # Pass 1 – collect every FMT definition from the whole file by
        #          skipping non-FMT messages with seek (uses lengths that
        #          were already learned from earlier FMT messages).
        # Pass 2 – not needed; data_start_offset is recorded in pass 1.
        with open(self.file_path, 'rb') as f:
            first_data_pos: Optional[int] = None

            while True:
                pos = f.tell()
                header = f.read(3)

                if len(header) < 3 or header[:2] != MSG_HEADER:
                    break

                msg_id = header[2]

                if msg_id == FMT_MSG_ID:
                    payload = f.read(FMT_PAYLOAD_LEN)
                    if len(payload) < FMT_PAYLOAD_LEN:
                        break
                    self._parse_fmt(payload)
                else:
                    if first_data_pos is None:
                        first_data_pos = pos
                    entry = self._formats.get(msg_id)
                    if entry is None:
                        break  # unknown type; cannot determine skip length
                    f.seek(entry['length'] - 3, 1)

        self.data_start_offset = first_data_pos if first_data_pos is not None else 0

    def _parse_fmt(self, payload: bytes) -> None:
        defined_id, length, name_raw, fmt_raw, labels_raw = FMT_STRUCT.unpack(payload)

        name = name_raw.decode('ascii', errors='ignore').strip('\x00')
        ap_fmt = fmt_raw.decode('ascii', errors='ignore').strip('\x00')
        labels_str = labels_raw.decode('ascii', errors='ignore').strip('\x00')
        labels = [lbl.strip() for lbl in labels_str.split(',') if lbl.strip()]

        struct_fmt = '<' + ''.join(AP_TO_STRUCT.get(c, '') for c in ap_fmt)
        # Per-field scale factors (None means no scaling needed)
        scales = [AP_SCALE.get(c) for c in ap_fmt if c in AP_TO_STRUCT]

        self._formats[defined_id] = {
            'name': name,
            'length': length,
            'struct_fmt': struct_fmt,
            'labels': labels,
            'scales': scales,
        }
        self._name_to_id[name] = defined_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_id_by_name(self, name: str) -> Optional[int]:
        """Return the numeric message ID for a message name (e.g. 'GPS')."""
        return self._name_to_id.get(name)

    def get_length(self, msg_id: int) -> Optional[int]:
        """Return the total byte length (header included) for a message type."""
        entry = self._formats.get(msg_id)
        return entry['length'] if entry else None

    def decode(self, msg_id: int, payload: bytes) -> Optional[Dict]:
        """Unpack a raw payload into a labelled dictionary.

        Returns None if the message type is unknown or the payload is malformed.
        """
        entry = self._formats.get(msg_id)
        if entry is None:
            return None

        try:
            values = struct.unpack(entry['struct_fmt'], payload)
        except struct.error:
            return None

        result: Dict = {'_msg_type': entry['name']}
        for label, value, scale in zip(entry['labels'], values, entry['scales']):
            if isinstance(value, bytes):
                value = value.decode('ascii', errors='ignore').strip('\x00')
            elif scale is not None:
                value = round(value * scale, 10)
            result[label] = value
        return result
