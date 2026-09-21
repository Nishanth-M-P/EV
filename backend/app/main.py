import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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

sim_service = SimulationService()
realtime_service = RealtimeEnergyService(sim_service)
active_websockets: List[WebSocket] = []

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
    """Streams live real-time simulation step ticks continuously (1 Hz)."""
    while True:
        try:
            if sim_service.is_running:
                db = SessionLocal()
                try:
                    tick_res = realtime_service.process_tick(db=db)
                except Exception as tick_err:
                    import traceback
                    print(f"[ENGINE_ERROR] Digital Twin tick exception at {datetime.utcnow().isoformat()}: {tick_err}")
                    traceback.print_exc()
                    tick_res = None
                finally:
                    db.close()

                if tick_res:
                    # Broadcast live streaming payload
                    await broadcast_websocket_event({
                        "type": "REALTIME_UPDATE",
                        "data": tick_res
                    })
                    # Backwards-compatible SIM_STEP event for legacy listeners
                    await broadcast_websocket_event({
                        "type": "SIM_STEP",
                        "data": tick_res["step_data"]
                    })
            else:
                # Send static status update so clock and connection health stay live
                static_data = realtime_service.get_realtime_data()
                await broadcast_websocket_event({
                    "type": "REALTIME_STATIC",
                    "data": static_data
                })

            await asyncio.sleep(sim_service.tick_interval_seconds)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[RealTime Loop Exception]: {e}")
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
    # Launch background loop
    loop_task = asyncio.create_task(realtime_background_loop())
    yield
    loop_task.cancel()

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

# Static Files & Homepage Serving
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
if not os.path.exists(static_dir):
    static_dir = os.path.abspath("static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>GridWise AI Backend Active</h1>")

# WebSocket Real-Time Telemetry Endpoints
@app.websocket("/ws/simulation")
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
            "current_hour": current_state["hour"],
            "is_running": sim_service.is_running,
            "evs": current_state["evs"],
            "energy_state": current_state["energy_state"],
            "manual_overrides": sim_service.engine.manual_overrides,
            "data": current_state,
            "realtime": realtime_data
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
                elif cmd == "START":
                    sim_service.start()
                    await broadcast_websocket_event({"type": "SIM_STARTED"})
                elif cmd == "PAUSE":
                    sim_service.pause()
                    await broadcast_websocket_event({"type": "SIM_PAUSED"})
                elif cmd == "STOP":
                    sim_service.stop()
                    await broadcast_websocket_event({"type": "SIM_STOPPED"})
                elif cmd == "RESET":
                    sim_service.reset()
                    await broadcast_websocket_event({"type": "SIM_RESET", "hour": 0.0})
                elif cmd == "STEP":
                    step_data = sim_service.step()
                    await broadcast_websocket_event({"type": "SIM_STEP", "data": step_data})
                elif cmd == "SET_SPEED":
                    spd = float(msg.get("speed", 1.0))
                    realtime_service.set_speed(spd)
                    await broadcast_websocket_event({"type": "SPEED_CHANGED", "speed": spd})
                elif cmd == "SET_MODE":
                    mod = str(msg.get("mode", "digital_twin"))
                    realtime_service.set_mode(mod)
                    await broadcast_websocket_event({"type": "MODE_CHANGED", "mode": mod})
            except Exception as parse_err:
                print(f"[WS Command Parse Error]: {parse_err}")
    except WebSocketDisconnect:
        pass
    except Exception as ex:
        print(f"[WS Error]: {ex}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
