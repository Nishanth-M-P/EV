import math
import numpy as np

class EnergyService:
    """
    Manages 24-hour profiles for:
    - Electricity Price (₹/kWh) - Time of Use (TOU) & Peak Pricing
    - Solar / Renewable Energy Generation (kW)
    - Grid Base Load (kW or % capacity)
    """

    def __init__(self, max_grid_capacity_kw: float = 100.0, max_solar_capacity_kw: float = 40.0):
        self.max_grid_capacity_kw = max_grid_capacity_kw
        self.max_solar_capacity_kw = max_solar_capacity_kw
        
        # Default 24-hour profiles (hour 0 to 23)
        self.hours = list(range(24))
        self.price_profile = self._generate_price_profile()
        self.solar_profile = self._generate_solar_profile()
        self.grid_load_profile = self._generate_grid_load_profile()

    def _generate_price_profile(self) -> list[float]:
        """
        TOU Pricing (₹/kWh):
        - Off-peak (23:00 - 06:00): ₹4.0 - ₹4.5 / kWh
        - Mid-peak (06:00 - 16:00): ₹6.0 - ₹7.5 / kWh
        - Peak demand (16:00 - 22:00): ₹10.0 - ₹12.5 / kWh
        """
        prices = []
        for h in range(24):
            if 0 <= h < 6 or h >= 23:
                price = 4.0 + 0.3 * math.sin(h / 3.0)
            elif 6 <= h < 16:
                price = 6.5 + 1.0 * math.sin((h - 6) / 10.0 * math.pi)
            else:  # 16 to 22 peak
                price = 10.5 + 2.0 * math.sin((h - 16) / 6.0 * math.pi)
            prices.append(round(price, 2))
        return prices

    def _generate_solar_profile(self) -> list[float]:
        """
        Solar Generation profile (kW):
        Bell curve starting ~06:00, peaking at 13:00 (~38 kW), dropping to 0 by 19:00.
        """
        solar = []
        for h in range(24):
            if 6 <= h <= 18:
                # Bell curve peak at hour 13
                factor = math.sin((h - 6) / 12.0 * math.pi)
                val = self.max_solar_capacity_kw * (factor ** 1.5)
            else:
                val = 0.0
            solar.append(round(val, 2))
        return solar

    def _generate_grid_load_profile(self) -> list[float]:
        """
        Base Grid Load profile (kW out of max capacity):
        Morning peak (08:00 - 10:00) ~65-75 kW
        Evening peak (18:00 - 21:00) ~85-95 kW (High grid stress)
        Night valley (01:00 - 05:00) ~25-35 kW
        """
        loads = []
        for h in range(24):
            if 1 <= h <= 5:
                load = 30.0 + 5.0 * math.sin(h)
            elif 6 <= h <= 12:
                load = 60.0 + 15.0 * math.sin((h - 6) / 6.0 * math.pi)
            elif 13 <= h <= 17:
                load = 55.0 + 10.0 * math.sin((h - 13) / 4.0 * math.pi)
            elif 18 <= h <= 22:
                load = 82.0 + 13.0 * math.sin((h - 18) / 4.0 * math.pi)
            else:
                load = 40.0
            loads.append(round(min(load, self.max_grid_capacity_kw * 0.98), 2))
        return loads

    def get_state_at_hour(self, hour: float) -> dict:
        """
        Interpolates grid parameters for fractional simulation steps (e.g. 14.25).
        """
        h_idx = int(hour) % 24
        next_idx = (h_idx + 1) % 24
        frac = hour - int(hour)

        price = self.price_profile[h_idx] * (1 - frac) + self.price_profile[next_idx] * frac
        solar = self.solar_profile[h_idx] * (1 - frac) + self.solar_profile[next_idx] * frac
        grid_load = self.grid_load_profile[h_idx] * (1 - frac) + self.grid_load_profile[next_idx] * frac

        grid_pct = (grid_load / self.max_grid_capacity_kw) * 100.0
        
        if grid_pct >= 90:
            stress = "CRITICAL"
        elif grid_pct >= 75:
            stress = "HIGH"
        elif grid_pct >= 50:
            stress = "MEDIUM"
        else:
            stress = "LOW"

        return {
            "hour": round(hour, 2),
            "electricity_price": round(price, 2),
            "solar_generation_kw": round(solar, 2),
            "grid_load_kw": round(grid_load, 2),
            "grid_max_capacity_kw": self.max_grid_capacity_kw,
            "grid_load_pct": round(grid_pct, 1),
            "grid_stress_level": stress,
            "is_peak_price": price >= 9.0,
            "is_high_solar": solar >= (self.max_solar_capacity_kw * 0.5)
        }
