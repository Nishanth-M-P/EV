"""
GridWise AI - DRL Policy Training Pipeline
Uses Stable-Baselines3 PPO to train an optimal bidirectional V2G controller.
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from gymnasium.utils.env_checker import check_env

from backend.app.config import AppConfig, load_config
from backend.app.rl.environment import V2GEnvironment
from backend.app.utils.logger import logger

MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


class TrainingProgressCallback(BaseCallback):
    """Logs training metrics periodically without excessive console spam."""

    def __init__(self, check_freq: int = 1000, verbose: int = 1):
        super().__init__(verbose)
        self.check_freq = check_freq
        self.episode_rewards = []
        self.last_mean_reward = -np.inf

    def _on_step(self) -> bool:
        if self.n_calls % self.check_freq == 0:
            logger.info(f"Training step {self.n_calls} / {self.locals.get('total_timesteps', 'N/A')} completed.")
        return True


def train_drl_agent(
    config: Optional[AppConfig] = None,
    total_timesteps: Optional[int] = None,
    model_name: str = "ppo_v2g_latest"
) -> Dict[str, Any]:
    cfg = config or load_config()
    timesteps = total_timesteps or cfg.drl.total_timesteps

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"{model_name}.zip"
    meta_path = MODELS_DIR / f"{model_name}_metadata.json"

    logger.info("Initializing Gymnasium V2GEnvironment for PPO training...")
    env = V2GEnvironment(config=cfg)

    # 1. Validate Environment
    logger.info("Validating environment compliance with Gymnasium check_env...")
    check_env(env.unwrapped)
    logger.info("Environment validation successful!")

    # 2. Instantiate PPO Policy
    logger.info(
        f"Creating PPO model: lr={cfg.drl.learning_rate}, gamma={cfg.drl.gamma}, "
        f"batch_size={cfg.drl.batch_size}, clip={cfg.drl.clip_range}"
    )
    model = PPO(
        policy="MlpPolicy",
        env=env,
        learning_rate=cfg.drl.learning_rate,
        n_steps=cfg.drl.batch_size * 4,
        batch_size=cfg.drl.batch_size,
        gamma=cfg.drl.gamma,
        gae_lambda=cfg.drl.gae_lambda,
        clip_range=cfg.drl.clip_range,
        ent_coef=0.01,
        verbose=0,
        seed=cfg.simulation.random_seed
    )

    # 3. Train Policy
    logger.info(f"Starting PPO training for {timesteps} timesteps...")
    start_time = datetime.now()
    callback = TrainingProgressCallback(check_freq=max(1000, timesteps // 10))
    model.learn(total_timesteps=timesteps, callback=callback)
    training_duration_sec = (datetime.now() - start_time).total_seconds()
    logger.info(f"Training finished in {training_duration_sec:.2f} seconds.")

    # 4. Save Model & Metadata
    model.save(str(model_path))
    logger.info(f"Model saved to: {model_path}")

    metadata = {
        "model_name": model_name,
        "algorithm": cfg.drl.algorithm,
        "total_timesteps": timesteps,
        "learning_rate": cfg.drl.learning_rate,
        "gamma": cfg.drl.gamma,
        "batch_size": cfg.drl.batch_size,
        "clip_range": cfg.drl.clip_range,
        "fleet_size": cfg.simulation.fleet_size,
        "random_seed": cfg.simulation.random_seed,
        "training_duration_seconds": round(training_duration_sec, 2),
        "training_date": datetime.now().isoformat(),
        "model_path": str(model_path)
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved to: {meta_path}")

    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train GridWise AI PPO Agent")
    parser.add_argument("--timesteps", type=int, default=5000, help="Total training timesteps")
    parser.add_argument("--model-name", type=str, default="ppo_v2g_latest", help="Output model name")
    args = parser.parse_args()

    train_drl_agent(total_timesteps=args.timesteps, model_name=args.model_name)

