import pytest
from backend.app.simulator.ev_simulator import EVDigitalTwin
from backend.app.ai.constraints import ConstraintEngine

def test_departure_urgency_forces_charge():
    # EV needs 30% SOC (18 kWh), max charge rate 7.4 kW -> needs ~2.5 hours
    # Only 1.0 hour remaining before departure!
    ev = EVDigitalTwin(
        ev_id="EV-URGENT",
        name="Urgent EV",
        battery_capacity_kwh=60.0,
        current_soc=50.0,
        target_soc=85.0,
        arrival_time=8.0,
        departure_time=18.0,
        max_charge_power_kw=7.4
    )
    ev.update_schedule_status(17.0)

    # RL tries to IDLE (0) because price is peak
    action, power_kw, overrides = ConstraintEngine.validate_action(
        ev=ev,
        proposed_action=0,
        current_hour=17.0,
        grid_load_pct=85.0,
        electricity_price=12.0
    )

    assert action == 1  # Forced CHARGE
    assert power_kw > 0.0
    assert any("DEPARTURE SLA GUARANTEE" in o for o in overrides)

def test_overcharge_prevented():
    ev = EVDigitalTwin(
        ev_id="EV-FULL",
        name="Full EV",
        battery_capacity_kwh=50.0,
        current_soc=100.0,
        maximum_soc=100.0,
        target_soc=100.0,
        arrival_time=8.0,
        departure_time=18.0
    )
    ev.update_schedule_status(10.0)

    # RL tries to charge (1)
    action, power_kw, overrides = ConstraintEngine.validate_action(
        ev=ev,
        proposed_action=1,
        current_hour=10.0,
        grid_load_pct=40.0,
        electricity_price=4.0
    )

    assert action == 0  # Blocked to IDLE
    assert power_kw == 0.0
    assert any("MAX SOC LIMIT" in o for o in overrides)

def test_disconnected_ev_blocked():
    ev = EVDigitalTwin(
        ev_id="EV-AWAY",
        name="Away EV",
        battery_capacity_kwh=50.0,
        current_soc=30.0,
        arrival_time=10.0,
        departure_time=18.0
    )
    # Current time is 8.0 (EV has not arrived)
    ev.update_schedule_status(8.0)

    action, power_kw, overrides = ConstraintEngine.validate_action(
        ev=ev,
        proposed_action=1,
        current_hour=8.0,
        grid_load_pct=40.0,
        electricity_price=4.0
    )

    assert action == 0
    assert power_kw == 0.0
