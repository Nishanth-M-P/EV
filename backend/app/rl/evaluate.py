"""
GridWise AI - DRL Policy Evaluation Runner
Loads trained model weights and performs full 24-hour deterministic rollouts.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
from stable_baselines3 import PPO

from backend.app.config import AppConfig, load_config
from backend.app.rl.environment import V2GEnvironment
from backend.app.utils.logger import logger

MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


def evaluate_drl_agent(
    model_path: Optional[Path] = None,
    config: Optional[AppConfig] = None
) -> Dict[str, Any]:
    cfg = config or load_config()
    mpath = model_path or (MODELS_DIR / "ppo_v2g_latest.zip")

    if not mpath.exists():
        logger.warning(f"DRL model file not found at {mpath}. Evaluation requires trained weights.")
        return {"error": "Model not trained", "status": "Not trained"}

    logger.info(f"Loading trained PPO model from {mpath}...")
    model = PPO.load(str(mpath))
    env = V2GEnvironment(config=cfg)

    obs, _ = env.reset(seed=cfg.simulation.random_seed)
    total_reward = 0.0
    rewards_history = []
    grid_demand_history = []
    ev_power_history = []
    soc_history = []

    for step in range(env.total_steps):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward

        rewards_history.append(float(reward))
        grid_demand_history.append(float(info["net_grid_mw"]))
        ev_power_history.append(float(info["net_ev_power_kw"]))
        soc_history.append(float(np.mean([ev.current_soc for ev in env.fleet])))

        if terminated or truncated:
            break

    peak_grid_mw = max(grid_demand_history) if grid_demand_history else 0.0
    baseline_peak_mw = max(env.grid_model.base_demand_mw)
    peak_reduction_pct = ((baseline_peak_mw - peak_grid_mw) / baseline_peak_mw * 100.0) if baseline_peak_mw > 0 else 0.0

    departed = [ev for ev in env.fleet if ev.has_departed(24.0)]
    compliant = [ev for ev in departed if ev.departure_soc_satisfied()]
    soc_compliance = (len(compliant) / len(departed) * 100.0) if departed else 100.0

    results = {
        "status": "Evaluated",
        "total_reward": float(np.round(total_reward, 2)),
        "baseline_peak_mw": float(np.round(baseline_peak_mw, 3)),
        "controlled_peak_mw": float(np.round(peak_grid_mw, 3)),
        "peak_reduction_pct": float(np.round(peak_reduction_pct, 2)),
        "total_cost": float(np.round(env.v2g_manager.net_cost, 2)),
        "v2g_energy_kwh": float(np.round(env.v2g_manager.discharging_energy_kwh, 2)),
        "charging_energy_kwh": float(np.round(env.v2g_manager.charging_energy_kwh, 2)),
        "soc_compliance_pct": float(np.round(soc_compliance, 2)),
        "grid_demand_history": grid_demand_history,
        "ev_power_history": ev_power_history,
        "soc_history": soc_history,
        "rewards_history": rewards_history
    }
    logger.info(f"Evaluation complete: Peak Shaving = {peak_reduction_pct:.2f}%, Compliance = {soc_compliance:.1f}%")
    return results

