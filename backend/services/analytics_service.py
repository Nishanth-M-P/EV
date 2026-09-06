from typing import List, Dict, Any

class AnalyticsService:
    @staticmethod
    def compute_simulation_analytics(simulation_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyzes simulation history telemetry step-by-step and computes summary KPIs.
        """
        if not simulation_history:
            return AnalyticsService._empty_analytics()

        total_grid_cost = 0.0
        v2g_revenue = 0.0
        solar_consumed_kwh = 0.0
        grid_energy_drawn_kwh = 0.0
        v2g_energy_supplied_kwh = 0.0

        max_grid_load = 0.0
        
        charge_count = 0
        idle_count = 0
        discharge_count = 0
        safety_override_count = 0
        
        rewards = []

        for step in simulation_history:
            hour_data = step.get("energy_state", {})
            ev_decisions = step.get("ev_decisions", [])
            price = hour_data.get("electricity_price", 5.0)
            solar = hour_data.get("solar_generation_kw", 0.0)
            base_grid = hour_data.get("grid_load_kw", 40.0)

            step_ev_charging_power = 0.0
            step_ev_v2g_power = 0.0

            for dec in ev_decisions:
                pwr = dec.get("power_kw", 0.0)
                act = dec.get("final_action", 0)
                rew = dec.get("reward", 0.0)
                rewards.append(rew)

                if dec.get("safety_overrides"):
                    safety_override_count += len(dec["safety_overrides"])

                if act == 1:  # Charge
                    charge_count += 1
                    step_ev_charging_power += pwr
                    
                    # 0.5 hour step duration
                    energy_kwh = pwr * 0.5
                    solar_avail_step = solar * 0.5
                    
                    solar_used = min(energy_kwh, solar_avail_step)
                    grid_drawn = max(0.0, energy_kwh - solar_used)
                    
                    solar_consumed_kwh += solar_used
                    grid_energy_drawn_kwh += grid_drawn
                    
                    # Grid cost paid only for grid energy drawn (Solar is ₹0/kWh)
                    total_grid_cost += grid_drawn * price

                elif act == 2:  # Discharge V2G
                    discharge_count += 1
                    dis_pwr = abs(pwr)
                    step_ev_v2g_power += dis_pwr
                    v2g_kwh = dis_pwr * 0.5
                    v2g_energy_supplied_kwh += v2g_kwh
                    v2g_revenue += v2g_kwh * price * 0.8  # ₹ Feed-in revenue

                else:  # Idle
                    idle_count += 1

            # Combined Net Grid Load at this step
            net_grid_load = base_grid + step_ev_charging_power - step_ev_v2g_power
            if net_grid_load > max_grid_load:
                max_grid_load = net_grid_load

        total_decisions = max(1, charge_count + idle_count + discharge_count)
        avg_reward = sum(rewards) / len(rewards) if rewards else 0.0
        net_cost = max(0.0, total_grid_cost - v2g_revenue)

        return {
            "economic_metrics": {
                "total_charging_cost_inr": round(total_grid_cost, 2),
                "v2g_revenue_earned_inr": round(v2g_revenue, 2),
                "net_energy_cost_inr": round(net_cost, 2),
                "avg_cost_per_kwh_inr": round(total_grid_cost / max(1.0, grid_energy_drawn_kwh), 2)
            },
            "grid_metrics": {
                "peak_grid_load_kw": round(max_grid_load, 2),
                "v2g_energy_supplied_kwh": round(v2g_energy_supplied_kwh, 2),
                "grid_energy_drawn_kwh": round(grid_energy_drawn_kwh, 2)
            },
            "renewable_metrics": {
                "solar_energy_consumed_kwh": round(solar_consumed_kwh, 2),
                "renewable_utilization_pct": round((solar_consumed_kwh / max(1.0, solar_consumed_kwh + grid_energy_drawn_kwh)) * 100.0, 1)
            },
            "ai_metrics": {
                "total_reward": round(sum(rewards), 2),
                "avg_reward": round(avg_reward, 2),
                "charge_pct": round((charge_count / total_decisions) * 100.0, 1),
                "idle_pct": round((idle_count / total_decisions) * 100.0, 1),
                "v2g_pct": round((discharge_count / total_decisions) * 100.0, 1),
                "safety_overrides_count": safety_override_count
            }
        }

    @staticmethod
    def _empty_analytics() -> Dict[str, Any]:
        return {
            "economic_metrics": {"total_charging_cost_inr": 0.0, "v2g_revenue_earned_inr": 0.0, "net_energy_cost_inr": 0.0, "avg_cost_per_kwh_inr": 0.0},
            "grid_metrics": {"peak_grid_load_kw": 0.0, "v2g_energy_supplied_kwh": 0.0, "grid_energy_drawn_kwh": 0.0},
            "renewable_metrics": {"solar_energy_consumed_kwh": 0.0, "renewable_utilization_pct": 0.0},
            "ai_metrics": {"total_reward": 0.0, "avg_reward": 0.0, "charge_pct": 0.0, "idle_pct": 0.0, "v2g_pct": 0.0, "safety_overrides_count": 0}
        }
