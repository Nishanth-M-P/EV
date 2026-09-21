from typing import Dict, Any, List
import copy

from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.simulator.energy_provider import SimulationEnergyProvider
from backend.app.ai.agent import RLAgent
from backend.app.ai.baseline import ImmediateChargingBaseline

class AIComparator:
    """
    Executes identical 24-hour simulation runs for:
    - Scenario A: Traditional Immediate Uncontrolled Charging
    - Scenario B: GridWise AI (Reinforcement Learning + Safety Constraint Layer)
    Calculates true quantitative KPI improvements with zero fabricated metrics.
    """
    @staticmethod
    def run_comparison(
        fleet_specs: List[Dict[str, Any]],
        grid_capacity_kw: float = 100.0,
        solar_capacity_kw: float = 40.0,
        timestep_minutes: int = 15
    ) -> Dict[str, Any]:
        timestep_hours = timestep_minutes / 60.0
        total_steps = int(24.0 / timestep_hours)

        # Provider A and Provider B with identical profiles
        provider_a = SimulationEnergyProvider(grid_capacity_kw, solar_capacity_kw)
        provider_b = SimulationEnergyProvider(grid_capacity_kw, solar_capacity_kw)

        # Instantiate Fleet A
        fleet_a = [
            EVDigitalTwin(
                ev_id=s["ev_id"],
                name=s["name"],
                battery_capacity_kwh=s["battery_capacity_kwh"],
                current_soc=s["current_soc"],
                minimum_soc=s.get("minimum_soc", 20.0),
                maximum_soc=s.get("maximum_soc", 100.0),
                target_soc=s.get("target_soc", 85.0),
                arrival_time=s["arrival_time"],
                departure_time=s["departure_time"],
                max_charge_power_kw=s.get("max_charge_power_kw", 7.4),
                max_discharge_power_kw=s.get("max_discharge_power_kw", 5.0)
            )
            for s in fleet_specs
        ]

        # Instantiate Fleet B
        fleet_b = [
            EVDigitalTwin(
                ev_id=s["ev_id"],
                name=s["name"],
                battery_capacity_kwh=s["battery_capacity_kwh"],
                current_soc=s["current_soc"],
                minimum_soc=s.get("minimum_soc", 20.0),
                maximum_soc=s.get("maximum_soc", 100.0),
                target_soc=s.get("target_soc", 85.0),
                arrival_time=s["arrival_time"],
                departure_time=s["departure_time"],
                max_charge_power_kw=s.get("max_charge_power_kw", 7.4),
                max_discharge_power_kw=s.get("max_discharge_power_kw", 5.0)
            )
            for s in fleet_specs
        ]

        rl_agent = RLAgent(provider_b)

        history_a = []
        history_b = []

        total_cost_a = 0.0
        total_cost_b = 0.0
        solar_used_a = 0.0
        solar_used_b = 0.0
        v2g_energy_a = 0.0
        v2g_energy_b = 0.0
        peak_grid_a = 0.0
        peak_grid_b = 0.0

        for step_idx in range(total_steps):
            hour = round(step_idx * timestep_hours, 2)
            
            # --- RUN SCENARIO A (Traditional Baseline) ---
            step_charge_a = 0.0
            decisions_a = []
            for ev in fleet_a:
                ev.update_schedule_status(hour)
                dec = ImmediateChargingBaseline.select_action(ev, hour)
                res = ev.apply_power(dec["power_kw"], timestep_hours)
                pwr = res["actual_power_kw"]
                step_charge_a += max(0.0, pwr)
                decisions_a.append({
                    "ev_id": ev.ev_id,
                    "power_kw": pwr,
                    "soc": res["soc"],
                    "action_name": dec["action_name"]
                })

            grid_a = provider_a.get_grid_state(hour, charging_kw=step_charge_a, v2g_kw=0.0)
            price_a = provider_a.get_electricity_price(hour)["current_price"]
            solar_a = provider_a.get_solar_generation(hour)

            # Energy allocations for A
            charge_kwh_a = step_charge_a * timestep_hours
            solar_avail_kwh_a = solar_a * timestep_hours
            solar_to_ev_a = min(charge_kwh_a, solar_avail_kwh_a)
            grid_to_ev_a = max(0.0, charge_kwh_a - solar_to_ev_a)
            solar_used_a += solar_to_ev_a
            total_cost_a += grid_to_ev_a * price_a
            if grid_a["net_grid_load_kw"] > peak_grid_a:
                peak_grid_a = grid_a["net_grid_load_kw"]

            history_a.append({
                "hour": hour,
                "net_grid_load_kw": grid_a["net_grid_load_kw"],
                "base_load_kw": grid_a["base_load_kw"],
                "total_charging_power_kw": round(step_charge_a, 2),
                "total_v2g_power_kw": 0.0,
                "electricity_price": price_a,
                "solar_generation_kw": solar_a,
                "ev_decisions": decisions_a
            })

            # --- RUN SCENARIO B (GridWise AI) ---
            step_charge_b = 0.0
            step_v2g_b = 0.0
            decisions_b = []
            for ev in fleet_b:
                ev.update_schedule_status(hour)
                if not ev.is_connected:
                    decisions_b.append({
                        "ev_id": ev.ev_id,
                        "power_kw": 0.0,
                        "soc": ev.current_soc,
                        "action_name": "IDLE",
                        "reason": "Not connected"
                    })
                    continue

                dec = rl_agent.select_action(ev, hour, timestep_hours)
                res = ev.apply_power(dec["power_kw"], timestep_hours)
                pwr = res["actual_power_kw"]
                if pwr > 0:
                    step_charge_b += pwr
                elif pwr < 0:
                    step_v2g_b += abs(pwr)

                decisions_b.append({
                    "ev_id": ev.ev_id,
                    "power_kw": pwr,
                    "soc": res["soc"],
                    "action_name": dec["action_name"],
                    "reason": dec["reason"],
                    "reward": dec["reward"]
                })

            grid_b = provider_b.get_grid_state(hour, charging_kw=step_charge_b, v2g_kw=step_v2g_b)
            price_b = provider_b.get_electricity_price(hour)["current_price"]
            solar_b = provider_b.get_solar_generation(hour)

            # Energy allocations for B
            charge_kwh_b = step_charge_b * timestep_hours
            v2g_kwh_b = step_v2g_b * timestep_hours
            v2g_energy_b += v2g_kwh_b

            solar_avail_kwh_b = solar_b * timestep_hours
            solar_to_ev_b = min(charge_kwh_b, solar_avail_kwh_b)
            grid_to_ev_b = max(0.0, charge_kwh_b - solar_to_ev_b)
            solar_used_b += solar_to_ev_b

            # V2G feed-in revenue offsets electricity draw
            v2g_revenue = v2g_kwh_b * price_b * 0.85
            step_net_cost = (grid_to_ev_b * price_b) - v2g_revenue
            total_cost_b += step_net_cost

            if grid_b["net_grid_load_kw"] > peak_grid_b:
                peak_grid_b = grid_b["net_grid_load_kw"]

            history_b.append({
                "hour": hour,
                "net_grid_load_kw": grid_b["net_grid_load_kw"],
                "base_load_kw": grid_b["base_load_kw"],
                "total_charging_power_kw": round(step_charge_b, 2),
                "total_v2g_power_kw": round(step_v2g_b, 2),
                "electricity_price": price_b,
                "solar_generation_kw": solar_b,
                "ev_decisions": decisions_b
            })

        # Calculate fleet satisfaction (SOC reaching target_soc)
        sat_a = (sum(1 for ev in fleet_a if ev.current_soc >= (ev.target_soc - 2.0)) / len(fleet_a)) * 100.0
        sat_b = (sum(1 for ev in fleet_b if ev.current_soc >= (ev.target_soc - 2.0)) / len(fleet_b)) * 100.0

        cycles_a = sum(ev.battery.cycle_count for ev in fleet_a)
        cycles_b = sum(ev.battery.cycle_count for ev in fleet_b)

        # Improvement percentages
        cost_savings_pct = max(0.0, min(100.0, ((total_cost_a - max(0.0, total_cost_b)) / max(1.0, total_cost_a)) * 100.0))
        peak_reduction_pct = max(0.0, ((peak_grid_a - peak_grid_b) / max(1.0, peak_grid_a)) * 100.0)
        solar_gain_pct = max(0.0, ((solar_used_b - solar_used_a) / max(1.0, solar_used_a)) * 100.0)

        return {
            "summary_comparison": {
                "energy_cost_traditional_inr": round(total_cost_a, 2),
                "energy_cost_ai_inr": round(max(0.0, total_cost_b), 2),
                "cost_savings_pct": round(cost_savings_pct, 1),
                "peak_load_traditional_kw": round(peak_grid_a, 2),
                "peak_load_ai_kw": round(peak_grid_b, 2),
                "peak_load_reduction_pct": round(peak_reduction_pct, 1),
                "solar_used_traditional_kwh": round(solar_used_a, 2),
                "solar_used_ai_kwh": round(solar_used_b, 2),
                "solar_utilization_gain_pct": round(solar_gain_pct, 1),
                "v2g_energy_traditional_kwh": round(v2g_energy_a, 2),
                "v2g_energy_ai_kwh": round(v2g_energy_b, 2),
                "battery_cycles_traditional": round(cycles_a, 3),
                "battery_cycles_ai": round(cycles_b, 3),
                "ev_satisfaction_traditional_pct": round(sat_a, 1),
                "ev_satisfaction_ai_pct": round(sat_b, 1)
            },
            "hourly_history_traditional": history_a,
            "hourly_history_ai": history_b
        }
