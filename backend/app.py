import os
import json
import asyncio
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.responses import JSONResponse, HTMLResponse, FileResponse
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from backend.services.energy_service import EnergyService
from backend.services.ev_service import EVFleetService
from backend.simulation_engine import SimulationEngine
from backend.services.analytics_service import AnalyticsService
from backend.services.openai_service import OpenAIService

# Instantiating Services
energy_service = EnergyService()
ev_service = EVFleetService()
sim_engine = SimulationEngine()
sim_engine.energy_service = energy_service
sim_engine.ev_service = ev_service
sim_engine.is_running = True  # Default live real-time simulation running

active_websockets: list[WebSocket] = []
background_loop_task = None

async def realtime_background_loop():
    """
    Continuous background loop streaming live real-time telemetry every second.
    """
    while True:
        try:
            if sim_engine.is_running:
                step_data = sim_engine.step()
                await broadcast_websocket_event({"type": "SIM_STEP", "data": step_data})
            await asyncio.sleep(sim_engine.tick_interval_seconds)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[RealTime Loop Error]: {e}")
            await asyncio.sleep(1.0)

@asynccontextmanager
async def lifespan(app):
    global background_loop_task
    background_loop_task = asyncio.create_task(realtime_background_loop())
    yield
    if background_loop_task:
        background_loop_task.cancel()

# --- REST Handlers ---

async def homepage(request):
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "static", "index.html"),
        os.path.join(os.getcwd(), "static", "index.html"),
        os.path.abspath("static/index.html")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return FileResponse(path)
    return HTMLResponse("<h1>GridWise AI Backend Running</h1>")

# EV Fleet APIs
async def list_evs(request):
    return JSONResponse({"evs": ev_service.get_all_evs(), "overrides": sim_engine.manual_overrides})

async def add_ev(request):
    try:
        data = await request.json()
        ev = ev_service.add_ev(data)
        return JSONResponse({"status": "success", "ev": ev.to_dict()}, status_code=201)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

async def get_ev(request):
    ev_id = request.path_params["ev_id"]
    ev = ev_service.get_ev(ev_id)
    if not ev:
        return JSONResponse({"error": "EV not found"}, status_code=404)
    return JSONResponse(ev.to_dict())

async def delete_ev(request):
    ev_id = request.path_params["ev_id"]
    success = ev_service.remove_ev(ev_id)
    if success:
        return JSONResponse({"status": "deleted", "ev_id": ev_id})
    return JSONResponse({"error": "EV not found"}, status_code=404)

async def set_ev_override(request):
    ev_id = request.path_params["ev_id"]
    try:
        data = await request.json()
        action = data.get("action")  # "CHARGE", "DISCHARGE", "IDLE", or None
        sim_engine.set_manual_override(ev_id, action)
        await broadcast_websocket_event({"type": "OVERRIDE_CHANGED", "ev_id": ev_id, "action": action})
        return JSONResponse({"status": "updated", "ev_id": ev_id, "override": action})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# Energy Profile APIs
async def get_grid(request):
    return JSONResponse({
        "max_capacity_kw": energy_service.max_grid_capacity_kw,
        "hours": energy_service.hours,
        "grid_load_profile_kw": energy_service.grid_load_profile,
        "current_state": energy_service.get_state_at_hour(sim_engine.current_hour)
    })

async def get_prices(request):
    return JSONResponse({
        "currency": "INR (₹)",
        "hours": energy_service.hours,
        "price_profile": energy_service.price_profile
    })

async def get_renewables(request):
    return JSONResponse({
        "max_solar_capacity_kw": energy_service.max_solar_capacity_kw,
        "hours": energy_service.hours,
        "solar_profile": energy_service.solar_profile
    })

# AI Control Center APIs
async def get_ai_status(request):
    return JSONResponse({
        "algorithm": "Stable-Baselines3 PPO (Proximal Policy Optimization)",
        "framework": "Gymnasium 1.3.0 + PyTorch",
        "action_space": ["0: IDLE", "1: CHARGE", "2: DISCHARGE (V2G)"],
        "safety_constraint_layer": "ACTIVE",
        "current_simulation_hour": sim_engine.current_hour,
        "realtime_loop_status": "RUNNING" if sim_engine.is_running else "PAUSED"
    })

async def get_ai_schedule(request):
    schedule = {}
    temp_sim = SimulationEngine()
    temp_sim.energy_service = energy_service
    temp_sim.ev_service = EVFleetService()
    temp_sim.ev_service.reset_default_fleet()

    for h in range(24):
        hour_val = float(h)
        for ev in temp_sim.ev_service.evs.values():
            ev.update_status(hour_val)
            if ev.ev_id not in schedule:
                schedule[ev.ev_id] = {"ev_name": ev.name, "timeline": []}
            
            if ev.status in ["WAITING", "COMPLETED"]:
                action_name = "IDLE"
            else:
                dec = temp_sim.rl_engine.select_action(ev, hour_val)
                action_name = dec["action_name"]
            
            schedule[ev.ev_id]["timeline"].append({
                "hour": h,
                "action": action_name
            })

    return JSONResponse({"schedule": schedule})

async def ai_decision_single(request):
    try:
        data = await request.json()
        ev_id = data.get("ev_id")
        ev = ev_service.get_ev(ev_id) or list(ev_service.evs.values())[0]
        hour = float(data.get("hour", sim_engine.current_hour))
        decision = sim_engine.rl_engine.select_action(ev, hour)
        return JSONResponse(decision)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

