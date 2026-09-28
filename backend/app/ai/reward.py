"""
GridWise AI - Reward Function Module
Calculates transparent weighted multi-objective reinforcement learning reward.
Adheres strictly to PRD Section 19, 20, and 21:
- Positive reward factors:
  1. Renewable charging
  2. Cost-saving / off-peak arbitrage
  3. Peak demand reduction
  4. Grid stability support
  5. Departure target SOC guarantee
  6. Efficient energy management
  7. Appropriate V2G operation
- Negative penalties:
  1. High-price charging
  2. Peak grid penalty
  3. Battery degradation on cycling
  4. Unnecessary battery discharge
  5. Missing departure target
  6. Energy losses
  7. Safety constraint violations
- Configurable weights and transparent component breakdown.
"""

from typing import Dict, Any, Optional


class RewardFunction:
    """
    Transparent weighted multi-objective reinforcement learning reward calculator.
    """
    def __init__(
        self,
        cost_weight: float = 0.15,
        solar_bonus_weight: float = 2.0,
        grid_support_weight: float = 2.5,
        target_soc_bonus_weight: float = 25.0,
        peak_penalty_weight: float = 0.35,
        degradation_penalty_weight: float = 0.25,
        constraint_violation_penalty: float = 10.0,
        energy_loss_penalty_weight: float = 0.50
    ):
        self.cost_weight = cost_weight
        self.solar_bonus_weight = solar_bonus_weight
        self.grid_support_weight = grid_support_weight
        self.target_soc_bonus_weight = target_soc_bonus_weight
        self.peak_penalty_weight = peak_penalty_weight
        self.degradation_penalty_weight = degradation_penalty_weight
        self.constraint_violation_penalty = constraint_violation_penalty
        self.energy_loss_penalty_weight = energy_loss_penalty_weight

    def calculate_reward_breakdown(
        self,
        actual_power_kw: float,
        timestep_hours: float,
        electricity_price: float,
        solar_generation_kw: float,
        grid_load_pct: float,
        is_done: bool,
        current_soc: float,
        target_soc: float,
        had_constraint_violation: bool = False,
        losses_kw: float = 0.0,
        v2g_enabled: bool = True
    ) -> Dict[str, Any]:
        """
        Calculates exact reward and individual component values per PRD Section 20.
        """
        renewable_reward = 0.0
        cost_saving_reward = 0.0
        peak_reduction_reward = 0.0
        grid_support_reward = 0.0
        departure_reward = 0.0

        electricity_cost = 0.0
        battery_degradation_cost = 0.0
        unnecessary_discharge_penalty = 0.0
        peak_load_penalty = 0.0
        energy_loss_penalty = losses_kw * timestep_hours * self.energy_loss_penalty_weight
        safety_violation_penalty = self.constraint_violation_penalty if had_constraint_violation else 0.0

        if actual_power_kw > 0.05:
            # CHARGING MODE
            charge_energy_kwh = actual_power_kw * timestep_hours
            solar_used = min(actual_power_kw, max(0.0, solar_generation_kw))
            renewable_reward = solar_used * timestep_hours * self.solar_bonus_weight

            # Cost calculation
            grid_energy_drawn = max(0.0, actual_power_kw - solar_used) * timestep_hours
            electricity_cost = grid_energy_drawn * electricity_price * self.cost_weight

            # Off-peak bonus
            if electricity_price <= 6.50:
                cost_saving_reward = (7.0 - electricity_price) * 0.5 * charge_energy_kwh

            # Peak loading penalty
            if grid_load_pct > 75.0:
                peak_load_penalty = (grid_load_pct - 75.0) * self.peak_penalty_weight * actual_power_kw * timestep_hours

            # Battery cycling wear
            battery_degradation_cost = actual_power_kw * timestep_hours * (self.degradation_penalty_weight * 0.3)

        elif actual_power_kw < -0.05:
            # DISCHARGING (V2G) MODE
            v2g_kw = abs(actual_power_kw)
            v2g_energy = v2g_kw * timestep_hours

            # Arbitrage revenue
            v2g_revenue = v2g_energy * electricity_price * 0.85
            cost_saving_reward = v2g_revenue

            # Grid support bonus if grid is under high stress
            if grid_load_pct >= 75.0:
                grid_support_reward = (grid_load_pct / 100.0) * v2g_kw * self.grid_support_weight
                peak_reduction_reward = ((grid_load_pct - 70.0) / 10.0) * 1.5

            # Battery degradation penalty (V2G cycling cost per Section 21)
            battery_degradation_cost = v2g_energy * self.degradation_penalty_weight

            # Penalty for discharging when grid doesn't need it or price is low
            if grid_load_pct < 65.0 and electricity_price < 7.0:
                unnecessary_discharge_penalty = v2g_energy * 1.8

        else:
            # IDLE MODE
            # Smart patience reward during critical grid stress or high price
            if grid_load_pct >= 80.0 or electricity_price >= 8.5:
                grid_support_reward = 1.50
                peak_reduction_reward = 0.50

        # Departure SLA Guarantee evaluation
        if is_done:
            if current_soc >= (target_soc - 1.0):
                departure_reward = self.target_soc_bonus_weight
            else:
                departure_reward = -((target_soc - current_soc) * 2.0)

        # Weighted composite formula (Section 20)
        total_reward = (
            renewable_reward
            + cost_saving_reward
            + peak_reduction_reward
            + grid_support_reward
            + departure_reward
            - electricity_cost
            - battery_degradation_cost
            - unnecessary_discharge_penalty
            - peak_load_penalty
            - energy_loss_penalty
            - safety_violation_penalty
        )

        components_dict = {
            "renewable_reward": round(renewable_reward, 3),
            "cost_saving_reward": round(cost_saving_reward, 3),
            "peak_reduction_reward": round(peak_reduction_reward, 3),
            "grid_support_reward": round(grid_support_reward, 3),
            "departure_reward": round(departure_reward, 3),
            "electricity_cost": round(electricity_cost, 3),
            "battery_degradation_cost": round(battery_degradation_cost, 3),
            "unnecessary_discharge_penalty": round(unnecessary_discharge_penalty, 3),
            "peak_load_penalty": round(peak_load_penalty, 3),
            "energy_loss_penalty": round(energy_loss_penalty, 3),
            "safety_violation_penalty": round(safety_violation_penalty, 3)
        }

        return {
            "total_reward": round(total_reward, 2),
            "components": components_dict,
            **components_dict
        }

    def calculate_step_reward(
        self,
        actual_power_kw: float,
        timestep_hours: float,
        electricity_price: float,
        solar_generation_kw: float,
        grid_load_pct: float,
        is_done: bool,
        current_soc: float,
        target_soc: float,
        had_constraint_violation: bool = False,
        losses_kw: float = 0.0
    ) -> float:
        """Backward-compatible scalar reward calculation."""
        res = self.calculate_reward_breakdown(
            actual_power_kw=actual_power_kw,
            timestep_hours=timestep_hours,
            electricity_price=electricity_price,
            solar_generation_kw=solar_generation_kw,
            grid_load_pct=grid_load_pct,
            is_done=is_done,
            current_soc=current_soc,
            target_soc=target_soc,
            had_constraint_violation=had_constraint_violation,
            losses_kw=losses_kw
        )
        return res["total_reward"]

    def calculate_reward(
        self,
        ev: Any,
        action: int,
        current_hour: float,
        grid_load_kw: float,
        grid_capacity_kw: float,
        electricity_price: float,
        solar_generation_kw: float,
        timestep_hours: float = 0.25,
        had_constraint_violation: bool = False
    ) -> float:
        """Backward-compatible agent reward calculation."""
        grid_pct = (grid_load_kw / (grid_capacity_kw + 1e-5)) * 100.0
        power_kw = 0.0
        if action in [1, "CHARGE"]:
            power_kw = getattr(ev, "max_charge_power_kw", getattr(ev, "max_charge_kw", 7.4))
        elif action in [2, "DISCHARGE"]:
            power_kw = -getattr(ev, "max_discharge_power_kw", getattr(ev, "max_discharge_kw", 5.0))

        is_done = current_hour >= getattr(ev, "departure_time", 24.0)
        return self.calculate_step_reward(
            actual_power_kw=power_kw,
            timestep_hours=timestep_hours,
            electricity_price=electricity_price,
            solar_generation_kw=solar_generation_kw,
            grid_load_pct=grid_pct,
            is_done=is_done,
            current_soc=getattr(ev, "current_soc", getattr(ev, "soc", 50.0)),
            target_soc=getattr(ev, "target_soc", 80.0),
            had_constraint_violation=had_constraint_violation
        )
