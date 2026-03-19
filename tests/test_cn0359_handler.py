"""
Unit tests for CN0359Handler -- uses mock serial ports so no hardware needed.

Run with:  python -m pytest tests/test_cn0359_handler.py -v
Or:        python tests/test_cn0359_handler.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from modes.hardware.cn0359_handler import CN0359Handler, _SensorState, POLL_LINES, MAX_CONSECUTIVE_FAILS


GOOD_RESPONSE_LINES = [
    b"EXC V: 0.400000V\n",
    b"EXC FREQ: 10000.000000Hz\n",
    b"+Ip-p: 0.001234V\n",
    b"-Ip-p: 0.001230V\n",
    b"+Vp-p: 0.398000V\n",
    b"-Vp-p: 0.397000V\n",
    b"+PHASE: 1.200000deg\n",
    b"-PHASE: -1.100000deg\n",
    b"Rp-p: 322.580645Ohm\n",
    b"Rreal: 322.500000Ohm\n",
    b"Rimag: 6.740000Ohm\n",
    b"|Z|: 322.570000Ohm\n",
    b"PHASE: 1.198000deg\n",
    b"R COMBINED: 322.540000Ohm\n",
    b"cell constant: 0.080000/cm\n",
    b"temp coefficient: 5.200000\n",
    b"setup time: 0.300000\n",
    b"hold time: 0.400000\n",
    b"\n",
    b"TEMP: 25.300000'C\n",
    b"\n",
    b"conductivity: 1.067099e-03S/cm\n",
]


def make_mock_serial(response_lines=None, is_open=True):
    """Create a mock serial.Serial object that returns canned response lines."""
    mock = MagicMock()
    type(mock).is_open = PropertyMock(return_value=is_open)
    mock.port = "MOCK_PORT"
    if response_lines is not None:
        mock.readline = MagicMock(side_effect=list(response_lines))
    else:
        mock.readline = MagicMock(return_value=b"")
    return mock


class TestSensorState(unittest.TestCase):
    """Tests for _SensorState bookkeeping class."""

    def test_initial_values(self):
        s = _SensorState(1, "COM3", "30")
        self.assertEqual(s.unit_id, 1)
        self.assertEqual(s.port_name, "COM3")
        self.assertEqual(s.address, "30")
        self.assertIsNone(s.ser)
        self.assertEqual(s.consecutive_failures, 0)
        self.assertIsNone(s.last_successful_poll)

    def test_failure_tracking(self):
        s = _SensorState(2, "COM5", "30")
        s.consecutive_failures = 3
        self.assertEqual(s.consecutive_failures, 3)


class TestCN0359HandlerInit(unittest.TestCase):
    """Tests for CN0359Handler initialization."""

    def test_default_values(self):
        h = CN0359Handler([(1, "COM3", "30")])
        self.assertEqual(h.baudrate, 115200)
        self.assertFalse(h.running)
        self.assertFalse(h.paused)
        self.assertEqual(len(h.sensors), 0)  # not populated until run()

    def test_custom_baudrate(self):
        h = CN0359Handler([(1, "COM3", "30")], baudrate=9600)
        self.assertEqual(h.baudrate, 9600)

    def test_custom_interval(self):
        h = CN0359Handler([(1, "COM3", "30")], query_interval=5.0)
        self.assertEqual(h.query_interval, 5.0)

    def test_multiple_sensor_configs(self):
        configs = [(1, "COM3", "30"), (2, "COM5", "31"), (3, "COM7", "32")]
        h = CN0359Handler(configs)
        self.assertEqual(len(h.sensor_configs), 3)


class TestCN0359HandlerPollOneSensor(unittest.TestCase):
    """Tests for _poll_one_sensor() with mocked serial."""

    def setUp(self):
        self.handler = CN0359Handler([(1, "COM3", "30")])
        self.handler.running = True

    def test_successful_poll(self):
        sensor = _SensorState(1, "COM3", "30")
        sensor.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        result = self.handler._poll_one_sensor(sensor)
        self.assertIsNotNone(result)
        self.assertIn("conductivity:", result)
        self.assertIn("TEMP:", result)
        sensor.ser.write.assert_called_once_with(b"poll\n")
        sensor.ser.reset_input_buffer.assert_called_once()

    def test_timeout_returns_none(self):
        sensor = _SensorState(1, "COM3", "30")
        # readline returns empty bytes (simulates timeout -- no data)
        sensor.ser = make_mock_serial()
        sensor.ser.readline = MagicMock(return_value=b"")
        # _poll_one_sensor will loop until PER_SENSOR_TIMEOUT, then return None
        result = self.handler._poll_one_sensor(sensor)
        self.assertIsNone(result)

    def test_partial_response_returns_none(self):
        sensor = _SensorState(1, "COM3", "30")
        sensor.ser = make_mock_serial()
        # 5 real lines then empty bytes forever (simulates sensor dying mid-response)
        real_lines = list(GOOD_RESPONSE_LINES[:5])
        call_count = {"n": 0}
        def fake_readline():
            call_count["n"] += 1
            if call_count["n"] <= len(real_lines):
                return real_lines[call_count["n"] - 1]
            return b""
        sensor.ser.readline = fake_readline
        result = self.handler._poll_one_sensor(sensor)
        self.assertIsNone(result)

    def test_correct_command_sent(self):
        sensor = _SensorState(3, "COM7", "42")
        sensor.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        self.handler._poll_one_sensor(sensor)
        sensor.ser.write.assert_called_once_with(b"poll\n")

    def test_running_false_aborts(self):
        self.handler.running = False
        sensor = _SensorState(1, "COM3", "30")
        sensor.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        result = self.handler._poll_one_sensor(sensor)
        self.assertIsNone(result)


class TestCN0359HandlerPollAll(unittest.TestCase):
    """Tests for _poll_all_sensors() with mocked sensors."""

    def setUp(self):
        self.handler = CN0359Handler([(1, "COM3", "30"), (2, "COM5", "30")])
        self.handler.running = True

    def test_all_sensors_respond(self):
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        s2 = _SensorState(2, "COM5", "30")
        s2.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        self.handler.sensors = [s1, s2]

        responses = self.handler._poll_all_sensors()
        self.assertEqual(len(responses), 2)
        self.assertIn(1, responses)
        self.assertIn(2, responses)

    def test_one_sensor_fails_other_succeeds(self):
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        s2 = _SensorState(2, "COM5", "30")
        s2.ser = make_mock_serial()  # will timeout
        s2.ser.readline = MagicMock(return_value=b"")
        self.handler.sensors = [s1, s2]

        responses = self.handler._poll_all_sensors()
        self.assertEqual(len(responses), 1)
        self.assertIn(1, responses)
        self.assertNotIn(2, responses)

    def test_failure_counter_increments(self):
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial()
        s1.ser.readline = MagicMock(return_value=b"")
        self.handler.sensors = [s1]

        self.handler._poll_all_sensors()
        self.assertEqual(s1.consecutive_failures, 1)

        # Reset mock for second poll
        s1.ser.readline = MagicMock(return_value=b"")
        self.handler._poll_all_sensors()
        self.assertEqual(s1.consecutive_failures, 2)

    def test_success_resets_failure_counter(self):
        s1 = _SensorState(1, "COM3", "30")
        s1.consecutive_failures = 4
        s1.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        self.handler.sensors = [s1]

        self.handler._poll_all_sensors()
        self.assertEqual(s1.consecutive_failures, 0)
        self.assertIsNotNone(s1.last_successful_poll)

    def test_closed_port_skipped(self):
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial(is_open=False)
        self.handler.sensors = [s1]

        responses = self.handler._poll_all_sensors()
        self.assertEqual(len(responses), 0)

    def test_none_serial_skipped(self):
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = None
        self.handler.sensors = [s1]

        responses = self.handler._poll_all_sensors()
        self.assertEqual(len(responses), 0)


class TestCN0359HandlerLifecycle(unittest.TestCase):
    """Tests for pause/resume/stop/close."""

    def test_pause_resume(self):
        h = CN0359Handler([(1, "COM3", "30")])
        self.assertFalse(h.paused)
        h.pause()
        self.assertTrue(h.paused)
        h.resume()
        self.assertFalse(h.paused)

    def test_close_connection(self):
        h = CN0359Handler([(1, "COM3", "30")])
        s = _SensorState(1, "COM3", "30")
        mock_ser = make_mock_serial()
        s.ser = mock_ser
        h.sensors = [s]

        h.close_connection()
        mock_ser.close.assert_called_once()
        self.assertIsNone(s.ser)

    def test_close_handles_error_gracefully(self):
        h = CN0359Handler([(1, "COM3", "30")])
        s = _SensorState(1, "COM3", "30")
        s.ser = make_mock_serial()
        s.ser.close.side_effect = Exception("port stuck")
        h.sensors = [s]

        h.close_connection()  # should not raise
        self.assertIsNone(s.ser)

    def test_write_data_broadcasts(self):
        h = CN0359Handler([(1, "COM3", "30"), (2, "COM5", "30")])
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial()
        s2 = _SensorState(2, "COM5", "30")
        s2.ser = make_mock_serial()
        h.sensors = [s1, s2]

        h.write_data("test data")
        s1.ser.write.assert_called_once_with(b"test data")
        s2.ser.write.assert_called_once_with(b"test data")

    def test_write_data_bytes(self):
        h = CN0359Handler([(1, "COM3", "30")])
        s = _SensorState(1, "COM3", "30")
        s.ser = make_mock_serial()
        h.sensors = [s]

        h.write_data(b"raw bytes")
        s.ser.write.assert_called_once_with(b"raw bytes")


class TestCN0359HandlerEmptyAddress(unittest.TestCase):
    """Tests for empty-address (no prefix) polling -- matches boards that
    respond to bare 'poll\\n' instead of '30 poll\\n'."""

    def setUp(self):
        self.handler = CN0359Handler([(1, "COM3", "")])
        self.handler.running = True

    def test_poll_with_empty_address(self):
        sensor = _SensorState(1, "COM3", "")
        sensor.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        result = self.handler._poll_one_sensor(sensor)
        self.assertIsNotNone(result)
        sensor.ser.write.assert_called_once_with(b"poll\n")

    def test_poll_with_address_still_sends_bare_poll(self):
        sensor = _SensorState(1, "COM3", "42")
        sensor.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        self.handler._poll_one_sensor(sensor)
        sensor.ser.write.assert_called_once_with(b"poll\n")


class TestCN0359HandlerSerialExceptions(unittest.TestCase):
    """Tests for SerialException handling during poll operations."""

    def setUp(self):
        self.handler = CN0359Handler([(1, "COM3", "30"), (2, "COM5", "30")])
        self.handler.running = True
        self.handler.error_occurred = MagicMock()

    def test_serial_exception_during_readline(self):
        import serial
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial()
        s1.ser.readline = MagicMock(side_effect=serial.SerialException("USB disconnected"))
        s2 = _SensorState(2, "COM5", "30")
        s2.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        self.handler.sensors = [s1, s2]

        responses = self.handler._poll_all_sensors()
        self.assertNotIn(1, responses)
        self.assertIn(2, responses)
        self.assertEqual(s1.consecutive_failures, 1)
        self.assertTrue(self.handler.error_occurred.emit.called)

    def test_serial_exception_during_write(self):
        import serial
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial()
        s1.ser.write = MagicMock(side_effect=serial.SerialException("port gone"))
        s2 = _SensorState(2, "COM5", "30")
        s2.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        self.handler.sensors = [s1, s2]

        responses = self.handler._poll_all_sensors()
        self.assertNotIn(1, responses)
        self.assertIn(2, responses)
        self.assertEqual(s1.consecutive_failures, 1)

    def test_max_consecutive_fails_emits_warning(self):
        s1 = _SensorState(1, "COM3", "30")
        s1.ser = make_mock_serial()
        s1.ser.readline = MagicMock(return_value=b"")
        s1.consecutive_failures = MAX_CONSECUTIVE_FAILS - 1
        self.handler.sensors = [s1]

        self.handler._poll_all_sensors()
        self.assertEqual(s1.consecutive_failures, MAX_CONSECUTIVE_FAILS)
        calls = [str(c) for c in self.handler.error_occurred.emit.call_args_list]
        has_threshold_warning = any("consecutive failures" in c for c in calls)
        self.assertTrue(has_threshold_warning)


class TestCN0359PreflightSnapshot(unittest.TestCase):
    """Tests for startup preflight status snapshot."""

    def test_preflight_detects_good_sensor(self):
        handler = CN0359Handler([(1, "COM3", "")], query_interval=1)
        handler.running = True
        s = _SensorState(1, "COM3", "")
        s.ser = make_mock_serial(GOOD_RESPONSE_LINES)
        handler.sensors = [s]

        snap = handler.preflight_snapshot(attempts=1)
        self.assertEqual(len(snap), 1)
        self.assertTrue(snap[0]["detected"])
        self.assertTrue(snap[0]["parse_ok"])
        self.assertGreater(snap[0]["non_empty_lines"], 0)

    def test_preflight_marks_no_data_sensor(self):
        handler = CN0359Handler([(1, "COM3", "")], query_interval=1)
        handler.running = True
        s = _SensorState(1, "COM3", "")
        s.ser = make_mock_serial()
        s.ser.readline = MagicMock(return_value=b"")
        handler.sensors = [s]

        snap = handler.preflight_snapshot(attempts=1)
        self.assertEqual(len(snap), 1)
        self.assertFalse(snap[0]["detected"])
        self.assertFalse(snap[0]["parse_ok"])
        self.assertEqual(snap[0]["non_empty_lines"], 0)


class TestCN0359HandlerOpenConnections(unittest.TestCase):
    """Tests for _open_connections with failing ports."""

    @patch('modes.hardware.cn0359_handler.serial.Serial')
    @patch('modes.hardware.cn0359_handler.time.sleep')
    def test_open_connections_one_port_fails(self, mock_sleep, mock_serial_cls):
        import serial
        good_mock = MagicMock()
        type(good_mock).is_open = PropertyMock(return_value=True)

        def side_effect(port, **kw):
            if port == "COM_BAD":
                raise serial.SerialException("port not found")
            return good_mock

        mock_serial_cls.side_effect = side_effect

        h = CN0359Handler([(1, "COM3", "30"), (2, "COM_BAD", "30")])
        h.error_occurred = MagicMock()
        h.disconnected = MagicMock()
        h._open_connections()

        self.assertEqual(len(h.sensors), 2)
        self.assertIsNotNone(h.sensors[0].ser)
        self.assertIsNone(h.sensors[1].ser)
        self.assertTrue(h.error_occurred.emit.called)
        h.disconnected.emit.assert_not_called()

    @patch('modes.hardware.cn0359_handler.serial.Serial')
    @patch('modes.hardware.cn0359_handler.time.sleep')
    def test_open_connections_all_fail(self, mock_sleep, mock_serial_cls):
        import serial
        mock_serial_cls.side_effect = serial.SerialException("all ports fail")

        h = CN0359Handler([(1, "COM3", "30"), (2, "COM5", "30")])
        h.error_occurred = MagicMock()
        h.disconnected = MagicMock()
        h._open_connections()

        self.assertTrue(all(s.ser is None for s in h.sensors))
        h.disconnected.emit.assert_called_once()

    @patch('modes.hardware.cn0359_handler.serial.Serial')
    def test_open_connections_emulator_bypasses_physical_serial(self, mock_serial_cls):
        h = CN0359Handler([(1, "EMULATOR1", "")])
        h.error_occurred = MagicMock()
        h.disconnected = MagicMock()
        h._open_connections()

        self.assertEqual(len(h.sensors), 1)
        self.assertIsNotNone(h.sensors[0].ser)
        self.assertTrue(h.sensors[0].ser.is_open)
        mock_serial_cls.assert_not_called()
        h.disconnected.emit.assert_not_called()


class TestCN0359HandlerEdgeCases(unittest.TestCase):
    """Tests for edge cases: garbled bytes, encode errors, stop timeout."""

    def test_garbled_bytes_decoded_safely(self):
        handler = CN0359Handler([(1, "COM3", "30")])
        handler.running = True
        sensor = _SensorState(1, "COM3", "30")
        garbled_lines = [b"\xff\xfe\x00garbage\n"] + list(GOOD_RESPONSE_LINES[1:])
        sensor.ser = make_mock_serial(garbled_lines)
        result = handler._poll_one_sensor(sensor)
        self.assertIsNotNone(result)

    def test_write_data_encode_error(self):
        h = CN0359Handler([(1, "COM3", "30")])
        h.error_occurred = MagicMock()
        s = _SensorState(1, "COM3", "30")
        s.ser = make_mock_serial()
        s.ser.write = MagicMock(side_effect=Exception("encode error"))
        h.sensors = [s]
        h.write_data("test")
        self.assertTrue(h.error_occurred.emit.called)

    def test_stop_sets_running_false(self):
        h = CN0359Handler([(1, "COM3", "30")])
        h.running = True
        h.wait = MagicMock(return_value=True)
        h.stop()
        self.assertFalse(h.running)
        h.wait.assert_called_once_with(5000)

    def test_stop_force_terminates_on_timeout(self):
        h = CN0359Handler([(1, "COM3", "30")])
        h.running = True
        h.wait = MagicMock(return_value=False)
        h.terminate = MagicMock()
        h.stop()
        self.assertFalse(h.running)
        h.terminate.assert_called_once()

    def test_emulator_poll_returns_parseable_payload(self):
        h = CN0359Handler([(1, "EMULATOR1", "")])
        h.running = True
        h._open_connections()
        self.assertEqual(len(h.sensors), 1)
        response = h._poll_one_sensor(h.sensors[0])
        self.assertIsNotNone(response)
        self.assertIn("EXC FREQ:", response)
        self.assertIn("TEMP:", response)
        self.assertIn("conductivity:", response)


class TestConstants(unittest.TestCase):
    """Verify critical constants haven't been accidentally changed."""

    def test_poll_lines(self):
        self.assertEqual(POLL_LINES, 22)

    def test_max_consecutive_fails(self):
        self.assertEqual(MAX_CONSECUTIVE_FAILS, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
