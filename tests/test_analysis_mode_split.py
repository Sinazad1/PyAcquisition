import os
import tempfile

import pandas as pd

from modes.analysis_mode import AnalysisWindow


def _build_measurements_df(rows=5, max_units=8):
    data = {
        "Timestamp": [f"2026-03-03 09:00:{idx:02d}.000" for idx in range(rows)],
        "Ref1_Conductivity_mS_cm": [1.0 + 0.01 * idx for idx in range(rows)],
        "Ref2_Conductivity_mS_cm": [1.1 + 0.01 * idx for idx in range(rows)],
        "Ref1_Temperature_degC": [24.0 + 0.1 * idx for idx in range(rows)],
        "Ref2_Temperature_degC": [24.2 + 0.1 * idx for idx in range(rows)],
    }
    for unit in range(1, max_units + 1):
        data[f"DUT{unit}_Cond_Freq_Hz"] = [10000.0] * rows
        data[f"DUT{unit}_Cond_RzMag_Ohm"] = [500.0 + unit + idx for idx in range(rows)]
        data[f"DUT{unit}_Cond_RzPhase_Deg"] = [0.0] * rows
        data[f"DUT{unit}_Temp_Freq_Hz"] = [0.0] * rows
        data[f"DUT{unit}_Temp_RzMag_Ohm"] = [1100.0 + unit + idx for idx in range(rows)]
        data[f"DUT{unit}_Temp_RzPhase_Deg"] = [0.0] * rows
    return pd.DataFrame(data)


def test_split_measurements_file_supports_eight_duts():
    # Avoid full QMainWindow init; split_measurements_file only needs max_dut_units.
    window = AnalysisWindow.__new__(AnalysisWindow)
    window.max_dut_units = 8

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "measurements_20260303_090000.csv")
        _build_measurements_df(rows=5, max_units=8).to_csv(src_path, index=False)

        dut_path, ipb_path = window.split_measurements_file(src_path, tmpdir)

        assert os.path.exists(dut_path)
        assert os.path.exists(ipb_path)

        dut_df = pd.read_csv(dut_path)
        assert "TIMECODE" in dut_df.columns
        assert "ConImpedance8" in dut_df.columns
        assert "TempImpedance8" in dut_df.columns

        ipb_df = pd.read_csv(ipb_path, header=None)
        assert ipb_df.shape[1] == 5
