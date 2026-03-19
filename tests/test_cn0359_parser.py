"""
Comprehensive unit tests for CN0359Parser.

Run with:  python -m pytest tests/test_cn0359_parser.py -v
Or:        python tests/test_cn0359_parser.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from modes.controllers.cn0359_parser import CN0359Parser

# ---------------------------------------------------------------------------
# Realistic 22-line sample (from CN0359 firmware cmd_poll.cpp)
# ---------------------------------------------------------------------------
GOOD_RESPONSE = (
    "EXC V: 0.400000V\n"
    "EXC FREQ: 10000.000000Hz\n"
    "+Ip-p: 0.001234V\n"
    "-Ip-p: 0.001230V\n"
    "+Vp-p: 0.398000V\n"
    "-Vp-p: 0.397000V\n"
    "+PHASE: 1.200000deg\n"
    "-PHASE: -1.100000deg\n"
    "Rp-p: 322.580645Ohm\n"
    "Rreal: 322.500000Ohm\n"
    "Rimag: 6.740000Ohm\n"
    "|Z|: 322.570000Ohm\n"
    "PHASE: 1.198000deg\n"
    "R COMBINED: 322.540000Ohm\n"
    "cell constant: 0.080000/cm\n"
    "temp coefficient: 5.200000\n"
    "setup time: 0.300000\n"
    "hold time: 0.400000\n"
    "\n"
    "TEMP: 25.300000'C\n"
    "\n"
    "conductivity: 1.067099e-03S/cm\n"
)

# Real V2 firmware sample captured from CN0359Troubleshooter output.
V2_RESPONSE = (
    "EXC V: 1.000000V\n"
    "EXC FREQ: 10000.000000Hz\n"
    "EXC setup time: 10.000000%\n"
    "EXC hold time: 1.000000%\n"
    "TEMP COEF: 2.000000%/'C\n"
    "cell K: 1.000000/cm\n"
    "ADC0 hits: 363618\n"
    "+I gain: 1000\n"
    "+Ip-p: -1.721084e-11A\n"
    "-I gain: 1000\n"
    "-Ip-p: 1.229346e-11A\n"
    "+V gain: 10\n"
    "+Vp-p: 1.474715e+00V\n"
    "-V gain: 10\n"
    "-Vp-p: -1.473636e+00V\n"
    "ADC1 hits: 53080\n"
    "RTD: PT1000\n"
    "RTD wire: 4 wire\n"
    "TEMP: 34.504932'C\n"
    "\n"
    "conductivity: -8.408589e-12S/cm\n"
    "\n"
)


class TestParsePollResponse(unittest.TestCase):
    """Tests for CN0359Parser.parse_poll_response()"""

    # ---- Happy path ----

    def test_good_response_returns_dict(self):
        result = CN0359Parser.parse_poll_response(GOOD_RESPONSE)
        self.assertIsNotNone(result)
        self.assertIn('conductivity', result)
        self.assertIn('temperature', result)

    def test_conductivity_value(self):
        result = CN0359Parser.parse_poll_response(GOOD_RESPONSE)
        self.assertAlmostEqual(result['conductivity']['rzmag'], 322.540000, places=6)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 1.067099e-03, places=10)

    def test_temperature_value(self):
        result = CN0359Parser.parse_poll_response(GOOD_RESPONSE)
        self.assertAlmostEqual(result['temperature']['rzmag'], 1098.510338025, places=6)
        self.assertAlmostEqual(result['temperature']['temperature_c'], 25.3, places=2)

    def test_frequency_value(self):
        result = CN0359Parser.parse_poll_response(GOOD_RESPONSE)
        self.assertAlmostEqual(result['conductivity']['frequency'], 10000.0, places=1)

    def test_v2_firmware_response_parses(self):
        """Regression test for real V2 board output format."""
        result = CN0359Parser.parse_poll_response(V2_RESPONSE)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['conductivity']['frequency'], 10000.0, places=1)
        self.assertAlmostEqual(result['temperature']['rzmag'], 1134.1680598186824, places=6)
        self.assertAlmostEqual(result['temperature']['temperature_c'], 34.504932, places=6)
        self.assertAlmostEqual(result['conductivity']['rzmag'], 99929535694.79701, places=2)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], -8.408589e-12, places=18)

    def test_rzphase_always_zero(self):
        result = CN0359Parser.parse_poll_response(GOOD_RESPONSE)
        self.assertEqual(result['conductivity']['rzphase'], 0.0)
        self.assertEqual(result['temperature']['rzphase'], 0.0)

    def test_temperature_frequency_always_zero(self):
        result = CN0359Parser.parse_poll_response(GOOD_RESPONSE)
        self.assertEqual(result['temperature']['frequency'], 0.0)

    # ---- Scientific notation variants ----

    def test_large_conductivity_scientific(self):
        resp = GOOD_RESPONSE.replace("1.067099e-03", "5.432100e+02")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 543.21, places=2)

    def test_negative_exponent(self):
        resp = GOOD_RESPONSE.replace("1.067099e-03", "9.99e-07")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 9.99e-07, places=13)

    def test_uppercase_E_scientific(self):
        resp = GOOD_RESPONSE.replace("1.067099e-03", "1.5E+01")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 15.0, places=1)

    def test_plain_decimal_conductivity(self):
        resp = GOOD_RESPONSE.replace("1.067099e-03", "0.001067")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 0.001067, places=6)

    def test_integer_conductivity(self):
        resp = GOOD_RESPONSE.replace("1.067099e-03", "42")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 42.0, places=1)

    # ---- Temperature variants ----

    def test_high_temperature(self):
        resp = GOOD_RESPONSE.replace("25.300000", "99.900000")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertAlmostEqual(result['temperature']['rzmag'], 1384.675714225, places=6)
        self.assertAlmostEqual(result['temperature']['temperature_c'], 99.9, places=1)

    def test_low_temperature(self):
        resp = GOOD_RESPONSE.replace("25.300000", "0.100000")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertAlmostEqual(result['temperature']['rzmag'], 1000.390824225, places=6)
        self.assertAlmostEqual(result['temperature']['temperature_c'], 0.1, places=1)

    # ---- Missing / malformed fields ----

    def test_missing_conductivity_returns_none(self):
        resp = GOOD_RESPONSE.replace("conductivity:", "GARBAGE:")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertIsNone(result)

    def test_missing_temperature_returns_none(self):
        resp = GOOD_RESPONSE.replace("TEMP:", "GARBAGE:")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertIsNone(result)

    def test_missing_frequency_still_works(self):
        resp = GOOD_RESPONSE.replace("EXC FREQ:", "GARBAGE:")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertIsNotNone(result)
        self.assertEqual(result['conductivity']['frequency'], 0.0)

    def test_empty_string_returns_none(self):
        result = CN0359Parser.parse_poll_response("")
        self.assertIsNone(result)

    def test_garbage_string_returns_none(self):
        result = CN0359Parser.parse_poll_response("hello world\nfoo bar\n")
        self.assertIsNone(result)

    def test_partial_response_cond_only(self):
        result = CN0359Parser.parse_poll_response("conductivity: 0.005S/cm\n")
        self.assertIsNone(result)  # temperature missing

    def test_partial_response_temp_only(self):
        result = CN0359Parser.parse_poll_response("TEMP: 25.0'C\n")
        self.assertIsNone(result)  # conductivity missing

    # ---- Whitespace / formatting edge cases ----

    def test_extra_whitespace_around_values(self):
        resp = (
            "EXC FREQ:   5000.0  Hz\n"
            "TEMP COEF: 0.0%/'C\n"
            "cell K: 1.0/cm\n"
            "TEMP:   22.5  'C\n"
            "conductivity:   0.001  S/cm\n"
        )
        result = CN0359Parser.parse_poll_response(resp)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['conductivity']['rzmag'], 1000.0, places=1)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 0.001, places=6)
        self.assertAlmostEqual(result['temperature']['rzmag'], 1087.644390625, places=6)
        self.assertAlmostEqual(result['temperature']['temperature_c'], 22.5, places=1)

    def test_no_trailing_newlines(self):
        resp = "TEMP: 20.0'C\nconductivity: 0.005S/cm"
        result = CN0359Parser.parse_poll_response(resp)
        self.assertIsNone(result)

    def test_windows_line_endings(self):
        resp = GOOD_RESPONSE.replace("\n", "\r\n")
        result = CN0359Parser.parse_poll_response(resp)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['conductivity']['rzmag'], 322.540000, places=6)


class TestParseAllSensors(unittest.TestCase):
    """Tests for CN0359Parser.parse_all_sensors()"""

    def test_single_sensor(self):
        responses = {1: GOOD_RESPONSE}
        result = CN0359Parser.parse_all_sensors(responses, "14:30:05.123")
        self.assertEqual(len(result['dut_units']), 1)
        self.assertEqual(result['dut_units'][0]['unit_id'], 1)
        self.assertEqual(result['timestamp_str'], "14:30:05.123")
        self.assertEqual(result['reference_devices'], [])

    def test_multiple_sensors(self):
        responses = {
            1: GOOD_RESPONSE,
            3: GOOD_RESPONSE.replace("25.300000", "26.100000")
                            .replace("1.067099e-03", "2.15e-03"),
            5: GOOD_RESPONSE.replace("25.300000", "24.000000")
                            .replace("1.067099e-03", "3.00e-03"),
        }
        result = CN0359Parser.parse_all_sensors(responses, "10:00:00.000")
        self.assertEqual(len(result['dut_units']), 3)
        ids = [u['unit_id'] for u in result['dut_units']]
        self.assertEqual(ids, [1, 3, 5])  # sorted

    def test_sensors_sorted_by_id(self):
        responses = {6: GOOD_RESPONSE, 2: GOOD_RESPONSE, 4: GOOD_RESPONSE}
        result = CN0359Parser.parse_all_sensors(responses, "12:00:00.000")
        ids = [u['unit_id'] for u in result['dut_units']]
        self.assertEqual(ids, [2, 4, 6])

    def test_bad_sensor_skipped(self):
        responses = {
            1: GOOD_RESPONSE,
            2: "total garbage with no valid data",
        }
        result = CN0359Parser.parse_all_sensors(responses, "12:00:00.000")
        self.assertEqual(len(result['dut_units']), 1)
        self.assertEqual(result['dut_units'][0]['unit_id'], 1)

    def test_all_sensors_bad_returns_empty(self):
        responses = {
            1: "garbage",
            2: "more garbage",
        }
        result = CN0359Parser.parse_all_sensors(responses, "12:00:00.000")
        self.assertEqual(len(result['dut_units']), 0)
        self.assertIn('timestamp', result)

    def test_empty_responses_dict(self):
        result = CN0359Parser.parse_all_sensors({}, "12:00:00.000")
        self.assertEqual(len(result['dut_units']), 0)

    def test_timestamp_str_preserved(self):
        result = CN0359Parser.parse_all_sensors({1: GOOD_RESPONSE}, "2026-02-11 14:30:05.123456")
        self.assertEqual(result['timestamp_str'], "2026-02-11 14:30:05.123456")

    def test_timestamp_converted_to_float(self):
        result = CN0359Parser.parse_all_sensors({1: GOOD_RESPONSE}, "14:30:05.123")
        self.assertIsInstance(result['timestamp'], float)
        self.assertGreater(result['timestamp'], 0)

    def test_output_shape_matches_data_parser(self):
        """Verify the output has exactly the keys DataManager/GraphManager expect."""
        result = CN0359Parser.parse_all_sensors({1: GOOD_RESPONSE}, "14:30:05.000")
        self.assertIn('timestamp', result)
        self.assertIn('timestamp_str', result)
        self.assertIn('dut_units', result)
        self.assertIn('reference_devices', result)
        unit = result['dut_units'][0]
        self.assertIn('unit_id', unit)
        self.assertIn('conductivity', unit)
        self.assertIn('temperature', unit)
        self.assertIn('rzmag', unit['conductivity'])
        self.assertIn('frequency', unit['conductivity'])
        self.assertIn('rzphase', unit['conductivity'])


class TestTimestampToSeconds(unittest.TestCase):
    """Tests for CN0359Parser.timestamp_to_seconds()"""

    def test_time_only_format(self):
        result = CN0359Parser.timestamp_to_seconds("14:30:05.123")
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0)

    def test_full_datetime_format(self):
        result = CN0359Parser.timestamp_to_seconds("2026-02-11 14:30:05.123456")
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0)

    def test_bad_timestamp_returns_now(self):
        result = CN0359Parser.timestamp_to_seconds("not-a-timestamp")
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0)


class TestParserMalformedValues(unittest.TestCase):
    """Tests for values that match the regex but aren't valid floats,
    or edge-case numeric values (negative, overflow)."""

    def _response_with(self, cond="1.067099e-03", temp="25.300000", freq="10000.000000"):
        return (
            f"EXC V: 0.400000V\n"
            f"EXC FREQ: {freq}Hz\n"
            f"TEMP COEF: 0.0%/'C\n"
            f"cell K: 1.000000/cm\n"
            f"TEMP: {temp}'C\n"
            f"\n"
            f"conductivity: {cond}S/cm\n"
        )

    def test_malformed_float_in_conductivity(self):
        result = CN0359Parser.parse_poll_response(self._response_with(cond="1.2.3"))
        self.assertIsNone(result)

    def test_malformed_float_in_temperature(self):
        result = CN0359Parser.parse_poll_response(self._response_with(temp="25..3"))
        self.assertIsNone(result)

    def test_overflow_conductivity(self):
        result = CN0359Parser.parse_poll_response(self._response_with(cond="1e999"))
        self.assertIsNone(result)

    def test_negative_conductivity_parsed(self):
        result = CN0359Parser.parse_poll_response(self._response_with(cond="-0.001"))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['conductivity']['rzmag'], 1000.0, places=1)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], -0.001)

    def test_duplicate_conductivity_lines_uses_first(self):
        response = (
            "EXC FREQ: 10000.0Hz\n"
            "TEMP COEF: 0.0%/'C\n"
            "cell K: 1.000000/cm\n"
            "TEMP: 25.0'C\n"
            "conductivity: 1.0e-03S/cm\n"
            "conductivity: 9.9e-03S/cm\n"
        )
        result = CN0359Parser.parse_poll_response(response)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['conductivity']['conductivity_s_cm'], 1.0e-03)


if __name__ == "__main__":
    unittest.main(verbosity=2)
