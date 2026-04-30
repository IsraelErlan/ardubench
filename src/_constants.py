"""Shared constants for the ArduPilot binary log parser."""

import struct
from typing import Dict

MSG_HEADER = bytes([0xA3, 0x95])
FMT_MSG_ID = 0x80          # 128
FMT_TOTAL_LEN = 89
FMT_PAYLOAD_LEN = FMT_TOTAL_LEN - 3   # 86 bytes after the 3-byte header

# Maps ArduPilot format characters to Python struct format characters.
AP_TO_STRUCT: Dict[str, str] = {
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

# Scaling divisors for ArduPilot format characters that store a real value
# as a multiplied integer (same convention pymavlink uses).
AP_SCALE: Dict[str, float] = {
    'c': 1e-2,   # int16 × 100  → divide by 100
    'C': 1e-2,   # uint16 × 100 → divide by 100
    'e': 1e-2,   # int32 × 100  → divide by 100
    'E': 1e-2,   # uint32 × 100 → divide by 100
    'L': 1e-7,   # int32 lat/lon in degrees × 1e7 → divide by 1e7
}

# FMT payload layout:
#   defined_id (uint8) | length (uint8) | name (4s) | format (16s) | labels (64s)
FMT_STRUCT = struct.Struct('<BB4s16s64s')
