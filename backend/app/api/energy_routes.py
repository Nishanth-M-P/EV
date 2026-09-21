from fastapi import APIRouter
from typing import Dict, Any
from backend.app.simulator.forecasting import ForecastProvider

def create_energy_router(sim_service):
    router = APIRouter(prefix="/api", tags=["Energy Profiles & Forecasting"])

    @router.get("/grid")
    @router.get("/energy/grid")
    def get_grid_profile():
        engine = sim_service.engine
        grid_sim = engine.energy_provider.grid
        current_state = grid_sim.calculate_grid_state(engine.current_hour)
        
        return {
            "max_capacity_kw": grid_sim.grid_capacity_kw,
            "peak_threshold_kw": grid_sim.peak_threshold_kw,
            "hours": list(range(24)),
            "grid_load_profile_kw": grid_sim.base_demand_curve,
            "baseline_hourly_kw": grid_sim.base_demand_curve,
            "current_state": {
                "grid_load_kw": current_state["base_load_kw"],
                "grid_load_pct": current_state["utilization_pct"],
                "grid_stress_level": current_state["stress_level"],
                "solar_generation_kw": engine.energy_provider.get_solar_generation(engine.current_hour),
                "electricity_price": engine.energy_provider.get_electricity_price(engine.current_hour)["current_price"]
            }
        }

    @router.get("/prices")
    @router.get("/energy/price")
    def get_price_profile():
        price_sim = sim_service.engine.energy_provider.price
        return {
            "currency": price_sim.currency,
            "label": price_sim.LABEL,
            "hours": list(range(24)),
            "price_profile": price_sim.price_profile,
            "hourly_prices": price_sim.price_profile
        }

    @router.get("/renewables")
    @router.get("/energy/solar")
    def get_renewables_profile():
        solar_sim = sim_service.engine.energy_provider.solar
        profile = solar_sim.get_24h_profile()
        return {
            "max_solar_capacity_kw": solar_sim.solar_peak_capacity_kw,
            "cloud_factor": solar_sim.cloud_factor,
            "hours": list(range(24)),
            "solar_profile": profile,
            "hourly_generation_kw": profile
        }

    @router.get("/energy/forecast")
    @router.get("/forecast")
    def get_energy_forecast(horizon_hours: float = 4.0):
        engine = sim_service.engine
        return ForecastProvider.get_4h_forecast(
            current_hour=engine.current_hour,
            energy_provider=engine.energy_provider,
            horizon_hours=horizon_hours,
            timestep_minutes=engine.timestep_minutes
        )

    return router
