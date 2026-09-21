from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.database.database import get_db
from backend.app.models.database_models import SystemSetting

DEFAULT_SETTINGS = {
    "simulation": {
        "default_timestep_minutes": 15,
        "default_duration_hours": 24.0,
        "auto_step_cadence_seconds": 1.0,
    },
    "safety_limits": {
        "min_soc_pct": 20.0,
        "max_soc_pct": 95.0,
        "target_soc_pct": 85.0,
        "departure_urgency_buffer_hours": 2.0
    },
    "grid_limits": {
        "default_feeder_capacity_kw": 100.0,
        "feeder_peak_threshold_kw": 85.0,
        "high_stress_pct": 85.0,
        "critical_stress_pct": 95.0
    },
    "v2g_settings": {
        "enable_v2g": True,
        "min_discharge_soc_pct": 35.0,
        "v2g_revenue_multiplier": 0.85,
        "max_discharge_rate_c": 0.5
    },
    "ai_settings": {
        "enable_safety_constraints": True,
        "prioritize_solar_self_consumption": True,
        "peak_shaving_weight": 2.0,
        "departure_urgency_weight": 3.0
    }
}

class UpdateSettingsRequest(BaseModel):
    simulation: Optional[Dict[str, Any]] = None
    safety_limits: Optional[Dict[str, Any]] = None
    grid_limits: Optional[Dict[str, Any]] = None
    v2g_settings: Optional[Dict[str, Any]] = None
    ai_settings: Optional[Dict[str, Any]] = None

def create_settings_router(sim_service):
    router = APIRouter(prefix="/api/settings", tags=["System Settings"])

    @router.get("")
    def get_settings(db: Session = Depends(get_db)) -> Dict[str, Any]:
        rec = db.query(SystemSetting).filter(SystemSetting.key == "platform_configuration").first()
        if rec and isinstance(rec.value, dict):
            # Merge stored settings with defaults for missing keys
            merged = {**DEFAULT_SETTINGS, **rec.value}
            return merged
        return DEFAULT_SETTINGS

    @router.post("")
    def update_settings(req: UpdateSettingsRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
        rec = db.query(SystemSetting).filter(SystemSetting.key == "platform_configuration").first()
        current = rec.value if (rec and isinstance(rec.value, dict)) else DEFAULT_SETTINGS.copy()

        req_dict = req.model_dump(exclude_unset=True)
        for section, values in req_dict.items():
            if values is not None:
                if section not in current:
                    current[section] = {}
                current[section].update(values)

        if not rec:
            rec = SystemSetting(
                key="platform_configuration",
                value=current,
                description="Global GridWise AI platform and simulator settings"
            )
            db.add(rec)
        else:
            rec.value = current

        db.commit()

        # Safely apply to active simulator engine if applicable
        if "simulation" in current and "default_timestep_minutes" in current["simulation"]:
            ts = current["simulation"]["default_timestep_minutes"]
            if ts in [1, 5, 15, 60]:
                sim_service.engine.timestep_minutes = int(ts)
                sim_service.engine.timestep_hours = ts / 60.0

        return {"status": "success", "settings": current}

    return router
