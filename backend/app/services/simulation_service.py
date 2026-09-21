import asyncio
import copy
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.app.simulator.simulation_engine import SimulationEngine
from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.simulator.charger_simulator import ChargerSimulator
from backend.app.ai.comparator import AIComparator
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.report_service import ReportService
from backend.app.models.database_models import (
    Simulation,
    SimulationStep,
    AIDecisionRecord,
    AnalyticsRecord
)

class SimulationService:
    def __init__(self):
        self.engine = SimulationEngine()
        self.tick_interval_seconds = 1.0  # Real-time update cadence
        self.is_running = True  # Default Mode A: continuous real-time advance
        self.engine.is_running = True
        self.engine.status = "RUNNING"
        self.preset_scenario = "Smart Grid Peak-Shaving Demo"

    def start(self):
        self.is_running = True
        self.engine.is_running = True
        self.engine.status = "RUNNING"

    def pause(self):
        self.is_running = False
        self.engine.is_running = False
        self.engine.status = "PAUSED"

    def stop(self):
        self.is_running = False
        self.engine.is_running = False
        self.engine.status = "STOPPED"

    def reset(self):
        self.is_running = False
        self.engine.reset()

    def step(self) -> Dict[str, Any]:
        return self.engine.step()

    def configure(
        self,
        duration_hours: float = 24.0,
        timestep_minutes: int = 15,
        grid_capacity_kw: float = 100.0,
        solar_capacity_kw: float = 40.0,
        cloud_factor: float = 1.0,
        num_evs: int = 5,
        scenario_name: str = "Smart Grid Peak-Shaving Demo"
    ):
        self.preset_scenario = scenario_name
        self.engine = SimulationEngine(
            grid_capacity_kw=grid_capacity_kw,
            solar_capacity_kw=solar_capacity_kw,
            timestep_minutes=timestep_minutes,
            duration_hours=duration_hours
        )
        self.engine.energy_provider.solar.cloud_factor = cloud_factor
        return self.engine.get_current_state()

    def create_custom_scenario(
        self,
        name: str = "Custom Scenario",
        scenario: str = "custom",
        duration_hours: float = 24.0,
        timestep_minutes: int = 15,
        grid_capacity_kw: float = 100.0,
        solar_capacity_kw: float = 40.0,
        cloud_factor: float = 1.0,
        evs_config: Optional[List[Dict[str, Any]]] = None,
        pricing_config: Optional[Dict[str, Any]] = None,
        ai_enabled: bool = True,
        v2g_enabled: bool = True
    ) -> Dict[str, Any]:
        """Creates and loads an advanced scenario into the Digital Twin."""
        self.preset_scenario = name
        self.engine = SimulationEngine(
            grid_capacity_kw=grid_capacity_kw,
            solar_capacity_kw=solar_capacity_kw,
            timestep_minutes=timestep_minutes,
            duration_hours=duration_hours
        )
        self.engine.energy_provider.solar.cloud_factor = cloud_factor

        # Configure custom fleet if provided
        if evs_config and len(evs_config) > 0:
            self.engine.evs.clear()
            self.engine.chargers.clear()
            for idx, item in enumerate(evs_config):
                ev_id = item.get("id") or item.get("ev_id") or f"EV-{idx+1:03d}"
                ev_name = item.get("name", f"EV-{idx+1}")
                cap = float(item.get("battery_capacity_kwh", 60.0))
                cur_soc = float(item.get("current_soc", 50.0))
                min_soc = float(item.get("minimum_soc", 20.0))
                max_soc = float(item.get("maximum_soc", 100.0))
                tgt_soc = float(item.get("target_soc", item.get("required_soc", 85.0)))
                arr = float(item.get("arrival_time", 8.0))
                dep = float(item.get("departure_time", 18.0))
                max_chg = float(item.get("max_charge_power_kw", 7.4))
                max_dis = float(item.get("max_discharge_power_kw", 5.0)) if v2g_enabled else 0.0

                ev = EVDigitalTwin(
                    ev_id=ev_id,
                    name=ev_name,
                    battery_capacity_kwh=cap,
                    current_soc=cur_soc,
                    minimum_soc=min_soc,
                    maximum_soc=max_soc,
                    target_soc=tgt_soc,
                    arrival_time=arr,
                    departure_time=dep,
                    max_charge_power_kw=max_chg,
                    max_discharge_power_kw=max_dis
                )
                self.engine.evs[ev.ev_id] = ev
                charger = ChargerSimulator(
                    charger_id=f"CHG-{ev.ev_id}",
                    max_power_kw=max(ev.max_charge_power_kw, ev.max_discharge_power_kw) * 1.5
                )
                self.engine.chargers[charger.charger_id] = charger

        return self.engine.get_current_state()

    def run_benchmark(self) -> Dict[str, Any]:
        fleet_specs = [ev.to_dict() for ev in self.engine.evs.values()]
        return AIComparator.run_comparison(
            fleet_specs=fleet_specs,
            grid_capacity_kw=self.engine.energy_provider.grid.grid_capacity_kw,
            solar_capacity_kw=self.engine.energy_provider.solar.solar_peak_capacity_kw,
            timestep_minutes=self.engine.timestep_minutes
        )

    def run_24h_cycle(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """Runs the entire 24h simulation batch to completion, compares against baseline and returns full results."""
        self.engine.reset()
        self.engine.status = "RUNNING"

        total_steps = int((self.engine.duration_hours * 60) / self.engine.timestep_minutes)
        for _ in range(total_steps):
            self.step()

        self.engine.status = "COMPLETED"
        self.is_running = False

        benchmark = self.run_benchmark()
        analytics = AnalyticsService.compute_analytics(self.engine.history)

        if db:
            self.persist_to_db(db)

        return {
            "simulation_id": self.engine.simulation_id,
            "status": "COMPLETED",
            "duration_hours": self.engine.duration_hours,
            "steps_executed": len(self.engine.history),
            "benchmark": benchmark,
            "analytics": analytics,
            "final_state": self.engine.get_current_state()
        }

    def generate_report(self) -> Dict[str, Any]:
        analytics = AnalyticsService.compute_analytics(self.engine.history)
        benchmark = self.run_benchmark()
        params = {
            "simulation_id": self.engine.simulation_id,
            "scenario": self.preset_scenario,
            "grid_capacity_kw": self.engine.energy_provider.grid.grid_capacity_kw,
            "solar_capacity_kw": self.engine.energy_provider.solar.solar_peak_capacity_kw,
            "timestep_minutes": self.engine.timestep_minutes,
            "num_evs": len(self.engine.evs)
        }
        return ReportService.generate_report(
            simulation_id=self.engine.simulation_id,
            parameters=params,
            analytics=analytics,
            benchmark=benchmark
        )

    def persist_to_db(self, db: Session):
        """Saves current simulation run and analytics record into SQLite/PostgreSQL."""
        sim = db.query(Simulation).filter(Simulation.id == self.engine.simulation_id).first()
        if not sim:
            sim = Simulation(
                id=self.engine.simulation_id,
                name=self.preset_scenario,
                scenario=self.preset_scenario,
                duration_hours=self.engine.duration_hours,
                timestep_minutes=self.engine.timestep_minutes,
                total_evs=len(self.engine.evs),
                status=self.engine.status,
                completed_at=datetime.utcnow() if self.engine.status in ["COMPLETED", "STOPPED"] else None
            )
            db.add(sim)
            db.commit()
        else:
            sim.status = self.engine.status
            if self.engine.status in ["COMPLETED", "STOPPED"] and not sim.completed_at:
                sim.completed_at = datetime.utcnow()
            db.commit()

        # Compute and persist Analytics record
        analytics_data = AnalyticsService.compute_analytics(self.engine.history)
        econ = analytics_data["economic_metrics"]
        grid = analytics_data["grid_metrics"]
        renew = analytics_data["renewable_metrics"]
        ai = analytics_data["ai_metrics"]

        existing_an = db.query(AnalyticsRecord).filter(AnalyticsRecord.simulation_id == sim.id).first()
        if not existing_an:
            an_rec = AnalyticsRecord(
                simulation_id=sim.id,
                total_energy_consumed_kwh=grid["grid_energy_drawn_kwh"],
                total_charging_cost_inr=econ["total_charging_cost_inr"],
                average_electricity_price=econ["average_electricity_price"],
                peak_grid_load_kw=grid["peak_grid_load_kw"],
                solar_energy_generated_kwh=renew["solar_energy_generated_kwh"],
                solar_energy_utilized_kwh=renew["solar_energy_consumed_kwh"],
                renewable_utilization_pct=renew["renewable_utilization_pct"],
                v2g_energy_supplied_kwh=grid["v2g_energy_supplied_kwh"],
                v2g_revenue_earned_inr=econ["v2g_revenue_earned_inr"],
                rl_total_reward=ai["total_reward"],
                full_report_json=analytics_data
            )
            db.add(an_rec)
            db.commit()
        else:
            existing_an.total_energy_consumed_kwh = grid["grid_energy_drawn_kwh"]
            existing_an.total_charging_cost_inr = econ["total_charging_cost_inr"]
            existing_an.average_electricity_price = econ["average_electricity_price"]
            existing_an.peak_grid_load_kw = grid["peak_grid_load_kw"]
            existing_an.solar_energy_generated_kwh = renew["solar_energy_generated_kwh"]
            existing_an.solar_energy_utilized_kwh = renew["solar_energy_consumed_kwh"]
            existing_an.renewable_utilization_pct = renew["renewable_utilization_pct"]
            existing_an.v2g_energy_supplied_kwh = grid["v2g_energy_supplied_kwh"]
            existing_an.v2g_revenue_earned_inr = econ["v2g_revenue_earned_inr"]
            existing_an.rl_total_reward = ai["total_reward"]
            existing_an.full_report_json = analytics_data
            db.commit()

    def get_simulation_results(self, sim_id: str, db: Session) -> Dict[str, Any]:
        """Returns simulation results for a given simulation ID."""
        if sim_id == self.engine.simulation_id or sim_id == "current":
            analytics = AnalyticsService.compute_analytics(self.engine.history)
            benchmark = self.run_benchmark()
            return {
                "simulation_id": self.engine.simulation_id,
                "status": self.engine.status,
                "analytics": analytics,
                "benchmark": benchmark,
                "state": self.engine.get_current_state()
            }
        
        sim = db.query(Simulation).filter(Simulation.id == sim_id).first()
        if not sim:
            return {"error": "Simulation run not found"}

        an = db.query(AnalyticsRecord).filter(AnalyticsRecord.simulation_id == sim_id).first()
        return {
            "simulation_id": sim.id,
            "name": sim.name,
            "status": sim.status,
            "duration_hours": sim.duration_hours,
            "total_evs": sim.total_evs,
            "created_at": sim.created_at.isoformat() if sim.created_at else None,
            "completed_at": sim.completed_at.isoformat() if sim.completed_at else None,
            "analytics": an.full_report_json if an else None
        }

    def get_history(self, db: Session, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns history of simulation runs stored in database."""
        sims = db.query(Simulation).order_by(Simulation.created_at.desc()).limit(limit).all()
        history = []
        for s in sims:
            an = db.query(AnalyticsRecord).filter(AnalyticsRecord.simulation_id == s.id).first()
            history.append({
                "simulation_id": s.id,
                "name": s.name,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "completed_at": s.completed_at.isoformat() if s.completed_at else "",
                "total_evs": s.total_evs,
                "timestep_minutes": s.timestep_minutes,
                "total_charging_cost_inr": an.total_charging_cost_inr if an else 0.0,
                "peak_grid_load_kw": an.peak_grid_load_kw if an else 0.0,
                "solar_utilization_pct": an.renewable_utilization_pct if an else 0.0,
                "v2g_energy_kwh": an.v2g_energy_supplied_kwh if an else 0.0
            })
        return history

    @staticmethod
    def get_presets() -> Dict[str, Any]:
        return {
            "normal_day": {
                "name": "Normal Diurnal Day",
                "description": "Standard balanced residential demand with normal solar and 5 commuter EVs.",
                "duration_hours": 24.0,
                "timestep_minutes": 15,
                "grid_capacity_kw": 100.0,
                "solar_capacity_kw": 40.0,
                "cloud_factor": 1.0,
                "v2g_enabled": True
            },
            "high_solar": {
                "name": "High Solar Day",
                "description": "Excess 60 kW PV generation array under clear skies to test maximum renewable soak.",
                "duration_hours": 24.0,
                "timestep_minutes": 15,
                "grid_capacity_kw": 100.0,
                "solar_capacity_kw": 60.0,
                "cloud_factor": 1.0,
                "v2g_enabled": True
            },
            "peak_grid_stress": {
                "name": "Peak Grid Stress Day",
                "description": "High evening residential demand spikes testing V2G peak-shaving relief.",
                "duration_hours": 24.0,
                "timestep_minutes": 15,
                "grid_capacity_kw": 120.0,
                "solar_capacity_kw": 35.0,
                "cloud_factor": 0.9,
                "v2g_enabled": True
            },
            "overcast_low_solar": {
                "name": "Overcast Low-Solar Day",
                "description": "Heavy cloud cover (0.3) testing off-peak night charging load shifting.",
                "duration_hours": 24.0,
                "timestep_minutes": 15,
                "grid_capacity_kw": 90.0,
                "solar_capacity_kw": 40.0,
                "cloud_factor": 0.3,
                "v2g_enabled": False
            },
            "high_ev_fleet": {
                "name": "High EV Fleet Demand",
                "description": "8 mixed electric vehicles with aggressive departure SLAs.",
                "duration_hours": 24.0,
                "timestep_minutes": 15,
                "grid_capacity_kw": 140.0,
                "solar_capacity_kw": 50.0,
                "cloud_factor": 1.0,
                "v2g_enabled": True
            },
            "v2g_stress_test": {
                "name": "V2G Stress Test",
                "description": "Aggressive grid relief scenario validating battery health and reserve protections.",
                "duration_hours": 24.0,
                "timestep_minutes": 15,
                "grid_capacity_kw": 80.0,
                "solar_capacity_kw": 40.0,
                "cloud_factor": 1.0,
                "v2g_enabled": True
            }
        }

    def load_preset(self, preset_key: str) -> Dict[str, Any]:
        presets = self.get_presets()
        if preset_key not in presets:
            preset_key = "normal_day"
        p = presets[preset_key]
        return self.create_custom_scenario(
            name=p["name"],
            scenario=preset_key,
            duration_hours=p["duration_hours"],
            timestep_minutes=p["timestep_minutes"],
            grid_capacity_kw=p["grid_capacity_kw"],
            solar_capacity_kw=p["solar_capacity_kw"],
            cloud_factor=p["cloud_factor"],
            v2g_enabled=p["v2g_enabled"]
        )

    def export_experiment_csv(self) -> str:
        lines = ["step,time,hour,net_grid_load_kw,solar_gen_kw,price_inr,ev_id,ev_name,soc_pct,target_soc_pct,temperature_c,soh_pct,proposed_action,approved_action,power_kw,reward,safety_override"]
        for s in self.engine.history:
            step_idx = s.get("step_index", 0)
            t_str = s.get("time", "")
            hr = s.get("hour", 0.0)
            g_kw = s.get("net_grid_load_kw", 0.0)
            sol_kw = s.get("solar_generation_kw", 0.0)
            pr = s.get("electricity_price", 0.0)
            evs = s.get("evs", [])
            decisions = {d["ev_id"]: d for d in s.get("ai_decisions", [])}

            for ev in evs:
                eid = ev.get("id") or ev.get("ev_id")
                d = decisions.get(eid, {})
                prop_act = d.get("proposed_action", d.get("action_name", "IDLE"))
                appr_act = d.get("action_name", "IDLE")
                pwr = d.get("power_kw", ev.get("current_power_kw", 0.0))
                rew = d.get("reward", 0.0)
                overrides = "; ".join(d.get("safety_overrides", []))

                line = f"{step_idx},{t_str},{hr},{g_kw},{sol_kw},{pr},{eid},{ev.get('name')},{ev.get('current_soc')},{ev.get('target_soc')},{ev.get('temperature_c', 25.0)},{ev.get('battery_health', 100.0)},{prop_act},{appr_act},{pwr},{rew},\"{overrides}\""
                lines.append(line)

        return "\n".join(lines)

