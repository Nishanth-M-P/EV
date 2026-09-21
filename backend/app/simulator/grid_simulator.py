import math
from typing import Dict, Any, List

class GridSimulator:
    """
    Digital twin representing the local distribution grid feeder.
    Tracks capacity, base demand curves, aggregate EV charging/discharging,
    utilization %, stress levels, and peak status.
    """
    def __init__(
        self,
        grid_capacity_kw: float = 100.0,
        peak_threshold_pct: float = 80.0
    ):
        self.grid_capacity_kw = float(grid_capacity_kw)
        self.peak_threshold_pct = float(peak_threshold_pct)
        self.peak_threshold_kw = (self.peak_threshold_pct / 100.0) * self.grid_capacity_kw
        
        # 24-Hour Base Demand Profile
        self.base_demand_curve = self._generate_base_demand_curve()
        self.current_base_load_kw: float = 0.0
        self.net_grid_load_kw: float = 0.0

    def _generate_base_demand_curve(self) -> List[float]:
        """
        Generates realistic 24-hour baseline municipal/commercial demand:
        - Night valley (00:00 - 05:00): ~25-35% capacity
        - Morning peak (07:00 - 10:00): ~65-75% capacity
        - Afternoon steady (11:00 - 16:00): ~50-60% capacity
        - Evening peak (17:00 - 21:00): ~80-92% capacity
        """
        curve = []
        for h in range(24):
            if 0 <= h < 6:
                pct = 28.0 + 4.0 * math.sin(h / 2.0)
            elif 6 <= h < 12:
                pct = 58.0 + 15.0 * math.sin((h - 6) / 6.0 * math.pi)
            elif 12 <= h < 17:
                pct = 52.0 + 8.0 * math.sin((h - 12) / 5.0 * math.pi)
            elif 17 <= h < 22:
                pct = 78.0 + 12.0 * math.sin((h - 17) / 5.0 * math.pi)
            else:
                pct = 40.0
            load_kw = (pct / 100.0) * self.grid_capacity_kw
            curve.append(round(min(load_kw, self.grid_capacity_kw * 0.95), 2))
        return curve

    def get_base_load_at_hour(self, hour: float) -> float:
        """Interpolates base load for continuous timesteps."""
        h_idx = int(hour) % 24
        next_idx = (h_idx + 1) % 24
        frac = hour - int(hour)
        load = self.base_demand_curve[h_idx] * (1.0 - frac) + self.base_demand_curve[next_idx] * frac
        return round(load, 2)

    def calculate_grid_state(
        self,
        hour: float,
        ev_charging_power_kw: float = 0.0,
        ev_v2g_power_kw: float = 0.0,
        solar_surplus_kw: float = 0.0
    ) -> Dict[str, Any]:
        self.current_base_load_kw = self.get_base_load_at_hour(hour)
        
        # Net grid load = Base + EV Charging - V2G - Solar backfed to grid
        raw_net = self.current_base_load_kw + ev_charging_power_kw - ev_v2g_power_kw - solar_surplus_kw
        self.net_grid_load_kw = max(0.0, raw_net)
        
        utilization_pct = (self.net_grid_load_kw / self.grid_capacity_kw) * 100.0
        is_peak = self.net_grid_load_kw >= self.peak_threshold_kw
        
        if utilization_pct >= 90.0:
            stress_level = "CRITICAL"
        elif utilization_pct >= 75.0:
            stress_level = "HIGH"
        elif utilization_pct >= 50.0:
            stress_level = "MEDIUM"
        else:
            stress_level = "LOW"

        return {
            "capacity_kw": self.grid_capacity_kw,
            "base_load_kw": round(self.current_base_load_kw, 2),
            "current_load_kw": round(self.net_grid_load_kw, 2),
            "net_grid_load_kw": round(self.net_grid_load_kw, 2),
            "utilization_pct": round(utilization_pct, 1),
            "stress_level": stress_level,
            "peak_threshold_kw": round(self.peak_threshold_kw, 2),
            "peak_status": is_peak
        }
