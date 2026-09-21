import math
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.app.telemetry.source import (
    TelemetrySource,
    DigitalTwinTelemetrySource,
    HybridTelemetrySource
)
from backend.app.models.database_models import (
    TelemetrySnapshot,
    EnergyTransaction,
    ChargingSession,
    V2GSession,
    AlertEvent
)

class RealtimeEnergyService:
    """
    Central Real-Time Energy Management Service.
    Orchestrates Telemetry Sources (Digital Twin / Hardware / Hybrid),
    the Energy Conservation Balance Engine, immutable Energy Transaction Ledger,
    Charging & V2G Sessions, and Real-Time Operational Alerts.
    """

    def __init__(self, simulation_service):
        self.sim_service = simulation_service
        self.digital_twin_source = DigitalTwinTelemetrySource(self.sim_service.engine)
        self.hybrid_source = HybridTelemetrySource(self.sim_service.engine)
        
        self.current_mode: str = "digital_twin"  # digital_twin, hardware, hybrid
        self.speed_multiplier: float = 1.0       # 1.0 (1x Real-Time), 60.0 (60x Accelerated), 900.0 (900x Fast Demo)
        self.feed_in_allowed: bool = True
        
        # Recent in-memory time-series cache for rapid graph streaming (last 60 ticks)
        self.telemetry_history: List[Dict[str, Any]] = []
        self.active_charging_sessions: Dict[str, str] = {}  # ev_id -> session_id
        self.active_v2g_sessions: Dict[str, str] = {}       # ev_id -> session_id
        self.recent_alerts: List[Dict[str, Any]] = []
        
        self.snapshot_counter = 0
        self.total_ticks = 0
        self.last_tick_time = None
        self.last_balance_error_kw = 0.0

    @property
    def active_source(self) -> TelemetrySource:
        if self.current_mode == "hybrid":
            return self.hybrid_source
        return self.digital_twin_source

    def set_mode(self, mode: str):
        if mode in ["digital_twin", "hardware", "hybrid"]:
            self.current_mode = mode

    def set_speed(self, speed: float):
        self.speed_multiplier = float(speed)
        self.digital_twin_source.set_speed(self.speed_multiplier)
        self.hybrid_source.set_speed(self.speed_multiplier)

    def get_telemetry_status(self) -> Dict[str, Any]:
        return {
            "mode": self.current_mode,
            "source_label": "DIGITAL TWIN — REAL-TIME SIMULATION" if self.current_mode == "digital_twin" else (
                "HYBRID (LIVE INVERTER + DIGITAL FLEET)" if self.current_mode == "hybrid" else "LIVE HARDWARE ADAPTER"
            ),
            "speed_multiplier": self.speed_multiplier,
            "is_healthy": self.active_source.is_healthy(),
            "feed_in_allowed": self.feed_in_allowed,
            "connected_chargers": len(self.sim_service.engine.chargers),
            "connected_evs": len(self.sim_service.engine.evs)
        }

    def process_tick(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Processes one real-time second tick:
        - Calculates dynamic dt_hours based on speed multiplier
        - Steps Digital Twin (if digital_twin or hybrid mode)
        - Collects instantaneous power & accumulated kWh
        - Writes ledger entries & snapshots to DB
        - Monitors constraints and generates alerts
        """
        # Calculate simulation timestep in hours for 1 second of wall-clock time
        # 1x => 1 / 3600 h (~0.000278 h)
        # 60x => 60 / 3600 h = 1 / 60 h (~0.01667 h = 1 sim minute)
        # 900x => 900 / 3600 h = 0.25 h (15 sim minutes)
        dt_hours = self.speed_multiplier / 3600.0

        # Execute step in simulation engine
        step_data = self.sim_service.engine.step(dt_hours=dt_hours)
        telemetry = self.active_source.get_telemetry()
        
        flow = step_data.get("energy_flow", {})
        price = step_data.get("price", {}).get("current_price", 6.80)
        cum = step_data.get("cumulative_energy", {})

        self.total_ticks += 1
        self.last_tick_time = datetime.utcnow().isoformat()
        self.last_balance_error_kw = round(abs(flow.get("balance_error_kw", 0.0)), 4)

        # In-memory history buffer for high-frequency charts
        hist_entry = {
            "timestamp": telemetry["timestamp"],
            "sim_time": step_data["time"],
            "hour": step_data["hour"],
            "solar_kw": telemetry["power"]["solar_gen_kw"],
            "grid_import_kw": telemetry["power"]["grid_import_kw"],
            "grid_export_kw": telemetry["power"]["grid_export_kw"],
            "ev_charging_kw": telemetry["power"]["ev_charging_kw"],
            "v2g_discharge_kw": telemetry["power"]["v2g_discharge_kw"],
            "station_aux_kw": telemetry["power"]["station_aux_kw"],
            "system_losses_kw": telemetry["power"]["system_losses_kw"],
            "solar_share_pct": flow.get("solar_share_pct", 0.0),
            "grid_share_pct": flow.get("grid_share_pct", 0.0),
            "frequency_hz": telemetry["grid_diagnostics"]["frequency_hz"],
            "voltage_v": telemetry["grid_diagnostics"]["voltage_v"],
            "grid_stress_pct": telemetry["grid_diagnostics"]["grid_stress_pct"]
        }
        self.telemetry_history.append(hist_entry)
        if len(self.telemetry_history) > 120:
            self.telemetry_history.pop(0)

        # Check safety & alert conditions
        self._check_and_generate_alerts(step_data, telemetry, db)

        # Update Session tracking and Ledger
        self._update_sessions_and_ledger(step_data, dt_hours, price, db)

        # Periodic DB snapshot (every 5 ticks to prevent DB bloat)
        self.snapshot_counter += 1
        if db and self.snapshot_counter % 5 == 0:
            try:
                snap = TelemetrySnapshot(
                    source_mode=self.current_mode,
                    solar_power_kw=telemetry["power"]["solar_gen_kw"],
                    grid_import_power_kw=telemetry["power"]["grid_import_kw"],
                    grid_export_power_kw=telemetry["power"]["grid_export_kw"],
                    ev_charging_power_kw=telemetry["power"]["ev_charging_kw"],
                    v2g_power_kw=telemetry["power"]["v2g_discharge_kw"],
                    station_aux_power_kw=telemetry["power"]["station_aux_kw"],
                    system_losses_kw=telemetry["power"]["system_losses_kw"],
                    net_power_balance_kw=flow.get("balance_error_kw", 0.0),
                    grid_frequency_hz=telemetry["grid_diagnostics"]["frequency_hz"],
                    grid_voltage_v=telemetry["grid_diagnostics"]["voltage_v"],
                    ambient_temp_c=telemetry["grid_diagnostics"]["ambient_temp_c"],
                    solar_irradiance_w_m2=telemetry["grid_diagnostics"]["solar_irradiance_w_m2"],
                    raw_telemetry_json=hist_entry
                )
                db.add(snap)
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"[Snapshot DB Error]: {e}")

        return {
            "telemetry": telemetry,
            "step_data": step_data,
            "history_point": hist_entry,
            "status": self.get_telemetry_status()
        }

    def _check_and_generate_alerts(self, step_data: Dict[str, Any], telemetry: Dict[str, Any], db: Optional[Session]):
        grid_stress = telemetry["grid_diagnostics"]["grid_stress_pct"]
        if grid_stress > 85.0:
            self._record_alert(
                level="WARNING",
                category="GRID_OVERLOAD",
                message=f"Distribution grid feeder stress high: {grid_stress:.1f}%. Throttling charging.",
                db=db
            )

        # Check battery temperatures
        for ev in step_data.get("evs", []):
            temp = ev.get("temperature_c", 25.0)
            if temp > 43.0:
                self._record_alert(
                    level="WARNING",
                    category="THERMAL_DERATE",
                    message=f"EV {ev.get('ev_id')} battery temperature elevated ({temp:.1f}°C). BMS thermal derating active.",
                    db=db
                )

        # Check conservation
        flow = step_data.get("energy_flow", {})
        if not flow.get("is_balanced", True):
            self._record_alert(
                level="CRITICAL",
                category="CONSERVATION_FAIL",
                message=f"Energy conservation imbalance detected: error = {flow.get('balance_error_kw')} kW.",
                db=db
            )

    def _record_alert(self, level: str, category: str, message: str, db: Optional[Session]):
        # Deduplicate recent alerts in the last 15 seconds
        now = datetime.utcnow()
        for a in self.recent_alerts[-5:]:
            if a["category"] == category and (now - a["timestamp"]).total_seconds() < 15:
                return

        alert_dict = {
            "id": len(self.recent_alerts) + 1,
            "timestamp": now,
            "time_str": now.strftime("%H:%M:%S"),
            "level": level,
            "category": category,
            "message": message
        }
        self.recent_alerts.append(alert_dict)
        if len(self.recent_alerts) > 50:
            self.recent_alerts.pop(0)

        if db:
            try:
                alert_rec = AlertEvent(
                    timestamp=now,
                    level=level,
                    category=category,
                    message=message
                )
                db.add(alert_rec)
                db.commit()
            except Exception:
                db.rollback()

    def _update_sessions_and_ledger(self, step_data: Dict[str, Any], dt_hours: float, price: float, db: Optional[Session]):
        flow = step_data.get("energy_flow", {})
        sim_id = step_data.get("simulation_id")
        
        # 1. Energy Transactions to Ledger
        # Solar to EV
        solar_ev_kw = flow.get("solar_to_ev_kw", 0.0)
        if solar_ev_kw > 0.05 and db:
            try:
                d_kwh = solar_ev_kw * dt_hours
                db.add(EnergyTransaction(
                    source_category="SOLAR",
                    destination_category="EV_CHARGING",
                    power_kw=solar_ev_kw,
                    energy_kwh=round(d_kwh, 5),
                    tariff_rate_inr=0.0,
                    cost_or_revenue_inr=0.0,
                    simulation_id=sim_id
                ))
            except Exception:
                pass

        # Grid to EV
        grid_ev_kw = flow.get("grid_to_ev_kw", 0.0)
        if grid_ev_kw > 0.05 and db:
            try:
                d_kwh = grid_ev_kw * dt_hours
                cost = d_kwh * price
                db.add(EnergyTransaction(
                    source_category="GRID_IMPORT",
                    destination_category="EV_CHARGING",
                    power_kw=grid_ev_kw,
                    energy_kwh=round(d_kwh, 5),
                    tariff_rate_inr=price,
                    cost_or_revenue_inr=round(cost, 4),
                    simulation_id=sim_id
                ))
            except Exception:
                pass

        # V2G to Grid / Station
        v2g_kw = step_data.get("total_v2g_power_kw", 0.0)
        if v2g_kw > 0.05 and db:
            try:
                d_kwh = v2g_kw * dt_hours
                payout = d_kwh * price * 1.15
                db.add(EnergyTransaction(
                    source_category="V2G_DISCHARGE",
                    destination_category="GRID_EXPORT",
                    power_kw=v2g_kw,
                    energy_kwh=round(d_kwh, 5),
                    tariff_rate_inr=round(price * 1.15, 2),
                    cost_or_revenue_inr=round(-payout, 4),  # Revenue is negative cost
                    simulation_id=sim_id
                ))
            except Exception:
                pass

        if db:
            try:
                db.commit()
            except Exception:
                db.rollback()

    def get_realtime_data(self) -> Dict[str, Any]:
        """Returns comprehensive real-time payload for the Energy Dashboard."""
        state = self.sim_service.engine.get_current_state()
        telemetry = self.active_source.get_telemetry()
        cum = state.get("cumulative_energy", {})
        flow = state.get("energy_flow", {})

        return {
            "status": self.get_telemetry_status(),
            "telemetry": telemetry,
            "power_kw": {
                "solar_gen": telemetry["power"]["solar_gen_kw"],
                "grid_import": telemetry["power"]["grid_import_kw"],
                "grid_export": telemetry["power"]["grid_export_kw"],
                "ev_charging": telemetry["power"]["ev_charging_kw"],
                "v2g_discharge": telemetry["power"]["v2g_discharge_kw"],
                "station_aux": telemetry["power"]["station_aux_kw"],
                "system_losses": telemetry["power"]["system_losses_kw"],
                "net_station_load": round(telemetry["power"]["ev_charging_kw"] + telemetry["power"]["station_aux_kw"] - telemetry["power"]["v2g_discharge_kw"], 2)
            },
            "cumulative_kwh_today": {
                "solar_generated": cum.get("solar_gen_kwh_today", 0.0),
                "solar_consumed": cum.get("solar_used_kwh_today", 0.0),
                "grid_imported": cum.get("grid_import_kwh_today", 0.0),
                "grid_exported": cum.get("grid_export_kwh_today", 0.0),
                "ev_charged": cum.get("ev_charging_kwh_today", 0.0),
                "v2g_discharged": cum.get("v2g_discharge_kwh_today", 0.0),
                "station_aux": cum.get("station_aux_kwh_today", 0.0),
                "losses": cum.get("system_losses_kwh_today", 0.0)
            },
            "financials_today_inr": {
                "import_cost": cum.get("total_import_cost_inr", 0.0),
                "export_revenue": cum.get("total_export_revenue_inr", 0.0),
                "v2g_revenue": cum.get("total_v2g_payout_inr", 0.0),
                "net_cost": cum.get("net_energy_cost_inr", 0.0)
            },
            "conservation_check": {
                "total_in_kw": flow.get("total_in_kw", 0.0),
                "total_out_kw": flow.get("total_out_kw", 0.0),
                "balance_error_kw": flow.get("balance_error_kw", 0.0),
                "is_balanced": flow.get("is_balanced", True)
            },
            "attribution": {
                "solar_share_pct": flow.get("solar_share_pct", 0.0),
                "grid_share_pct": flow.get("grid_share_pct", 0.0),
                "summary": flow.get("flow_summary", "Operational")
            },
            "evs": state.get("evs", []),
            "diagnostics": telemetry.get("grid_diagnostics", {})
        }

    def get_flow_topology(self) -> Dict[str, Any]:
        """Provides directional graph topology and particle flow intensity for SVG animation."""
        state = self.sim_service.engine.get_current_state()
        flow = state.get("energy_flow", {})
        
        nodes = [
            {"id": "solar", "label": "Solar PV Array", "kw": flow.get("solar_to_ev_kw", 0.0) + flow.get("solar_to_grid_kw", 0.0) + flow.get("solar_to_aux_kw", 0.0)},
            {"id": "grid", "label": "Primary Utility Grid", "kw": flow.get("grid_import_kw", 0.0)},
            {"id": "bus", "label": "Microgrid AC Bus", "kw": flow.get("total_in_kw", 0.0)},
            {"id": "station", "label": "Station Aux & Losses", "kw": flow.get("station_aux_kw", 6.0) + flow.get("system_losses_kw", 0.5)},
            {"id": "ev_chargers", "label": "EV Charging Fleet", "kw": state.get("total_charging_power_kw", 0.0)},
            {"id": "v2g_feed", "label": "V2G Storage Supply", "kw": state.get("total_v2g_power_kw", 0.0)}
        ]

        links = [
            {"from": "solar", "to": "bus", "kw": round(flow.get("solar_to_ev_kw", 0.0) + flow.get("solar_to_grid_kw", 0.0) + flow.get("solar_to_aux_kw", 0.0), 2), "active": (flow.get("solar_to_ev_kw", 0.0) + flow.get("solar_to_grid_kw", 0.0) > 0.05)},
            {"from": "grid", "to": "bus", "kw": round(flow.get("grid_import_kw", 0.0), 2), "active": (flow.get("grid_import_kw", 0.0) > 0.05)},
            {"from": "bus", "to": "grid", "kw": round(flow.get("grid_export_kw", 0.0), 2), "active": (flow.get("grid_export_kw", 0.0) > 0.05)},
            {"from": "bus", "to": "ev_chargers", "kw": round(state.get("total_charging_power_kw", 0.0), 2), "active": (state.get("total_charging_power_kw", 0.0) > 0.05)},
            {"from": "ev_chargers", "to": "bus", "kw": round(state.get("total_v2g_power_kw", 0.0), 2), "active": (state.get("total_v2g_power_kw", 0.0) > 0.05)},
            {"from": "bus", "to": "station", "kw": round(flow.get("station_aux_kw", 6.0) + flow.get("system_losses_kw", 0.5), 2), "active": True}
        ]

        return {
            "summary": flow.get("flow_summary", "Operational"),
            "nodes": nodes,
            "links": links
        }

    def get_history_series(self) -> List[Dict[str, Any]]:
        return self.telemetry_history

    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(reversed(self.recent_alerts[-limit:]))

    def get_ledger(self, db: Session, limit: int = 50) -> List[Dict[str, Any]]:
        transactions = db.query(EnergyTransaction).order_by(EnergyTransaction.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": t.id,
                "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S") if t.timestamp else "",
                "source": t.source_category,
                "destination": t.destination_category,
                "power_kw": round(t.power_kw, 2),
                "energy_kwh": round(t.energy_kwh, 4),
                "tariff_rate_inr": round(t.tariff_rate_inr, 2),
                "cost_or_revenue_inr": round(t.cost_or_revenue_inr, 2)
            }
            for t in transactions
        ]
