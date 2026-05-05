# ArduPilot Binary Log Parser

A Python project for parsing ArduPilot `.bin` telemetry log files. Implements five independent parsing strategies — each a self-contained package — so you can compare their speed and choose the right one for your use case.

---

## Project Structure

```
part-b/
├── .env                        ← log file path (not committed)
├── .env.example
├── requirements.txt
└── src/
    └── business_logic/
        ├── main.py             ← runs all parsers
        ├── utils/
        │   └── shared/
        │       ├── _constants.py   ← binary protocol constants
        │       └── logger.py       ← shared logger factory
        ├── sequential_parser/
        ├── parallel_parser/
        ├── threaded_parser/
        ├── asyncio_parser/
        └── mavlink_parser/
```

Each parser package contains:

| File | Purpose |
|---|---|
| `__init__.py` | Exports the parser class |
| `format_manager.py` | Scans FMT records, builds type registry, decodes messages |
| `parser.py` | Orchestrates parsing using the chosen concurrency strategy |
| `workers.py` | Worker function run in a thread/process (not in sequential) |
| `main.py` | Standalone benchmark for this parser |

---

## Parsers

### SequentialParser
Single process, single thread. Reads the file from start to finish with `mmap`. The simplest implementation and the baseline for comparisons.

```python
from sequential_parser import SequentialParser

parser = SequentialParser('flight.bin')
parser.parse()                   # all messages
parser.parse('GPS')              # one type
parser.parse(['GPS', 'ATT'])     # multiple types
```

### ParallelParser
Splits the file into N equal chunks and decodes each chunk in a **separate process** using `ProcessPoolExecutor`. Fastest option for parsing all messages from large files.

```python
from parallel_parser import ParallelParser

parser = ParallelParser('flight.bin')
parser.parse()                   # all messages — uses os.cpu_count() processes
parser.parse('GPS', n_workers=4) # override worker count
```

### ThreadedParser
Same chunk-split strategy as `ParallelParser` but uses `ThreadPoolExecutor`. The GIL prevents true CPU parallelism, so speed is similar to sequential for CPU-bound work. Useful when I/O is the bottleneck (e.g. network-mounted storage).

```python
from threaded_parser import ThreadedParser

parser = ThreadedParser('flight.bin')
parser.parse()
parser.parse('GPS', n_threads=8)
```

### AsyncParser
Runs the file scan inside `asyncio.to_thread`, so it never blocks the event loop. The right choice when the parser lives inside an async application (FastAPI, aiohttp, etc.).

```python
from asyncio_parser import AsyncParser

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

At the beginning of the file there are `FMT` messages (type `0x80`) that define the schema for every other message type:

```
FMT: type_id=130  length=52  name="GPS"  format="QBILLeeEefIBB"  labels="TimeUS,Status,GMS,..."
```

The `FormatManager` scans these `FMT` records first, builds a registry of pre-compiled `struct.Struct` objects, then uses that registry to decode every subsequent message in a single pass with `unpack_from` (no slice allocation).

---

## Performance Comparison

Results on a ~400 MB log file (7.6 million messages):

| Parser | `parse()` | `parse('GPS')` |
|---|---|---|
| SequentialParser | ~20s | ~1.8s |
| ParallelParser | ~11s | ~1.6s |
| ThreadedParser | ~20s | ~1.8s |
| AsyncParser | ~20s | ~1.6s |
| MavlinkParser | — | — |

> `ParallelParser` is fastest for all-messages because it distributes CPU work across real processes.
> `ThreadedParser` matches sequential speed because the GIL prevents CPU parallelism.
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
python src/business_logic/asyncio_parser/main.py
python src/business_logic/mavlink_parser/main.py
```

---

## Logging

All parsers log to `stderr` using Python's standard `logging` module. The default level is `INFO`.

```
INFO     sequential_parser.format_manager: loaded flight.bin  [47 types, data offset: 4450]
INFO     sequential_parser.parser: parse('GPS') → 102405 messages
```

To enable debug logs (chunk-level details):
```bash
LOG_LEVEL=DEBUG python src/business_logic/main.py
```
