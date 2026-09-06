import sys
import os

# Configure stdout encoding for Windows console Unicode compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import uvicorn
from backend.services.energy_service import EnergyService
from backend.services.ev_service import EVFleetService
from backend.simulation_engine import SimulationEngine

def main():
    print("=" * 70)
    print("⚡ GridWise AI: Smart EV Charging & V2G Energy Management Platform")
    print("=" * 70)
    print("Core Engine: Gymnasium 1.3.0 + Stable-Baselines3 PPO")
    print("Safety Layer: Hard Boundary & Departure Urgency Guarantee Active")
    print("Web Server: Starlette + WebSockets on Uvicorn")
    print("-" * 70)
    print("🚀 Server starting at: http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server.")
    print("=" * 70)

    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()
