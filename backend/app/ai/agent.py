from typing import Dict, Any, List, Optional
import numpy as np

from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.simulator.energy_provider import EnergyDataProvider
from backend.app.ai.constraints import ConstraintEngine
from backend.app.ai.reward import RewardFunction
from backend.app.ai.ppo_model import PPOActorCritic

class RLAgent:
    """
    Intelligent RL Decision Engine powered by genuine PPO Actor-Critic Neural Policy
    coupled with deterministic Safety Constraint Engine and Explainable AI (XAI).
    """
    def __init__(self, energy_provider: EnergyDataProvider, ppo_model: Optional[PPOActorCritic] = None):
        self.energy_provider = energy_provider
        self.reward_fn = RewardFunction()
        self.ppo = ppo_model or PPOActorCritic()
        self.action_names = {0: "IDLE", 1: "CHARGE", 2: "DISCHARGE (V2G)"}

    def build_observation(self, ev: EVDigitalTwin, current_hour: float) -> np.ndarray:
        """Constructs the standard 10-dimensional normalized continuous observation vector."""
        grid_state = self.energy_provider.get_grid_state(current_hour)
        price_info = self.energy_provider.get_electricity_price(current_hour)
        solar_kw = self.energy_provider.get_solar_generation(current_hour)

        time_remaining = max(0.0, ev.departure_time - current_hour)
        total_window = max(1.0, ev.departure_time - ev.arrival_time)
        norm_power = (ev.current_power_kw / ev.max_charge_power_kw) if ev.max_charge_power_kw > 0 else 0.0

        solar_cap = getattr(self.energy_provider.solar, "solar_peak_capacity_kw", 40.0)

        return np.array([
            ev.current_soc / 100.0,
            ev.target_soc / 100.0,
            ev.minimum_soc / 100.0,
            min(1.0, time_remaining / total_window),
            min(1.0, price_info["current_price"] / 15.0),
            min(1.0, grid_state["utilization_pct"] / 100.0),
            min(1.0, solar_kw / max(1.0, solar_cap)),
            max(-1.0, min(1.0, norm_power)),
            0.0,
            ev.battery_health / 100.0
        ], dtype=np.float32)

    def select_action(
        self,
        ev: EVDigitalTwin,
        current_hour: float,
        timestep_hours: float = 0.25
    ) -> Dict[str, Any]:
        grid_state = self.energy_provider.get_grid_state(current_hour)
        price_info = self.energy_provider.get_electricity_price(current_hour)
        solar_kw = self.energy_provider.get_solar_generation(current_hour)

        price = price_info["current_price"]
        grid_pct = grid_state["utilization_pct"]

        # 1. PPO Neural Network Forward Pass
        obs = self.build_observation(ev, current_hour)
        raw_action, probs_dict, state_val, confidence = self.ppo.predict(obs, deterministic=True)

        # 2. Deterministic Safety Constraint Engine (Boundary Enforcement)
        final_action, approved_power, overrides = ConstraintEngine.validate_action(
            ev, raw_action, current_hour, grid_pct, price
        )

        time_remaining = max(0.05, ev.departure_time - current_hour)
        soc_needed = max(0.0, ev.target_soc - ev.current_soc)
        energy_needed = (soc_needed / 100.0) * ev.battery_capacity_kwh
        hours_needed = energy_needed / (ev.max_charge_power_kw * ev.charging_efficiency + 1e-5)

        # 3. Explainable AI (XAI) Rationale Generation
        reasons = []
        if overrides:
            reasons.extend(overrides)
        else:
            if final_action == 1:
                if solar_kw > 10.0:
                    reasons.append(f"Abundant solar generation ({solar_kw} kW) -> Zero-cost charging")
                if price <= 6.0:
                    reasons.append(f"Off-peak electricity tariff (₹{price}/kWh)")
                if time_remaining <= (hours_needed * 1.5):
                    reasons.append(f"Approaching departure deadline ({round(time_remaining, 1)}h remaining)")
            elif final_action == 2:
                if grid_pct >= 75.0:
                    reasons.append(f"High feeder demand ({grid_pct}%) -> Providing V2G grid support")
                if price >= 9.0:
                    reasons.append(f"Peak electricity price (₹{price}/kWh) -> Exporting at premium")
            else:
                if grid_pct >= 80.0:
                    reasons.append(f"Grid feeder heavily loaded ({grid_pct}%) -> Postponing charging")
                elif price >= 8.5:
                    reasons.append(f"Peak tariff active (₹{price}/kWh) -> Waiting for off-peak solar/rates")
                else:
                    reasons.append("Optimal state: Battery energy balanced with departure window")

        reason_str = " + ".join(reasons) if reasons else "Multi-objective cost & grid stability optimization"

        # Calculate reward
        step_reward = self.reward_fn.calculate_reward(
            ev=ev,
            action=final_action,
            current_hour=current_hour,
            grid_load_kw=grid_state["net_grid_load_kw"],
            grid_capacity_kw=grid_state["capacity_kw"],
            electricity_price=price,
            solar_generation_kw=solar_kw,
            timestep_hours=timestep_hours
        )

        return {
            "ev_id": ev.ev_id,
            "ev_name": ev.name,
            "raw_action": raw_action,
            "proposed_action": self.action_names.get(raw_action, "IDLE"),
            "final_action": final_action,
            "action_name": self.action_names.get(final_action, "IDLE"),
            "power_kw": approved_power,
            "action_probabilities": probs_dict,
            "state_value": state_val,
            "confidence": confidence,
            "reason": reason_str,
            "reward": round(step_reward, 2),
            "soc": round(ev.current_soc, 1),
            "safety_overrides": overrides,
            "is_safety_overridden": len(overrides) > 0 and (raw_action != final_action)
        }
