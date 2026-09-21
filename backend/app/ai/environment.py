import math
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, Any, Tuple, Optional

from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.simulator.energy_provider import SimulationEnergyProvider
from backend.app.ai.constraints import ConstraintEngine
from backend.app.ai.reward import RewardFunction

class EVChargingGymEnv(gym.Env):
    """
    Gymnasium standard environment for Reinforcement Learning EV smart charging & V2G.
    """
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        energy_provider: Optional[SimulationEnergyProvider] = None,
        ev: Optional[EVDigitalTwin] = None,
        timestep_minutes: int = 15
    ):
        super().__init__()
        self.energy_provider = energy_provider or SimulationEnergyProvider()
        self.ev = ev or EVDigitalTwin(
            ev_id="EV-RL-TRAIN",
            name="Gym Training EV",
            battery_capacity_kwh=60.0,
            current_soc=35.0,
            minimum_soc=20.0,
            maximum_soc=100.0,
            target_soc=85.0,
            arrival_time=8.0,
            departure_time=18.0
        )
        self.timestep_hours = timestep_minutes / 60.0
        self.reward_fn = RewardFunction()

        self.current_hour = self.ev.arrival_time
        self.previous_action = 0

        # Observation Space: 10 normalized features
        # [current_soc, target_soc, min_soc, time_until_dep, price, grid_pct, solar_norm, current_power, prev_act, batt_health]
        self.observation_space = spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0], dtype=np.float32),
            high=np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 1.0], dtype=np.float32),
            dtype=np.float32
        )

        # Discrete Action Space: 0 = IDLE, 1 = CHARGE, 2 = DISCHARGE (V2G)
        self.action_space = spaces.Discrete(3)

    def _get_obs(self) -> np.ndarray:
        grid_state = self.energy_provider.get_grid_state(self.current_hour)
        solar_kw = self.energy_provider.get_solar_generation(self.current_hour)
        price_info = self.energy_provider.get_electricity_price(self.current_hour)

        time_remaining = max(0.0, self.ev.departure_time - self.current_hour)
        total_window = max(1.0, self.ev.departure_time - self.ev.arrival_time)
        norm_power = (self.ev.current_power_kw / self.ev.max_charge_power_kw) if self.ev.max_charge_power_kw > 0 else 0.0

        return np.array([
            self.ev.current_soc / 100.0,
            self.ev.target_soc / 100.0,
            self.ev.minimum_soc / 100.0,
            min(1.0, time_remaining / total_window),
            min(1.0, price_info["current_price"] / 15.0),
            min(1.0, grid_state["utilization_pct"] / 100.0),
            min(1.0, solar_kw / max(1.0, self.energy_provider.solar.solar_peak_capacity_kw)),
            max(-1.0, min(1.0, norm_power)),
            float(self.previous_action),
            self.ev.battery_health / 100.0
        ], dtype=np.float32)

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> Tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        self.current_hour = self.ev.arrival_time
        self.ev.current_soc = 35.0
        self.ev.update_schedule_status(self.current_hour)
        self.previous_action = 0
        return self._get_obs(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        self.ev.update_schedule_status(self.current_hour)
        grid_state = self.energy_provider.get_grid_state(self.current_hour)
        price_info = self.energy_provider.get_electricity_price(self.current_hour)
        solar_kw = self.energy_provider.get_solar_generation(self.current_hour)

        # Pass proposed action through mandatory Safety Constraint Engine
        final_action, approved_power, overrides = ConstraintEngine.validate_action(
            self.ev, action, self.current_hour, grid_state["utilization_pct"], price_info["current_price"]
        )

        res = self.ev.apply_power(approved_power, self.timestep_hours)
        actual_power = res["actual_power_kw"]

        self.current_hour += self.timestep_hours
        done = self.current_hour >= self.ev.departure_time

        reward = self.reward_fn.calculate_step_reward(
            actual_power_kw=actual_power,
            timestep_hours=self.timestep_hours,
            electricity_price=price_info["current_price"],
            solar_generation_kw=solar_kw,
            grid_load_pct=grid_state["utilization_pct"],
            is_done=done,
            current_soc=self.ev.current_soc,
            target_soc=self.ev.target_soc,
            had_constraint_violation=len(overrides) > 0
        )

        self.previous_action = final_action
        info = {
            "final_action": final_action,
            "actual_power_kw": actual_power,
            "soc": self.ev.current_soc,
            "overrides": overrides
        }

        return self._get_obs(), reward, done, False, info
