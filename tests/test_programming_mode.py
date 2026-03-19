import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from modes.programming_mode import ProgrammingWindow, ProgrammingWorker


class _FakeDeviceSerial:
    """Deterministic fake serial interface for ProgrammingWorker tests."""

    def __init__(self):
        self._buf = bytearray()

    @property
    def in_waiting(self):
        return len(self._buf)

    def flush(self):
        return None

    def write(self, data):
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd.startswith("j "):
            unit = cmd.split()[-1]
            self._buf.extend(f"Selected Unit: {unit}\n".encode("utf-8"))
            return
        if cmd.startswith("save,"):
            values = cmd.split(",")[1:]
            lines = []
            for idx, val in enumerate(values):
                typ = "double" if idx < 8 else "float"
                lines.append(f"{idx} ({typ}): {float(val):.10f}")
            lines.append("Confirm write to EEPROM? (y/n)")
            self._buf.extend(("\n".join(lines) + "\n").encode("utf-8"))
            return
        if cmd == "y":
            self._buf.extend(b"verification successful\n")

    def read(self, n):
        n = min(n, len(self._buf))
        out = self._buf[:n]
        del self._buf[:n]
        return bytes(out)


def _coef_file_text():
    return """SENSOR 1
TEMPERATURE CALIBRATION:
  Scale: 1.1234567890
  Offset: -0.1234567890
DUAL-RANGE ALY MODEL 2:
HIGH RANGE (C > 0.002 S/cm):
  K: 4.1000000000
  Alpha: 0.0200000000
  Eta: 1.0000000000
  Zeta: 0.0000000000
LOW RANGE (C <= 0.002 S/cm):
  K: 4.2000000000
  Alpha: 0.0210000000
  Eta: 1.0000000000
  Zeta: 0.0000000000
GLOBAL MODEL (All Data - For Prospective Discrimination):
  K: 4.3000000000
  Alpha: 0.0220000000
  Eta: 1.0000000000
  Zeta: 0.0000000000

SENSOR 2
TEMPERATURE CALIBRATION:
  Scale: 1.2234567890
  Offset: -0.2234567890
DUAL-RANGE ALY MODEL 2:
HIGH RANGE (C > 0.002 S/cm):
  K: 5.1000000000
  Alpha: 0.0230000000
  Eta: 1.0000000000
  Zeta: 0.0000000000
LOW RANGE (C <= 0.002 S/cm):
  K: 5.2000000000
  Alpha: 0.0240000000
  Eta: 1.0000000000
  Zeta: 0.0000000000
GLOBAL MODEL (All Data - For Prospective Discrimination):
  K: 5.3000000000
  Alpha: 0.0250000000
  Eta: 1.0000000000
  Zeta: 0.0000000000

CALIBRATION ACCEPTANCE STATUS
J1: ACCEPTED
J2: REJECTED
"""


def test_programming_window_loads_only_accepted_coefficients():
    app = QApplication.instance() or QApplication([])
    window = ProgrammingWindow()
    with tempfile.TemporaryDirectory() as td:
        file_path = os.path.join(td, "demo_coefficients.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(_coef_file_text())
        window.load_coefficient_file(file_path)
        assert sorted(window.coefficient_data.keys()) == [1]
        assert window.sensor_combo.count() >= 1
    window.close()
    app.quit()


def test_programming_worker_happy_path_completes():
    coeffs = {
        "k_high": 4.1,
        "alpha_high": 0.02,
        "eta_high": 1.0,
        "zeta_high": 0.0,
        "k_low": 4.2,
        "alpha_low": 0.021,
        "eta_low": 1.0,
        "zeta_low": 0.0,
        "k_global": 4.3,
        "alpha_global": 0.022,
        "eta_global": 1.0,
        "zeta_global": 0.0,
        "temp_scale": 1.123456,
        "temp_offset": -0.123456,
    }
    worker = ProgrammingWorker(_FakeDeviceSerial(), [(1, coeffs)])
    completed = []
    worker.programming_complete.connect(lambda success, message: completed.append((success, message)))
    worker.run()
    assert completed
    assert completed[-1][0] is True
