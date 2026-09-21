import pytest
import numpy as np
from backend.app.ai.environment import EVChargingGymEnv

def test_gym_env_spaces_and_reset():
    env = EVChargingGymEnv()
    
    assert env.action_space.n == 3
    assert env.observation_space.shape == (10,)
    
    obs, info = env.reset()
    assert obs.shape == (10,)
    assert isinstance(obs, np.ndarray)
    assert np.all(obs >= env.observation_space.low)
    assert np.all(obs <= env.observation_space.high)

def test_gym_env_step():
    env = EVChargingGymEnv()
    obs, _ = env.reset()

    # Step action 1 (CHARGE)
    next_obs, reward, done, truncated, info = env.step(action=1)
    
    assert next_obs.shape == (10,)
    assert isinstance(reward, float)
    assert isinstance(done, bool)
    assert "actual_power_kw" in info
    assert info["actual_power_kw"] >= 0.0

def test_gym_env_run_to_completion():
    env = EVChargingGymEnv(timestep_minutes=60)
    obs, _ = env.reset()
    done = False
    step_count = 0

    while not done and step_count < 24:
        action = env.action_space.sample()
        obs, reward, done, truncated, info = env.step(action)
        step_count += 1

    assert done is True
