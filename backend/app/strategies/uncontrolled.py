"""
GridWise AI - Strategy 1: Uncontrolled Charging (Baseline S1)
Behavior: When an EV arrives, immediately charge at maximum rate until
the required departure SOC is attained. Zero grid-awareness.
"""

from typing import List, Dict, Any
from backend.app.simulation.ev import EVFleet, EV


class UncontrolledStrategy:
    """Baseline S1: Immediate Uncoordinated Charging."""

    name = "Uncontrolled (S1)"

    def compute_power_actions(
        self,
        fleet: EVFleet,
        current_time_hours: float,
        dt_hours: float,
        grid_demand_mw: float,
        electricity_price: float
    ) -> Dict[str, float]:
        """
        Returns dict mapping ev_id -> requested_power_kw.
        """
        actions = {}
        for ev in fleet:
            if not ev.is_connected(current_time_hours):
                actions[ev.ev_id] = 0.0
                continue

            # If current SOC is less than required departure target, charge at maximum rating
            if ev.current_soc < ev.required_departure_soc:
                actions[ev.ev_id] = ev.max_charge_kw
            else:
                actions[ev.ev_id] = 0.0

        return actions

