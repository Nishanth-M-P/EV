"""
GridWise AI - Unified Live Telemetry Pipeline
Coordinates real-world data adapters, data normalization, and state aggregation:
REAL WORLD DATA SOURCES -> DATA NORMALIZATION -> GRIDWISE LIVE DATA ENGINE -> V2G CONTROL ENGINE
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.data_sources.adapters import (
    GridDataProvider,
    PriceDataProvider,
    RenewableDataProvider,
    WeatherDataProvider
)


class LiveTelemetryPipeline:
    """Central pipeline aggregating normalized Indian grid, market, and renewable feeds."""

    def __init__(
        self,
        grid_provider: Optional[GridDataProvider] = None,
        price_provider: Optional[PriceDataProvider] = None,
        renewable_provider: Optional[RenewableDataProvider] = None,
        weather_provider: Optional[WeatherDataProvider] = None
    ):
        self.grid_provider = grid_provider or GridDataProvider()
        self.price_provider = price_provider or PriceDataProvider()
        self.renewable_provider = renewable_provider or RenewableDataProvider()
        self.weather_provider = weather_provider or WeatherDataProvider()

    def fetch_all(self) -> Dict[str, Any]:
        """Collects fresh normalized telemetry from all active providers."""
        grid_data = self.grid_provider.get_current()
        price_data = self.price_provider.get_current()
        renewable_data = self.renewable_provider.get_current()
        weather_data = self.weather_provider.get_current()

        # Overall health assessment
        all_live = (
            grid_data["status"] == "LIVE" and
            price_data["status"] == "LIVE" and
            renewable_data["status"] == "LIVE"
        )
        data_health = "100% HEALTHY" if all_live else "DEGRADED"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "grid": grid_data,
            "price": price_data,
            "renewable": renewable_data,
            "weather": weather_data,
            "health": {
                "overall": data_health,
                "grid_source": grid_data["source"],
                "grid_status": grid_data["status"],
                "price_source": price_data["source"],
                "price_status": price_data["status"],
                "renewable_source": renewable_data["source"],
                "renewable_status": renewable_data["status"]
            }
        }
