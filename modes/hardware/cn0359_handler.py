"""
CN0359 Serial Communication Handler
====================================
This module's job: talk to 1-8 CN0359 conductivity sensor boards over
USB-to-serial connections.  Each sensor gets its own COM port.

HOW IT WORKS (big picture):
    1. The app creates a CN0359Handler with a list of sensor tuples
    2. CN0359Handler.start() launches a background thread (it's a QThread)
    3. The thread opens all serial connections, then enters a poll loop
    4. Each poll cycle, it sends "poll\\n" to each sensor
    5. It reads 22 lines of ASCII response from each sensor
    6. It bundles all responses into a dict and emits data_received signal
    7. acquisition_mode.py receives the signal and passes data to CN0359Parser

FAULT TOLERANCE:
    - Each sensor is polled independently.  If sensor 2 hangs, sensors 1/3/4/5/6
      still get polled on time.
    - Per-sensor timeouts: 200ms per readline, 2s total per sensor
    - Consecutive failure tracking: after 5 failures, a warning is emitted
      (but we keep retrying -- the sensor might come back)
    - Serial exceptions are caught per-sensor, never crashing the thread

SIGNAL INTERFACE:
    Same signals as DutHandler so acquisition_mode.py can use either one
    without changing its signal connection code:
        data_received(object)        - the poll results
        error_occurred(str)          - error messages
        disconnected()               - all ports failed
        command_sent(str)            - "poll" (for logging)
        response_received(str, str)  - ("poll", summary)

Serial protocol adapted from
CN0_Python_Scripts/modules/analog_devices_conductivity_board.py
"""
import logging
import time
import threading
from collections import deque

from PySide6.QtCore import QThread, Signal
import serial

logger = logging.getLogger(__name__)


# ==========================================================================
# CONSTANTS  --  these control the sensor communication timing
# ==========================================================================

# The CN0359 firmware always outputs exactly 22 lines when you send "poll"
POLL_LINES = 22

# How long to wait for a single readline() before giving up.
# 200ms is generous -- a healthy sensor responds in ~50ms per line.
PER_LINE_TIMEOUT = 0.2   # seconds

# Maximum wall-clock time to spend reading from ONE sensor.
# If 2 seconds pass and we still don't have 22 lines, we give up
# and move on to the next sensor.  This prevents one dead sensor
# from blocking the entire poll cycle.
PER_SENSOR_TIMEOUT = 2.0  # seconds

# After this many consecutive failed polls, we emit a stronger warning.
# We don't stop trying though -- the sensor might recover.
MAX_CONSECUTIVE_FAILS = 5
EMULATOR_PORT_PREFIX = "EMULATOR"


def _is_emulator_port(port_name):
    """True when this sensor should use the in-process CN0359 emulator."""
    if not port_name:
        return False
    return str(port_name).upper().startswith(EMULATOR_PORT_PREFIX)


class _EmulatedSerial:
    """Small serial-like CN0359 emulator used for hardware-free testing."""

    def __init__(self, unit_id, port_name):
        self.unit_id = int(unit_id)
        self.port = port_name
        self._is_open = True
        self._rx = deque()
        self._poll_count = 0
        self._adc0_hits = 0
        self._adc1_hits = 0

    @property
    def is_open(self):
        return self._is_open

    def close(self):
        self._is_open = False
        self._rx.clear()

    def flush(self):
        return None

    def reset_input_buffer(self):
        self._rx.clear()

    def write(self, data):
        if not self._is_open:
            raise serial.SerialException(f"{self.port} is closed")
        if isinstance(data, bytes):
            cmd = data.decode("utf-8", errors="ignore").strip().lower()
        else:
            cmd = str(data).strip().lower()
        if cmd == "poll":
            self._queue_poll_response()

    def readline(self):
        if not self._is_open:
            return b""
        if self._rx:
            return self._rx.popleft()
        return b""

    def _queue_poll_response(self):
        self._poll_count += 1
        self._adc0_hits += 9 + self.unit_id
        self._adc1_hits += 3 + self.unit_id

        # Deterministic per-sensor values with small dynamic change each poll.
        cond = 0.00075 + (self.unit_id * 0.00011) + ((self._poll_count % 11) * 0.000007)
        temp = 23.8 + (self.unit_id * 0.45) + ((self._poll_count % 9) * 0.03)
        freq = 10000.0 + (self.unit_id * 125.0)
        setup = 10.0
        hold = 1.0
        cell_k = 1.0 + (self.unit_id * 0.02)
        p_curr = 0.00100 + (self.unit_id * 0.00002)
        n_curr = -p_curr
        p_volt = 0.965 + (self.unit_id * 0.002)
        n_volt = -p_volt

        lines = [
            f"EXC V: 1.000000V\n",
            f"EXC FREQ: {freq:.6f}Hz\n",
            f"EXC setup time: {setup:.6f}%\n",
            f"EXC hold time: {hold:.6f}%\n",
            "TEMP COEF: 2.000000%/'C\n",
            f"cell K: {cell_k:.6f}/cm\n",
            f"ADC0 hits: {self._adc0_hits}\n",
            "+I gain: 10\n",
            f"+Ip-p: {p_curr:.6e}A\n",
            "-I gain: 10\n",
            f"-Ip-p: {n_curr:.6e}A\n",
            "+V gain: 10\n",
            f"+Vp-p: {p_volt:.6e}V\n",
            "-V gain: 10\n",
            f"-Vp-p: {n_volt:.6e}V\n",
            f"ADC1 hits: {self._adc1_hits}\n",
            "RTD: PT1000\n",
            "RTD wire: 4 wire\n",
            f"TEMP: {temp:.6f}'C\n",
            f"conductivity: {cond:.6e}S/cm\n",
            f"raw conductivity: {cond * 0.98:.6e}S/cm\n",
            f"sensor id: U{self.unit_id:02d}\n",
        ]
        self._rx.extend(ln.encode("utf-8") for ln in lines)


