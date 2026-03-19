"""
Integration tests: handler -> parser -> data format, end to end.
Uses the same FakeSerial from live_demo.py to run the real handler,
then validates the parsed output matches what DataManager/GraphManager expect.

Run with:  python -m pytest tests/test_integration.py -v
"""
import sys, os, time, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import MagicMock, PropertyMock

from modes.controllers.cn0359_parser import CN0359Parser
from modes.hardware.cn0359_handler import CN0359Handler, _SensorState, POLL_LINES


# ---------------------------------------------------------------------------
# FakeSerial (same concept as live_demo.py, self-contained here)
# ---------------------------------------------------------------------------
class FakeSerial:
    def __init__(self, port, baudrate=115200, timeout=None, **kw):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout or 0.2
        self.is_open = True
        self._buf = b""
        self._lock = threading.Lock()
        self._cond = 1.067e-03
        self._temp = 25.3

    def write(self, data):
        cmd = data.decode('ascii', errors='replace').strip()
        if cmd.endswith("poll"):
            resp = self._make_response()
            with self._lock:
                self._buf += resp.encode('ascii')

    def readline(self):
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            with self._lock:
                idx = self._buf.find(b'\n')
                if idx >= 0:
                    line, self._buf = self._buf[:idx+1], self._buf[idx+1:]
                    return line
            time.sleep(0.002)
        return b""

    def reset_input_buffer(self):
        with self._lock:
            self._buf = b""

    def flush(self):
        pass

    def close(self):
        self.is_open = False

    def _make_response(self):
        r = 1.0 / self._cond
        lines = [
            f"EXC V: 0.400000V",
            f"EXC FREQ: 10000.000000Hz",
            "+Ip-p: 0.001234V", "-Ip-p: 0.001230V",
            "+Vp-p: 0.398000V", "-Vp-p: 0.397000V",
            "+PHASE: 1.200000deg", "-PHASE: -1.100000deg",
            f"Rp-p: {r:.6f}Ohm", f"Rreal: {r:.6f}Ohm",
            "Rimag: 6.740000Ohm", f"|Z|: {r:.6f}Ohm",
            "PHASE: 1.198000deg", f"R COMBINED: {r:.6f}Ohm",
            "cell constant: 0.080000/cm", "temp coefficient: 5.200000",
            "setup time: 0.300000", "hold time: 0.400000",
            "",
            f"TEMP: {self._temp:.6f}'C",
            "",
            f"conductivity: {self._cond:.6e}S/cm",
        ]
        return "\n".join(lines) + "\n"


class FakeSerialDead:
    """A serial port that never responds (simulates disconnected sensor)."""
    def __init__(self, port, baudrate=115200, timeout=None, **kw):
        self.port = port
        self.is_open = True
        self.timeout = timeout or 0.2

    def write(self, data):
        pass

    def readline(self):
        time.sleep(self.timeout)
        return b""

    def reset_input_buffer(self):
        pass

    def flush(self):
        pass

    def close(self):
        self.is_open = False


