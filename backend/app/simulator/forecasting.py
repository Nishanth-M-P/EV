from typing import Dict, Any, List
import math

class ForecastProvider:
    """
    Generates forward-looking predictive horizons (4-hour lookahead) for:
    - Solar PV irradiance generation
    - Feeder base demand load
    - Simulated dynamic electricity price
    Allows RL Agent to proactively schedule charging ahead of peak tariffs and solar ramps.
    """

    @staticmethod
    def get_4h_forecast(
        current_hour: float,
        energy_provider,
        horizon_hours: float = 4.0,
        timestep_minutes: int = 15
    ) -> Dict[str, Any]:
        step_hours = timestep_minutes / 60.0
        num_steps = int((horizon_hours * 60) / timestep_minutes)

        timeline = []
        solar_curve = []
        grid_load_curve = []
        price_curve = []

        for i in range(1, num_steps + 1):
            future_hour = (current_hour + i * step_hours) % 24.0
            h = int(future_hour)
            m = int((future_hour - h) * 60)
            time_label = f"{h:02d}:{m:02d}"

            # Query physical twins for future projection
            solar_kw = energy_provider.get_solar_generation(future_hour)
            price_info = energy_provider.get_electricity_price(future_hour)
            grid_state = energy_provider.get_grid_state(future_hour, charging_kw=0.0, v2g_kw=0.0)

            timeline.append(time_label)
            solar_curve.append(round(solar_kw, 2))
            grid_load_curve.append(round(grid_state["base_load_kw"], 2))
            price_curve.append(round(price_info["current_price"], 2))

        # Strategic summary
        max_solar = max(solar_curve) if solar_curve else 0.0
        max_price = max(price_curve) if price_curve else 0.0
        min_price = min(price_curve) if price_curve else 0.0

        if max_solar > 25.0:
            summary = f"High solar ramp expected within horizon (peaking at {max_solar} kW). Deferring non-urgent load to maximize free solar self-consumption."
        elif max_price >= 9.0:
            summary = f"Peak tariff window approaching (up to ₹{max_price}/kWh). Preparing fleet batteries for potential V2G grid-support arbitrage."
        else:
            summary = f"Stable low tariff regime (₹{min_price}-₹{max_price}/kWh). Favorable window for steady baseline charging."

        return {
            "current_hour": round(current_hour, 2),
            "horizon_hours": horizon_hours,
            "timestep_minutes": timestep_minutes,
            "timeline": timeline,
            "forecast_solar_kw": solar_curve,
            "forecast_grid_load_kw": grid_load_curve,
            "forecast_price_inr": price_curve,
            "strategic_summary": summary
        }
