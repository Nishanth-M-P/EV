from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class EconomicMetrics(BaseModel):
    total_charging_cost_inr: float
    v2g_revenue_earned_inr: float
    net_energy_cost_inr: float
    avg_cost_per_kwh_inr: float

class GridMetrics(BaseModel):
    peak_grid_load_kw: float
    v2g_energy_supplied_kwh: float
    grid_energy_drawn_kwh: float

class RenewableMetrics(BaseModel):
    solar_energy_consumed_kwh: float
    renewable_utilization_pct: float

class AIMetrics(BaseModel):
    total_reward: float
    avg_reward: float
    charge_pct: float
    idle_pct: float
    v2g_pct: float
    safety_overrides_count: int

class AnalyticsSummaryResponse(BaseModel):
    economic_metrics: EconomicMetrics
    grid_metrics: GridMetrics
    renewable_metrics: RenewableMetrics
    ai_metrics: AIMetrics
