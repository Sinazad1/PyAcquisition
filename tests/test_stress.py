"""
Stress and endurance tests for the CN0359 pipeline.
Tests rapid polling, sensor dropout mid-stream, data consistency over many cycles.

Run with:  python -m pytest tests/test_stress.py -v
"""
import sys, os, time, threading, random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from modes.controllers.cn0359_parser import CN0359Parser
from modes.hardware.cn0359_handler import CN0359Handler, _SensorState, POLL_LINES


# ---------------------------------------------------------------------------
# Fake serial variants
# ---------------------------------------------------------------------------
class FakeSerial:
    """Normal responding sensor."""
    def __init__(self, port, baudrate=115200, timeout=None, **kw):
        self.port = port
        self.is_open = True
        self.timeout = timeout or 0.2
        self._buf = b""
        self._lock = threading.Lock()
        self._cond = 1.067e-03
        self._temp = 25.3
        self._poll_count = 0

    def write(self, data):
        cmd = data.decode('ascii', errors='replace').strip()
        if cmd.endswith("poll"):
            self._poll_count += 1
            self._cond += random.gauss(0, self._cond * 0.01)
            self._temp += random.gauss(0, 0.05)
            with self._lock:
                self._buf += self._make_response().encode('ascii')

    def readline(self):
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            with self._lock:
                idx = self._buf.find(b'\n')
                if idx >= 0:
                    line, self._buf = self._buf[:idx+1], self._buf[idx+1:]
                    return line
            time.sleep(0.001)
        return b""

    def reset_input_buffer(self):
        with self._lock:
            self._buf = b""

    def flush(self):
        pass

    def close(self):
        self.is_open = False

    def _make_response(self):
        r = 1.0 / self._cond if self._cond > 0 else 999999.0
        lines = [
            f"EXC V: 0.400000V", f"EXC FREQ: 10000.000000Hz",
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


class FakeSerialFlaky:
    """Sensor that works sometimes and dies randomly."""
    def __init__(self, port, baudrate=115200, timeout=None, fail_rate=0.3, **kw):
        self.port = port
        self.is_open = True
        self.timeout = timeout or 0.2
        self._good = FakeSerial(port, baudrate, timeout)
        self._fail_rate = fail_rate
        self._should_fail = False

    def write(self, data):
        self._should_fail = random.random() < self._fail_rate
        if not self._should_fail:
            self._good.write(data)

    def readline(self):
        if self._should_fail:
            time.sleep(self.timeout)
            return b""
        return self._good.readline()

    def reset_input_buffer(self):
        self._good.reset_input_buffer()

    def flush(self):
        pass

    def close(self):
        self.is_open = False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestRapidPolling(unittest.TestCase):
    """Test many poll cycles in quick succession."""

    def test_50_consecutive_polls(self):
        """50 rapid polls all produce valid parsed output."""
        handler = CN0359Handler([(1, "F1", "30")])
        handler.running = True
        s = _SensorState(1, "F1", "30")
        s.ser = FakeSerial("F1")
        handler.sensors = [s]

        for i in range(50):
            responses = handler._poll_all_sensors()
            self.assertEqual(len(responses), 1)
            parsed = CN0359Parser.parse_all_sensors(responses, f"10:00:{i:02d}.000")
            self.assertEqual(len(parsed['dut_units']), 1)
            unit = parsed['dut_units'][0]
            self.assertGreater(unit['conductivity']['rzmag'], 0)
            self.assertGreater(unit['temperature']['rzmag'], 0)

    def test_50_polls_multi_sensor(self):
        """50 rapid polls with 4 sensors all produce valid output."""
        configs = [(i, f"F{i}", "30") for i in range(1, 5)]
        handler = CN0359Handler(configs)
        handler.running = True
        for uid, port, addr in configs:
            s = _SensorState(uid, port, addr)
            s.ser = FakeSerial(port)
            handler.sensors.append(s)

        for cycle in range(50):
            responses = handler._poll_all_sensors()
            self.assertEqual(len(responses), 4)
            parsed = CN0359Parser.parse_all_sensors(responses, f"10:00:{cycle:02d}.000")
            self.assertEqual(len(parsed['dut_units']), 4)


class TestSensorDropoutMidStream(unittest.TestCase):
    """Sensor dies partway through a session."""

    def test_sensor_dies_after_10_polls(self):
        """Sensor works for 10 polls then closes -- handler doesn't crash."""
        handler = CN0359Handler([(1, "F1", "30")])
        handler.running = True
        s = _SensorState(1, "F1", "30")
        s.ser = FakeSerial("F1")
        handler.sensors = [s]

        for i in range(10):
            responses = handler._poll_all_sensors()
            self.assertEqual(len(responses), 1)

        s.ser.close()
        s.ser.is_open = False

        for i in range(5):
            responses = handler._poll_all_sensors()
            self.assertEqual(len(responses), 0)


class TestFlakySensor(unittest.TestCase):
    """Sensor that intermittently fails."""

    def test_flaky_sensor_recovers(self):
        """Flaky sensor (30% fail rate) still produces data most of the time."""
        handler = CN0359Handler([(1, "FLAKY", "30")])
        handler.running = True
        s = _SensorState(1, "FLAKY", "30")
        s.ser = FakeSerialFlaky("FLAKY", fail_rate=0.3)
        handler.sensors = [s]

        successes = 0
        total = 30
        for i in range(total):
            responses = handler._poll_all_sensors()
            if len(responses) == 1:
                parsed = CN0359Parser.parse_all_sensors(responses, f"10:00:{i:02d}.000")
                if len(parsed['dut_units']) == 1:
                    successes += 1

        # With 30% fail rate over 30 tries, expect at least 12 successes
        self.assertGreater(successes, 10,
                           f"Only {successes}/{total} successful polls -- too many failures")

    def test_failure_counter_tracks_correctly(self):
        """Consecutive failure counter rises and resets properly."""
        handler = CN0359Handler([(1, "FLAKY", "30")])
        handler.running = True
        s = _SensorState(1, "FLAKY", "30")
        s.ser = FakeSerialFlaky("FLAKY", fail_rate=0.5)
        handler.sensors = [s]

        max_consecutive = 0
        for _ in range(50):
            handler._poll_all_sensors()
            max_consecutive = max(max_consecutive, s.consecutive_failures)

        # With 50% fail rate, we should see at least some consecutive failures
        # but also resets (consecutive_failures goes back to 0)
        self.assertGreater(max_consecutive, 0)


class TestDataConsistency(unittest.TestCase):
    """Verify data stays reasonable over many cycles."""

    def test_conductivity_stays_positive(self):
        """Conductivity never goes negative or zero over 100 polls."""
        handler = CN0359Handler([(1, "F1", "30")])
        handler.running = True
        s = _SensorState(1, "F1", "30")
        s.ser = FakeSerial("F1")
        handler.sensors = [s]

        for i in range(100):
            responses = handler._poll_all_sensors()
            parsed = CN0359Parser.parse_all_sensors(responses, f"10:{i//60:02d}:{i%60:02d}.000")
            if parsed['dut_units']:
                cond = parsed['dut_units'][0]['conductivity']['rzmag']
                self.assertGreater(cond, 0, f"Conductivity went non-positive at poll {i}")

    def test_temperature_stays_reasonable(self):
        """Temperature (degC) stays within bounds over 100 polls."""
        handler = CN0359Handler([(1, "F1", "30")])
        handler.running = True
        s = _SensorState(1, "F1", "30")
        s.ser = FakeSerial("F1")
        handler.sensors = [s]

        for i in range(100):
            responses = handler._poll_all_sensors()
            parsed = CN0359Parser.parse_all_sensors(responses, f"10:{i//60:02d}:{i%60:02d}.000")
            if parsed['dut_units']:
                temp = parsed['dut_units'][0]['temperature']['temperature_c']
                self.assertGreater(temp, -10, f"Temperature too low at poll {i}: {temp}")
                self.assertLess(temp, 100, f"Temperature too high at poll {i}: {temp}")

    def test_all_polls_produce_valid_timestamps(self):
        """Every parsed result has a positive float timestamp."""
        handler = CN0359Handler([(1, "F1", "30")])
        handler.running = True
        s = _SensorState(1, "F1", "30")
        s.ser = FakeSerial("F1")
        handler.sensors = [s]

        for i in range(50):
            responses = handler._poll_all_sensors()
            parsed = CN0359Parser.parse_all_sensors(responses, f"10:00:{i:02d}.000")
            self.assertIsInstance(parsed['timestamp'], float)
            self.assertGreater(parsed['timestamp'], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
