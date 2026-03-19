import os
import tempfile

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from modes.controllers.cn0359_parser import CN0359Parser
from modes.hardware.cn0359_handler import CN0359Handler
from modes.analysis_mode import AnalysisWindow
from modes.programming_mode import ProgrammingWorker


class _FakeProgrammingSerial:
    """Deterministic serial stub for ProgrammingWorker smoke flow."""

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
            vals = cmd.split(",")[1:]
            lines = []
            for idx, val in enumerate(vals):
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


def _write_measurements_and_events(base_dir, rows=100, max_units=8):
    measurements_path = os.path.join(base_dir, "measurements_20260303_000001.csv")
    events_path = os.path.join(base_dir, "events_20260303_000001.csv")

    # Build measurements schema used by analysis mode checklist/split.
    data = {
        "Timestamp": [f"2026-03-03 10:00:{idx:02d}.000" for idx in range(rows)],
        "Ref1_Conductivity_mS_cm": [1.00 + 0.001 * idx for idx in range(rows)],
        "Ref2_Conductivity_mS_cm": [1.02 + 0.001 * idx for idx in range(rows)],
        "Ref1_Temperature_degC": [24.0 + 0.02 * idx for idx in range(rows)],
        "Ref2_Temperature_degC": [24.2 + 0.02 * idx for idx in range(rows)],
    }
    for unit in range(1, max_units + 1):
        data[f"DUT{unit}_Cond_Freq_Hz"] = [10000.0 + unit] * rows
        data[f"DUT{unit}_Cond_RzMag_Ohm"] = [700.0 + unit + 0.2 * idx for idx in range(rows)]
        data[f"DUT{unit}_Cond_RzPhase_Deg"] = [0.0] * rows
        data[f"DUT{unit}_Temp_Freq_Hz"] = [0.0] * rows
        data[f"DUT{unit}_Temp_RzMag_Ohm"] = [1100.0 + unit + 0.1 * idx for idx in range(rows)]
        data[f"DUT{unit}_Temp_RzPhase_Deg"] = [0.0] * rows
    pd.DataFrame(data).to_csv(measurements_path, index=False)

    # Events CSV in the expected simple one-column style.
    event_rows = [
        "2026-03-03 10:00:10.000",
        "2026-03-03 10:00:20.000",
        "2026-03-03 10:00:30.000",
        "2026-03-03 10:00:40.000",
        "2026-03-03 10:00:50.000",
        "2026-03-03 10:01:00.000",
        "2026-03-03 10:01:10.000",
        "2026-03-03 10:01:20.000",
        "2026-03-03 10:01:30.000",
        "2026-03-03 10:01:40.000",
    ]
    pd.DataFrame(event_rows).to_csv(events_path, index=False, header=False)
    return measurements_path, events_path


def test_offline_e2e_smoke_acquire_analyze_program():
    # 1) Acquisition-style emulator read and parser conversion.
    handler = CN0359Handler(
        [(1, "EMULATOR1", ""), (2, "EMULATOR2", ""), (3, "EMULATOR3", ""), (4, "EMULATOR4", ""),
         (5, "EMULATOR5", ""), (6, "EMULATOR6", ""), (7, "EMULATOR7", ""), (8, "EMULATOR8", "")],
        query_interval=1,
    )
    handler.running = True
    handler._open_connections()
    responses = handler._poll_all_sensors()
    assert len(responses) == 8
    parsed = CN0359Parser.parse_all_sensors(responses, "2026-03-03 10:00:00.000")
    assert len(parsed["dut_units"]) == 8

    # 2) Analysis checklist against generated measurements/events files.
    app = QApplication.instance() or QApplication([])
    window = AnalysisWindow()
    with tempfile.TemporaryDirectory() as td:
        m_path, e_path = _write_measurements_and_events(td, rows=100, max_units=8)
        window.file_mode = "measurements"
        window.file1_path = m_path
        window.event_file1_path = e_path
        assert window.run_analysis_checklist(show_dialog=False) is True
    window.close()
    app.quit()

    # 3) Programming worker end-to-end command flow.
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
    worker = ProgrammingWorker(_FakeProgrammingSerial(), [(1, coeffs)])
    completed = []
    worker.programming_complete.connect(lambda success, message: completed.append((success, message)))
    worker.run()
    assert completed and completed[-1][0] is True
