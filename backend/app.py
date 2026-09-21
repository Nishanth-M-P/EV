"""
GridWise AI Main Application Entrypoint
Provides backward-compatible export of the FastAPI app instance.
"""
from backend.app.main import app, sim_service

__all__ = ["app", "sim_service"]
