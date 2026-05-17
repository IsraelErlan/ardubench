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
    'c': 'h', 'C': 'H', 'e': 'i', 'E': 'I', 'L': 'i',
    'M': 'b', 'a': '64s', 'g': 'e',
}

GPS_ID, ATT_ID, BAR_ID, POS_ID = 130, 131, 132, 133
GPS_STRUCT = struct.Struct('<I')
ATT_STRUCT = struct.Struct('<HH')
BAR_STRUCT = struct.Struct('<H')
POS_STRUCT = struct.Struct('<hi')   # c → h (/100), L → i (/10_000_000)


def _fmt_record(type_id: int, name: str, fmt_chars: str, labels: str) -> bytes:
    data_struct = struct.Struct('<' + ''.join(_FMT_TO_STRUCT.get(c, '') for c in fmt_chars))
    payload = _FMT_PAYLOAD_STRUCT.pack(
        type_id, 3 + data_struct.size,
        name.encode().ljust(4, b'\x00')[:4],
        fmt_chars.encode().ljust(16, b'\x00')[:16],
        labels.encode().ljust(64, b'\x00')[:64],
    )
    return _HEADER + bytes([_FMT_TYPE_ID]) + payload


def _data_record(type_id: int, payload: bytes) -> bytes:
    return _HEADER + bytes([type_id]) + payload


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def bin_file(tmp_path) -> str:
    content = (
        _fmt_record(_FMT_TYPE_ID, 'FMT', 'BBnNZ', 'Type,Length,Name,Format,Columns') +
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
    p = tmp_path / 'test.bin'
    p.write_bytes(content)
    return str(p)


@pytest.fixture
def divisor_file(tmp_path) -> str:
    content = (
        _fmt_record(POS_ID, 'POS', 'cL', 'Alt,Lat') +
        _data_record(POS_ID, POS_STRUCT.pack(5000, 316017200)) +
        _data_record(POS_ID, POS_STRUCT.pack(-200, -118462000))
    )
    p = tmp_path / 'divisor.bin'
    p.write_bytes(content)
    return str(p)


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

def test_sequential(bin_file, tmp_path):
    p = SequentialParser(bin_file)
    assert len(p.parse()) == 11
    assert len(p.parse('GPS')) == 3
    assert len(p.parse('gps')) == 3
    assert len(p.parse(['GPS', 'ATT'])) == 5
    assert p.parse('UNKNOWN') == []
    assert [m['TimeUS'] for m in p.parse('GPS')] == [1000, 2000, 3000]

    with pytest.raises(FileNotFoundError):
        SequentialParser(str(tmp_path / 'missing.bin'))

    bad = tmp_path / 'bad.bin'
    bad.write_bytes(
        _fmt_record(GPS_ID, 'GPS', 'I', 'TimeUS') +
        b'\xDE\xAD' + bytes([GPS_ID]) + GPS_STRUCT.pack(1)
    )
    assert all(m['_msg_type'] == 'FMT' for m in SequentialParser(str(bad)).parse())


@pytest.mark.parametrize("parse_fn", [
    lambda f: ParallelParser(f).parse(n_workers=1),
    lambda f: ThreadedParser(f).parse(n_threads=1),
    lambda f: asyncio.run(AsyncParser(f).parse()),
])
def test_concurrent_matches_sequential(bin_file, parse_fn):
    assert parse_fn(bin_file) == SequentialParser(bin_file).parse()


def test_threaded_multi_chunk(bin_file):
    expected = SequentialParser(bin_file).parse()
    result = sorted(ThreadedParser(bin_file).parse(n_threads=4), key=lambda m: (m['_msg_type'], str(m)))
    expected = sorted(expected, key=lambda m: (m['_msg_type'], str(m)))
    drop_ts = lambda msgs: [{k: v for k, v in m.items() if k != '_timestamp'} for m in msgs]
    assert drop_ts(result) == drop_ts(expected)


def test_divisors(divisor_file, bin_file):
    msgs = SequentialParser(divisor_file).parse('POS')
    assert msgs[0]['Alt'] == pytest.approx(50.0)
    assert msgs[0]['Lat'] == pytest.approx(31.60172)
    assert msgs[1]['Alt'] == pytest.approx(-2.0)
    assert msgs[1]['Lat'] == pytest.approx(-11.8462)

    with pytest.raises(ValueError):
        ParallelParser(bin_file).parse(n_workers=0)
    with pytest.raises(ValueError):
        ThreadedParser(bin_file).parse(n_threads=0)


def test_mavlink_matches_sequential(bin_file):
    seq = SequentialParser(bin_file).parse()
    mav = MavlinkParser(bin_file).parse()
    assert seq == mav
