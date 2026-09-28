"""
GridWise AI - Performance Metrics Calculator
Quantifies peak demand, shaving percentage, TOU cost, V2G energy, and battery life.
"""

from typing import Dict, Any, List
import numpy as np


def compute_simulation_metrics(
    strategy_name: str,
    grid_demand_mw_history: List[float],
    baseline_demand_mw_history: List[float],
    ev_power_kw_history: List[float],
    cost_history: List[float],
    v2g_energy_kwh: float,
    charging_energy_kwh: float,
    fleet_socs_at_departure: List[float],
    required_socs: List[float],
    battery_capacities: List[float],
    dt_hours: float = 0.25
) -> Dict[str, Any]:
    peak_demand = float(np.max(grid_demand_mw_history)) if grid_demand_mw_history else 0.0
    baseline_peak = float(np.max(baseline_demand_mw_history)) if baseline_demand_mw_history else 0.0

    peak_reduction_pct = float(
        ((baseline_peak - peak_demand) / baseline_peak * 100.0) if baseline_peak > 0 else 0.0
    )

    total_cost = float(np.sum(cost_history)) if cost_history else 0.0

    # Valley-to-Peak Ratio (VPR) = P_min / P_max
    min_demand = float(np.min(grid_demand_mw_history)) if grid_demand_mw_history else 0.0
    vpr = float(min_demand / peak_demand) if peak_demand > 0 else 0.0

    # SOC Compliance
    compliant_count = sum(
        1 for actual, req in zip(fleet_socs_at_departure, required_socs) if actual >= (req - 1e-4)
    )
    total_departed = len(fleet_socs_at_departure)
    soc_compliance_pct = float(
        (compliant_count / total_departed * 100.0) if total_departed > 0 else 100.0
    )

    # Battery Throughput in Equivalent Full Cycles (EFC)
    total_energy_kwh = v2g_energy_kwh + charging_energy_kwh
    total_capacity_kwh = sum(battery_capacities) if battery_capacities else 3000.0
    efc = float(total_energy_kwh / (2.0 * total_capacity_kwh)) if total_capacity_kwh > 0 else 0.0

    return {
        "strategy": strategy_name,
        "peak_demand_mw": float(np.round(peak_demand, 3)),
        "baseline_peak_mw": float(np.round(baseline_peak, 3)),
        "peak_reduction_pct": float(np.round(peak_reduction_pct, 2)),
        "total_cost": float(np.round(total_cost, 2)),
        "v2g_energy_kwh": float(np.round(v2g_energy_kwh, 2)),
        "charging_energy_kwh": float(np.round(charging_energy_kwh, 2)),
        "valley_to_peak_ratio": float(np.round(vpr, 3)),
        "soc_compliance_pct": float(np.round(soc_compliance_pct, 2)),
        "battery_throughput_efc": float(np.round(efc, 4))
    }

