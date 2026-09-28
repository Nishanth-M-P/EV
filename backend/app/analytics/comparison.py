"""
GridWise AI - Multi-Strategy Benchmark Comparison Engine
Runs identical EV fleet and grid scenarios across Uncontrolled (S1),
Rule-Based (S2), and DRL-V2G (S3) for reproducible scientific comparison.
"""

from typing import Dict, Any, Optional
from pathlib import Path
import json

from backend.app.config import AppConfig, load_config
from backend.app.simulation.grid import GridModel
from backend.app.simulation.pricing import PricingModel
from backend.app.simulation.ev import EVFleet
from backend.app.simulation.v2g import V2GManager
from backend.app.strategies.uncontrolled import UncontrolledStrategy
from backend.app.strategies.rule_based import RuleBasedStrategy
from backend.app.strategies.drl import DRLStrategy
from backend.app.analytics.metrics import compute_simulation_metrics
from backend.app.utils.logger import logger

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "results"
MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


def run_strategy_simulation(
    strategy: Any,
    config: AppConfig,
    fleet_seed: int = 42
) -> Dict[str, Any]:
    # 1. Create identical grid and pricing
    grid = GridModel(
        duration_hours=config.simulation.duration_hours,
        timestep_minutes=config.simulation.timestep_minutes,
        base_peak_mw=config.grid.base_peak_mw,
        substation_limit_mw=config.grid.substation_limit_mw,
        noise_std_mw=config.grid.noise_std_mw,
        random_seed=fleet_seed
    )
    pricing = PricingModel(
        pricing_type=config.pricing.type,
        off_peak_rate=config.pricing.off_peak_rate,
        normal_rate=config.pricing.normal_rate,
        peak_rate=config.pricing.peak_rate
    )
    fleet = EVFleet.create_synthetic_fleet(
        fleet_size=config.simulation.fleet_size,
        random_seed=fleet_seed
    )
    v2g = V2GManager()

    total_steps = grid.total_steps
    dt_hours = grid.dt_hours

    grid_demand_history = []
    base_demand_history = []
    ev_power_history = []
    cost_history = []
    soc_mean_history = []
    time_labels = []

    for step in range(total_steps):
        current_time = grid.get_time_hours(step)
        base_demand_mw = grid.get_demand(step)
        price = pricing.get_price(current_time, base_demand_mw)
        time_labels.append(grid.get_time_str(step))

        # Compute strategy power decisions
        power_actions = strategy.compute_power_actions(
            fleet=fleet,
            current_time_hours=current_time,
            dt_hours=dt_hours,
            grid_demand_mw=base_demand_mw,
            electricity_price=price
        )

        # Apply decisions to fleet
        step_net_ev_power_kw = 0.0
        for ev in fleet:
            req_power = power_actions.get(ev.ev_id, 0.0)
            actual_kw, _ = ev.apply_power(req_power, dt_hours, price)
            step_net_ev_power_kw += actual_kw

        # V2G accounting
        res = v2g.record_step(
            net_ev_power_kw=step_net_ev_power_kw,
            dt_hours=dt_hours,
            electricity_price=price,
            base_grid_power_mw=base_demand_mw
        )

        grid_demand_history.append(res["net_grid_mw"])
        base_demand_history.append(base_demand_mw)
        ev_power_history.append(step_net_ev_power_kw)
        cost_history.append(res["net_step_cost"])
        soc_mean_history.append(float(fleet.get_aggregate_telemetry(current_time)["average_soc"]))

    # Gather departure metrics
    fleet_socs = [ev.current_soc for ev in fleet]
    required_socs = [ev.required_departure_soc for ev in fleet]
    capacities = [ev.battery_capacity_kwh for ev in fleet]

    metrics = compute_simulation_metrics(
        strategy_name=strategy.name,
        grid_demand_mw_history=grid_demand_history,
        baseline_demand_mw_history=base_demand_history,
        ev_power_kw_history=ev_power_history,
        cost_history=cost_history,
        v2g_energy_kwh=v2g.discharging_energy_kwh,
        charging_energy_kwh=v2g.charging_energy_kwh,
        fleet_socs_at_departure=fleet_socs,
        required_socs=required_socs,
        battery_capacities=capacities,
        dt_hours=dt_hours
    )

    metrics["time_labels"] = time_labels
    metrics["grid_demand_history"] = grid_demand_history
    metrics["base_demand_history"] = base_demand_history
    metrics["ev_power_history"] = ev_power_history
    metrics["soc_mean_history"] = soc_mean_history
    metrics["cost_history"] = cost_history

    return metrics


