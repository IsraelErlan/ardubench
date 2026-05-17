import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Dict, List, Optional

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from pymavlink import mavutil
from utils.shared.format_manager import Names
from utils.shared.logger import get_logger

_log = get_logger(__name__)


class MavlinkParser:
    """ArduPilot .bin log parser backed by pymavlink.

    Uses pymavlink's built-in DFReader instead of a custom binary decoder.
    Useful as a reference implementation to verify correctness and compare speed.

    parser = MavlinkParser('flight.bin')
    parser.parse()               # all messages
    parser.parse('GPS')          # one type
    parser.parse(['GPS', 'ATT']) # multiple types
    """

    def __init__(self, file_path: str) -> None:
        if not Path(file_path).is_file():
            raise FileNotFoundError(f"Log file not found: {file_path}")
        self.file_path = file_path

    def parse(self, names: Names = None) -> List[Dict[str, Any]]:
        _log.debug("parse(names=%r)", names)
        try:
            type_filter = _resolve_type_filter(names)
            mlog = mavutil.mavlink_connection(self.file_path, robust_parsing=True)
            messages: List[Dict[str, Any]] = []

            while True:
                msg = mlog.recv_msg()
                if msg is None:
                    break
                if msg.get_type() == "BAD_DATA":
                    continue
                if type_filter is not None and msg.get_type() not in type_filter:
                    continue
                row = msg.to_dict()
                row["_msg_type"] = row.pop("mavpackettype", msg.get_type())
                row["_timestamp"] = datetime.fromtimestamp(msg._timestamp, tz=ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                messages.append(row)

            _log.info("parse(%r) -> %d messages", names, len(messages))
            return messages
        except Exception as error:
            _log.error("parse failed: %s", error)
            raise


def _resolve_type_filter(names: Names) -> Optional[List[str]]:
    if names is None:
        return None
    if isinstance(names, str):
        return [names.upper()]
    return [n.upper() for n in names]
