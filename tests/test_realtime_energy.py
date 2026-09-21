import pytest
from fastapi.testclient import TestClient
from backend.app.main import app, sim_service, realtime_service
from backend.app.simulator.energy_balance import EnergyBalanceEngine, PowerFlowState
from backend.app.telemetry.source import DigitalTwinTelemetrySource, HybridTelemetrySource

client = TestClient(app)

def test_energy_conservation_balance():
    """Verify physical energy conservation: P_solar + P_grid_in + P_v2g = P_ev + P_aux + P_export + P_losses."""
    engine = EnergyBalanceEngine(base_station_aux_kw=6.0, loss_factor=0.035)
    
    # Scenario 1: Abundant solar, charging EVs, surplus export
    state1 = engine.calculate_balance(solar_gen_kw=35.0, ev_charging_demand_kw=15.0, v2g_discharge_kw=0.0, hour=12.0)
    assert state1.is_balanced is True
    assert state1.balance_error_kw <= 0.05
    assert state1.solar_to_ev_kw == 15.0
    assert state1.solar_to_grid_kw > 0.0
    assert state1.grid_import_kw == 0.0
    assert state1.solar_share_pct == 100.0

    # Scenario 2: Zero solar (night), grid imports for EV charging and aux
    state2 = engine.calculate_balance(solar_gen_kw=0.0, ev_charging_demand_kw=20.0, v2g_discharge_kw=0.0, hour=2.0)
    assert state2.is_balanced is True
    assert state2.balance_error_kw <= 0.05
    assert state2.solar_to_ev_kw == 0.0
    assert state2.grid_import_kw >= 26.0  # EV + aux + losses
    assert state2.grid_share_pct == 100.0

    # Scenario 3: V2G peak shaving export
    state3 = engine.calculate_balance(solar_gen_kw=5.0, ev_charging_demand_kw=0.0, v2g_discharge_kw=15.0, hour=19.0)
    assert state3.is_balanced is True
    assert state3.balance_error_kw <= 0.05
    assert state3.v2g_to_station_kw > 0.0
    assert state3.grid_export_kw > 0.0


def test_ev_attribution_shares():
    """Verify individual EV solar vs grid power breakdown attribution."""
    engine = EnergyBalanceEngine()
    # 50% solar, 50% grid
    flow = PowerFlowState(
        solar_share_pct=60.0,
        grid_share_pct=40.0
    )
    attr = engine.attribute_ev_power(10.0, flow)
    assert attr["power_kw"] == 10.0
    assert attr["solar_power_kw"] == 6.0
    assert attr["grid_power_kw"] == 4.0
    assert attr["solar_pct"] == 60.0
    assert attr["grid_pct"] == 40.0

    # Zero power idle
    zero_attr = engine.attribute_ev_power(0.0, flow)
    assert zero_attr["power_kw"] == 0.0
    assert zero_attr["solar_power_kw"] == 0.0


def test_accumulated_energy_integration():
    """Verify delta energy integration: delta E = P * delta t."""
    engine = EnergyBalanceEngine()
    state = engine.calculate_balance(solar_gen_kw=20.0, ev_charging_demand_kw=10.0, v2g_discharge_kw=0.0, hour=11.0)
    
    # 15 minutes = 0.25h
    res = engine.accumulate_energy(state, timestep_hours=0.25, grid_tariff_inr=7.0)
    assert res["cumulative"]["solar_gen_kwh_today"] == 5.0  # 20 kW * 0.25h
    assert res["cumulative"]["ev_charging_kwh_today"] == 2.5  # 10 kW * 0.25h


def test_telemetry_source_modes():
    """Verify telemetry source switching and properties."""
    source = DigitalTwinTelemetrySource(sim_service.engine)
    assert source.get_mode() == "digital_twin"
    assert source.is_healthy() is True

    snap = source.get_telemetry()
    assert "power" in snap
    assert "grid_diagnostics" in snap
    assert snap["grid_diagnostics"]["frequency_hz"] >= 49.0
    assert snap["grid_diagnostics"]["frequency_hz"] <= 51.0

    hybrid = HybridTelemetrySource(sim_service.engine)
    assert hybrid.get_mode() == "hybrid"
    h_snap = hybrid.get_telemetry()
    assert h_snap["source_mode"] == "hybrid"


def test_realtime_api_endpoints():
    """Verify all real-time REST API endpoints return HTTP 200 with valid schema."""
    # 1. Realtime energy data
    res = client.get("/api/energy/realtime")
    assert res.status_code == 200
    data = res.json()
    assert "power_kw" in data
    assert "cumulative_kwh_today" in data
    assert "conservation_check" in data
    assert data["conservation_check"]["is_balanced"] is True

    # 2. Energy flow topology
    flow_res = client.get("/api/energy/flow")
    assert flow_res.status_code == 200
    flow_data = flow_res.json()
    assert "nodes" in flow_data
    assert "links" in flow_data

    # 3. Energy summary
    summary_res = client.get("/api/energy/summary")
    assert summary_res.status_code == 200
    assert "cumulative_kwh" in summary_res.json()

    # 4. Energy ledger
    ledger_res = client.get("/api/energy/ledger")
    assert ledger_res.status_code == 200
    assert "transactions" in ledger_res.json()

    # 5. Telemetry status & mode update
    status_res = client.get("/api/telemetry/status")
    assert status_res.status_code == 200
    assert status_res.json()["mode"] in ["digital_twin", "hardware", "hybrid"]

    # Change mode and speed
    mode_res = client.post("/api/telemetry/mode", json={"mode": "hybrid", "speed_multiplier": 60.0})
    assert mode_res.status_code == 200
    assert mode_res.json()["mode"] == "hybrid"
    assert mode_res.json()["speed_multiplier"] == 60.0

    # Reset back to digital twin
    mode_res2 = client.post("/api/telemetry/mode", json={"mode": "digital_twin", "speed_multiplier": 1.0})
    assert mode_res2.status_code == 200
    assert mode_res2.json()["mode"] == "digital_twin"

    # 6. Operational alerts
    alerts_res = client.get("/api/alerts")
    assert alerts_res.status_code == 200
    assert "alerts" in alerts_res.json()
