"""
GridWise AI - Unified V2G Digital Twin Simulation Engine
Coordinates real-time data ingestion, dual-rate physics/control loops (1s physics, 10s control),
exact battery physics integration, charging timeline countdowns, and telemetry buffering.
Complies strictly with PRD Sections 1-85 and Critical Simulation Behavior Specification:
- Default state: CHARGE when EV connected & SOC < target
- V2G allowed ONLY when high load is confirmed after 30s persistence, reserve safe & departure safe
- Price and renewables alone MUST NOT trigger V2G
- Charger and V2G smooth ramping (max 1.0 kW/s)
- Minimum dwell times (5 min at 1x) to prevent rapid mode oscillation
"""

import time
import math
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Set, Callable
import numpy as np

from backend.data_sources.kptcl_sldc import KPTCLSLDCSource
from backend.data_sources.iex_rtm import IEXRTMPriceSource
from backend.data_sources.renewable import RenewableGenerationSource
from backend.data_fusion.pipeline import LiveTelemetryPipeline
from backend.data_fusion.realtime_state import RealTimeGridState
from backend.grid.demand import GridDemandManager, GridStressEvaluator, GridStressEngine
from backend.ev.ev_model import EVState, BatteryState, DepartureUrgencyCalculator
from backend.charger.bidirectional_charger import ChargerState
from backend.controller.drl_controller import ControllerState, Decision, SafetyFilter
from backend.topology import FixedSystemTopology
from backend.simulation.circuit_engine import CircuitEngine
from backend.app.utils.logger import logger


