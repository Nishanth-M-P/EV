import copy
import asyncio
from typing import Dict, List, Any, Optional
from backend.services.energy_service import EnergyService
from backend.services.ev_service import EVFleetService, EVModel
from backend.rl_engine import RLDecisionEngine
from backend.services.analytics_service import AnalyticsService


class SimulationEngine:
    def __init__(self):
        self.energy_service = EnergyService()
        self.ev_service = EVFleetService()
        self.rl_engine = RLDecisionEngine(self.energy_service)
        self.current_hour = 0.0
        self.is_running = False
        self.tick_interval_seconds = 1.0  # 1 second real-time tick rate
        self.step_size_hours = 0.5        # 30 minute simulated time per tick
        self.manual_overrides: Dict[str, str] = {}  # ev_id -> "CHARGE" | "DISCHARGE" | "IDLE"
        self.history: List[Dict[str, Any]] = []

    def reset(self):
        self.current_hour = 0.0
        self.is_running = False
        self.history.clear()
        self.manual_overrides.clear()
        self.ev_service.reset_default_fleet()

    def set_manual_override(self, ev_id: str, action_override: Optional[str]):
        if action_override is None:
            if ev_id in self.manual_overrides:
                del self.manual_overrides[ev_id]
        else:
            self.manual_overrides[ev_id] = action_override

    def step(self) -> Dict[str, Any]:
        if self.current_hour >= 24.0:
            self.current_hour = 0.0  # Auto loop continuous 24h cycle
            self.ev_service.reset_default_fleet()

        energy_state = self.energy_service.get_state_at_hour(self.current_hour)
        ev_decisions = []

        total_charging_power = 0.0
        total_discharging_power = 0.0

        for ev in self.ev_service.evs.values():
            ev.update_status(self.current_hour)
            
            if ev.status in ["WAITING", "COMPLETED"]:
                ev_decisions.append({
                    "ev_id": ev.ev_id,
                    "ev_name": ev.name,
                    "final_action": 0,
                    "action_name": "IDLE",
                    "power_kw": 0.0,
                    "reason": "EV not connected" if ev.status == "WAITING" else "EV completed trip & departed",
                    "soc": ev.current_soc,
                    "reward": 0.0,
                    "is_manual_override": False
                })
                continue

            # Check if there is a manual override for this EV
            override = self.manual_overrides.get(ev.ev_id)
            if override:
                if override == "CHARGE":
                    act = 1
                    pwr = ev.max_charge_power_kw
                elif override == "DISCHARGE":
                    act = 2
                    pwr = -ev.max_discharge_power_kw
                else:
                    act = 0
                    pwr = 0.0

                res = ev.apply_power_decision(pwr, duration_hours=self.step_size_hours)
                ev_decisions.append({
                    "ev_id": ev.ev_id,
                    "ev_name": ev.name,
                    "final_action": act,
                    "action_name": "CHARGE" if act == 1 else ("DISCHARGE (V2G)" if act == 2 else "IDLE"),
                    "power_kw": res["actual_power_kw"],
                    "reason": f"Manual Operator Override: Forced {override}",
                    "soc": res["soc"],
                    "reward": 0.0,
                    "is_manual_override": True
                })
                actual_pwr = res["actual_power_kw"]
                if actual_pwr > 0:
                    total_charging_power += actual_pwr
                elif actual_pwr < 0:
                    total_discharging_power += abs(actual_pwr)
                continue

            # AI RL Decision
            decision = self.rl_engine.select_action(ev, self.current_hour)
            res = ev.apply_power_decision(decision["power_kw"], duration_hours=self.step_size_hours)
            
            decision["soc"] = res["soc"]
            decision["ev_name"] = ev.name
            decision["is_manual_override"] = False
            ev_decisions.append(decision)

            pwr = res["actual_power_kw"]
            if pwr > 0:
                total_charging_power += pwr
            elif pwr < 0:
                total_discharging_power += abs(pwr)

        step_record = {
            "hour": round(self.current_hour, 2),
            "energy_state": energy_state,
            "ev_decisions": ev_decisions,
            "total_charging_power_kw": round(total_charging_power, 2),
            "total_v2g_power_kw": round(total_discharging_power, 2),
            "net_grid_impact_kw": round(energy_state["grid_load_kw"] + total_charging_power - total_discharging_power, 2),
            "ev_fleet_status": self.ev_service.get_all_evs()
        }

        self.history.append(step_record)
        self.current_hour = round(self.current_hour + self.step_size_hours, 2)

        return step_record

    @staticmethod
    def run_benchmark() -> Dict[str, Any]:
        """
        Runs Scenario A (Traditional Immediate Charging) vs Scenario B (GridWise AI)
        over 24 hours with identical profiles.
        """
        energy_svc = EnergyService()
        
        fleet_a = EVFleetService()
        fleet_a.reset_default_fleet()
        
        fleet_b = EVFleetService()
        fleet_b.reset_default_fleet()
        
        rl_engine_b = RLDecisionEngine(energy_svc)

        history_a = []
        history_b = []

        for step_idx in range(48):
            hour = step_idx * 0.5
            energy_state = energy_svc.get_state_at_hour(hour)

            # Scenario A: Traditional Immediate Charging
            ev_decisions_a = []
            for ev in fleet_a.evs.values():
                ev.update_status(hour)
                if hour >= ev.arrival_time and hour < ev.departure_time and ev.current_soc < ev.required_soc:
                    power = ev.max_charge_power_kw
                    act = 1
                    reason = "Traditional rule: Immediate charging upon arrival"
                else:
                    power = 0.0
                    act = 0
                    reason = "Idle / Fully charged"

                res = ev.apply_power_decision(power, duration_hours=0.5)
                ev_decisions_a.append({
                    "ev_id": ev.ev_id,
                    "final_action": act,
                    "power_kw": res["actual_power_kw"],
                    "soc": res["soc"],
                    "reason": reason,
                    "reward": 0.0
                })

            history_a.append({
                "hour": hour,
                "energy_state": energy_state,
                "ev_decisions": ev_decisions_a
            })

            # Scenario B: GridWise AI
            ev_decisions_b = []
            for ev in fleet_b.evs.values():
                ev.update_status(hour)
                if ev.status in ["WAITING", "COMPLETED"]:
                    ev_decisions_b.append({
                        "ev_id": ev.ev_id,
                        "final_action": 0,
                        "power_kw": 0.0,
                        "soc": ev.current_soc,
                        "reason": "Not connected",
                        "reward": 0.0
                    })
                    continue

                decision = rl_engine_b.select_action(ev, hour)
                res = ev.apply_power_decision(decision["power_kw"], duration_hours=0.5)
                decision["soc"] = res["soc"]
                ev_decisions_b.append(decision)

            history_b.append({
                "hour": hour,
                "energy_state": energy_state,
                "ev_decisions": ev_decisions_b
            })

        analytics_a = AnalyticsService.compute_simulation_analytics(history_a)
        analytics_b = AnalyticsService.compute_simulation_analytics(history_b)

        sat_a = sum(1 for ev in fleet_a.evs.values() if ev.current_soc >= (ev.required_soc - 2.0)) / len(fleet_a.evs) * 100.0
        sat_b = sum(1 for ev in fleet_b.evs.values() if ev.current_soc >= (ev.required_soc - 2.0)) / len(fleet_b.evs) * 100.0

        cycles_a = sum(ev.cycle_count for ev in fleet_a.evs.values())
        cycles_b = sum(ev.cycle_count for ev in fleet_b.evs.values())

        cost_a = analytics_a["economic_metrics"]["total_charging_cost_inr"]
        cost_b = analytics_b["economic_metrics"]["net_energy_cost_inr"]
        savings_pct = round(((cost_a - cost_b) / max(1.0, cost_a)) * 100.0, 1)

        peak_a = analytics_a["grid_metrics"]["peak_grid_load_kw"]
        peak_b = analytics_b["grid_metrics"]["peak_grid_load_kw"]
        peak_red_pct = round(((peak_a - peak_b) / max(1.0, peak_a)) * 100.0, 1)

        return {
            "summary_comparison": {
                "energy_cost_traditional_inr": cost_a,
                "energy_cost_ai_inr": cost_b,
                "cost_savings_pct": savings_pct if cost_a > 0 else 100.0,
                "peak_load_traditional_kw": peak_a,
                "peak_load_ai_kw": peak_b,
                "peak_load_reduction_pct": peak_red_pct,
                "solar_used_traditional_kwh": analytics_a["renewable_metrics"]["solar_energy_consumed_kwh"],
                "solar_used_ai_kwh": analytics_b["renewable_metrics"]["solar_energy_consumed_kwh"],
                "v2g_energy_traditional_kwh": analytics_a["grid_metrics"]["v2g_energy_supplied_kwh"],
                "v2g_energy_ai_kwh": analytics_b["grid_metrics"]["v2g_energy_supplied_kwh"],
                "battery_cycles_traditional": round(cycles_a, 2),
                "battery_cycles_ai": round(cycles_b, 2),
                "ev_satisfaction_traditional_pct": round(sat_a, 1),
                "ev_satisfaction_ai_pct": round(sat_b, 1)
            },
            "analytics_traditional": analytics_a,
            "analytics_ai": analytics_b,
            "hourly_history_traditional": history_a,
            "hourly_history_ai": history_b
        }
