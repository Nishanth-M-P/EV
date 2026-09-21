import pytest
from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.ai.constraints import ConstraintEngine

def test_v2g_valid_conditions():
    # EV with high SOC (90%), ample time before departure
    ev = EVDigitalTwin(
        ev_id="EV-V2G-OK",
        name="V2G Provider",
        battery_capacity_kwh=60.0,
        current_soc=90.0,
        minimum_soc=20.0,
        target_soc=80.0,
        arrival_time=8.0,
        departure_time=18.0
    )
    ev.update_schedule_status(12.0)

    # Propose V2G action (2 = DISCHARGE)
    action, power_kw, overrides = ConstraintEngine.validate_action(
        ev=ev,
        proposed_action=2,
        current_hour=12.0,
        grid_load_pct=85.0,
        electricity_price=10.5
    )

    assert action == 2
    assert power_kw < 0.0  # Approved negative power for export
    assert len(overrides) == 0

def test_v2g_blocked_when_at_minimum_soc():
    # EV at minimum SOC (20%)
    ev = EVDigitalTwin(
        ev_id="EV-V2G-BLOCK",
        name="Depleted EV",
        battery_capacity_kwh=60.0,
        current_soc=20.0,
        minimum_soc=20.0,
        target_soc=80.0,
        arrival_time=8.0,
        departure_time=23.0
    )
    ev.update_schedule_status(12.0)

    # Propose V2G action (2)
    action, power_kw, overrides = ConstraintEngine.validate_action(
        ev=ev,
        proposed_action=2,
        current_hour=12.0,
        grid_load_pct=90.0,
        electricity_price=11.0
    )

    assert action == 0  # Forced IDLE
    assert power_kw == 0.0
    assert any("MIN SOC LIMIT" in o for o in overrides)

def test_v2g_blocked_when_departure_near():
    # EV has 80% SOC, target 85%, but only 30 mins left before departure
    ev = EVDigitalTwin(
        ev_id="EV-V2G-URGENT",
        name="Hurried EV",
        battery_capacity_kwh=60.0,
        current_soc=80.0,
        minimum_soc=20.0,
        target_soc=85.0,
        arrival_time=8.0,
        departure_time=18.0
    )
    ev.update_schedule_status(17.5) # 30 mins left

    # Attempt V2G
    action, power_kw, overrides = ConstraintEngine.validate_action(
        ev=ev,
        proposed_action=2,
        current_hour=17.5,
        grid_load_pct=90.0,
        electricity_price=11.0
    )

    assert action != 2  # Discharging forbidden
