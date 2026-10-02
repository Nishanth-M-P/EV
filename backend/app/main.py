import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.database.database import init_db, SessionLocal
from backend.app.services.simulation_service import SimulationService
from backend.app.services.realtime_energy_service import RealtimeEnergyService
from backend.app.services.auth_service import AuthService
from backend.app.api.auth_routes import create_auth_router
from backend.app.api.platform_routes import create_platform_router, create_system_router
from backend.app.api.settings_routes import create_settings_router
from backend.app.api.ev_routes import create_ev_router
from backend.app.api.simulation_routes import create_simulation_router
from backend.app.api.ai_routes import create_ai_router
from backend.app.api.energy_routes import create_energy_router
from backend.app.api.realtime_energy_routes import create_realtime_energy_router
from backend.app.api.analytics_routes import create_analytics_router
from backend.app.api.fixed_twin import router as fixed_twin_router
from backend.app.api.results import router as results_router
from backend.simulation.engine import digital_twin
import time
from datetime import datetime
from pydantic import BaseModel

sim_service = SimulationService()
realtime_service = RealtimeEnergyService(sim_service)
active_websockets: List[WebSocket] = []
main_event_loop: Optional[asyncio.AbstractEventLoop] = None

def on_twin_step(twin_state: dict):
    global main_event_loop
    try:
        if main_event_loop and main_event_loop.is_running():
            unified_payload = {
                **twin_state,
                "type": "digital_twin_update",
                "state": twin_state,
                "data": {
                    **twin_state,
                    "telemetry": twin_state.get("telemetry", {}),
                    "step_data": twin_state,
                    "status": realtime_service.get_telemetry_status()
                }
            }
            asyncio.run_coroutine_threadsafe(broadcast_websocket_event(unified_payload), main_event_loop)
    except Exception:
        pass

digital_twin.register_callback(on_twin_step)

async def broadcast_websocket_event(event: dict):
    disconnected = []
    for ws in list(active_websockets):
        try:
            await ws.send_json(event)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

async def realtime_background_loop():
    """Periodically writes authoritative digital twin telemetry snapshots to the database."""
    while True:
        try:
            if sim_service.is_running:
                db = SessionLocal()
                try:
                    state = digital_twin.get_full_state()
                    realtime_service.snapshot_counter += 1
                    if realtime_service.snapshot_counter % 5 == 0:
                        snap = TelemetrySnapshot(
                            source_mode=realtime_service.current_mode,
                            solar_power_kw=state["solar"]["generation_kw"],
                            grid_import_power_kw=state["power_flow"]["grid_import_kw"],
                            grid_export_power_kw=state["power_flow"]["grid_export_kw"],
                            ev_charging_power_kw=state["power_flow"]["ev_charging_kw"],
                            v2g_power_kw=state["power_flow"]["ev_discharge_kw"],
                            station_aux_power_kw=state["load"]["building_load_kw"],
                            system_losses_kw=state["power_flow"]["losses_kw"],
                            net_power_balance_kw=state["power_flow"]["conservation_error_kw"],
                            grid_frequency_hz=state["grid"]["frequency_hz"],
                            grid_voltage_v=state["grid"]["voltage_v"],
                            ambient_temp_c=state["battery"]["temperature_c"],
                            solar_irradiance_w_m2=state["solar"]["irradiance_w_m2"],
                            raw_telemetry_json=state
                        )
                        db.add(snap)
                        db.commit()
                except Exception as db_err:
                    db.rollback()
                finally:
                    db.close()
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            await asyncio.sleep(1.0)

# Ensure database tables exist and default admin is seeded
init_db()
try:
    with SessionLocal() as db_session:
        AuthService.seed_default_admin(db_session)
except Exception as seed_err:
    print(f"[Database Initialization Warning]: {seed_err}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()
    digital_twin.run()
    # Launch background loop
    loop_task = asyncio.create_task(realtime_background_loop())
    yield
    loop_task.cancel()
    digital_twin.pause()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="GridWise AI: Smart EV Charging, Digital Twin & V2G Energy Management System",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".html", ".js", ".css")) or path in ["/", "/simulator"]:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Register Routers
app.include_router(create_auth_router())
app.include_router(create_platform_router(sim_service, lambda: len(active_websockets), realtime_service=realtime_service))
app.include_router(create_system_router(sim_service, lambda: len(active_websockets), realtime_service=realtime_service))
app.include_router(create_settings_router(sim_service))
app.include_router(create_ev_router(sim_service))
app.include_router(create_simulation_router(sim_service, broadcast_websocket_event))
app.include_router(create_ai_router(sim_service))
app.include_router(create_energy_router(sim_service))
app.include_router(create_realtime_energy_router(realtime_service))
app.include_router(create_analytics_router(sim_service))
app.include_router(fixed_twin_router)
app.include_router(results_router)

# Digital Twin Live Telemetry Endpoints
@app.get("/api/digital-twin/state")
@app.get("/api/live/state")
def get_digital_twin_live_state():
    return digital_twin.get_full_state()

