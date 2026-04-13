"""
IonIn commissioning CLI for stepwise troubleshooting and recipe execution.

This script is intentionally hardware-first:
1) verify sensor reads
2) verify each actuator independently
3) run a calibration recipe (protocol JSON) once the rig is ready
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

class _TeeStream:
    """Mirror writes to multiple streams."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for stream in self._streams:
            try:
                stream.write(data)
            except Exception:  # noqa: BLE001
                pass
        return len(data)

    def flush(self):
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:  # noqa: BLE001
                pass

    def isatty(self):
        for stream in self._streams:
            if hasattr(stream, "isatty"):
                try:
                    return bool(stream.isatty())
                except Exception:  # noqa: BLE001
                    continue
        return False


def _initialize_process_logging() -> Path | None:
    """Start always-on CLI session logging as soon as process starts."""
    try:
        log_dir = Path.cwd() / "data" / "cli_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"ionin_cli_session_{stamp}.log"
        log_fh = open(log_path, "a", encoding="utf-8")
        sys.stdout = _TeeStream(sys.__stdout__, log_fh)
        sys.stderr = _TeeStream(sys.__stderr__, log_fh)
        print(f"[IONIN-CLI] Session log started: {log_path.resolve()}")
        print(f"[IONIN-CLI] Command line: {' '.join(sys.argv)}")
        return log_path
    except Exception as exc:  # noqa: BLE001
        try:
            sys.__stderr__.write(f"[IONIN-CLI] Failed to initialize session logging: {exc}\n")
            sys.__stderr__.flush()
        except Exception:  # noqa: BLE001
            pass
        return None


CLI_LOG_PATH = _initialize_process_logging()

from modes.controllers.device_controller import DeviceController
from modes.hardware.chiller_handler import ChillerThread
from modes.hardware.cn0359_handler import CN0359Handler
from modes.hardware.syringe_pump_handler import SyringePumpThread
from modes.hardware.tic_handler import TicThread
from modes.hardware.protocol_handler import ProtocolHandler
from modes.utils.settings import load_settings

