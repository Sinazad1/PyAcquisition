"""
IonIn fixture adapter for bridging AcquisitionWindow/device handlers.

This adapter allows IonIn runtime orchestration to reuse the application's
existing hardware control methods without duplicating driver logic.
"""

from __future__ import annotations

import time
from typing import Any

from ionin.hardware.interfaces import FixtureAdapter


class AppFixtureAdapter(FixtureAdapter):
    """Bridge IonIn runtime calls to existing AcquisitionWindow handlers."""

    def __init__(self, acquisition_window):
        self.window = acquisition_window

    def _log(self, message: str, color: str = "#00CED1", log_type: str = "IONIN-RUNTIME") -> None:
        if hasattr(self.window, "log_event"):
            self.window.log_event(message, color=color, log_type=log_type)

    def set_pump_rate(self, pump_id: int, rate_ml_min: float) -> None:
        settings = {"pump_id": int(pump_id), "rate": float(rate_ml_min), "run": True}
        self.apply_pump_settings(settings)

    def apply_pump_settings(self, settings: dict[str, Any]) -> None:
        if hasattr(self.window, "apply_pump_settings"):
            self.window.apply_pump_settings(settings)
            self._log(f"Applied pump settings via IonIn: {settings}")
        else:
            raise RuntimeError("Acquisition window missing apply_pump_settings()")

    def set_heater_setpoint(self, temperature_c: float) -> None:
        self.apply_chiller_settings({"temperature": float(temperature_c), "start": True})

    def apply_tic_settings(self, settings: dict[str, Any], tic_id: str) -> None:
        if str(tic_id).upper() == "A":
            if hasattr(self.window, "apply_tic_a_settings"):
                self.window.apply_tic_a_settings(settings)
            else:
                raise RuntimeError("Acquisition window missing apply_tic_a_settings()")
        else:
            if hasattr(self.window, "apply_tic_b_settings"):
                self.window.apply_tic_b_settings(settings)
            else:
                raise RuntimeError("Acquisition window missing apply_tic_b_settings()")
        self._log(f"Applied TIC {tic_id} settings via IonIn: {settings}")

    def apply_chiller_settings(self, settings: dict[str, Any]) -> None:
        if hasattr(self.window, "apply_chiller_settings"):
            self.window.apply_chiller_settings(settings)
            self._log(f"Applied chiller settings via IonIn: {settings}")
        else:
            raise RuntimeError("Acquisition window missing apply_chiller_settings()")

    def read_dut_sample(self) -> dict[str, Any]:
        dm = getattr(self.window, "data_manager", None)
        if dm is None:
            return {}
        for unit_id in range(1, getattr(dm, "max_dut_units", 8) + 1):
            series = dm.get_dut_data(unit_id)
            if series and series["timestamps"]:
                idx = -1
                return {
                    "unit_id": unit_id,
                    "timestamp": series["timestamps"][idx],
                    "conductivity_rzmag_ohm": series["conductivity_rzmag"][idx],
                    "conductivity_s_cm": series["conductivity_s_cm"][idx],
                    "temperature_rzmag_ohm": series["temperature_rzmag"][idx],
                }
        return {}

    def read_reference_sample(self) -> dict[str, Any]:
        dm = getattr(self.window, "data_manager", None)
        if dm is None:
            return {}
        payload: dict[str, Any] = {}
        for ref_id in (1, 2):
            series = dm.get_reference_data(ref_id)
            if series and series["timestamps"]:
                idx = -1
                payload[f"ref{ref_id}_conductivity_ms_cm"] = series["conductivity_rzmag"][idx]
                payload[f"ref{ref_id}_temperature_c"] = series["temperature_rzmag"][idx]
        return payload

    def emit_event(self, name: str, payload: dict[str, Any] | None = None) -> None:
        details = f"{name} | payload={payload or {}}"
        self._log(details, color="#9370DB", log_type="IONIN-EVENT")

    def sleep_seconds(self, seconds: float) -> None:
        time.sleep(float(seconds))
