import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.database import engine
from sqlalchemy import text

client = TestClient(app)

def test_auth_me_valid_and_invalid_tokens():
    # 1. Missing token -> 401
    res_no_token = client.get("/api/auth/me")
    assert res_no_token.status_code == 401
    assert "detail" in res_no_token.json()

    # 2. Invalid token -> 401
    res_bad_token = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_token_12345"})
    assert res_bad_token.status_code == 401

    # 3. Valid login -> Bearer token -> 200
    res_login = client.post("/api/auth/login", json={
        "username": "admin@gridwise.ai",
        "password": "GridWise@2026"
    })
    assert res_login.status_code == 200
    token = res_login.json()["token"]
    assert token

    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    user_data = res_me.json()
    assert user_data["username"] == "admin"
    assert user_data["role"] == "admin"

def test_system_health_and_diagnostics_endpoints():
    # Test GET /api/system/health
    res_health = client.get("/api/system/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert h_data["status"] in ["healthy", "degraded"]
    assert h_data["server"] == "online"
    assert h_data["database"] == "healthy"
    assert h_data["digital_twin"] in ["running", "stopped"]
    assert h_data["websocket"] == "available"

    # Test GET /api/system/diagnostics
    res_diag = client.get("/api/system/diagnostics")
    assert res_diag.status_code == 200
    d_data = res_diag.json()
    assert "server" in d_data
    assert "database" in d_data
    assert "digital_twin" in d_data
    assert "websocket" in d_data
    assert "authentication" in d_data
    assert "ppo" in d_data
    assert "energy_balance" in d_data
    assert d_data["database"]["journal_mode"] == "WAL"

def test_constraint_events_response_shape():
    res = client.get("/api/ai/constraints/events?limit=25")
    assert res.status_code == 200
    data = res.json()
    # Contract: MUST have "events", "recent_events", "total", "limit"
    assert "events" in data
    assert isinstance(data["events"], list)
    assert "recent_events" in data
    assert "total" in data
    assert "limit" in data
    assert data["limit"] == 25

def test_ppo_background_training_flow():
    # Background training job start
    res_bg = client.post("/api/ai/train", json={"episodes": 10, "background": True})
    assert res_bg.status_code == 200
    data_bg = res_bg.json()
    assert data_bg["status"] == "started"
    assert "job_id" in data_bg
    assert data_bg["episodes"] == 10

    # Training status check
    res_status = client.get("/api/ai/training/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "mean_reward" in status_data
    assert isinstance(status_data["mean_reward"], (int, float))
    assert "best_reward" in status_data
    assert "final_reward" in status_data

def test_simulation_start_idempotency():
    res1 = client.post("/api/simulation/start")
    assert res1.status_code == 200
    assert res1.json()["status"] == "started"
    assert res1.json()["is_running"] is True

    res2 = client.post("/api/simulation/start")
    assert res2.status_code == 200
    assert res2.json()["status"] == "started"
    assert res2.json()["engine_status"] == "already_running"

def test_sqlite_wal_mode_enabled():
    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA journal_mode;")).fetchone()
        assert res[0].upper() == "WAL"
