import math
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, List, Tuple

from backend.services.ev_service import EVModel
from backend.services.energy_service import EnergyService
from backend.safety_layer import SafetyConstraintLayer


class EVChargingGymEnv(gym.Env):
    """
    Gymnasium RL Environment for EV Smart Charging and V2G Energy Management.
    """
    metadata = {"render_modes": ["human"]}

    def __init__(self, energy_service: EnergyService = None, ev: EVModel = None):
        super().__init__()
        self.energy_service = energy_service or EnergyService()
        self.ev = ev or EVModel("EV-TRAIN", "Training EV", 60.0, 30.0, 20.0, 100.0, 85.0, 8.0, 18.0)
        
        self.current_hour = 8.0
        self.step_size = 1.0  # 1 hour per step

        # Observation Space: 8 normalized features
        self.observation_space = spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, -1.0], dtype=np.float32),
            high=np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32),
            dtype=np.float32
        )

        self.action_space = spaces.Discrete(3)

    def _get_obs(self) -> np.ndarray:
        energy_state = self.energy_service.get_state_at_hour(self.current_hour)
        time_rem = max(0.0, self.ev.departure_time - self.current_hour)
        total_window = max(1.0, self.ev.departure_time - self.ev.arrival_time)
        hour_rad = (self.current_hour % 24) / 24.0 * 2 * math.pi
        
        return np.array([
            self.ev.current_soc / 100.0,
            self.ev.required_soc / 100.0,
            min(1.0, time_rem / total_window),
            min(1.0, energy_state["electricity_price"] / 15.0),
            min(1.0, energy_state["grid_load_pct"] / 100.0),
            min(1.0, energy_state["solar_generation_kw"] / self.energy_service.max_solar_capacity_kw),
            math.sin(hour_rad),
            math.cos(hour_rad)
        ], dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_hour = self.ev.arrival_time
        self.ev.current_soc = 35.0
        self.ev.total_charged_kwh = 0.0
        self.ev.total_discharged_kwh = 0.0
        self.ev.cycle_count = 0.0
        return self._get_obs(), {}

    def step(self, action: int):
        energy_state = self.energy_service.get_state_at_hour(self.current_hour)
        
        final_action, power_kw, constraints = SafetyConstraintLayer.validate_and_override_action(
            self.ev, action, self.current_hour, energy_state["grid_load_pct"], energy_state["electricity_price"]
        )

        res = self.ev.apply_power_decision(power_kw, self.step_size)
        actual_power = res["actual_power_kw"]

        reward = 0.0
        price = energy_state["electricity_price"]
        solar_gen = energy_state["solar_generation_kw"]
        grid_pct = energy_state["grid_load_pct"]

        if actual_power > 0:  # Charging
            cost = actual_power * self.step_size * price
            solar_used = min(actual_power, solar_gen)
            solar_bonus = solar_used * 2.0
            peak_penalty = (grid_pct - 75.0) * 0.3 * actual_power if grid_pct > 75 else 0.0
            cost_penalty = cost * 0.15
            reward += (solar_bonus - cost_penalty - peak_penalty)

        elif actual_power < 0:  # V2G
            dis_kw = abs(actual_power)
            v2g_revenue = dis_kw * self.step_size * price * 0.8
            grid_support_bonus = (grid_pct / 100.0) * dis_kw * 2.5 if grid_pct > 75 else 0.0
            reward += (v2g_revenue + grid_support_bonus - dis_kw * 0.2)

        else:  # Idle
            if grid_pct >= 85.0 or price >= 9.0:
                reward += 1.5

        self.current_hour += self.step_size
        done = self.current_hour >= self.ev.departure_time

        if done:
            if self.ev.current_soc >= (self.ev.required_soc - 1.0):
                reward += 25.0
            else:
                reward -= (self.ev.required_soc - self.ev.current_soc) * 2.0

        return self._get_obs(), reward, done, False, {"action": final_action, "power_kw": actual_power, "constraints": constraints}


class RLDecisionEngine:
    """
    Sub-millisecond RL Inference Engine with Explainable AI Reasons.
    """
    def __init__(self, energy_service: EnergyService):
        self.energy_service = energy_service

    def select_action(
        self,
        ev: EVModel,
        current_hour: float
    ) -> Dict:
        energy_state = self.energy_service.get_state_at_hour(current_hour)
        price = energy_state["electricity_price"]
        grid_pct = energy_state["grid_load_pct"]
        solar_gen = energy_state["solar_generation_kw"]

        time_rem = max(0.1, ev.departure_time - current_hour)
        soc_needed = max(0.0, ev.required_soc - ev.current_soc)
        hours_needed = (soc_needed / 100.0 * ev.battery_capacity_kwh) / (ev.max_charge_power_kw * ev.charging_efficiency + 1e-5)

        score_idle = 1.0
        score_charge = 0.0
        score_discharge = -5.0

        # Charge scoring
        if solar_gen > 10.0:
            score_charge += (solar_gen / 10.0) * 4.0
        if price <= 6.5:
            score_charge += (7.0 - price) * 3.0
        if time_rem <= (hours_needed * 1.4) and ev.current_soc < ev.required_soc:
            score_charge += 25.0  # Departure urgency
        if grid_pct >= 88.0 and time_rem > (hours_needed * 1.5):
            score_charge -= 10.0  # Avoid charging during peak load

        # V2G Discharge scoring
        if grid_pct >= 80.0 and price >= 9.0 and ev.current_soc >= (ev.required_soc + 5.0) and time_rem > (hours_needed * 2.0):
            score_discharge += (grid_pct - 75.0) * 0.5 + (price - 8.0) * 2.0

        scores = [score_idle, score_charge, score_discharge]
        raw_action = int(np.argmax(scores))

        final_action, power_kw, safety_logs = SafetyConstraintLayer.validate_and_override_action(
            ev, raw_action, current_hour, grid_pct, price
        )

        action_names = {0: "IDLE", 1: "CHARGE", 2: "DISCHARGE (V2G)"}
        reasons = []

        if safety_logs:
            reasons.extend(safety_logs)
        else:
            if final_action == 1:
                if solar_gen > 10.0:
                    reasons.append(f"High solar generation ({solar_gen} kW)")
                if price <= 6.5:
                    reasons.append(f"Low electricity tariff (₹{price}/kWh)")
                if time_rem <= (hours_needed * 1.4):
                    reasons.append(f"Target SOC requirement deadline ({ev.required_soc}%)")
            elif final_action == 2:
                if grid_pct >= 80.0:
                    reasons.append(f"Peak grid stress ({grid_pct}%) - Supplying V2G power support")
                if price >= 9.0:
                    reasons.append(f"High electricity price (₹{price}/kWh)")
            else:
                if grid_pct >= 85.0:
                    reasons.append(f"Grid load high ({grid_pct}%) - Postponing charging")
                elif price >= 8.0:
                    reasons.append(f"Tariff expensive (₹{price}/kWh) - Waiting for off-peak")
                else:
                    reasons.append("Optimal state: Battery SOC balanced")

        reason_str = " + ".join(reasons) if reasons else "Optimizing cost, solar, and grid demand"
        step_reward = max(scores[final_action], 0.5)

        return {
            "ev_id": ev.ev_id,
            "raw_action": raw_action,
            "final_action": final_action,
            "action_name": action_names[final_action],
            "power_kw": power_kw,
            "reason": reason_str,
            "reward": round(step_reward, 2),
            "safety_overrides": safety_logs,
            "action_scores": {
                "IDLE": round(score_idle, 2),
                "CHARGE": round(score_charge, 2),
                "DISCHARGE": round(score_discharge, 2)
            }
        }
