from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.app.schemas.simulation_schema import SimulationConfigSchema, BenchmarkResponse, ReportResponse
from backend.app.database.database import get_db

class CreateScenarioRequest(BaseModel):
    name: Optional[str] = "Custom Scenario"
    duration_hours: Optional[float] = 24.0
    timestep_minutes: Optional[int] = 15
    grid_capacity_kw: Optional[float] = 100.0
    solar_capacity_kw: Optional[float] = 40.0
    cloud_factor: Optional[float] = 1.0
    evs: Optional[List[Dict[str, Any]]] = None
    pricing: Optional[Dict[str, Any]] = None
    ai_enabled: Optional[bool] = True
    v2g_enabled: Optional[bool] = True

def create_simulation_router(sim_service, broadcast_fn):
    router = APIRouter(prefix="/api/simulation", tags=["Simulation Controls & Lab"])

    @router.get("/status")
    def get_simulation_status():
        engine = sim_service.engine
        return {
            "simulation_id": engine.simulation_id,
            "status": engine.status,
            "is_running": sim_service.is_running,
            "current_hour": engine.current_hour,
            "timestep_minutes": engine.timestep_minutes,
            "tick_interval_seconds": sim_service.tick_interval_seconds,
            "history_count": len(engine.history),
            "fleet_count": len(engine.evs)
        }

    @router.get("/current/state")
    def get_current_state():
        return sim_service.engine.get_current_state()

    @router.get("/history")
    def get_simulation_history(db: Session = Depends(get_db)):
        return sim_service.get_history(db)

    @router.post("/create")
    async def create_scenario(req: CreateScenarioRequest, db: Session = Depends(get_db)):
        state = sim_service.create_custom_scenario(
            name=req.name or "Custom Scenario",
            duration_hours=req.duration_hours or 24.0,
            timestep_minutes=req.timestep_minutes or 15,
            grid_capacity_kw=req.grid_capacity_kw or 100.0,
            solar_capacity_kw=req.solar_capacity_kw or 40.0,
            cloud_factor=req.cloud_factor if req.cloud_factor is not None else 1.0,
            evs_config=req.evs,
            pricing_config=req.pricing,
            ai_enabled=req.ai_enabled if req.ai_enabled is not None else True,
            v2g_enabled=req.v2g_enabled if req.v2g_enabled is not None else True
        )
        await broadcast_fn({"type": "SIM_RESET", "hour": 0.0})
        return {"status": "created", "simulation_id": sim_service.engine.simulation_id, "state": state}

    @router.post("/start")
    async def start_simulation():
        was_running = sim_service.is_running
        sim_service.start()
        await broadcast_fn({"type": "SIM_STARTED"})
        return {
            "status": "started",
            "engine_status": "already_running" if was_running else "running",
            "mode": "REAL_TIME",
            "speed": getattr(sim_service, "speed_multiplier", 1.0),
            "is_running": True
        }

    @router.post("/pause")
    async def pause_simulation():
        sim_service.pause()
        await broadcast_fn({"type": "SIM_PAUSED"})
        return {"status": "paused", "is_running": False}

    @router.post("/resume")
    async def resume_simulation():
        sim_service.start()
        await broadcast_fn({"type": "SIM_STARTED"})
        return {"status": "resumed", "is_running": True}

    @router.post("/stop")
    async def stop_simulation(db: Session = Depends(get_db)):
        sim_service.stop()
        sim_service.persist_to_db(db)
        await broadcast_fn({"type": "SIM_STOPPED"})
        return {"status": "stopped", "is_running": False}

    @router.post("/reset")
    async def reset_simulation():
        sim_service.reset()
        await broadcast_fn({"type": "SIM_RESET", "hour": 0.0})
        return {"status": "reset", "current_hour": 0.0}

    @router.post("/step")
    async def step_simulation(db: Session = Depends(get_db)):
        step_data = sim_service.step()
        await broadcast_fn({"type": "SIM_STEP", "data": step_data})
        return step_data

    @router.post("/run-24h")
    async def run_24h_simulation(db: Session = Depends(get_db)):
        results = sim_service.run_24h_cycle(db)
        await broadcast_fn({"type": "SIM_COMPLETED", "data": results})
        return results

    @router.post("/configure")
    async def configure_simulation(config: SimulationConfigSchema):
        state = sim_service.configure(
            duration_hours=config.duration_hours,
            timestep_minutes=config.timestep_minutes,
            grid_capacity_kw=config.grid_capacity_kw,
            solar_capacity_kw=config.solar_capacity_kw,
            cloud_factor=config.cloud_factor,
            num_evs=config.num_evs,
            scenario_name=config.name or "Custom Simulation"
        )
        await broadcast_fn({"type": "SIM_RESET", "hour": 0.0})
        return {"status": "configured", "state": state}

    @router.post("/demo")
    async def launch_smart_grid_demo():
        state = sim_service.configure(
            duration_hours=24.0,
            timestep_minutes=15,
            grid_capacity_kw=100.0,
            solar_capacity_kw=40.0,
            cloud_factor=1.0,
            num_evs=5,
            scenario_name="Smart Grid Peak-Shaving Demo"
        )
        sim_service.start()
        await broadcast_fn({"type": "SIM_STARTED"})
        return {"status": "demo_started", "scenario": "Smart Grid Peak-Shaving Demo", "state": state}

    @router.get("/benchmark", response_model=BenchmarkResponse)
    def run_benchmark():
        return sim_service.run_benchmark()

    @router.get("/report")
    def generate_report(db: Session = Depends(get_db)):
        report = sim_service.generate_report()
        sim_service.persist_to_db(db)
        return report

    @router.get("/presets")
    def list_scenario_presets():
        return sim_service.get_presets()

    @router.post("/presets/{preset_key}")
    async def load_scenario_preset(preset_key: str):
        state = sim_service.load_preset(preset_key)
        await broadcast_fn({"type": "SIM_RESET", "hour": 0.0})
        return {"status": "preset_loaded", "preset": preset_key, "state": state}

    @router.get("/export/csv")
    def export_csv_data():
        csv_text = sim_service.export_experiment_csv()
        sim_id = sim_service.engine.simulation_id
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=gridwise_experiment_{sim_id[:8]}.csv"}
        )

    # Parameterized route aliases for /api/simulation/{id}/*
    @router.get("/{sim_id}/state")
    def get_state_by_id(sim_id: str):
        if sim_id == sim_service.engine.simulation_id or sim_id == "current":
            return sim_service.engine.get_current_state()
        raise HTTPException(status_code=404, detail="Simulation ID not currently active")

    @router.get("/{sim_id}/results")
    def get_results_by_id(sim_id: str, db: Session = Depends(get_db)):
        return sim_service.get_simulation_results(sim_id, db)

    @router.get("/{sim_id}")
    def get_simulation_by_id(sim_id: str, db: Session = Depends(get_db)):
        return sim_service.get_simulation_results(sim_id, db)

    @router.post("/{sim_id}/start")
    async def start_sim_by_id(sim_id: str):
        return await start_simulation()

    @router.post("/{sim_id}/pause")
    async def pause_sim_by_id(sim_id: str):
        return await pause_simulation()

    @router.post("/{sim_id}/resume")
    async def resume_sim_by_id(sim_id: str):
        return await resume_simulation()

    @router.post("/{sim_id}/step")
    async def step_sim_by_id(sim_id: str, db: Session = Depends(get_db)):
        return await step_simulation(db)

    @router.post("/{sim_id}/stop")
    async def stop_sim_by_id(sim_id: str, db: Session = Depends(get_db)):
        return await stop_simulation(db)

    @router.post("/{sim_id}/reset")
    async def reset_sim_by_id(sim_id: str):
        return await reset_simulation()

    return router

