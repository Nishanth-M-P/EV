"""
GridWise AI - EV Model, Battery State, and Departure Urgency Module
Complies with PRD Sections 46, 48, and 68.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, Optional

@dataclass
class EVState:
    ev_id: str = "EV-01"
    name: str = "Electric Vehicle (Integrated Battery)"
    model: str = "Tata Nexon EV Max"
    soc: float = 64.2
    capacity_kwh: float = 72.0
    min_soc: float = 20.0
    max_soc: float = 95.0
    arrival_time: str = "08:00"
    departure_time: str = "19:30"
    required_soc: float = 80.0
    connected: bool = True
    v2g_enabled: bool = True
    v2g_reserve: float = 30.0
    charge_limit_kw: float = 22.0
    discharge_limit_kw: float = 11.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BatteryState:
    soc: float = 64.2
    energy_kwh: float = 46.22
    voltage: float = 400.0
    current: float = 21.0
    power_kw: float = 8.4
    state: str = "CHARGING" # CHARGING, V2G, TARGET_REACHED, FULL, IDLE
    capacity_kwh: float = 72.0
    charge_limit_kw: float = 22.0
    discharge_limit_kw: float = 11.0
    time_to_target_seconds: Optional[int] = 5255
    time_to_target_str: str = "01:27:35"
    time_to_full_seconds: Optional[int] = 9450
    time_to_full_str: str = "02:37:30"
    estimated_completion_time: str = "21:20:35"
    departure_feasible: bool = True
    departure_status: str = "✓ DEPARTURE TARGET FEASIBLE"
    effective_power_kw: float = 7.98
    battery_health_percent: float = 99.4
    charging_energy_total_kwh: float = 142.5
    discharging_energy_total_kwh: float = 18.2
    cycle_estimate: float = 2.2

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class DepartureUrgencyCalculator:
    """
    Computes time-to-departure and required charging power to guarantee EV target SOC (PRD Section 46, 68).
    """

    @staticmethod
    def calculate(
        current_time_str: str,
        departure_time_str: str,
        current_soc: float,
        target_soc: float,
        capacity_kwh: float,
        charger_efficiency: float = 0.95
    ) -> Dict[str, Any]:
        # Convert "HH:MM" to decimal hours
        def to_hours(t_str: str) -> float:
            try:
                parts = t_str.split(":")
                return float(parts[0]) + float(parts[1]) / 60.0
            except Exception:
                return 19.5

        t_now = to_hours(current_time_str)
        t_dep = to_hours(departure_time_str)

        time_remaining_hours = t_dep - t_now
        if time_remaining_hours <= 0:
            time_remaining_hours = 0.05  # Imminent

        needed_soc_delta = max(0.0, target_soc - current_soc)
        needed_energy_kwh = (needed_soc_delta / 100.0) * capacity_kwh
        required_power_kw = (needed_energy_kwh / max(0.1, time_remaining_hours)) / charger_efficiency

        # Urgency: 0.0 (plenty of time) to 1.0 (requires max charger power to hit target)
        urgency = min(1.0, max(0.0, required_power_kw / 22.0))
        is_departure_critical = urgency >= 0.70 or (current_soc < target_soc and time_remaining_hours < 1.0)
        departure_target_safe = required_power_kw <= 22.0 and not is_departure_critical

        return {
            "time_remaining_hours": round(time_remaining_hours, 2),
            "needed_energy_kwh": round(needed_energy_kwh, 2),
            "required_average_power_kw": round(required_power_kw, 2),
            "minimum_required_charge_power": round(required_power_kw, 2),
            "departure_urgency": round(urgency, 3),
            "departure_critical": is_departure_critical,
            "departure_target_safe": departure_target_safe
        }
