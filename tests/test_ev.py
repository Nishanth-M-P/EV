import pytest
from backend.app.simulator.ev_simulator import EVDigitalTwin

def test_ev_initial_status_and_schedule():
    ev = EVDigitalTwin(
        ev_id="EV-TEST-1",
        name="Test EV",
        battery_capacity_kwh=60.0,
        current_soc=40.0,
        arrival_time=9.0,
        departure_time=17.0,
        target_soc=80.0
    )
    
    # Before arrival
    ev.update_schedule_status(8.0)
    assert ev.status == "WAITING"
    assert not ev.is_connected

    # During stay
    ev.update_schedule_status(10.0)
    assert ev.status == "IDLE"
    assert ev.is_connected

    # After departure
    ev.update_schedule_status(18.0)
    assert ev.status == "DEPARTED"
    assert not ev.is_connected

def test_ev_apply_power_limits():
    ev = EVDigitalTwin(
        ev_id="EV-TEST-2",
        name="Test EV",
        battery_capacity_kwh=50.0,
        current_soc=40.0,
        arrival_time=8.0,
        departure_time=18.0,
        max_charge_power_kw=7.4,
        max_discharge_power_kw=5.0
    )
    ev.update_schedule_status(9.0)

    # Request excessive charge power (e.g. 50 kW) -> clamped to 7.4 kW
    res = ev.apply_power(50.0, timestep_hours=0.25)
    assert res["actual_power_kw"] <= 7.4
    assert ev.status == "CHARGING"

    # Request excessive discharge power (e.g. -20 kW) -> clamped to -5.0 kW
    res = ev.apply_power(-20.0, timestep_hours=0.25)
    assert abs(res["actual_power_kw"]) <= 5.0
    assert ev.status == "DISCHARGING"
