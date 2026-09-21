from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from backend.app.schemas.ev_schema import EVCreate, EVResponse, EVOverrideRequest

def create_ev_router(sim_service):
    router = APIRouter(prefix="/api/evs", tags=["EV Fleet"])

    @router.get("", response_model=Dict[str, Any])
    def list_evs():
        return {
            "evs": [ev.to_dict() for ev in sim_service.engine.evs.values()],
            "overrides": sim_service.engine.manual_overrides
        }

    @router.post("", status_code=201)
    def add_ev(payload: EVCreate):
        try:
            ev = sim_service.engine.evs
            new_ev = sim_service.engine.ev_service.add_ev(payload.dict()) if hasattr(sim_service.engine, "ev_service") else None
            # Also add directly into engine.evs if ev_service not bound
            from backend.app.simulator.ev_simulator import EVDigitalTwin
            import uuid
            ev_id = payload.ev_id or f"EV-{uuid.uuid4().hex[:4].upper()}"
            twin = EVDigitalTwin(
                ev_id=ev_id,
                name=payload.name,
                battery_capacity_kwh=payload.battery_capacity_kwh,
                current_soc=payload.current_soc,
                minimum_soc=payload.minimum_soc,
                maximum_soc=payload.maximum_soc,
                target_soc=payload.target_soc,
                arrival_time=payload.arrival_time,
                departure_time=payload.departure_time,
                max_charge_power_kw=payload.max_charge_power_kw,
                max_discharge_power_kw=payload.max_discharge_power_kw,
                charging_efficiency=payload.charging_efficiency,
                discharging_efficiency=payload.discharging_efficiency,
                battery_health=payload.battery_health
            )
            sim_service.engine.evs[ev_id] = twin
            return {"status": "success", "ev": twin.to_dict()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/{ev_id}")
    def get_ev(ev_id: str):
        ev = sim_service.engine.evs.get(ev_id)
        if not ev:
            raise HTTPException(status_code=404, detail="EV not found")
        return ev.to_dict()

    @router.delete("/{ev_id}")
    def delete_ev(ev_id: str):
        if ev_id in sim_service.engine.evs:
            del sim_service.engine.evs[ev_id]
            sim_service.engine.manual_overrides.pop(ev_id, None)
            return {"status": "deleted", "ev_id": ev_id}
        raise HTTPException(status_code=404, detail="EV not found")

    @router.post("/{ev_id}/override")
    def set_ev_override(ev_id: str, payload: EVOverrideRequest):
        if ev_id not in sim_service.engine.evs:
            raise HTTPException(status_code=404, detail="EV not found")
        action = payload.action
        sim_service.engine.set_override(ev_id, action)
        return {"status": "updated", "ev_id": ev_id, "override": action}

    return router
