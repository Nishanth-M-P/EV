import pytest
import numpy as np
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.ai.ppo_model import PPOActorCritic
from backend.app.ai.environment import EVChargingGymEnv
from backend.app.ai.constraints import ConstraintEngine
from backend.app.simulator.battery_simulator import BatterySimulator
from backend.app.simulator.forecasting import ForecastProvider
from backend.app.simulator.energy_provider import SimulationEnergyProvider

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_ppo_actor_critic_forward_and_predict():
    policy = PPOActorCritic(obs_dim=10, act_dim=3, hidden_dim=64, seed=42)
    sample_obs = np.array([0.5, 0.85, 0.20, 0.6, 0.4, 0.65, 0.7, 0.0, 0.0, 1.0], dtype=np.float32)
    
    probs, value = policy.forward(sample_obs)
    assert len(probs) == 3
    assert np.isclose(np.sum(probs), 1.0, atol=1e-5)
    assert isinstance(value, float)

    act, probs_dict, state_val, conf = policy.predict(sample_obs, deterministic=True)
    assert act in [0, 1, 2]
    assert "CHARGE" in probs_dict
    assert "IDLE" in probs_dict
    assert "DISCHARGE" in probs_dict
    assert 0.0 <= conf <= 1.0

def test_ppo_training_on_gym_env():
    policy = PPOActorCritic(obs_dim=10, act_dim=3, hidden_dim=64)
    env = EVChargingGymEnv()
    
    res = policy.train_on_env(env, num_episodes=5)
    assert res["episodes_trained"] > 10000
    assert "mean_reward" in res
    assert "best_reward" in res
    assert res["status"] == "TRAINED"

def test_ai_training_center_api(client):
    res_status = client.get("/api/ai/training/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["algorithm"] == "PPO (Proximal Policy Optimization)"
    assert data["status"] == "TRAINED"
    assert "training_curves" in data
    assert len(data["training_curves"]["episodes"]) > 5

    # Trigger live training step
    res_train = client.post("/api/ai/train", json={"episodes": 10})
    assert res_train.status_code == 200
    train_data = res_train.json()
    assert train_data["status"] == "success"
    assert "metrics" in train_data

def test_constraint_event_logging_and_explain(client):
    # Trigger an override by asking for explain
    res_explain = client.get("/api/ai/explain/EV-001")
    assert res_explain.status_code == 200
    exp = res_explain.json()
    assert "detailed_explanation" in exp
    assert "neural_network_probabilities" in exp
    assert "proposed_action" in exp
    assert "final_action" in exp

    # Check constraint events endpoint
    res_events = client.get("/api/ai/constraints/events")
    assert res_events.status_code == 200
    events_data = res_events.json()
    assert "recent_events" in events_data
    assert isinstance(events_data["recent_events"], list)

def test_battery_thermal_physics():
    batt = BatterySimulator(capacity_kwh=60.0, initial_soc=50.0, ambient_temp_c=25.0)
    assert batt.temperature_c == 25.0

    # Charge at high power (22 kW) for 1 hour -> should heat up
    res = batt.charge(power_kw=22.0, timestep_hours=1.0)
    assert res["temperature_c"] > 25.0
    assert batt.temperature_c > 25.0

    # Test thermal derating when hot
    batt.temperature_c = 48.0
    derate = batt._get_thermal_derating_factor()
    assert derate < 1.0  # throttled

def test_battery_soh_degradation():
    batt = BatterySimulator(capacity_kwh=60.0, initial_soc=50.0, degradation_factor=0.001)
    initial_health = batt.battery_health
    
    # Discharge battery
    batt.discharge(power_kw=10.0, timestep_hours=1.0)
    assert batt.battery_health < initial_health
    assert batt.equivalent_full_cycles > 0.0

def test_predictive_forecasting():
    provider = SimulationEnergyProvider()
    forecast = ForecastProvider.get_4h_forecast(current_hour=10.0, energy_provider=provider, horizon_hours=4.0)
    
    assert len(forecast["timeline"]) == 16  # 4h * 4 (15m steps)
    assert len(forecast["forecast_solar_kw"]) == 16
    assert len(forecast["forecast_grid_load_kw"]) == 16
    assert len(forecast["forecast_price_inr"]) == 16
    assert "strategic_summary" in forecast

def test_energy_forecast_api(client):
    res = client.get("/api/energy/forecast")
    assert res.status_code == 200
    data = res.json()
    assert "forecast_solar_kw" in data
    assert "strategic_summary" in data

def test_scenario_presets_and_csv_export(client):
    res_presets = client.get("/api/simulation/presets")
    assert res_presets.status_code == 200
    presets = res_presets.json()
    assert "normal_day" in presets
    assert "peak_grid_stress" in presets
    assert "high_solar" in presets

    # Load a preset
    res_load = client.post("/api/simulation/presets/high_solar")
    assert res_load.status_code == 200
    assert res_load.json()["status"] == "preset_loaded"

    # Step simulation to populate history
    client.post("/api/simulation/step")

    # Export CSV
    res_csv = client.get("/api/simulation/export/csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "net_grid_load_kw" in res_csv.text
    assert "soc_pct" in res_csv.text
