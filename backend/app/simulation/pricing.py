"""
GridWise AI - Electricity Pricing Models
Supports Fixed, Time-of-Use (TOU), and Dynamic Grid-Responsive pricing.
"""

from typing import Optional


class PricingModel:
    """Calculates electricity tariff in ₹/kWh."""

    def __init__(
        self,
        pricing_type: str = "tou",
        fixed_rate: float = 6.50,
        off_peak_rate: float = 4.10,
        normal_rate: float = 6.80,
        peak_rate: float = 9.20
    ):
        self.pricing_type = pricing_type.lower()
        self.fixed_rate = fixed_rate
        self.off_peak_rate = off_peak_rate
        self.normal_rate = normal_rate
        self.peak_rate = peak_rate

    def get_price(self, time_hours: float, current_demand_mw: Optional[float] = None) -> float:
        """Returns electricity tariff in ₹/kWh."""
        t = time_hours % 24.0

        if self.pricing_type == "fixed":
            return self.fixed_rate

        elif self.pricing_type == "dynamic":
            # Baseline dynamic: price scales linearly with grid stress
            demand = current_demand_mw if current_demand_mw is not None else 4.0
            # Normalized between 2.0 MW (min) and 7.0 MW (substation max)
            stress_factor = max(0.0, min(1.0, (demand - 2.0) / 5.0))
            return self.off_peak_rate + stress_factor * (self.peak_rate - self.off_peak_rate)

        else:
            # Time-of-Use (TOU) Standard
            # 00:00 - 06:00: Off-Peak Valley
            if 0.0 <= t < 6.0:
                return self.off_peak_rate
            # 17:00 - 21:00: Critical Evening Peak
            elif 17.0 <= t < 21.0:
                return self.peak_rate
            # 21:00 - 24:00: Shoulder Post-Peak
            elif 21.0 <= t < 24.0:
                return (self.normal_rate + self.peak_rate) / 2.0
            # 06:00 - 17:00: Standard Daytime
            else:
                return self.normal_rate

