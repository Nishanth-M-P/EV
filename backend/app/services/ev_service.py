import uuid
from typing import Dict, List, Optional, Any
from backend.app.simulator.ev_simulator import EVDigitalTwin

class EVService:
    """
    Manages fleet operations, EV creation, deletion, lookup, and status synchronization.
    """
    def __init__(self, simulator_evs_ref: Dict[str, EVDigitalTwin]):
        self.evs = simulator_evs_ref

    def list_all(self) -> List[Dict[str, Any]]:
        return [ev.to_dict() for ev in self.evs.values()]

    def get_by_id(self, ev_id: str) -> Optional[EVDigitalTwin]:
        return self.evs.get(ev_id)

    def add_ev(self, data: Dict[str, Any]) -> EVDigitalTwin:
        ev_id = data.get("ev_id") or f"EV-{uuid.uuid4().hex[:4].upper()}"
        ev = EVDigitalTwin(
            ev_id=ev_id,
            name=data.get("name", "Electric Vehicle"),
            battery_capacity_kwh=float(data.get("battery_capacity_kwh", 50.0)),
            current_soc=float(data.get("current_soc", 40.0)),
            minimum_soc=float(data.get("minimum_soc", 20.0)),
            maximum_soc=float(data.get("maximum_soc", 100.0)),
            target_soc=float(data.get("target_soc", data.get("required_soc", 85.0))),
            arrival_time=float(data.get("arrival_time", 8.0)),
            departure_time=float(data.get("departure_time", 18.0)),
            max_charge_power_kw=float(data.get("max_charge_power_kw", 7.4)),
            max_discharge_power_kw=float(data.get("max_discharge_power_kw", 5.0)),
            charging_efficiency=float(data.get("charging_efficiency", 0.95)),
            discharging_efficiency=float(data.get("discharging_efficiency", 0.95)),
            battery_health=float(data.get("battery_health", 100.0))
        )
        self.evs[ev_id] = ev
        return ev

    def remove_ev(self, ev_id: str) -> bool:
        if ev_id in self.evs:
            del self.evs[ev_id]
            return True
        return False