def run_benchmark_comparison(
    config: Optional[AppConfig] = None,
    save_json: bool = True
) -> Dict[str, Any]:
    cfg = config or load_config()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Executing Benchmark Comparison: S1 Uncontrolled vs S2 Rule-Based vs S3 DRL...")

    # Load DRL model if available
    model = None
    model_path = MODELS_DIR / "ppo_v2g_latest.zip"
    if model_path.exists():
        try:
            from stable_baselines3 import PPO
            model = PPO.load(str(model_path))
            logger.info("Loaded trained PPO model for S3.")
        except Exception as e:
            logger.warning(f"Failed to load DRL model: {e}")

    s1 = UncontrolledStrategy()
    s2 = RuleBasedStrategy()
    s3 = DRLStrategy(model=model)

    res_s1 = run_strategy_simulation(s1, cfg, fleet_seed=cfg.simulation.random_seed)
    res_s2 = run_strategy_simulation(s2, cfg, fleet_seed=cfg.simulation.random_seed)
    res_s3 = run_strategy_simulation(s3, cfg, fleet_seed=cfg.simulation.random_seed)

    # Normalize metrics relative to Uncontrolled (S1) baseline
    s1_peak = res_s1["peak_demand_mw"]
    for res in [res_s1, res_s2, res_s3]:
        res["baseline_peak_mw"] = s1_peak
        res["peak_reduction_pct"] = round(
            max(0.0, (s1_peak - res["peak_demand_mw"]) / s1_peak * 100.0), 2
        )

    comparison_results = {
        "uncontrolled": res_s1,
        "rule_based": res_s2,
        "drl": res_s3,
        "summary": {
            "fleet_size": cfg.simulation.fleet_size,
            "duration_hours": cfg.simulation.duration_hours,
            "s1_peak_mw": res_s1["peak_demand_mw"],
            "s2_peak_mw": res_s2["peak_demand_mw"],
            "s3_peak_mw": res_s3["peak_demand_mw"],
            "peak_reduction_pct_vs_s1": round(
                ((res_s1["peak_demand_mw"] - res_s3["peak_demand_mw"]) / res_s1["peak_demand_mw"] * 100.0), 2
            ),
            "cost_reduction_pct_vs_s1": round(
                ((res_s1["total_cost"] - res_s3["total_cost"]) / res_s1["total_cost"] * 100.0), 2
            ) if res_s1["total_cost"] > 0 else 0.0,
            "v2g_energy_delivered_kwh": res_s3["v2g_energy_kwh"],
            "drl_soc_compliance_pct": res_s3["soc_compliance_pct"]
        }
    }

    if save_json:
        output_file = RESULTS_DIR / "benchmark_comparison.json"
        # Save a clean version without voluminous raw arrays to benchmark_summary.json
        clean_summary = {
            "uncontrolled": {k: v for k, v in res_s1.items() if not k.endswith("_history") and k != "time_labels"},
            "rule_based": {k: v for k, v in res_s2.items() if not k.endswith("_history") and k != "time_labels"},
            "drl": {k: v for k, v in res_s3.items() if not k.endswith("_history") and k != "time_labels"},
            "summary": comparison_results["summary"]
        }
        with open(RESULTS_DIR / "benchmark_summary.json", "w", encoding="utf-8") as f:
            json.dump(clean_summary, f, indent=2)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(comparison_results, f, indent=2)
        logger.info(f"Comparison results saved to {output_file}")

    return comparison_results


if __name__ == "__main__":
    run_benchmark_comparison()
