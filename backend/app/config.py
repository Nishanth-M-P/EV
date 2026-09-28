import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "GridWise AI"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:////tmp/gridwise.db" if os.getenv("VERCEL") else "sqlite:///./gridwise.db"
    )
    SECRET_KEY: str = os.getenv("SECRET_KEY", "gridwise-secret-key-2026")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    DEFAULT_TIMESTEP_MINUTES: int = 15
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

settings = Settings()

from pathlib import Path
import yaml
from pydantic import BaseModel, Field
from typing import Optional

CONFIG_FILE_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

class SimulationConfig(BaseModel):
    duration_hours: int = 24
    timestep_minutes: int = 15
    random_seed: int = 42
    fleet_size: int = 50

    @property
    def total_timesteps(self) -> int:
        return int((self.duration_hours * 60) / self.timestep_minutes)

    @property
    def dt_hours(self) -> float:
        return self.timestep_minutes / 60.0

class EVConfig(BaseModel):
    battery_capacity_kwh: float = 60.0
    initial_soc: float = 0.4
    required_departure_soc: float = 0.8
    max_charge_kw: float = 7.4
    max_discharge_kw: float = 5.0
    min_soc: float = 0.2
    max_soc: float = 1.0
    charging_efficiency: float = 0.95
    discharging_efficiency: float = 0.95

class GridConfig(BaseModel):
    base_peak_mw: float = 5.5
    substation_limit_mw: float = 7.0
    noise_std_mw: float = 0.05

class PricingConfig(BaseModel):
    type: str = "tou"
    off_peak_rate: float = 4.10
    normal_rate: float = 6.80
    peak_rate: float = 9.20

class RewardWeights(BaseModel):
    grid_support: float = 1.5
    cost: float = 1.0
    soc_violation: float = 2.5
    battery_cycling: float = 0.2
    departure_bonus: float = 2.0

class DRLConfig(BaseModel):
    algorithm: str = "PPO"
    learning_rate: float = 0.0003
    gamma: float = 0.99
    batch_size: int = 64
    clip_range: float = 0.2
    gae_lambda: float = 0.95
    total_timesteps: int = 25000
    reward_weights: RewardWeights = Field(default_factory=RewardWeights)

class AppConfig(BaseModel):
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    ev: EVConfig = Field(default_factory=EVConfig)
    grid: GridConfig = Field(default_factory=GridConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    drl: DRLConfig = Field(default_factory=DRLConfig)

def load_config(config_path: Optional[Path] = None) -> AppConfig:
    path = config_path or CONFIG_FILE_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return AppConfig(**data)
    return AppConfig()

app_config = load_config()