async def get_openai_insight(request):
    """
    OpenAI LLM Endpoint for strategic energy advisor insights.
    """
    energy_state = energy_service.get_state_at_hour(sim_engine.current_hour)
    evs_info = ", ".join([f"{ev.ev_id}: SOC {ev.current_soc}%, Status {ev.status}" for ev in ev_service.evs.values()])
    
    insight = OpenAIService.generate_llm_insight(
        grid_load_pct=energy_state["grid_load_pct"],
        electricity_price=energy_state["electricity_price"],
        solar_kw=energy_state["solar_generation_kw"],
        ev_summary=evs_info
    )
    
    if not insight:
        insight = "GridWise AI Advisor: High solar availability detected. Prioritizing EV charging during daytime window to minimize peak grid draw and lower charging cost."

    return JSONResponse({"insight": insight})

# Simulation APIs
async def sim_status(request):
    return JSONResponse({
        "current_hour": sim_engine.current_hour,
        "is_running": sim_engine.is_running,
        "tick_interval_seconds": sim_engine.tick_interval_seconds,
        "history_count": len(sim_engine.history),
        "fleet_count": len(ev_service.evs)
    })

async def sim_step(request):
    step_data = sim_engine.step()
    await broadcast_websocket_event({"type": "SIM_STEP", "data": step_data})
    return JSONResponse(step_data)

async def sim_reset(request):
    sim_engine.reset()
    await broadcast_websocket_event({"type": "SIM_RESET", "hour": 0.0})
    return JSONResponse({"status": "reset", "current_hour": 0.0})

async def sim_start(request):
    sim_engine.is_running = True
    await broadcast_websocket_event({"type": "SIM_STARTED"})
    return JSONResponse({"status": "started", "is_running": True})

async def sim_pause(request):
    sim_engine.is_running = False
    await broadcast_websocket_event({"type": "SIM_PAUSED"})
    return JSONResponse({"status": "paused", "is_running": False})

async def get_benchmark(request):
    benchmark_results = SimulationEngine.run_benchmark()
    return JSONResponse(benchmark_results)

# Analytics APIs
async def get_analytics_summary(request):
    summary = AnalyticsService.compute_simulation_analytics(sim_engine.history)
    return JSONResponse(summary)


# --- WebSocket Handler ---

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        await websocket.send_json({
            "type": "INIT_STATE",
            "current_hour": sim_engine.current_hour,
            "is_running": sim_engine.is_running,
            "evs": ev_service.get_all_evs(),
            "energy_state": energy_service.get_state_at_hour(sim_engine.current_hour),
            "manual_overrides": sim_engine.manual_overrides
        })
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                cmd = msg.get("command")
                if cmd == "STEP":
                    res = sim_engine.step()
                    await broadcast_websocket_event({"type": "SIM_STEP", "data": res})
                elif cmd == "START":
                    sim_engine.is_running = True
                    await broadcast_websocket_event({"type": "SIM_STARTED"})
                elif cmd == "PAUSE":
                    sim_engine.is_running = False
                    await broadcast_websocket_event({"type": "SIM_PAUSED"})
                elif cmd == "RESET":
                    sim_engine.reset()
                    await broadcast_websocket_event({"type": "SIM_RESET", "hour": 0.0})
            except Exception:
                pass
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

async def broadcast_websocket_event(event: dict):
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(event)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)


# Application Routes
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
if not os.path.exists(static_dir):
    static_dir = os.path.abspath("static")

routes = [
    Route("/", homepage),
    # EV APIs
    Route("/api/evs", list_evs, methods=["GET"]),
    Route("/api/evs", add_ev, methods=["POST"]),
    Route("/api/evs/{ev_id}", get_ev, methods=["GET"]),
    Route("/api/evs/{ev_id}", delete_ev, methods=["DELETE"]),
    Route("/api/evs/{ev_id}/override", set_ev_override, methods=["POST"]),
    # Energy APIs
    Route("/api/grid", get_grid, methods=["GET"]),
    Route("/api/prices", get_prices, methods=["GET"]),
    Route("/api/renewables", get_renewables, methods=["GET"]),
    # AI APIs
    Route("/api/ai/status", get_ai_status, methods=["GET"]),
    Route("/api/ai/schedule", get_ai_schedule, methods=["GET"]),
    Route("/api/ai/decision", ai_decision_single, methods=["POST"]),
    Route("/api/ai/insight", get_openai_insight, methods=["GET"]),
    # Simulation APIs
    Route("/api/simulation/status", sim_status, methods=["GET"]),
    Route("/api/simulation/step", sim_step, methods=["POST"]),
    Route("/api/simulation/reset", sim_reset, methods=["POST"]),
    Route("/api/simulation/start", sim_start, methods=["POST"]),
    Route("/api/simulation/pause", sim_pause, methods=["POST"]),
    Route("/api/simulation/benchmark", get_benchmark, methods=["GET"]),
    # Analytics
    Route("/api/analytics/summary", get_analytics_summary, methods=["GET"]),
    # WebSockets
    WebSocketRoute("/ws/simulation", websocket_endpoint),
    # Static Assets
    Mount("/static", StaticFiles(directory=static_dir), name="static")
]

app = Starlette(
    debug=True,
    routes=routes,
    lifespan=lifespan
)
