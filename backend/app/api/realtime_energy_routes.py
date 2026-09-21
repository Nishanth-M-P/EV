from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.app.database.database import get_db
from backend.app.services.realtime_energy_service import RealtimeEnergyService

class ModeUpdateRequest(BaseModel):
    mode: Optional[str] = None  # digital_twin, hardware, hybrid
    speed_multiplier: Optional[float] = None  # 1.0, 60.0, 900.0

def create_realtime_energy_router(realtime_service: RealtimeEnergyService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["Real-Time Energy & Telemetry"])

    @router.get("/energy/realtime")
    def get_realtime_energy():
        """Instantaneous power (kW) and accumulated energy (kWh) with strict conservation balance."""
        return realtime_service.get_realtime_data()

    @router.get("/energy/flow")
    def get_energy_flow():
        """Node-link topology and power intensities for the animated SVG energy flow diagram."""
        return realtime_service.get_flow_topology()

    @router.get("/energy/history")
    def get_energy_history():
        """Recent high-resolution time-series data for live streaming charts."""
        return {
            "history": realtime_service.get_history_series(),
            "count": len(realtime_service.telemetry_history)
        }

    @router.get("/energy/summary")
    def get_energy_summary():
        """Daily cumulative scorecard: solar generated/consumed, grid imported/exported, net cost."""
        state = realtime_service.sim_service.engine.get_current_state()
        cum = state.get("cumulative_energy", {})
        flow = state.get("energy_flow", {})
        return {
            "timestamp": state.get("time", "00:00"),
            "cumulative_kwh": cum,
            "flow_state": flow,
            "status": realtime_service.get_telemetry_status()
        }

    @router.get("/energy/ledger")
    def get_energy_ledger(limit: int = 50, db: Session = Depends(get_db)):
        """Immutable energy transaction ledger entries."""
        return {
            "transactions": realtime_service.get_ledger(db=db, limit=limit)
        }

    @router.get("/telemetry/status")
    def get_telemetry_status():
        """Current operating mode (Digital Twin / Hardware / Hybrid), speed multiplier, and sensor health."""
        return realtime_service.get_telemetry_status()

    @router.post("/telemetry/mode")
    def set_telemetry_mode(req: ModeUpdateRequest):
        """Switches operating mode and adjusts simulation time scaling (1x, 60x, 900x)."""
        if req.mode:
            if req.mode not in ["digital_twin", "hardware", "hybrid"]:
                raise HTTPException(status_code=400, detail="Invalid mode. Must be digital_twin, hardware, or hybrid")
            realtime_service.set_mode(req.mode)
        if req.speed_multiplier is not None:
            if req.speed_multiplier <= 0:
                raise HTTPException(status_code=400, detail="Speed multiplier must be positive")
            realtime_service.set_speed(req.speed_multiplier)
        return realtime_service.get_telemetry_status()

    @router.get("/alerts")
    def get_alerts(limit: int = 20):
        """Active operational alerts (grid stress, thermal BMS derating, conservation warnings)."""
        return {
            "alerts": realtime_service.get_recent_alerts(limit=limit)
        }

    return router
