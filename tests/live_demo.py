"""
CN0359 Live End-to-End Demo  (NO hardware, NO virtual COM ports needed)

This script:
  1. Patches serial.Serial so the handler talks to an in-memory fake sensor
  2. Starts the CN0359Handler thread (the real production code)
  3. Feeds it realistic, drifting CN0359 poll responses
  4. Prints every parsed data point to the terminal in real time

Run:  python tests/live_demo.py

Press Ctrl+C to stop.
"""
import sys, os, time, threading, random, io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modes.controllers.cn0359_parser import CN0359Parser


# ---------------------------------------------------------------------------
# Fake serial port that responds to "poll\n" with 22-line responses
# ---------------------------------------------------------------------------
class FakeSerial:
    """Drop-in replacement for serial.Serial that simulates a CN0359 sensor."""

    def __init__(self, port, baudrate=115200, timeout=None, **kwargs):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout or 0.2
        self.is_open = True
        self._read_buffer = b""
        self._lock = threading.Lock()

        self._base_cond = 1.067e-03
        self._base_temp = 25.3
        self._freq = 10000.0
        self._cond = self._base_cond
        self._temp = self._base_temp
        self._poll_count = 0

    def write(self, data):
        cmd = data.decode('ascii', errors='replace').strip()
        if cmd == "poll":
            self._poll_count += 1
            self._cond += random.gauss(0, self._base_cond * 0.02)
            self._cond = max(self._base_cond * 0.5, min(self._base_cond * 1.5, self._cond))
            self._temp += random.gauss(0, 0.1)
            self._temp = max(self._base_temp - 3, min(self._base_temp + 3, self._temp))

            response = self._build_response()
            with self._lock:
                self._read_buffer += response.encode('ascii')

    def readline(self):
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            with self._lock:
                idx = self._read_buffer.find(b'\n')
                if idx >= 0:
                    line = self._read_buffer[:idx + 1]
                    self._read_buffer = self._read_buffer[idx + 1:]
                    return line
            time.sleep(0.005)
        return b""

    def reset_input_buffer(self):
        with self._lock:
            self._read_buffer = b""

    def flush(self):
        pass

    def close(self):
        self.is_open = False

    def _build_response(self):
        r = 1.0 / self._cond if self._cond > 0 else 999999.0
        lines = [
            f"EXC V: 0.400000V",
            f"EXC FREQ: {self._freq:.6f}Hz",
            f"+Ip-p: 0.001234V",
            f"-Ip-p: 0.001230V",
            f"+Vp-p: 0.398000V",
            f"-Vp-p: 0.397000V",
            f"+PHASE: 1.200000deg",
            f"-PHASE: -1.100000deg",
            f"Rp-p: {r:.6f}Ohm",
            f"Rreal: {r:.6f}Ohm",
            f"Rimag: 6.740000Ohm",
            f"|Z|: {r:.6f}Ohm",
            f"PHASE: 1.198000deg",
            f"R COMBINED: {r:.6f}Ohm",
            f"cell constant: 0.080000/cm",
            f"temp coefficient: 5.200000",
            f"setup time: 0.300000",
            f"hold time: 0.400000",
            f"",
            f"TEMP: {self._temp:.6f}'C",
            f"",
            f"conductivity: {self._cond:.6e}S/cm",
        ]
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Monkey-patch serial.Serial before importing the handler
# ---------------------------------------------------------------------------
import serial
_OriginalSerial = serial.Serial
serial.Serial = FakeSerial

from modes.hardware.cn0359_handler import CN0359Handler

# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------
def main():
    from PySide6.QtCore import QCoreApplication, QTimer

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)

    print("=" * 60)
    print("  CN0359 Live End-to-End Demo")
    print("  No hardware or virtual COM ports needed")
    print("=" * 60)
    print()

    sensor_configs = [
        (1, "FAKE_COM_A", ""),
        (2, "FAKE_COM_B", ""),
    ]

    handler = CN0359Handler(
        sensor_configs=sensor_configs,
        baudrate=115200,
        query_interval=2,
    )

    poll_count = [0]

    def on_data(responses):
        poll_count[0] += 1
        timestamp = time.strftime("%H:%M:%S")

        parsed = CN0359Parser.parse_all_sensors(responses, timestamp)

        print(f"\n--- Poll #{poll_count[0]} at {timestamp} ---")
        for unit in parsed['dut_units']:
            uid = unit['unit_id']
            cond = unit['conductivity']['rzmag']
            temp = unit['temperature']['rzmag']
            freq = unit['conductivity']['frequency']
            print(f"  Sensor {uid}:  conductivity = {cond:.6e} S/cm  |  "
                  f"temp = {temp:.2f} C  |  freq = {freq:.0f} Hz")
        sys.stdout.flush()

    def on_error(msg):
        print(f"  [ERROR] {msg}")
        sys.stdout.flush()

    handler.data_received.connect(on_data)
    handler.error_occurred.connect(on_error)

    print(f"Starting handler with {len(sensor_configs)} fake sensors...")
    print(f"Poll interval: {handler.query_interval}s")
    print(f"Press Ctrl+C to stop.\n")
    sys.stdout.flush()

    handler.start()
    handler.resume()

    shutdown_timer = QTimer()
    shutdown_timer.setSingleShot(True)
    shutdown_timer.timeout.connect(lambda: None)

    try:
        app.exec()
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n\nStopping after {poll_count[0]} polls...")
        handler.stop()
        print("Done.")


if __name__ == "__main__":
    main()
