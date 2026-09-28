"""
GridWise AI - Grid Demand Profile Modeling
Generates realistic 24-hour diurnal load curves with morning and evening peaks.
"""

from typing import List, Dict, Any, Optional
import numpy as np


class GridModel:
    """Simulates realistic utility grid base demand without EV charging."""

    def __init__(
        self,
        duration_hours: int = 24,
        timestep_minutes: int = 15,
        base_peak_mw: float = 5.20,
        substation_limit_mw: float = 7.00,
        noise_std_mw: float = 0.05,
        random_seed: int = 42
    ):
        self.duration_hours = duration_hours
        self.timestep_minutes = timestep_minutes
        self.base_peak_mw = base_peak_mw
        self.substation_limit_mw = substation_limit_mw
        self.noise_std_mw = noise_std_mw
        self.random_seed = random_seed

        self.total_steps = int((duration_hours * 60) / timestep_minutes)
        self.dt_hours = timestep_minutes / 60.0

        # Precompute deterministic synthetic base profile
        self.base_demand_mw = self._generate_profile()

    def _generate_profile(self) -> np.ndarray:
        rng = np.random.default_rng(self.random_seed)
        profile = np.zeros(self.total_steps, dtype=np.float32)

        for step in range(self.total_steps):
            t = step * self.dt_hours  # hour in [0.0, 24.0)

            # 1. Base Overnight Load (Baseline ~1.8 to 2.2 MW)
            base = 2.0

            # 2. Daytime Activity Bell Curve (07:00 to 20:00)
            daytime = 1.4 * np.exp(-((t - 13.0) ** 2) / 32.0)

            # 3. Morning Workday Inrush Peak (08:00 - 11:00)
            morning_peak = 0.8 * np.exp(-((t - 9.5) ** 2) / 3.0)

            # 4. Prominent Evening Peak (17:00 - 21:00, centered at 19:00)
            evening_peak = 1.8 * np.exp(-((t - 19.0) ** 2) / 4.0)

            # 5. Stochastic Noise
            noise = rng.normal(0.0, self.noise_std_mw)

            total_mw = base + daytime + morning_peak + evening_peak + noise
            # Bound below by overnight trough and above by realistic safety margin
            profile[step] = max(1.5, min(self.substation_limit_mw - 0.2, total_mw))

        return profile

    def get_demand(self, step: int) -> float:
        """Returns base grid load in MW at step index."""
        idx = step % self.total_steps
        return float(self.base_demand_mw[idx])

    def get_time_hours(self, step: int) -> float:
        return (step % self.total_steps) * self.dt_hours

    def get_time_str(self, step: int) -> str:
        t = self.get_time_hours(step)
        hour = int(t)
        minute = int((t - hour) * 60)
        return f"{hour:02d}:{minute:02d}"

