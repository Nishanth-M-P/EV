"""
GridWise AI - Vehicle-to-Grid (V2G) Energy Accounting Model
Tracks two-way energy flows between EV fleet and electrical substation.
"""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class V2GManager:
    charging_energy_kwh: float = 0.0
    discharging_energy_kwh: float = 0.0
    grid_energy_supplied_kwh: float = 0.0
    total_cost_incurred: float = 0.0
    total_revenue_generated: float = 0.0

    def record_step(
        self,
        net_ev_power_kw: float,
        dt_hours: float,
        electricity_price: float,
        base_grid_power_mw: float
    ) -> Dict[str, float]:
        """
        net_ev_power_kw: Positive = fleet charging (demand), Negative = fleet discharging (V2G injection).
        """
        # Net EV energy in kWh
        ev_energy_kwh = abs(net_ev_power_kw) * dt_hours

        step_charging_kwh = 0.0
        step_discharging_kwh = 0.0
        step_cost = 0.0
        step_revenue = 0.0

        if net_ev_power_kw > 0:
            step_charging_kwh = ev_energy_kwh
            self.charging_energy_kwh += step_charging_kwh
            step_cost = step_charging_kwh * electricity_price
            self.total_cost_incurred += step_cost
        elif net_ev_power_kw < 0:
            step_discharging_kwh = ev_energy_kwh
            self.discharging_energy_kwh += step_discharging_kwh
            step_revenue = step_discharging_kwh * electricity_price
            self.total_revenue_generated += step_revenue

        # Net Grid power seen at substation in MW
        net_grid_mw = base_grid_power_mw + (net_ev_power_kw / 1000.0)
        grid_energy_step_kwh = max(0.0, net_grid_mw * 1000.0 * dt_hours)
        self.grid_energy_supplied_kwh += grid_energy_step_kwh

        return {
            "step_charging_kwh": step_charging_kwh,
            "step_discharging_kwh": step_discharging_kwh,
            "net_grid_mw": net_grid_mw,
            "step_cost": step_cost,
            "step_revenue": step_revenue,
            "net_step_cost": step_cost - step_revenue
        }

    @property
    def net_cost(self) -> float:
        return self.total_cost_incurred - self.total_revenue_generated

    def reset(self):
        self.charging_energy_kwh = 0.0
        self.discharging_energy_kwh = 0.0
        self.grid_energy_supplied_kwh = 0.0
        self.total_cost_incurred = 0.0
        self.total_revenue_generated = 0.0

