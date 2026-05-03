"""Shared constants for the ArduPilot binary log parser."""

import struct
from typing import Dict

MSG_HEADER = bytes([0xA3, 0x95])
FMT_TYPE_ID = 0x80          # 128 — the message type that defines other types
FMT_TOTAL_LEN = 89
FMT_PAYLOAD_LEN = FMT_TOTAL_LEN - 3   # 86 bytes after the 3-byte header

# Maps each ArduPilot format character to its Python struct equivalent.
FORMAT_TO_STRUCT: Dict[str, str] = {
    'b': 'b', 'B': 'B',
    'h': 'h', 'H': 'H',
    'i': 'i', 'I': 'I',
    'f': 'f', 'd': 'd',
    'c': 'h', 'C': 'H',
    'e': 'i', 'E': 'I',
    'L': 'i',
    'M': 'B',
    'q': 'q', 'Q': 'Q',
    'n': '4s', 'N': '16s', 'Z': '64s',
}

# Scaling divisors for format characters that store a real value as a
# multiplied integer (e.g. Lat stored as degrees x 1e7).
FORMAT_SCALE: Dict[str, float] = {
    'c': 1e-2,
    'C': 1e-2,
    'e': 1e-2,
    'E': 1e-2,
    'L': 1e-7,
}

# Struct used to unpack a raw FMT payload:
#   type_id (uint8) | length (uint8) | name (4s) | format_chars (16s) | labels (64s)
FMT_PAYLOAD_STRUCT = struct.Struct('<BB4s16s64s')
