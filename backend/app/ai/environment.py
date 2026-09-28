"""
GridWise AI - Gymnasium Environment Module
Connects the PPO RL agent directly to the Authoritative Digital Twin simulation engine.
Adheres strictly to PRD Section 5, 6, and 7:
- Gymnasium standard interface: reset() and step(action)
- 19-dimensional continuous observation space
- Closed loop execution:
  1. Read current state
  2. Receive PPO action
  3. Send through Safety Validator
  4. Execute approved action via ActionModule
  5. Run Digital Twin physics
  6. Update battery SOC, grid load, circuit power flow
  7. Calculate energy movement and losses
  8. Calculate transparent multi-objective reward
  9. Generate next 19-dimensional state
  10. Return: (next_state, reward, terminated, truncated, info)
"""

import math
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, Any, Tuple, Optional

from backend.app.ai.state_space import StateSpaceModule
from backend.app.ai.actions import ActionModule
from backend.app.ai.reward import RewardFunction
from backend.app.ai.constraints import ConstraintEngine
from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.simulator.energy_provider import SimulationEnergyProvider


class EVChargingGymEnv(gym.Env):
    """
    Standard Gymnasium environment for intelligent EV charging, V2G, and grid support.
    Connects directly to authoritative physical models and safety validation layers.
    """
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        digital_twin_engine: Optional[Any] = None,
        ev: Optional[Any] = None,
        energy_provider: Optional[Any] = None,
        timestep_minutes: int = 15
    ):
        super().__init__()
        self.engine = digital_twin_engine
        self.energy_provider = energy_provider or SimulationEnergyProvider()
        
        self.ev = ev or EVDigitalTwin(
            ev_id="EV-001",
            name="Bench EV Digital Twin",
            battery_capacity_kwh=72.0,
            current_soc=45.0,
            minimum_soc=20.0,
            maximum_soc=95.0,
            target_soc=80.0,
            arrival_time=8.0,
            departure_time=19.5,
            max_charge_power_kw=22.0,
            max_discharge_power_kw=11.0
        )
        self.timestep_hours = timestep_minutes / 60.0
        self.timestep_seconds = timestep_minutes * 60.0
        self.reward_fn = RewardFunction()
        self.state_space = StateSpaceModule()

        self.current_hour = float(getattr(self.ev, "arrival_time", 8.0))
        self.previous_action = 0
        self.step_count = 0
        self.max_steps_per_episode = int(24.0 / self.timestep_hours)

        # 19-dimensional normalized continuous observation space (PRD Section 8)
        self.observation_space = spaces.Box(
            low=np.array([
                0.0,  # battery_soc
                0.0,  # battery_temperature
                0.0,  # battery_health
                -1.0, # battery_power
                0.0,  # grid_load
                0.0,  # grid_capacity
                0.0,  # grid_utilization
                0.0,  # grid_voltage
                0.0,  # grid_frequency
                0.0,  # electricity_price
                0.0,  # solar_generation
                0.0,  # solar_availability
                0.0,  # building_load
                0.0,  # ev_connected
                0.0,  # time_until_departure
                0.0,  # target_soc
                0.0,  # required_energy
                0.0,  # v2g_enabled
                0.0   # previous_action
            ], dtype=np.float32),
            high=np.array([
                1.0,  # battery_soc
                1.0,  # battery_temperature
                1.0,  # battery_health
                1.0,  # battery_power
                1.5,  # grid_load
                1.5,  # grid_capacity
                1.5,  # grid_utilization
                1.5,  # grid_voltage
                1.0,  # grid_frequency
                1.5,  # electricity_price
                1.5,  # solar_generation
                1.0,  # solar_availability
                1.5,  # building_load
                1.0,  # ev_connected
                1.0,  # time_until_departure
                1.0,  # target_soc
                1.0,  # required_energy
                1.0,  # v2g_enabled
                2.0   # previous_action
            ], dtype=np.float32),
            dtype=np.float32
        )

        # Discrete Action Space: 0 = IDLE, 1 = CHARGE, 2 = DISCHARGE / V2G
        self.action_space = spaces.Discrete(3)

    def _get_obs(self) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Constructs and validates the 19D state vector."""
        if self.engine is not None and hasattr(self.engine, "get_full_state"):
            full_st = self.engine.get_full_state()
            grid_data = full_st.get("grid", {})
            price_data = full_st.get("price", {})
            solar_data = full_st.get("solar", {})
            building_load = full_st.get("load", {}).get("building_load_kw", 38.0)
            target_ev = self.engine.fleet_manager.fleet.get(self.ev.ev_id, self.ev)
        else:
            grid_data = self.energy_provider.get_grid_state(self.current_hour)
            solar_kw = self.energy_provider.get_solar_generation(self.current_hour)
            price_info = self.energy_provider.get_electricity_price(self.current_hour)
            grid_data["load_kw"] = grid_data.get("current_load_kw", grid_data.get("base_load_kw", 38.0))
            price_data = {"electricity_price": price_info.get("current_price", 6.80)}
            solar_data = {
                "generation_kw": solar_kw,
                "installed_capacity_kw": getattr(self.energy_provider.solar, "solar_peak_capacity_kw", 40.0),
                "solar_availability": 1.0 if solar_kw > 1.0 else 0.0
            }
            building_load = 38.0
            target_ev = self.ev

        return StateSpaceModule.build_state(
            ev=target_ev,
            grid_data=grid_data,
            price_data=price_data,
            solar_data=solar_data,
            building_load_kw=building_load,
            current_hour=self.current_hour,
            previous_action=self.previous_action
        )

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> Tuple[np.ndarray, dict]:
        """Resets environment state to episode start."""
        super().reset(seed=seed)
        self.step_count = 0
        arr = float(getattr(self.ev, "arrival_time", 8.0))
        self.current_hour = arr
        self.previous_action = 0

        if hasattr(self.ev, "current_soc"):
            self.ev.current_soc = 40.0
        elif hasattr(self.ev, "soc"):
            self.ev.soc = 40.0

        if hasattr(self.ev, "update_schedule_status"):
            self.ev.update_schedule_status(self.current_hour)

        obs_vec, raw_dict = self._get_obs()
        return obs_vec, {"raw_state": raw_dict}

    def step(self, action: Any) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """
        Executes complete closed-loop RL step adhering to PRD Section 7:
        Action -> Safety Validation -> Action Execution -> Physics -> Conservation -> Reward -> Next State
        """
        self.step_count += 1

        # 1. Parse action input
        if isinstance(action, dict):
            act_idx = action.get("action", 0)
            if isinstance(act_idx, str):
                act_map = {"IDLE": 0, "CHARGE": 1, "DISCHARGE": 2, "V2G": 2}
                act_idx = act_map.get(act_idx.upper(), 0)
            req_power = float(action.get("power_kw", 0.0))
        elif isinstance(action, (list, np.ndarray)):
            act_idx = int(action[0])
            req_power = float(action[1]) if len(action) > 1 else 0.0
        else:
            act_idx = int(action)
            req_power = 0.0

        # Assign default max rating if power not specified
        max_c = float(getattr(self.ev, "max_charge_power_kw", getattr(self.ev, "max_charge_kw", 22.0)))
        max_d = float(getattr(self.ev, "max_discharge_power_kw", getattr(self.ev, "max_discharge_kw", 11.0)))
        if req_power == 0.0:
            if act_idx == 1:
                req_power = max_c
            elif act_idx == 2:
                req_power = -max_d

        # 2. Update schedule status
        if hasattr(self.ev, "update_schedule_status"):
            self.ev.update_schedule_status(self.current_hour)

        # 3. Read environment telemetry
        if self.engine is not None and hasattr(self.engine, "get_full_state"):
            full_st = self.engine.get_full_state()
            grid_data = full_st.get("grid", {})
            price_data = full_st.get("price", {})
            solar_data = full_st.get("solar", {})
            circuit = self.engine.circuit
        else:
            grid_data = self.energy_provider.get_grid_state(self.current_hour)
            solar_kw = self.energy_provider.get_solar_generation(self.current_hour)
            price_info = self.energy_provider.get_electricity_price(self.current_hour)
            grid_data["load_kw"] = grid_data.get("current_load_kw", grid_data.get("base_load_kw", 38.0))
            price_data = {"electricity_price": price_info.get("current_price", 6.80)}
            solar_data = {"generation_kw": solar_kw}
            circuit = getattr(self.engine, "circuit", None) if self.engine else None

        price = float(price_data.get("electricity_price", 6.80))
        grid_pct = float(grid_data.get("utilization_pct", 38.0))
        solar_gen = float(solar_data.get("generation_kw", 0.0))

        # 4. Mandatory Safety Validation (AI Action -> Safety Validator -> Approved)
        final_action, approved_power, overrides = ConstraintEngine.validate_action(
            self.ev, act_idx, self.current_hour, grid_pct, price
        )

        # 5. Execute approved action in physical Digital Twin & circuit
        exec_res = ActionModule.execute(
            action=final_action,
            power_kw=approved_power,
            ev=self.ev,
            dt_seconds=self.timestep_seconds,
            circuit=circuit
        )

        # 6. Advance simulation time
        self.current_hour += self.timestep_hours
        dep_h = float(getattr(self.ev, "departure_time", 19.5))
        terminated = self.current_hour >= dep_h
        truncated = self.step_count >= self.max_steps_per_episode

        # 7. Calculate multi-objective transparent reward
        cur_soc = getattr(self.ev, "current_soc", getattr(self.ev, "soc", 50.0))
        tgt_soc = getattr(self.ev, "target_soc", 80.0)
        losses_kw = abs(approved_power) * 0.05 if abs(approved_power) > 0.05 else 0.0

        reward_breakdown = self.reward_fn.calculate_reward_breakdown(
            actual_power_kw=exec_res.actual_power_kw,
            timestep_hours=self.timestep_hours,
            electricity_price=price,
            solar_generation_kw=solar_gen,
            grid_load_pct=grid_pct,
            is_done=terminated,
            current_soc=cur_soc,
            target_soc=tgt_soc,
            had_constraint_violation=len(overrides) > 0,
            losses_kw=losses_kw,
            v2g_enabled=getattr(self.ev, "v2g_enabled", True)
        )
        step_reward = reward_breakdown["total_reward"]

        self.previous_action = final_action

        # 8. Generate next 19D state
        next_obs_vec, raw_dict = self._get_obs()

        info = {
            "raw_action": act_idx,
            "final_action": final_action,
            "action_name": {0: "IDLE", 1: "CHARGE", 2: "DISCHARGE"}.get(final_action, "IDLE"),
            "power_kw": exec_res.actual_power_kw,
            "actual_power_kw": exec_res.actual_power_kw,
            "soc": cur_soc,
            "reward_breakdown": reward_breakdown,
            "overrides": overrides,
            "is_safety_overridden": len(overrides) > 0 and (act_idx != final_action),
            "state_dict": raw_dict,
            "circuit_direction": exec_res.circuit_direction,
            "wire_active": exec_res.wire_active
        }

        return next_obs_vec, step_reward, terminated, truncated, info
