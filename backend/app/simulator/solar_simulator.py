import math
from typing import Dict, Any, List

class SolarSimulator:
    """
    Simulates photovoltaic (PV) solar generation profile across 24 hours.
    Takes into account peak capacity, cloud cover attenuation, and seasonal factors.
    """
    def __init__(
        self,
        solar_peak_capacity_kw: float = 40.0,
        cloud_factor: float = 1.0,
        season_factor: float = 1.0
    ):
        self.solar_peak_capacity_kw = float(solar_peak_capacity_kw)
        self.cloud_factor = max(0.0, min(1.0, float(cloud_factor)))  # 1.0 = clear sky, 0.2 = heavy overcast
        self.season_factor = max(0.5, min(1.2, float(season_factor)))

    def get_generation_at_hour(self, hour: float) -> float:
        """
        Solar Bell Curve between 06:00 and 19:00.
        Peak at ~12:30 - 13:00.
        """
        h = hour % 24.0
        if 6.0 <= h <= 18.5:
            # Solar elevation angle representation
            solar_phase = (h - 6.0) / 12.5 * math.pi
            insolation = math.sin(solar_phase) ** 1.6
            raw_gen = self.solar_peak_capacity_kw * insolation * self.cloud_factor * self.season_factor
            return round(max(0.0, raw_gen), 2)
        return 0.0

    def get_24h_profile(self) -> List[float]:
        return [self.get_generation_at_hour(float(h)) for h in range(24)]

    def to_dict(self, hour: float) -> Dict[str, Any]:
        return {
            "generation_kw": self.get_generation_at_hour(hour),
            "peak_capacity_kw": self.solar_peak_capacity_kw,
            "cloud_factor": self.cloud_factor,
            "season_factor": self.season_factor
        }
