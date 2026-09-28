"""
GridWise AI - Central Real-Time State
Maintains exactly one authoritative external observation state (PRD Section 45).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any

@dataclass
class RealTimeGridState:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    demand_mw: float = 13740.0
    demand_gw: float = 13.74
    supply_mw: float = 14200.0
    supply_gw: float = 14.20
    supply_margin_mw: float = 460.0
    frequency_hz: float = 49.96
    solar_mw: float = 1990.0
    wind_mw: float = 2410.0
    hydro_mw: float = 620.0
    renewable_mw: float = 5020.0
    renewable_share: float = 36.54
    market_price: float = 8.20
    market_block: str = "18:45–19:00"
    grid_stress: str = "NORMAL"
    grid_state: str = "NORMAL"
    data_status: str = "LIVE"
    grid_source: str = "KPTCL SLDC"
    price_source: str = "IEX RTM"
    renewable_source: str = "Karnataka SLDC / NIWE"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_status"] = self.data_status
        return d
