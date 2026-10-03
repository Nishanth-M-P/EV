import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from backend.app.schemas.ev_schema import EVCreate, EVResponse, EVOverrideRequest

logger = logging.getLogger("gridwise.ev_routes")

def create_ev_router(sim_service):
    router = APIRouter(prefix="/api/evs", tags=["EV Fleet"])

    @router.get("", response_model=Dict[str, Any])
    def list_evs():
        fleet = sim_service.engine.fleet_manager.fleet if hasattr(sim_service.engine, "fleet_manager") else getattr(sim_service.engine, "evs", {})
        res_list = []
        cur_h = getattr(sim_service.engine, "current_hour", 12.0)
        for ev in fleet.values():
            if hasattr(ev, "to_dict"):
                try:
                    res_list.append(ev.to_dict(current_hour=cur_h))
                except TypeError:
                    res_list.append(ev.to_dict())
        return {
            "evs": res_list,
            "overrides": getattr(sim_service.engine, "manual_overrides", {})
        }

    @router.post("", status_code=201)
    def add_ev(payload: EVCreate):
        try:
            ev_dict = payload.dict()
            if not ev_dict.get("ev_id"):
                import uuid
                ev_dict["ev_id"] = f"EV-{uuid.uuid4().hex[:4].upper()}"

            # Guarantee newly added battery is fully connected and ready to charge
            ev_dict["connected"] = True
            ev_dict["v2g_enabled"] = True

            cur_h = getattr(sim_service.engine, "current_hour", 12.0)
            dep_val = float(ev_dict.get("departure_time", 18.0))
            if dep_val <= cur_h:
                ev_dict["departure_time"] = 24.0
            arr_val = float(ev_dict.get("arrival_time", 8.0))
            if arr_val > cur_h:
                ev_dict["arrival_time"] = 0.0

            # Add to authoritative fleet manager
            if hasattr(sim_service.engine, "fleet_manager"):
                new_ev = sim_service.engine.fleet_manager.add_ev(ev_dict)
            else:
                new_ev = sim_service.engine.ev_service.add_ev(ev_dict)

            # Ensure battery is connected and in active CHARGING state
            new_ev.connected = True
            target = getattr(new_ev, "target_soc", 80.0)
            if new_ev.soc < target:
                new_ev.charging_state = "CHARGING"
            if hasattr(new_ev, "is_connected"):
                new_ev.is_connected = True

            if hasattr(sim_service.engine, "fleet_persisted_decisions"):
                from backend.simulation.unified_engine import SafetyDecision
                import numpy as np
                chg_power = getattr(new_ev, "max_charge_kw", 7.4)
                sim_service.engine.fleet_persisted_decisions[new_ev.ev_id] = {
                    "proposed_action": "CHARGE",
                    "proposed_kw": chg_power,
                    "action_index": 1,
                    "probabilities": {"CHARGE": 1.0, "IDLE": 0.0, "DISCHARGE": 0.0},
                    "confidence": 1.0,
                    "state_value": 0.0,
                    "safety_decision": SafetyDecision(
                        approved=True,
                        raw_action="CHARGE",
                        final_action="CHARGE",
                        power_kw=chg_power,
                        reason_code="ACTIVE_CHARGE",
                        reason=f"Newly added battery twin {new_ev.ev_id} active charging",
                        corrective_action="None"
                    ),
                    "validated_power_kw": chg_power,
                    "obs_19d": np.zeros(19, dtype=np.float32),
                    "obs_raw": {}
                }

            logger.info(f"Successfully added battery twin to circuit: {new_ev.ev_id} ({new_ev.capacity_kwh} kWh, SOC={new_ev.soc}%)")
            
            try:
                ret_dict = new_ev.to_dict(current_hour=cur_h)
            except TypeError:
                ret_dict = new_ev.to_dict()
                
            return {"status": "success", "ev": ret_dict}
        except Exception as e:
            logger.error(f"Error adding EV to fleet: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/{ev_id}")
    def get_ev(ev_id: str):
        fleet = sim_service.engine.fleet_manager.fleet if hasattr(sim_service.engine, "fleet_manager") else getattr(sim_service.engine, "evs", {})
        ev = fleet.get(ev_id)
        if not ev:
            raise HTTPException(status_code=404, detail="EV not found")
        cur_h = getattr(sim_service.engine, "current_hour", 12.0)
        try:
            return ev.to_dict(current_hour=cur_h)
        except TypeError:
            return ev.to_dict()

    @router.delete("/{ev_id}")
    def delete_ev(ev_id: str):
        fleet = sim_service.engine.fleet_manager.fleet if hasattr(sim_service.engine, "fleet_manager") else getattr(sim_service.engine, "evs", {})
        if ev_id in fleet:
            del fleet[ev_id]
            if hasattr(sim_service.engine, "fleet_persisted_decisions"):
                sim_service.engine.fleet_persisted_decisions.pop(ev_id, None)
            if hasattr(sim_service.engine, "manual_overrides"):
                sim_service.engine.manual_overrides.pop(ev_id, None)
            return {"status": "deleted", "ev_id": ev_id}
        raise HTTPException(status_code=404, detail="EV not found")

    @router.post("/{ev_id}/action")
    @router.post("/{ev_id}/override")
    def set_ev_override(ev_id: str, payload: EVOverrideRequest):
        fleet = sim_service.engine.fleet_manager.fleet if hasattr(sim_service.engine, "fleet_manager") else getattr(sim_service.engine, "evs", {})
        if ev_id not in fleet:
            raise HTTPException(status_code=404, detail="EV not found")
        action = payload.action
        sim_service.engine.manual_overrides[ev_id] = action
        return {"status": "updated", "ev_id": ev_id, "override": action}

    return router

