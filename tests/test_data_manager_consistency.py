"""
Consistency tests for DataManager CSV output.
"""
import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from modes.controllers import data_manager as dm_module
from modes.controllers.data_manager import DataManager


class TestDataManagerConsistency(unittest.TestCase):
    def test_csv_header_contains_eight_dut_units(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(dm_module, "SAVE_DIRECTORY", tmpdir):
                dm = DataManager(parent=None)
                try:
                    with open(dm.csv_file_path, newline="", encoding="utf-8") as f:
                        header = next(csv.reader(f))
                    self.assertIn("DUT8_Cond_Freq_Hz", header)
                    self.assertIn("DUT8_Temp_RzPhase_Deg", header)
                    self.assertIn("DUT8_Cond_Value_S_cm", header)
                    # 1 timestamp + (8 DUT * 7 cols) + (2 refs * 2 cols)
                    self.assertEqual(len(header), 61)
                finally:
                    dm.close_files()

    def test_csv_row_uses_provided_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(dm_module, "SAVE_DIRECTORY", tmpdir):
                dm = DataManager(parent=None)
                try:
                    ts = "2026-03-02 17:05:06.789"
                    dut_measurements = {
                        1: {
                            "conductivity": {"frequency": 10000.0, "rzmag": 1.23e-3, "rzphase": 0.0},
                            "temperature": {"frequency": 0.0, "rzmag": 25.4, "rzphase": 0.0},
                        }
                    }
                    ref_measurements = {1: {"conductivity_value": 1.5, "temperature_value": 24.9}}
                    dm.write_consolidated_row(ts, dut_measurements, ref_measurements)
                    dm.csv_file.flush()

                    with open(dm.csv_file_path, newline="", encoding="utf-8") as f:
                        rows = list(csv.reader(f))

                    self.assertGreaterEqual(len(rows), 2)
                    self.assertEqual(rows[1][0], ts)
                finally:
                    dm.close_files()


if __name__ == "__main__":
    unittest.main(verbosity=2)