# ==========================================================================
# CHUNK 1: Per-sensor bookkeeping
# ==========================================================================
class _SensorState:
    """Tracks the state of one CN0359 sensor.

    This is an internal class -- the rest of the app never sees it.
    CN0359Handler creates one _SensorState per configured sensor.

    Attributes:
        unit_id:              Which sensor number (1-7) this is
        port_name:            COM port string, e.g. "COM3"
        address:              Legacy field kept for compatibility; ignored in V2
        ser:                  The pyserial Serial object (or None if not open)
        consecutive_failures: How many polls in a row have failed
        last_successful_poll: Unix timestamp of last good poll (or None)
    """

    def __init__(self, unit_id, port_name, address):
        self.unit_id = unit_id
        self.port_name = port_name
        self.address = address
        self.ser = None                  # set by _open_connections()
        self.consecutive_failures = 0    # reset to 0 on each success
        self.last_successful_poll = None # updated on each success


# ==========================================================================
# CHUNK 2: The main handler thread
# ==========================================================================
class CN0359Handler(QThread):
    """QThread that polls multiple CN0359 sensors sequentially.

    Inherits from QThread so it runs in a background thread.  The main
    GUI thread stays responsive while this thread does blocking serial I/O.

    Usage:
        handler = CN0359Handler([(1, "COM3", "30"), (2, "COM5", "30")])
        handler.data_received.connect(my_callback)
        handler.start()    # launches the background thread
        handler.resume()   # starts polling (handler starts paused)
        ...
        handler.stop()     # cleanly shuts down
    """

    # Qt Signals -- these are how the handler communicates back to the GUI.
    # Signals are thread-safe: emitting from the worker thread delivers
    # to slots on the main thread automatically.
    data_received = Signal(object)       # emits dict {unit_id: response_text}
    error_occurred = Signal(str)         # emits error message string
    disconnected = Signal()              # emits when ALL ports fail to open
    command_sent = Signal(str)           # emits "poll" (for UI logging)
    response_received = Signal(str, str) # emits (command, summary) for UI logging

    def __init__(self, sensor_configs, baudrate=115200, query_interval=0.1):
        """Set up the handler (but don't open ports yet -- that happens in run()).

        Args:
            sensor_configs: list of sensor tuples. Accepted forms:
                            (unit_id, com_port) or (unit_id, com_port, legacy_address)
                            Legacy address is ignored; handler always uses bare "poll\\n".
            baudrate: baud rate for all sensors.  CN0359 default is 115200.
            query_interval: minimum seconds between poll cycles.
                            Set by config.ini [CN0359] poll_interval.
        """
        super().__init__()

        # Validate: at least one sensor must be configured
        if not sensor_configs:
            raise ValueError("sensor_configs must contain at least one sensor tuple")

        self.sensor_configs = sensor_configs
        self.baudrate = baudrate

        # Enforce minimum 0.1s poll interval to prevent CPU spinning
        self.query_interval = max(0.1, query_interval)

        # Will be populated by _open_connections() when run() is called
        self.sensors: list[_SensorState] = []

        # Thread control flags (set/read from different threads, but Python's
        # GIL makes bool reads/writes atomic so no lock needed)
        self.running = False   # False = thread should exit its loop
        self.paused = False    # True = skip polling but stay alive
        self._io_lock = threading.RLock()

    # ==================================================================
    # CHUNK 3: Thread lifecycle methods
    # ==================================================================

    def run(self):
        """Main thread entry point -- called automatically by QThread.start().

        Opens serial connections, then enters a poll loop that runs until
        self.running is set to False.  The loop:
          1. Checks if enough time has passed since the last poll
          2. If yes (and not paused), polls all sensors
          3. If any sensor returned data, emits data_received signal
          4. If no, sleeps 10ms to avoid busy-waiting
        """
        try:
            self._open_connections()
            self.running = True

            # Track when we last polled so we respect query_interval
            last_query_time = 0.0

            while self.running:
                current_time = time.time()

                # Only poll if: (a) not paused, (b) enough time has elapsed
                if not self.paused and current_time - last_query_time >= self.query_interval:
                    responses = self._poll_all_sensors()
                    last_query_time = time.time()

                    # Only emit if at least one sensor returned data
                    if responses:
                        self.data_received.emit(responses)
                else:
                    # Sleep briefly to avoid burning 100% CPU
                    time.sleep(0.01)

        except Exception as e:
            # Catch-all for unexpected errors so the thread doesn't die silently
            self.error_occurred.emit(f"CN0359Handler fatal error: {e}")
        finally:
            # Always close ports when the thread exits, no matter why
            self.close_connection()

    def stop(self):
        """Signal the thread to exit and wait for it to finish.

        Called from the main thread.  Sets running=False so the while loop
        in run() exits, then wait() blocks until the thread is actually done.
        A 5-second timeout prevents the GUI from freezing if the serial
        driver ignores the readline timeout (e.g., broken USB driver).
        """
        self.running = False
        if not self.wait(5000):
            logger.error("CN0359Handler thread did not stop within 5s, force-terminating")
            self.terminate()
            self.wait(2000)

    def pause(self):
        """Pause polling without stopping the thread.

        The thread stays alive but skips the polling step.  Useful when the
        user clicks "Pause" in the UI.
        """
        self.paused = True

    def resume(self):
        """Resume polling after a pause."""
        self.paused = False

    def close_connection(self):
        """Close all open serial ports.

        Called automatically when the thread exits.  Also safe to call
        manually.  Handles errors gracefully (e.g., if the USB cable was
        already unplugged, the close() might fail).
        """
        for s in self.sensors:
            if s.ser and s.ser.is_open:
                try:
                    s.ser.close()
                except Exception as e:
                    logger.error("Error closing port %s: %s", s.port_name, e)
            s.ser = None  # clear the reference even if close failed

    def write_data(self, data):
        """Broadcast raw data to all open sensor ports (rarely needed).

        This exists to maintain API compatibility with DutHandler, which
        has the same method.  In practice, we almost never need to send
        arbitrary data to CN0359 sensors -- the poll command is handled
        internally by _poll_one_sensor().
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        for s in self.sensors:
            if s.ser and s.ser.is_open:
                try:
                    s.ser.write(data)
                except Exception as e:
                    self.error_occurred.emit(
                        f"Write error on unit {s.unit_id} ({s.port_name}): {e}"
                    )

    # ==================================================================
    # CHUNK 4: Opening serial connections
    # ==================================================================

    def _open_connections(self):
        """Open a serial port for each configured sensor.

        Iterates through self.sensor_configs and creates a pyserial Serial
        object for each one.  If a port fails to open (e.g., port doesn't
        exist, permission denied), we emit an error but keep going --
        the other sensors might still work.
        """
        self.sensors = []

        for cfg in self.sensor_configs:
            if len(cfg) >= 3:
                unit_id, port_name, _ = cfg[0], cfg[1], cfg[2]
            elif len(cfg) == 2:
                unit_id, port_name = cfg[0], cfg[1]
            else:
                self.error_occurred.emit(f"Invalid sensor config entry: {cfg!r}")
                continue

            state = _SensorState(unit_id, port_name, "")
            try:
                if _is_emulator_port(port_name):
                    state.ser = _EmulatedSerial(unit_id, port_name)
                    self.sensors.append(state)
                    continue

                # Open the serial port.  Key parameters:
                #   port:     COM port name, e.g. "COM3"
                #   baudrate: must match the sensor (CN0359 uses 115200)
                #   timeout:  how long readline() waits before returning empty
                #             (PER_LINE_TIMEOUT = 0.2s)
                state.ser = serial.Serial(
                    port=port_name,
                    baudrate=self.baudrate,
                    timeout=PER_LINE_TIMEOUT,
                )
                # Stop auto-publish mode.  The CN0359 firmware may be in
                # binary auto-publish mode from a previous session.  Sending
                # " e\n" disables it so we can use ASCII poll mode.
                time.sleep(0.3)
                state.ser.reset_input_buffer()
                state.ser.write(b" e\n")
                time.sleep(0.3)
                state.ser.reset_input_buffer()
            except serial.SerialException as e:
                # Port couldn't be opened -- maybe it doesn't exist,
                # or another program has it locked
                self.error_occurred.emit(
                    f"Failed to open {port_name} for sensor {unit_id}: {e}"
                )
            # Add to the list even if ser is None -- _poll_all_sensors()
            # will skip sensors with ser=None
            self.sensors.append(state)

        # Check if ANY port opened successfully
        opened = sum(1 for s in self.sensors if s.ser and s.ser.is_open)
        if opened == 0:
            self.error_occurred.emit("No CN0359 sensor ports could be opened")
            self.disconnected.emit()

    def _try_reconnect(self, sensor):
        """Attempt to reopen a failed sensor's serial port.

        Called when a sensor has hit MAX_CONSECUTIVE_FAILS and its port is
        closed or None.  If the USB cable was replugged, this will bring
        the sensor back online without restarting the app.
        """
        try:
            if sensor.ser is not None:
                try:
                    sensor.ser.close()
                except Exception:
                    pass
                sensor.ser = None

            if _is_emulator_port(sensor.port_name):
                sensor.ser = _EmulatedSerial(sensor.unit_id, sensor.port_name)
            else:
                sensor.ser = serial.Serial(
                    port=sensor.port_name,
                    baudrate=self.baudrate,
                    timeout=PER_LINE_TIMEOUT,
                )
                time.sleep(0.3)
                sensor.ser.reset_input_buffer()
                sensor.ser.write(b" e\n")
                time.sleep(0.3)
                sensor.ser.reset_input_buffer()

            sensor.consecutive_failures = 0
            logger.info("Reconnected sensor %s on %s", sensor.unit_id, sensor.port_name)
            self.error_occurred.emit(
                f"Sensor {sensor.unit_id} on {sensor.port_name}: reconnected successfully"
            )
        except serial.SerialException:
            pass
        except Exception as e:
            logger.debug("Reconnect attempt failed for %s: %s", sensor.port_name, e)

    # ==================================================================
    # CHUNK 5: Polling all sensors (the main poll cycle)
    # ==================================================================

    def _poll_all_sensors(self):
        """Poll each sensor sequentially and collect their responses.

        This is the heart of each poll cycle.  For each sensor:
          1. Skip if port isn't open
          2. Call _poll_one_sensor() to send command and read response
          3. On success: store response, reset failure counter
          4. On failure: increment failure counter, emit error
          5. Catch any exception so one broken sensor never crashes the loop

        Returns:
            dict mapping unit_id -> response_text for sensors that responded.
            Empty dict if no sensors responded.
        """
        responses = {}
        with self._io_lock:
            for s in self.sensors:
                # Try to reconnect sensors whose port is dead/closed
                if s.ser is None or not s.ser.is_open:
                    if s.consecutive_failures >= MAX_CONSECUTIVE_FAILS:
                        self._try_reconnect(s)
                    if s.ser is None or not s.ser.is_open:
                        continue

                try:
                    response = self._poll_one_sensor(s)

                    if response is not None:
                        # SUCCESS -- store the response and reset failure tracking
                        responses[s.unit_id] = response
                        s.consecutive_failures = 0
                        s.last_successful_poll = time.time()
                    else:
                        # TIMEOUT -- sensor didn't respond with 22 lines in time
                        s.consecutive_failures += 1
                        self.error_occurred.emit(
                            f"Sensor {s.unit_id} on {s.port_name} timed out "
                            f"(fail {s.consecutive_failures}/{MAX_CONSECUTIVE_FAILS})"
                        )
                        # Emit a stronger warning after MAX_CONSECUTIVE_FAILS
                        if s.consecutive_failures >= MAX_CONSECUTIVE_FAILS:
                            self.error_occurred.emit(
                                f"Sensor {s.unit_id} on {s.port_name}: "
                                f"{MAX_CONSECUTIVE_FAILS} consecutive failures"
                            )

                except serial.SerialException as e:
                    # Serial-specific error (port disconnected, USB unplugged, etc.)
                    s.consecutive_failures += 1
                    self.error_occurred.emit(
                        f"Serial error on sensor {s.unit_id} ({s.port_name}): {e}"
                    )
                except Exception as e:
                    # Catch-all for unexpected errors
                    s.consecutive_failures += 1
                    self.error_occurred.emit(
                        f"Unexpected error polling sensor {s.unit_id} ({s.port_name}): {e}"
                    )

        # Emit summary for the UI log panel
        if responses:
            summary = ", ".join(
                f"U{uid}" for uid in sorted(responses.keys())
            )
            self.command_sent.emit("poll")
            self.response_received.emit("poll", f"Received data from: {summary}")

        return responses

    def preflight_snapshot(self, attempts=2):
        """Run a quick, deterministic connectivity snapshot across configured sensors.

        Returns a list of dictionaries with per-sensor status fields:
            unit_id, port, detected, parse_ok, non_empty_lines, error, preview
        """
        attempts = max(1, int(attempts))
        results = []
        with self._io_lock:
            for s in self.sensors:
                best_non_empty = 0
                best_response = None
                last_error = ""
                for _ in range(attempts):
                    if s.ser is None or not s.ser.is_open:
                        last_error = "port not open"
                        break
                    try:
                        response = self._poll_one_sensor(s)
                        if response:
                            non_empty = sum(1 for ln in response.splitlines() if ln.strip())
                            if non_empty > best_non_empty:
                                best_non_empty = non_empty
                                best_response = response
                    except Exception as e:  # noqa: BLE001
                        last_error = str(e)

                detected = best_non_empty > 0
                parse_ok = False
                preview = ""
                if best_response:
                    blob = best_response.lower()
                    has_primary = ("conductivity:" in blob) and ("temp:" in blob)
                    has_explicit_resistance = ("r combined:" in blob) or ("|z|:" in blob) or ("rp-p:" in blob)
                    has_iv_for_derived_resistance = (
                        ("+ip-p:" in blob)
                        and ("-ip-p:" in blob)
                        and ("+vp-p:" in blob)
                        and ("-vp-p:" in blob)
                    )
                    parse_ok = has_primary and (has_explicit_resistance or has_iv_for_derived_resistance)
                    preview = next((ln for ln in best_response.splitlines() if ln.strip()), "")

                results.append({
                    "unit_id": s.unit_id,
                    "port": s.port_name,
                    "detected": detected,
                    "parse_ok": parse_ok,
                    "non_empty_lines": best_non_empty,
                    "error": last_error,
                    "preview": preview,
                })
        return results

    # ==================================================================
    # CHUNK 6: Polling ONE sensor
    # ==================================================================

    def _poll_one_sensor(self, sensor):
        """Send a poll command to one sensor and read its 22-line response.

        This is where the actual serial I/O happens.  The protocol:
          1. Clear any stale data in the serial buffer
          2. Send bare "poll\\n"
          3. Read lines one at a time until we have 22
          4. If we exceed PER_SENSOR_TIMEOUT before getting 22 lines, abort

        Args:
            sensor: _SensorState object with an open serial connection.

        Returns:
            str: The concatenated 22-line response, or None on timeout.
        """
        # Clear any leftover bytes from the previous poll.  Without this,
        # stale data could mix with the new response and cause parse errors.
        sensor.ser.reset_input_buffer()

        # V2 firmware path: always use bare "poll\n".
        sensor.ser.write(b"poll\n")
        sensor.ser.flush()  # make sure it's sent immediately

        response = ""
        start = time.time()
        lines_read = 0

        # Read exactly POLL_LINES (22) lines from the sensor
        while lines_read < POLL_LINES:
            # Check if we've exceeded the total timeout for this sensor
            if time.time() - start > PER_SENSOR_TIMEOUT:
                return None  # timeout -- caller will handle it

            # Check if the handler is being shut down
            if not self.running:
                return None

            # readline() blocks up to PER_LINE_TIMEOUT (0.2s), then returns
            # whatever it has (or empty bytes if nothing came in)
            line = sensor.ser.readline()

            if line:
                # Decode the raw bytes to a string.  errors='replace' means
                # if there's a garbled byte, replace it with '?' instead of
                # crashing.  This is defensive -- real CN0359 data is ASCII.
                response += line.decode('utf-8', errors='replace')
                lines_read += 1
            # If line is empty (timeout on this readline), the while loop
            # will try again until PER_SENSOR_TIMEOUT is reached

        return response