REPO_ROOT = Path(__file__).resolve().parent
OPERATIONAL_MODE_RECIPES: dict[str, dict[str, str]] = {
    "prime": {
        "description": "Fast initial line fill and bubble purge.",
        "path": "protocols/operational_modes/prime_mode.json",
    },
    "flush": {
        "description": "Clear lines/chamber between fluids or runs.",
        "path": "protocols/operational_modes/flush_mode.json",
    },
    "circulation": {
        "description": "Recirculate sample with controlled flow and temperature.",
        "path": "protocols/operational_modes/circulation_mode.json",
    },
    "stabilize": {
        "description": "Low-flow thermal/electrical stabilization hold.",
        "path": "protocols/operational_modes/stabilize_mode.json",
    },
    "calibration": {
        "description": "Stepwise calibration sequence (recipe-driven).",
        "path": "protocols/operational_modes/calibration_mode.json",
    },
    "rinse": {
        "description": "Post-run rinse to minimize carryover.",
        "path": "protocols/operational_modes/rinse_mode.json",
    },
    "safe_idle": {
        "description": "Put actuators in a safe parked state.",
        "path": "protocols/operational_modes/safe_idle_mode.json",
    },
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    payload: dict[str, Any] | None = None


class ConsoleLogger:
    """Small parent object for DeviceController-compatible logging."""

    def log_event(self, message, color="#FFFFFF", log_type="IONIN-CLI"):
        del color  # Not used in CLI output.
        print(f"[{log_type}] {message}")


class IonInCliWorkflow:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.logger = ConsoleLogger()
        self.device_controller = DeviceController(self.logger)
        self.device_controller.set_pump_port(self.settings.get("SYRINGE_PUMP_PORT"))
        self.device_controller.set_chiller_port(self.settings.get("CHILLER_PORT"))
        self.device_controller.set_tic_serials(
            self.settings.get("TIC_A_SERIAL_NUMBER"),
            self.settings.get("TIC_B_SERIAL_NUMBER"),
        )

    def print_config_summary(self) -> None:
        sensors = self.settings.get("CN0359_SENSORS", [])
        print("\n=== IonIn CLI Commissioning ===")
        print(f"CN0359 enabled: {bool(self.settings.get('CN0359_ENABLED', False))}")
        print(f"CN0359 sensors configured: {len(sensors)}")
        for entry in sensors:
            if len(entry) >= 2:
                print(f"  - U{entry[0]} -> {entry[1]}")
        print(f"Pump port: {self.settings.get('SYRINGE_PUMP_PORT') or '<not set>'}")
        print(f"Chiller port: {self.settings.get('CHILLER_PORT') or '<not set>'}")
        print(f"Tic A serial: {self.settings.get('TIC_A_SERIAL_NUMBER') or '<not set>'}")
        print(f"Tic B serial: {self.settings.get('TIC_B_SERIAL_NUMBER') or '<not set>'}")

    def check_sensors(self, attempts: int = 2) -> CheckResult:
        sensors = self.settings.get("CN0359_SENSORS", [])
        if not sensors:
            return CheckResult("sensors", False, "No CN0359 sensors configured in config.ini")

        handler = None
        try:
            handler = CN0359Handler(
                sensors,
                baudrate=int(self.settings.get("CN0359_BAUDRATE", 115200)),
                query_interval=float(self.settings.get("CN0359_POLL_INTERVAL", 10)),
            )
            handler.running = True
            handler._open_connections()
            snapshot = handler.preflight_snapshot(attempts=max(1, int(attempts)))
        except Exception as exc:  # noqa: BLE001
            return CheckResult("sensors", False, f"Sensor check failed: {exc}")
        finally:
            if handler is not None:
                handler.running = False
                try:
                    handler.close_connection()
                except Exception:  # noqa: BLE001
                    pass

        detected = sum(1 for row in snapshot if row.get("detected"))
        parse_ok = sum(1 for row in snapshot if row.get("parse_ok"))
        total = len(snapshot)
        ok = detected == total and parse_ok == total
        detail = f"{detected}/{total} detected, {parse_ok}/{total} parse_ok"
        return CheckResult("sensors", ok, detail, {"snapshot": snapshot})

    def check_pump(self, allow_motion: bool = False, pulse_seconds: float = 1.0) -> CheckResult:
        port = self.settings.get("SYRINGE_PUMP_PORT")
        if not port:
            return CheckResult("pump", False, "Pump port not configured")

        pump = SyringePumpThread(port, baudrate=int(self.settings.get("PUMP_BAUDRATE", 19200)))
        try:
            pump.run()  # run synchronously for CLI usage
            if not pump.running or not pump.serial_connection:
                return CheckResult("pump", False, "Unable to open/identify pump")
            ver = pump.send_command("VER")
            if not ver:
                return CheckResult("pump", False, "No response to VER")
            if allow_motion:
                pump.send_command("RUN")
                time.sleep(max(0.1, float(pulse_seconds)))
                pump.send_command("STP")
            return CheckResult("pump", True, f"Pump responsive (VER={ver})")
        except Exception as exc:  # noqa: BLE001
            return CheckResult("pump", False, f"Pump check failed: {exc}")
        finally:
            try:
                pump.stop()
            except Exception:  # noqa: BLE001
                pass

    def check_chiller(self, allow_motion: bool = False, pulse_seconds: float = 1.0) -> CheckResult:
        port = self.settings.get("CHILLER_PORT")
        if not port:
            return CheckResult("chiller", False, "Chiller port not configured")

        chiller = ChillerThread(port, baudrate=int(self.settings.get("CHILLER_BAUDRATE", 4800)))
        try:
            chiller.run()  # run synchronously for CLI usage
            if not chiller.running or not chiller.serial_connection:
                return CheckResult("chiller", False, "Unable to open chiller connection")
            temp = chiller.read_temperature()
            if temp is None:
                return CheckResult("chiller", False, "No valid temperature response")
            if allow_motion:
                chiller.start_chiller()
                time.sleep(max(0.1, float(pulse_seconds)))
                chiller.stop_chiller()
            return CheckResult("chiller", True, f"Chiller responsive (temp={temp:.2f} C)")
        except Exception as exc:  # noqa: BLE001
            return CheckResult("chiller", False, f"Chiller check failed: {exc}")
        finally:
            try:
                chiller.stop()
            except Exception:  # noqa: BLE001
                pass

    def check_tic(self, tic_id: str, allow_motion: bool = False, pulse_seconds: float = 1.0) -> CheckResult:
        tic_id = str(tic_id).upper()
        serial_number = self.settings.get("TIC_A_SERIAL_NUMBER" if tic_id == "A" else "TIC_B_SERIAL_NUMBER")
        name = f"tic_{tic_id.lower()}"
        if not serial_number:
            return CheckResult(name, False, f"Tic {tic_id} serial not configured")

        tic = TicThread(serial_number)
        try:
            tic.run()  # run synchronously for CLI usage
            status = tic.get_status()
            if not status:
                return CheckResult(name, False, f"Tic {tic_id} did not return status")
            if allow_motion:
                tic.energize()
                tic.set_velocity(100000)
                time.sleep(max(0.1, float(pulse_seconds)))
                tic.set_velocity(0)
                tic.deenergize()
            op_state = status.get("Operation state", "unknown")
            return CheckResult(name, True, f"Tic {tic_id} responsive (state={op_state})", {"status": status})
        except Exception as exc:  # noqa: BLE001
            return CheckResult(name, False, f"Tic {tic_id} check failed: {exc}")
        finally:
            try:
                tic.stop()
            except Exception:  # noqa: BLE001
                pass

    def run_commissioning_workflow(self, allow_motion: bool, pulse_seconds: float, sensor_attempts: int) -> int:
        self.print_config_summary()
        print("\nStep 1/5: Sensor preflight")
        sensor_result = self.check_sensors(attempts=sensor_attempts)
        self._print_result(sensor_result)
        if sensor_result.payload and sensor_result.payload.get("snapshot"):
            for row in sensor_result.payload["snapshot"]:
                err = row.get("error") or "ok"
                print(
                    f"  U{row.get('unit_id')} {row.get('port')}: "
                    f"detected={row.get('detected')} parse_ok={row.get('parse_ok')} "
                    f"lines={row.get('non_empty_lines')} err={err}"
                )

        print("\nStep 2/5: Pump check")
        pump_result = self.check_pump(allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        self._print_result(pump_result)

        print("\nStep 3/5: Chiller check")
        chiller_result = self.check_chiller(allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        self._print_result(chiller_result)

        print("\nStep 4/5: Tic A check")
        tic_a_result = self.check_tic("A", allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        self._print_result(tic_a_result)

        print("\nStep 5/5: Tic B check")
        tic_b_result = self.check_tic("B", allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        self._print_result(tic_b_result)

        all_results = [sensor_result, pump_result, chiller_result, tic_a_result, tic_b_result]
        failed = [r for r in all_results if not r.ok]
        print("\n=== Readiness Summary ===")
        if not failed:
            print("PASS: all components are ready for calibration recipe runs.")
            return 0

        print(f"FAIL: {len(failed)} component(s) need attention.")
        for result in failed:
            print(f"  - {result.name}: {result.detail}")
        return 2

    def run_recipe(
        self,
        recipe_path: str,
        dry_run: bool = False,
        skip_waits: bool = False,
        sample_sensors_each_step: bool = False,
    ) -> int:
        protocol = ProtocolHandler()
        if not protocol.load_protocol(recipe_path):
            print(f"[ERROR] Failed to load recipe: {recipe_path}")
            return 2

        print(f"\nLoaded recipe: {recipe_path}")
        print(protocol.get_protocol_summary())

        for step in protocol.protocol_steps:
            print(f"\n--- Step {step.step_number} ---")
            print(step.description or "<no description>")
            print(f"Duration: {step.duration_minutes} min")
            if step.pump_settings:
                print(f"Pump: {json.dumps(step.pump_settings)}")
            if step.tic_a_settings:
                print(f"Tic A: {json.dumps(step.tic_a_settings)}")
            if step.tic_b_settings:
                print(f"Tic B: {json.dumps(step.tic_b_settings)}")
            if step.chiller_settings:
                print(f"Chiller: {json.dumps(step.chiller_settings)}")

            if not dry_run:
                self.device_controller.apply_all_settings(
                    pump_settings=step.pump_settings,
                    tic_a_settings=step.tic_a_settings,
                    tic_b_settings=step.tic_b_settings,
                    chiller_settings=step.chiller_settings,
                )

            if sample_sensors_each_step:
                sample_result = self.check_sensors(attempts=1)
                self._print_result(sample_result)

            if skip_waits or dry_run:
                print("[INFO] Wait skipped.")
            else:
                wait_seconds = max(0, int(round(float(step.duration_minutes) * 60.0)))
                print(f"[INFO] Holding for {wait_seconds} seconds...")
                time.sleep(wait_seconds)

        if not dry_run:
            print("\n[INFO] Recipe complete. Moving all devices to safe stop state.")
            self.device_controller.stop_all_devices()

        print("Recipe run complete.")
        return 0

    @staticmethod
    def _print_result(result: CheckResult) -> None:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="IonIn CLI workflow for stepwise commissioning and calibration recipes."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    workflow = sub.add_parser("workflow", help="Run full troubleshooting workflow in logical order.")
    workflow.add_argument(
        "--allow-motion",
        action="store_true",
        help="Enable brief actuator movement/start-stop pulses during checks.",
    )
    workflow.add_argument(
        "--pulse-seconds",
        type=float,
        default=1.0,
        help="Duration of actuator pulse when --allow-motion is set.",
    )
    workflow.add_argument(
        "--sensor-attempts",
        type=int,
        default=2,
        help="Number of polling attempts per sensor during preflight.",
    )

    check = sub.add_parser("check", help="Run one component check.")
    check.add_argument(
        "component",
        choices=["sensors", "pump", "chiller", "tic_a", "tic_b"],
        help="Component to test.",
    )
    check.add_argument(
        "--allow-motion",
        action="store_true",
        help="Enable brief actuator movement/start-stop pulses for actuator checks.",
    )
    check.add_argument("--pulse-seconds", type=float, default=1.0)
    check.add_argument("--sensor-attempts", type=int, default=2)

    recipe = sub.add_parser("run-recipe", help="Run calibration recipe JSON step-by-step.")
    recipe.add_argument("recipe_path", help="Path to protocol recipe JSON.")
    recipe.add_argument("--dry-run", action="store_true", help="Print planned actions only.")
    recipe.add_argument("--skip-waits", action="store_true", help="Do not sleep between recipe steps.")
    recipe.add_argument(
        "--sample-sensors-each-step",
        action="store_true",
        help="Poll sensors once after each recipe step for quick diagnostics.",
    )

    list_modes = sub.add_parser("list-modes", help="List built-in operational mode recipes.")
    list_modes.add_argument("--show-paths", action="store_true", help="Show recipe file path for each mode.")

    run_mode = sub.add_parser("run-mode", help="Run a built-in operational mode by name.")
    run_mode.add_argument("mode", choices=sorted(OPERATIONAL_MODE_RECIPES.keys()))
    run_mode.add_argument("--dry-run", action="store_true", help="Print planned actions only.")
    run_mode.add_argument("--skip-waits", action="store_true", help="Do not sleep between mode steps.")
    run_mode.add_argument(
        "--sample-sensors-each-step",
        action="store_true",
        help="Poll sensors once after each mode step for quick diagnostics.",
    )

    return parser


def print_available_modes(show_paths: bool = False) -> None:
    print("\nBuilt-in operational modes:")
    for mode_name in sorted(OPERATIONAL_MODE_RECIPES.keys()):
        meta = OPERATIONAL_MODE_RECIPES[mode_name]
        line = f"  - {mode_name}: {meta['description']}"
        if show_paths:
            recipe_path = (REPO_ROOT / meta["path"]).resolve()
            line += f" ({recipe_path})"
        print(line)


def resolve_mode_recipe(mode_name: str) -> str:
    meta = OPERATIONAL_MODE_RECIPES[str(mode_name).lower()]
    return str((REPO_ROOT / meta["path"]).resolve())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    workflow = IonInCliWorkflow(settings=settings)

    if args.command == "workflow":
        return workflow.run_commissioning_workflow(
            allow_motion=bool(args.allow_motion),
            pulse_seconds=float(args.pulse_seconds),
            sensor_attempts=int(args.sensor_attempts),
        )

    if args.command == "check":
        component = str(args.component).lower()
        if component == "sensors":
            result = workflow.check_sensors(attempts=int(args.sensor_attempts))
        elif component == "pump":
            result = workflow.check_pump(
                allow_motion=bool(args.allow_motion),
                pulse_seconds=float(args.pulse_seconds),
            )
        elif component == "chiller":
            result = workflow.check_chiller(
                allow_motion=bool(args.allow_motion),
                pulse_seconds=float(args.pulse_seconds),
            )
        elif component == "tic_a":
            result = workflow.check_tic(
                "A",
                allow_motion=bool(args.allow_motion),
                pulse_seconds=float(args.pulse_seconds),
            )
        else:
            result = workflow.check_tic(
                "B",
                allow_motion=bool(args.allow_motion),
                pulse_seconds=float(args.pulse_seconds),
            )
        workflow._print_result(result)
        return 0 if result.ok else 2

    if args.command == "run-recipe":
        recipe_path = os.path.abspath(args.recipe_path)
        if not Path(recipe_path).exists():
            print(f"[ERROR] Recipe file not found: {recipe_path}")
            return 2
        return workflow.run_recipe(
            recipe_path=recipe_path,
            dry_run=bool(args.dry_run),
            skip_waits=bool(args.skip_waits),
            sample_sensors_each_step=bool(args.sample_sensors_each_step),
        )

    if args.command == "list-modes":
        print_available_modes(show_paths=bool(args.show_paths))
        return 0

    if args.command == "run-mode":
        recipe_path = resolve_mode_recipe(args.mode)
        if not Path(recipe_path).exists():
            print(f"[ERROR] Mode recipe not found: {recipe_path}")
            return 2
        print(f"Running mode '{args.mode}' using {recipe_path}")
        return workflow.run_recipe(
            recipe_path=recipe_path,
            dry_run=bool(args.dry_run),
            skip_waits=bool(args.skip_waits),
            sample_sensors_each_step=bool(args.sample_sensors_each_step),
        )

    print("[ERROR] Unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
