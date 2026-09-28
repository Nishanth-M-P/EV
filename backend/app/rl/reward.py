"""
GridWise AI - DRL Reward Function Formulation
Computes multi-objective reward balancing peak shaving, charging cost,
departure SOC guarantees, and battery cycle degradation.
"""

from typing import Dict, Any
from backend.app.config import RewardWeights


class RewardCalculator:
    """
    Reward = Grid Support Reward
           - Energy Cost Penalty
           - SOC Violation Penalty
           - Battery Cycling Penalty
           + Departure Compliance Bonus
    """

    def __init__(self, weights: RewardWeights):
        self.weights = weights

    def compute_reward(
        self,
        base_demand_mw: float,
        net_demand_mw: float,
        electricity_price: float,
        net_ev_power_kw: float,
        dt_hours: float,
        average_soc: float,
        departure_deficits: float,
        num_compliant_departures: int,
        num_departures_this_step: int,
        battery_throughput_kwh: float
    ) -> Dict[str, float]:
        # 1. Grid Support: Reward reducing peak load above 5.0 MW; penalize increasing peak
        delta_p = base_demand_mw - net_demand_mw  # Positive if V2G shaved peak
        if base_demand_mw > 4.8:
            grid_reward = delta_p * 2.5
        else:
            # During valley, reward valley filling (net_demand > base_demand)
            grid_reward = -abs(delta_p) * 0.2

        # 2. Energy Cost: Penalize buying expensive energy
        ev_energy_kwh = net_ev_power_kw * dt_hours
        cost_penalty = (ev_energy_kwh * electricity_price) / 100.0 if net_ev_power_kw > 0 else 0.0

        # 3. Departure SOC Deficit Penalty (Priority SLA)
        soc_penalty = departure_deficits * 5.0

        # 4. Battery Cycling / Throughput Degradation
        cycling_penalty = (battery_throughput_kwh / 50.0) * 0.1

        # 5. Departure Compliance Bonus
        departure_bonus = (num_compliant_departures * 3.0) if num_compliant_departures > 0 else 0.0

        total_reward = (
            self.weights.grid_support * grid_reward
            - self.weights.cost * cost_penalty
            - self.weights.soc_violation * soc_penalty
            - self.weights.battery_cycling * cycling_penalty
            + self.weights.departure_bonus * departure_bonus
        )

        return {
            "total_reward": float(total_reward),
            "grid_reward": float(grid_reward),
            "cost_penalty": float(cost_penalty),
            "soc_penalty": float(soc_penalty),
            "cycling_penalty": float(cycling_penalty),
            "departure_bonus": float(departure_bonus)
        }

