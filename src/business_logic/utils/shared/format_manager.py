"""Shared FormatManager for all ArduPilot .bin log parsers."""

import array
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Union

_src_dir = str(Path(__file__).parent.parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from utils.shared._constants import (
    FMT_TYPE_ID, FMT_PAYLOAD_LEN, FMT_PAYLOAD_STRUCT,
    FORMAT_TO_STRUCT, FORMAT_DIVISOR,
    MSG_HEADER_B0, MSG_HEADER_B1, MSG_HEADER,
)
from utils.shared.logger import get_logger

_log = get_logger(__name__)

Names = Optional[Union[str, Iterable[str]]]


class FormatManager:
    """Exposes per-type decode metadata for ArduPilot .bin log files.

    Does not open the file itself. Call load(buffer) once the caller has
    opened the file, so the file handle can be shared with the parser.

    Includes pickle support (__getstate__/__setstate__) so instances can be
    sent to worker processes via ProcessPoolExecutor.
    """

    def __init__(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f'Log file not found: {file_path}')
        if path.stat().st_size == 0:
            raise ValueError(f'File is empty: {file_path}')
        self.file_path = file_path
        self._registry: Dict[int, Dict[str, Any]] = {}
        self._name_to_id: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Pickle support (struct.Struct is not picklable in Python 3.14+)
    # ------------------------------------------------------------------

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state['_registry'] = {
            type_id: {**type_entry, 'struct': type_entry['struct'].format}
            for type_id, type_entry in state['_registry'].items()
        }
        return state

    def __setstate__(self, state: dict) -> None:
        for type_entry in state['_registry'].values():
            type_entry['struct'] = struct.Struct(type_entry['struct'])
        self.__dict__.update(state)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, buffer) -> None:
        """Scan FMT records from an already-open mmap buffer."""
        self._registry.clear()
        self._name_to_id.clear()
        try:
            offset, scan_end = 0, len(buffer)
            while offset + 3 <= scan_end:
                if buffer[offset] != MSG_HEADER_B0 or buffer[offset + 1] != MSG_HEADER_B1:
                    _log.warning('invalid header at offset %d during FMT scan — stopping', offset)
                    break
                type_id = buffer[offset + 2]
                offset += 3
                if type_id == FMT_TYPE_ID:
                    if offset + FMT_PAYLOAD_LEN > scan_end:
                        raise ValueError(f'truncated FMT record at offset {offset}')
                    fmt_fields = FMT_PAYLOAD_STRUCT.unpack_from(buffer, offset)
                    self._register_type(fmt_fields)
                    offset += FMT_PAYLOAD_LEN
                else:
                    length = self.get_length(type_id)
                    if length is None:
                        _log.warning(
                            'skipping unknown type_id=%d at offset=%d (no FMT definition)',
                            type_id, offset - 3,
                        )
                        next_pos = buffer.find(MSG_HEADER, offset)
                        if next_pos == -1:
                            break
                        offset = next_pos
                        continue
                    offset += length - 3
            if FMT_TYPE_ID not in self._registry:
                self._register_type((
                    FMT_TYPE_ID, FMT_PAYLOAD_LEN + 3,
                    b'FMT\x00',
                    b'BBnNZ' + b'\x00' * 11,
                    b'Type,Length,Name,Format,Columns' + b'\x00' * 33,
                ))
            _log.info('loaded %s  [%d types]', Path(self.file_path).name, len(self._registry))
        except Exception as error:
            _log.error('failed to load FMT records from %s: %s', Path(self.file_path).name, error)
            raise

    def get_id(self, name: str) -> Optional[int]:
        return self._name_to_id.get(name.upper())

    def resolve_type_ids(self, names: Names) -> Optional[Set[int]]:
        if names is None:
            return None
        if isinstance(names, str):
            names = [names]
        type_ids: Set[int] = set()
        for name in names:
            tid = self.get_id(name)
            if tid is None:
                _log.warning('resolve_type_ids: unknown message type %r', name)
            else:
                type_ids.add(tid)
        return type_ids

    def get_entry(self, type_id: int) -> Optional[Dict[str, Any]]:
        return self._registry.get(type_id)

    def get_length(self, type_id: int) -> Optional[int]:
        type_entry = self._registry.get(type_id)
        return type_entry['total_length'] if type_entry else None

    def decode_from(self, buffer, offset: int, type_id: int) -> Optional[Dict[str, Any]]:
        type_entry = self._registry.get(type_id)
        if type_entry is None:
            return None
        try:
            payload_fields = type_entry['struct'].unpack_from(buffer, offset)
        except struct.error as e:
            _log.warning('decode failed for type_id=%d at offset=%d: %s', type_id, offset, e)
            return None
        return self._build_message(type_entry, payload_fields)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register_type(self, fmt_fields: tuple) -> None:
        type_id, total_length, name_raw, fmt_raw, labels_raw = fmt_fields
        name = name_raw.decode('ascii', errors='ignore').strip('\x00')
        raw_fmt = fmt_raw.decode('ascii', errors='ignore')
        fmt_chars = raw_fmt[:raw_fmt.index('\x00')] if '\x00' in raw_fmt else raw_fmt

        if total_length < 3:
            raise ValueError(
                f'FMT type_id={type_id} ({name!r}) has invalid total_length={total_length}'
            )

        labels = [
            label.strip()
            for label in labels_raw.decode('ascii', errors='ignore').strip('\x00').split(',')
            if label.strip()
        ]
        divisors = [FORMAT_DIVISOR.get(c) for c in fmt_chars if c in FORMAT_TO_STRUCT]
        field_fmt_chars = [c for c in fmt_chars if c in FORMAT_TO_STRUCT]

        if len(labels) != len(field_fmt_chars):
            missing_chars = [c for c in fmt_chars if c not in FORMAT_TO_STRUCT]
            _log.debug('FMT %s: unrecognized format chars: %s', name, missing_chars)
            _log.warning(
                'FMT %s (type_id=%d): %d labels but %d format fields — extra fields will be dropped',
                name, type_id, len(labels), len(field_fmt_chars),
            )

        struct_format = '<' + ''.join(FORMAT_TO_STRUCT.get(c, '') for c in fmt_chars)
        parsed_struct = struct.Struct(struct_format)

        self._registry[type_id] = {
            'name': name,
            'total_length': total_length,
            'struct': parsed_struct,
            'labels': labels,
            'divisors': divisors,
            'fmt_chars': field_fmt_chars,
        }
        self._name_to_id[name] = type_id

    def _build_message(self, type_entry: Dict[str, Any], payload_fields: tuple) -> Dict[str, Any]:
        message: Dict[str, Any] = {'_msg_type': type_entry['name']}
        msg_name = type_entry['name']
        for label, value, divisor, fmt_char in zip(
            type_entry['labels'], payload_fields, type_entry['divisors'], type_entry['fmt_chars']
        ):
            if isinstance(value, bytes):
                if fmt_char == 'Z' and msg_name == 'FILE':
                    pass  # pymavlink special case: FILE payload returned as raw bytes
                elif fmt_char == 'a':
                    value = array.array('h', value)
                else:
                    try:
                        value = value.decode('utf-8')
                    except UnicodeDecodeError:
                        value = value.decode('iso-8859-1')
                    null_pos = value.find('\x00')
                    if null_pos != -1:
                        value = value[:null_pos]
            elif divisor is not None:
                value = value / divisor
            message[label] = value
        return message
