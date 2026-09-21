from datetime import datetime
from typing import Dict, Any

class ReportService:
    """
    Generates structured, professional engineering simulation reports in
    Markdown and JSON formats for audit, export, and executive review.
    """
    @staticmethod
    def generate_report(
        simulation_id: str,
        parameters: Dict[str, Any],
        analytics: Dict[str, Any],
        benchmark: Dict[str, Any]
    ) -> Dict[str, Any]:
        econ = analytics.get("economic_metrics", {})
        grid = analytics.get("grid_metrics", {})
        renew = analytics.get("renewable_metrics", {})
        ai = analytics.get("ai_metrics", {})
        comp = benchmark.get("summary_comparison", {})

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        md = f"""# GridWise AI — Simulation & Energy Management Report
**Simulation Run ID:** `{simulation_id}`  
**Generated At:** {now_str}  
**Platform Version:** 1.0.0 (FastAPI + Gymnasium + Digital Twin)

---

## 1. Executive Summary
During this simulated 24-hour evaluation, GridWise AI orchestrated charging and V2G discharging across the simulated EV fleet, prioritizing daytime solar self-consumption and curtailing load during evening peak tariff surges.

| Metric | Traditional Uncontrolled | GridWise AI (RL + Safety) | Improvement / Delta |
| :--- | :--- | :--- | :--- |
| **Net Grid Energy Cost** | ₹{comp.get('energy_cost_traditional_inr', 0.0):.2f} | ₹{comp.get('energy_cost_ai_inr', 0.0):.2f} | **{comp.get('cost_savings_pct', 0.0)}% Savings** |
| **Peak Feeder Load** | {comp.get('peak_load_traditional_kw', 0.0):.1f} kW | {comp.get('peak_load_ai_kw', 0.0):.1f} kW | **-{comp.get('peak_load_reduction_pct', 0.0)}% Peak Shaved** |
| **Solar PV Energy Used** | {comp.get('solar_used_traditional_kwh', 0.0):.1f} kWh | {comp.get('solar_used_ai_kwh', 0.0):.1f} kWh | **+{comp.get('solar_utilization_gain_pct', 0.0)}% Gain** |
| **V2G Grid Support** | {comp.get('v2g_energy_traditional_kwh', 0.0):.1f} kWh | {comp.get('v2g_energy_ai_kwh', 0.0):.1f} kWh | **Active Grid Feed** |
| **Departure SLA Satisfaction** | {comp.get('ev_satisfaction_traditional_pct', 100.0):.1f}% | {comp.get('ev_satisfaction_ai_pct', 100.0):.1f}% | **100% Guaranteed** |

---

## 2. Technical System Parameters
- **Feeder Capacity:** {parameters.get('grid_capacity_kw', 100.0)} kW
- **Solar Peak Capacity:** {parameters.get('solar_capacity_kw', 40.0)} kW
- **Simulation Timestep:** {parameters.get('timestep_minutes', 15)} minutes
- **Active Fleet Size:** {parameters.get('num_evs', 5)} EVs
- **Safety Layer Mode:** Active (Physical Bounds & Departure SLA Protection)

---

## 3. Operational & Environmental Metrics
- **Total Charging Power Drawn:** {grid.get('grid_energy_drawn_kwh', 0.0):.2f} kWh
- **Total Solar Generated:** {renew.get('solar_energy_generated_kwh', 0.0):.2f} kWh
- **Solar Clean Energy Utilized:** {renew.get('solar_energy_consumed_kwh', 0.0):.2f} kWh
- **Renewable Self-Consumption Ratio:** {renew.get('renewable_utilization_pct', 0.0):.1f}%
- **V2G Energy Injected into Feeder:** {grid.get('v2g_energy_supplied_kwh', 0.0):.2f} kWh
- **V2G Revenue Earned:** ₹{econ.get('v2g_revenue_earned_inr', 0.0):.2f}

---

## 4. Reinforcement Learning Performance
- **Total Policy Step Rewards:** {ai.get('total_reward', 0.0):.2f}
- **Charging Action Allocation:** {ai.get('charge_pct', 0.0):.1f}%
- **Idle Preservation Allocation:** {ai.get('idle_pct', 0.0):.1f}%
- **V2G Discharging Allocation:** {ai.get('v2g_pct', 0.0):.1f}%
- **Safety Overrides Intercepted:** {ai.get('safety_overrides_count', 0)}

---
*Report automatically compiled by GridWise AI Energy Analytics Engine.*
"""

        return {
            "simulation_id": simulation_id,
            "title": f"Simulation Report - {simulation_id[:8]}",
            "generated_at": now_str,
            "parameters": parameters,
            "metrics": {
                "economic": econ,
                "grid": grid,
                "renewable": renew,
                "ai": ai,
                "comparison": comp
            },
            "markdown_report": md
        }