class DigitalTwinEngine:
    def __init__(self):
        # 1. External Data Sources & Live Telemetry Pipeline
        self.kptcl_source = KPTCLSLDCSource()
        self.iex_source = IEXRTMPriceSource()
        self.renewable_source = RenewableGenerationSource()
        self.pipeline = LiveTelemetryPipeline()
        self.sequence_number: int = 1000
        self.circuit_engine = CircuitEngine()

        # 2. Grid Stress Engine (Dedicated persistence & hysteresis evaluation)
        self.grid_stress_engine = GridStressEngine(
            v2g_entry_stress=75.0,
            v2g_exit_stress=60.0,
            supply_margin_threshold_pct=5.0,
            high_load_confirmation_time_sec=30.0,
            v2g_recovery_time_sec=30.0
        )

        # 3. Continuous Live Digital Twin Operational State
        self.is_running: bool = False
        self.is_paused: bool = False
        self.data_mode: str = "LIVE"  # Always LIVE
        self.speed_multiplier: float = 1.0  # 1x real-time physics

        # 4. Real-Time Simulation Clock
        now_dt = datetime.now()
        self.sim_clock_seconds: float = float(now_dt.hour * 3600 + now_dt.minute * 60 + now_dt.second)
        self.sim_time_str: str = now_dt.strftime("%H:%M:%S")
        self.real_time_str: str = now_dt.strftime("%H:%M:%S")

        # 5. Dual-Rate Loop & Dwell Time Timing (PRD Section 10, 11, 24, 25, 34)
        self.control_interval_sec: float = 10.0
        self.time_since_last_control_eval_sec: float = 0.0
        self.time_to_next_control_eval_sec: float = 10.0
        self.current_mode: str = "CHARGING" # CHARGING, V2G, IDLE
        self.mode_dwell_time_sec: float = 0.0
        self.minimum_charge_hold_sec: float = 30.0 # 30s per Section 11
        self.minimum_v2g_hold_sec: float = 30.0    # 30s per Section 11
        self.default_charge_kw: float = 11.0
        self.default_v2g_kw: float = -6.0
        self.scenario: str = "normal"
        self.last_tick_time: float = time.time()
        self.last_tick_dt: float = 1.0
        self.last_tick_iso: str = datetime.now(timezone.utc).isoformat()

        # 6. Deep Reinforcement Learning PPO Model (Stable-Baselines3)
        self.ppo_model = None
        self.ppo_last_action: float = 0.5
        self.ppo_proposed_kw: float = 11.0
        try:
            from stable_baselines3 import PPO
            from pathlib import Path
            model_path = Path(__file__).resolve().parent.parent.parent / "models" / "ppo_v2g_latest.zip"
            if model_path.exists():
                self.ppo_model = PPO.load(str(model_path))
                logger.info(f"Loaded trained PPO policy model from {model_path}")
                print(f"[PPO_ENGINE] Loaded trained PPO policy from {model_path}", flush=True)
            else:
                logger.warning(f"PPO model not found at {model_path}")
        except Exception as ppo_err:
            logger.error(f"Failed to load PPO model: {ppo_err}")

        # 7. Authoritative Component States
        self.grid_state = RealTimeGridState()
        self.ev_state = EVState()
        self.battery_state = BatteryState()
        self.charger_state = ChargerState(
            power_kw=11.0,
            target_power_kw=11.0,
            ramp_rate_kw_per_sec=1.0
        )
        self.controller_state = ControllerState(
            algorithm="PPO (SB3 Neural Policy)",
            model_version="ppo_v2g_latest.zip"
        )
        self.latest_decision = Decision(
            action="CHARGE",
            power_kw=11.0,
            reason_code="PPO_OPTIMAL",
            reason="PPO model active: CHARGE (+11.0 kW)",
            controller="PPO_MODEL"
        )

        # 7. Energy Meter (Observation only, PRD Section 14, 35, 36)
        self.meter_state: Dict[str, Any] = {
            "import_power_kw": 11.0,
            "export_power_kw": 0.0,
            "net_power_kw": 11.0,
            "imported_energy_kwh": 14.82,
            "exported_energy_kwh": 0.0,
            "direction": "GRID → EV",
            "voltage_v": 400.0,
            "current_a": 27.5,
            "power_factor": 0.99
        }

        # 8. Telemetry History Buffer (PRD Section 55 & 57)
        self.telemetry_history: deque = deque(maxlen=3600)
        self._seed_telemetry_history()

        # 9. Background Loop & Callbacks
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._telemetry_callbacks: Set[Callable[[Dict[str, Any]], None]] = set()
        self._lock = threading.Lock()
        self.step_count = 0

    def register_callback(self, cb: Callable[[Dict[str, Any]], None]):
        self._telemetry_callbacks.add(cb)

    def unregister_callback(self, cb: Callable[[Dict[str, Any]], None]):
        self._telemetry_callbacks.discard(cb)

    def _seed_telemetry_history(self):
        """Pre-populates rolling buffer with recent baseline telemetry points."""
        base_time = datetime.now(timezone.utc) - timedelta(seconds=300)
        start_clock = self.sim_clock_seconds - 300
        soc_val = max(20.0, self.battery_state.soc - 0.5)
        for i in range(30):
            pt_time = base_time + timedelta(seconds=i * 10)
            pt_clock_sec = start_clock + i * 10
            h = int((pt_clock_sec // 3600) % 24)
            m = int((pt_clock_sec % 3600) // 60)
            s = int(pt_clock_sec % 60)
            soc_val = min(self.battery_state.soc, soc_val + 0.015)
            sample = {
                "timestamp": pt_time.isoformat(),
                "sim_time": f"{h:02d}:{m:02d}:{s:02d}",
                "demand_mw": 13740.0,
                "demand_gw": 13.74,
                "supply_mw": 14200.0,
                "supply_gw": 14.20,
                "managed_mw": 13751.0,
                "solar_mw": 1990.0,
                "wind_mw": 2410.0,
                "hydro_mw": 620.0,
                "renewable_mw": 5020.0,
                "renewable_share": 36.5,
                "price": 8.20,
                "soc": round(soc_val, 2),
                "target_soc": self.ev_state.required_soc,
                "min_soc": self.ev_state.min_soc,
                "max_soc": self.ev_state.max_soc,
                "battery_power_kw": 11.0,
                "charger_power_kw": 11.0,
                "meter_import_kw": 11.0,
                "meter_export_kw": 0.0,
                "meter_net_kw": 11.0,
                "grid_stress": 42.0,
                "grid_state": "NORMAL"
            }
            self.telemetry_history.append(sample)

    def get_history(self, window_seconds: int = 3600) -> List[Dict[str, Any]]:
        """Returns the recent rolling history window."""
        with self._lock:
            all_pts = list(self.telemetry_history)
            if not window_seconds or window_seconds >= 3600:
                return all_pts
            pts_count = min(len(all_pts), max(10, int(window_seconds)))
            return all_pts[-pts_count:]

    def set_speed(self, multiplier: float):
        """Sets simulation speed (1x, 2x, 5x, 10x) per PRD Section 29, 67, 68."""
        self.speed_multiplier = max(1.0, min(10.0, float(multiplier)))

    def set_scenario(self, scenario: str):
        """Switches physical grid scenario (e.g. normal, high_load)."""
        with self._lock:
            self.scenario = scenario
            self.kptcl_source.set_scenario(scenario)
            self.iex_source.scenario = scenario

    def get_full_state(self) -> Dict[str, Any]:
        """Returns the authoritative real-time state frame (PRD Section 77)."""
        with self._lock:
            # 1. External telemetry
            grid_data = self.kptcl_source.get_telemetry()
            price_data = self.iex_source.get_telemetry()
            renewable_data = self.renewable_source.get_telemetry(total_demand_gw=grid_data["demand_gw"])

            # Status determination
            if self.data_mode == "SIMULATION":
                overall_status = "SIMULATION"
            elif grid_data["status"] == "LIVE" and price_data["status"] == "LIVE":
                overall_status = "LIVE"
            elif grid_data["status"] == "OFFLINE" or price_data["status"] == "OFFLINE":
                overall_status = "OFFLINE"
            else:
                overall_status = "STALE"

            # 2. Clocks
            self.real_time_str = datetime.now().strftime("%H:%M:%S")
            h = int((self.sim_clock_seconds // 3600) % 24)
            m = int((self.sim_clock_seconds % 3600) // 60)
            s = int(self.sim_clock_seconds % 60)
            self.sim_time_str = f"{h:02d}:{m:02d}:{s:02d}"

            # 3. Departure Urgency
            departure_eval = DepartureUrgencyCalculator.calculate(
                current_time_str=self.sim_time_str[:5],
                departure_time_str=self.ev_state.departure_time,
                current_soc=self.ev_state.soc,
                target_soc=self.ev_state.required_soc,
                capacity_kwh=self.ev_state.capacity_kwh
            )

            # 4. Managed Grid Impact (PRD Section 70, 71)
            ev_charge_kw = max(0.0, self.charger_state.power_kw) if self.charger_state.power_kw > 0 else 0.0
            v2g_export_kw = abs(self.charger_state.power_kw) if self.charger_state.power_kw < 0 else 0.0

            grid_impact = GridDemandManager.calculate_impact(
                live_grid_demand_mw=grid_data["demand_mw"],
                ev_charge_power_kw=ev_charge_kw,
                v2g_export_power_kw=v2g_export_kw
            )

            # 5. Synchronize Grid State
            self.grid_state.timestamp = datetime.now(timezone.utc).isoformat()
            self.grid_state.demand_mw = grid_data["demand_mw"]
            self.grid_state.demand_gw = grid_data["demand_gw"]
            self.grid_state.supply_mw = grid_data["supply_mw"]
            self.grid_state.supply_gw = grid_data["supply_gw"]
            self.grid_state.supply_margin_mw = grid_data["margin_mw"]
            self.grid_state.frequency_hz = grid_data["frequency_hz"]
            self.grid_state.solar_mw = renewable_data["solar_gw"] * 1000.0
            self.grid_state.wind_mw = renewable_data["wind_gw"] * 1000.0
            self.grid_state.hydro_mw = renewable_data["hydro_gw"] * 1000.0
            self.grid_state.renewable_mw = renewable_data["total_renewable_mw"]
            self.grid_state.renewable_share = renewable_data["renewable_share_pct"]
            self.grid_state.market_price = price_data["mcp_inr_per_kwh"]
            self.grid_state.market_block = price_data["current_block"]
            self.grid_state.grid_stress = self.grid_stress_engine.grid_condition
            self.grid_state.data_status = overall_status

            # 6. Synchronize Controller State (Single Source of Truth)
            self.controller_state.grid_state = self.grid_stress_engine.grid_condition
            self.controller_state.price_state = price_data["price_state"]
            self.controller_state.renewable_state = renewable_data["surplus_status"]
            self.controller_state.departure_urgency = departure_eval["departure_urgency"]
            self.controller_state.power_kw = self.charger_state.power_kw
            self.controller_state.command_kw = self.charger_state.power_kw
            self.controller_state.action = self.current_mode

            # Diagnostics dictionary for engineering panel
            diagnostics = {
                **self.grid_stress_engine.to_dict(),
                "current_mode": self.current_mode,
                "mode_dwell_time_seconds": round(self.mode_dwell_time_sec, 1),
                "minimum_charge_hold_seconds": self.minimum_charge_hold_sec,
                "minimum_v2g_hold_seconds": self.minimum_v2g_hold_sec,
                "next_control_eval_seconds": round(self.time_to_next_control_eval_sec, 1),
                "control_interval_seconds": self.control_interval_sec,
                "ramp_rate_kw_per_sec": self.charger_state.ramp_rate_kw_per_sec,
                "target_power_kw": self.charger_state.target_power_kw,
                "decision_reason": self.latest_decision.reason,
                "decision_code": self.latest_decision.reason_code
            }

            return {
                "type": "simulation_state",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sequence": self.sequence_number,
                "is_live": True,
                "simulation_time": self.sim_time_str,
                "real_time": self.real_time_str,
                "speed_multiplier": self.speed_multiplier,
                "data_mode": self.data_mode,
                "scenario": self.scenario,
                "last_tick_dt": self.last_tick_dt,
                "engine_running": self.is_running,
                "engine_paused": self.is_paused,
                "grid": {
                    **self.grid_state.to_dict(),
                    "demand_mw": self.grid_state.demand_mw,
                    "demand_gw": self.grid_state.demand_gw,
                    "supply_mw": self.grid_state.supply_mw,
                    "supply_gw": self.grid_state.supply_gw,
                    "frequency_hz": self.grid_state.frequency_hz,
                    "capacity_mw": self.grid_state.supply_mw,
                    "margin_mw": self.grid_state.supply_margin_mw,
                    "supply_margin_mw": self.grid_state.supply_margin_mw,
                    "margin_gw": round(self.grid_state.supply_margin_mw / 1000.0, 3),
                    "status": overall_status,
                    "data_status": overall_status,
                    "source": grid_data.get("source", "KPTCL_SLDC"),
                    "updated_at": self.grid_state.timestamp,
                    "impact": grid_impact,
                    "stress_score": self.grid_stress_engine.stress_score
                },
                "price": {
                    **price_data,
                    "value_inr_per_kwh": price_data.get("mcp_inr_per_kwh", 8.20),
                    "market": price_data.get("market_type", "IEX_RTM"),
                    "block": price_data.get("current_block", "18:45-19:00"),
                    "status": price_data.get("status", "LIVE"),
                    "source": price_data.get("source", "IEX_API"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "renewable": {
                    **renewable_data,
                    "solar_mw": renewable_data.get("solar_gw", 0.0) * 1000.0,
                    "wind_mw": renewable_data.get("wind_gw", 0.0) * 1000.0,
                    "hydro_mw": renewable_data.get("hydro_gw", 0.0) * 1000.0,
                    "total_mw": renewable_data.get("total_renewable_mw", 0.0),
                    "source": renewable_data.get("source", "RE_REGIONAL_POOL"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "status": renewable_data.get("status", "LIVE")
                },
                "ev": {
                    **self.ev_state.to_dict(),
                    "id": getattr(self.ev_state, "ev_id", "EV-01"),
                    "model": getattr(self.ev_state, "model", getattr(self.ev_state, "name", "Tata Nexon EV Max")),
                    "connected": self.ev_state.connected,
                    "capacity_kwh": self.ev_state.capacity_kwh,
                    "energy_kwh": round(self.battery_state.energy_kwh, 3),
                    "soc": round(self.battery_state.soc, 3),
                    "target_soc": self.ev_state.required_soc,
                    "minimum_soc": self.ev_state.min_soc,
                    "arrival_time": self.ev_state.arrival_time,
                    "departure_time": self.ev_state.departure_time,
                    "time_to_target_seconds": self.battery_state.time_to_target_seconds,
                    "departure_metrics": departure_eval
                },
                "battery": self.battery_state.to_dict(),
                "charger": {
                    **self.charger_state.to_dict(),
                    "status": "ONLINE" if self.ev_state.connected else "DISCONNECTED",
                    "mode": self.current_mode,
                    "power_kw": self.charger_state.power_kw,
                    "max_charge_kw": getattr(self.charger_state, "max_charge_kw", getattr(self.charger_state, "rated_power_kw", 22.0)),
                    "max_discharge_kw": getattr(self.charger_state, "max_discharge_kw", 11.0),
                    "efficiency": self.charger_state.efficiency
                },
                "meter": {
                    **self.meter_state,
                    "import_kw": self.meter_state.get("import_power_kw", 0.0),
                    "export_kw": self.meter_state.get("export_power_kw", 0.0),
                    "net_kw": self.meter_state.get("net_power_kw", 0.0),
                    "imported_kwh": self.meter_state.get("imported_energy_kwh", 0.0),
                    "exported_kwh": self.meter_state.get("exported_energy_kwh", 0.0),
                    "direction": self.meter_state.get("direction", "NO EV POWER FLOW")
                },
                "controller": {
                    **self.controller_state.to_dict(),
                    "action": self.current_mode,
                    "command_kw": self.charger_state.power_kw,
                    "power_kw": self.charger_state.power_kw,
                    "reason": self.latest_decision.reason,
                    "policy": "DRL_PPO_V2G",
                    "state": self.grid_stress_engine.grid_condition
                },
                "decision": self.latest_decision.to_dict(),
                "diagnostics": diagnostics,
                "next_control_eval_seconds": round(self.time_to_next_control_eval_sec, 1),
                "circuit": self.circuit_engine.get_circuit_state(),
                "topology": FixedSystemTopology.get_topology(),
                "health": {
                    "grid": {"status": grid_data.get("status", "LIVE"), "age_seconds": grid_data.get("age_seconds", 0.0), "source": grid_data.get("source", "KPTCL_SLDC")},
                    "price": {"status": price_data.get("status", "LIVE"), "age_seconds": price_data.get("age_seconds", 0.0), "source": price_data.get("source", "IEX_API")},
                    "renewable": {"status": renewable_data.get("status", "LIVE"), "age_seconds": renewable_data.get("age_seconds", 0.0), "source": renewable_data.get("source", "RE_REGIONAL_POOL")}
                }
            }

    def step(self, dt_seconds: float = 1.0) -> Dict[str, Any]:
        """
        Executes one discrete physics & control cycle (Section 18, 24, 25).
        Physics runs every second: battery energy integration & smooth power ramp.
        Control decisions evaluate every 10 seconds (or immediately on emergency safety event).
        """
        with self._lock:
            # Advance simulation clock, dwell timers & sequence counter
            self.sequence_number += 1
            self.sim_clock_seconds += dt_seconds
            dt_hours = dt_seconds / 3600.0
            self.mode_dwell_time_sec += dt_seconds
            self.time_since_last_control_eval_sec += dt_seconds
            self.time_to_next_control_eval_sec = max(
                0.0,
                self.control_interval_sec - (self.time_since_last_control_eval_sec % self.control_interval_sec)
            )

            # 0. Evolve physical external data sources with simulation time
            self.kptcl_source.update_for_sim_time(self.sim_clock_seconds, scenario=self.scenario)
            self.renewable_source.update_for_sim_time(self.sim_clock_seconds)
            self.iex_source.update_for_sim_time(self.sim_clock_seconds, scenario=self.scenario)
            self.last_tick_time = time.time()
            self.last_tick_dt = dt_seconds
            self.last_tick_iso = datetime.now(timezone.utc).isoformat()

            # 1. Ingest fresh telemetry and update Grid Stress Engine
            grid_data = self.kptcl_source.get_telemetry()
            price_data = self.iex_source.get_telemetry()
            renewable_data = self.renewable_source.get_telemetry(total_demand_gw=grid_data["demand_gw"])

            # Immediate update of authoritative grid_state so hist_point is never stale
            self.grid_state.timestamp = datetime.now(timezone.utc).isoformat()
            self.grid_state.demand_mw = grid_data["demand_mw"]
            self.grid_state.demand_gw = grid_data["demand_gw"]
            self.grid_state.supply_mw = grid_data["supply_mw"]
            self.grid_state.supply_gw = grid_data["supply_gw"]
            self.grid_state.supply_margin_mw = grid_data["margin_mw"]
            self.grid_state.frequency_hz = grid_data["frequency_hz"]
            self.grid_state.solar_mw = renewable_data["solar_gw"] * 1000.0
            self.grid_state.wind_mw = renewable_data["wind_gw"] * 1000.0
            self.grid_state.hydro_mw = renewable_data["hydro_gw"] * 1000.0
            self.grid_state.renewable_mw = renewable_data["total_renewable_mw"]
            self.grid_state.renewable_share = renewable_data["renewable_share_pct"]
            self.grid_state.market_price = price_data["mcp_inr_per_kwh"]
            self.grid_state.market_block = price_data["current_block"]

            is_v2g_active = (self.current_mode == "V2G" or self.charger_state.power_kw < -0.05)
            self.grid_stress_engine.update(
                dt_seconds=dt_seconds,
                demand_mw=grid_data["demand_mw"],
                supply_mw=grid_data["supply_mw"],
                frequency_hz=grid_data["frequency_hz"],
                is_v2g_active=is_v2g_active
            )
            self.grid_state.grid_stress = self.grid_stress_engine.grid_condition
            self.grid_state.data_status = "LIVE"

            # 2. Check Departure Feasibility
            departure_eval = DepartureUrgencyCalculator.calculate(
                current_time_str=self.sim_time_str[:5],
                departure_time_str=self.ev_state.departure_time,
                current_soc=self.ev_state.soc,
                target_soc=self.ev_state.required_soc,
                capacity_kwh=self.ev_state.capacity_kwh
            )
            dep_safe = departure_eval["departure_urgency"] < 0.65

            # 3. Determine if Control Loop Should Evaluate (Section 24, 25, 40)
            should_eval_control = (self.time_since_last_control_eval_sec >= self.control_interval_sec)
            
            # Emergency overrides or state transitions bypass 10s control interval:
            is_overcharge = self.battery_state.soc >= self.ev_state.max_soc and self.charger_state.power_kw > 0
            is_overdischarge = self.battery_state.soc <= self.ev_state.v2g_reserve and self.charger_state.power_kw < 0
            is_departure_emergency = not dep_safe and self.current_mode in ["V2G", "DISCHARGE"]
            high_load_transition = (self.grid_stress_engine.is_high_load_confirmed != getattr(self, "_last_high_load_confirmed", False))
            emergency_override = is_overcharge or is_overdischarge or is_departure_emergency or high_load_transition
            self._last_high_load_confirmed = self.grid_stress_engine.is_high_load_confirmed

            if should_eval_control or emergency_override:
                # Calculate proposed power via PPO model if available
                proposed_kw = self.latest_decision.power_kw
                ppo_action_val = 0.0

                if getattr(self, "ppo_model", None) is not None and self.ev_state.connected:
                    try:
                        cur_hour = (self.sim_clock_seconds % 86400) / 3600.0
                        t_norm = (cur_hour % 24.0) / 24.0
                        sin_t = float(math.sin(2 * math.pi * t_norm))
                        cos_t = float(math.cos(2 * math.pi * t_norm))

                        # Remaining dwell hours
                        dep_parts = self.ev_state.departure_time.split(":")
                        dep_sec = int(dep_parts[0]) * 3600 + int(dep_parts[1]) * 60
                        cur_sec = self.sim_clock_seconds % 86400
                        dwell_rem_hours = max(0.0, (dep_sec - cur_sec) / 3600.0)

                        demand_gw = grid_data["demand_gw"]
                        headroom = max(0.0, 7.0 - demand_gw) / 7.0
                        soc_norm = self.battery_state.soc / 100.0
                        target_norm = self.ev_state.required_soc / 100.0
                        deficit = max(0.0, target_norm - soc_norm)
                        freq_dev = abs(grid_data.get("frequency_hz", 50.0) - 50.0) / 0.5

                        obs = np.array([
                            soc_norm,
                            demand_gw / 7.0,
                            price_data.get("mcp_inr_per_kwh", 4.5) / 10.0,
                            sin_t,
                            cos_t,
                            min(1.0, dwell_rem_hours / 12.0),
                            target_norm,
                            1.0 if self.ev_state.connected else 0.0,
                            min(2.0, deficit),
                            headroom,
                            0.42,
                            min(1.0, freq_dev)
                        ], dtype=np.float32)

                        action, _ = self.ppo_model.predict(obs, deterministic=True)
                        ppo_action_val = float(action[0] if isinstance(action, (np.ndarray, list)) else action)

                        max_chg = getattr(self.charger_state, "max_charge_kw", 22.0)
                        max_dis = getattr(self.charger_state, "max_discharge_kw", 11.0)
                        if ppo_action_val > 0.05:
                            proposed_kw = ppo_action_val * max_chg
                        elif ppo_action_val < -0.05:
                            proposed_kw = ppo_action_val * max_dis
                        else:
                            proposed_kw = 0.0
                    except Exception as e:
                        logger.warning(f"PPO inference warning: {e}")

                decision = SafetyFilter.filter_action(
                    proposed_power_kw=proposed_kw,
                    current_soc=self.ev_state.soc,
                    min_soc=self.ev_state.min_soc,
                    max_soc=self.ev_state.max_soc,
                    target_soc=self.ev_state.required_soc,
                    departure_urgency=departure_eval["departure_urgency"],
                    grid_stress=self.grid_stress_engine.grid_condition,
                    price_state=price_data.get("price_state", "NORMAL"),
                    v2g_enabled=self.ev_state.v2g_enabled,
                    v2g_reserve=self.ev_state.v2g_reserve,
                    is_high_load_confirmed=self.grid_stress_engine.is_high_load_confirmed,
                    departure_target_safe=dep_safe,
                    grid_stress_score=self.grid_stress_engine.stress_score,
                    current_mode=self.current_mode,
                    mode_dwell_time_sec=self.mode_dwell_time_sec,
                    minimum_charge_hold_sec=self.minimum_charge_hold_sec,
                    minimum_v2g_hold_sec=self.minimum_v2g_hold_sec,
                    default_charge_kw=self.default_charge_kw,
                    default_v2g_kw=self.default_v2g_kw
                )

                if getattr(self, "ppo_model", None) is not None:
                    decision.controller = "PPO_MODEL"

                if decision.action != self.current_mode:
                    self.current_mode = decision.action
                    self.mode_dwell_time_sec = 0.0

                self.latest_decision = decision
                circuit_target_kw = self.circuit_engine.calculate_power_flow(
                    requested_power_kw=decision.power_kw,
                    max_charge_kw=getattr(self.charger_state, "max_charge_kw", 22.0),
                    max_discharge_kw=getattr(self.charger_state, "max_discharge_kw", 11.0),
                    ev_connected=self.ev_state.connected
                )
                self.charger_state.apply_target_power(circuit_target_kw)
                self.time_since_last_control_eval_sec = 0.0

            # 4. Charger Power Execution with Smooth Ramp (Section 21, 22)
            actual_power_kw = self.charger_state.step_ramp(dt_seconds=dt_seconds)
            self.circuit_engine.circuit_power_kw = actual_power_kw

            # 5. Authoritative Circuit Engine Physics (Section 3, 5, 6, 7, 16, 18, 19)
            self.circuit_engine.validate_connections(ev_connected=self.ev_state.connected)
            self.circuit_engine.update_battery(
                circuit_power_kw=actual_power_kw,
                battery_state=self.battery_state,
                ev_state=self.ev_state,
                efficiency=self.charger_state.efficiency,
                dt_seconds=dt_seconds
            )
            self.circuit_engine.update_meter(
                circuit_power_kw=actual_power_kw,
                meter_state=self.meter_state,
                dt_seconds=dt_seconds
            )
            self.circuit_engine.update_connections(circuit_power_kw=actual_power_kw)
            renewable_data = self.renewable_source.get_telemetry(total_demand_gw=grid_data["demand_gw"])
            self.circuit_engine.calculate_energy_balance(
                circuit_power_kw=actual_power_kw,
                renewable_mw=renewable_data.get("total_renewable_mw", 5020.0),
                grid_demand_mw=grid_data["demand_mw"]
            )

            # Sync controller state
            self.controller_state.command_kw = actual_power_kw
            self.controller_state.power_kw = actual_power_kw
            self.controller_state.action = self.current_mode
            self.controller_state.algorithm = "PPO (DRL-v2.5)" if getattr(self, "ppo_model", None) else "RULE_BASED"
            self.controller_state.departure_urgency = round(departure_eval["departure_urgency"], 3)
            self.controller_state.grid_state = self.grid_stress_engine.grid_condition
            self.controller_state.price_state = price_data.get("price_state", "NORMAL")

            # 6. Realistic Dynamic Charging Countdown (PRD Section 18, 19, 44, 45)
            soc_now = self.battery_state.soc
            target_soc = self.ev_state.required_soc
            max_soc = self.ev_state.max_soc
            capacity = max(10.0, self.battery_state.capacity_kwh)
            eff = max(0.5, min(1.0, self.charger_state.efficiency))

            active_chg_kw = actual_power_kw if actual_power_kw > 0.05 else self.default_charge_kw
            if soc_now < target_soc:
                needed_kwh = max(0.0, (target_soc - soc_now) / 100.0 * capacity)
                eff_charge_kw = active_chg_kw * eff
                time_target_sec = int((needed_kwh / max(0.1, eff_charge_kw)) * 3600.0)
                th = time_target_sec // 3600
                tm = (time_target_sec % 3600) // 60
                ts = time_target_sec % 60
                self.battery_state.time_to_target_seconds = time_target_sec
                self.battery_state.time_to_target_str = f"{th:02d}:{tm:02d}:{ts:02d}"

                # Est. Completion time
                est_dt = datetime.now() + timedelta(seconds=time_target_sec)
                self.battery_state.estimated_completion_time = est_dt.strftime("%H:%M:%S")

                # Departure feasibility (PRD Section 46)
                dep_parts = self.ev_state.departure_time.split(":")
                dep_sec = (int(dep_parts[0]) * 3600 + int(dep_parts[1]) * 60)
                cur_sec = self.sim_clock_seconds % 86400
                rem_to_dep_sec = dep_sec - cur_sec
                if rem_to_dep_sec > 0 and rem_to_dep_sec < time_target_sec:
                    self.battery_state.departure_feasible = False
                    self.battery_state.departure_status = "⚠ DEPARTURE TARGET AT RISK"
                else:
                    self.battery_state.departure_feasible = True
                    self.battery_state.departure_status = "✓ DEPARTURE TARGET FEASIBLE"

            elif soc_now >= target_soc:
                self.battery_state.time_to_target_seconds = 0
                self.battery_state.time_to_target_str = "00:00:00"
                self.battery_state.estimated_completion_time = "TARGET REACHED"
                self.battery_state.departure_feasible = True
                self.battery_state.departure_status = "✓ TARGET ACHIEVED"

            # Time to full
            if soc_now < max_soc:
                needed_full_kwh = max(0.0, (max_soc - soc_now) / 100.0 * capacity)
                eff_charge_kw = active_chg_kw * eff
                time_full_sec = int((needed_full_kwh / max(0.1, eff_charge_kw)) * 3600.0)
                fh = time_full_sec // 3600
                fm = (time_full_sec % 3600) // 60
                fs = time_full_sec % 60
                self.battery_state.time_to_full_seconds = time_full_sec
                self.battery_state.time_to_full_str = f"{fh:02d}:{fm:02d}:{fs:02d}"
            else:
                self.battery_state.time_to_full_seconds = 0
                self.battery_state.time_to_full_str = "00:00:00"

            # 7. Append Telemetry History Point (PRD Section 55)
            h = int((self.sim_clock_seconds // 3600) % 24)
            m = int((self.sim_clock_seconds % 3600) // 60)
            s = int(self.sim_clock_seconds % 60)
            sim_time_formatted = f"{h:02d}:{m:02d}:{s:02d}"
            self.sim_time_str = sim_time_formatted
            self.real_time_str = datetime.now().strftime("%H:%M:%S")

            hist_point = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sim_time": sim_time_formatted,
                "demand_mw": self.grid_state.demand_mw,
                "demand_gw": self.grid_state.demand_gw,
                "supply_mw": self.grid_state.supply_mw,
                "supply_gw": self.grid_state.supply_gw,
                "managed_mw": self.grid_state.demand_mw + (actual_power_kw / 1000.0),
                "solar_mw": self.grid_state.solar_mw,
                "wind_mw": self.grid_state.wind_mw,
                "hydro_mw": self.grid_state.hydro_mw,
                "renewable_mw": self.grid_state.renewable_mw,
                "price": self.grid_state.market_price,
                "soc": round(self.battery_state.soc, 3),
                "energy_kwh": round(self.battery_state.energy_kwh, 3),
                "target_soc": self.ev_state.required_soc,
                "min_soc": self.ev_state.min_soc,
                "max_soc": self.ev_state.max_soc,
                "battery_power_kw": self.battery_state.power_kw,
                "charger_power_kw": self.charger_state.power_kw,
                "meter_import_kw": self.meter_state["import_power_kw"],
                "meter_export_kw": self.meter_state["export_power_kw"],
                "meter_net_kw": self.meter_state["net_power_kw"],
                "grid_stress": self.grid_stress_engine.stress_score,
                "grid_state": self.grid_stress_engine.grid_condition
            }
            self.telemetry_history.append(hist_point)
            self.step_count += 1

            # Debug Telemetry ASCII Block Every Control Evaluation (Section 35)
            if self.time_since_last_control_eval_sec == 0.0 or (self.step_count % 10 == 0):
                debug_txt = CircuitEngine.format_debug_block(
                    sim_time_str=sim_time_formatted,
                    grid_data=grid_data,
                    price_data=price_data,
                    renewable_data=renewable_data,
                    ev_state=self.ev_state,
                    battery_state=self.battery_state,
                    controller_state=self.controller_state,
                    charger_state=self.charger_state,
                    meter_state=self.meter_state,
                    circuit_power_kw=actual_power_kw,
                    circuit_direction=self.circuit_engine.circuit_direction,
                    decision=self.latest_decision
                )
                try:
                    print(debug_txt, flush=True)
                except Exception:
                    try:
                        print(debug_txt.encode("ascii", "replace").decode("ascii"), flush=True)
                    except Exception:
                        pass

            # Section 51 Structured Console Logging:
            pwr_str = f"+{actual_power_kw:.2f}" if actual_power_kw >= 0 else f"{actual_power_kw:.2f}"
            renewable_gw = renewable_data["total_renewable_mw"] / 1000.0
            try:
                print(
                    f"[TWIN #{self.sequence_number}] dt={dt_seconds:.3f}s grid_demand={grid_data['demand_gw']:.2f}GW "
                    f"grid_supply={grid_data['supply_gw']:.2f}GW renewable={renewable_gw:.2f}GW "
                    f"price={price_data['mcp_inr_per_kwh']:.2f}INR/kWh stress={self.grid_stress_engine.stress_score:.0f} "
                    f"mode={self.current_mode} power={pwr_str}kW soc={self.battery_state.soc:.3f}% "
                    f"energy={self.battery_state.energy_kwh:.3f}kWh "
                    f"import={self.meter_state['import_power_kw']:.2f}kW export={self.meter_state['export_power_kw']:.2f}kW",
                    flush=True
                )
            except Exception:
                pass

        # Broadcast state to registered observers (outside the lock)
        full_state = self.get_full_state()
        broadcast_payload = {
            "type": "digital_twin_update",
            "sequence": self.sequence_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "simulation_time": self.sim_time_str,
            "real_time": self.real_time_str,
            "telemetry": hist_point,
            "state": full_state,
            **full_state
        }
        for cb in list(self._telemetry_callbacks):
            try:
                cb(broadcast_payload)
            except Exception:
                pass

        return full_state

    # ================= CONTINUOUS SIMULATION ENGINE CONTROLS =================
    def run(self):
        """Starts the persistent background simulation runner (PRD Section 17, 18, 28)."""
        self.is_running = True
        self.is_paused = False
        if not self._thread or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._background_runner, daemon=True)
            self._thread.start()

    def pause(self):
        self.is_paused = True

    def stop(self):
        self.is_running = False
        self.is_paused = False
        self._stop_event.set()
        self.charger_state.apply_target_power(0.0)
        self.charger_state.apply_power_command(0.0)

    def reset(self):
        self.stop()
        with self._lock:
            self.sim_clock_seconds = 18 * 3600 + 30 * 60
            self.sim_time_str = "18:30:00"
            self.ev_state.soc = 64.2
            self.battery_state.soc = 64.2
            self.battery_state.energy_kwh = 46.22
            self.current_mode = "CHARGING"
            self.mode_dwell_time_sec = 0.0
            self.time_since_last_control_eval_sec = 0.0
            self.time_to_next_control_eval_sec = 10.0
            self.charger_state.apply_target_power(11.0)
            self.charger_state.apply_power_command(11.0)
            self.latest_decision = Decision(
                action="CHARGE",
                power_kw=11.0,
                reason_code="SOC_BELOW_TARGET",
                reason="EV SOC below target; normal charging active"
            )
            self.meter_state["imported_energy_kwh"] = 0.0
            self.meter_state["exported_energy_kwh"] = 0.0
            self.meter_state["net_power_kw"] = 11.0
            self.meter_state["direction"] = "GRID → EV"
            self.step_count = 0
            self.grid_stress_engine.high_load_candidate_timer = 0.0
            self.grid_stress_engine.is_high_load_confirmed = False
            self.grid_stress_engine.recovery_timer = 0.0
            self.telemetry_history.clear()
            self._seed_telemetry_history()

    def _background_runner(self):
        """True continuous monotonic second-by-second background tick (Section 3)."""
        previous_update = time.monotonic()
        while not self._stop_event.is_set() and self.is_running:
            now = time.monotonic()
            elapsed = now - previous_update
            previous_update = now

            if not self.is_paused:
                # Actual measured wall-clock elapsed time
                dt_real = max(0.1, min(5.0, elapsed))
                dt = dt_real * self.speed_multiplier
                try:
                    self.step(dt_seconds=dt)
                except Exception as e:
                    logger.error(f"Error in continuous simulation step: {e}", exc_info=True)

            compute_duration = time.monotonic() - now
            sleep_time = max(0.05, 1.0 - compute_duration)
            time.sleep(sleep_time)


# Authoritative single simulation engine (Single Source of Truth)
from backend.simulation.unified_engine import authoritative_simulation_engine as digital_twin

