"""Tests for all ArduPilot .bin log parsers."""
import asyncio
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'src' / 'business_logic'))

from sequential_parser import SequentialParser
from parallel_parser import ParallelParser
from mavlink_parser import MavlinkParser
from threaded_parser import ThreadedParser
from async_parser import AsyncParser

# ─────────────────────────────────────────────
# Binary-building helpers
# ─────────────────────────────────────────────

_HEADER = bytes([0xA3, 0x95])
_FMT_TYPE_ID = 0x80
_FMT_PAYLOAD_STRUCT = struct.Struct('<BB4s16s64s')
_FMT_TO_STRUCT = {
    'b': 'b', 'B': 'B', 'h': 'h', 'H': 'H',
    'i': 'i', 'I': 'I', 'f': 'f', 'd': 'd',
    'q': 'q', 'Q': 'Q', 'n': '4s', 'N': '16s', 'Z': '64s',
}


def _fmt_record(type_id: int, name: str, fmt_chars: str, labels: str) -> bytes:
    """Build an 89-byte FMT message that defines a data-message schema."""
    data_struct = struct.Struct('<' + ''.join(_FMT_TO_STRUCT.get(c, '') for c in fmt_chars))
    total_length = 3 + data_struct.size
    payload = _FMT_PAYLOAD_STRUCT.pack(
        type_id,
        total_length,
        name.encode().ljust(4, b'\x00')[:4],
        fmt_chars.encode().ljust(16, b'\x00')[:16],
        labels.encode().ljust(64, b'\x00')[:64],
    )
    return _HEADER + bytes([_FMT_TYPE_ID]) + payload


def _data_record(type_id: int, payload: bytes) -> bytes:
    return _HEADER + bytes([type_id]) + payload


# ─────────────────────────────────────────────
# Shared type definitions
# ─────────────────────────────────────────────

GPS_ID = 130
ATT_ID = 131
GPS_STRUCT = struct.Struct('<I')   # TimeUS: uint32
ATT_STRUCT = struct.Struct('<HH')  # Roll, Pitch: uint16


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

BAR_ID = 132
BAR_STRUCT = struct.Struct('<H')  # Alt: uint16


@pytest.fixture
def bin_file(tmp_path) -> str:
    """Valid .bin with 3 GPS, 2 ATT and 2 BAR messages."""
    content = (
        _fmt_record(GPS_ID, 'GPS', 'I',  'TimeUS') +
        _fmt_record(ATT_ID, 'ATT', 'HH', 'Roll,Pitch') +
        _fmt_record(BAR_ID, 'BAR', 'H',  'Alt') +
        _data_record(GPS_ID, GPS_STRUCT.pack(1000)) +
        _data_record(ATT_ID, ATT_STRUCT.pack(10, 20)) +
        _data_record(BAR_ID, BAR_STRUCT.pack(500)) +
        _data_record(GPS_ID, GPS_STRUCT.pack(2000)) +
        _data_record(ATT_ID, ATT_STRUCT.pack(30, 40)) +
        _data_record(BAR_ID, BAR_STRUCT.pack(510)) +
        _data_record(GPS_ID, GPS_STRUCT.pack(3000))
    )
    path = tmp_path / 'test.bin'
    path.write_bytes(content)
    return str(path)


@pytest.fixture
def invalid_header_file(tmp_path) -> str:
    """Valid GPS FMT then a record whose header bytes are wrong."""
    content = (
        _fmt_record(GPS_ID, 'GPS', 'I', 'TimeUS') +
        b'\xDE\xAD' + bytes([GPS_ID]) + GPS_STRUCT.pack(1)
    )
    path = tmp_path / 'bad_header.bin'
    path.write_bytes(content)
    return str(path)


@pytest.fixture
def truncated_fmt_file(tmp_path) -> str:
    """FMT record with only 10 of the required 86 payload bytes."""
    content = _HEADER + bytes([_FMT_TYPE_ID]) + b'\x00' * 10
    path = tmp_path / 'truncated_fmt.bin'
    path.write_bytes(content)
    return str(path)


@pytest.fixture
def unregistered_type_file(tmp_path) -> str:
    """GPS FMT defined, then a data record for an undefined type (200)."""
    content = (
        _fmt_record(GPS_ID, 'GPS', 'I', 'TimeUS') +
        _data_record(200, b'\x01\x02\x03\x04')
    )
    path = tmp_path / 'unknown_type.bin'
    path.write_bytes(content)
    return str(path)


