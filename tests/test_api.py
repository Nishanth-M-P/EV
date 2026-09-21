import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_homepage_and_docs():
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200

    res_home = client.get("/")
    assert res_home.status_code == 200

def test_ev_fleet_endpoints():
    res = client.get("/api/evs")
    assert res.status_code == 200
    data = res.json()
    assert "evs" in data
    assert len(data["evs"]) > 0

    # Test override
    first_id = data["evs"][0]["id"]
    res_over = client.post(f"/api/evs/{first_id}/override", json={"action": "CHARGE"})
    assert res_over.status_code == 200
    assert res_over.json()["override"] == "CHARGE"

    # Clear override
    res_clear = client.post(f"/api/evs/{first_id}/override", json={"action": None})
    assert res_clear.status_code == 200
    assert res_clear.json()["override"] is None

def test_energy_endpoints():
    res_grid = client.get("/api/grid")
    assert res_grid.status_code == 200
    assert "max_capacity_kw" in res_grid.json()

    res_prices = client.get("/api/prices")
    assert res_prices.status_code == 200
    assert res_prices.json()["label"] == "Simulated Electricity Price"

    res_renew = client.get("/api/renewables")
    assert res_renew.status_code == 200
    assert len(res_renew.json()["solar_profile"]) == 24

def test_ai_endpoints():
    res_status = client.get("/api/ai/status")
    assert res_status.status_code == 200
    assert res_status.json()["safety_constraint_layer"] == "ACTIVE"

    res_sched = client.get("/api/ai/schedule")
    assert res_sched.status_code == 200
    assert "schedule" in res_sched.json()

def test_simulation_controls_and_benchmark():
    # Step
    res_step = client.post("/api/simulation/step")
    assert res_step.status_code == 200
    step_data = res_step.json()
    assert "energy_flow" in step_data

    # Pause
    res_pause = client.post("/api/simulation/pause")
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "paused"

    # Start
    res_start = client.post("/api/simulation/start")
    assert res_start.status_code == 200
    assert res_start.json()["status"] == "started"

    # Reset
    res_reset = client.post("/api/simulation/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["current_hour"] == 0.0

    # Benchmark
    res_bm = client.get("/api/simulation/benchmark")
    assert res_bm.status_code == 200
    assert "summary_comparison" in res_bm.json()

    # Report
    res_rep = client.get("/api/simulation/report")
    assert res_rep.status_code == 200
    assert "markdown_report" in res_rep.json()
