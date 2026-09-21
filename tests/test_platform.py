import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.database import SessionLocal
from backend.app.services.auth_service import AuthService

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_auth_service_password_hashing():
    raw = "SuperSecretPassword123"
    hashed = AuthService.hash_password(raw)
    assert hashed != raw
    assert "$" in hashed
    assert AuthService.verify_password(raw, hashed) is True
    assert AuthService.verify_password("WrongPassword", hashed) is False

def test_auth_login_and_me_lifecycle(client):
    # Ensure default admin is seeded
    with SessionLocal() as db:
        AuthService.seed_default_admin(db)

    # 1. Failed login
    res_bad = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrong_password"
    })
    assert res_bad.status_code == 401

    # 2. Successful login
    res_good = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "GridWise@2026"
    })
    assert res_good.status_code == 200
    data = res_good.json()
    assert "token" in data
    token = data["token"]
    assert data["user"]["username"] == "admin"

    # 3. Get /me
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["username"] == "admin"

    # 4. Forgot password
    res_forgot = client.post("/api/auth/forgot-password", json={"email": "admin@gridwise.ai"})
    assert res_forgot.status_code == 200
    assert res_forgot.json()["status"] == "success"

    # 5. Logout
    res_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res_logout.status_code == 200

    # 6. Verify token is invalidated
    res_me_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me_after.status_code == 401

def test_platform_health_status(client):
    res = client.get("/api/platform/status")
    assert res.status_code == 200
    data = res.json()
    assert data["overall_healthy"] is True
    assert data["services"]["backend"]["status"] == "healthy"
    assert data["services"]["database"]["status"] == "healthy"
    assert data["services"]["digital_twin"]["fleet_count"] >= 1
    assert data["services"]["ai_engine"]["observation_dim"] == 10

def test_settings_get_and_update(client):
    res_get = client.get("/api/settings")
    assert res_get.status_code == 200
    settings = res_get.json()
    assert "simulation" in settings
    assert "safety_limits" in settings
    assert "v2g_settings" in settings

    # Update settings
    res_post = client.post("/api/settings", json={
        "safety_limits": {"min_soc_pct": 25.0},
        "v2g_settings": {"min_discharge_soc_pct": 40.0}
    })
    assert res_post.status_code == 200
    updated = res_post.json()["settings"]
    assert updated["safety_limits"]["min_soc_pct"] == 25.0
    assert updated["v2g_settings"]["min_discharge_soc_pct"] == 40.0

def test_custom_scenario_creation_and_run(client):
    custom_scenario = {
        "name": "Heavy EV Fleet Scenario",
        "duration_hours": 24.0,
        "timestep_minutes": 15,
        "grid_capacity_kw": 120.0,
        "solar_capacity_kw": 50.0,
        "cloud_factor": 0.8,
        "evs": [
            {
                "id": "EV-TEST-1",
                "name": "Tesla Model 3 Long Range",
                "battery_capacity_kwh": 75.0,
                "current_soc": 30.0,
                "minimum_soc": 20.0,
                "maximum_soc": 90.0,
                "target_soc": 80.0,
                "arrival_time": 7.0,
                "departure_time": 17.0,
                "max_charge_power_kw": 11.0,
                "max_discharge_power_kw": 7.0
            },
            {
                "id": "EV-TEST-2",
                "name": "Hyundai Ioniq 5 AWD",
                "battery_capacity_kwh": 77.4,
                "current_soc": 40.0,
                "minimum_soc": 20.0,
                "maximum_soc": 95.0,
                "target_soc": 85.0,
                "arrival_time": 9.0,
                "departure_time": 19.0,
                "max_charge_power_kw": 11.0,
                "max_discharge_power_kw": 7.0
            }
        ],
        "v2g_enabled": True
    }

    res_create = client.post("/api/simulation/create", json=custom_scenario)
    assert res_create.status_code == 200
    data = res_create.json()
    assert data["status"] == "created"
    assert len(data["state"]["evs"]) == 2
    assert data["state"]["evs"][0]["id"] == "EV-TEST-1"

    # Step custom simulation
    res_step = client.post("/api/simulation/step")
    assert res_step.status_code == 200
    assert "energy_flow" in res_step.json()

def test_run_24h_cycle_and_history(client):
    # Run full 24h cycle
    res_24h = client.post("/api/simulation/run-24h")
    assert res_24h.status_code == 200
    res_data = res_24h.json()
    assert res_data["status"] == "COMPLETED"
    assert res_data["steps_executed"] > 0
    assert "benchmark" in res_data
    assert "analytics" in res_data

    # Check history endpoint
    res_hist = client.get("/api/simulation/history")
    assert res_hist.status_code == 200
    history = res_hist.json()
    assert isinstance(history, list)
    assert len(history) >= 1

    # Check simulation results by ID
    sim_id = res_data["simulation_id"]
    res_res = client.get(f"/api/simulation/{sim_id}/results")
    assert res_res.status_code == 200
