"""
GridWise AI - Strategy 2: Rule-Based Smart Charging (Heuristic S2)
Deterministic heuristics prioritizing off-peak charging, peak-load avoidance,
and conditional V2G peak shaving when surplus SOC is available.
"""

from typing import Dict, Any
from backend.app.simulation.ev import EVFleet, EV


class RuleBasedStrategy:
    """Heuristic S2: Deterministic TOU and threshold rule engine."""

    name = "Rule-Based (S2)"

    def __init__(
        self,
        peak_demand_threshold_mw: float = 4.80,
        peak_price_threshold: float = 7.50,
        v2g_safety_margin_soc: float = 0.05
    ):
        self.peak_demand_threshold_mw = peak_demand_threshold_mw
        self.peak_price_threshold = peak_price_threshold
        self.v2g_safety_margin_soc = v2g_safety_margin_soc

    def compute_power_actions(
        self,
        fleet: EVFleet,
        current_time_hours: float,
        dt_hours: float,
        grid_demand_mw: float,
        electricity_price: float
    ) -> Dict[str, float]:
        actions = {}
        is_grid_stressed = (grid_demand_mw >= self.peak_demand_threshold_mw) or (electricity_price >= self.peak_price_threshold)

        for ev in fleet:
            if not ev.is_connected(current_time_hours):
                actions[ev.ev_id] = 0.0
                continue

            dwell_rem = ev.remaining_dwell_hours(current_time_hours)
            deficit = ev.departure_soc_deficit()

            # Time needed to charge to target at full speed
            needed_energy_kwh = deficit * ev.battery_capacity_kwh
            min_charge_time_hours = needed_energy_kwh / (ev.max_charge_kw * ev.charging_efficiency) if ev.max_charge_kw > 0 else 0.0

            # Rule 1: Emergency charging SLA guarantee
            # If remaining dwell is close to minimum needed charge time, MUST charge!
            if deficit > 0.01 and dwell_rem <= (min_charge_time_hours + 0.25):
                actions[ev.ev_id] = ev.max_charge_kw
                continue

            # Rule 2: Grid is NOT stressed (cheap price / low demand)
            if not is_grid_stressed:
                if ev.current_soc < ev.required_departure_soc:
                    actions[ev.ev_id] = ev.max_charge_kw
                else:
                    actions[ev.ev_id] = 0.0
                continue

            # Rule 3: Grid IS stressed (peak window)
            # Check if EV has safe surplus SOC to discharge into grid (V2G)
            safe_v2g_threshold = ev.required_departure_soc + self.v2g_safety_margin_soc
            if ev.current_soc > safe_v2g_threshold:
                # Discharge to support grid
                actions[ev.ev_id] = -ev.max_discharge_kw
            else:
                # Idle to avoid stressing the grid during peak
                actions[ev.ev_id] = 0.0

        return actions

