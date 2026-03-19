r"""
CN0359 Data Parser Module
=========================
This module's job: take the raw 22-line ASCII text that a CN0359 sensor board
spits out when you send it "30 poll\n", and pull out the three numbers we care
about -- conductivity (S/cm), temperature (°C), and excitation frequency (Hz).

It then packages those numbers into a dict that looks EXACTLY like what the
existing DataParser produces for the Teensy path.  That way, DataManager and
GraphManager don't need any changes -- they see the same shape of data no
matter which sensor path is active.

WHERE THE REGEX CAME FROM:
    The patterns are adapted from the proven Python scripts in
    CN0_Python_Scripts/modules/analog_devices_conductivity_board.py (lines 72, 111).
    We tightened them from greedy (.*) to [\d.eE+-]+ so they won't accidentally
    capture serial garbage if the sensor sends a garbled line.
"""
import logging
import math
import re
from datetime import datetime

# Create a logger for this module.  Messages go to whatever handler the app
# configures (file, console, etc.) instead of being lost in stdout.
logger = logging.getLogger(__name__)

# Try to import the app's timestamp format constant.  If we're running this
# file standalone (e.g., python -m modes.controllers.cn0359_parser), the
# import might fail, so we fall back to a sensible default.
try:
    from modes.utils.config import TIMESTAMP_FORMAT
except ImportError:
    TIMESTAMP_FORMAT = "%H:%M:%S.%f"


# ==========================================================================
# REGEX PATTERNS  --  the core of the parser
# ==========================================================================
# Each pattern looks for a specific label in the 22-line ASCII response and
# captures the numeric value after it.
#
# [\d.eE+-]+  means "one or more characters that can appear in a number":
#   \d  = digits 0-9
#   .   = decimal point
#   eE  = scientific notation indicator (1.067e-03 or 1.067E-03)
#   +-  = positive/negative sign
#
# \s* means "zero or more whitespace characters" -- handles cases where the
# sensor puts extra spaces before/after the value.
#
# Example line the conductivity regex matches:
#   "conductivity: 1.067099e-03S/cm"
#   It captures "1.067099e-03" into group(1).

_RE_CONDUCTIVITY = re.compile(r'conductivity:\s*([\d.eE+-]+)\s*S/cm')
_RE_TEMPERATURE = re.compile(r"TEMP:\s*([\d.eE+-]+)\s*'C")
_RE_FREQUENCY = re.compile(r'EXC FREQ:\s*([\d.eE+-]+)\s*Hz')
_RE_R_COMBINED = re.compile(r'R COMBINED:\s*([\d.eE+-]+)\s*Ohm')
_RE_Z_MAG = re.compile(r'\|Z\|:\s*([\d.eE+-]+)\s*Ohm')
_RE_R_PP = re.compile(r'Rp-p:\s*([\d.eE+-]+)\s*Ohm')
_RE_I_POS = re.compile(r'\+Ip-p:\s*([\d.eE+-]+)\s*A')
_RE_I_NEG = re.compile(r'-Ip-p:\s*([\d.eE+-]+)\s*A')
_RE_V_POS = re.compile(r'\+Vp-p:\s*([\d.eE+-]+)\s*V')
_RE_V_NEG = re.compile(r'-Vp-p:\s*([\d.eE+-]+)\s*V')
_RE_CELL_K = re.compile(r'cell\s+(?:K|constant):\s*([\d.eE+-]+)\s*/cm', re.IGNORECASE)
_RE_TEMP_COEF = re.compile(r'(?:TEMP COEF|temp coefficient):\s*([\d.eE+-]+)', re.IGNORECASE)
_RE_RTD_TYPE = re.compile(r'RTD:\s*PT(\d+)', re.IGNORECASE)


def _temperature_to_rtd_resistance(temp_c, rtd_nominal):
    """Convert RTD temperature (degC) to resistance (Ohm) using IEC751 polynomial."""
    coeff = (1.0, 3.9083e-3, -5.775e-7, 4.183e-10, -4.183e-12)
    if temp_c >= 0:
        res_norm = coeff[2]
        for idx in (1, 0):
            res_norm = res_norm * temp_c + coeff[idx]
    else:
        res_norm = coeff[4]
        for idx in (3, 2, 1, 0):
            res_norm = res_norm * temp_c + coeff[idx]
    return float(rtd_nominal) * res_norm