class FakeSerialCorrupt:
    """A serial port that returns garbage data."""
    def __init__(self, port, baudrate=115200, timeout=None, **kw):
        self.port = port
        self.is_open = True
        self.timeout = timeout or 0.2
        self._lines_sent = 0

    def write(self, data):
        self._lines_sent = 0

    def readline(self):
        self._lines_sent += 1
        if self._lines_sent <= POLL_LINES:
            return f"GARBAGE LINE {self._lines_sent}\n".encode('ascii')
        return b""

    def reset_input_buffer(self):
        pass

    def flush(self):
        pass

    def close(self):
        self.is_open = False


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------
class TestHandlerToParserIntegration(unittest.TestCase):
    """End-to-end: handler polls fake sensor -> parser produces valid output."""

    def test_single_sensor_full_pipeline(self):
        """Handler polls one sensor, parser produces correct data structure."""
        handler = CN0359Handler([(1, "FAKE1", "30")])
        handler.running = True
        s = _SensorState(1, "FAKE1", "30")
        s.ser = FakeSerial("FAKE1")
        handler.sensors = [s]

        responses = handler._poll_all_sensors()
        self.assertEqual(len(responses), 1)
        self.assertIn(1, responses)

        timestamp = "14:30:05.000"
        parsed = CN0359Parser.parse_all_sensors(responses, timestamp)

        self.assertIn('timestamp', parsed)
        self.assertIn('timestamp_str', parsed)
        self.assertIn('dut_units', parsed)
        self.assertIn('reference_devices', parsed)
        self.assertEqual(len(parsed['dut_units']), 1)

        unit = parsed['dut_units'][0]
        self.assertEqual(unit['unit_id'], 1)
        expected_cond = 1.067e-03
        self.assertAlmostEqual(unit['conductivity']['conductivity_s_cm'], expected_cond, places=8)
        self.assertAlmostEqual(unit['conductivity']['rzmag'], 1.0 / expected_cond, places=3)
        self.assertAlmostEqual(unit['temperature']['temperature_c'], 25.3, places=1)
        # Temperature rzmag stores derived RTD resistance (Ohm), not degC.
        self.assertGreater(unit['temperature']['rzmag'], 900.0)
        self.assertAlmostEqual(unit['conductivity']['frequency'], 10000.0, places=0)
        self.assertEqual(unit['conductivity']['rzphase'], 0.0)
        self.assertEqual(unit['temperature']['rzphase'], 0.0)

    def test_multi_sensor_full_pipeline(self):
        """Handler polls 3 sensors, parser produces sorted output."""
        handler = CN0359Handler([(1, "F1", "30"), (2, "F2", "30"), (3, "F3", "30")])
        handler.running = True

        for uid, port, addr in [(1, "F1", "30"), (2, "F2", "30"), (3, "F3", "30")]:
            s = _SensorState(uid, port, addr)
            s.ser = FakeSerial(port)
            handler.sensors.append(s)

        responses = handler._poll_all_sensors()
        parsed = CN0359Parser.parse_all_sensors(responses, "10:00:00.000")

        self.assertEqual(len(parsed['dut_units']), 3)
        ids = [u['unit_id'] for u in parsed['dut_units']]
        self.assertEqual(ids, [1, 2, 3])

    def test_dead_sensor_doesnt_block_others(self):
        """One dead sensor times out; the other still produces data."""
        handler = CN0359Handler([(1, "GOOD", "30"), (2, "DEAD", "30")])
        handler.running = True

        s1 = _SensorState(1, "GOOD", "30")
        s1.ser = FakeSerial("GOOD")
        s2 = _SensorState(2, "DEAD", "30")
        s2.ser = FakeSerialDead("DEAD")
        handler.sensors = [s1, s2]

        responses = handler._poll_all_sensors()
        self.assertIn(1, responses)
        self.assertNotIn(2, responses)

        parsed = CN0359Parser.parse_all_sensors(responses, "12:00:00.000")
        self.assertEqual(len(parsed['dut_units']), 1)
        self.assertEqual(parsed['dut_units'][0]['unit_id'], 1)

    def test_corrupt_sensor_parsed_as_none(self):
        """Sensor returns garbage -> parser skips it gracefully."""
        handler = CN0359Handler([(1, "CORRUPT", "30")])
        handler.running = True

        s = _SensorState(1, "CORRUPT", "30")
        s.ser = FakeSerialCorrupt("CORRUPT")
        handler.sensors = [s]

        responses = handler._poll_all_sensors()
        self.assertEqual(len(responses), 1)

        parsed = CN0359Parser.parse_all_sensors(responses, "12:00:00.000")
        self.assertEqual(len(parsed['dut_units']), 0)

    def test_mixed_good_and_corrupt(self):
        """One good sensor + one corrupt -> only good sensor in output."""
        handler = CN0359Handler([(1, "GOOD", "30"), (2, "BAD", "30")])
        handler.running = True

        s1 = _SensorState(1, "GOOD", "30")
        s1.ser = FakeSerial("GOOD")
        s2 = _SensorState(2, "BAD", "30")
        s2.ser = FakeSerialCorrupt("BAD")
        handler.sensors = [s1, s2]

        responses = handler._poll_all_sensors()
        parsed = CN0359Parser.parse_all_sensors(responses, "12:00:00.000")

        self.assertEqual(len(parsed['dut_units']), 1)
        self.assertEqual(parsed['dut_units'][0]['unit_id'], 1)

    def test_output_compatible_with_data_manager(self):
        """Verify exact dict keys that DataManager.store_measurement() expects."""
        handler = CN0359Handler([(1, "F1", "30")])
        handler.running = True
        s = _SensorState(1, "F1", "30")
        s.ser = FakeSerial("F1")
        handler.sensors = [s]

        responses = handler._poll_all_sensors()
        parsed = CN0359Parser.parse_all_sensors(responses, "14:00:00.000")

        required_top_keys = {'timestamp', 'timestamp_str', 'dut_units', 'reference_devices'}
        self.assertEqual(set(parsed.keys()), required_top_keys)

        unit = parsed['dut_units'][0]
        required_unit_keys = {'unit_id', 'conductivity', 'temperature'}
        self.assertEqual(set(unit.keys()), required_unit_keys)

        for measurement_key in ('conductivity', 'temperature'):
            measurement = unit[measurement_key]
            required_meas_keys = {'frequency', 'rzmag', 'rzphase'}
            self.assertTrue(required_meas_keys.issubset(set(measurement.keys())))
            for base_key in required_meas_keys:
                self.assertIsInstance(measurement[base_key], float)
        self.assertIn('conductivity_s_cm', unit['conductivity'])
        self.assertIn('temperature_c', unit['temperature'])
        for v in unit['conductivity'].values():
            self.assertIsInstance(v, float)
        for v in unit['temperature'].values():
                self.assertIsInstance(v, float)


class TestHandlerValidation(unittest.TestCase):
    """Tests for constructor validation."""

    def test_empty_config_raises(self):
        with self.assertRaises(ValueError):
            CN0359Handler([])

    def test_min_query_interval_enforced(self):
        h = CN0359Handler([(1, "X", "30")], query_interval=0.01)
        self.assertGreaterEqual(h.query_interval, 0.1)