@pytest.fixture
def truncated_payload_file(tmp_path) -> str:
    """GPS FMT (total_length=7) then a GPS record with only 2 of 4 payload bytes."""
    content = (
        _fmt_record(GPS_ID, 'GPS', 'I', 'TimeUS') +
        _HEADER + bytes([GPS_ID]) + b'\x01\x02'
    )
    path = tmp_path / 'truncated_payload.bin'
    path.write_bytes(content)
    return str(path)


# ─────────────────────────────────────────────
# SequentialParser — full contract + error cases
# ─────────────────────────────────────────────

class TestSequentialParser:
    def test_parse_all(self, bin_file):
        msgs = SequentialParser(bin_file).parse()
        assert len(msgs) == 10  # 3 FMT + 3 GPS + 2 ATT + 2 BAR

    def test_filter(self, bin_file):
        assert len(SequentialParser(bin_file).parse('GPS')) == 3
        assert len(SequentialParser(bin_file).parse('gps')) == 3        # case-insensitive
        assert len(SequentialParser(bin_file).parse(['GPS', 'ATT'])) == 5
        assert SequentialParser(bin_file).parse('UNKNOWN') == []

    def test_field_values(self, bin_file):
        gps = SequentialParser(bin_file).parse('GPS')
        assert [m['TimeUS'] for m in gps] == [1000, 2000, 3000]
        att = SequentialParser(bin_file).parse('ATT')
        assert att[0] == {'_msg_type': 'ATT', 'Roll': 10, 'Pitch': 20}
        assert att[1] == {'_msg_type': 'ATT', 'Roll': 30, 'Pitch': 40}

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SequentialParser(str(tmp_path / 'missing.bin'))

    def test_invalid_header_returns_partial(self, invalid_header_file):
        msgs = SequentialParser(invalid_header_file).parse()
        assert all(m['_msg_type'] == 'FMT' for m in msgs)

    def test_truncated_fmt_raises(self, truncated_fmt_file):
        with pytest.raises(ValueError, match='truncated FMT'):
            SequentialParser(truncated_fmt_file).parse()

    def test_unregistered_type_skipped(self, unregistered_type_file):
        msgs = SequentialParser(unregistered_type_file).parse()
        assert all(m['_msg_type'] == 'FMT' for m in msgs)

    def test_truncated_payload_returns_partial(self, truncated_payload_file):
        msgs = SequentialParser(truncated_payload_file).parse()
        assert all(m['_msg_type'] == 'FMT' for m in msgs)


# ─────────────────────────────────────────────
# Concurrent parsers — parity with Sequential
# ─────────────────────────────────────────────

class TestConcurrentParserParity:
    """Each concurrent parser must return the same output as SequentialParser."""

    def test_parallel_matches_sequential(self, bin_file):
        expected = SequentialParser(bin_file).parse()
        assert ParallelParser(bin_file).parse(n_workers=1) == expected

    def test_threaded_matches_sequential(self, bin_file):
        expected = SequentialParser(bin_file).parse()
        assert ThreadedParser(bin_file).parse(n_threads=1) == expected

    def test_threaded_multi_worker_matches_sequential(self, bin_file):
        expected = SequentialParser(bin_file).parse()
        result = sorted(ThreadedParser(bin_file).parse(n_threads=4), key=lambda m: (m['_msg_type'], str(m)))
        expected_sorted = sorted(expected, key=lambda m: (m['_msg_type'], str(m)))
        assert result == expected_sorted

    def test_async_matches_sequential(self, bin_file):
        expected = SequentialParser(bin_file).parse()
        assert asyncio.run(AsyncParser(bin_file).parse()) == expected


# ─────────────────────────────────────────────
# Cross-validation: custom parsers vs pymavlink
# ─────────────────────────────────────────────

class TestCrossValidationVsMavlink:
    def test_all_messages_match(self, bin_file):
        seq = SequentialParser(bin_file).parse()
        mav = MavlinkParser(bin_file).parse()

        assert len(seq) == len(mav), (
            f'message count differs: sequential={len(seq)}, mavlink={len(mav)}'
        )
        for i, (s, m) in enumerate(zip(seq, mav)):
            assert s == m, f'message {i} differs:\n  sequential: {s}\n  mavlink:    {m}'
