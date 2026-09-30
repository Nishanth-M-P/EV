import sys
import os

# Include project root in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.main import app

__all__ = ["app"]
