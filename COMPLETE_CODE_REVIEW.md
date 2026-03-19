# alyPyAcquisition v1.0.0b -- Complete Code Review
## Master Document: Architecture, Review, Evidence, and Meeting Prep

This is the single, all-in-one document combining every review artifact. Use the table of contents to navigate.

---

## TABLE OF CONTENTS

| Part | Title | What It Is |
|------|-------|-----------|
| **A** | [Fundamentals](#part-a-fundamentals--core-concepts) | Core concepts explained from scratch (threads, signals, serial, Qt) |
| **B** | [File Map](#part-b-the-file-map--every-component) | Every file, what it does, one-sentence descriptions |
| **C** | [Architecture Walkthrough](#part-c-architecture-walkthrough-for-sean) | Step-by-step guided tour of the codebase for the architecture review |
| **D** | [Technical Architecture Details](#part-d-technical-architecture-details) | Detailed technical documentation with code and component layers |
| **E** | [IBP vs DUT Handler Comparison](#part-e-ibp-vs-dut-handler-comparison) | Side-by-side comparison of the two main handlers |
| **F** | [Code Review Findings](#part-f-code-review-findings--what-needs-fixing) | The three issues with actual code and fixes |
| **G** | [Code Evidence](#part-g-code-evidence--every-code-snippet) | Every code snippet referenced in the review, with file paths and line numbers |
| **H** | [Executive Review](#part-h-executive-code-review) | High-density technical review pack with talk tracks and FAQ |
| **I** | [Presentation Script](#part-i-presentation-script--how-to-say-it) | Literal script for presenting the review |
| **J** | [Meeting Prep Notes](#part-j-meeting-prep-notes) | Discussion topics, questions, and desired outcomes |
| **K** | [Audit Table](#part-k-audit-report-table) | One-table summary of all critical improvements |

---

---

# PART A: FUNDAMENTALS -- CORE CONCEPTS

*If you've never seen this code before, start here. Every concept is explained before it's used.*

---

## Concept 1: What is a "Thread"?

Your computer can do multiple things at the same time. Each thing it's doing is called a **thread**.

This app has **one main thread** (the "UI thread") that draws the window, buttons, and graphs. If this thread is busy doing something else, the window freezes -- you can't click anything, nothing updates.

To prevent freezing, heavy work (like talking to hardware over a cable) runs in **separate threads**. These background threads do their work without bothering the window.

**The rule:** The main thread draws the screen. Background threads do the heavy lifting.

---

## Concept 2: What is a "Signal" and a "Slot"?

Threads can't just directly talk to each other -- it's unsafe (imagine two people writing on the same piece of paper at the same time). Instead, they use a messaging system called **Signals and Slots**.

- A **Signal** is like raising your hand and saying "I have something to announce."
- A **Slot** is like someone who was listening and says "Got it, I'll handle that."

Example in this app:
- The DutHandler thread reads data from hardware and **emits a signal**: "Hey, I got new data!"
- The main window has a **slot** (a method) connected to that signal: "Got it, I'll parse and display it."

```python
# The signal is defined in the background thread:
data_received = Signal(str)     # "I will announce a text string"

# The connection is made in the main window:
self.serial_handler.data_received.connect(self.handle_data)
# Translation: "When serial_handler announces data_received, call my handle_data method"
```

**Why this matters:** Signals cross thread boundaries safely. This is the correct way for a background thread to send data to the UI.

---

## Concept 3: What is a "Serial Port" and "Baud Rate"?

The hardware devices (sensors, pumps, etc.) are connected to the computer with **serial cables** (USB adapters that act like old-school COM ports).

To talk to a device, you need:
- **Port**: Which cable (e.g., `COM3`, `COM7`)
- **Baud rate**: How fast to talk (measured in bits per second)

Think of baud rate like language speed. If you talk too fast, the listener misses words. Different devices listen at different speeds:

| Device | Baud Rate | Speed Comparison |
|--------|-----------|-----------------|
| DUT (main sensor) | 115200 | Very fast -- like a native speaker |
| Pump | 19200 | 6x slower -- like speaking carefully |
| Chiller | 4800 | 24x slower -- like spelling out each word |

**Why this matters:** When you send a command to the slow chiller, you need to WAIT before sending the next one. The code has `time.sleep()` delays for this reason -- they're correct. (The problem is WHERE those waits happen, not that they exist.)

---

## Concept 4: What is "Qt" and "PySide6"?

**Qt** (pronounced "cute") is a toolkit for building desktop applications with windows, buttons, text fields, and graphs. **PySide6** is how you use Qt in Python.

Key Qt pieces used in this app:

| Qt Class | What It Is | Plain English |
|----------|-----------|---------------|
| `QApplication` | The app itself | "The program is running" |
| `QMainWindow` | A window with menus and toolbars | The main screen you see |
| `QDialog` | A popup window | A settings box or prompt |
| `QThread` | A background worker | Does work without freezing the window |
| `Signal` | A message broadcaster | "Hey everyone, something happened!" |
| `QTimer` | A repeating alarm clock | "Call this function every X seconds" |
| `QObject` | Base class for Qt things | The foundation everything else builds on |

---

## Concept 5: What is "pyserial"?

`pyserial` is a Python library that lets you talk to devices through serial ports. The main class is `serial.Serial`:

```python
# Open a connection to a device:
connection = serial.Serial(
    port='COM3',          # Which cable
    baudrate=115200,      # How fast to talk
    timeout=10            # Give up after 10 seconds of silence
)

# Send data to the device:
connection.write(b'b')    # Send the byte 'b'

# Read data from the device:
byte = connection.read(1) # Read one byte back
```

---

## Concept 6: What is PyQtGraph?

**PyQtGraph** is a library for drawing fast, live-updating charts inside a Qt window. This app uses it to show conductivity and temperature values changing in real time as data comes in from the hardware.

---

## Glossary of Technical Terms

| Term | Plain English |
|------|--------------|
| `QThread` | A background worker that runs code without freezing the window |
| `Signal` | A message that one piece of code broadcasts to anyone listening |
| `Slot` | A method that receives and handles a Signal |
| `emit` | The act of sending a Signal ("broadcasting the message") |
| `connect` | Wiring a Signal to a Slot ("sign me up to hear that message") |
| `serial.Serial` | A Python object that represents a cable connection to a device |
| `baud rate` | How fast data travels over the cable (bits per second) |
| `COM port` | The name of the serial cable connection (e.g., COM3, COM7) |
| `DUT` | Device Under Test -- the main sensor being calibrated |
| `IBP` | Reference sensor brand (IBP HDU-CDTP) -- used for comparison/calibration |
| `TIC` | Pololu Tic 36v4 -- a stepper motor controller |
| `ticcmd` | Command-line program for controlling TIC motors over USB |
| `protocol` | An automated multi-step test sequence defined in a JSON file |
| `QTimer` | A Qt object that calls a function at regular intervals |
| `event loop` | The heartbeat of a Qt app -- processes clicks, signals, redraws, forever |
| `regex` | Regular expressions -- pattern matching for extracting data from text |
| `CSV` | Comma-Separated Values -- a spreadsheet-like text file format |
| `EEPROM` | Electrically Erasable Programmable Read-Only Memory (on the DUT chip) |
| `RzMag` | Impedance magnitude -- the main measurement value |
| `RzPhase` | Impedance phase angle -- measured alongside magnitude |
| `mS/cm` | Millisiemens per centimeter -- unit of conductivity |
| `parse` | To break a text string into structured pieces (numbers, labels) |
| `decode` | To convert raw bytes into readable text (e.g., UTF-8 decoding) |
| `flush` | To force all buffered data to actually send over the cable |
| `in_waiting` | How many bytes are sitting in the serial port's inbox, ready to read |
| `timeout` | How long to wait for a response before giving up |

---

---

# PART B: THE FILE MAP -- EVERY COMPONENT

---

## The File Map

```
alyPyAcquisition-v1.0.0bMK/
|
|-- main.py                              The front door. Starts everything.
|-- config.ini                           Settings file (baud rates, ports)
|
|-- modes/
|   |-- mode_manager.py                  The traffic cop. Decides which window to open.
|   |-- acquisition_mode.py              THE BIG ONE. The main data collection window.
|   |-- analysis_mode.py                 Offline data analysis window.
|   |-- programming_mode.py              Writes calibration to device memory.
|   |
|   |-- controllers/
|   |   |-- device_controller.py         The middle manager. Coordinates pump, chiller, TIC.
|   |   |-- data_parser.py               The translator. Turns raw text into structured numbers.
|   |   |-- data_manager.py              The filing clerk. Saves data to CSV and keeps it in memory.
|   |
|   |-- hardware/
|   |   |-- dut_handler.py               Talks to the DUT sensor (the main device).
|   |   |-- ibp_reference_handler.py     Talks to the IBP reference sensors.
|   |   |-- syringe_pump_handler.py      Talks to the syringe pump.
|   |   |-- chiller_handler.py           Talks to the chiller (temperature control).
|   |   |-- tic_handler.py              Talks to the TIC stepper motors.
|   |   |-- protocol_handler.py          Runs automated test sequences (protocols).
|   |
|   |-- dialogs/
|   |   |-- syringe_pump_dialog.py       Popup window: pump controls.
|   |   |-- chiller_dialog.py            Popup window: chiller controls.
|   |   |-- tic_dialog.py                Popup window: motor controls.
|   |   |-- protocol_dialog.py           Popup window: run automated protocols.
|   |   |-- app_mode_selector.py         Popup window: choose Acquisition/Analysis/Programming.
|   |
|   |-- utils/
|       |-- config.py                    Loads settings from config.ini into Python variables.
|       |-- graph_widgets.py             Creates and updates the live charts.
```

---

## What each file does -- one sentence each

| File | One-Sentence Job |
|------|-----------------|
| `main.py` | Opens the front door: creates ModeManager and exits when done. |
| `config.ini` | A text file where you set baud rates, COM ports, and timeouts without editing code. |
| `config.py` | Reads `config.ini` and turns it into Python variables like `BAUDRATE = 115200`. |
| `mode_manager.py` | Shows a menu ("Pick a mode"), opens the right window, and loops until you quit. |
| `acquisition_mode.py` | The main screen: connects to hardware, collects data, shows graphs, saves to CSV. |
| `analysis_mode.py` | Loads saved CSV files and calculates calibration coefficients. |
| `programming_mode.py` | Writes calibration coefficients to the device's EEPROM memory. |
| `device_controller.py` | A helper that knows how to start/stop the pump, chiller, and TIC motors. |
| `data_parser.py` | Takes a raw text string from the DUT and extracts numbers (frequency, impedance, phase). |
| `data_manager.py` | Keeps all measurements in memory AND writes them to a CSV file, row by row. |
| `graph_widgets.py` | Creates four live charts (conductivity + temperature for DUT and references) and updates them. |
| `dut_handler.py` | A background thread that polls the DUT sensor every few seconds and emits the response. |
| `ibp_reference_handler.py` | A background thread that reads IBP reference sensors when asked. |
| `syringe_pump_handler.py` | A background thread that sends commands to the syringe pump. |
| `chiller_handler.py` | A background thread that sends commands to the chiller. |
| `tic_handler.py` | A background thread that controls TIC stepper motors via USB. |
| `protocol_handler.py` | Runs a multi-step automated test: step 1 for X minutes, step 2 for Y minutes, etc. |
| `syringe_pump_dialog.py` | A popup where you manually set pump diameter, rate, volume, and click RUN. |
| `chiller_dialog.py` | A popup where you manually set chiller temperature and turn it on/off. |
| `tic_dialog.py` | A popup where you manually control TIC motor speed and direction. |
| `protocol_dialog.py` | A popup where you load a JSON protocol file and click Start to run it automatically. |
| `app_mode_selector.py` | The first popup: "Do you want Acquisition, Analysis, or Programming?" |

---

---

# PART C: ARCHITECTURE WALKTHROUGH FOR SEAN

*Guided tour of the codebase, step by step, showing actual code at every point.*

**Goal of this meeting:** Walk through the architecture of the application. Understand what every piece does, how they connect, and confirm the design is sound before we move toward a v2 that works without the Teensy.

**What this document is:** A guided tour of the codebase, step by step, showing the actual code at every point.

**What this document is NOT:** A bug list. We'll note opportunities for optimization and error handling as we go, but we'll save those for a dedicated follow-up session. Today is about understanding the machine.

---

## 1. THE BIG PICTURE

The app is a **Qt desktop application** written in Python (PySide6). It has three modes:

| Mode | Purpose |
|------|---------|
| **Acquisition** | Real-time data collection from hardware -- this is the core |
| **Analysis** | Load saved data, generate calibration coefficients |
| **Programming** | Write calibration coefficients to device EEPROM |

We're reviewing **Acquisition mode** because that's where all the real-time hardware interaction, threading, and data flow lives. Analysis and Programming are straightforward by comparison.

### The architecture in one sentence:

> A mode manager selects which window to show. The Acquisition window creates background threads for each hardware device. Those threads talk to devices over serial ports and emit Qt Signals. The main window receives those signals, parses the data, stores it in memory and CSV, and updates live graphs.

---

## 2. STARTUP SEQUENCE

### 2a. Entry Point

**File: `main.py` (28 lines -- the entire file)**
```python
from modes.mode_manager import ModeManager

def main():
    try:
        manager = ModeManager()
        exit_code = manager.run()
        sys.exit(exit_code)
    except Exception as e:
        sys.exit(1)

if __name__ == "__main__":
    main()
```

This is the front door. It creates one object (`ModeManager`) and calls `run()`. That's it.

### 2b. ModeManager -- The Application Loop

**File: `modes/mode_manager.py`**

ModeManager owns the `QApplication` (the Qt runtime) and runs a simple loop:

```python
# Lines 84-115
def run(self) -> int:
    while True:
        selected_mode = self._get_next_mode()
        if selected_mode is None:
            break

        if not self._launch_window(selected_mode):
            break

        self.app.exec()

        self._handle_window_closed()

    return 0
```

**Window creation uses a factory pattern:**
```python
# Lines 159-187
def _create_window(self, mode):
    window_factory = {
        AppMode.ACQUISITION: lambda: AcquisitionWindow(production_mode=production_mode),
        AppMode.ANALYSIS: lambda: AnalysisWindow(),
        AppMode.PROGRAMMING: lambda: ProgrammingWindow()
    }

    try:
        window = window_factory[mode]()
        window.setAttribute(Qt.WA_DeleteOnClose)
        return window
    except Exception as e:
        self.logger.error(f"Error creating {mode} window: {e}", exc_info=True)
        return None
```

**Architecture note:** This is clean. Each mode is its own independent window class. ModeManager doesn't know or care what happens inside each window. It just creates, shows, waits for close, repeats.

---

## 3. ACQUISITION WINDOW -- THE HEART OF THE APP

**File: `modes/acquisition_mode.py` (1353 lines)**

### 3a. What It Creates On Startup

```python
# Lines 85-148 (simplified)
class AcquisitionWindow(QMainWindow):

    def __init__(self, production_mode=False):
        super().__init__()

        self.serial_handler = None          # DUT handler (background thread)
        self.ibp_ref1_handler = None        # IBP reference 1 (background thread)
        self.ibp_ref2_handler = None        # IBP reference 2 (background thread)
        self.pump_port = None               # Stored for later
        self.chiller_port = None            # Stored for later
        self.tic_a_serial = None            # TIC A serial number
        self.tic_b_serial = None            # TIC B serial number

        self.pending_ibp_data = {}

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown_display)
        self.countdown_timer.start(100)

        # THE FOUR MANAGERS:
        self.data_manager = DataManager(parent=self)
        self.graph_manager = GraphManager()
        self.control_panel = ControlPanel(parent=self)
        self.device_controller = DeviceController(parent_window=self)

        self.init_ui()
```

**Architecture note:** Good separation of concerns. Each manager does one thing:
- `DataManager` = data
- `GraphManager` = charts
- `ControlPanel` = buttons
- `DeviceController` = hardware coordination

The window itself is the **orchestrator** -- it wires everything together but delegates the actual work.

---

### 3b. The UI Layout

```
+-----------------------------------------------------------------------+
|  Title Bar                                                             |
+-----------------------------------------------------------------------+
|  Control Panel (Play/Pause, New File, Serial Ports, Devices, Timer)   |
+------------------------------------+----------------------------------+
|                                    |                                  |
|  DUT Conductivity Graph (top-left) |  Ref Conductivity Graph (top-R) |
|                                    |                                  |
+------------------------------------+----------------------------------+
|                                    |                                  |
|  DUT Temperature Graph (bot-left)  |  Ref Temperature Graph (bot-R)  |
|                                    |                                  |
+------------------------------------+----------------------------------+
|  System Log (scrolling text showing commands, responses, errors)       |
+-----------------------------------------------------------------------+
```

---

## 4. HARDWARE LAYER -- THE BACKGROUND THREADS

### 4a. Device Inventory

| Device | Handler Class | File | Communication | Baud Rate |
|--------|--------------|------|---------------|-----------|
| DUT (main sensor) | `DutHandler` | `modes/hardware/dut_handler.py` | Serial (pyserial) | 115200 |
| IBP Reference x2 | `IBPReferenceHandler` | `modes/hardware/ibp_reference_handler.py` | Serial (pyserial) | 9600 |
| Syringe Pump | `SyringePumpThread` | `modes/hardware/syringe_pump_handler.py` | Serial (pyserial) | 19200 |
| Chiller | `ChillerThread` | `modes/hardware/chiller_handler.py` | Serial (pyserial) | 4800 |
| TIC Motors x2 | `TicThread` | `modes/hardware/tic_handler.py` | USB (subprocess/ticcmd) | N/A |

All inherit from `QThread`. They all follow the same pattern:
1. Open a connection in `run()`
2. Do their work (poll, send commands, read responses)
3. Emit Qt Signals to announce results
4. Clean up in `stop()`

### 4b. DutHandler -- The Primary Data Source

**File: `modes/hardware/dut_handler.py` (192 lines)**

**Signals it broadcasts:**
```python
class DutHandler(QThread):
    data_received = Signal(str)
    error_occurred = Signal(str)
    disconnected = Signal()
    command_sent = Signal(str)
    response_received = Signal(str, str)
```

**The polling loop:**
```python
def run(self):
    self.serial_connection = serial.Serial(
        port=self.port, baudrate=self.baudrate, timeout=self.timeout
    )
    self.running = True

    while self.running:
        if not self.paused and time_to_poll:
            self.command_sent.emit('b')
            self.serial_connection.write(b'b')
            self.serial_connection.flush()
            time.sleep(0.05)

            data = b''
            while self.running and not self.paused:
                if self.serial_connection.in_waiting > 0:
                    byte = self.serial_connection.read(1)
                    data += byte
                    if byte == b'*':
                        break
                else:
                    time.sleep(0.01)

                if elapsed > READ_TIMEOUT_MAX:
                    self.error_occurred.emit("Read timeout...")
                    break

            decoded = data.rstrip(b'*').decode('utf-8').strip()
            self.data_received.emit(decoded)
```

**Architecture note:** Correct pattern -- all I/O in a thread, results delivered via signals.

---

### 4c. IBPReferenceHandler -- On-Demand Reader

**File: `modes/hardware/ibp_reference_handler.py` (204 lines)**

Unlike DutHandler (which polls on a timer), IBP handlers sit idle and only read when the main window calls `read_data()`. This ensures IBP and DUT readings are time-synchronized.

```python
class IBPReferenceHandler(QThread):
    data_received = Signal(int, float, float)
    error_occurred = Signal(int, str)
    serial_number_received = Signal(int, str)

def run(self):
    self.serial_connection = serial.Serial(port=self.port, baudrate=self.baudrate, ...)
    sn = self.send_command("SYSSNR")

    while self.running:
        time.sleep(0.1)

def read_data(self):
    """Called by the main window when DUT data arrives"""
    response = self.send_command("VALAR")
    parts = response.split('/')
    conductivity = float(parts[0])
    temperature = float(parts[2])
    self.data_received.emit(self.ref_id, conductivity, temperature)
```

**Architecture note:** The "read on demand" pattern keeps IBP and DUT data in the same time window.

---

### 4d. Pump, Chiller, TIC -- Peripheral Handlers

**Syringe Pump** (`SyringePumpThread`, 19200 baud):
- Commands: `VER` (identify), `DIA` (diameter), `DIR` (direction), `RAT` (rate), `VOL` (volume), `RUN`, `STP`

**Chiller** (`ChillerThread`, 4800 baud -- slowest device):
- Commands: `in_pv_00` (read temp), `out_mode_05 1` (start), `out_mode_05 0` (stop), `out_sp_00 X` (set temp)
- Special: 7-bit, even parity serial (unusual settings)

**TIC Motors** (`TicThread`, USB):
- Commands sent via `subprocess.run(['ticcmd', ...])` -- not serial, but USB command-line tool
- Functions: `energize()`, `deenergize()`, `set_velocity()`, `get_status()`

---

## 5. DATA PIPELINE -- FROM RAW BYTES TO GRAPHS

### Step-by-step with file and line references:

```
DutHandler (background thread)
  |
  |  self.serial_connection.write(b'b')        --> dut_handler.py line 70
  |  reads bytes until b'*'                    --> dut_handler.py lines 87-95
  |  self.data_received.emit(decoded_data)     --> dut_handler.py line 129
  |
  v
Qt delivers signal across threads (automatic, thread-safe)
  |
  v
AcquisitionWindow.handle_data(data)            --> acquisition_mode.py line 654
  |
  |  self.ibp_ref1_handler.read_data()         --> acquisition_mode.py line 661
  |  self.ibp_ref2_handler.read_data()         --> acquisition_mode.py line 663
  |
  |  timestamp = datetime.now().strftime(...)   --> acquisition_mode.py line 666
  |
  |  self.parse_and_update(data, timestamp)     --> acquisition_mode.py line 675
  |
  v
AcquisitionWindow.parse_and_update()            --> acquisition_mode.py line 677
  |
  |  parsed = DataParser.parse_all_measurements(data, timestamp)
  |
  |  for unit_data in parsed['dut_units']:
  |      |
  |      |  self.data_manager.add_dut_data(unit_id, time, conductivity, temperature)
  |      |
  |      |  self.graph_manager.update_dut_plots(unit_id, timestamps, cond_values, temp_values)
  |
  |  self.data_manager.write_consolidated_row(timestamp, dut_measurements, ref_measurements)
```

**Architecture note:** This pipeline is clean and linear. Data flows one direction: hardware -> thread -> signal -> parse -> store -> graph. No circular dependencies.

---

## 6. CONTROLLER LAYER -- DeviceController

**File: `modes/controllers/device_controller.py`**

```python
class DeviceController:
    def __init__(self, parent_window):
        self.parent_window = parent_window
        self.pump_port = None
        self.chiller_port = None
        self.tic_a_serial = None
        self.tic_b_serial = None
        self.tic_threads = {'A': None, 'B': None}
```

**Key methods:**

| Method | What It Does |
|--------|-------------|
| `apply_pump_settings(settings)` | Creates a temporary SyringePumpThread, sends DIA/DIR/RAT/VOL/RUN, then stops thread |
| `apply_tic_settings(settings, tic_id)` | Creates or reuses a persistent TicThread, energizes motor, sets velocity |
| `apply_chiller_settings(settings)` | Creates a temporary ChillerThread, sets temperature, starts/stops chiller |
| `stop_all_devices()` | Sends stop commands to every device |

**Two thread management patterns:**

| Pattern | Used For | How It Works |
|---------|---------|-------------|
| **Temporary** | Pump, Chiller | Create thread -> send commands -> destroy thread |
| **Persistent** | TIC Motors | Create once, reuse across protocol steps, destroy at protocol end |

---

## 7. PROTOCOL SYSTEM -- AUTOMATED TESTING

### 7a. ProtocolHandler -- The Timer

**File: `modes/hardware/protocol_handler.py`**

```python
class ProtocolHandler(QObject):
    step_started = Signal(int, object)
    time_remaining = Signal(int)
    step_completed = Signal(int)
    protocol_completed = Signal()
```

ProtocolHandler loads a JSON file, starts a QTimer (1-second ticks), and counts down each step. When a step starts, it emits `step_started`. It does NOT apply device settings itself.

### 7b. ProtocolDialog -- The Connector

```
ProtocolHandler emits step_started(step_num, step)
    |
    v
ProtocolDialog:
    +-- parent_window.unpause()
    +-- parent_window.apply_pump_settings(step.pump)
    +-- parent_window.apply_tic_a_settings(step.tic_a)
    +-- parent_window.apply_tic_b_settings(step.tic_b)
    +-- parent_window.apply_chiller_settings(step.chiller)
```

**Architecture note:** Good separation -- ProtocolHandler only knows about time and steps. ProtocolDialog knows how to translate steps into device commands.

---

## 8. CONFIGURATION SYSTEM

### config.ini (what the operator edits)
```ini
[Serial]
baudrate = 115200
query_interval = 10

[Pump]
baudrate = 19200

[Chiller]
baudrate = 4800
```

### config.py (what the code reads)
```python
BAUDRATE = 115200
PUMP_BAUDRATE = 19200
CHILLER_BAUDRATE = 4800
QUERY_INTERVAL = 10
SAVE_DIRECTORY = "data"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
MAX_GRAPH_POINTS = 1000
```

---

## 9. COMMUNICATION MAP

```
+------------------+          Qt Signals           +--------------------+
|  DutHandler      | --(data_received)-----------> |                    |
|  (QThread)       | --(error_occurred)----------> |                    |
+------------------+                               |                    |
                                                   |  AcquisitionWindow |
+------------------+          Qt Signals           |  (QMainWindow)     |
|  IBPRefHandler   | --(data_received)-----------> |                    |
|  (QThread x2)    | --(error_occurred)----------> |                    |
+------------------+                               |                    |
                                                   |         |          |
                             Direct method calls   |         v          |
                         +-------------------------| DeviceController   |
                         |                         |         |          |
                         v                         +--------------------+
               +-------------------+                         |
               | SyringePumpThread |     DeviceController     |
               | ChillerThread     | <-- creates temporary --+
               | TicThread         |     threads and sends
               +-------------------+     commands via them

+------------------+                    +------------------+
|  ProtocolHandler | --(step_started)-> | ProtocolDialog   |
|  (QObject+QTimer)|                    | calls back to    |
|                  | <-(start/abort)--- | AcquisitionWindow|
+------------------+                    +------------------+
```

**Two communication patterns:**
1. **Signals/Slots** (thread-safe): Hardware threads --> Main window
2. **Direct method calls** (same thread): Main window --> DeviceController --> Hardware threads

---

## 10. THE FULL ARCHITECTURE DIAGRAM

```
                         config.ini
                            |
                         config.py
                            |
                         main.py
                            |
                       ModeManager
                      /     |     \
              Acquisition  Analysis  Programming
                   |
            AcquisitionWindow
           /    |    |    |    \
     Control  Graph  Data   Data    Device
     Panel    Mgr   Parser  Mgr    Controller
       |       |      |      |     /   |    \
    Buttons  4 live  regex  CSV   Pump Chiller TIC
             charts        +RAM
                    |
              DutHandler (QThread, 115200 baud)
              IBPHandler x2 (QThread, 9600 baud)
                    |
              Physical Devices via Serial/USB
```

---

## 11. ARCHITECTURE ASSESSMENT

### What's solid

| Aspect | Assessment |
|--------|-----------|
| **Mode separation** | Clean. Each mode is an independent window. ModeManager is simple. |
| **Thread model for I/O** | Correct. All serial communication runs in QThread subclasses. |
| **Signal/Slot for cross-thread** | Correct. Data moves from hardware threads to UI via Qt signals. Thread-safe by design. |
| **Data pipeline** | Linear and clean. Hardware -> Parse -> Store -> Graph. No circular dependencies. |
| **DataParser** | Stateless (static methods). Easy to test. Does one thing. |
| **DataManager** | Single responsibility. Owns both in-memory storage and CSV writing. |
| **GraphManager** | Clean abstraction. The window calls `update_plots()`. |
| **Protocol system** | Good separation between timing (ProtocolHandler) and device application (ProtocolDialog + DeviceController). |
| **Configuration** | Centralized in config.ini/config.py. Baud rates and ports aren't scattered. |
| **IBP time-sync** | Smart design. IBP reads are triggered by DUT data arrival. |

### What we should improve for v2

| Area | What We'd Improve | Why It Matters for v2 |
|------|-------------------|----------------------|
| **Error handling consistency** | DUT init isn't guarded like IBP is. Standardize the try/except pattern. | v2 may have different hardware with different failure modes. |
| **Thread placement of delays** | Some `time.sleep()` calls run on the GUI thread. Move them into worker threads. | v2 should have zero UI freezing. |
| **Protocol constants** | Serial commands are hardcoded strings. Centralize them. | v2 with new hardware will have different commands. |
| **Abstract handler interface** | DutHandler and IBPHandler share no base class. Define a `BaseHandler` ABC. | v2 can swap in mock handlers for testing. |
| **DeviceController threading** | Currently runs on the GUI thread. Could own its own worker thread. | Eliminates all UI-blocking device coordination. |

> **The bottom line:** The architecture is sound. The separation of concerns is good. The threading model for I/O is correct. The data pipeline is clean and linear. The improvements above are **polish and hardening**, not fundamental redesigns.

---

## 12. NEXT STEPS

1. **Today:** Confirm we're aligned on how the architecture works and that the design is sound for building v2 on top of.
2. **Next session:** Deep dive into the specific optimization and error handling improvements.
3. **v2 planning:** Apply these improvements alongside the hardware changes.

*The architecture is good. Let's make it bulletproof for v2.*

---

---

# PART D: TECHNICAL ARCHITECTURE DETAILS

*Detailed technical documentation with component layers and code.*

---

## Component Layers

```
+-------------------------------------------------------------+
|                    Application Layer                          |
|  main.py -> ModeManager -> Mode Windows (QMainWindow)        |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
|                    Controller Layer                           |
|  DeviceController, DataManager, DataParser, GraphManager     |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
|                    Hardware Layer (QThread)                   |
|  DutHandler, IBPReferenceHandler, SyringePumpThread, etc.    |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
|                    Serial I/O Layer                           |
|  pyserial -> Physical Hardware (DUT, IBP, Pump, Chiller)     |
+-------------------------------------------------------------+
```

---

## Production Mode Manager

**Lines 240-353 of `modes/mode_manager.py`:**
```python
class ProductionModeManager:
    PHASES = [AppMode.ACQUISITION, AppMode.ANALYSIS, AppMode.PROGRAMMING]

    def start(self) -> None:
        self.active = True
        self.current_phase_index = 0

    def advance(self) -> bool:
        self.current_phase_index += 1
        if self.current_phase_index >= len(self.PHASES):
            self.reset()
            return False
        return True
```

**Workflow:** User selects "Production Mode" -> Acquisition -> Analysis -> Programming sequentially, each phase auto-launching after the previous one closes.

---

## Data Parsing -- DataParser

**File: `modes/controllers/data_parser.py`**

**Input (what the DUT sends):**
```
Selected Unit: 2 | Reset Pin: 22 | Interrupt Pin: 21
Freq: 10000.00 Hz DataPoints: 1 RzMag: 1017.36 Ohm, RzPhase: -0.01 deg;
Freq: 0.01 Hz RzMag: 1000.88 Ohm, RzPhase: 0.0 deg
```

**Output (what DataParser returns):**
```python
{
    'timestamp': 1707666000.123,
    'dut_units': [
        {
            'unit_id': 2,
            'conductivity': {
                'frequency': 10000.00,
                'rzmag': 1017.36,
                'rzphase': -0.01
            },
            'temperature': {
                'frequency': 0.01,
                'rzmag': 1000.88,
                'rzphase': 0.0
            }
        }
    ],
    'reference_devices': [ ... ]
}
```

**Key methods:**
- `parse_dut_units(data)` -- finds "Selected Unit: X" blocks and extracts numbers
- `parse_reference_devices(data)` -- finds reference device data
- `parse_all_measurements(data, timestamp)` -- calls both, returns everything

---

## Data Storage -- DataManager

**File: `modes/controllers/data_manager.py`**

**What it stores in memory:**
```python
unit_data[unit_id] = {
    'timestamps': [1707666000.1, 1707666010.2, ...],
    'conductivity_rzmag': [1017.36, 1018.12, ...],
    'temperature_rzmag': [1000.88, 1001.02, ...],
    'conductivity_freq': [...],
    'conductivity_rzphase': [...],
    'temperature_freq': [...],
    'temperature_rzphase': [...]
}
```

**Key methods:**
- `setup_save_files()` -- creates a timestamped folder and opens CSV + log files
- `add_dut_data(unit_id, timestamp, conductivity, temperature)` -- stores one data point
- `write_consolidated_row(timestamp, dut_measurements, ref_measurements)` -- writes one CSV row
- `create_new_files()` -- starts a new CSV file
- `close_files()` -- closes everything when the window shuts down

---

## Graph Updates -- GraphManager

**File: `modes/utils/graph_widgets.py`**

```
+---------------------------+---------------------------+
|  DUT Conductivity (top L) |  Ref Conductivity (top R) |
|  Y: mS/cm  X: time       |  Y: mS/cm  X: time       |
+---------------------------+---------------------------+
|  DUT Temperature (bot L)  |  Ref Temperature (bot R)  |
|  Y: degrees  X: time     |  Y: degrees  X: time     |
+---------------------------+---------------------------+
```

Each chart can show up to 6 DUT lines (color-coded) or 2 reference lines.

---

## Key Architectural Decisions

### Baud Rate-Driven Timing (Important Context)

| Device | Baud Rate | Wire Time per 10 Bytes | Typical Sleep |
|--------|-----------|----------------------|---------------|
| DUT | 115200 | ~0.9 ms | 0.05 s |
| Pump | 19200 | ~5.2 ms | 0.1 s |
| Chiller | **4800** | **~21 ms** | 0.1-0.2 s |
| TIC | USB (ticcmd) | N/A (subprocess) | 0.1-0.3 s |

At 4800 baud (chiller), one character takes ~2.1 ms. The developer added sleeps because slower devices genuinely need time. **The sleep durations are hardware-correct. The issue is they execute on the GUI thread instead of inside the handler threads.**

---

---

# PART E: IBP VS DUT HANDLER COMPARISON

*Side-by-side comparison -- what's the same, what's different, and why.*

---

## Before We Start: What Are These Two Things?

Both `DutHandler` and `IBPReferenceHandler` are **background workers** that talk to physical sensors through serial cables.

| | DutHandler | IBPReferenceHandler |
|--|-----------|-------------------|
| **What device it talks to** | The DUT -- the main sensor being tested | IBP reference sensors -- known-good sensors used for comparison |
| **How many** | 1 | 2 (ref #1 and ref #2) |
| **File** | `modes/hardware/dut_handler.py` (192 lines) | `modes/hardware/ibp_reference_handler.py` (204 lines) |

---

## WHAT THEY HAVE IN COMMON

### Both Are QThread Subclasses

```python
class DutHandler(QThread):          class IBPReferenceHandler(QThread):
```

### Both Open a Serial Port in run()

**DutHandler:**
```python
def run(self):
    self.serial_connection = serial.Serial(
        port=self.port,
        baudrate=self.baudrate,      # 115200
        timeout=self.timeout
    )
```

**IBPReferenceHandler:**
```python
def run(self):
    self.serial_connection = serial.Serial(
        port=self.port,
        baudrate=self.baudrate,      # 9600
        timeout=self.timeout,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE
    )
```

### Both Broadcast Messages via Signals

**DutHandler signals:**
```python
data_received = Signal(str)
error_occurred = Signal(str)
disconnected = Signal()
command_sent = Signal(str)
response_received = Signal(str, str)
```

**IBPReferenceHandler signals:**
```python
data_received = Signal(int, float, float)   # ref_id + 2 numbers
error_occurred = Signal(int, str)
disconnected = Signal(int)
command_sent = Signal(int, str)
response_received = Signal(int, str, str)
serial_number_received = Signal(int, str)   # IBP only
```

**Differences:**
1. IBP adds `ref_id` to every signal (because there are 2 IBP sensors)
2. IBP's `data_received` sends pre-parsed numbers; DUT sends raw text
3. IBP has an extra signal (`serial_number_received`)

### Identical Lifecycle Methods

```python
# Both are literally identical:
def stop(self):
    self.running = False
    self.wait()

def pause(self):
    self.paused = True

def resume(self):
    self.paused = False

def close_connection(self):
    if self.serial_connection and self.serial_connection.is_open:
        self.serial_connection.close()
```

### Both Use a finally Block for Cleanup

Both ensure the serial port gets closed even if something crashes:
```python
def run(self):
    try:
        # ... open port, do work ...
    except serial.SerialException as e:
        self.error_occurred.emit(...)
    finally:
        self.close_connection()    # ALWAYS close the port
```

---

## WHAT MAKES THEM DIFFERENT

### Difference 1: WHO Decides When to Read

**DutHandler: Self-driven (internal timer)**
```python
while self.running:
    if not self.paused and current_time - last_query_time >= self.query_interval:
        self.serial_connection.write(b'b')
        # ... read response ...
```

**IBPReferenceHandler: Externally triggered (on-demand)**
```python
while self.running:
    time.sleep(0.1)     # Just sit here and wait

def read_data(self):
    """Called by the main window when DUT data arrives"""
    response = self.send_command("VALAR")
```

**WHY:** DUT is the primary data source. IBP sensors read at the exact moment DUT data arrives for time-alignment.

### Difference 2: HOW They Send Commands

**DutHandler:** Single raw byte, reads until `b'*'`
```python
self.serial_connection.write(b'b')
while self.running:
    byte = self.serial_connection.read(1)
    if byte == b'*': break
decoded = data.rstrip(b'*').decode('utf-8')
```

**IBPReferenceHandler:** Text command with carriage return
```python
def send_command(self, command):
    full_command = (command + '\r').encode('ascii')
    self.serial_connection.write(full_command)
    response = b''
    while time.time() - start_time < timeout:
        byte = self.serial_connection.read(1)
        if byte == b'\r': break
        response += byte
    return response.decode('ascii').strip()
```

### Difference 3: WHAT Data They Return

- **DUT:** Raw text string -> main window's `DataParser` extracts numbers
- **IBP:** Pre-parsed numbers (conductivity, temperature) -> emits clean values

### Difference 4: Startup Handshake

- **DUT:** Opens port, starts polling immediately. No handshake.
- **IBP:** Opens port, asks `"SYSSNR"` for serial number, then waits.

### Difference 5: Timeout System

- **DUT:** Two-layer (overall max + idle timeout)
- **IBP:** Simple single 2-second timeout

---

## Summary Table

| Feature | DutHandler | IBPReferenceHandler |
|---------|-----------|-------------------|
| **Baud rate** | 115200 (fast) | 9600 (moderate) |
| **Polling model** | Self-driven (internal timer) | On-demand (`read_data()` calls) |
| **Poll command** | `b'b'` (raw byte) | `"VALAR"` (ASCII text + CR) |
| **Message terminator** | `b'*'` (star) | `b'\r'` (carriage return) |
| **Has `send_command()`** | No | Yes |
| **Startup handshake** | None | Reads serial number |
| **Data format emitted** | Raw text string | Pre-parsed numbers |
| **Signal includes ref_id** | No (only one DUT) | Yes |
| **Timeout system** | Two-layer | Simple single |
| **Encoding** | UTF-8 (with latin-1 fallback) | ASCII only |
| **Error handling at init** | No try/except in caller | Wrapped in try/except |

---

---

# PART F: CODE REVIEW FINDINGS -- WHAT NEEDS FIXING

*The three categories of issues with actual code and fixes.*

---

## FIX #1: DUT INITIALIZATION CAN CRASH THE APP

### The broken code

**File: `modes/acquisition_mode.py` (Lines 500-516) -- NO try/except**
```python
    if dut_port:
        self.serial_handler = DutHandler(
            port=dut_port,
            baudrate=config.BAUDRATE,
            timeout=config.TIMEOUT,
            query_interval=config.QUERY_INTERVAL
        )
        self.serial_handler.data_received.connect(self.handle_data)
        self.serial_handler.error_occurred.connect(self.handle_error)
        self.serial_handler.disconnected.connect(self.handle_disconnection)
        self.serial_handler.command_sent.connect(self.handle_serial_command)
        self.serial_handler.response_received.connect(self.handle_serial_response)
        self.serial_handler.start()
        self.serial_handler.pause()
```

### The correct pattern already exists for IBP (same file, 80 lines later)

**File: `modes/acquisition_mode.py` (Lines 593-619) -- HAS try/except**
```python
    if ref1_port:
        try:
            self.ibp_ref1_handler = IBPReferenceHandler(
                ref_id=1,
                port=ref1_port,
                baudrate=config.IBP_BAUDRATE,
                timeout=config.IBP_TIMEOUT
            )
            # ... signal connections ...
            self.ibp_ref1_handler.start()

            self.log_event(f"IBP Reference 1 connecting: {ref1_port}", ...)
        except Exception as e:
            self.log_event(f"Failed to start IBP Reference 1: {str(e)}", ...)
```

### What to do
Copy the IBP pattern to DUT. Wrap lines 502-516 in `try/except`. Log the error. Set `self.serial_handler = None`. Let the window stay open.

**Effort: ~5 lines of code. Highest priority fix.**

---

## FIX #2: THE UI FREEZES BECAUSE OF time.sleep ON THE WRONG THREAD

### Why the sleeps exist (important context)

The developer added them because **slower devices genuinely need processing time.** At 4800 baud (chiller), a 10-byte command takes ~21 ms just to transmit. You NEED to wait. **The sleep durations are correct. The bug is that they run on the UI thread instead of in a background thread.**

### Every location that freezes the UI

#### LOCATION 1: Stopping all devices (0.1 s)
**File: `modes/acquisition_mode.py` (Lines 1304-1323)**
```python
def stop_all_devices(self):
    self.device_controller.stop_all_devices()
    import time
    time.sleep(0.1)      # UI FROZEN
```

#### LOCATION 2: Running the pump (0.4 s)
**File: `modes/dialogs/syringe_pump_dialog.py` (Lines 395-424)**
```python
def run_pump(self):
    self.pump_thread.send_command(f"DIA {diameter}")
    time.sleep(0.1)       # UI FROZEN
    self.pump_thread.send_command(f"DIR {direction}")
    time.sleep(0.1)       # UI FROZEN
    self.pump_thread.send_command(f"RAT {rate} {self.rate_units}")
    time.sleep(0.1)       # UI FROZEN
    self.pump_thread.send_command(f"VOL {volume}")
    time.sleep(0.1)       # UI FROZEN
    self.pump_thread.send_command("RUN")
    # TOTAL: 0.4 seconds of frozen dialog
```

#### LOCATION 3: Closing TIC dialog (0.2-0.4 s)
**File: `modes/dialogs/tic_dialog.py` (Lines 753-769)**
```python
def closeEvent(self, event):
    for tic_id in ['A', 'B']:
        if self.tic_threads[tic_id] and self.tic_threads[tic_id].isRunning():
            self.tic_threads[tic_id].set_velocity(0)
            time.sleep(0.2)   # UI FROZEN per motor
```

#### LOCATION 4: DeviceController applying pump settings during protocol
**File: `modes/controllers/device_controller.py` (Lines 89-127)**
```python
def apply_pump_settings(self, settings):
    pump_thread.send_command(f"DIA {settings['diameter']}")
    time.sleep(0.1)       # UI FROZEN
    pump_thread.send_command(f"DIR {settings['direction']}")
    time.sleep(0.1)       # UI FROZEN
    pump_thread.send_command(f"RAT {settings['rate']} {PUMP_RATE_UNITS}")
    time.sleep(0.1)       # UI FROZEN
    pump_thread.send_command(f"VOL {settings['volume']}")
    time.sleep(0.1)       # UI FROZEN
```

#### LOCATION 5: DeviceController applying TIC settings
**File: `modes/controllers/device_controller.py` (Lines 150-185)**
```python
def apply_tic_settings(self, settings, tic_id='A'):
    if self.tic_threads[tic_id] is None:
        self.tic_threads[tic_id] = TicThread(tic_serial)
        self.tic_threads[tic_id].start()
        time.sleep(0.3)       # UI FROZEN
    tic_thread.energize()
    time.sleep(0.15)          # UI FROZEN
    tic_thread.set_velocity(velocity)
    time.sleep(0.1)           # UI FROZEN
```

#### LOCATION 6: DeviceController stop_all_devices
**File: `modes/controllers/device_controller.py` (Lines 326-428)**
```python
def stop_all_devices(self):
    pump_thread.send_command("STP")
    time.sleep(0.1)            # UI FROZEN
    chiller_thread.stop_chiller()
    time.sleep(0.1)            # UI FROZEN
    tic_thread.set_velocity(0)
    time.sleep(0.1)            # UI FROZEN
    tic_thread.deenergize()
    time.sleep(0.1)            # UI FROZEN
    # ... same for TIC B
```

#### WORST CASE: Protocol step transition
```
apply_pump_settings()    -->  ~0.4 s frozen
apply_tic_settings('A')  -->  ~0.55 s frozen
apply_tic_settings('B')  -->  ~0.55 s frozen
apply_chiller_settings() -->  ~0.2 s frozen
----------------------------------------------
TOTAL:                        ~1.7 SECONDS OF UI FREEZE

On Windows, 500 ms is enough for the "Not Responding" title bar to appear.
```

### What to do
**Rule: Zero `time.sleep()` on the UI thread.** Keep the exact same delay durations but move them into background threads. The UI asks the thread to do the work. The thread signals back "done."

---

## FIX #3: HARDCODED SERIAL COMMANDS ("MAGIC STRINGS")

### Every hardcoded string in the codebase

| Device | Baud Rate | String | File | Line | Usage |
|--------|-----------|--------|------|------|-------|
| DUT | 115200 | `b'b'` | dut_handler.py | 70 | Poll command |
| DUT | 115200 | `b'*'` | dut_handler.py | 94, 125, 133 | Termination character |
| DUT | 115200 | `'*'` | dut_handler.py | 117 | Error message string |
| Pump | 19200 | `"VER"` | syringe_pump_handler.py | 65 | Identify device |
| IBP | 9600 | `"SYSSNR"` | ibp_reference_handler.py | 61 | Read serial number |
| IBP | 9600 | `"VALAR"` | ibp_reference_handler.py | 90, 93 | Read measurements |
| Chiller | **4800** | `"in_pv_00"` | chiller_handler.py | 129 | Read temperature |
| Chiller | **4800** | `"out_mode_05 1"` | chiller_handler.py | 148 | Start chiller |
| Chiller | **4800** | `"out_mode_05 0"` | chiller_handler.py | 162 | Stop chiller |

### What to do
Create one constants file per device:
```python
# dut_protocol.py
DUT_CMD_POLL = b'b'
DUT_TERMINATOR = b'*'

# ibp_protocol.py
IBP_CMD_READ_SN = "SYSSNR"
IBP_CMD_READ_VALUES = "VALAR"

# chiller_protocol.py
CHILLER_CMD_READ_TEMP = "in_pv_00"
CHILLER_CMD_START = "out_mode_05 1"
CHILLER_CMD_STOP = "out_mode_05 0"

# pump_protocol.py
PUMP_CMD_IDENTIFY = "VER"
```

---

## PRIORITY ORDER

| Priority | Fix | Effort | Impact | Why This Order |
|----------|-----|--------|--------|---------------|
| **1** | Guard DUT init with try/except | ~5 lines | Prevents crashes | Smallest change, biggest safety win |
| **2** | Constants for serial commands | ~4 small files + find-replace | Prevents silent bugs | Touches every handler, easy to verify |
| **3** | Move sleeps to worker threads | Architectural refactor | Fixes UI freezing | Most complex, but UI already "works" |

---

---

# PART G: CODE EVIDENCE -- EVERY CODE SNIPPET

*Every code snippet referenced in the review, with file paths and line numbers.*

---

## The Outer Shell

**File: `main.py` (Lines 1-28)**
```python
import sys
from modes.utils import qt_opengl_shim
from modes.mode_manager import ModeManager

def main():
    try:
        manager = ModeManager()
        exit_code = manager.run()
        sys.exit(exit_code)
    except Exception as e:
        sys.exit(1)            # <-- No logging on crash
```

---

## DutHandler Sends `b'b'` and Reads Until `b'*'`

**File: `modes/hardware/dut_handler.py` (Lines 20-27) -- Class definition**
```python
class DutHandler(QThread):
    """Thread-based serial port handler"""
    data_received = Signal(str)
    error_occurred = Signal(str)
    disconnected = Signal()
    command_sent = Signal(str)
    response_received = Signal(str, str)
```

**File: `modes/hardware/dut_handler.py` (Lines 66-75) -- The poll command**
```python
    if not self.paused and current_time - last_query_time >= self.query_interval:
        self.command_sent.emit('b')
        self.serial_connection.write(b'b')       # <-- HARDCODED poll command
        self.serial_connection.flush()
        last_query_time = current_time
        time.sleep(0.05)                         # 50 ms wait (in thread -- safe)
```

**File: `modes/hardware/dut_handler.py` (Lines 87-95) -- Reading until terminator**
```python
        while self.running and not self.paused:
            if self.serial_connection.in_waiting > 0:
                byte = self.serial_connection.read(1)
                data += byte
                last_data_time = time.time()
                if byte == b'*':                 # <-- HARDCODED terminator
                    break
```

**File: `modes/hardware/dut_handler.py` (Lines 122-129) -- Decode and emit**
```python
        if data:
            try:
                decoded_data = data.rstrip(b'*').decode('utf-8').strip()
                if decoded_data:
                    self.response_received.emit('b', decoded_data)
                    self.data_received.emit(decoded_data)   # <-- Signal crosses to UI
```

---

## Signal/Slot Wiring

**File: `modes/acquisition_mode.py` (Lines 508-512)**
```python
    self.serial_handler.data_received.connect(self.handle_data)
    self.serial_handler.error_occurred.connect(self.handle_error)
    self.serial_handler.disconnected.connect(self.handle_disconnection)
    self.serial_handler.command_sent.connect(self.handle_serial_command)
    self.serial_handler.response_received.connect(self.handle_serial_response)
```

---

## handle_data Triggers Everything

**File: `modes/acquisition_mode.py` (Lines 654-675)**
```python
def handle_data(self, data):
    self.last_query_time = time.time()
    self.query_count += 1

    if self.ibp_ref1_handler and not self.is_paused:
        self.ibp_ref1_handler.read_data()            # <-- Blocks main thread for IBP round-trip
    if self.ibp_ref2_handler and not self.is_paused:
        self.ibp_ref2_handler.read_data()            # <-- Blocks main thread for IBP round-trip

    timestamp = datetime.now().strftime(config.TIMESTAMP_FORMAT)
    if ".%f" in config.TIMESTAMP_FORMAT:
        timestamp = timestamp[:-3]

    self.parse_and_update(data, timestamp)
```

---

## parse_and_update Does the Actual Work

**File: `modes/acquisition_mode.py` (Lines 677-715)**
```python
def parse_and_update(self, data, timestamp):
    try:
        parsed = DataParser.parse_all_measurements(data, timestamp)
        time_seconds = parsed['timestamp']

        for unit_data in parsed['dut_units']:
            unit_id = unit_data['unit_id']
            conductivity = unit_data['conductivity']
            temperature = unit_data['temperature']

            self.data_manager.add_dut_data(
                unit_id, time_seconds, conductivity, temperature
            )

            stored_data = self.data_manager.get_dut_data(unit_id)
            self.graph_manager.update_dut_plots(
                unit_id,
                stored_data['timestamps'],
                stored_data['conductivity_rzmag'],
                stored_data['temperature_rzmag']
            )
```

---

## IBP Sync: read_data Sends "VALAR"

**File: `modes/hardware/ibp_reference_handler.py` (Lines 88-98)**
```python
def read_data(self):
    if not self.running:
        return

    try:
        self.command_sent.emit(self.ref_id, "VALAR")     # <-- HARDCODED command
        response = self.send_command("VALAR")             # <-- HARDCODED command (again)

        if response and response != "99":                 # <-- HARDCODED sentinel value
            parts = response.split('/')
            if len(parts) == 3:
                # ... parse conductivity and temperature
```

---

## DUT Init -- No try/except (THE PROBLEM)

**File: `modes/acquisition_mode.py` (Lines 500-516)**
```python
    if dut_port:
        self.serial_handler = DutHandler(            # <-- NO try/except
            port=dut_port,
            baudrate=config.BAUDRATE,
            timeout=config.TIMEOUT,
            query_interval=config.QUERY_INTERVAL
        )
        self.serial_handler.data_received.connect(self.handle_data)
        self.serial_handler.error_occurred.connect(self.handle_error)
        self.serial_handler.disconnected.connect(self.handle_disconnection)
        self.serial_handler.command_sent.connect(self.handle_serial_command)
        self.serial_handler.response_received.connect(self.handle_serial_response)
        self.serial_handler.start()
        self.serial_handler.pause()
```

**Compare: IBP Init (Lines 593-619) -- HAS try/except**
```python
    if ref1_port:
        try:                                         # <-- HAS try/except
            self.ibp_ref1_handler = IBPReferenceHandler(
                ref_id=1,
                port=ref1_port,
                baudrate=config.IBP_BAUDRATE,
                timeout=config.IBP_TIMEOUT
            )
            # ... signal connections ...
            self.ibp_ref1_handler.start()
            self.log_event(f"IBP Reference 1 connecting: {ref1_port}", ...)
        except Exception as e:                       # <-- CATCHES failure
            self.log_event(f"Failed to start IBP Reference 1: {str(e)}", ...)
```

---

## UI-Blocking Sleeps -- DeviceController

**File: `modes/controllers/device_controller.py` (Lines 89-127) -- Pump**
```python
def apply_pump_settings(self, settings):
    pump_thread = SyringePumpThread(self.pump_port, baudrate=PUMP_BAUDRATE)
    pump_thread.start()
    pump_thread.wait(500)

    if 'diameter' in settings:
        pump_thread.send_command(f"DIA {settings['diameter']}")
        time.sleep(0.1)                           # <-- BLOCKS GUI

    if 'direction' in settings:
        pump_thread.send_command(f"DIR {settings['direction']}")
        time.sleep(0.1)                           # <-- BLOCKS GUI

    if 'rate' in settings:
        pump_thread.send_command(f"RAT {settings['rate']} {PUMP_RATE_UNITS}")
        time.sleep(0.1)                           # <-- BLOCKS GUI

    if 'volume' in settings:
        pump_thread.send_command(f"VOL {settings['volume']}")
        time.sleep(0.1)                           # <-- BLOCKS GUI
```

**File: `modes/controllers/device_controller.py` (Lines 132-191) -- TIC**
```python
def apply_tic_settings(self, settings, tic_id='A'):
    if self.tic_threads[tic_id] is None or not self.tic_threads[tic_id].isRunning():
        self.tic_threads[tic_id] = TicThread(tic_serial)
        self.tic_threads[tic_id].start()
        time.sleep(0.3)                           # <-- BLOCKS GUI

    if 'energize' in settings:
        if settings['energize']:
            tic_thread.energize()
            time.sleep(0.15)                      # <-- BLOCKS GUI
        else:
            tic_thread.deenergize()
            time.sleep(0.1)                       # <-- BLOCKS GUI

    if 'velocity' in settings:
        tic_thread.set_velocity(velocity)
        time.sleep(0.1)                           # <-- BLOCKS GUI
```

---

## Hardcoded Strings -- Complete Table

| Line | Code | What It Is |
|------|------|-----------|
| dut_handler.py:70 | `self.serial_connection.write(b'b')` | Poll command |
| dut_handler.py:94 | `if byte == b'*':` | Termination check |
| dut_handler.py:117 | `f"...missing termination character '*'."` | Error message |
| dut_handler.py:125 | `data.rstrip(b'*').decode('utf-8')` | Strip terminator |
| dut_handler.py:133 | `data.rstrip(b'*').decode('latin-1')` | Strip terminator (fallback) |
| syringe_pump_handler.py:65 | `response = self.send_command("VER")` | Device ID |
| ibp_reference_handler.py:61 | `sn = self.send_command("SYSSNR")` | Read serial number |
| ibp_reference_handler.py:90 | `self.command_sent.emit(self.ref_id, "VALAR")` | Log VALAR |
| ibp_reference_handler.py:93 | `response = self.send_command("VALAR")` | Read measurements |
| chiller_handler.py:129 | `response = self.send_command("in_pv_00")` | Read temperature |
| chiller_handler.py:148 | `response = self.send_command("out_mode_05 1")` | Start chiller |
| chiller_handler.py:162 | `response = self.send_command("out_mode_05 0")` | Stop chiller |

---

## What Constants Would Replace

Instead of scattered literals:
```python
self.serial_connection.write(b'b')       # dut_handler.py:70
if byte == b'*':                         # dut_handler.py:94
self.send_command("SYSSNR")              # ibp_reference_handler.py:61
self.send_command("out_mode_05 1")       # chiller_handler.py:148
```

You'd have:
```python
# dut_protocol.py
DUT_CMD_POLL = b'b'
DUT_TERMINATOR = b'*'

# ibp_protocol.py
IBP_CMD_READ_SN = "SYSSNR"
IBP_CMD_READ_VALUES = "VALAR"

# chiller_protocol.py
CHILLER_CMD_READ_TEMP = "in_pv_00"
CHILLER_CMD_START = "out_mode_05 1"
CHILLER_CMD_STOP = "out_mode_05 0"
```

---

---

# PART H: EXECUTIVE CODE REVIEW

*High-density technical review pack for the meeting. Talk tracks and FAQ.*

---

## 1. The Architecture: Data Pipeline

### End-to-End Flow

| Stage | Component | Mechanism | Responsibility |
|-------|-----------|-----------|----------------|
| 1. Hardware I/O | `DutHandler` (QThread) | Serial write `b'b'`, read until `b'*'` | Poll DUT at `query_interval`; decode UTF-8 |
| 2. Cross-thread | Qt Signal | `data_received.emit(str)` | Thread-safe delivery to main thread |
| 3. Slot (main thread) | `AcquisitionWindow.handle_data(data)` | Connected to `data_received` | Timestamp; trigger IBP reads; call `parse_and_update` |
| 4. Parse | `DataParser.parse_all_measurements` | Static method, regex-based | Split by "Selected Unit:"; extract Freq/RzMag/RzPhase |
| 5. Store | `DataManager.add_dut_data` | In-memory lists | Append to unit_data[unit_id] |
| 6. Persist | `DataManager.write_consolidated_row` | CSV write | One row per sample; DUT + refs aligned |
| 7. Visualize | `GraphManager.update_dut_plots` | PyQtGraph setData | Plot conductivity and temperature vs time |

### IBP Synchronization

When DUT data arrives, `handle_data` synchronously calls `ibp_ref1_handler.read_data()` and `ibp_ref2_handler.read_data()`. IBP results are stored in `pending_ibp_data` and merged into the next consolidated CSV row. So IBP and DUT are time-aligned at the row level by design.

---

## 2. Critical Risks: Talk Tracks

### Risk 1: DutHandler Init Crash (acquisition_mode.py, ~line 502)

**What happens:** `DutHandler(port=..., baudrate=..., ...)` is called with no surrounding try/except. If the port is in use or wrong, the exception can take down the acquisition window. IBP handlers are wrapped in try/except with user-visible logging; DUT is not.

**Why it's a risk:** Single point of failure. Inconsistent contract. One bad port choice can prevent Acquisition mode from starting.

**How to fix it:** Wrap the entire DUT setup block in try/except. On exception: log with same pattern as IBP, set `self.serial_handler = None`, continue. Window stays open.

### Risk 2: UI-Blocking time.sleep on Main Thread

**What happens:** Several code paths on the Qt main thread call `time.sleep()`. During a protocol step transition, pump + TIC A + TIC B + chiller sleeps chain to over a second of total UI freeze.

**Important nuance -- Baud Rate Context:**

| Device | Baud Rate | Typical Sleep | Rationale |
|--------|-----------|---------------|-----------|
| DUT | 115200 | 0.05 s | Fast device |
| Pump | 19200 | 0.1 s | ~6x slower than DUT |
| Chiller | **4800** | 0.1-0.2 s | ~24x slower; 10-byte command takes ~21 ms to transmit |
| TIC | USB | 0.1-0.3 s | Subprocess overhead |

**The sleep durations are correct; the bug is their location on the GUI thread.**

**How to fix it:** No `time.sleep()` in any code path called from the main thread. Keep the exact same delays but move them into worker threads. The GUI signals "do this," the worker does it (including waits), the worker signals "done."

### Risk 3: Hardcoded Serial Strings

**What happens:** Protocol details are literal strings in multiple files (9 distinct strings across 4 handler files).

**Why it's a risk:** Firmware change forces edits in several places; one missed literal causes subtle bugs.

**How to fix it:** One constants module per device. Replace every literal at call sites. A protocol change becomes a one-line edit.

---

## 3. Technical Deep Dive

### Block A: Data Pipeline + IBP Synchronization

1. DutHandler polls, emits `data_received`
2. Main thread: `handle_data` synchronously calls IBP `read_data()`
3. IBP sends "VALAR", parses, emits `data_received(ref_id, cond, temp)`
4. Main thread: `parse_and_update` parses DUT, stores, graphs, writes CSV

**Takeaway:** IBP reads block the main thread. If IBP is slow, UI can stutter.

### Block B: Protocol Execution

1. ProtocolDialog holds ProtocolHandler. User loads JSON, clicks Start.
2. ProtocolHandler uses QTimer (1s ticks) for step timing.
3. On `step_started`, ProtocolDialog applies device settings via `parent_window.apply_*` -> `DeviceController`.
4. DeviceController creates temporary threads with sleeps on the calling thread (main thread).

**Takeaway:** Step timing is non-blocking (QTimer). Device application is fully synchronous and blocks the GUI. The sleeps are hardware-correct but belong in worker threads.

### Block C: Threading Model

- **Handler threads (QThread):** DutHandler, IBPHandler, SyringePumpThread, ChillerThread, TicThread -- all own their I/O.
- **Main thread:** Runs all UI, slots, `handle_data`, `parse_and_update`, and DeviceController methods with sleeps.

**Takeaway:** I/O is correctly offloaded. The failure is coordination -- "do several things with delays" is implemented on the main thread.

---

## 4. Future Roadmap

### 4.1 Abstract Base Class for Handlers
Define a common interface (start, stop, pause, resume, data_received, error_occurred). Acquisition window can treat all handlers uniformly. Adding a new device type means implementing the interface.

### 4.2 Centralized Protocol Constants
Per-device constant modules. Optionally load from configuration for multi-firmware support. Turns code changes into configuration changes.

---

## 5. FAQ: Pressure-Test Questions

**Q1: "If the DUT port is wrong, what happens today?"**
**A:** The thread terminates abnormally. We don't catch it at the window level. IBP is protected; DUT is not.

**Q2: "Where does the main thread block?"**
**A:** IBP read_data calls, SyringePumpDialog.run_pump (0.4s), TicDialog.closeEvent (0.2s), stop_all_devices, and DeviceController apply methods during protocols. Longest: protocol step transition at ~1.7s. Sleep durations are hardware-justified but misplaced.

**Q3: "How is protocol timing decoupled from device application?"**
**A:** It isn't fully. Step duration is QTimer (non-blocking). But applying settings is synchronous on the main thread.

**Q4: "Why TIC threads persistent but pump/chiller temporary?"**
**A:** TIC needs continuous control during protocols. Pump/chiller are "set and forget" per step.

**Q5: "One change for most maintainability benefit?"**
**A:** Centralizing serial protocol constants. Removes scattered magic strings, makes protocol changes predictable.

**Q6: "Aren't the time.sleep calls there because devices need them?"**
**A:** Yes -- and that's important. The sleep durations correlate with baud rates. The developer was correct. The problem is they execute on the GUI thread. The fix: keep the same values, move them into worker threads.

---

---

# PART I: PRESENTATION SCRIPT -- HOW TO SAY IT

*Literal script for presenting the review. Read it, internalize the flow, deliver in order.*

---

## Opening (30 seconds)

> "I've done a full review of the alyPyAcquisition codebase. I'm going to walk through three things: how data flows from hardware to the screen, three specific risks I found with fixes, and two architectural improvements I'd like to propose. I'll keep it tight."

---

## Part 1: How the System Works (3-5 minutes)

### The Big Picture

> "The app has three modes: Acquisition, Analysis, and Programming. Today I'm focused on Acquisition because that's where the real-time hardware interaction happens."

> "At startup, `main.py` creates a `ModeManager`. The ModeManager shows a mode selector dialog, creates the chosen window, runs the Qt event loop until that window closes, then loops back to the selector."

### The Data Pipeline

> "**Step 1 -- Hardware.** We have `DutHandler`. It's a Qt thread. Every few seconds it sends the letter `b` over a serial port. The DUT responds with a message ending with a star character. The handler reads bytes until it sees that star, decodes the message, and emits a Qt signal called `data_received`."

> "Think of it like a walkie-talkie. The handler presses the button, says 'b', and listens until the device says 'over' -- which is the star character."

> "**Step 2 -- Signal crosses threads.** That `data_received` signal is connected to `handle_data` on the main window. Qt delivers this safely from the background thread."

> "**Step 3 -- Parse.** `DataParser.parse_all_measurements` takes the raw string and uses regex to split by unit. For each unit it extracts frequency, impedance magnitude, and phase."

> "**Step 4 -- Store and display.** `DataManager` appends to in-memory lists and writes a CSV row. `GraphManager` updates live PyQtGraph plots."

> "**Step 5 -- IBP sync.** When DUT data arrives, we also trigger reads from IBP reference sensors for time-alignment."

**Pause. Ask:** "Does that flow make sense before I move to the risks?"

---

## Part 2: The Three Risks (5-8 minutes)

> "I found three categories of issues. None are data-corruption bugs -- the pipeline works correctly. These are reliability and maintainability risks."

### Risk 1: DUT Initialization Can Crash the Window

> "In `acquisition_mode.py`, around line 502, we create `DutHandler` with no try/except. Compare that to IBP -- those are wrapped in try/except with logging."

> "The fix is straightforward: wrap DUT setup in the same try/except pattern we already use for IBP."

> "It's like having a safety catch on five out of six circuit breakers."

### Risk 2: UI Freezes from Blocking Sleeps

> "There are `time.sleep` calls on the main Qt thread. The specific locations are stop_all_devices, run_pump (0.4s), TIC closeEvent, and DeviceController protocol methods."

**Important context -- say this before the fix:**

> "Now, before the fix: these sleeps aren't arbitrary. They correlate with baud rates. DUT runs at 115200 -- fast. Pump at 19200 -- 6x slower. Chiller at 4800 -- 24x slower. The developer added delays because slower devices genuinely need time. **The sleep durations are correct -- they're hardware-justified. The issue is where they execute.**"

> "The rule going forward: no `time.sleep` on the main thread. Keep the same durations, move them into worker threads."

> "Right now we're standing at the stove waiting for water to boil. We should put the water on, walk away, and come back when the kettle whistles."

### Risk 3: Hardcoded Serial Strings

> "Every serial command is a raw string. DUT poll is `b'b'`, terminator is `*`, chiller start is `out_mode_05 1`. These appear in multiple places."

> "We create one constants module per device. A protocol change becomes a one-line edit."

> "It's the difference between writing someone's phone number on ten sticky notes versus putting it in your contacts once."

---

## Part 3: Two Improvements (2-3 minutes)

### Improvement 1: Abstract Base Class for Handlers

> "DutHandler and IBPReferenceHandler look very similar but share no interface. A `BaseSerialHandler` ABC would standardize signals and methods. Adding a new device type means implementing the interface."

### Improvement 2: Centralized Protocol Constants

> "Once we have per-device constant modules, we can also load them from configuration. A firmware change becomes a config change instead of a code change."

---

## Closing (30 seconds)

> "To summarize: the data pipeline is solid. The three risks are: unguarded DUT init, blocking sleeps on the UI thread, and scattered magic strings. The fixes are targeted refactors, not a rewrite."

> "I'd like to agree on priority order: DUT init guard first (five-minute fix), then constants refactor, then sleep removal."

> "What questions do you have?"

---

## Cheat Sheet: If They Push Back

| They say | You say |
|----------|---------|
| "The sleeps are only 100 ms, that's fine." | "Individually yes, and they're hardware-justified. But in the protocol step-change path they chain to over a second. On Windows, 500 ms triggers 'Not Responding'. The durations are correct; they just need worker threads." |
| "We've never had a DUT port crash." | "Correct -- because the operator always gets it right. But ports can shift after reboot. The fix is five lines and matches the IBP pattern." |
| "Constants modules are overkill." | "Today, yes. But we have 4 devices with 7 commands. One more device doubles the count. One-time investment." |
| "Why not Enum?" | "Either works. Constants are lighter. Start with constants, upgrade to Enum if the team prefers." |
| "One thing to fix first?" | "Guard the DUT init. Highest risk-to-effort ratio." |

---

## Quick Reference: File Locations

| Topic | File | Line(s) |
|-------|------|---------|
| DUT init (no try/except) | modes/acquisition_mode.py | ~502 |
| IBP init (has try/except) | modes/acquisition_mode.py | ~594, ~623 |
| stop_all_devices sleep | modes/acquisition_mode.py | ~1323 |
| run_pump sleeps | modes/dialogs/syringe_pump_dialog.py | ~413-422 |
| TIC closeEvent sleep | modes/dialogs/tic_dialog.py | ~764 |
| DeviceController sleeps | modes/controllers/device_controller.py | ~92-185, ~324-421 |
| DUT poll command `b'b'` | modes/hardware/dut_handler.py | ~70 |
| DUT terminator `b'*'` | modes/hardware/dut_handler.py | ~94, 117, 125, 133 |
| Pump `"VER"` | modes/hardware/syringe_pump_handler.py | ~65 |
| IBP `"SYSSNR"` / `"VALAR"` | modes/hardware/ibp_reference_handler.py | ~61, ~93 |
| Chiller commands | modes/hardware/chiller_handler.py | ~129, ~148, ~162 |

---

---

# PART J: MEETING PREP NOTES

*Discussion topics, questions to ask, and desired outcomes.*

---

## Meeting Goals

- **Clarify reliability and failure-handling strategy** around serial hardware initialization and runtime errors.
- **Agree on a plan to eliminate UI blocking** caused by `time.sleep()` on the main Qt thread.
- **Define a consistent approach for serial protocol commands and magic values.**
- **Validate and refine the current architecture pattern** for future scaling.
- **Leave with a concrete, prioritized TODO list** and ownership.

---

## 1. Reliability & Error Handling

### 1.1 DUT vs IBP Initialization Asymmetry

- **Observation:** DutHandler created without try/except (~line 502). IBP handlers are guarded.
- **Discussion:**
  - Should DUT failures be handled the same as IBP?
  - Desired UX if DUT port is wrong? Fail the mode? Show error and stay?
  - Should ModeManager recover from window init failures?
- **Decisions Needed:**
  - Standard pattern for all hardware handler init.
  - Whether ModeManager should gracefully recover.

### 1.2 Global Exception Handling

- **Observation:** `main.py` has a broad try/except that does `sys.exit(1)` with no logging.
- **Discussion:** Where should global logging live? What format?
- **Decisions Needed:** Minimal global logging policy. User-facing "critical error" dialog.

---

## 2. UI Blocking & Threading

### 2.1 Known Blocking Points

| Location | File | Sleep Duration |
|----------|------|---------------|
| `stop_all_devices()` | acquisition_mode.py:1323 | 0.1 s + DeviceController sleeps |
| `run_pump()` | syringe_pump_dialog.py:395-422 | 4 x 0.1 s = 0.4 s |
| `closeEvent()` | tic_dialog.py:764 | 0.2 s per motor |
| `apply_pump_settings` | device_controller.py | 4 x 0.1 s |
| `apply_tic_settings` | device_controller.py | 0.3 + 0.15 + 0.1 s |
| `stop_all_devices` | device_controller.py | Multiple 0.1 s |

### 2.1.1 Baud Rate Context

| Device | Baud Rate | Init Sleep | Between-Command Sleep |
|--------|-----------|------------|----------------------|
| DUT | 115200 | none | 0.05 s (in thread -- safe) |
| Pump | 19200 | 0.1 s | 0.1 s |
| Chiller | **4800** | **0.2 s** | -- |
| TIC | USB | 0.3 s | 0.1-0.15 s |

**The delays are hardware-justified; the issue is their location (GUI thread).**

### 2.2 Discussion Topics

- Acceptable latency budget for UI freeze?
- Should all operations move into worker threads?
- Should DeviceController have its own thread?
- Use Qt queued connections instead of direct calls with sleeps?

### 2.3 Desired Outcomes

- **No-`time.sleep` on GUI thread** rule
- Concrete refactoring pattern
- Priority order for fixing blocking sites
- Acknowledgment that sleep durations are correct

---

## 3. Serial Protocol & Magic Strings

### 3.1 Current Hardcoded Commands

| Device | Command | File:Line |
|--------|---------|-----------|
| DUT | `b'b'` poll, `b'*'` terminator | dut_handler.py:70, 94 |
| Pump | `"VER"` | syringe_pump_handler.py:65 |
| IBP | `"SYSSNR"`, `"VALAR"` | ibp_reference_handler.py:61, 93 |
| Chiller | `"in_pv_00"`, `"out_mode_05 1/0"` | chiller_handler.py:129, 148, 162 |

### 3.2 Discussion Topics

- Simple constants modules vs richer enums?
- Should terminators and sentinel values also be centralized?
- Configuration-driven protocol layer for firmware variants?

### 3.3 Desired Outcomes

- Single source of truth per device
- Decision on where constants live

---

## 4. Architecture & Responsibilities

### 4.1 Current Patterns

- **Signals/Slots:** Hardware handler threads --> AcquisitionWindow (good)
- **Direct Calls:** AcquisitionWindow --> DeviceController (synchronous)
- **Direct Calls:** DeviceController --> AcquisitionWindow (`parent_window.log_event`)

### 4.2 Discussion Topics

- Is the hybrid approach intentional?
- Should DeviceController become a formal async service?
- Should DeviceController emit signals instead of calling `log_event` directly?

---

## 5. Questions to Ask

1. "If DUT initialization fails, should Acquisition mode still open with a warning, or should we bounce back to the mode selector?"
2. "Where do you want global exception logging to live?"
3. "Is any intentional blocking on close/start acceptable, or should we aim for zero `time.sleep` in GUI handlers?"
4. "How stable are the current device protocols? Do we expect firmware variants?"
5. "Do you prefer simple constants modules or enums?"
6. "Do you see DeviceController evolving into an async service?"

---

---

# PART K: AUDIT REPORT TABLE

*One-table summary of all critical improvements.*

---

## Architecture Overview

The architecture mixes Qt Signals/Slots for threaded hardware handlers (DUT/IBP/etc.) with direct method calls between `AcquisitionWindow` and `DeviceController`, creating a hybrid event-driven and tightly coupled control layer.

## Critical Improvements

| File:Line | Bug | Required Fix |
| --- | --- | --- |
| `modes/acquisition_mode.py:502` | `DutHandler` instantiated without `try/except`, unlike IBP handlers. DUT port failures can crash Acquisition startup. | Wrap DUT creation block in `try/except` mirroring IBP pattern. Log error, keep UI responsive. |
| `modes/acquisition_mode.py:1304-1323` | `stop_all_devices()` performs shutdown on GUI thread with `time.sleep(0.1)`. | Move blocking stop operations into worker thread. Replace sleep with async progress. |
| `modes/dialogs/syringe_pump_dialog.py:395-422` | `run_pump()` sends pump commands with four `time.sleep(0.1)` on GUI thread (0.4s freeze). **Note:** Delays are hardware-justified at 19200 baud. | Keep delays, offload pump command sequence to SyringePumpThread. Dialog calls single API, thread handles sleeps internally. |
| `modes/dialogs/tic_dialog.py:764` | `closeEvent()` calls `time.sleep(0.2)` while stopping motors, blocking GUI. | Perform TIC stop in worker thread or use non-blocking timers. |
| `modes/hardware/dut_handler.py:70` | Poll command hardcoded as `b'b'`. | Introduce constant `DUT_CMD_POLL = b"b"`. |
| `modes/hardware/dut_handler.py:82-133` | Termination character `'*'` scattered across multiple literals. | Define `DUT_TERMINATOR = b'*'` and reference everywhere. |
| `modes/hardware/syringe_pump_handler.py:65` | Pump identification uses hardcoded `"VER"`. | Move to `PUMP_COMMANDS` constants. |
| `modes/hardware/ibp_reference_handler.py:61` | IBP serial-number query uses hardcoded `"SYSSNR"`. | Extract to `IBP_CMD_READ_SN` constant. |
| `modes/hardware/ibp_reference_handler.py:93` | IBP data read uses hardcoded `"VALAR"` in two places. | Centralize as `IBP_CMD_READ_VALUES`. |
| `modes/hardware/chiller_handler.py:129` | Chiller temp read uses hardcoded `"in_pv_00"`. | Introduce `CHILLER_CMD_READ_TEMP` constant. |
| `modes/hardware/chiller_handler.py:148` | Chiller start command `"out_mode_05 1"` inlined. | Replace with `CHILLER_CMD_START` constant. |
| `modes/hardware/chiller_handler.py:162` | Chiller stop command `"out_mode_05 0"` inlined. | Replace with `CHILLER_CMD_STOP` constant. |

**Baud Rate Context:** The inter-command sleeps correlate with device baud rates (Chiller=4800, Pump=19200, DUT=115200). The delays are hardware-justified; the issue is that they execute on the GUI thread instead of inside handler threads.

---

---

*End of Complete Code Review. Three things to fix: guard DUT init, centralize protocol strings, move sleeps off the UI thread. The architecture is sound. Let's make it bulletproof for v2.*