@app.get("/api/grid/current")
def get_grid_current():
    return digital_twin.get_full_state().get("grid", {})

@app.get("/api/price/current")
def get_price_current():
    return digital_twin.get_full_state().get("price", {})

@app.get("/api/renewable/current")
def get_renewable_current():
    return digital_twin.get_full_state().get("renewable", {})

@app.get("/api/ev/state")
def get_ev_state_endpoint():
    return digital_twin.get_full_state().get("ev", {})

@app.get("/api/battery/state")
def get_battery_state_endpoint():
    return digital_twin.get_full_state().get("battery", {})

@app.get("/api/charger/state")
def get_charger_state_endpoint():
    return digital_twin.get_full_state().get("charger", {})

@app.get("/api/controller/state")
def get_controller_state_endpoint():
    return digital_twin.get_full_state().get("controller", {})

@app.get("/api/meter/state")
def get_meter_state_endpoint():
    return digital_twin.get_full_state().get("meter", {})

@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "GridWise AI Simulation Platform",
        "version": "1.0.0",
        "simulator_running": digital_twin.is_running
    }

@app.get("/api/simulation/health")
def get_simulation_health():
    full_state = digital_twin.get_full_state()
    now_t = time.time()
    tick_age = round(now_t - getattr(digital_twin, "last_tick_time", now_t), 3)
    is_alive = tick_age < 3.0 and digital_twin.is_running
    return {
        "status": "HEALTHY" if is_alive else "STALLED",
        "is_running": digital_twin.is_running,
        "sequence": digital_twin.sequence_number,
        "tick_age_seconds": tick_age,
        "last_tick_dt": getattr(digital_twin, "last_tick_dt", 1.0),
        "last_tick_iso": getattr(digital_twin, "last_tick_iso", None),
        "simulation_time": digital_twin.sim_time_str,
        "scenario": getattr(digital_twin, "scenario", "normal"),
        "battery_soc": round(digital_twin.battery_state.soc, 3),
        "battery_energy_kwh": round(digital_twin.battery_state.energy_kwh, 3),
        "charger_power_kw": digital_twin.charger_state.power_kw,
        "mode": digital_twin.current_mode,
        "grid_stress_score": digital_twin.grid_stress_engine.stress_score,
        "grid_condition": digital_twin.grid_stress_engine.grid_condition,
        "high_load_confirmed": digital_twin.grid_stress_engine.is_high_load_confirmed
    }

class ScenarioPayload(BaseModel):
    scenario: str = "high_load"

@app.post("/api/simulation/trigger-load")
def trigger_high_load():
    digital_twin.set_scenario("high_load")
    return {"status": "success", "scenario": "high_load", "message": "High load scenario engaged; grid stress surging >= 75"}

@app.post("/api/simulation/scenario")
def set_scenario_api(payload: ScenarioPayload):
    digital_twin.set_scenario(payload.scenario)
    return {"status": "success", "scenario": payload.scenario}

class CircuitConnectionPayload(BaseModel):
    from_component: str
    from_port: str
    to_component: str
    to_port: str
    connection_type: Optional[str] = "power"
    connection_id: Optional[str] = None
    label: Optional[str] = ""

@app.post("/api/circuit/validate")
def validate_circuit_connection(payload: CircuitConnectionPayload):
    valid, msg = digital_twin.circuit.validate_connection(
        payload.from_component, payload.from_port,
        payload.to_component, payload.to_port
    )
    return {"valid": valid, "message": msg}

@app.post("/api/circuit/connect")
def add_circuit_connection(payload: CircuitConnectionPayload):
    import uuid
    cid = payload.connection_id or f"conn_{uuid.uuid4().hex[:6]}"
    success = digital_twin.circuit.add_connection(
        cid=cid,
        from_c=payload.from_component,
        from_p=payload.from_port,
        to_c=payload.to_component,
        to_p=payload.to_port,
        c_type=payload.connection_type or "power",
        label=payload.label or ""
    )
    if not success:
        last_err = digital_twin.circuit.connection_errors[-1] if digital_twin.circuit.connection_errors else "Invalid connection"
        raise HTTPException(status_code=400, detail=last_err)
    return {"status": "success", "connection_id": cid}

# Static Files & Homepage Serving
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
if not os.path.exists(static_dir):
    static_dir = os.path.abspath("static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

assets_dir = os.path.join(static_dir, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

results_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "results"))
if not os.path.exists(results_dir):
    results_dir = os.path.abspath("results")
if os.path.exists(results_dir):
    app.mount("/results", StaticFiles(directory=results_dir), name="results")

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return HTMLResponse("<h1>GridWise AI Backend Active</h1>")

