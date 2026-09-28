"""
GridWise AI - Data Fusion: Normalizer, Validator, Freshness Monitor
Enforces scientific boundaries and data hygiene without fake random numbers.
"""

import time
from typing import Dict, Any, Tuple

class DataFreshnessMonitor:
    @staticmethod
    def evaluate(last_updated_timestamp: float, live_threshold_sec: float = 30.0, stale_threshold_sec: float = 300.0) -> Tuple[str, int]:
        now = time.time()
        age = max(0, int(now - last_updated_timestamp))
        if age <= live_threshold_sec:
            return "LIVE", age
        elif age <= stale_threshold_sec:
            return "STALE", age
        return "OFFLINE", age


class UnitNormalizer:
    @staticmethod
    def gw_to_mw(gw: float) -> float:
        return round(gw * 1000.0, 3)

    @staticmethod
    def mw_to_gw(mw: float) -> float:
        return round(mw / 1000.0, 4)

    @staticmethod
    def kw_to_mw(kw: float) -> float:
        return round(kw / 1000.0, 6)

    @staticmethod
    def mw_to_kw(mw: float) -> float:
        return round(mw * 1000.0, 3)


class PhysicalBoundsValidator:
    @staticmethod
    def validate_grid_frequency(freq: float) -> bool:
        # Standard Indian Grid Code IEGC safe operating range: 49.50 - 50.20 Hz
        return 47.0 <= freq <= 53.0

    @staticmethod
    def validate_soc(soc: float) -> bool:
        return 0.0 <= soc <= 100.0

    @staticmethod
    def validate_power_kw(power_kw: float, max_charge_kw: float = 22.0, max_discharge_kw: float = 22.0) -> bool:
        return -max_discharge_kw <= power_kw <= max_charge_kw
