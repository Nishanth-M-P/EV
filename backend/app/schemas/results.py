"""
GridWise AI - Results & Benchmark Schemas
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class StrategyMetrics(BaseModel):
    strategy: str
    peak_demand_mw: float
    baseline_peak_mw: float
    peak_reduction_pct: float
    total_cost: float
    v2g_energy_kwh: float
    charging_energy_kwh: float
    valley_to_peak_ratio: float
    soc_compliance_pct: float
    battery_throughput_efc: float


class BenchmarkSummary(BaseModel):
    fleet_size: int
    duration_hours: int
    s1_peak_mw: float
    s2_peak_mw: float
    s3_peak_mw: float
    peak_reduction_pct_vs_s1: float
    cost_reduction_pct_vs_s1: float
    v2g_energy_delivered_kwh: float
    drl_soc_compliance_pct: float


class BenchmarkComparisonResponse(BaseModel):
    uncontrolled: StrategyMetrics
    rule_based: StrategyMetrics
    drl: StrategyMetrics
    summary: BenchmarkSummary


class DRLTrainRequest(BaseModel):
    timesteps: int = 5000
    learning_rate: Optional[float] = 0.0003
    batch_size: Optional[int] = 64
    algorithm: Optional[str] = "PPO"


class DRLTrainStatusResponse(BaseModel):
    status: str
    message: str
    model_name: Optional[str] = None
    timesteps: Optional[int] = None
    training_duration_seconds: Optional[float] = None
    model_path: Optional[str] = None

