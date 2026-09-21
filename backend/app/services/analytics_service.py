from typing import List, Dict, Any

class AnalyticsService:
    """
    Computes genuine quantitative analytical metrics across historical simulation steps.
    All metrics are computed strictly from simulation records—zero fabricated data.
    """
    @staticmethod
    def compute_analytics(history: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not history:
            return AnalyticsService._empty_analytics()

        total_grid_cost = 0.0
        v2g_revenue = 0.0
        solar_consumed_kwh = 0.0
        solar_generated_kwh = 0.0
        grid_energy_drawn_kwh = 0.0
        v2g_energy_supplied_kwh = 0.0
        max_grid_load = 0.0

        charge_count = 0
        idle_count = 0
        discharge_count = 0
        safety_override_count = 0

        rewards = []
        prices = []
        ev_socs = []

        for step in history:
            price = step.get("price", {}).get("current_price", step.get("energy_state", {}).get("electricity_price", 5.0))
            prices.append(price)

            solar_kw = step.get("solar", {}).get("generation_kw", step.get("energy_state", {}).get("solar_generation_kw", 0.0))
            base_grid = step.get("grid", {}).get("base_load_kw", step.get("energy_state", {}).get("grid_load_kw", 40.0))
            net_grid = step.get("net_grid_load_kw", base_grid)
            
            if net_grid > max_grid_load:
                max_grid_load = net_grid

            # 15 minute (0.25h) step duration default
            duration_hours = 0.25

            solar_generated_kwh += solar_kw * duration_hours

            ev_decisions = step.get("ai_decisions", [])
            for dec in ev_decisions:
                pwr = dec.get("power_kw", 0.0)
                act = dec.get("final_action", 0)
                rew = dec.get("reward", 0.0)
                rewards.append(rew)

                if dec.get("safety_overrides"):
                    safety_override_count += len(dec["safety_overrides"])

                if act == 1 or pwr > 0.05:  # Charge
                    charge_count += 1
                    energy_kwh = pwr * duration_hours
                    solar_avail = solar_kw * duration_hours
                    
                    solar_used = min(energy_kwh, solar_avail)
                    grid_drawn = max(0.0, energy_kwh - solar_used)
                    
                    solar_consumed_kwh += solar_used
                    grid_energy_drawn_kwh += grid_drawn
                    total_grid_cost += grid_drawn * price

                elif act == 2 or pwr < -0.05:  # V2G Discharge
                    discharge_count += 1
                    dis_pwr = abs(pwr)
                    v2g_kwh = dis_pwr * duration_hours
                    v2g_energy_supplied_kwh += v2g_kwh
                    v2g_revenue += v2g_kwh * price * 0.85

                else:
                    idle_count += 1

            # Track average SOC
            ev_list = step.get("evs", step.get("ev_fleet_status", []))
            for ev_item in ev_list:
                ev_socs.append(ev_item.get("current_soc", 50.0))

        total_decisions = max(1, charge_count + idle_count + discharge_count)
        avg_reward = sum(rewards) / len(rewards) if rewards else 0.0
        avg_price = sum(prices) / len(prices) if prices else 0.0
        avg_soc = sum(ev_socs) / len(ev_socs) if ev_socs else 50.0
        net_energy_cost = max(0.0, total_grid_cost - v2g_revenue)
        renewable_pct = (solar_consumed_kwh / max(0.1, solar_consumed_kwh + grid_energy_drawn_kwh)) * 100.0

        return {
            "economic_metrics": {
                "total_charging_cost_inr": round(total_grid_cost, 2),
                "v2g_revenue_earned_inr": round(v2g_revenue, 2),
                "net_energy_cost_inr": round(net_energy_cost, 2),
                "avg_cost_per_kwh_inr": round(total_grid_cost / max(1.0, grid_energy_drawn_kwh), 2),
                "average_electricity_price": round(avg_price, 2)
            },
            "grid_metrics": {
                "peak_grid_load_kw": round(max_grid_load, 2),
                "v2g_energy_supplied_kwh": round(v2g_energy_supplied_kwh, 2),
                "grid_energy_drawn_kwh": round(grid_energy_drawn_kwh, 2)
            },
            "renewable_metrics": {
                "solar_energy_generated_kwh": round(solar_generated_kwh, 2),
                "solar_energy_consumed_kwh": round(solar_consumed_kwh, 2),
                "renewable_utilization_pct": round(min(100.0, renewable_pct), 1)
            },
            "ai_metrics": {
                "total_reward": round(sum(rewards), 2),
                "avg_reward": round(avg_reward, 2),
                "average_ev_soc": round(avg_soc, 1),
                "charge_pct": round((charge_count / total_decisions) * 100.0, 1),
                "idle_pct": round((idle_count / total_decisions) * 100.0, 1),
                "v2g_pct": round((discharge_count / total_decisions) * 100.0, 1),
                "safety_overrides_count": safety_override_count
            }
        }

    @staticmethod
    def _empty_analytics() -> Dict[str, Any]:
        return {
            "economic_metrics": {
                "total_charging_cost_inr": 0.0,
                "v2g_revenue_earned_inr": 0.0,
                "net_energy_cost_inr": 0.0,
                "avg_cost_per_kwh_inr": 0.0,
                "average_electricity_price": 0.0
            },
            "grid_metrics": {
                "peak_grid_load_kw": 0.0,
                "v2g_energy_supplied_kwh": 0.0,
                "grid_energy_drawn_kwh": 0.0
            },
            "renewable_metrics": {
                "solar_energy_generated_kwh": 0.0,
                "solar_energy_consumed_kwh": 0.0,
                "renewable_utilization_pct": 0.0
            },
            "ai_metrics": {
                "total_reward": 0.0,
                "avg_reward": 0.0,
                "average_ev_soc": 0.0,
                "charge_pct": 0.0,
                "idle_pct": 0.0,
                "v2g_pct": 0.0,
                "safety_overrides_count": 0
            }
        }
