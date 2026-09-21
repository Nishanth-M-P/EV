import pytest
from backend.app.simulator.simulation_engine import SimulationEngine
from backend.app.ai.comparator import AIComparator

def test_simulation_engine_initialization_and_step():
    engine = SimulationEngine(grid_capacity_kw=100.0, solar_capacity_kw=40.0, timestep_minutes=15)
    assert len(engine.evs) == 5
    assert engine.current_hour == 0.0
    
    step_data = engine.step()
    assert step_data["step_index"] == 0
    assert "grid" in step_data
    assert "solar" in step_data
    assert "price" in step_data
    assert "energy_flow" in step_data
    assert len(step_data["evs"]) == 5
    assert engine.current_hour == 0.25

def test_simulation_engine_24h_cycle():
    engine = SimulationEngine(grid_capacity_kw=100.0, solar_capacity_kw=40.0, timestep_minutes=60)
    for _ in range(24):
        engine.step()

    assert len(engine.history) == 24
    assert engine.total_solar_generated_kwh > 0.0

def test_multi_ev_simultaneous_management():
    engine = SimulationEngine(timestep_minutes=30)
    # Step into midday (e.g. 12:00) when all EVs are connected
    for _ in range(24):
        step_data = engine.step()
        if step_data["hour"] == 12.0:
            active_count = sum(1 for e in step_data["evs"] if e["status"] in ["CHARGING", "IDLE", "DISCHARGING"])
            assert active_count == 5

def test_comparator_benchmark():
    engine = SimulationEngine()
    fleet_specs = [ev.to_dict() for ev in engine.evs.values()]
    
    results = AIComparator.run_comparison(
        fleet_specs=fleet_specs,
        grid_capacity_kw=100.0,
        solar_capacity_kw=40.0,
        timestep_minutes=15
    )

    summary = results["summary_comparison"]
    assert "energy_cost_traditional_inr" in summary
    assert "energy_cost_ai_inr" in summary
    assert "cost_savings_pct" in summary
    assert "peak_load_reduction_pct" in summary
    assert summary["cost_savings_pct"] >= 0.0
