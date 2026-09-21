from typing import Dict, Any

class RewardFunction:
    """
    Configurable multi-objective reinforcement learning reward calculator.
    Balances economic cost minimization, solar renewable self-consumption,
    grid peak-shaving / stabilization, V2G revenue, target SOC satisfaction,
    and battery degradation minimization.
    """
    def __init__(
        self,
        cost_weight: float = 0.15,
        solar_bonus_weight: float = 2.0,
        grid_support_weight: float = 2.5,
        target_soc_bonus_weight: float = 25.0,
        peak_penalty_weight: float = 0.35,
        degradation_penalty_weight: float = 0.25,
        constraint_violation_penalty: float = 10.0
    ):
        self.cost_weight = cost_weight
        self.solar_bonus_weight = solar_bonus_weight
        self.grid_support_weight = grid_support_weight
        self.target_soc_bonus_weight = target_soc_bonus_weight
        self.peak_penalty_weight = peak_penalty_weight
        self.degradation_penalty_weight = degradation_penalty_weight
        self.constraint_violation_penalty = constraint_violation_penalty

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
        had_constraint_violation: bool = False
    ) -> float:
        reward = 0.0

        if actual_power_kw > 0.05:
            # Charging
            cost = actual_power_kw * timestep_hours * electricity_price
            solar_used = min(actual_power_kw, solar_generation_kw)
            
            solar_bonus = solar_used * timestep_hours * self.solar_bonus_weight
            cost_penalty = cost * self.cost_weight
            peak_penalty = (grid_load_pct - 75.0) * self.peak_penalty_weight * actual_power_kw if grid_load_pct > 75.0 else 0.0
            
            reward += (solar_bonus - cost_penalty - peak_penalty)

        elif actual_power_kw < -0.05:
            # Discharging (V2G)
            v2g_kw = abs(actual_power_kw)
            v2g_revenue = v2g_kw * timestep_hours * electricity_price * 0.85
            grid_support_bonus = (grid_load_pct / 100.0) * v2g_kw * self.grid_support_weight if grid_load_pct > 75.0 else 0.0
            degradation_penalty = v2g_kw * timestep_hours * self.degradation_penalty_weight
            
            reward += (v2g_revenue + grid_support_bonus - degradation_penalty)

        else:
            # Idle
            if grid_load_pct >= 85.0 or electricity_price >= 9.5:
                reward += 1.5  # Positive incentive for smart patience during peak stress

        if had_constraint_violation:
            reward -= self.constraint_violation_penalty

        if is_done:
            if current_soc >= (target_soc - 1.0):
                reward += self.target_soc_bonus_weight
            else:
                reward -= (target_soc - current_soc) * 2.0

        return round(reward, 2)

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
        grid_pct = (grid_load_kw / (grid_capacity_kw + 1e-5)) * 100.0
        power_kw = 0.0
        if action == 1:
            power_kw = getattr(ev, "max_charge_power_kw", 7.4)
        elif action == 2:
            power_kw = -getattr(ev, "max_discharge_power_kw", 5.0)

        is_done = current_hour >= getattr(ev, "departure_time", 24.0)
        return self.calculate_step_reward(
            actual_power_kw=power_kw,
            timestep_hours=timestep_hours,
            electricity_price=electricity_price,
            solar_generation_kw=solar_generation_kw,
            grid_load_pct=grid_pct,
            is_done=is_done,
            current_soc=getattr(ev, "current_soc", 50.0),
            target_soc=getattr(ev, "target_soc", 80.0),
            had_constraint_violation=had_constraint_violation
        )

