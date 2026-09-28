"""
GridWise AI - Fixed Twin REST API Endpoints
Implements all required PRD Section 76 endpoints.
"""

from fastapi import APIRouter, Body
from typing import Dict, Any, Optional

from backend.simulation.engine import digital_twin
from backend.topology import FixedSystemTopology

router = APIRouter(prefix="/api", tags=["Fixed Real-Time V2G Digital Twin"])

@router.get("/realtime/grid")
def get_realtime_grid():
    return digital_twin.kptcl_source.get_telemetry()

@router.get("/realtime/price")
def get_realtime_price():
    return digital_twin.iex_source.get_telemetry()

@router.get("/realtime/renewables")
def get_realtime_renewables():
    return digital_twin.renewable_source.get_telemetry()

@router.get("/realtime/state")
def get_realtime_state():
    return digital_twin.get_full_state()

@router.get("/ev")
def get_ev_state():
    return digital_twin.ev_state.to_dict()

@router.put("/ev")
def update_ev_state(payload: Dict[str, Any] = Body(...)):
    """Allows parameter edits during EDIT mode (PRD Section 21, 59)."""
    ev = digital_twin.ev_state
    if "arrival_time" in payload:
        ev.arrival_time = str(payload["arrival_time"])
    if "departure_time" in payload:
        ev.departure_time = str(payload["departure_time"])
    if "capacity_kwh" in payload:
        ev.capacity_kwh = float(payload["capacity_kwh"])
        digital_twin.battery_state.capacity_kwh = ev.capacity_kwh
    if "soc" in payload:
        ev.soc = float(payload["soc"])
        digital_twin.battery_state.soc = ev.soc
        digital_twin.battery_state.energy_kwh = (ev.soc / 100.0) * ev.capacity_kwh
    if "required_soc" in payload:
        ev.required_soc = float(payload["required_soc"])
    if "min_soc" in payload:
        ev.min_soc = float(payload["min_soc"])
    if "max_soc" in payload:
        ev.max_soc = float(payload["max_soc"])
    if "v2g_enabled" in payload:
        ev.v2g_enabled = bool(payload["v2g_enabled"])
    if "v2g_reserve" in payload:
        ev.v2g_reserve = float(payload["v2g_reserve"])
    if "charge_limit_kw" in payload:
        ev.charge_limit_kw = float(payload["charge_limit_kw"])
    if "discharge_limit_kw" in payload:
        ev.discharge_limit_kw = float(payload["discharge_limit_kw"])
    return {"status": "updated", "ev": ev.to_dict()}

@router.get("/battery")
def get_battery_state():
    return digital_twin.battery_state.to_dict()

@router.get("/charger")
def get_charger_state():
    return digital_twin.charger_state.to_dict()

@router.get("/controller")
def get_controller_state():
    return digital_twin.controller_state.to_dict()

@router.get("/meter")
def get_meter_state():
    return digital_twin.meter_state

@router.post("/simulation/run")
def run_simulation():
    digital_twin.run()
    return {"status": "running"}

@router.post("/simulation/pause")
def pause_simulation():
    digital_twin.pause()
    return {"status": "paused"}

@router.post("/simulation/stop")
def stop_simulation():
    digital_twin.stop()
    return {"status": "stopped"}

@router.post("/simulation/reset")
def reset_simulation():
    digital_twin.reset()
    return {"status": "reset", "state": digital_twin.get_full_state()}

@router.get("/topology")
def get_topology():
    return FixedSystemTopology.get_topology()

@router.get("/config")
def get_config():
    return {
        "topology": FixedSystemTopology.get_topology(),
        "ev": digital_twin.ev_state.to_dict(),
        "charger": digital_twin.charger_state.to_dict(),
        "data_mode": digital_twin.data_mode,
        "max_charge_rate_kw": digital_twin.charger_state.rated_power_kw,
        "max_v2g_rate_kw": digital_twin.charger_state.rated_power_kw,
        "v2g_min_soc": digital_twin.ev_state.v2g_reserve,
        "max_soc": digital_twin.ev_state.max_soc,
        "v2g_entry_stress": digital_twin.grid_stress_engine.v2g_entry_stress,
        "v2g_exit_stress": digital_twin.grid_stress_engine.v2g_exit_stress,
        "high_load_confirmation_time_sec": digital_twin.grid_stress_engine.high_load_confirmation_time_sec,
        "v2g_recovery_time_sec": digital_twin.grid_stress_engine.v2g_recovery_time_sec,
        "minimum_charge_hold_sec": digital_twin.minimum_charge_hold_sec,
        "minimum_v2g_hold_sec": digital_twin.minimum_v2g_hold_sec,
        "control_interval_sec": digital_twin.control_interval_sec,
        "ramp_rate_kw_per_sec": digital_twin.charger_state.ramp_rate_kw_per_sec
    }

