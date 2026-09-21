import pytest
from backend.app.simulator.solar_simulator import SolarSimulator
from backend.app.simulator.price_simulator import PriceSimulator

def test_solar_daily_curve_and_cloud_factor():
    solar = SolarSimulator(solar_peak_capacity_kw=50.0, cloud_factor=1.0)
    
    # Night hours should be 0
    assert solar.get_generation_at_hour(1.0) == 0.0
    assert solar.get_generation_at_hour(22.0) == 0.0

    # Midday peak should be high
    peak_gen = solar.get_generation_at_hour(12.5)
    assert peak_gen > 30.0
    assert peak_gen <= 50.0

    # Overcast attenuation
    overcast = SolarSimulator(solar_peak_capacity_kw=50.0, cloud_factor=0.3)
    cloudy_peak = overcast.get_generation_at_hour(12.5)
    assert cloudy_peak < peak_gen
    assert abs(cloudy_peak - peak_gen * 0.3) < 1.0

def test_price_profile_and_categories():
    price_sim = PriceSimulator()
    
    off_peak = price_sim.get_price_at_hour(3.0)
    assert off_peak["price_category"] == "Off-Peak"
    assert off_peak["current_price"] < 6.0
    assert off_peak["is_simulated"] is True
    assert off_peak["label"] == "Simulated Electricity Price"

    peak = price_sim.get_price_at_hour(19.0)
    assert peak["price_category"] == "Peak"
    assert peak["current_price"] >= 9.5
