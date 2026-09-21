import uuid
import math
from typing import Dict, Any, List, Optional

from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.simulator.charger_simulator import ChargerSimulator
from backend.app.simulator.energy_provider import SimulationEnergyProvider
from backend.app.simulator.energy_balance import EnergyBalanceEngine, PowerFlowState
from backend.app.ai.agent import RLAgent
from backend.app.ai.constraints import ConstraintEngine

class SimulationEngine:
    """
    Central Digital Twin Simulation Engine.
    Manages fleet, chargers, energy telemetry, step execution, real-time streaming,
    and multi-EV energy flow calculations.
    """
    def __init__(
        self,
        simulation_id: Optional[str] = None,
        grid_capacity_kw: float = 100.0,
        solar_capacity_kw: float = 40.0,
        timestep_minutes: int = 15,
        duration_hours: float = 24.0
    ):
        self.simulation_id = simulation_id or str(uuid.uuid4())
        self.timestep_minutes = int(timestep_minutes)
        self.timestep_hours = self.timestep_minutes / 60.0
        self.duration_hours = float(duration_hours)
        
        self.current_hour: float = 0.0
        self.step_index: int = 0
        self.is_running: bool = False
        self.status: str = "READY"  # READY, RUNNING, PAUSED, COMPLETED, STOPPED
        
        # Physical Twins
        self.energy_provider = SimulationEnergyProvider(
            grid_capacity_kw=grid_capacity_kw,
            solar_capacity_kw=solar_capacity_kw
        )
        self.evs: Dict[str, EVDigitalTwin] = {}
        self.chargers: Dict[str, ChargerSimulator] = {}
        self.manual_overrides: Dict[str, str] = {}  # ev_id -> "CHARGE" | "DISCHARGE" | "IDLE"
        
        # AI Engine
        self.rl_agent = RLAgent(self.energy_provider)
        
        # History
        self.history: List[Dict[str, Any]] = []
        
        # Cumulative Energy Accounting
        self.energy_balance = EnergyBalanceEngine(base_station_aux_kw=6.0, loss_factor=0.035)
        self.total_solar_generated_kwh: float = 0.0
        self.total_solar_used_kwh: float = 0.0
        self.total_grid_drawn_kwh: float = 0.0
        self.total_v2g_supplied_kwh: float = 0.0
        self.total_energy_cost_inr: float = 0.0
        self.total_v2g_revenue_inr: float = 0.0
        self.peak_grid_load_kw: float = 0.0

        self.reset_default_fleet()

    def reset_default_fleet(self):
        """Initializes a realistic fleet of 5 EVs and corresponding chargers."""
        self.evs.clear()
        self.chargers.clear()
        defaults = [
            ("EV-001", "Tesla Model 3", 60.0, 35.0, 20.0, 100.0, 85.0, 8.0, 18.0, 7.4, 5.0),
            ("EV-002", "Nissan Leaf", 40.0, 45.0, 25.0, 100.0, 80.0, 7.0, 16.0, 6.6, 4.0),
            ("EV-003", "Hyundai Ioniq 5", 77.0, 25.0, 20.0, 100.0, 90.0, 9.0, 19.0, 11.0, 7.0),
            ("EV-004", "Tata Nexon EV", 40.0, 60.0, 30.0, 100.0, 85.0, 12.0, 20.0, 7.2, 4.5),
            ("EV-005", "MG ZS EV", 50.0, 40.0, 20.0, 100.0, 80.0, 10.0, 21.0, 7.4, 5.0)
        ]
        for item in defaults:
            ev = EVDigitalTwin(
                ev_id=item[0],
                name=item[1],
                battery_capacity_kwh=item[2],
                current_soc=item[3],
                minimum_soc=item[4],
                maximum_soc=item[5],
                target_soc=item[6],
                arrival_time=item[7],
                departure_time=item[8],
                max_charge_power_kw=item[9],
                max_discharge_power_kw=item[10]
            )
            self.evs[ev.ev_id] = ev
            charger = ChargerSimulator(
                charger_id=f"CHG-{ev.ev_id}",
                max_power_kw=max(ev.max_charge_power_kw, ev.max_discharge_power_kw) * 1.5
            )
            self.chargers[charger.charger_id] = charger

    def reset(self):
        self.current_hour = 0.0
        self.step_index = 0
        self.is_running = False
        self.status = "READY"
        self.history.clear()
        self.manual_overrides.clear()
        self.energy_balance.reset_daily_meters()
        self.total_solar_generated_kwh = 0.0
        self.total_solar_used_kwh = 0.0
        self.total_grid_drawn_kwh = 0.0
        self.total_v2g_supplied_kwh = 0.0
        self.total_energy_cost_inr = 0.0
        self.total_v2g_revenue_inr = 0.0
        self.peak_grid_load_kw = 0.0
        self.reset_default_fleet()

    def set_override(self, ev_id: str, action: Optional[str]):
        if action is None:
            self.manual_overrides.pop(ev_id, None)
        else:
            self.manual_overrides[ev_id] = action

    def step(self, dt_hours: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes a single simulation timestep:
        1. Time calculation
        2. Solar generation
        3. Electricity price
        4. Base grid load
        5. EV schedule status update
        6. AI / Operator decision evaluation
        7. Physical charging/discharging execution
        8. Instantaneous energy flow calculation
        9. Grid load aggregation
        10. Cumulative telemetry recording
        """
        if self.current_hour >= self.duration_hours:
            self.current_hour = 0.0
            self.step_index = 0
            self.reset_default_fleet()

        hour = self.current_hour
        timestep = float(dt_hours) if dt_hours is not None else self.timestep_hours

        # 1. Update environments
        solar_gen_kw = self.energy_provider.get_solar_generation(hour)
        price_data = self.energy_provider.get_electricity_price(hour)
        price = price_data["current_price"]

        # 2. Update EV schedules & collect decisions
        step_charging_kw = 0.0
        step_v2g_kw = 0.0
        ai_decisions = []

        for ev in self.evs.values():
            ev.update_schedule_status(hour)
            
            if not ev.is_connected:
                ai_decisions.append({
                    "ev_id": ev.ev_id,
                    "ev_name": ev.name,
                    "raw_action": 0,
                    "final_action": 0,
                    "action_name": "IDLE",
                    "power_kw": 0.0,
                    "reason": "EV outside parking window" if ev.status == "WAITING" else "EV completed trip & departed",
                    "reward": 0.0,
                    "soc": ev.current_soc,
                    "safety_overrides": [],
                    "is_manual_override": False
                })
                continue

            # Check manual override
            override = self.manual_overrides.get(ev.ev_id)
            if override:
                if override == "CHARGE":
                    raw_act = 1
                elif override == "DISCHARGE":
                    raw_act = 2
                else:
                    raw_act = 0

                # Validate override with safety layer
                final_act, power, overrides = ConstraintEngine.validate_action(
                    ev, raw_act, hour, 70.0, price
                )
                res = ev.apply_power(power, timestep)
                pwr = res["actual_power_kw"]
                if pwr > 0:
                    step_charging_kw += pwr
                elif pwr < 0:
                    step_v2g_kw += abs(pwr)

                ai_decisions.append({
                    "ev_id": ev.ev_id,
                    "ev_name": ev.name,
                    "raw_action": raw_act,
                    "final_action": final_act,
                    "action_name": "CHARGE" if final_act == 1 else ("DISCHARGE (V2G)" if final_act == 2 else "IDLE"),
                    "power_kw": pwr,
                    "reason": f"Manual Operator Override: Forced {override}",
                    "reward": 0.0,
                    "soc": res["soc"],
                    "safety_overrides": overrides,
                    "is_manual_override": True
                })
                continue

            # Intelligent RL Decision
            decision = self.rl_agent.select_action(ev, hour, timestep)
            res = ev.apply_power(decision["power_kw"], timestep)
            pwr = res["actual_power_kw"]
            decision["power_kw"] = pwr
            decision["soc"] = res["soc"]
            decision["is_manual_override"] = False
            ai_decisions.append(decision)

            if pwr > 0:
                step_charging_kw += pwr
            elif pwr < 0:
                step_v2g_kw += abs(pwr)

        # 3. Energy Flow & Strict Conservation Balance
        flow_state = self.energy_balance.calculate_balance(
            solar_gen_kw=solar_gen_kw,
            ev_charging_demand_kw=step_charging_kw,
            v2g_discharge_kw=step_v2g_kw,
            hour=hour,
            feed_in_allowed=True
        )

        solar_to_ev_kw = flow_state.solar_to_ev_kw
        grid_to_ev_kw = flow_state.grid_to_ev_kw
        ev_to_grid_kw = flow_state.v2g_to_grid_kw
        solar_to_grid_kw = flow_state.solar_to_grid_kw

        # 4. Grid State with dynamic EV load
        grid_state = self.energy_provider.get_grid_state(
            hour=hour,
            charging_kw=step_charging_kw,
            v2g_kw=step_v2g_kw,
            solar_surplus_kw=solar_to_grid_kw
        )

        net_grid_kw = grid_state["net_grid_load_kw"]
        if net_grid_kw > self.peak_grid_load_kw:
            self.peak_grid_load_kw = net_grid_kw

        # 5. Energy and Financial Accumulation (ΔE = P * Δt)
        acc_result = self.energy_balance.accumulate_energy(
            state=flow_state,
            timestep_hours=timestep,
            grid_tariff_inr=price,
            feed_in_tariff_inr=max(3.0, price * 0.65),
            v2g_payout_rate_inr=price * 1.15
        )

        self.total_solar_generated_kwh = self.energy_balance.cumulative_solar_gen_kwh
        self.total_solar_used_kwh = self.energy_balance.cumulative_solar_used_kwh
        self.total_grid_drawn_kwh = self.energy_balance.cumulative_grid_import_kwh
        self.total_v2g_supplied_kwh = self.energy_balance.cumulative_v2g_discharge_kwh
        self.total_energy_cost_inr = self.energy_balance.total_import_cost_inr
        self.total_v2g_revenue_inr = self.energy_balance.total_v2g_payout_inr

        flow_summary = flow_state.summary_text

        energy_flow = {
            "solar_to_ev_kw": round(flow_state.solar_to_ev_kw, 2),
            "solar_to_grid_kw": round(flow_state.solar_to_grid_kw, 2),
            "solar_to_aux_kw": round(flow_state.solar_to_aux_kw, 2),
            "grid_to_ev_kw": round(flow_state.grid_to_ev_kw, 2),
            "ev_to_grid_kw": round(flow_state.v2g_to_grid_kw, 2),
            "grid_import_kw": round(flow_state.grid_import_kw, 2),
            "grid_export_kw": round(flow_state.grid_export_kw, 2),
            "station_aux_kw": round(flow_state.station_aux_kw, 2),
            "system_losses_kw": round(flow_state.system_losses_kw, 2),
            "total_in_kw": round(flow_state.total_in_kw, 2),
            "total_out_kw": round(flow_state.total_out_kw, 2),
            "balance_error_kw": round(flow_state.balance_error_kw, 4),
            "is_balanced": flow_state.is_balanced,
            "solar_share_pct": flow_state.solar_share_pct,
            "grid_share_pct": flow_state.grid_share_pct,
            "flow_summary": flow_summary
        }

        # 6. Format Step State
        mins = int(round((hour % 1.0) * 60))
        h_int = int(hour)
        time_str = f"{h_int:02d}:{mins:02d}"

        # Enrich EV telemetry with per-EV solar vs grid power breakdown
        ev_fleet_data = []
        for ev in self.evs.values():
            item = ev.to_dict()
            item["power_breakdown"] = self.energy_balance.attribute_ev_power(ev.current_power_kw, flow_state)
            ev_fleet_data.append(item)

        step_record = {
            "simulation_id": self.simulation_id,
            "status": self.status,
            "time": time_str,
            "hour": round(hour, 2),
            "step_index": self.step_index,
            "grid": grid_state,
            "solar": {
                "generation_kw": round(solar_gen_kw, 2),
                "peak_capacity_kw": self.energy_provider.solar.solar_peak_capacity_kw,
                "cloud_factor": self.energy_provider.solar.cloud_factor
            },
            "price": price_data,
            "evs": ev_fleet_data,
            "energy_flow": energy_flow,
            "cumulative_energy": acc_result["cumulative"],
            "ai_decisions": ai_decisions,
            "total_charging_power_kw": round(step_charging_kw, 2),
            "total_v2g_power_kw": round(step_v2g_kw, 2),
            "net_grid_load_kw": round(net_grid_kw, 2),
            # Backwards-compatible fields for existing frontend
            "energy_state": {
                "grid_load_kw": grid_state["base_load_kw"],
                "grid_load_pct": grid_state["utilization_pct"],
                "grid_stress_level": grid_state["stress_level"],
                "solar_generation_kw": round(solar_gen_kw, 2),
                "electricity_price": price
            },
            "ev_fleet_status": ev_fleet_data
        }

        self.history.append(step_record)
        self.step_index += 1
        self.current_hour = round(self.current_hour + timestep, 3)

        return step_record

    def get_current_state(self) -> Dict[str, Any]:
        if self.history:
            return self.history[-1]
        
        # Generate initial state without advancing time
        grid_state = self.energy_provider.get_grid_state(self.current_hour)
        solar_gen = self.energy_provider.get_solar_generation(self.current_hour)
        price_info = self.energy_provider.get_electricity_price(self.current_hour)
        flow_state = self.energy_balance.calculate_balance(solar_gen, 0.0, 0.0, self.current_hour)

        mins = int(round((self.current_hour % 1.0) * 60))
        h_int = int(self.current_hour)
        time_str = f"{h_int:02d}:{mins:02d}"

        ev_fleet_data = []
        for ev in self.evs.values():
            item = ev.to_dict()
            item["power_breakdown"] = self.energy_balance.attribute_ev_power(ev.current_power_kw, flow_state)
            ev_fleet_data.append(item)

        return {
            "simulation_id": self.simulation_id,
            "status": self.status,
            "time": time_str,
            "hour": round(self.current_hour, 2),
            "step_index": self.step_index,
            "grid": grid_state,
            "solar": {
                "generation_kw": round(solar_gen, 2),
                "peak_capacity_kw": self.energy_provider.solar.solar_peak_capacity_kw,
                "cloud_factor": self.energy_provider.solar.cloud_factor
            },
            "price": price_info,
            "evs": ev_fleet_data,
            "energy_flow": {
                "solar_to_ev_kw": 0.0,
                "solar_to_grid_kw": 0.0,
                "solar_to_aux_kw": round(flow_state.solar_to_aux_kw, 2),
                "grid_to_ev_kw": 0.0,
                "ev_to_grid_kw": 0.0,
                "grid_import_kw": round(flow_state.grid_import_kw, 2),
                "grid_export_kw": round(flow_state.grid_export_kw, 2),
                "station_aux_kw": round(flow_state.station_aux_kw, 2),
                "system_losses_kw": round(flow_state.system_losses_kw, 2),
                "total_in_kw": round(flow_state.total_in_kw, 2),
                "total_out_kw": round(flow_state.total_out_kw, 2),
                "balance_error_kw": 0.0,
                "is_balanced": True,
                "solar_share_pct": 0.0,
                "grid_share_pct": 0.0,
                "flow_summary": "System Ready"
            },
            "cumulative_energy": {
                "solar_gen_kwh_today": round(self.energy_balance.cumulative_solar_gen_kwh, 2),
                "solar_used_kwh_today": round(self.energy_balance.cumulative_solar_used_kwh, 2),
                "grid_import_kwh_today": round(self.energy_balance.cumulative_grid_import_kwh, 2),
                "grid_export_kwh_today": round(self.energy_balance.cumulative_grid_export_kwh, 2),
                "ev_charging_kwh_today": round(self.energy_balance.cumulative_ev_charging_kwh, 2),
                "v2g_discharge_kwh_today": round(self.energy_balance.cumulative_v2g_discharge_kwh, 2),
                "station_aux_kwh_today": round(self.energy_balance.cumulative_station_aux_kwh, 2),
                "system_losses_kwh_today": round(self.energy_balance.cumulative_losses_kwh, 2),
                "total_import_cost_inr": round(self.energy_balance.total_import_cost_inr, 2),
                "total_export_revenue_inr": round(self.energy_balance.total_export_revenue_inr, 2),
                "total_v2g_payout_inr": round(self.energy_balance.total_v2g_payout_inr, 2),
                "net_energy_cost_inr": round(self.energy_balance.net_energy_cost_inr, 2)
            },
            "ai_decisions": [],
            "total_charging_power_kw": 0.0,
            "total_v2g_power_kw": 0.0,
            "net_grid_load_kw": round(grid_state["base_load_kw"], 2),
            "energy_state": {
                "grid_load_kw": grid_state["base_load_kw"],
                "grid_load_pct": grid_state["utilization_pct"],
                "grid_stress_level": grid_state["stress_level"],
                "solar_generation_kw": round(solar_gen, 2),
                "electricity_price": price_info["current_price"]
            },
            "ev_fleet_status": ev_fleet_data
        }