class CN0359Parser:
    """Parses CN0359 poll responses into the same dict format as DataParser.

    All methods are @staticmethod because the parser holds no state -- it's
    purely functional.  You pass data in, you get a dict out.
    """

    # ==================================================================
    # CHUNK 1: Timestamp conversion
    # ==================================================================
    @staticmethod
    def timestamp_to_seconds(timestamp_str):
        """Convert a timestamp string to Unix epoch seconds (float).

        Supports two formats:
          - Full datetime:  "2026-02-11 14:30:05.123456"
          - Time only:      "14:30:05.123"

        This is duplicated from DataParser.timestamp_to_seconds so both
        parsers stay independent -- changing one doesn't break the other.

        Returns:
            float: seconds since Unix epoch (Jan 1 1970).
                   Falls back to datetime.now() if parsing fails.
        """
        try:
            time_str = timestamp_str.strip()

            # CASE 1: Full "YYYY-MM-DD HH:MM:SS.ffffff" format
            # The space between date and time tells us it's the full format.
            if ' ' in time_str:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                return dt.timestamp()

            # CASE 2: Time-only "HH:MM:SS.mmm" format
            # We combine it with today's date to get a full datetime.
            else:
                today = datetime.now().date()
                time_parts = time_str.split(':')  # ["14", "30", "05.123"]

                if len(time_parts) >= 3:
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])

                    # Handle the seconds portion, which may have a decimal
                    # e.g. "05.123" -> seconds=5, milliseconds=123
                    seconds_parts = time_parts[2].split('.')
                    seconds = int(seconds_parts[0])
                    milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0

                    # Build a full datetime and convert to epoch seconds
                    # microseconds = milliseconds * 1000 because datetime
                    # uses microseconds internally
                    dt = datetime(today.year, today.month, today.day,
                                  hours, minutes, seconds, milliseconds * 1000)
                    return dt.timestamp()
                else:
                    # Not enough parts to parse -- just use current time
                    return datetime.now().timestamp()

        except Exception as e:
            logger.warning("Error converting timestamp '%s': %s", timestamp_str, e)
            return datetime.now().timestamp()

    # ==================================================================
    # CHUNK 2: Parse ONE sensor's poll response
    # ==================================================================
    @staticmethod
    def parse_poll_response(response_text):
        """Parse the 22-line ASCII response from a single CN0359 sensor.

        The CN0359 board responds to "30 poll\\n" with exactly 22 lines of
        ASCII text.  We only care about 3 of those lines:
          - "conductivity: 1.067099e-03S/cm"  -> the actual measurement
          - "TEMP: 25.300000'C"               -> solution temperature
          - "EXC FREQ: 10000.000000Hz"        -> excitation frequency

        Args:
            response_text: The full 22-line string (all lines concatenated).

        Returns:
            dict with two sub-dicts ('conductivity' and 'temperature'),
            each containing 'frequency', 'rzmag', and 'rzphase' keys.
            Returns None if conductivity or temperature is missing
            (frequency is optional -- defaults to 0.0 if not found).

        The output keys ('rzmag', 'rzphase', 'frequency') match what the
        old Teensy/DataParser path uses.  This is intentional -- it means
        DataManager, GraphManager, and CSV export all work unchanged.
        Mapping:
            resistance (Ohm)    -> conductivity.rzmag
            conductivity (S/cm) -> conductivity.conductivity_s_cm
            RTD resistance (Ohm)-> temperature.rzmag
            temperature  (°C)   -> temperature.temperature_c
            exc frequency (Hz)  -> conductivity.frequency
            rzphase             -> always 0.0 (CN0359 doesn't provide this)
        """
        # Run each regex against the full response text.
        # .search() scans the entire string and returns the first match,
        # or None if the pattern isn't found anywhere.
        cond_match = _RE_CONDUCTIVITY.search(response_text)
        temp_match = _RE_TEMPERATURE.search(response_text)
        freq_match = _RE_FREQUENCY.search(response_text)
        r_combined_match = _RE_R_COMBINED.search(response_text)
        z_mag_match = _RE_Z_MAG.search(response_text)

        # Conductivity is REQUIRED -- if the sensor didn't report it,
        # something went wrong (garbled data, wrong sensor, etc.)
        if not cond_match:
            logger.warning("conductivity not found in response")
            return None

        # Temperature is REQUIRED for the same reason
        if not temp_match:
            logger.warning("temperature not found in response")
            return None

        # .group(1) extracts the captured text inside the parentheses
        # in the regex pattern.  float() converts "1.067099e-03" -> 0.001067099
        # The regex can match strings like "1.2.3" that float() rejects,
        # so we guard against ValueError and OverflowError.
        try:
            conductivity = float(cond_match.group(1))
            if math.isinf(conductivity) or math.isnan(conductivity):
                raise ValueError("inf/nan")
        except (ValueError, OverflowError):
            logger.warning("conductivity value '%s' is not a valid number", cond_match.group(1))
            return None

        try:
            temperature = float(temp_match.group(1))
            if math.isinf(temperature) or math.isnan(temperature):
                raise ValueError("inf/nan")
        except (ValueError, OverflowError):
            logger.warning("temperature value '%s' is not a valid number", temp_match.group(1))
            return None

        rtd_nominal = 1000.0
        rtd_type_match = _RE_RTD_TYPE.search(response_text)
        if rtd_type_match:
            try:
                parsed_rtd = int(rtd_type_match.group(1))
                if parsed_rtd in (100, 1000):
                    rtd_nominal = float(parsed_rtd)
            except ValueError:
                pass

        try:
            temperature_resistance = _temperature_to_rtd_resistance(temperature, rtd_nominal)
            if math.isinf(temperature_resistance) or math.isnan(temperature_resistance):
                raise ValueError("inf/nan")
        except (ValueError, OverflowError):
            logger.warning("failed to derive RTD resistance from temperature %s", temperature)
            return None

        resistance_ohm = None
        for resistance_match in (r_combined_match, z_mag_match, _RE_R_PP.search(response_text)):
            if not resistance_match:
                continue
            try:
                resistance_ohm = abs(float(resistance_match.group(1)))
                if math.isinf(resistance_ohm) or math.isnan(resistance_ohm):
                    resistance_ohm = None
                    continue
                break
            except (ValueError, OverflowError):
                resistance_ohm = None

        # If resistance wasn't explicitly printed, derive it from raw V/I values.
        if resistance_ohm is None:
            try:
                i_pos = _RE_I_POS.search(response_text)
                i_neg = _RE_I_NEG.search(response_text)
                v_pos = _RE_V_POS.search(response_text)
                v_neg = _RE_V_NEG.search(response_text)
                if i_pos and i_neg and v_pos and v_neg:
                    current_delta = float(i_pos.group(1)) - float(i_neg.group(1))
                    voltage_delta = float(v_pos.group(1)) - float(v_neg.group(1))
                    if abs(current_delta) > 1e-18 and not math.isinf(voltage_delta) and not math.isnan(voltage_delta):
                        resistance_ohm = abs(voltage_delta / current_delta)
            except (ValueError, OverflowError, ZeroDivisionError):
                resistance_ohm = None

        # Last-resort derivation for firmware that only reports conductivity.
        if resistance_ohm is None:
            try:
                cell_k_match = _RE_CELL_K.search(response_text)
                temp_coef_match = _RE_TEMP_COEF.search(response_text)
                if cell_k_match:
                    cell_k = float(cell_k_match.group(1))
                    temp_coef = float(temp_coef_match.group(1)) if temp_coef_match else 0.0
                    compensation = 100.0 / (100.0 + temp_coef * (temperature - 25.0))
                    if abs(conductivity) > 1e-18 and compensation > 0:
                        resistance_ohm = abs((cell_k * compensation) / conductivity)
            except (ValueError, OverflowError, ZeroDivisionError):
                resistance_ohm = None

        if resistance_ohm is None:
            logger.warning("resistance could not be determined from response")
            return None

        # Frequency is OPTIONAL -- some older firmware might not include it.
        # If missing, we default to 0.0 so the dict shape stays consistent.
        try:
            frequency = float(freq_match.group(1)) if freq_match else 0.0
            if math.isinf(frequency) or math.isnan(frequency):
                frequency = 0.0
        except (ValueError, OverflowError):
            logger.warning("frequency value '%s' is not a valid number", freq_match.group(1))
            frequency = 0.0

        # Build the output dict in the exact shape DataManager expects.
        # This shape must match DataParser.parse_all_measurements() output.
        return {
            'conductivity': {
                'frequency': frequency,    # excitation frequency in Hz
                'rzmag': resistance_ohm,   # conductivity channel stores resistance in Ohm
                'rzphase': 0.0,            # not available from CN0359
                'conductivity_s_cm': conductivity,  # keep true conductivity alongside resistance
            },
            'temperature': {
                'frequency': 0.0,          # not applicable for temperature
                'rzmag': temperature_resistance,  # RTD resistance in Ohm
                'rzphase': 0.0,            # not available from CN0359
                'temperature_c': temperature,     # keep true temperature alongside resistance
            },
        }

    # ==================================================================
    # CHUNK 3: Parse ALL sensors into one combined result
    # ==================================================================
    @staticmethod
    def parse_all_sensors(sensor_responses, timestamp_str):
        """Parse responses from all sensors into one DataParser-compatible dict.

        This is the main entry point called by acquisition_mode.py.
        It takes the raw responses from CN0359Handler (which polls each
        sensor and collects their 22-line responses) and converts them
        into the exact same dict format that DataParser.parse_all_measurements()
        returns for the Teensy path.

        Args:
            sensor_responses: dict mapping unit_id (int) -> response_text (str).
                              Example: {1: "EXC V: 0.4V\\n...", 3: "EXC V: 0.4V\\n..."}
            timestamp_str: timestamp in the app's configured format,
                           e.g. "14:30:05.123" or "2026-02-11 14:30:05.123456"

        Returns:
            dict with these keys (identical to DataParser output):
            {
                'timestamp': float,          # Unix epoch seconds
                'timestamp_str': str,        # original timestamp string
                'dut_units': [               # list of sensor results
                    {
                        'unit_id': int,
                        'conductivity': {frequency, rzmag, rzphase},
                        'temperature':  {frequency, rzmag, rzphase},
                    },
                    ...
                ],
                'reference_devices': []      # always empty for CN0359
            }
        """
        # Convert the timestamp string to a float for graphing (X axis)
        time_seconds = CN0359Parser.timestamp_to_seconds(timestamp_str)

        dut_units = []

        # Process sensors in sorted order by unit_id so the output is
        # deterministic (unit 1 always comes before unit 3, etc.)
        for unit_id in sorted(sensor_responses.keys()):
            response_text = sensor_responses[unit_id]

            # Parse this sensor's response into conductivity + temperature
            parsed = CN0359Parser.parse_poll_response(response_text)

            # If parsing failed (garbled data, missing fields), skip this
            # sensor but keep processing the others
            if parsed is None:
                logger.warning("Skipping unit %d -- parse failed", unit_id)
                continue

            # Add this sensor's data to the list
            dut_units.append({
                'unit_id': unit_id,
                'conductivity': parsed['conductivity'],
                'temperature': parsed['temperature'],
            })

        # Return the combined result.  'reference_devices' is always empty
        # because CN0359 sensors don't have a separate reference channel
        # (unlike the Teensy path which can have IBP reference devices).
        return {
            'timestamp': time_seconds,
            'timestamp_str': timestamp_str,
            'dut_units': dut_units,
            'reference_devices': [],
        }


