"""
GridWise AI - Bidirectional Charger Model with Configurable Power Ramp Rate
Complies with PRD Section 21, 22, 47, and Section 66-68.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any

@dataclass
class ChargerState:
    id: str = "CHG-01"
    mode: str = "CHARGING" # IDLE, CHARGING, V2G, FAULT
    power_kw: float = 8.4 # Positive = G2V (into battery), Negative = V2G (into grid)
    target_power_kw: float = 8.4
    direction: str = "GRID → EV" # GRID → EV, EV → GRID, IDLE
    efficiency: float = 0.95
    status: str = "READY"
    rated_power_kw: float = 22.0
    max_charge_kw: float = 22.0
    max_discharge_kw: float = 11.0
    voltage_v: float = 400.0
    current_a: float = 21.0
    ramp_rate_kw_per_sec: float = 1.0 # Default 1.0 kW/s per Section 21

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def apply_target_power(self, target_kw: float):
        """Sets target power setpoint bounded by hardware ratings."""
        self.target_power_kw = round(max(-self.rated_power_kw, min(self.rated_power_kw, float(target_kw))), 2)

    def step_ramp(self, dt_seconds: float = 1.0) -> float:
        """
        Smoothly ramps power toward target_power_kw at ramp_rate_kw_per_sec.
        Complies with PRD Section 21 and 22.
        """
        max_delta = self.ramp_rate_kw_per_sec * dt_seconds
        diff = self.target_power_kw - self.power_kw
        
        if abs(diff) <= max_delta:
            self.power_kw = self.target_power_kw
        elif diff > 0:
            self.power_kw += max_delta
        else:
            self.power_kw -= max_delta

        self.power_kw = round(self.power_kw, 2)
        self._update_operating_mode()
        return self.power_kw

    def apply_power_command(self, commanded_kw: float):
        """Instantaneous power command (used for step tests / direct override)."""
        self.target_power_kw = round(max(-self.rated_power_kw, min(self.rated_power_kw, commanded_kw)), 2)
        self.power_kw = self.target_power_kw
        self._update_operating_mode()

    def _update_operating_mode(self):
        if self.power_kw > 0.05:
            self.mode = "CHARGING"
            self.direction = "GRID → EV"
            self.current_a = round((self.power_kw * 1000.0) / max(self.voltage_v, 1.0), 1)
        elif self.power_kw < -0.05:
            self.mode = "V2G"
            self.direction = "EV → GRID"
            self.current_a = round((abs(self.power_kw) * 1000.0) / max(self.voltage_v, 1.0), 1)
        else:
            self.mode = "IDLE"
            self.direction = "IDLE"
            self.power_kw = 0.0
            self.current_a = 0.0
