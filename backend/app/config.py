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
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

settings = Settings()
