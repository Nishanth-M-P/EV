from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class AIDecisionRequest(BaseModel):
    ev_id: Optional[str] = None
    hour: Optional[float] = None

class AIDecisionResponse(BaseModel):
    ev_id: str
    ev_name: str
    raw_action: int
    final_action: int
    action_name: str
    power_kw: float
    reason: str
    reward: float
    safety_overrides: List[str] = []
    is_manual_override: bool = False
    action_scores: Optional[Dict[str, float]] = None
