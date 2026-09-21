import sys
import os

# Configure stdout encoding for Windows console Unicode compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import uvicorn
from backend.app.config import settings

def main():
    print("=" * 70)
    print("⚡ GridWise AI: Smart EV Charging & V2G Energy Management Platform")
    print("=" * 70)
    print("Core Engine: Gymnasium 1.3.0 + PPO Agent & Safety Constraint Layer")
    print("Physical Twins: Battery, Charger, EV Fleet, Feeder Grid, Solar PV, TOU Pricing")
    print("Server: FastAPI + Starlette WebSockets + SQLAlchemy")
    print("-" * 70)
    print(f"🚀 Server starting at: http://{settings.HOST}:{settings.PORT}")
    print(f"📖 API Documentation: http://{settings.HOST}:{settings.PORT}/docs")
    print("Press Ctrl+C to stop the server.")
    print("=" * 70)

    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=False)

if __name__ == "__main__":
    main()
