"""
GridWise AI - Strategy 3: Deep Reinforcement Learning (DRL S3)
Applies a trained policy model (e.g. PPO) to dynamically modulate EV power.
"""

from typing import Dict, Any, Optional
import numpy as np
from backend.app.simulation.ev import EVFleet, EV


class DRLStrategy:
    """Strategy S3: DRL Trained Agent Policy Wrapper."""

    name = "DRL-V2G (S3)"

    def __init__(self, model: Optional[Any] = None):
        self.model = model

    def compute_power_actions(
        self,
        fleet: EVFleet,
        current_time_hours: float,
        dt_hours: float,
        grid_demand_mw: float,
        electricity_price: float
    ) -> Dict[str, float]:
        actions = {}
        connected = fleet.get_connected_evs(current_time_hours)

        for ev in fleet:
            if not ev.is_connected(current_time_hours):
                actions[ev.ev_id] = 0.0
                continue

            # Build single-EV normalized observation vector
            t_norm = (current_time_hours % 24.0) / 24.0
            sin_t = float(np.sin(2 * np.pi * t_norm))
            cos_t = float(np.cos(2 * np.pi * t_norm))

            obs = np.array([
                ev.current_soc,
                grid_demand_mw / 7.0,
                electricity_price / 10.0,
                sin_t,
                cos_t,
                ev.remaining_dwell_hours(current_time_hours) / 24.0,
                ev.required_departure_soc,
                ev.max_charge_kw / 22.0,
                ev.max_discharge_kw / 15.0,
                (grid_demand_mw - 5.0) / 2.0,
                len(connected) / 50.0,
                ev.departure_soc_deficit()
            ], dtype=np.float32)

            if self.model is not None:
                action, _ = self.model.predict(obs, deterministic=True)
                # Map continuous action in [-1.0, 1.0] to kW
                act_val = float(action[0] if isinstance(action, (np.ndarray, list)) else action)
            else:
                # Default heuristic dispatch when model weights not yet loaded
                if grid_demand_mw >= 5.0 and ev.current_soc > ev.required_departure_soc:
                    act_val = -0.8
                elif grid_demand_mw <= 3.5 and ev.current_soc < ev.required_departure_soc:
                    act_val = 1.0
                elif ev.remaining_dwell_hours(current_time_hours) <= 1.0 and ev.current_soc < ev.required_departure_soc:
                    act_val = 1.0
                else:
                    act_val = 0.0

            if act_val > 0:
                actions[ev.ev_id] = act_val * ev.max_charge_kw
            elif act_val < 0:
                actions[ev.ev_id] = act_val * ev.max_discharge_kw
            else:
                actions[ev.ev_id] = 0.0

        return actions

