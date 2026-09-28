"""
GridWise AI - Battery Physical Modeling
Implements battery energy storage, charging/discharging efficiency,
physical SOC limits, and degradation cycle tracking.
"""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class Battery:
    capacity_kwh: float
    current_soc: float = 0.50
    min_soc: float = 0.20
    max_soc: float = 1.00
    charging_efficiency: float = 0.95
    discharging_efficiency: float = 0.95

    # Telemetry and cycle degradation counters
    total_charged_kwh: float = 0.0
    total_discharged_kwh: float = 0.0

    def __post_init__(self):
        if self.capacity_kwh <= 0:
            raise ValueError(f"Battery capacity must be positive, got {self.capacity_kwh}")
        if not (0.0 <= self.min_soc < self.max_soc <= 1.0):
            raise ValueError(f"Invalid SOC bounds: min={self.min_soc}, max={self.max_soc}")
        self.current_soc = max(self.min_soc, min(self.max_soc, self.current_soc))

    @property
    def stored_energy_kwh(self) -> float:
        return self.current_soc * self.capacity_kwh

    @property
    def available_charge_headroom_kwh(self) -> float:
        return max(0.0, (self.max_soc - self.current_soc) * self.capacity_kwh)

    @property
    def available_discharge_energy_kwh(self) -> float:
        return max(0.0, (self.current_soc - self.min_soc) * self.capacity_kwh)

    @property
    def equivalent_full_cycles(self) -> float:
        """Equivalent Full Cycles (EFC) = (Charged + Discharged) / (2 * Capacity)."""
        return (self.total_charged_kwh + self.total_discharged_kwh) / (2.0 * self.capacity_kwh)

    def charge(self, power_kw: float, dt_hours: float) -> Tuple[float, float]:
        """
        Apply charging power (kW) for duration dt_hours.
        Returns (actual_power_kw, actual_energy_added_kwh).
        """
        if power_kw <= 0 or dt_hours <= 0:
            return 0.0, 0.0

        if self.current_soc >= self.max_soc:
            return 0.0, 0.0

        # Maximum energy that can be accepted based on pack headroom
        max_energy_accepted_kwh = self.available_charge_headroom_kwh
        max_power_allowable_kw = max_energy_accepted_kwh / (dt_hours * self.charging_efficiency)

        actual_power_kw = min(power_kw, max_power_allowable_kw)
        energy_added_kwh = actual_power_kw * dt_hours * self.charging_efficiency

        self.current_soc = min(self.max_soc, self.current_soc + (energy_added_kwh / self.capacity_kwh))
        self.total_charged_kwh += energy_added_kwh

        return actual_power_kw, energy_added_kwh

    def discharge(self, power_kw: float, dt_hours: float) -> Tuple[float, float]:
        """
        Apply discharging power (kW) for duration dt_hours.
        Returns (actual_power_kw, actual_energy_delivered_to_grid_kwh).
        """
        if power_kw <= 0 or dt_hours <= 0:
            return 0.0, 0.0

        if self.current_soc <= self.min_soc:
            return 0.0, 0.0

        # Energy drawn from battery pack = Power * dt / discharging_efficiency
        max_pack_energy_available = self.available_discharge_energy_kwh
        max_power_deliverable_kw = (max_pack_energy_available * self.discharging_efficiency) / dt_hours

        actual_power_kw = min(power_kw, max_power_deliverable_kw)
        energy_drawn_from_pack = (actual_power_kw * dt_hours) / self.discharging_efficiency
        energy_delivered_kwh = actual_power_kw * dt_hours

        self.current_soc = max(self.min_soc, self.current_soc - (energy_drawn_from_pack / self.capacity_kwh))
        self.total_discharged_kwh += energy_drawn_from_pack

        return actual_power_kw, energy_delivered_kwh

    def reset(self, initial_soc: float):
        self.current_soc = max(self.min_soc, min(self.max_soc, initial_soc))
        self.total_charged_kwh = 0.0
        self.total_discharged_kwh = 0.0

