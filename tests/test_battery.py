import pytest
from backend.app.simulator.battery_simulator import BatterySimulator

def test_battery_initialization():
    bat = BatterySimulator(capacity_kwh=60.0, initial_soc=50.0, minimum_soc=20.0, maximum_soc=90.0)
    assert bat.capacity_kwh == 60.0
    assert bat.current_soc == 50.0
    assert bat.stored_energy_kwh == 30.0
    assert bat.minimum_soc == 20.0
    assert bat.maximum_soc == 90.0
    assert bat.battery_health == 100.0

def test_battery_charging_within_bounds():
    bat = BatterySimulator(capacity_kwh=60.0, initial_soc=50.0, maximum_soc=90.0, charging_efficiency=1.0)
    # Charge at 10 kW for 1 hour -> adds 10 kWh -> delta SOC = (10/60)*100 = 16.67% -> new SOC ~ 66.67%
    res = bat.charge(power_kw=10.0, timestep_hours=1.0)
    assert res["actual_power_kw"] == 10.0
    assert res["energy_kwh"] == 10.0
    assert abs(bat.current_soc - 66.67) < 0.1

def test_battery_charging_clamps_to_max_soc():
    bat = BatterySimulator(capacity_kwh=50.0, initial_soc=80.0, maximum_soc=85.0, charging_efficiency=1.0)
    # 50 kWh capacity, room to 85% is 5% = 2.5 kWh
    res = bat.charge(power_kw=10.0, timestep_hours=1.0) # Requests 10 kWh
    assert bat.current_soc == 85.0
    assert res["energy_kwh"] == 2.5
    assert bat.current_soc <= 100.0

def test_battery_discharging_v2g_within_bounds():
    bat = BatterySimulator(capacity_kwh=60.0, initial_soc=60.0, minimum_soc=20.0, discharging_efficiency=1.0)
    # Discharge 6 kW for 1 hour -> removes 6 kWh -> delta SOC = 10% -> new SOC = 50%
    res = bat.discharge(power_kw=6.0, timestep_hours=1.0)
    assert res["actual_power_kw"] == -6.0
    assert res["energy_kwh"] == 6.0
    assert bat.current_soc == 50.0

def test_battery_discharging_clamps_to_min_soc():
    bat = BatterySimulator(capacity_kwh=50.0, initial_soc=25.0, minimum_soc=20.0, discharging_efficiency=1.0)
    # Room to 20% is 5% = 2.5 kWh
    res = bat.discharge(power_kw=10.0, timestep_hours=1.0)
    assert bat.current_soc == 20.0
    assert res["energy_kwh"] == 2.5
    assert bat.current_soc >= 0.0

def test_battery_cycle_counting():
    bat = BatterySimulator(capacity_kwh=50.0, initial_soc=20.0, minimum_soc=20.0, maximum_soc=100.0, charging_efficiency=1.0)
    # 50 kWh throughput = 0.5 full cycle
    bat.charge(power_kw=50.0, timestep_hours=1.0) # 40 kWh to 100%
    assert bat.cycle_count > 0.0