@app.get("/simulator", response_class=HTMLResponse)
async def serve_simulator():
    sim_path = os.path.join(static_dir, "simulator.html")
    if os.path.exists(sim_path):
        return FileResponse(sim_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return HTMLResponse("<h1>Digital Twin Simulator Lab not found</h1>")

# WebSocket Real-Time Telemetry Endpoints
@app.websocket("/ws/simulation")
@app.websocket("/ws/sim")
@app.websocket("/ws/simulation/{simulation_id}")
async def websocket_simulation_endpoint(websocket: WebSocket, simulation_id: str = None):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        # Send initial full state immediately upon connection
        current_state = sim_service.engine.get_current_state()
        realtime_data = realtime_service.get_realtime_data()
        await websocket.send_json({
            "type": "INIT_STATE",
            "current_hour": current_state.get("hour", 0.0),
            "is_running": sim_service.is_running,
            "evs": current_state.get("evs", []),
            "energy_state": current_state.get("energy_state", {}),
            "manual_overrides": getattr(sim_service.engine, "manual_overrides", {}),
            "ai_decisions": current_state.get("ai_decisions", []),
            "ai_decision": current_state.get("ai_decision", {}),
            "data": current_state,
            "realtime": realtime_data
        })

        # Also send authoritative digital twin frame
        twin_state = digital_twin.get_full_state()
        history = digital_twin.get_history(window_seconds=300)
        latest_sample = history[-1] if history else {}
        await websocket.send_json({
            **twin_state,
            "type": "digital_twin_update",
            "sequence": digital_twin.sequence_number,
            "timestamp": twin_state.get("timestamp"),
            "simulation_time": digital_twin.sim_time_str,
            "real_time": digital_twin.real_time_str,
            "state": twin_state,
            "telemetry": latest_sample
        })

        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                cmd = msg.get("command") or msg.get("type")
                if cmd in ["ping", "PING", "heartbeat"]:
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    continue
                elif cmd in ["START", "start", "run"]:
                    sim_service.start()
                    digital_twin.run()
                    await broadcast_websocket_event({"type": "SIM_STARTED"})
                elif cmd in ["PAUSE", "pause"]:
                    sim_service.pause()
                    digital_twin.pause()
                    await broadcast_websocket_event({"type": "SIM_PAUSED"})
                elif cmd in ["STOP", "stop"]:
                    sim_service.stop()
                    digital_twin.pause()
                    await broadcast_websocket_event({"type": "SIM_STOPPED"})
                elif cmd in ["RESET", "reset"]:
                    sim_service.reset()
                    digital_twin.reset()
                    await broadcast_websocket_event({"type": "SIM_RESET", "hour": 0.0})
                elif cmd in ["STEP", "step"]:
                    step_data = sim_service.step()
                    await broadcast_websocket_event({"type": "SIM_STEP", "data": step_data})
                elif cmd in ["SET_SPEED", "speed"]:
                    spd = float(msg.get("speed", 1.0))
                    realtime_service.set_speed(spd)
                    digital_twin.set_speed(spd)
                    await broadcast_websocket_event({"type": "SPEED_CHANGED", "speed": spd})
                elif cmd in ["SET_MODE", "mode"]:
                    mod = str(msg.get("mode", "digital_twin"))
                    realtime_service.set_mode(mod)
                    await broadcast_websocket_event({"type": "MODE_CHANGED", "mode": mod})
                elif cmd in ["scenario", "set_scenario"]:
                    sc = msg.get("scenario", "normal")
                    digital_twin.set_scenario(sc)
                elif cmd == "trigger_load":
                    digital_twin.set_scenario("high_load")
                elif cmd in ["VALIDATE_CONNECTION", "validate_connection"]:
                    valid, msg_str = digital_twin.circuit.validate_connection(
                        msg.get("from_component", ""), msg.get("from_port", ""),
                        msg.get("to_component", ""), msg.get("to_port", "")
                    )
                    await websocket.send_json({"type": "CONNECTION_VALIDATION", "valid": valid, "message": msg_str})
                elif cmd in ["ADD_CONNECTION", "add_connection"]:
                    import uuid
                    cid = msg.get("connection_id") or f"conn_{uuid.uuid4().hex[:6]}"
                    success = digital_twin.circuit.add_connection(
                        cid=cid,
                        from_c=msg.get("from_component", ""),
                        from_p=msg.get("from_port", ""),
                        to_c=msg.get("to_component", ""),
                        to_p=msg.get("to_port", ""),
                        c_type=msg.get("connection_type", "power"),
                        label=msg.get("label", "")
                    )
                    await websocket.send_json({"type": "CONNECTION_ADDED", "success": success, "connection_id": cid})
                elif cmd in ["OVERRIDE_EV", "override_ev", "MANUAL_OVERRIDE"]:
                    ev_id = msg.get("ev_id", "EV-001")
                    act = msg.get("action", "IDLE")
                    digital_twin.apply_manual_override(ev_id, act)
                    await broadcast_websocket_event({"type": "OVERRIDE_APPLIED", "ev_id": ev_id, "action": act})
                elif cmd in ["ADD_EV", "add_ev"]:
                    ev_item = digital_twin.fleet_manager.add_ev(msg.get("ev_data", {}))
                    await broadcast_websocket_event({"type": "EV_ADDED", "ev": ev_item.to_dict()})
            except Exception as parse_err:
                print(f"[WS Command Parse Error]: {parse_err}")
    except WebSocketDisconnect:
        pass
    except Exception as ex:
        print(f"[WS Error]: {ex}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