# ==========================================================================
# SELF-TEST  --  run with: python -m modes.controllers.cn0359_parser
# ==========================================================================
if __name__ == "__main__":
    # Realistic 22-line sample based on CN0359 firmware cmd_poll.cpp output
    SAMPLE_RESPONSE = (
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

    print("=== Single sensor parse ===")
    result = CN0359Parser.parse_poll_response(SAMPLE_RESPONSE)
    print(f"  resistance.rzmag   = {result['conductivity']['rzmag']}")
    print(f"  conductivity.freq  = {result['conductivity']['frequency']}")
    print(f"  temperature.rzmag  = {result['temperature']['rzmag']}")
    print()

    assert abs(result['conductivity']['rzmag'] - 322.54) < 0.5
    assert abs(result['conductivity']['conductivity_s_cm'] - 1.067099e-03) < 1e-10
    assert abs(result['conductivity']['frequency'] - 10000.0) < 0.01
    assert abs(result['temperature']['rzmag'] - 25.3) < 0.01
    assert result['conductivity']['rzphase'] == 0.0
    assert result['temperature']['rzphase'] == 0.0
    print("  Single sensor assertions PASSED\n")

    print("=== Multi-sensor parse ===")
    sensor_responses = {
        1: SAMPLE_RESPONSE,
        3: SAMPLE_RESPONSE.replace("25.300000", "26.100000")
                          .replace("1.067099e-03", "2.150000e-03"),
    }
    multi = CN0359Parser.parse_all_sensors(sensor_responses, "14:30:05.123")
    print(f"  timestamp_str = {multi['timestamp_str']}")
    print(f"  num units     = {len(multi['dut_units'])}")
    for u in multi['dut_units']:
        print(f"    unit {u['unit_id']}: cond={u['conductivity']['rzmag']:.6e} S/cm, "
              f"temp={u['temperature']['rzmag']:.1f} C")
    print()

    assert len(multi['dut_units']) == 2
    assert multi['dut_units'][0]['unit_id'] == 1
    assert multi['dut_units'][1]['unit_id'] == 3
    assert abs(multi['dut_units'][1]['conductivity']['rzmag'] - 2.15e-03) < 1e-10
    assert abs(multi['dut_units'][1]['temperature']['rzmag'] - 26.1) < 0.01
    assert multi['reference_devices'] == []
    print("  Multi-sensor assertions PASSED\n")

    print("=== Error handling (missing conductivity) ===")
    bad_response = "TEMP: 25.0'C\nsome garbage\n"
    bad_result = CN0359Parser.parse_poll_response(bad_response)
    assert bad_result is None
    print("  Correctly returned None for bad input\n")

    print("ALL TESTS PASSED")
