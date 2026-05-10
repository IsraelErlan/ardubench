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
# SequentialParser
# ─────────────────────────────────────────────

class TestSequentialParser:
    def test_parse_all_returns_all_messages(self, bin_file):
        msgs = SequentialParser(bin_file).parse()
        assert len(msgs) == 7

    def test_parse_single_name_filters_correctly(self, bin_file):
        msgs = SequentialParser(bin_file).parse('GPS')
        assert len(msgs) == 3
        assert all(m['_msg_type'] == 'GPS' for m in msgs)

    def test_parse_multiple_names(self, bin_file):
        msgs = SequentialParser(bin_file).parse(['GPS', 'ATT'])
        assert len(msgs) == 5  # excludes the 2 BAR messages

    def test_parse_case_insensitive(self, bin_file):
        lower = SequentialParser(bin_file).parse('gps')
        upper = SequentialParser(bin_file).parse('GPS')
        assert len(lower) == len(upper) == 3

    def test_parse_unknown_name_returns_empty(self, bin_file):
        assert SequentialParser(bin_file).parse('UNKNOWN') == []

    def test_field_values_are_correct(self, bin_file):
        msgs = SequentialParser(bin_file).parse('GPS')
        assert [m['TimeUS'] for m in msgs] == [1000, 2000, 3000]

    def test_att_field_values_are_correct(self, bin_file):
        msgs = SequentialParser(bin_file).parse('ATT')
        assert msgs[0] == {'_msg_type': 'ATT', 'Roll': 10, 'Pitch': 20}
        assert msgs[1] == {'_msg_type': 'ATT', 'Roll': 30, 'Pitch': 40}

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SequentialParser(str(tmp_path / 'missing.bin'))

    def test_invalid_header_raises(self, invalid_header_file):
        with pytest.raises(ValueError, match='invalid header'):
            SequentialParser(invalid_header_file).parse()

    def test_truncated_fmt_raises(self, truncated_fmt_file):
        with pytest.raises(ValueError, match='truncated FMT'):
            SequentialParser(truncated_fmt_file).parse()

    def test_unregistered_type_raises(self, unregistered_type_file):
        with pytest.raises(ValueError, match='unregistered type_id'):
            SequentialParser(unregistered_type_file).parse()

    def test_truncated_payload_raises(self, truncated_payload_file):
        with pytest.raises(ValueError, match='truncated payload'):
            SequentialParser(truncated_payload_file).parse()


# ─────────────────────────────────────────────
# ParallelParser
# ─────────────────────────────────────────────

class TestParallelParser:
    def test_parse_all_returns_all_messages(self, bin_file):
        msgs = ParallelParser(bin_file).parse(n_workers=1)
        assert len(msgs) == 7

    def test_parse_single_name_filters_correctly(self, bin_file):
        msgs = ParallelParser(bin_file).parse('GPS', n_workers=1)
        assert len(msgs) == 3
        assert all(m['_msg_type'] == 'GPS' for m in msgs)

    def test_parse_multiple_names(self, bin_file):
        msgs = ParallelParser(bin_file).parse(['GPS', 'ATT'], n_workers=1)
        assert len(msgs) == 5  # excludes the 2 BAR messages

    def test_parse_case_insensitive(self, bin_file):
        lower = ParallelParser(bin_file).parse('gps', n_workers=1)
        upper = ParallelParser(bin_file).parse('GPS', n_workers=1)
        assert len(lower) == len(upper) == 3

    def test_parse_unknown_name_returns_empty(self, bin_file):
        assert ParallelParser(bin_file).parse('UNKNOWN', n_workers=1) == []

    def test_field_values_are_correct(self, bin_file):
        msgs = ParallelParser(bin_file).parse('GPS', n_workers=1)
        assert [m['TimeUS'] for m in msgs] == [1000, 2000, 3000]

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ParallelParser(str(tmp_path / 'missing.bin'))


# ─────────────────────────────────────────────
# ThreadedParser
# ─────────────────────────────────────────────

class TestThreadedParser:
    def test_parse_all_returns_all_messages(self, bin_file):
        msgs = ThreadedParser(bin_file).parse(n_threads=1)
        assert len(msgs) == 7

    def test_parse_single_name_filters_correctly(self, bin_file):
        msgs = ThreadedParser(bin_file).parse('GPS', n_threads=1)
        assert len(msgs) == 3
        assert all(m['_msg_type'] == 'GPS' for m in msgs)

    def test_parse_multiple_names(self, bin_file):
        msgs = ThreadedParser(bin_file).parse(['GPS', 'ATT'], n_threads=1)
        assert len(msgs) == 5  # excludes the 2 BAR messages

    def test_parse_case_insensitive(self, bin_file):
        lower = ThreadedParser(bin_file).parse('gps', n_threads=1)
        upper = ThreadedParser(bin_file).parse('GPS', n_threads=1)
        assert len(lower) == len(upper) == 3

    def test_parse_unknown_name_returns_empty(self, bin_file):
        assert ThreadedParser(bin_file).parse('UNKNOWN', n_threads=1) == []

    def test_field_values_are_correct(self, bin_file):
        msgs = ThreadedParser(bin_file).parse('GPS', n_threads=1)
        assert [m['TimeUS'] for m in msgs] == [1000, 2000, 3000]

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ThreadedParser(str(tmp_path / 'missing.bin'))


# ─────────────────────────────────────────────
# AsyncParser
# ─────────────────────────────────────────────

class TestAsyncParser:
    def test_parse_all_returns_all_messages(self, bin_file):
        msgs = asyncio.run(AsyncParser(bin_file).parse())
        assert len(msgs) == 7

    def test_parse_single_name_filters_correctly(self, bin_file):
        msgs = asyncio.run(AsyncParser(bin_file).parse('GPS'))
        assert len(msgs) == 3
        assert all(m['_msg_type'] == 'GPS' for m in msgs)

    def test_parse_multiple_names(self, bin_file):
        msgs = asyncio.run(AsyncParser(bin_file).parse(['GPS', 'ATT']))
        assert len(msgs) == 5  # excludes the 2 BAR messages

    def test_parse_case_insensitive(self, bin_file):
        lower = asyncio.run(AsyncParser(bin_file).parse('gps'))
        upper = asyncio.run(AsyncParser(bin_file).parse('GPS'))
        assert len(lower) == len(upper) == 3

    def test_parse_unknown_name_returns_empty(self, bin_file):
        assert asyncio.run(AsyncParser(bin_file).parse('UNKNOWN')) == []

    def test_field_values_are_correct(self, bin_file):
        msgs = asyncio.run(AsyncParser(bin_file).parse('GPS'))
        assert [m['TimeUS'] for m in msgs] == [1000, 2000, 3000]

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            AsyncParser(str(tmp_path / 'missing.bin'))


# ─────────────────────────────────────────────
# Cross-validation: custom parsers vs pymavlink
# ─────────────────────────────────────────────

class TestCrossValidationVsMavlink:
    """Verify that SequentialParser produces identical data to pymavlink."""

    def test_all_messages_match(self, bin_file):
        seq = SequentialParser(bin_file).parse()
        # pymavlink includes FMT records in its output — exclude them
        mav = [m for m in MavlinkParser(bin_file).parse() if m['_msg_type'] != 'FMT']

        assert len(seq) == len(mav), (
            f'message count differs: sequential={len(seq)}, mavlink={len(mav)}'
        )
        for i, (s, m) in enumerate(zip(seq, mav)):
            assert s == m, f'message {i} differs:\n  sequential: {s}\n  mavlink:    {m}'
