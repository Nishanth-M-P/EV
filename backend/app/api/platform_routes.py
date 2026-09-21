import time
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.database.database import get_db
from backend.app.config import settings

START_TIME = time.time()

def get_diagnostics_data(sim_service, get_ws_count: Callable[[], int], realtime_service, db: Session) -> Dict[str, Any]:
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    engine = sim_service.engine
    twin_status = "running" if sim_service.is_running else "stopped"
    ws_count = get_ws_count()

    total_ticks = getattr(realtime_service, "total_ticks", 0) if realtime_service else 0
    last_tick = getattr(realtime_service, "last_tick_time", None) if realtime_service else None
    balance_err = getattr(realtime_service, "last_balance_error_kw", 0.0) if realtime_service else 0.0

    ppo_status = "idle"
    if hasattr(engine, "rl_agent") and engine.rl_agent is not None:
        ppo = getattr(engine.rl_agent, "ppo", None)
        if ppo:
            ppo_status = getattr(ppo, "model_status", "trained").lower()

    return {
        "server": {
            "status": "online",
            "uptime_seconds": round(time.time() - START_TIME, 1),
            "version": settings.VERSION,
            "framework": "FastAPI + Uvicorn ASGI"
        },
        "database": {
            "status": db_status,
            "engine": "SQLite / SQLAlchemy ORM",
            "journal_mode": "WAL",
            "file": "gridwise.db"
        },
        "digital_twin": {
            "status": twin_status,
            "tick_rate_hz": 1.0,
            "ticks": total_ticks,
            "last_tick": last_tick,
            "simulation_id": engine.simulation_id,
            "current_hour": round(engine.current_hour, 2),
            "fleet_count": len(engine.evs)
        },
        "websocket": {
            "status": "available",
            "clients": ws_count,
            "endpoint": "/ws/simulation"
        },
        "authentication": {
            "status": "configured",
            "auth_type": "Bearer JWT / Token",
            "role_support": ["admin", "operator", "viewer"]
        },
        "ppo": {
            "status": ppo_status
        },
        "energy_balance": {
            "status": "balanced" if balance_err <= 0.05 else "imbalanced",
            "error_kw": balance_err
        }
    }

def create_platform_router(sim_service, get_ws_count: Callable[[], int], realtime_service=None):
    router = APIRouter(prefix="/api/platform", tags=["Platform Health & Status"])

    @router.get("/status")
    def get_platform_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
        diag = get_diagnostics_data(sim_service, get_ws_count, realtime_service, db)
        return {
            "platform_name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "uptime_seconds": diag["server"]["uptime_seconds"],
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "backend": {**diag["server"], "status": "healthy"},
                "database": diag["database"],
                "digital_twin": diag["digital_twin"],
                "ai_engine": {
                    "status": "active" if diag["ppo"]["status"] != "idle" else "ready",
                    "model": "PPO + Deterministic ConstraintEngine",
                    "observation_dim": 10,
                    "actions": ["IDLE", "CHARGE", "DISCHARGE_V2G"]
                },
                "websocket": diag["websocket"]
            },
            "overall_healthy": (diag["database"]["status"] == "healthy")
        }

    @router.get("/health")
    def platform_health_alias(db: Session = Depends(get_db)):
        return get_system_health(sim_service, get_ws_count, realtime_service, db)

    @router.get("/diagnostics")
    def platform_diagnostics_alias(db: Session = Depends(get_db)):
        return get_diagnostics_data(sim_service, get_ws_count, realtime_service, db)

    return router

def get_system_health(sim_service, get_ws_count: Callable[[], int], realtime_service, db: Session) -> Dict[str, Any]:
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    is_running = sim_service.is_running
    status_str = "healthy" if db_ok and is_running else "degraded"

    return {
        "status": status_str,
        "server": "online",
        "database": "healthy" if db_ok else "unhealthy",
        "digital_twin": "running" if is_running else "stopped",
        "websocket": "available",
        "timestamp": datetime.utcnow().isoformat()
    }

def create_system_router(sim_service, get_ws_count: Callable[[], int], realtime_service=None):
    router = APIRouter(prefix="/api/system", tags=["System Health & Diagnostics"])

    @router.get("/health")
    def system_health(db: Session = Depends(get_db)) -> Dict[str, Any]:
        return get_system_health(sim_service, get_ws_count, realtime_service, db)

    @router.get("/diagnostics")
    def system_diagnostics(db: Session = Depends(get_db)) -> Dict[str, Any]:
        return get_diagnostics_data(sim_service, get_ws_count, realtime_service, db)

    return router
