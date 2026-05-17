"""Timestamp clock mirroring PyMAVLink's DFReaderClock_usec for ArduPilot .bin logs."""

import struct
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING, Any, Dict, Optional

_src_dir = str(Path(__file__).parent.parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared._constants import FORMAT_TO_STRUCT, MSG_HEADER, MSG_HEADER_B0, MSG_HEADER_B1
from utils.shared.logger import get_logger

if TYPE_CHECKING:
    from utils.shared.format_manager import FormatManager

_log = get_logger(__name__)
_TZ = ZoneInfo("Asia/Jerusalem")

# Seconds between Unix epoch (1970-01-01) and GPS epoch (1980-01-06)
_GPS_EPOCH: int = 86400 * (10 * 365 + int((1980 - 1969) / 4) + 1 + 6 - 2)
# Current GPS leap seconds offset
_GPS_LEAP_SECONDS: int = 18


class TimestampClock:
    """Mirrors DFReaderClock_usec from PyMAVLink.

    set_message_timestamp logic (in priority order):
      1. First field is 'TimeUS'  →  timebase + TimeUS * 1e-6
      2. First field is 'TimeMS', not ACC*/GYR*, not going backwards  →  timebase + TimeMS * 1e-3
      3. Otherwise  →  carry-forward (self.timestamp)
    """

    def __init__(self) -> None:
        self.timebase: float = 0.0
        self.timestamp: float = 0.0
        self.first_us_stamp: Optional[int] = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def set_timebase(
        self, gps_week: int, gps_ms: int, gps_time_us: int, first_us_stamp: int
    ) -> None:
        """Compute absolute timebase from GPS week/ms and autopilot TimeUS.

        Mirrors DFReaderClock_usec.find_time_base().
        """
        t = _GPS_EPOCH + 86400 * 7 * gps_week + gps_ms * 0.001 - _GPS_LEAP_SECONDS
        self.timebase = t - gps_time_us * 0.000001
        self.first_us_stamp = first_us_stamp
        self.timestamp = self.timebase + first_us_stamp * 0.000001

    def rewind(self) -> None:
        """Reset carry-forward state. Mirrors DFReaderClock_usec.rewind_event()."""
        self.timestamp = self.timebase
        if self.first_us_stamp is not None:
            self.timestamp += self.first_us_stamp * 0.000001

    def copy(self) -> "TimestampClock":
        """Return a fresh copy with carry-forward state reset to initial position.

        Used by parallel/threaded workers so each chunk starts from the same
        initial timestamp without sharing mutable state.
        """
        c = TimestampClock()
        c.timebase = self.timebase
        c.first_us_stamp = self.first_us_stamp
        c.rewind()
        return c

    # ------------------------------------------------------------------
    # Per-message stamping
    # ------------------------------------------------------------------

    def set_message_timestamp(self, msg: Dict[str, Any], entry: Dict[str, Any]) -> None:
        """Set _timestamp on msg dict. Mirrors DFReaderClock_usec.set_message_timestamp()."""
        labels = entry["labels"]
        name = entry["name"]

        if labels and labels[0] == "TimeUS" and "TimeUS" in msg:
            ts = self.timebase + msg["TimeUS"] * 0.000001
        elif (
            labels
            and labels[0] == "TimeMS"
            and "TimeMS" in msg
            and not name.startswith("ACC")
            and not name.startswith("GYR")
            and self.timebase + msg["TimeMS"] * 0.001 >= self.timestamp
        ):
            ts = self.timebase + msg["TimeMS"] * 0.001
        else:
            ts = self.timestamp

        try:
            msg["_timestamp"] = datetime.fromtimestamp(ts, tz=_TZ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except (OSError, OverflowError, ValueError):
            msg["_timestamp"] = f"+{ts:.3f}s"
        self.timestamp = ts

    def advance_from_payload(self, payload: bytes, entry: Dict[str, Any]) -> None:
        """Advance carry-forward state from raw payload without full decode.

        Called for messages skipped due to target_ids filtering, so the clock
        stays in sync with the log stream.
        """
        labels = entry["labels"]
        fmt_chars = entry["fmt_chars"]
        name = entry["name"]

        if not labels or not fmt_chars:
            return

        struct_char = FORMAT_TO_STRUCT.get(fmt_chars[0])
        if struct_char is None:
            return

        sz = struct.calcsize(struct_char)
        if len(payload) < sz:
            return

        (raw_val,) = struct.unpack_from("<" + struct_char, payload)

        if labels[0] == "TimeUS":
            self.timestamp = self.timebase + raw_val * 0.000001
        elif (
            labels[0] == "TimeMS"
            and not name.startswith("ACC")
            and not name.startswith("GYR")
            and self.timebase + raw_val * 0.001 >= self.timestamp
        ):
            self.timestamp = self.timebase + raw_val * 0.001


# ------------------------------------------------------------------
# Clock initialisation (mirrors DFReader.init_clock for usec logs)
# ------------------------------------------------------------------


def init_clock(buffer: Any, fmt: "FormatManager") -> TimestampClock:
    """Pre-scan the buffer to build a TimestampClock.

    Mirrors the DFReaderClock_usec path in PyMAVLink's DFReader.init_clock():
    - Finds the first TimeUS value in the log (first_us_stamp).
    - Finds the first GPS message with GWk > 0 to compute an absolute timebase.
    - Falls back to relative timestamps (seconds from boot) if no GPS lock found.

    Must be called after fmt.load(buffer).
    """
    clock = TimestampClock()
    first_us_stamp: Optional[int] = None
    gps_id = fmt.get_id("GPS")

    offset = fmt.first_data_offset
    scan_end = len(buffer)

    while offset + 3 <= scan_end:
        if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
            break
        type_id = buffer[offset + 2]
        offset += 3

        entry = fmt.get_entry(type_id)
        if entry is None:
            nxt = buffer.find(MSG_HEADER, offset)
            if nxt == -1:
                break
            offset = nxt
            continue

        payload_len = entry["total_length"] - 3

        # Track the first TimeUS value seen in the log
        if (
            first_us_stamp is None
            and entry["labels"]
            and entry["labels"][0] == "TimeUS"
            and offset + payload_len <= scan_end
        ):
            msg = fmt.decode_from(buffer, offset, type_id)
            if msg is not None:
                first_us_stamp = int(msg["TimeUS"])

        # Look for a GPS message with a valid GPS week (GWk > 0)
        if (
            gps_id is not None
            and type_id == gps_id
            and first_us_stamp is not None
            and offset + payload_len <= scan_end
        ):
            msg = fmt.decode_from(buffer, offset, type_id)
            if msg is not None:
                gps_week = msg.get("GWk")
                gps_ms = msg.get("GMS")
                time_us = msg.get("TimeUS")
                if (
                    gps_week is not None
                    and gps_ms is not None
                    and time_us is not None
                    and int(gps_week) > 0
                ):
                    clock.set_timebase(
                        int(gps_week), int(gps_ms), int(time_us), first_us_stamp
                    )
                    _log.debug(
                        "init_clock: GPS lock found — timebase=%.3f first_us_stamp=%d",
                        clock.timebase,
                        first_us_stamp,
                    )
                    return clock

        offset += payload_len

    # No GPS with valid time found.
    # Mirrors PyMAVLink: DFReaderClock_usec is created but find_time_base() is never
    # called, so timebase=0, first_us_stamp=None, timestamp=0.
    # Messages with TimeUS still get TimeUS*1e-6; others carry-forward from 0.
    _log.debug("init_clock: no GPS lock — using relative timestamps")
    return clock
