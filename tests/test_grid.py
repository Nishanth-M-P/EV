import pytest
from backend.app.simulator.grid_simulator import GridSimulator

def test_grid_initialization_and_base_load():
    grid = GridSimulator(grid_capacity_kw=100.0, peak_threshold_pct=80.0)
    assert grid.grid_capacity_kw == 100.0
    assert grid.peak_threshold_kw == 80.0
    
    # Morning base load should be positive
    morning_load = grid.get_base_load_at_hour(9.0)
    assert morning_load > 20.0
    assert morning_load < 100.0

def test_grid_state_stress_and_peak():
    grid = GridSimulator(grid_capacity_kw=100.0, peak_threshold_pct=80.0)
    
    # Low load state
    low_state = grid.calculate_grid_state(hour=2.0, ev_charging_power_kw=0.0)
    assert low_state["utilization_pct"] < 50.0
    assert low_state["stress_level"] == "LOW"
    assert not low_state["peak_status"]

    # High load state with EV charging
    high_state = grid.calculate_grid_state(hour=19.0, ev_charging_power_kw=20.0)
    assert high_state["utilization_pct"] >= 80.0
    assert high_state["stress_level"] in ["HIGH", "CRITICAL"]
    assert high_state["peak_status"] is True

def test_grid_v2g_peak_shaving():
    grid = GridSimulator(grid_capacity_kw=100.0)
    # Peak hour without V2G
    state_without_v2g = grid.calculate_grid_state(hour=19.0, ev_charging_power_kw=0.0, ev_v2g_power_kw=0.0)
    # Peak hour with 15 kW V2G discharge back into feeder
    state_with_v2g = grid.calculate_grid_state(hour=19.0, ev_charging_power_kw=0.0, ev_v2g_power_kw=15.0)
    
    assert state_with_v2g["net_grid_load_kw"] < state_without_v2g["net_grid_load_kw"]
    assert state_with_v2g["utilization_pct"] < state_without_v2g["utilization_pct"]
