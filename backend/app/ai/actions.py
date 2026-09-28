"""
GridWise AI - Action Module
Executes validated AI actions in the Digital Twin circuit and battery physics.
Adheres strictly to PRD Section 13, 14, and 15:
- Actions: CHARGE, DISCHARGE (V2G), IDLE
- Physical energy calculations (charge efficiency, discharge efficiency, dt integration)
- Updates circuit topology, voltage, current (I = P * 1000 / V), direction, and active states
- Wires active only when current > 0; wire direction reverses on discharge
"""

import math
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

logger = logging.getLogger("gridwise.actions")


@dataclass
class ActionExecutionResult:
    action: str              # CHARGE, DISCHARGE, IDLE
    power_kw: float          # Signed: + for charge, - for discharge, 0 for idle
    actual_power_kw: float
    voltage_v: float
    current_a: float
    energy_delta_kwh: float
    soc_prev: float
    soc_next: float
    circuit_direction: str   # FORWARD (Grid/Solar -> EV), REVERSE (EV -> Grid), IDLE
    wire_active: bool
    temperature_c: float
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ActionModule:
    """
    Executes actions directly into the Digital Twin physical models and circuit topology.
    """

    @classmethod
    def execute(
        cls,
        action: str,
        power_kw: float,
        ev: Any,
        dt_seconds: float,
        circuit: Optional[Any] = None
    ) -> ActionExecutionResult:
        """
        Executes action with physical differential integration and circuit updates.
        Never allows instant SOC jumps or phantom power.
        """
        soc_prev = getattr(ev, "current_soc", getattr(ev, "soc", 50.0))
        connected = getattr(ev, "is_connected", getattr(ev, "connected", True))

        if not connected or abs(power_kw) < 0.01 or action == "IDLE":
            applied_kw = 0.0
            act_type = "IDLE"
        elif action in ["CHARGE", "charge", 1] or power_kw > 0.05:
            applied_kw = abs(power_kw)
            act_type = "CHARGE"
        elif action in ["DISCHARGE", "discharge", "V2G", 2] or power_kw < -0.05:
            applied_kw = -abs(power_kw)
            act_type = "DISCHARGE"
        else:
            applied_kw = 0.0
            act_type = "IDLE"

        # Step EV Battery Physics
        if hasattr(ev, "step_physics"):
            step_res = ev.step_physics(applied_kw, dt_seconds)
            actual_kw = step_res.get("power_kw", applied_kw)
            current_a = step_res.get("current_a", 0.0)
            voltage_v = step_res.get("voltage_v", 400.0)
            soc_next = step_res.get("soc", soc_prev)
            energy_delta = step_res.get("delta_kwh", 0.0)
            temp_c = step_res.get("temperature_c", getattr(ev, "temperature_c", 25.0))
        elif hasattr(ev, "apply_power"):
            dt_hours = dt_seconds / 3600.0
            step_res = ev.apply_power(applied_kw, dt_hours)
            actual_kw = step_res.get("actual_power_kw", applied_kw)
            current_a = step_res.get("current_a", 0.0)
            voltage_v = step_res.get("voltage_v", 400.0)
            soc_next = step_res.get("soc", soc_prev)
            energy_delta = step_res.get("energy_change_kwh", 0.0)
            temp_c = getattr(ev, "temperature_c", 25.0)
        else:
            actual_kw = applied_kw
            voltage_v = 400.0
            current_a = (abs(actual_kw) * 1000.0) / max(300.0, voltage_v) if abs(actual_kw) > 0.05 else 0.0
            soc_next = soc_prev
            energy_delta = 0.0
            temp_c = 25.0

        # Determine wire direction & activation strictly from actual current
        wire_active = abs(actual_kw) > 0.05
        if actual_kw > 0.05:
            direction = "FORWARD"  # Grid/Solar -> Charger -> Battery
        elif actual_kw < -0.05:
            direction = "REVERSE"  # Battery -> Inverter -> Grid
        else:
            direction = "IDLE"

        # Update Simulator Circuit Topology
        if circuit and hasattr(circuit, "update_power_flow"):
            circuit.update_power_flow(actual_kw, connected)

        return ActionExecutionResult(
            action=act_type,
            power_kw=applied_kw,
            actual_power_kw=actual_kw,
            voltage_v=round(voltage_v, 1),
            current_a=round(current_a, 2),
            energy_delta_kwh=round(energy_delta, 6),
            soc_prev=round(soc_prev, 3),
            soc_next=round(soc_next, 3),
            circuit_direction=direction,
            wire_active=wire_active,
            temperature_c=round(temp_c, 1)
        )
