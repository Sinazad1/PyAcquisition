"""
Enhanced IonIn operational CLI with safety gates, interlocks, and traceability.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import serial

from modes.controllers.device_controller import DeviceController
from modes.controllers.cn0359_parser import CN0359Parser
from modes.hardware.chiller_handler import ChillerThread
from modes.hardware.cn0359_handler import CN0359Handler
from modes.hardware.protocol_handler import ProtocolHandler
from modes.hardware.syringe_pump_handler import SyringePumpThread
from modes.hardware.tic_handler import TicThread
from modes.utils.settings import load_settings


REPO_ROOT = Path(__file__).resolve().parent
POLICY_PATH = REPO_ROOT / "protocols" / "operational_modes" / "operation_policy.json"
CLI_STATE_PATH = Path.cwd() / "data" / "cli_state.json"

MODE_RECIPES: dict[str, dict[str, str]] = {
    "prime": {"description": "Fast initial line fill and bubble purge.", "path": "protocols/operational_modes/prime_mode.json"},
    "flush": {"description": "Clear lines/chamber between fluids or runs.", "path": "protocols/operational_modes/flush_mode.json"},
    "circulation": {"description": "Recirculate sample with controlled flow and temperature.", "path": "protocols/operational_modes/circulation_mode.json"},
    "stabilize": {"description": "Low-flow thermal/electrical stabilization hold.", "path": "protocols/operational_modes/stabilize_mode.json"},
    "calibration": {"description": "Stepwise calibration sequence (recipe-driven).", "path": "protocols/operational_modes/calibration_mode.json"},
    "reference_check": {"description": "Validate IBP reference channels before/after DUT sequence.", "path": "protocols/operational_modes/reference_check_mode.json"},
    "rinse": {"description": "Post-run rinse to minimize carryover.", "path": "protocols/operational_modes/rinse_mode.json"},
    "safe_idle": {"description": "Put actuators in a safe parked state.", "path": "protocols/operational_modes/safe_idle_mode.json"},
}

DEFAULT_POLICY: dict[str, Any] = {
    "thresholds": {
        "sensor_min_detect_ratio": 1.0,
        "sensor_min_parse_ratio": 1.0,
    },
    "interlocks": {
        "max_pump_rate": 12.0,
        "max_chiller_temp_c": 40.0,
        "min_chiller_temp_c": 5.0,
        "max_tic_velocity_abs": 500000,
    },
    "chain_default": ["prime", "flush", "circulation", "stabilize", "calibration", "reference_check", "rinse", "safe_idle"],
    "modes": {
        "prime": {"data_policy": "diagnostic", "entry_checks": ["sensors"], "exit_checks": []},
        "flush": {"data_policy": "diagnostic", "entry_checks": ["sensors", "pump"], "exit_checks": []},
        "circulation": {"data_policy": "diagnostic", "entry_checks": ["sensors", "pump", "chiller"], "exit_checks": ["sensors"]},
        "stabilize": {"data_policy": "analysis_quality", "entry_checks": ["sensors", "chiller"], "exit_checks": ["sensors"]},
        "calibration": {
            "data_policy": "analysis_quality",
            "entry_checks": ["sensors", "pump", "chiller", "tic_a", "tic_b", "references"],
            "exit_checks": ["sensors", "references"],
            "preflight_required": True,
            "reference_each_step": True,
        },
        "reference_check": {"data_policy": "diagnostic", "entry_checks": ["references"], "exit_checks": ["references"]},
        "rinse": {"data_policy": "diagnostic", "entry_checks": ["pump"], "exit_checks": []},
        "safe_idle": {"data_policy": "diagnostic", "entry_checks": [], "exit_checks": []},
    },
}


class _TeeStream:
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_policy() -> dict[str, Any]:
    policy = dict(DEFAULT_POLICY)
    if POLICY_PATH.exists():
        try:
            with open(POLICY_PATH, "r", encoding="utf-8") as fh:
                policy = _deep_merge(policy, json.load(fh))
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Policy load failed; using defaults: {exc}")
    return policy


def start_session_logging() -> Path | None:
    try:
        log_dir = Path.cwd() / "data" / "cli_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"ionin_ops_cli_{stamp}.log"
        fh = open(log_path, "a", encoding="utf-8")
        sys.stdout = _TeeStream(sys.__stdout__, fh)
        sys.stderr = _TeeStream(sys.__stderr__, fh)
        print(f"[IONIN-OPS] session_log={log_path.resolve()}")
        print(f"[IONIN-OPS] argv={' '.join(sys.argv)}")
        return log_path
    except Exception as exc:  # noqa: BLE001
        try:
            sys.__stderr__.write(f"[IONIN-OPS] failed to start logging: {exc}\n")
        except Exception:  # noqa: BLE001
            pass
        return None


SESSION_LOG = start_session_logging()


def load_cli_state() -> dict[str, Any]:
    if CLI_STATE_PATH.exists():
        try:
            with open(CLI_STATE_PATH, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                return payload
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_cli_state(state: dict[str, Any]) -> None:
    try:
        CLI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CLI_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] failed to persist CLI state: {exc}")


def resolve_recipe_with_history(recipe_arg: str | None, use_last: bool, state: dict[str, Any]) -> str | None:
    last_recipe = state.get("last_recipe_path")

    if recipe_arg and not use_last:
        return os.path.abspath(recipe_arg)

    if use_last:
        if not last_recipe:
            print("[ERROR] --use-last requested but no previous recipe is saved yet.")
            return None
        print(f"[INFO] using last saved recipe: {last_recipe}")
        return os.path.abspath(str(last_recipe))

    if recipe_arg:
        return os.path.abspath(recipe_arg)

    # No recipe path provided: ask to reuse the last one when available.
    if not last_recipe:
        print("[ERROR] no recipe path provided and no saved last recipe exists.")
        return None

    if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
        try:
            answer = input(f"No recipe provided. Reuse last recipe?\n  {last_recipe}\n[Y/n]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer in ("", "y", "yes"):
            print(f"[INFO] reusing last recipe: {last_recipe}")
            return os.path.abspath(str(last_recipe))
        print("[ERROR] recipe not selected. Provide a path or use --use-last.")
        return None

    # Non-interactive shell fallback.
    print(f"[INFO] non-interactive shell: reusing last recipe {last_recipe}")
    return os.path.abspath(str(last_recipe))


def _prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            raw = input(f"{prompt} {suffix}: ").strip().lower()
        except EOFError:
            return default
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please enter y or n.")


def _prompt_float(prompt: str, default: float) -> float:
    while True:
        try:
            raw = input(f"{prompt} [{default}]: ").strip()
        except EOFError:
            return float(default)
        if raw == "":
            return float(default)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a valid number.")


def _prompt_int(prompt: str, default: int) -> int:
    while True:
        try:
            raw = input(f"{prompt} [{default}]: ").strip()
        except EOFError:
            return int(default)
        if raw == "":
            return int(default)
        try:
            return int(raw)
        except ValueError:
            print("Please enter a valid integer.")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    payload: dict[str, Any] | None = None
    elapsed_sec: float = 0.0


class ConsoleLogger:
    def log_event(self, message, color="#FFFFFF", log_type="IONIN-OPS"):
        del color
        print(f"[{log_type}] {message}")


class OpsWorkflow:
    def __init__(self, settings: dict[str, Any], policy: dict[str, Any]):
        self.settings = settings
        self.policy = policy
        self.logger = ConsoleLogger()
        self.device_controller = DeviceController(self.logger)
        self.device_controller.set_pump_port(self.settings.get("SYRINGE_PUMP_PORT"))
        self.device_controller.set_chiller_port(self.settings.get("CHILLER_PORT"))
        self.device_controller.set_tic_serials(self.settings.get("TIC_A_SERIAL_NUMBER"), self.settings.get("TIC_B_SERIAL_NUMBER"))

        self.run_id: str | None = None
        self.run_dir: Path | None = None
        self.manifest: dict[str, Any] | None = None
        self.checks_csv_path: Path | None = None
        self.checks: list[dict[str, Any]] = []

    def begin_run(self, command: str, args: dict[str, Any]) -> None:
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.run_dir = Path.cwd() / "data" / "runs" / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.checks_csv_path = self.run_dir / "checks.csv"
        self.manifest = {
            "run_id": self.run_id,
            "started_at_utc": _utc_now(),
            "command": command,
            "args": args,
            "session_log": str(SESSION_LOG) if SESSION_LOG else None,
            "policy_file": str(POLICY_PATH),
            "hardware": {
                "cn0359_sensors": self.settings.get("CN0359_SENSORS", []),
                "pump_port": self.settings.get("SYRINGE_PUMP_PORT"),
                "chiller_port": self.settings.get("CHILLER_PORT"),
                "tic_a_serial": self.settings.get("TIC_A_SERIAL_NUMBER"),
                "tic_b_serial": self.settings.get("TIC_B_SERIAL_NUMBER"),
                "ibp_ref1_port": self.settings.get("IBP_REF1_PORT"),
                "ibp_ref2_port": self.settings.get("IBP_REF2_PORT"),
            },
            "checks": [],
            "mode_runs": [],
            "analysis_link": None,
            "programming_link": None,
            "status": "running",
        }
        self._save_manifest()
        print(f"[IONIN-OPS] run_id={self.run_id}")
        print(f"[IONIN-OPS] manifest={(self.run_dir / 'manifest.json').resolve()}")

    def finalize_run(self, exit_code: int) -> None:
        if not self.manifest:
            return
        self.manifest["checks"] = self.checks
        self.manifest["ended_at_utc"] = _utc_now()
        self.manifest["exit_code"] = int(exit_code)
        self.manifest["status"] = "pass" if exit_code == 0 else "fail"
        self._save_manifest()

    def _save_manifest(self) -> None:
        if not self.manifest or not self.run_dir:
            return
        with open(self.run_dir / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(self.manifest, fh, indent=2)

    def _record_check(self, result: CheckResult) -> None:
        row = {
            "timestamp_utc": _utc_now(),
            "name": result.name,
            "ok": bool(result.ok),
            "elapsed_sec": round(float(result.elapsed_sec), 3),
            "detail": result.detail,
            "payload": result.payload or {},
        }
        self.checks.append(row)
        if self.checks_csv_path:
            write_header = not self.checks_csv_path.exists()
            with open(self.checks_csv_path, "a", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                if write_header:
                    writer.writerow(["timestamp_utc", "name", "ok", "elapsed_sec", "detail"])
                writer.writerow([row["timestamp_utc"], row["name"], int(row["ok"]), row["elapsed_sec"], row["detail"]])
        self._save_manifest()

    @staticmethod
    def print_check(result: CheckResult) -> None:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")

    def print_config_summary(self) -> None:
        sensors = self.settings.get("CN0359_SENSORS", [])
        print("\n=== Configuration Summary ===")
        print(f"CN0359 sensors: {len(sensors)}")
        for entry in sensors:
            if len(entry) >= 2:
                print(f"  - U{entry[0]} @ {entry[1]}")
        print(f"Ref1: {self.settings.get('IBP_REF1_PORT') or '<not set>'}")
        print(f"Ref2: {self.settings.get('IBP_REF2_PORT') or '<not set>'}")
        print(f"Pump: {self.settings.get('SYRINGE_PUMP_PORT') or '<not set>'}")
        print(f"Chiller: {self.settings.get('CHILLER_PORT') or '<not set>'}")
        print(f"Tic A: {self.settings.get('TIC_A_SERIAL_NUMBER') or '<not set>'}")
        print(f"Tic B: {self.settings.get('TIC_B_SERIAL_NUMBER') or '<not set>'}")

    def check_sensors(self, attempts: int = 2) -> CheckResult:
        started = time.time()
        sensors = self.settings.get("CN0359_SENSORS", [])
        if not sensors:
            out = CheckResult("sensors", False, "No CN0359 sensors configured", elapsed_sec=time.time() - started)
            self._record_check(out)
            return out

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
            out = CheckResult("sensors", False, f"Sensor check failed: {exc}", elapsed_sec=time.time() - started)
            self._record_check(out)
            return out
        finally:
            if handler is not None:
                handler.running = False
                try:
                    handler.close_connection()
                except Exception:  # noqa: BLE001
                    pass

        total = len(snapshot)
        detected = sum(1 for r in snapshot if r.get("detected"))
        parse_ok = sum(1 for r in snapshot if r.get("parse_ok"))
        ratio_detect = (detected / total) if total else 0.0
        ratio_parse = (parse_ok / total) if total else 0.0
        min_detect = float(self.policy["thresholds"].get("sensor_min_detect_ratio", 1.0))
        min_parse = float(self.policy["thresholds"].get("sensor_min_parse_ratio", 1.0))
        ok = ratio_detect >= min_detect and ratio_parse >= min_parse
        out = CheckResult(
            "sensors",
            ok,
            f"{detected}/{total} detected, {parse_ok}/{total} parse_ok",
            payload={"snapshot": snapshot, "ratio_detect": ratio_detect, "ratio_parse": ratio_parse},
            elapsed_sec=time.time() - started,
        )
        self._record_check(out)
        return out

    def check_references(self) -> CheckResult:
        started = time.time()
        refs = []
        failures = 0
        for ref_id, key in ((1, "IBP_REF1_PORT"), (2, "IBP_REF2_PORT")):
            port = self.settings.get(key)
            if not port:
                refs.append({"ref_id": ref_id, "configured": False})
                continue
            try:
                snap = self._read_ibp_snapshot(port)
                refs.append({"ref_id": ref_id, "configured": True, **snap})
            except Exception as exc:  # noqa: BLE001
                refs.append({"ref_id": ref_id, "configured": True, "ok": False, "error": str(exc)})
                failures += 1
        configured_count = sum(1 for r in refs if r.get("configured"))
        ok = configured_count > 0 and failures == 0 and all(r.get("ok", False) for r in refs if r.get("configured"))
        out = CheckResult("references", ok, f"{configured_count} configured, {failures} failed", payload={"references": refs}, elapsed_sec=time.time() - started)
        self._record_check(out)
        return out

    def _read_ibp_snapshot(self, port: str) -> dict[str, Any]:
        baudrate = int(self.settings.get("IBP_BAUDRATE", 115200))
        timeout = float(self.settings.get("IBP_TIMEOUT", 2.0))
        with serial.Serial(port=port, baudrate=baudrate, timeout=timeout, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE) as conn:
            time.sleep(0.1)
            sn = self._ibp_cmd(conn, "SYSSNR")
            valar = self._ibp_cmd(conn, "VALAR")
            parts = valar.split("/")
            if len(parts) != 3:
                raise RuntimeError(f"VALAR format invalid: {valar}")
            return {
                "ok": True,
                "serial_number": sn,
                "conductivity_ms_cm": float(parts[0].strip()),
                "temperature_c": float(parts[2].strip()),
            }

    @staticmethod
    def _ibp_cmd(conn: serial.Serial, command: str) -> str:
        conn.reset_input_buffer()
        conn.write((command + "\r").encode("ascii"))
        conn.flush()
        out = b""
        start = time.time()
        while time.time() - start < 2.0:
            b = conn.read(1)
            if not b:
                continue
            if b == b"\r":
                break
            out += b
        text = out.decode("ascii", errors="ignore").strip()
        if not text:
            raise RuntimeError(f"No response for {command}")
        return text

    def check_pump(self, allow_motion: bool = False, pulse_seconds: float = 1.0) -> CheckResult:
        started = time.time()
        port = self.settings.get("SYRINGE_PUMP_PORT")
        if not port:
            out = CheckResult("pump", False, "Pump port not configured", elapsed_sec=time.time() - started)
            self._record_check(out)
            return out
        pump = SyringePumpThread(port, baudrate=int(self.settings.get("PUMP_BAUDRATE", 19200)))
        try:
            pump.run()
            if not pump.running or not pump.serial_connection:
                raise RuntimeError("Unable to open/identify pump")
            ver = pump.send_command("VER")
            if not ver:
                raise RuntimeError("No response to VER")
            if allow_motion:
                pump.send_command("RUN")
                time.sleep(max(0.1, float(pulse_seconds)))
                pump.send_command("STP")
            out = CheckResult("pump", True, f"Pump responsive (VER={ver})", elapsed_sec=time.time() - started)
        except Exception as exc:  # noqa: BLE001
            out = CheckResult("pump", False, f"Pump check failed: {exc}", elapsed_sec=time.time() - started)
        finally:
            try:
                pump.stop()
            except Exception:  # noqa: BLE001
                pass
        self._record_check(out)
        return out

    def check_chiller(self, allow_motion: bool = False, pulse_seconds: float = 1.0) -> CheckResult:
        started = time.time()
        port = self.settings.get("CHILLER_PORT")
        if not port:
            out = CheckResult("chiller", False, "Chiller port not configured", elapsed_sec=time.time() - started)
            self._record_check(out)
            return out
        chiller = ChillerThread(port, baudrate=int(self.settings.get("CHILLER_BAUDRATE", 4800)))
        try:
            chiller.run()
            if not chiller.running or not chiller.serial_connection:
                raise RuntimeError("Unable to open chiller connection")
            temp = chiller.read_temperature()
            if temp is None:
                raise RuntimeError("No valid temperature response")
            if allow_motion:
                chiller.start_chiller()
                time.sleep(max(0.1, float(pulse_seconds)))
                chiller.stop_chiller()
            out = CheckResult("chiller", True, f"Chiller responsive (temp={temp:.2f} C)", payload={"temp": temp}, elapsed_sec=time.time() - started)
        except Exception as exc:  # noqa: BLE001
            out = CheckResult("chiller", False, f"Chiller check failed: {exc}", elapsed_sec=time.time() - started)
        finally:
            try:
                chiller.stop()
            except Exception:  # noqa: BLE001
                pass
        self._record_check(out)
        return out

    def check_tic(self, tic_id: str, allow_motion: bool = False, pulse_seconds: float = 1.0) -> CheckResult:
        started = time.time()
        tic_id = str(tic_id).upper()
        serial_number = self.settings.get("TIC_A_SERIAL_NUMBER" if tic_id == "A" else "TIC_B_SERIAL_NUMBER")
        name = f"tic_{tic_id.lower()}"
        if not serial_number:
            out = CheckResult(name, False, f"Tic {tic_id} serial not configured", elapsed_sec=time.time() - started)
            self._record_check(out)
            return out
        tic = TicThread(serial_number)
        try:
            tic.run()
            status = tic.get_status()
            if not status:
                raise RuntimeError("No status response")
            if allow_motion:
                tic.energize()
                tic.set_velocity(100000)
                time.sleep(max(0.1, float(pulse_seconds)))
                tic.set_velocity(0)
                tic.deenergize()
            out = CheckResult(name, True, f"Tic {tic_id} responsive", payload={"status": status}, elapsed_sec=time.time() - started)
        except Exception as exc:  # noqa: BLE001
            out = CheckResult(name, False, f"Tic {tic_id} check failed: {exc}", elapsed_sec=time.time() - started)
        finally:
            try:
                tic.stop()
            except Exception:  # noqa: BLE001
                pass
        self._record_check(out)
        return out

    def run_named_check(self, name: str, allow_motion: bool = False, pulse_seconds: float = 1.0, sensor_attempts: int = 2) -> CheckResult:
        if name == "sensors":
            return self.check_sensors(attempts=sensor_attempts)
        if name == "references":
            return self.check_references()
        if name == "pump":
            return self.check_pump(allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        if name == "chiller":
            return self.check_chiller(allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        if name == "tic_a":
            return self.check_tic("A", allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        if name == "tic_b":
            return self.check_tic("B", allow_motion=allow_motion, pulse_seconds=pulse_seconds)
        out = CheckResult(name, False, f"Unknown check: {name}")
        self._record_check(out)
        return out

    def run_workflow(self, allow_motion: bool, pulse_seconds: float, sensor_attempts: int) -> int:
        self.print_config_summary()
        order = ["sensors", "pump", "chiller", "tic_a", "tic_b", "references"]
        results = []
        for idx, name in enumerate(order, start=1):
            print(f"\nStep {idx}/{len(order)}: {name}")
            res = self.run_named_check(name, allow_motion=allow_motion, pulse_seconds=pulse_seconds, sensor_attempts=sensor_attempts)
            self.print_check(res)
            if name == "sensors" and res.payload and res.payload.get("snapshot"):
                for row in res.payload["snapshot"]:
                    print(f"  U{row.get('unit_id')} {row.get('port')}: detected={row.get('detected')} parse_ok={row.get('parse_ok')} lines={row.get('non_empty_lines')}")
            results.append(res)
        failed = [r for r in results if not r.ok]
        print("\n=== Readiness Summary ===")
        if not failed:
            print("PASS: all components ready.")
            return 0
        print(f"FAIL: {len(failed)} component(s) failed.")
        for f in failed:
            print(f"  - {f.name}: {f.detail}")
        return 2

    def validate_interlocks(self, protocol: ProtocolHandler) -> list[str]:
        inter = self.policy.get("interlocks", {})
        max_rate = float(inter.get("max_pump_rate", 12.0))
        min_temp = float(inter.get("min_chiller_temp_c", 5.0))
        max_temp = float(inter.get("max_chiller_temp_c", 40.0))
        max_vel = int(inter.get("max_tic_velocity_abs", 500000))
        errors = []
        for step in protocol.protocol_steps:
            if "rate" in (step.pump_settings or {}):
                rate = float(step.pump_settings["rate"])
                if rate > max_rate:
                    errors.append(f"step {step.step_number}: pump rate {rate} > {max_rate}")
            if "temperature" in (step.chiller_settings or {}):
                t = float(step.chiller_settings["temperature"])
                if t < min_temp or t > max_temp:
                    errors.append(f"step {step.step_number}: chiller temp {t} outside [{min_temp}, {max_temp}]")
            for tic_name, settings in (("A", step.tic_a_settings or {}), ("B", step.tic_b_settings or {})):
                if "velocity" in settings:
                    v = int(settings["velocity"])
                    if abs(v) > max_vel:
                        errors.append(f"step {step.step_number}: tic {tic_name} velocity {v} exceeds {max_vel}")
        return errors

    def safe_recovery(self) -> None:
        try:
            print("[WARN] entering safe recovery -> stop_all_devices()")
            self.device_controller.stop_all_devices()
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] safe recovery failed: {exc}")

    def run_recipe(self, recipe_path: str, dry_run: bool, skip_waits: bool, sample_sensors_each_step: bool, mode_name: str | None, enforce_gate: bool) -> int:
        protocol = ProtocolHandler()
        if not protocol.load_protocol(recipe_path):
            print(f"[ERROR] failed to load recipe: {recipe_path}")
            return 2
        recipe_sha = _sha256(recipe_path)
        mode_policy = self.policy.get("modes", {}).get(mode_name or "", {})
        data_policy = mode_policy.get("data_policy", "diagnostic")
        entry_checks = list(mode_policy.get("entry_checks", []))
        exit_checks = list(mode_policy.get("exit_checks", []))
        preflight_required = bool(mode_policy.get("preflight_required", False))
        reference_each_step = bool(mode_policy.get("reference_each_step", False))

        if self.manifest is not None:
            self.manifest["mode_runs"].append(
                {
                    "mode": mode_name or "custom_recipe",
                    "recipe_path": str(Path(recipe_path).resolve()),
                    "recipe_sha256": recipe_sha,
                    "data_policy": data_policy,
                    "entry_checks": entry_checks,
                    "exit_checks": exit_checks,
                }
            )
            self._save_manifest()

        if enforce_gate and preflight_required and not dry_run:
            print("[INFO] preflight gate required, running workflow gate")
            if self.run_workflow(allow_motion=False, pulse_seconds=1.0, sensor_attempts=2) != 0:
                print("[ERROR] preflight gate failed, recipe blocked")
                return 2

        if dry_run:
            if entry_checks:
                print(f"[INFO] dry-run: skipping entry checks {entry_checks}")
        else:
            for c in entry_checks:
                r = self.run_named_check(c, allow_motion=False, pulse_seconds=1.0, sensor_attempts=2)
                self.print_check(r)
                if not r.ok:
                    print(f"[ERROR] entry criterion failed: {c}")
                    return 2

        interlock_errors = self.validate_interlocks(protocol)
        if interlock_errors:
            print("[ERROR] interlock violations found, recipe blocked:")
            for err in interlock_errors:
                print(f"  - {err}")
            return 2

        print(f"\nLoaded recipe: {recipe_path}")
        print(protocol.get_protocol_summary())
        print(f"[INFO] recipe_sha256={recipe_sha}")
        print(f"[INFO] data_policy={data_policy}")

        try:
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
                    self.print_check(self.check_sensors(attempts=1))
                if reference_each_step:
                    if dry_run:
                        print("[INFO] dry-run: skipping per-step reference capture")
                    else:
                        self.print_check(self.check_references())

                if skip_waits or dry_run:
                    print("[INFO] wait skipped")
                else:
                    wait_sec = max(0, int(round(float(step.duration_minutes) * 60.0)))
                    print(f"[INFO] hold {wait_sec}s")
                    time.sleep(wait_sec)
        except KeyboardInterrupt:
            print("[WARN] interrupted by user")
            self.safe_recovery()
            return 130
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] recipe execution failed: {exc}")
            print(traceback.format_exc())
            self.safe_recovery()
            return 2

        if dry_run:
            if exit_checks:
                print(f"[INFO] dry-run: skipping exit checks {exit_checks}")
        else:
            for c in exit_checks:
                r = self.run_named_check(c, allow_motion=False, pulse_seconds=1.0, sensor_attempts=2)
                self.print_check(r)
                if not r.ok:
                    print(f"[WARN] exit criterion failed: {c}")

        if not dry_run:
            print("[INFO] recipe complete -> safe stop")
            self.device_controller.stop_all_devices()
        print("Recipe run complete.")
        return 0

    def run_chain(self, modes: list[str], dry_run: bool, skip_waits: bool, sample_sensors_each_step: bool) -> int:
        if not modes:
            print("[ERROR] empty mode chain")
            return 2
        for mode in modes:
            recipe = resolve_mode_recipe(mode)
            if not Path(recipe).exists():
                print(f"[ERROR] missing mode recipe: {mode} -> {recipe}")
                return 2
            print(f"\n=== Running mode: {mode} ===")
            rc = self.run_recipe(
                recipe_path=recipe,
                dry_run=dry_run,
                skip_waits=skip_waits,
                sample_sensors_each_step=sample_sensors_each_step,
                mode_name=mode,
                enforce_gate=True,
            )
            if rc != 0:
                print(f"[ERROR] chain halted at mode '{mode}'")
                return rc
        return 0

    def link_analysis(self, coeff_file: str | None, analysis_log: str | None, report_file: str | None) -> int:
        if self.manifest is None:
            return 2
        payload: dict[str, Any] = {"linked_at_utc": _utc_now()}
        if coeff_file:
            payload["coeff_file"] = os.path.abspath(coeff_file)
            if Path(coeff_file).exists():
                payload["coeff_sha256"] = _sha256(coeff_file)
        if analysis_log:
            payload["analysis_log"] = os.path.abspath(analysis_log)
        if report_file:
            payload["report_file"] = os.path.abspath(report_file)
        self.manifest["analysis_link"] = payload
        self._save_manifest()
        print("[INFO] linked analysis artifacts")
        return 0

    def link_programming(self, programming_log: str | None, status: str, notes: str | None) -> int:
        if self.manifest is None:
            return 2
        payload: dict[str, Any] = {"linked_at_utc": _utc_now(), "status": status}
        if programming_log:
            payload["programming_log"] = os.path.abspath(programming_log)
        if notes:
            payload["notes"] = notes
        self.manifest["programming_link"] = payload
        self._save_manifest()
        print("[INFO] linked programming artifacts")
        return 0

    @staticmethod
    def _enter_pressed() -> bool:
        """Non-blocking Enter detection for Windows terminals."""
        try:
            import msvcrt  # type: ignore
        except Exception:  # noqa: BLE001
            return False
        pressed = False
        while msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                pressed = True
        return pressed

    @staticmethod
    def _pump_query(pump: SyringePumpThread, command: str) -> str:
        try:
            resp = pump.send_command(command)
            return resp or ""
        except Exception:  # noqa: BLE001
            return ""

    def monitor(
        self,
        interval: float,
        duration_sec: int | None = None,
        output_csv: str | None = None,
        stop_on_enter: bool = False,
    ) -> int:
        interval = max(0.2, float(interval))
        output_path = Path(output_csv).resolve() if output_csv else ((self.run_dir / "monitor.csv") if self.run_dir else Path.cwd() / "data" / "monitor.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sensors_cfg = self.settings.get("CN0359_SENSORS", [])
        sensor_ids = [int(cfg[0]) for cfg in sensors_cfg if len(cfg) >= 2]
        sensor_handler = None
        pump = None
        chiller = None
        tic_a = None
        tic_b = None
        pump_ver = ""
        pump_dir = ""
        pump_rate = ""
        pump_volume = ""
        start = time.time()
        last_pump_ver_t = 0.0
        last_pump_detail_t = 0.0

        header = ["timestamp_utc"]
        for sid in sensor_ids:
            header.extend([f"sensor_{sid}_cond_s_cm", f"sensor_{sid}_temp_c"])
        header.extend(
            [
                "ref1_cond_ms_cm",
                "ref1_temp_c",
                "ref2_cond_ms_cm",
                "ref2_temp_c",
                "pump_connected",
                "pump_ver",
                "pump_dir",
                "pump_rate",
                "pump_volume",
                "chiller_connected",
                "chiller_temp_c",
                "tic_a_connected",
                "tic_a_pos",
                "tic_a_vel",
                "tic_b_connected",
                "tic_b_pos",
                "tic_b_vel",
                "errors",
            ]
        )

        print(f"[INFO] monitor interval={interval}s duration={duration_sec or 'infinite'} csv={output_path}")
        if stop_on_enter:
            print("[INFO] monitor stop-on-enter enabled (press Enter to stop).")
        try:
            # Setup sensors
            if sensors_cfg:
                sensor_handler = CN0359Handler(
                    sensors_cfg,
                    baudrate=int(self.settings.get("CN0359_BAUDRATE", 115200)),
                    query_interval=max(0.1, interval),
                )
                sensor_handler.running = True
                sensor_handler._open_connections()

            # Setup actuators
            if self.settings.get("SYRINGE_PUMP_PORT"):
                pump = SyringePumpThread(self.settings.get("SYRINGE_PUMP_PORT"), baudrate=int(self.settings.get("PUMP_BAUDRATE", 19200)))
                pump.run()
                if pump.running and pump.serial_connection:
                    pump_ver = pump.send_command("VER") or ""
            if self.settings.get("CHILLER_PORT"):
                chiller = ChillerThread(self.settings.get("CHILLER_PORT"), baudrate=int(self.settings.get("CHILLER_BAUDRATE", 4800)))
                chiller.run()
            if self.settings.get("TIC_A_SERIAL_NUMBER"):
                tic_a = TicThread(self.settings.get("TIC_A_SERIAL_NUMBER"))
                tic_a.run()
            if self.settings.get("TIC_B_SERIAL_NUMBER"):
                tic_b = TicThread(self.settings.get("TIC_B_SERIAL_NUMBER"))
                tic_b.run()

            with open(output_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=header)
                writer.writeheader()

                while True:
                    now = time.time()
                    if stop_on_enter and self._enter_pressed():
                        print("[INFO] monitor stopped by Enter key.")
                        break
                    if duration_sec is not None and (now - start) >= int(duration_sec):
                        print("[INFO] monitor duration reached, stopping.")
                        break

                    row: dict[str, Any] = {"timestamp_utc": _utc_now(), "errors": ""}
                    errors: list[str] = []

                    # Sensors poll
                    sensor_latest: dict[int, dict[str, Any]] = {}
                    if sensor_handler is not None:
                        try:
                            raw = sensor_handler._poll_all_sensors()
                            parsed = CN0359Parser.parse_all_sensors(raw, datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
                            for unit in parsed.get("dut_units", []):
                                sensor_latest[int(unit["unit_id"])] = unit
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"sensors:{exc}")

                    for sid in sensor_ids:
                        unit = sensor_latest.get(sid)
                        row[f"sensor_{sid}_cond_s_cm"] = unit["conductivity"].get("conductivity_s_cm") if unit else ""
                        row[f"sensor_{sid}_temp_c"] = unit["temperature"].get("temperature_c") if unit else ""

                    # References
                    for ref_id, key in ((1, "IBP_REF1_PORT"), (2, "IBP_REF2_PORT")):
                        port = self.settings.get(key)
                        if not port:
                            row[f"ref{ref_id}_cond_ms_cm"] = ""
                            row[f"ref{ref_id}_temp_c"] = ""
                            continue
                        try:
                            snap = self._read_ibp_snapshot(port)
                            row[f"ref{ref_id}_cond_ms_cm"] = snap.get("conductivity_ms_cm", "")
                            row[f"ref{ref_id}_temp_c"] = snap.get("temperature_c", "")
                        except Exception as exc:  # noqa: BLE001
                            row[f"ref{ref_id}_cond_ms_cm"] = ""
                            row[f"ref{ref_id}_temp_c"] = ""
                            errors.append(f"ref{ref_id}:{exc}")

                    # Pump
                    row["pump_connected"] = bool(pump and pump.running and pump.serial_connection)
                    if pump and pump.running and (now - last_pump_ver_t) >= 10.0:
                        try:
                            pump_ver = pump.send_command("VER") or pump_ver
                            last_pump_ver_t = now
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"pump:{exc}")
                    if pump and pump.running and (now - last_pump_detail_t) >= 5.0:
                        # Best-effort telemetry queries; blank when unsupported by firmware.
                        pump_dir = self._pump_query(pump, "DIR")
                        pump_rate = self._pump_query(pump, "RAT")
                        pump_volume = self._pump_query(pump, "VOL")
                        last_pump_detail_t = now
                    row["pump_ver"] = pump_ver
                    row["pump_dir"] = pump_dir
                    row["pump_rate"] = pump_rate
                    row["pump_volume"] = pump_volume

                    # Chiller
                    row["chiller_connected"] = bool(chiller and chiller.running and chiller.serial_connection)
                    if chiller and chiller.running:
                        try:
                            row["chiller_temp_c"] = chiller.read_temperature()
                        except Exception as exc:  # noqa: BLE001
                            row["chiller_temp_c"] = ""
                            errors.append(f"chiller:{exc}")
                    else:
                        row["chiller_temp_c"] = ""

                    # TIC A
                    row["tic_a_connected"] = bool(tic_a and tic_a.running)
                    if tic_a and tic_a.running:
                        try:
                            st = tic_a.get_status() or {}
                            row["tic_a_pos"] = st.get("position", "")
                            row["tic_a_vel"] = st.get("current_velocity", st.get("target_velocity", ""))
                        except Exception as exc:  # noqa: BLE001
                            row["tic_a_pos"] = ""
                            row["tic_a_vel"] = ""
                            errors.append(f"tic_a:{exc}")
                    else:
                        row["tic_a_pos"] = ""
                        row["tic_a_vel"] = ""

                    # TIC B
                    row["tic_b_connected"] = bool(tic_b and tic_b.running)
                    if tic_b and tic_b.running:
                        try:
                            st = tic_b.get_status() or {}
                            row["tic_b_pos"] = st.get("position", "")
                            row["tic_b_vel"] = st.get("current_velocity", st.get("target_velocity", ""))
                        except Exception as exc:  # noqa: BLE001
                            row["tic_b_pos"] = ""
                            row["tic_b_vel"] = ""
                            errors.append(f"tic_b:{exc}")
                    else:
                        row["tic_b_pos"] = ""
                        row["tic_b_vel"] = ""

                    row["errors"] = "; ".join(errors)
                    writer.writerow(row)
                    fh.flush()

                    # Console summary
                    sensor_chunks = []
                    for sid in sensor_ids:
                        c = row.get(f"sensor_{sid}_cond_s_cm", "")
                        t = row.get(f"sensor_{sid}_temp_c", "")
                        if c != "" or t != "":
                            sensor_chunks.append(f"U{sid}: cond={c} temp={t}")
                    summary = " | ".join(sensor_chunks) if sensor_chunks else "No DUT sensor data"
                    print(
                        f"[MONITOR] {row['timestamp_utc']} | {summary} | "
                        f"REF1={row.get('ref1_cond_ms_cm','')}/{row.get('ref1_temp_c','')} "
                        f"REF2={row.get('ref2_cond_ms_cm','')}/{row.get('ref2_temp_c','')} | "
                        f"PUMP(dir={row.get('pump_dir','')},rate={row.get('pump_rate','')},vol={row.get('pump_volume','')}) | "
                        f"CHILLER={row.get('chiller_temp_c','')} | "
                        f"TIC_A(pos={row.get('tic_a_pos','')},vel={row.get('tic_a_vel','')}) "
                        f"TIC_B(pos={row.get('tic_b_pos','')},vel={row.get('tic_b_vel','')})"
                    )
                    if row["errors"]:
                        print(f"[MONITOR-WARN] {row['errors']}")

                    time.sleep(interval)

            print(f"[INFO] monitor saved CSV: {output_path}")
            return 0
        except KeyboardInterrupt:
            print("[INFO] monitor interrupted by user.")
            return 130
        finally:
            if sensor_handler is not None:
                sensor_handler.running = False
                try:
                    sensor_handler.close_connection()
                except Exception:  # noqa: BLE001
                    pass
            if pump is not None:
                try:
                    pump.stop()
                except Exception:  # noqa: BLE001
                    pass
            if chiller is not None:
                try:
                    chiller.stop()
                except Exception:  # noqa: BLE001
                    pass
            if tic_a is not None:
                try:
                    tic_a.stop()
                except Exception:  # noqa: BLE001
                    pass
            if tic_b is not None:
                try:
                    tic_b.stop()
                except Exception:  # noqa: BLE001
                    pass


def print_modes(show_paths: bool = False) -> None:
    print("\nBuilt-in operational modes:")
    for mode in sorted(MODE_RECIPES.keys()):
        meta = MODE_RECIPES[mode]
        line = f"  - {mode}: {meta['description']}"
        if show_paths:
            line += f" ({(REPO_ROOT / meta['path']).resolve()})"
        print(line)


def resolve_mode_recipe(mode_name: str) -> str:
    return str((REPO_ROOT / MODE_RECIPES[str(mode_name).lower()]["path"]).resolve())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Enhanced IonIn operational CLI")
    sub = p.add_subparsers(dest="command", required=True)

    wf = sub.add_parser("workflow")
    wf.add_argument("--allow-motion", action="store_true")
    wf.add_argument("--pulse-seconds", type=float, default=1.0)
    wf.add_argument("--sensor-attempts", type=int, default=2)

    c = sub.add_parser("check")
    c.add_argument("component", choices=["sensors", "references", "pump", "chiller", "tic_a", "tic_b"])
    c.add_argument("--allow-motion", action="store_true")
    c.add_argument("--pulse-seconds", type=float, default=1.0)
    c.add_argument("--sensor-attempts", type=int, default=2)

    rr = sub.add_parser("run-recipe")
    rr.add_argument("recipe_path", nargs="?", default=None)
    rr.add_argument("--use-last", action="store_true", help="Reuse the last saved recipe path.")
    rr.add_argument("--dry-run", action="store_true")
    rr.add_argument("--skip-waits", action="store_true")
    rr.add_argument("--sample-sensors-each-step", action="store_true")

    lm = sub.add_parser("list-modes")
    lm.add_argument("--show-paths", action="store_true")

    rm = sub.add_parser("run-mode")
    rm.add_argument("mode", choices=sorted(MODE_RECIPES.keys()))
    rm.add_argument("--dry-run", action="store_true")
    rm.add_argument("--skip-waits", action="store_true")
    rm.add_argument("--sample-sensors-each-step", action="store_true")

    chain = sub.add_parser("run-chain")
    chain.add_argument("--modes", nargs="+", default=None)
    chain.add_argument("--dry-run", action="store_true")
    chain.add_argument("--skip-waits", action="store_true")
    chain.add_argument("--sample-sensors-each-step", action="store_true")

    la = sub.add_parser("link-analysis")
    la.add_argument("--coeff-file", default=None)
    la.add_argument("--analysis-log", default=None)
    la.add_argument("--report-file", default=None)

    lp = sub.add_parser("link-programming")
    lp.add_argument("--programming-log", default=None)
    lp.add_argument("--status", choices=["pass", "fail", "partial"], required=True)
    lp.add_argument("--notes", default=None)

    mon = sub.add_parser("monitor")
    mon.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds.")
    mon.add_argument("--duration-sec", type=int, default=None, help="Optional stop time in seconds.")
    mon.add_argument("--output-csv", default=None, help="Optional output CSV path.")
    mon.add_argument("--stop-on-enter", action="store_true", help="Stop monitor loop when Enter is pressed.")

    sub.add_parser("menu", help="Open interactive easy menu.")

    return p


def _select_menu_option(menu_items: list[tuple[str, str]]) -> str:
    """
    Let user select via arrows+Enter (Windows) or number input fallback.
    Returns the selected key (e.g. "1", "2", "0").
    """
    if not (hasattr(sys.stdin, "isatty") and sys.stdin.isatty()):
        return input("Select option: ").strip()

    try:
        import msvcrt  # type: ignore
    except Exception:  # noqa: BLE001
        return input("Select option: ").strip()

    idx = 0
    while True:
        os.system("cls")
        print("\n=== IonIn Easy Menu ===")
        for i, (key, label) in enumerate(menu_items):
            pointer = ">" if i == idx else " "
            print(f" {pointer} {key}) {label}")
        print("\nUse Up/Down + Enter, or press a number key.")

        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            return menu_items[idx][0]

        if ch in ("\x00", "\xe0"):
            keycode = msvcrt.getwch()
            if keycode == "H":  # up
                idx = (idx - 1) % len(menu_items)
            elif keycode == "P":  # down
                idx = (idx + 1) % len(menu_items)
            continue

        if ch.isdigit():
            for i, (key, _label) in enumerate(menu_items):
                if ch == key:
                    idx = i
                    return key


def _pause_to_menu() -> None:
    try:
        input("\nPress Enter to return to menu...")
    except EOFError:
        pass


def _run_easy_menu(settings: dict[str, Any], policy: dict[str, Any], cli_state: dict[str, Any]) -> int:
    menu_items = [
        ("1", "Start-of-day workflow (recommended first)"),
        ("2", "Live monitor"),
        ("3", "Run one mode"),
        ("4", "Run mode chain"),
        ("5", "Run recipe file"),
        ("6", "Run last recipe"),
        ("7", "List modes"),
        ("0", "Exit"),
    ]

    while True:
        choice = _select_menu_option(menu_items).strip()
        if choice == "0":
            return 0

        flow = OpsWorkflow(settings=settings, policy=policy)
        rc = 2

        if choice == "1":
            allow_motion = _prompt_yes_no("Allow actuator motion during checks?", default=False)
            pulse = _prompt_float("Pulse seconds", 1.0)
            attempts = _prompt_int("Sensor attempts", 2)
            flow.begin_run(command="menu-workflow", args={"allow_motion": allow_motion, "pulse_seconds": pulse, "sensor_attempts": attempts})
            try:
                rc = flow.run_workflow(allow_motion=allow_motion, pulse_seconds=pulse, sensor_attempts=attempts)
            finally:
                flow.finalize_run(rc)
            print(f"\n[INFO] Workflow exit code: {rc}")
            _pause_to_menu()
            continue

        if choice == "2":
            interval = _prompt_float("Monitor interval (sec)", 1.0)
            dur = _prompt_int("Duration seconds (0 = infinite)", 0)
            stop_on_enter = _prompt_yes_no("Stop when Enter is pressed?", default=True)
            flow.begin_run(command="menu-monitor", args={"interval": interval, "duration_sec": dur if dur > 0 else None, "stop_on_enter": stop_on_enter})
            try:
                rc = flow.monitor(interval=interval, duration_sec=(dur if dur > 0 else None), output_csv=None, stop_on_enter=stop_on_enter)
            finally:
                flow.finalize_run(rc)
            print(f"\n[INFO] Monitor exit code: {rc}")
            _pause_to_menu()
            continue

        if choice == "3":
            mode_list = sorted(MODE_RECIPES.keys())
            print("\nAvailable modes:")
            for i, mode_name in enumerate(mode_list, start=1):
                print(f"  {i}) {mode_name}")
            idx = _prompt_int("Mode number", 1)
            idx = max(1, min(len(mode_list), idx))
            mode_name = mode_list[idx - 1]
            dry = _prompt_yes_no("Dry run?", default=False)
            skip_waits = _prompt_yes_no("Skip waits?", default=False)
            flow.begin_run(command="menu-run-mode", args={"mode": mode_name, "dry_run": dry, "skip_waits": skip_waits})
            try:
                recipe = resolve_mode_recipe(mode_name)
                rc = flow.run_recipe(recipe_path=recipe, dry_run=dry, skip_waits=skip_waits, sample_sensors_each_step=False, mode_name=mode_name, enforce_gate=True)
                if rc == 0:
                    cli_state["last_recipe_path"] = recipe
                    cli_state["last_recipe_used_at_utc"] = _utc_now()
                    save_cli_state(cli_state)
            finally:
                flow.finalize_run(rc)
            print(f"\n[INFO] Run-mode exit code: {rc}")
            _pause_to_menu()
            continue

        if choice == "4":
            dry = _prompt_yes_no("Dry run?", default=False)
            skip_waits = _prompt_yes_no("Skip waits?", default=False)
            modes = list(policy.get("chain_default", []))
            print(f"Using default chain: {modes}")
            flow.begin_run(command="menu-run-chain", args={"modes": modes, "dry_run": dry, "skip_waits": skip_waits})
            try:
                rc = flow.run_chain(modes=modes, dry_run=dry, skip_waits=skip_waits, sample_sensors_each_step=False)
            finally:
                flow.finalize_run(rc)
            print(f"\n[INFO] Run-chain exit code: {rc}")
            _pause_to_menu()
            continue

        if choice == "5":
            recipe_in = input("Enter recipe path: ").strip()
            recipe = resolve_recipe_with_history(recipe_in if recipe_in else None, False, cli_state)
            if not recipe or not Path(recipe).exists():
                print(f"[ERROR] recipe not found: {recipe}")
                _pause_to_menu()
                continue
            dry = _prompt_yes_no("Dry run?", default=False)
            skip_waits = _prompt_yes_no("Skip waits?", default=False)
            flow.begin_run(command="menu-run-recipe", args={"recipe_path": recipe, "dry_run": dry, "skip_waits": skip_waits})
            try:
                rc = flow.run_recipe(recipe_path=recipe, dry_run=dry, skip_waits=skip_waits, sample_sensors_each_step=False, mode_name=None, enforce_gate=True)
                if rc == 0:
                    cli_state["last_recipe_path"] = recipe
                    cli_state["last_recipe_used_at_utc"] = _utc_now()
                    save_cli_state(cli_state)
            finally:
                flow.finalize_run(rc)
            print(f"\n[INFO] Run-recipe exit code: {rc}")
            _pause_to_menu()
            continue

        if choice == "6":
            recipe = resolve_recipe_with_history(None, True, cli_state)
            if not recipe or not Path(recipe).exists():
                print(f"[ERROR] last recipe not found: {recipe}")
                _pause_to_menu()
                continue
            dry = _prompt_yes_no("Dry run?", default=False)
            skip_waits = _prompt_yes_no("Skip waits?", default=False)
            flow.begin_run(command="menu-run-last-recipe", args={"recipe_path": recipe, "dry_run": dry, "skip_waits": skip_waits})
            try:
                rc = flow.run_recipe(recipe_path=recipe, dry_run=dry, skip_waits=skip_waits, sample_sensors_each_step=False, mode_name=None, enforce_gate=True)
                if rc == 0:
                    cli_state["last_recipe_path"] = recipe
                    cli_state["last_recipe_used_at_utc"] = _utc_now()
                    save_cli_state(cli_state)
            finally:
                flow.finalize_run(rc)
            print(f"\n[INFO] Run-last-recipe exit code: {rc}")
            _pause_to_menu()
            continue

        if choice == "7":
            flow.begin_run(command="menu-list-modes", args={})
            try:
                print_modes(show_paths=True)
                if cli_state.get("last_recipe_path"):
                    print(f"\nLast saved recipe: {cli_state.get('last_recipe_path')}")
                rc = 0
            finally:
                flow.finalize_run(rc)
            _pause_to_menu()
            continue

        print("[ERROR] invalid menu selection")
        _pause_to_menu()


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    policy = load_policy()
    cli_state = load_cli_state()

    # Easy mode: running with no subcommand drops into interactive menu.
    if argv is None and len(sys.argv) == 1:
        return _run_easy_menu(settings=settings, policy=policy, cli_state=cli_state)

    args = build_parser().parse_args(argv)
    if args.command == "menu":
        return _run_easy_menu(settings=settings, policy=policy, cli_state=cli_state)

    flow = OpsWorkflow(settings=settings, policy=policy)
    flow.begin_run(command=args.command, args=vars(args))

    rc = 2
    try:
        if args.command == "workflow":
            rc = flow.run_workflow(
                allow_motion=bool(args.allow_motion),
                pulse_seconds=float(args.pulse_seconds),
                sensor_attempts=int(args.sensor_attempts),
            )
        elif args.command == "check":
            res = flow.run_named_check(
                args.component,
                allow_motion=bool(args.allow_motion),
                pulse_seconds=float(args.pulse_seconds),
                sensor_attempts=int(args.sensor_attempts),
            )
            flow.print_check(res)
            rc = 0 if res.ok else 2
        elif args.command == "run-recipe":
            recipe = resolve_recipe_with_history(args.recipe_path, bool(args.use_last), cli_state)
            if not recipe:
                rc = 2
            elif not Path(recipe).exists():
                print(f"[ERROR] recipe not found: {recipe}")
                rc = 2
            else:
                rc = flow.run_recipe(
                    recipe_path=recipe,
                    dry_run=bool(args.dry_run),
                    skip_waits=bool(args.skip_waits),
                    sample_sensors_each_step=bool(args.sample_sensors_each_step),
                    mode_name=None,
                    enforce_gate=True,
                )
                if rc == 0:
                    cli_state["last_recipe_path"] = recipe
                    cli_state["last_recipe_used_at_utc"] = _utc_now()
                    save_cli_state(cli_state)
        elif args.command == "list-modes":
            print_modes(show_paths=bool(args.show_paths))
            print(f"\nPolicy file: {POLICY_PATH}")
            if cli_state.get("last_recipe_path"):
                print(f"Last saved recipe: {cli_state.get('last_recipe_path')}")
            rc = 0
        elif args.command == "run-mode":
            recipe = resolve_mode_recipe(args.mode)
            rc = flow.run_recipe(
                recipe_path=recipe,
                dry_run=bool(args.dry_run),
                skip_waits=bool(args.skip_waits),
                sample_sensors_each_step=bool(args.sample_sensors_each_step),
                mode_name=args.mode,
                enforce_gate=True,
            )
            if rc == 0:
                cli_state["last_recipe_path"] = recipe
                cli_state["last_recipe_used_at_utc"] = _utc_now()
                save_cli_state(cli_state)
        elif args.command == "run-chain":
            modes = list(args.modes) if args.modes else list(policy.get("chain_default", []))
            print(f"Mode chain: {modes}")
            rc = flow.run_chain(
                modes=modes,
                dry_run=bool(args.dry_run),
                skip_waits=bool(args.skip_waits),
                sample_sensors_each_step=bool(args.sample_sensors_each_step),
            )
        elif args.command == "link-analysis":
            rc = flow.link_analysis(args.coeff_file, args.analysis_log, args.report_file)
        elif args.command == "link-programming":
            rc = flow.link_programming(args.programming_log, args.status, args.notes)
        elif args.command == "monitor":
            rc = flow.monitor(
                interval=float(args.interval),
                duration_sec=int(args.duration_sec) if args.duration_sec is not None else None,
                output_csv=args.output_csv,
                stop_on_enter=bool(args.stop_on_enter),
            )
        else:
            print("[ERROR] unknown command")
            rc = 2
    finally:
        flow.finalize_run(rc)
    return int(rc)


if __name__ == "__main__":
    sys.exit(main())
