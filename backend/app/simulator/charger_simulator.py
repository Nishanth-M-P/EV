from typing import Optional, Dict, Any

class ChargerSimulator:
    """
    Represents an EV charger / EVSE unit.
    Statuses: AVAILABLE, CHARGING, DISCHARGING, IDLE, FAULT.
    """
    def __init__(
        self,
        charger_id: str,
        max_power_kw: float = 22.0,
        efficiency: float = 0.95
    ):
        self.charger_id = charger_id
        self.max_power_kw = float(max_power_kw)
        self.current_power_kw: float = 0.0
        self.efficiency = float(efficiency)
        self.status: str = "AVAILABLE"  # AVAILABLE, CHARGING, DISCHARGING, IDLE, FAULT
        self.connected_ev_id: Optional[str] = None

    def connect_ev(self, ev_id: str):
        if self.status != "FAULT":
            self.connected_ev_id = ev_id
            self.status = "IDLE"

    def disconnect_ev(self):
        if self.status != "FAULT":
            self.connected_ev_id = None
            self.status = "AVAILABLE"
            self.current_power_kw = 0.0

    def set_power(self, power_kw: float):
        if self.status == "FAULT" or not self.connected_ev_id:
            self.current_power_kw = 0.0
            return 0.0
        
        # Clamp to charger capability
        clamped_power = max(-self.max_power_kw, min(self.max_power_kw, power_kw))
        self.current_power_kw = clamped_power
        
        if clamped_power > 0.05:
            self.status = "CHARGING"
        elif clamped_power < -0.05:
            self.status = "DISCHARGING"
        else:
            self.status = "IDLE"
            
        return self.current_power_kw

    def to_dict(self) -> Dict[str, Any]:
        return {
            "charger_id": self.charger_id,
            "max_power_kw": self.max_power_kw,
            "current_power_kw": round(self.current_power_kw, 2),
            "efficiency": self.efficiency,
            "status": self.status,
            "connected_ev_id": self.connected_ev_id
        }
