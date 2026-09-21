from typing import Dict, Any
from backend.app.simulator.ev_simulator import EVDigitalTwin

class ImmediateChargingBaseline:
    """
    Standard uncontrolled industry charging strategy:
    As soon as an EV connects, charge at maximum available power
    until target SOC is achieved, with zero regard for electricity pricing,
    solar availability, or grid peak stress.
    """
    @staticmethod
    def select_action(ev: EVDigitalTwin, current_hour: float) -> Dict[str, Any]:
        if not ev.is_connected:
            return {
                "action": 0,
                "action_name": "IDLE",
                "power_kw": 0.0,
                "reason": "Baseline: EV not connected or parked"
            }

        if ev.current_soc < ev.target_soc:
            return {
                "action": 1,
                "action_name": "CHARGE",
                "power_kw": ev.max_charge_power_kw,
                "reason": f"Baseline Uncontrolled: Immediate charging upon arrival (SOC {ev.current_soc}% < {ev.target_soc}%)"
            }
        else:
            return {
                "action": 0,
                "action_name": "IDLE",
                "power_kw": 0.0,
                "reason": "Baseline: Target SOC achieved, sitting idle"
            }