@router.put("/config")
def update_config(payload: Dict[str, Any] = Body(...)):
    """Applies parameters updated in EDIT mode."""
    if "data_mode" in payload:
        digital_twin.data_mode = payload["data_mode"]
    if "ev" in payload:
        update_ev_state(payload["ev"])
    if "charger" in payload:
        chg = payload["charger"]
        if "rated_power_kw" in chg:
            digital_twin.charger_state.rated_power_kw = float(chg["rated_power_kw"])
        if "efficiency" in chg:
            digital_twin.charger_state.efficiency = float(chg["efficiency"])
        if "ramp_rate_kw_per_sec" in chg:
            digital_twin.charger_state.ramp_rate_kw_per_sec = float(chg["ramp_rate_kw_per_sec"])
    if "max_charge_rate_kw" in payload:
        digital_twin.charger_state.rated_power_kw = float(payload["max_charge_rate_kw"])
        digital_twin.ev_state.charge_limit_kw = float(payload["max_charge_rate_kw"])
    if "max_v2g_rate_kw" in payload:
        digital_twin.ev_state.discharge_limit_kw = float(payload["max_v2g_rate_kw"])
    if "v2g_min_soc" in payload:
        digital_twin.ev_state.v2g_reserve = float(payload["v2g_min_soc"])
    if "max_soc" in payload:
        digital_twin.ev_state.max_soc = float(payload["max_soc"])
    if "v2g_entry_stress" in payload:
        digital_twin.grid_stress_engine.v2g_entry_stress = float(payload["v2g_entry_stress"])
    if "v2g_exit_stress" in payload:
        digital_twin.grid_stress_engine.v2g_exit_stress = float(payload["v2g_exit_stress"])
    if "high_load_confirmation_time_sec" in payload:
        digital_twin.grid_stress_engine.high_load_confirmation_time_sec = float(payload["high_load_confirmation_time_sec"])
    if "v2g_recovery_time_sec" in payload:
        digital_twin.grid_stress_engine.v2g_recovery_time_sec = float(payload["v2g_recovery_time_sec"])
    if "minimum_charge_hold_sec" in payload:
        digital_twin.minimum_charge_hold_sec = float(payload["minimum_charge_hold_sec"])
    if "minimum_v2g_hold_sec" in payload:
        digital_twin.minimum_v2g_hold_sec = float(payload["minimum_v2g_hold_sec"])
    if "control_interval_sec" in payload:
        digital_twin.control_interval_sec = float(payload["control_interval_sec"])
    if "ramp_rate_kw_per_sec" in payload:
        digital_twin.charger_state.ramp_rate_kw_per_sec = float(payload["ramp_rate_kw_per_sec"])
    if "price" in payload:
        prc = payload["price"]
        if "mcp_inr_per_kwh" in prc:
            digital_twin.iex_source.set_parameters(mcp=float(prc["mcp_inr_per_kwh"]))
    if "grid" in payload:
        grd = payload["grid"]
        if "demand_gw" in grd:
            digital_twin.kptcl_source.set_parameters(demand_gw=float(grd["demand_gw"]))
    
    config_dict = {
        "max_charge_rate_kw": digital_twin.charger_state.rated_power_kw,
        "max_v2g_rate_kw": digital_twin.ev_state.discharge_limit_kw,
        "v2g_min_soc": digital_twin.ev_state.v2g_reserve,
        "max_soc": digital_twin.ev_state.max_soc,
        "v2g_entry_stress": digital_twin.grid_stress_engine.v2g_entry_stress,
        "v2g_exit_stress": digital_twin.grid_stress_engine.v2g_exit_stress,
        "high_load_confirmation_time_sec": digital_twin.grid_stress_engine.high_load_confirmation_time_sec,
        "v2g_recovery_time_sec": digital_twin.grid_stress_engine.v2g_recovery_time_sec,
        "minimum_charge_hold_sec": digital_twin.minimum_charge_hold_sec,
        "minimum_v2g_hold_sec": digital_twin.minimum_v2g_hold_sec,
        "control_interval_sec": digital_twin.control_interval_sec,
        "ramp_rate_kw_per_sec": digital_twin.charger_state.ramp_rate_kw_per_sec,
        "ev": digital_twin.ev_state.to_dict(),
        "charger": digital_twin.charger_state.to_dict(),
        "data_mode": digital_twin.data_mode
    }
    return {"status": "applied", "config": config_dict, "state": digital_twin.get_full_state()}

@router.get("/decisions")
def get_decisions():
    return [digital_twin.latest_decision.to_dict()]

@router.get("/telemetry")
def get_telemetry():
    return digital_twin.get_full_state()

@router.get("/telemetry/history")
def get_telemetry_history(window: int = 3600):
    """Returns rolling time-series telemetry buffer for instant chart population (PRD Section 55 & 56)."""
    return {
        "status": "success",
        "window_seconds": window,
        "history": digital_twin.get_history(window_seconds=window)
    }

@router.post("/simulation/speed")
def set_simulation_speed(payload: Dict[str, Any] = Body(...)):
    """Sets simulation speed (1x, 2x, 5x, 10x) per PRD Section 29, 67, 68."""
    speed = float(payload.get("speed", 1.0))
    digital_twin.set_speed(speed)
    return {"status": "success", "speed_multiplier": digital_twin.speed_multiplier}
