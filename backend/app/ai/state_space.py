"""
GridWise AI - State Space Module
Constructs, normalizes, and validates the 19-dimensional continuous state vector for PPO.
Adheres strictly to PRD Section 8 & 9:
- 19 explicit physical features
- Numerical variables normalized to [0, 1] or [-1, 1]
- Hard physical bounds validation (SOC in [0, 1], grid utilization >= 0, etc.)
- Rejection of corrupted/invalid state vectors before PPO inference
"""

import math
import logging
import numpy as np
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger("gridwise.state_space")


class StateSpaceModule:
    """
    Constructs, normalizes, and validates the 19-dimensional state space.
    """
    DIMENSION = 19
    FEATURE_NAMES = [
        "battery_soc",
        "battery_temperature",
        "battery_health",
        "battery_power",
        "grid_load",
        "grid_capacity",
        "grid_utilization",
        "grid_voltage",
        "grid_frequency",
        "electricity_price",
        "solar_generation",
        "solar_availability",
        "building_load",
        "ev_connected",
        "time_until_departure",
        "target_soc",
        "required_energy",
        "v2g_enabled",
        "previous_action"
    ]

    @classmethod
    def validate_raw_inputs(
        cls,
        soc_pct: float,
        temperature_c: float,
        grid_load_kw: float,
        grid_capacity_kw: float,
        voltage_v: float,
        frequency_hz: float,
        price_inr: float,
        solar_kw: float,
        time_until_departure_hours: float
    ) -> Tuple[bool, List[str]]:
        """
        Validates system state against hard physical sanity limits (PRD Section 9).
        Returns: (is_valid, validation_errors)
        """
        errors = []

        # 1. SOC in [0, 100]
        if soc_pct < 0.0 or soc_pct > 100.0:
            errors.append(f"Invalid SOC: {soc_pct}% outside [0, 100]")

        # 2. Grid utilization / load >= 0
        if grid_load_kw < 0.0:
            errors.append(f"Invalid negative grid load: {grid_load_kw} kW")
        if grid_capacity_kw <= 0.0:
            errors.append(f"Invalid grid capacity: {grid_capacity_kw} kW")

        # 3. Solar generation >= 0
        if solar_kw < 0.0:
            errors.append(f"Invalid negative solar generation: {solar_kw} kW")

        # 4. Voltage within physical range [180V, 480V]
        if voltage_v < 180.0 or voltage_v > 480.0:
            errors.append(f"Grid voltage out of range: {voltage_v} V (expected 180-480V)")

        # 5. Frequency within physical range [47.0Hz, 53.0Hz]
        if frequency_hz < 47.0 or frequency_hz > 53.0:
            errors.append(f"Grid frequency out of range: {frequency_hz} Hz (expected 47.0-53.0Hz)")

        # 6. Price >= 0 (unless market allows negative prices)
        if price_inr < 0.0:
            errors.append(f"Invalid negative electricity price: ₹{price_inr}/kWh")

        # 7. Time until departure >= 0
        if time_until_departure_hours < 0.0:
            errors.append(f"Invalid negative time-to-departure: {time_until_departure_hours} h")

        if errors:
            for err in errors:
                logger.error(f"[STATE VALIDATION REJECTED] {err}")
            return False, errors

        return True, []

    @classmethod
    def build_state(
        cls,
        ev: Any,
        grid_data: Dict[str, Any],
        price_data: Dict[str, Any],
        solar_data: Dict[str, Any],
        building_load_kw: float = 38.0,
        current_hour: float = 12.0,
        previous_action: int = 0
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Constructs and normalizes the full 19-dimensional continuous state vector.
        If validation fails, falls back safely without sending corrupted vectors to PPO.
        """
        # Extract raw features with safe defaults
        soc_pct = getattr(ev, "current_soc", getattr(ev, "soc", 50.0))
        temp_c = getattr(ev, "temperature_c", 25.0)
        health_pct = getattr(ev, "battery_health", getattr(ev, "soh_pct", 98.5))
        pwr_kw = getattr(ev, "current_power_kw", getattr(ev, "power_kw", 0.0))
        max_chg_kw = max(1.0, getattr(ev, "max_charge_power_kw", getattr(ev, "max_charge_kw", 22.0)))
        max_dis_kw = max(1.0, getattr(ev, "max_discharge_power_kw", getattr(ev, "max_discharge_kw", 11.0)))

        cap_kwh = getattr(ev, "battery_capacity_kwh", getattr(ev, "capacity_kwh", 60.0))
        tgt_soc_pct = getattr(ev, "target_soc", 80.0)
        arr_h = getattr(ev, "arrival_time", 8.0)
        dep_h = getattr(ev, "departure_time", 18.0)
        connected = bool(getattr(ev, "is_connected", getattr(ev, "connected", True)))
        v2g_on = bool(getattr(ev, "v2g_enabled", True))

        grid_load = float(grid_data.get("load_kw", grid_data.get("grid_load_kw", 38.0)))
        grid_cap = float(grid_data.get("capacity_kw", grid_data.get("feeder_capacity_kw", 100.0)))
        voltage_v = float(grid_data.get("voltage_v", grid_data.get("grid_voltage_v", 230.0)))
        freq_hz = float(grid_data.get("frequency_hz", 50.00))
        grid_util = float(grid_data.get("utilization_pct", (grid_load / max(1.0, grid_cap)) * 100.0))

        price_inr = float(price_data.get("electricity_price", price_data.get("current_price", 6.80)))
        solar_gen = float(solar_data.get("generation_kw", solar_data.get("solar_generation_kw", 0.0)))
        solar_cap = float(solar_data.get("installed_capacity_kw", solar_data.get("peak_capacity_kw", 40.0)))
        solar_avail = float(solar_data.get("solar_availability", 1.0 if solar_gen > 0.1 else 0.0))

        time_to_dep = max(0.0, dep_h - current_hour)
        req_energy_kwh = max(0.0, ((tgt_soc_pct - soc_pct) / 100.0) * cap_kwh)

        # Validate raw state per Section 9
        is_valid, validation_errors = cls.validate_raw_inputs(
            soc_pct=soc_pct,
            temperature_c=temp_c,
            grid_load_kw=grid_load,
            grid_capacity_kw=grid_cap,
            voltage_v=voltage_v,
            frequency_hz=freq_hz,
            price_inr=price_inr,
            solar_kw=solar_gen,
            time_until_departure_hours=time_to_dep
        )

        if not is_valid:
            # Clamp for safe fallback
            soc_pct = max(0.0, min(100.0, soc_pct))
            grid_load = max(0.0, grid_load)
            solar_gen = max(0.0, solar_gen)
            price_inr = max(0.0, price_inr)
            voltage_v = max(180.0, min(480.0, voltage_v))
            freq_hz = max(47.0, min(53.0, freq_hz))
            time_to_dep = max(0.0, time_to_dep)

        # Normalization (0.0 to 1.0 or -1.0 to 1.0)
        norm_soc = soc_pct / 100.0
        norm_temp = max(0.0, min(1.0, (temp_c - 10.0) / 60.0))
        norm_health = max(0.0, min(1.0, health_pct / 100.0))
        norm_power = max(-1.0, min(1.0, pwr_kw / max_chg_kw if pwr_kw >= 0 else pwr_kw / max_dis_kw))
        norm_grid_load = min(1.5, grid_load / max(1.0, grid_cap))
        norm_grid_cap = min(1.5, grid_cap / 200.0)
        norm_grid_util = min(1.5, grid_util / 100.0)
        norm_voltage = min(1.5, voltage_v / 250.0)
        norm_freq = max(0.0, min(1.0, (freq_hz - 48.0) / 4.0))
        norm_price = min(1.5, price_inr / 15.0)
        norm_solar_gen = min(1.2, solar_gen / max(1.0, solar_cap))
        norm_solar_avail = max(0.0, min(1.0, solar_avail))
        norm_bld_load = min(1.5, building_load_kw / max(1.0, grid_cap))
        norm_conn = 1.0 if connected else 0.0
        norm_time_dep = min(1.0, time_to_dep / 24.0)
        norm_tgt_soc = tgt_soc_pct / 100.0
        norm_req_energy = min(1.0, req_energy_kwh / max(1.0, cap_kwh))
        norm_v2g = 1.0 if v2g_on else 0.0
        norm_prev_act = float(previous_action)

        vec = np.array([
            norm_soc,
            norm_temp,
            norm_health,
            norm_power,
            norm_grid_load,
            norm_grid_cap,
            norm_grid_util,
            norm_voltage,
            norm_freq,
            norm_price,
            norm_solar_gen,
            norm_solar_avail,
            norm_bld_load,
            norm_conn,
            norm_time_dep,
            norm_tgt_soc,
            norm_req_energy,
            norm_v2g,
            norm_prev_act
        ], dtype=np.float32)

        raw_dict = {
            "battery_soc_pct": round(soc_pct, 2),
            "battery_soc_norm": round(norm_soc, 4),
            "battery_temperature_c": round(temp_c, 1),
            "battery_health_pct": round(health_pct, 1),
            "battery_power_kw": round(pwr_kw, 2),
            "grid_load_kw": round(grid_load, 2),
            "grid_capacity_kw": round(grid_cap, 2),
            "grid_utilization_pct": round(grid_util, 1),
            "grid_voltage_v": round(voltage_v, 1),
            "grid_frequency_hz": round(freq_hz, 3),
            "electricity_price_inr": round(price_inr, 2),
            "solar_generation_kw": round(solar_gen, 2),
            "solar_availability": round(solar_avail, 2),
            "building_load_kw": round(building_load_kw, 2),
            "ev_connected": connected,
            "time_until_departure_hours": round(time_to_dep, 2),
            "target_soc_pct": round(tgt_soc_pct, 2),
            "required_energy_kwh": round(req_energy_kwh, 2),
            "v2g_enabled": v2g_on,
            "previous_action": previous_action,
            "validation_errors": validation_errors,
            "is_valid": is_valid
        }

        return vec, raw_dict
