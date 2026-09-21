from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class SimulationConfigSchema(BaseModel):
    name: Optional[str] = "Smart Grid Peak-Shaving Run"
    scenario: Optional[str] = "peak_shaving"
    duration_hours: float = Field(24.0, gt=0, le=168)
    timestep_minutes: int = Field(15, description="1, 5, 15, or 60 minutes")
    grid_capacity_kw: float = Field(100.0, gt=0)
    solar_capacity_kw: float = Field(40.0, ge=0)
    cloud_factor: float = Field(1.0, ge=0.0, le=1.0)
    num_evs: int = Field(5, ge=1, le=50)

class EnergyFlowSchema(BaseModel):
    solar_to_ev_kw: float = 0.0
    solar_to_grid_kw: float = 0.0
    grid_to_ev_kw: float = 0.0
    ev_to_grid_kw: float = 0.0
    flow_summary: str = "Standard Grid Operations"

class GridStateSchema(BaseModel):
    capacity_kw: float
    base_load_kw: float
    current_load_kw: float
    utilization_pct: float
    stress_level: str
    peak_status: bool

class SolarStateSchema(BaseModel):
    generation_kw: float
    peak_capacity_kw: float
    cloud_factor: float

class PriceStateSchema(BaseModel):
    current_price: float
    price_category: str
    currency: str = "INR (₹)"
    is_simulated: bool = True

class SimulationStateResponse(BaseModel):
    simulation_id: str
    status: str
    time: str
    hour: float
    step_index: int
    grid: GridStateSchema
    solar: SolarStateSchema
    price: PriceStateSchema
    evs: List[Dict[str, Any]]
    energy_flow: EnergyFlowSchema
    ai_decisions: List[Dict[str, Any]]
    total_charging_power_kw: float
    total_v2g_power_kw: float
    net_grid_load_kw: float

class BenchmarkSummary(BaseModel):
    energy_cost_traditional_inr: float
    energy_cost_ai_inr: float
    cost_savings_pct: float
    peak_load_traditional_kw: float
    peak_load_ai_kw: float
    peak_load_reduction_pct: float
    solar_used_traditional_kwh: float
    solar_used_ai_kwh: float
    solar_utilization_gain_pct: float
    v2g_energy_traditional_kwh: float
    v2g_energy_ai_kwh: float
    battery_cycles_traditional: float
    battery_cycles_ai: float
    ev_satisfaction_traditional_pct: float
    ev_satisfaction_ai_pct: float

class BenchmarkResponse(BaseModel):
    summary_comparison: BenchmarkSummary
    hourly_history_traditional: List[Dict[str, Any]]
    hourly_history_ai: List[Dict[str, Any]]

class ReportResponse(BaseModel):
    simulation_id: str
    title: str
    generated_at: str
    parameters: Dict[str, Any]
    metrics: Dict[str, Any]
    markdown_report: str
