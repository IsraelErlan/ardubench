# ardubench

A Python project for parsing ArduPilot `.bin` telemetry log files. Implements five independent parsing strategies — each a self-contained package — so you can compare their speed and choose the right one for your use case.

---

## Project Structure

```
ardubench/
├── .env                        ← log file path (not committed)
├── .env.example
├── requirements.txt
├── tests/
│   └── test_parsers.py         ← pytest suite (34 tests)
└── src/
    └── business_logic/
        ├── main.py             ← runs all parsers
        ├── utils/
        │   └── shared/
        │       ├── _constants.py       ← binary protocol constants
        │       ├── buffer_parser.py    ← core scanning loop (shared by all parsers)
        │       ├── format_manager.py   ← shared FMT scanner & decoder
        │       ├── timestamp_clock.py  ← GPS-based timestamp computation
        │       └── logger.py           ← shared logger factory
        ├── sequential_parser/
        ├── parallel_parser/
        ├── threaded_parser/
        ├── async_parser/
        └── mavlink_parser/
```

Each parser package contains:

| File | Purpose |
|---|---|
| `__init__.py` | Exports the parser class |
| `parser.py` | Orchestrates parsing using the chosen concurrency strategy |
| `workers.py` | Worker function run in a thread/process (not in sequential/mavlink) |
| `main.py` | Standalone benchmark for this parser |

`FormatManager` lives once in `utils/shared/` and is shared by all parsers.

---

## Parsers

### SequentialParser
Single process, single thread. Opens the file once with `mmap`, loads FMT records, then parses from `first_data_offset` to EOF. The simplest implementation and the baseline for comparisons.

```python
from sequential_parser import SequentialParser

parser = SequentialParser('flight.bin')
parser.parse()                   # all messages
parser.parse('GPS')              # one type
parser.parse(['GPS', 'ATT'])     # multiple types
```

### ParallelParser
Opens the file once to load FMT records and compute N byte-range split points (using `mmap.find()`), then spawns N **separate processes** via `ProcessPoolExecutor` — each opens the file independently and decodes its chunk. Fastest option for parsing all messages from large files.

```python
from parallel_parser import ParallelParser

parser = ParallelParser('flight.bin')
parser.parse()                   # all messages — uses os.cpu_count() processes
parser.parse('GPS', n_workers=4) # override worker count
```

### ThreadedParser
Same chunk-split strategy as `ParallelParser` but uses `ThreadPoolExecutor`. The GIL prevents true CPU parallelism, so speed is similar to sequential for CPU-bound work. Threads share the open `mmap` buffer — no per-thread file open needed.

```python
from threaded_parser import ThreadedParser

parser = ThreadedParser('flight.bin')
parser.parse()
parser.parse('GPS', n_threads=8)
```

### AsyncParser
Opens the file once, loads FMT records, then runs the scan inside `asyncio.to_thread` passing the shared buffer — so it never blocks the event loop. The right choice when the parser lives inside an async application (FastAPI, aiohttp, etc.).

```python
from async_parser import AsyncParser

parser = AsyncParser('flight.bin')

# inside an async function:
messages = await parser.parse('GPS')
all_messages = await parser.parse()
```

### MavlinkParser
Uses the [`pymavlink`](https://github.com/ArduPilot/pymavlink) library instead of a custom binary decoder. Useful as a reference implementation to verify correctness and compare speed against the custom parsers.

```python
from mavlink_parser import MavlinkParser

parser = MavlinkParser('flight.bin')
parser.parse()
parser.parse('GPS')
```

---

## How the Binary Format Works

ArduPilot `.bin` files are a stream of binary messages. Every message starts with a 2-byte header (`0xA3 0x95`) followed by a 1-byte type ID and a variable-length payload.

```
[0xA3][0x95][type_id][...payload...]
```

`FMT` messages (type `0x80`) define the schema for every other message type and can appear anywhere in the file:

```
FMT: type_id=130  length=52  name="GPS"  format="QBILLeeEefIBB"  labels="TimeUS,Status,GMS,..."
```

`FormatManager` performs a single full-file scan to collect all `FMT` records, builds a registry of pre-compiled `struct.Struct` objects, and sets `first_data_offset` to the first non-FMT message. Parsers then decode from that offset with `unpack_from` (no slice allocation).

---

## Performance Comparison

Results on a ~400 MB log file (7.6 million messages):

| Parser | `parse()` | `parse('GPS')` |
|---|---|---|
| SequentialParser | ~21s | ~3.2s |
| ParallelParser | ~13s | ~2.9s |
| ThreadedParser | ~22s | ~4.2s |
| AsyncParser | ~20s | ~4.2s |
| MavlinkParser | ~60s | — |

> `ParallelParser` is fastest for all-messages because it distributes CPU work across real processes, bypassing the GIL.
> `ThreadedParser` matches sequential speed because the GIL prevents CPU parallelism for this CPU-bound workload.
> `AsyncParser`'s advantage is non-blocking integration, not raw speed.

---

## Setup

**1. Clone and install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure the log file path**
```bash
cp .env.example .env
# edit .env and set LOG_FILE_PATH to your .bin file
```

**3. Run all benchmarks**
```bash
python src/business_logic/main.py
```

**4. Run a single parser**
```bash
python src/business_logic/sequential_parser/main.py
python src/business_logic/parallel_parser/main.py
python src/business_logic/threaded_parser/main.py
python src/business_logic/async_parser/main.py
python src/business_logic/mavlink_parser/main.py
```

**5. Run the test suite**
```bash
pytest tests/
```

---

## Logging

All parsers log to `stderr` using Python's standard `logging` module. The default level is `INFO`.

```
INFO     utils.shared.format_manager: loaded flight.bin  [180 types, data offset: 15575]
INFO     sequential_parser.parser: parse('GPS') -> 102405 messages
```

To enable debug logs (chunk-level details):
```bash
LOG_LEVEL=DEBUG python src/business_logic/main.py
```
