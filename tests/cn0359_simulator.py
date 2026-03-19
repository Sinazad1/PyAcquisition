"""
CN0359 Fake Sensor Simulator
Listens on a virtual COM port and responds to "poll\n" commands
with realistic 22-line ASCII responses, just like a real CN0359 board.

SETUP:
  1. Install com0com (free): https://sourceforge.net/projects/com0com/
     Or use com0com signed drivers for Win10/11.
  2. Create a virtual COM port pair, e.g. COM20 <-> COM21
  3. Run this script pointed at one end:   python tests/cn0359_simulator.py --port COM20
  4. Point the app at the other end:       sensor_1_port = COM21 in config.ini
  5. Launch the app and press Play -- you'll see live data on the graphs!

The simulator adds slight random drift to conductivity and temperature so the
graphs show realistic-looking movement instead of a flat line.

Run with:  python tests/cn0359_simulator.py --port COM20
"""
import argparse
import random
import time
import serial
import sys


def build_poll_response(conductivity, temperature, frequency):
    """Build the 22-line ASCII response matching CN0359 firmware output."""
    r_combined = 1.0 / conductivity if conductivity > 0 else 999999.0
    lines = [
        f"EXC V: 0.400000V",
        f"EXC FREQ: {frequency:.6f}Hz",
        f"+Ip-p: 0.001234V",
        f"-Ip-p: 0.001230V",
        f"+Vp-p: 0.398000V",
        f"-Vp-p: 0.397000V",
        f"+PHASE: 1.200000deg",
        f"-PHASE: -1.100000deg",
        f"Rp-p: {r_combined:.6f}Ohm",
        f"Rreal: {r_combined:.6f}Ohm",
        f"Rimag: 6.740000Ohm",
        f"|Z|: {r_combined:.6f}Ohm",
        f"PHASE: 1.198000deg",
        f"R COMBINED: {r_combined:.6f}Ohm",
        f"cell constant: 0.080000/cm",
        f"temp coefficient: 5.200000",
        f"setup time: 0.300000",
        f"hold time: 0.400000",
        f"",
        f"TEMP: {temperature:.6f}'C",
        f"",
        f"conductivity: {conductivity:.6e}S/cm",
    ]
    return "\n".join(lines) + "\n"


def run_simulator(port, baudrate, base_cond, base_temp, freq):
    print(f"CN0359 Simulator")
    print(f"  Port:          {port}")
    print(f"  Baudrate:      {baudrate}")
    print(f"  Base cond:     {base_cond:.4e} S/cm")
    print(f"  Base temp:     {base_temp:.1f} C")
    print(f"  Frequency:     {freq:.0f} Hz")
    print(f"\nWaiting for poll commands...\n")

    try:
        ser = serial.Serial(port, baudrate, timeout=1)
    except serial.SerialException as e:
        print(f"ERROR: Cannot open {port}: {e}")
        print(f"\nMake sure you have com0com installed and the port pair created.")
        sys.exit(1)

    poll_count = 0
    cond = base_cond
    temp = base_temp

    try:
        while True:
            line = ser.readline()
            if not line:
                continue

            cmd = line.decode('ascii', errors='replace').strip()
            if not cmd:
                continue

            # Expect bare "poll"
            expected = "poll"
            if cmd == expected:
                poll_count += 1

                # Add realistic drift
                cond += random.gauss(0, base_cond * 0.02)
                cond = max(base_cond * 0.5, min(base_cond * 1.5, cond))
                temp += random.gauss(0, 0.1)
                temp = max(base_temp - 3, min(base_temp + 3, temp))

                response = build_poll_response(cond, temp, freq)
                ser.write(response.encode('ascii'))
                ser.flush()

                print(f"  [Poll #{poll_count}] cond={cond:.4e} S/cm, temp={temp:.2f} C")
            else:
                print(f"  [Unknown command] '{cmd}' (expected '{expected}')")

    except KeyboardInterrupt:
        print(f"\nSimulator stopped after {poll_count} polls.")
    finally:
        ser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CN0359 Fake Sensor Simulator")
    parser.add_argument("--port", required=True, help="COM port to listen on (e.g. COM20)")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--conductivity", type=float, default=1.067e-03,
                        help="Base conductivity in S/cm (default: 1.067e-03)")
    parser.add_argument("--temperature", type=float, default=25.3,
                        help="Base temperature in C (default: 25.3)")
    parser.add_argument("--frequency", type=float, default=10000.0,
                        help="Excitation frequency in Hz (default: 10000)")
    args = parser.parse_args()

    run_simulator(args.port, args.baudrate,
                  args.conductivity, args.temperature, args.frequency)
