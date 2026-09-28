"""
GridWise AI - Gymnasium V2G Simulation Environment
Standard Gymnasium environment for Stable-Baselines3 PPO/SAC training.
"""

from typing import Dict, Any, Tuple, Optional
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from backend.app.config import AppConfig, settings
from backend.app.simulation.grid import GridModel
from backend.app.simulation.pricing import PricingModel
from backend.app.simulation.ev import EVFleet
from backend.app.simulation.v2g import V2GManager
from backend.app.rl.reward import RewardCalculator


class V2GEnvironment(gym.Env):
    """Gymnasium Environment for Bidirectional V2G Fleet Optimization."""

    metadata = {"render_modes": ["human"], "render_fps": 4}

    def __init__(self, config: Optional[AppConfig] = None):
        super().__init__()
        self.config = config or settings
        self.seed = self.config.simulation.random_seed

        self.grid_model = GridModel(
            duration_hours=self.config.simulation.duration_hours,
            timestep_minutes=self.config.simulation.timestep_minutes,
            base_peak_mw=self.config.grid.base_peak_mw,
            substation_limit_mw=self.config.grid.substation_limit_mw,
            noise_std_mw=self.config.grid.noise_std_mw,
            random_seed=self.seed
        )

        self.pricing_model = PricingModel(
            pricing_type=self.config.pricing.type,
            off_peak_rate=self.config.pricing.off_peak_rate,
            normal_rate=self.config.pricing.normal_rate,
            peak_rate=self.config.pricing.peak_rate
        )

        self.reward_calculator = RewardCalculator(self.config.drl.reward_weights)
        self.v2g_manager = V2GManager()

        self.total_steps = self.grid_model.total_steps
        self.dt_hours = self.grid_model.dt_hours
        self.current_step = 0

        # Create fleet
        self.fleet = EVFleet.create_synthetic_fleet(
            fleet_size=self.config.simulation.fleet_size,
            random_seed=self.seed
        )

        # Observation space: 12 continuous normalized features
        self.observation_space = spaces.Box(
            low=-2.0,
            high=3.0,
            shape=(12,),
            dtype=np.float32
        )

        # Action space: continuous power command in [-1.0, 1.0]
        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(1,),
            dtype=np.float32
        )

    def _get_obs(self) -> np.ndarray:
        current_time = self.grid_model.get_time_hours(self.current_step)
        base_demand_mw = self.grid_model.get_demand(self.current_step)
        price = self.pricing_model.get_price(current_time, base_demand_mw)

        connected = self.fleet.get_connected_evs(current_time)
        avg_soc = float(np.mean([ev.current_soc for ev in self.fleet])) if self.fleet else 0.5
        avg_dwell = float(np.mean([ev.remaining_dwell_hours(current_time) for ev in connected])) if connected else 0.0

        t_norm = (current_time % 24.0) / 24.0
        sin_t = float(np.sin(2 * np.pi * t_norm))
        cos_t = float(np.cos(2 * np.pi * t_norm))

        deficits = sum(ev.departure_soc_deficit() for ev in connected) if connected else 0.0
        headroom = max(0.0, 7.0 - base_demand_mw) / 7.0

        obs = np.array([
            avg_soc,                                            # 0: Mean fleet SOC [0, 1]
            base_demand_mw / 7.0,                               # 1: Normalized grid demand
            price / 10.0,                                       # 2: Normalized price
            sin_t,                                              # 3: Time sin
            cos_t,                                              # 4: Time cos
            min(1.0, avg_dwell / 12.0),                         # 5: Normalized remaining dwell
            0.80,                                               # 6: Average departure target
            len(connected) / float(len(self.fleet)),            # 7: Occupancy ratio
            min(2.0, deficits),                                 # 8: Aggregate deficit
            headroom,                                           # 9: Substation headroom
            0.42,                                               # 10: Nominal load factor
            0.08                                                # 11: Frequency stability
        ], dtype=np.float32)

        return obs

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self.seed = seed

        self.current_step = 0
        self.fleet.reset()
        self.v2g_manager.reset()

        obs = self._get_obs()
        info = {"step": 0, "time": "00:00"}
        return obs, info

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        act_val = float(action[0] if isinstance(action, (np.ndarray, list)) else action)
        act_val = float(np.clip(act_val, -1.0, 1.0))

        current_time = self.grid_model.get_time_hours(self.current_step)
        base_demand_mw = self.grid_model.get_demand(self.current_step)
        price = self.pricing_model.get_price(current_time, base_demand_mw)

        connected = self.fleet.get_connected_evs(current_time)
        step_net_ev_power_kw = 0.0
        step_battery_throughput = 0.0

        # Dispatch power action to connected EVs
        for ev in connected:
            if act_val > 0.0:
                # Charge: Scale by action
                req_kw = act_val * ev.max_charge_kw
            elif act_val < 0.0:
                # Discharge: Scale by absolute action
                req_kw = act_val * ev.max_discharge_kw
            else:
                req_kw = 0.0

            actual_kw, energy_kwh = ev.apply_power(req_kw, self.dt_hours, price)
            step_net_ev_power_kw += actual_kw
            step_battery_throughput += energy_kwh

        # Record V2G and grid impact
        v2g_res = self.v2g_manager.record_step(
            net_ev_power_kw=step_net_ev_power_kw,
            dt_hours=self.dt_hours,
            electricity_price=price,
            base_grid_power_mw=base_demand_mw
        )

        net_grid_mw = v2g_res["net_grid_mw"]

        # Track departures at this step
        next_step = self.current_step + 1
        next_time = self.grid_model.get_time_hours(next_step)
        departing_evs = [
            ev for ev in self.fleet
            if ev.arrival_time <= current_time and ev.departure_time <= next_time and not ev.has_departed(current_time)
        ]

        compliant_departures = sum(1 for ev in departing_evs if ev.departure_soc_satisfied())
        total_deficits = sum(ev.departure_soc_deficit() for ev in connected)

        # Compute reward
        avg_soc = float(np.mean([ev.current_soc for ev in self.fleet]))
        reward_dict = self.reward_calculator.compute_reward(
            base_demand_mw=base_demand_mw,
            net_demand_mw=net_grid_mw,
            electricity_price=price,
            net_ev_power_kw=step_net_ev_power_kw,
            dt_hours=self.dt_hours,
            average_soc=avg_soc,
            departure_deficits=total_deficits,
            num_compliant_departures=compliant_departures,
            num_departures_this_step=len(departing_evs),
            battery_throughput_kwh=step_battery_throughput
        )

        self.current_step += 1
        terminated = (self.current_step >= self.total_steps)
        truncated = False

        obs = self._get_obs()
        info = {
            "step": self.current_step,
            "time_hours": current_time,
            "base_demand_mw": base_demand_mw,
            "net_grid_mw": net_grid_mw,
            "electricity_price": price,
            "net_ev_power_kw": step_net_ev_power_kw,
            "reward_breakdown": reward_dict
        }

        return obs, reward_dict["total_reward"], terminated, truncated, info

    def render(self):
        pass