class TestConfigValidation(unittest.TestCase):
    """Tests for settings.py CN0359 config validation."""

    def test_valid_config_loads(self):
        from modes.utils.settings import load_settings
        settings = load_settings()
        self.assertIn('CN0359_ENABLED', settings)
        self.assertIn('CN0359_BAUDRATE', settings)
        self.assertIn('CN0359_POLL_INTERVAL', settings)
        self.assertIn('CN0359_SENSORS', settings)
        self.assertIsInstance(settings['CN0359_SENSORS'], list)

    def test_baudrate_is_valid(self):
        from modes.utils.settings import load_settings
        settings = load_settings()
        self.assertIn(settings['CN0359_BAUDRATE'], (9600, 19200, 38400, 57600, 115200))

    def test_poll_interval_positive(self):
        from modes.utils.settings import load_settings
        settings = load_settings()
        self.assertGreaterEqual(settings['CN0359_POLL_INTERVAL'], 1)


class TestEmptyAddressPipeline(unittest.TestCase):
    """End-to-end test with empty address (the real board's flow)."""

    def test_empty_address_full_pipeline(self):
        handler = CN0359Handler([(1, "COM3", "")], query_interval=1)
        handler.running = True

        sensor = _SensorState(1, "COM3", "")
        sensor.ser = FakeSerial("COM3")
        handler.sensors = [sensor]

        responses = handler._poll_all_sensors()
        self.assertIn(1, responses)

        result = CN0359Parser.parse_all_sensors(responses, "2026-02-23 10:00:00.000")
        self.assertEqual(len(result['dut_units']), 1)
        unit = result['dut_units'][0]
        expected_cond = 1.067e-03
        self.assertAlmostEqual(unit['conductivity']['conductivity_s_cm'], expected_cond, places=8)
        self.assertAlmostEqual(unit['conductivity']['rzmag'], 1.0 / expected_cond, places=3)
        self.assertAlmostEqual(unit['temperature']['temperature_c'], 25.3, places=1)


class TestFirmwareLineMismatch(unittest.TestCase):
    """Test that extra lines from firmware don't break the pipeline."""

    def test_handler_reads_22_lines_parser_still_works(self):
        handler = CN0359Handler([(1, "COM3", "30")], query_interval=1)
        handler.running = True

        sensor = _SensorState(1, "COM3", "30")
        mock_ser = MagicMock()
        type(mock_ser).is_open = PropertyMock(return_value=True)

        base_lines = [
            b"EXC V: 0.400000V\n",
            b"EXC FREQ: 10000.000000Hz\n",
            b"+Ip-p: 0.001234V\n", b"-Ip-p: 0.001230V\n",
            b"+Vp-p: 0.398000V\n", b"-Vp-p: 0.397000V\n",
            b"+PHASE: 1.200000deg\n", b"-PHASE: -1.100000deg\n",
            b"Rp-p: 322.580645Ohm\n", b"Rreal: 322.500000Ohm\n",
            b"Rimag: 6.740000Ohm\n", b"|Z|: 322.570000Ohm\n",
            b"PHASE: 1.198000deg\n", b"R COMBINED: 322.540000Ohm\n",
            b"cell constant: 0.080000/cm\n", b"temp coefficient: 5.200000\n",
            b"setup time: 0.300000\n", b"hold time: 0.400000\n",
            b"\n",
            b"TEMP: 25.300000'C\n",
            b"\n",
            b"conductivity: 1.067099e-03S/cm\n",
            b"EXTRA LINE 1\n",
            b"EXTRA LINE 2\n",
            b"EXTRA LINE 3\n",
        ]
        mock_ser.readline = MagicMock(side_effect=list(base_lines))
        sensor.ser = mock_ser
        handler.sensors = [sensor]

        responses = handler._poll_all_sensors()
        self.assertIn(1, responses)
        raw = responses[1]

        result = CN0359Parser.parse_all_sensors({1: raw}, "2026-02-23 10:00:00.000")
        self.assertEqual(len(result['dut_units']), 1)
        unit = result['dut_units'][0]
        self.assertAlmostEqual(unit['conductivity']['conductivity_s_cm'], 1.067099e-03, places=9)
        # R COMBINED is present, so rzmag should be parsed as resistance.
        self.assertAlmostEqual(unit['conductivity']['rzmag'], 322.54, places=2)


class TestCN0359EnabledNoSensors(unittest.TestCase):
    """Test that enabled=True with no sensors configured doesn't crash."""

    def test_empty_sensor_list_raises(self):
        with self.assertRaises(ValueError):
            CN0359Handler([], query_interval=1)

    def test_fallback_logic_concept(self):
        cn0359_mode = True
        cn0359_sensors = []
        use_cn0359 = cn0359_mode and cn0359_sensors
        self.assertFalse(use_cn0359)


if __name__ == "__main__":
    unittest.main(verbosity=2)
