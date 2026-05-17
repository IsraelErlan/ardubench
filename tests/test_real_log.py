"""
Integration tests: every custom parser is compared against MavlinkParser on the real log file.

These tests are intentionally slow (~6 minutes for a 400 MB / 7.6 M message file).
They require LOG_FILE_PATH to be set in .env.

Run all:      pytest tests/test_real_log.py -v
Run one:      pytest tests/test_real_log.py -v -k "sequential"
"""

import asyncio
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "business_logic"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parents[1] / ".env")

from async_parser import AsyncParser
from mavlink_parser import MavlinkParser
from parallel_parser import ParallelParser
from sequential_parser import SequentialParser
from threaded_parser import ThreadedParser

_LOG_PATH = os.environ.get("LOG_FILE_PATH", "")


# ─────────────────────────────────────────────────────────────────────────────
# Reference data — MavlinkParser runs once; everything else is derived from it
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def log_path() -> str:
    if not _LOG_PATH or not Path(_LOG_PATH).is_file():
        pytest.skip("LOG_FILE_PATH not set or file not found")
    return _LOG_PATH


@pytest.fixture(scope="session")
def reference(log_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse the log once with MavlinkParser and store three views of it."""
    all_messages = MavlinkParser(log_path).parse()
    return {
        "all":     all_messages,
        "gps":     [m for m in all_messages if m["_msg_type"] == "GPS"],
        "gps_att": [m for m in all_messages if m["_msg_type"] in ("GPS", "ATT")],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Comparison helper
# ─────────────────────────────────────────────────────────────────────────────

def _equal(a: Dict, b: Dict) -> bool:
    """True if both dicts have the same keys and values.
    Treats nan == nan, because Python's default comparison does not.
    """
    if a.keys() != b.keys():
        return False
    for key in a:
        va, vb = a[key], b[key]
        both_nan = isinstance(va, float) and isinstance(vb, float) and math.isnan(va) and math.isnan(vb)
        if not both_nan and va != vb:
            return False
    return True


def _assert_matches(custom: List[Dict], reference: List[Dict], label: str) -> None:
    assert len(custom) == len(reference), (
        f"{label}: expected {len(reference)} messages, got {len(custom)}"
    )
    diffs = [
        f"  [#{i}]  custom={c!r}\n        mavlink={r!r}"
        for i, (c, r) in enumerate(zip(custom, reference))
        if not _equal(c, r)
    ][:20]
    assert not diffs, f"{label} — {len(diffs)} message(s) differ:\n" + "\n".join(diffs)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: parse() — all messages
# ─────────────────────────────────────────────────────────────────────────────

def test_sequential_all(log_path, reference):
    result = SequentialParser(log_path).parse()
    _assert_matches(result, reference["all"], "SequentialParser.parse()")


def test_async_all(log_path, reference):
    result = asyncio.run(AsyncParser(log_path).parse())
    _assert_matches(result, reference["all"], "AsyncParser.parse()")


def test_parallel_all(log_path, reference):
    result = ParallelParser(log_path).parse()
    _assert_matches(result, reference["all"], "ParallelParser.parse()")


def test_threaded_all(log_path, reference):
    result = ThreadedParser(log_path).parse()
    _assert_matches(result, reference["all"], "ThreadedParser.parse()")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: parse('GPS') — single-type filter
# ─────────────────────────────────────────────────────────────────────────────

def test_sequential_gps(log_path, reference):
    result = SequentialParser(log_path).parse("GPS")
    _assert_matches(result, reference["gps"], "SequentialParser.parse('GPS')")


def test_async_gps(log_path, reference):
    result = asyncio.run(AsyncParser(log_path).parse("GPS"))
    _assert_matches(result, reference["gps"], "AsyncParser.parse('GPS')")


def test_parallel_gps(log_path, reference):
    result = ParallelParser(log_path).parse("GPS")
    _assert_matches(result, reference["gps"], "ParallelParser.parse('GPS')")


def test_threaded_gps(log_path, reference):
    result = ThreadedParser(log_path).parse("GPS")
    _assert_matches(result, reference["gps"], "ThreadedParser.parse('GPS')")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: parse(['GPS', 'ATT']) — multi-type filter
# ─────────────────────────────────────────────────────────────────────────────

def test_sequential_gps_att(log_path, reference):
    result = SequentialParser(log_path).parse(["GPS", "ATT"])
    _assert_matches(result, reference["gps_att"], "SequentialParser.parse(['GPS','ATT'])")


def test_async_gps_att(log_path, reference):
    result = asyncio.run(AsyncParser(log_path).parse(["GPS", "ATT"]))
    _assert_matches(result, reference["gps_att"], "AsyncParser.parse(['GPS','ATT'])")


def test_parallel_gps_att(log_path, reference):
    result = ParallelParser(log_path).parse(["GPS", "ATT"])
    _assert_matches(result, reference["gps_att"], "ParallelParser.parse(['GPS','ATT'])")


def test_threaded_gps_att(log_path, reference):
    result = ThreadedParser(log_path).parse(["GPS", "ATT"])
    _assert_matches(result, reference["gps_att"], "ThreadedParser.parse(['GPS','ATT'])")
