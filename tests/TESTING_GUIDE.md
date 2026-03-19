# CN0359 Testing Guide

## Quick Reference -- Run All Tests

```
python -m pytest tests/ -v
```

Expected: **59 passed** (35 parser + 24 handler)

---

## Level 1: Parser Unit Tests (no hardware needed)

**What it tests:** Every edge case of parsing CN0359 sensor responses -- scientific notation, missing fields, garbage data, whitespace, Windows line endings, multi-sensor aggregation, timestamp conversion.

**Run:**
```
python -m pytest tests/test_cn0359_parser.py -v
```

**35 tests covering:**
- Good response parsing (conductivity, temperature, frequency, rzphase)
- Scientific notation variants (1.067e-03, 5.43E+02, 9.99e-07, plain decimals, integers)
- Missing/malformed fields (no conductivity, no temperature, no frequency, empty string, garbage)
- Whitespace edge cases (extra spaces, no trailing newlines, Windows \r\n)
- Multi-sensor parsing (sorted by ID, bad sensors skipped, empty dict)
- Output shape validation (matches DataParser format exactly)
- Timestamp conversion (time-only, full datetime, bad input)

---

## Level 2: Live End-to-End Demo (no hardware needed)

**What it does:** Runs the real CN0359Handler and CN0359Parser production code against 2 fake in-memory sensors. No virtual COM ports or drivers needed. The fake sensors respond to `30 poll\n` with realistic 22-line ASCII responses that drift over time.

**Run:**
```
python tests/live_demo.py
```

**What you'll see:**
```
============================================================
  CN0359 Live End-to-End Demo
  No hardware or virtual COM ports needed
============================================================

Starting handler with 2 fake sensors...
Poll interval: 2s
Press Ctrl+C to stop.

--- Poll #1 at 14:18:35 ---
  Sensor 1:  conductivity = 1.053823e-03 S/cm  |  temp = 25.31 C  |  freq = 10000 Hz
  Sensor 2:  conductivity = 1.084810e-03 S/cm  |  temp = 25.08 C  |  freq = 10000 Hz

--- Poll #2 at 14:18:37 ---
  Sensor 1:  conductivity = 1.040374e-03 S/cm  |  temp = 25.38 C  |  freq = 10000 Hz
  Sensor 2:  conductivity = 1.100072e-03 S/cm  |  temp = 25.09 C  |  freq = 10000 Hz
```

Press **Ctrl+C** to stop.

**How it works:**
- Patches `serial.Serial` with an in-memory fake that responds to poll commands
- Starts the real `CN0359Handler` thread (same production code the app uses)
- Handler polls 2 fake sensors every 2 seconds
- Responses are parsed by the real `CN0359Parser`
- Conductivity and temperature drift randomly to simulate realistic data

**Note:** The file `tests/cn0359_simulator.py` is also available for use with real or virtual COM ports (e.g. with com0com), but `live_demo.py` is the recommended approach since it requires zero setup.

---

## Level 3: Handler Unit Tests (no hardware needed)

**What it tests:** The CN0359Handler thread logic using mock serial ports -- no real COM ports needed.

**Run:**
```
python -m pytest tests/test_cn0359_handler.py -v
```

**24 tests covering:**
- SensorState bookkeeping (initial values, failure tracking)
- Handler initialization (defaults, custom baudrate, custom interval, multi-sensor configs)
- Poll one sensor (successful poll, timeout, partial response, correct command format, abort on stop)
- Poll all sensors (all respond, one fails other succeeds, failure counter increments, success resets counter, closed/null ports skipped)
- Lifecycle (pause/resume, close connection, close with error, write broadcast to all, write bytes)
- Constants (POLL_LINES=22, MAX_CONSECUTIVE_FAILS=5)

---

## Level 4: Manager Demo Script

Here's a step-by-step script for showing your manager (~10 minutes total):

### 1. Show the test suite (2 minutes)

Open a terminal and run:
```
python -m pytest tests/ -v
```

Point out: "59 automated tests cover the parser and handler. All pass."

### 2. Show Teensy backward compatibility (1 minute)

Make sure `enabled = false` in config.ini, launch the app:
```
python main.py
```

Point out: "Original DUT dialog, nothing changed for the existing Teensy workflow."

Close the app.

### 3. Show CN0359 mode (1 minute)

Set `enabled = true` in config.ini, launch:
```
python main.py
```

Point out: "6 sensor rows with configurable addresses. One config flag toggles between old and new."

Close the app.

### 4. Live data demo (3 minutes)

Run the live demo:
```
python tests/live_demo.py
```

Point out:
- "2 fake sensors polling every 2 seconds using the real production code"
- "Conductivity and temperature values drift realistically"
- "This is the exact same handler and parser that will run with real sensors"
- "No hardware or virtual COM ports needed -- the fake serial is patched in-memory"

Let it run for 30 seconds so they can see the data updating, then Ctrl+C.

### 5. Show the change control document (1 minute)

Open `CHANGE_CONTROL_v1_to_v2.md` and scroll through it.

Point out: "Every file change is documented with line numbers, rationale, and risk assessment."

### 6. Show the .exe build (1 minute)

Show the `dist/alyPyAcquisition/` folder and the `.exe` file.

Point out: "The app builds to a standalone executable -- no Python install needed on target machines."

---

## Files in the tests/ folder

| File | Purpose |
|------|---------|
| `test_cn0359_parser.py` | 35 automated parser unit tests |
| `test_cn0359_handler.py` | 24 automated handler unit tests |
| `live_demo.py` | Live end-to-end demo with fake sensors (recommended) |
| `cn0359_simulator.py` | COM port simulator for use with virtual/real serial ports |
| `TESTING_GUIDE.md` | This file |
