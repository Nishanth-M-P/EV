from typing import Tuple, List, Dict, Any
from datetime import datetime
from backend.app.simulator.ev_simulator import EVDigitalTwin

class ConstraintEngine:
    """
    Mandatory physical safety constraint layer.
    Intercepts and validates raw AI / Operator decisions BEFORE execution in simulation.
    Ensures zero violations of battery limits, connection status, grid stability,
    and departure SLA guarantees.

    Action IDs:
    0 = IDLE
    1 = CHARGE
    2 = DISCHARGE (V2G)
    """

    ACTION_MAP = {0: "IDLE", 1: "CHARGE", 2: "DISCHARGE"}
    _events_log: List[Dict[str, Any]] = []

    @classmethod
    def get_recent_events(cls, limit: int = 50) -> List[Dict[str, Any]]:
        return cls._events_log[-limit:]

    @classmethod
    def clear_events(cls):
        cls._events_log.clear()

    @classmethod
    def validate_action(
        cls,
        ev: EVDigitalTwin,
        proposed_action: int,
        current_hour: float,
        grid_load_pct: float,
        electricity_price: float
    ) -> Tuple[int, float, List[str]]:
        """
        Validates the proposed action against hard physical rules.

        Returns:
        - validated_action: int (0=IDLE, 1=CHARGE, 2=DISCHARGE)
        - approved_power_kw: float (+ for charge, - for discharge, 0 for idle)
        - constraint_logs: List[str] explaining any override or rejection
        """
        reasons = []
        action = proposed_action
        power_kw = 0.0
        rule_name = None

        # Rule 1: Physical Connection Status
        if current_hour < ev.arrival_time or current_hour >= ev.departure_time or not ev.is_connected:
            rule_name = "Physical Connection Guard"
            reason = "EV physically disconnected or outside parking window -> Forced IDLE"
            if proposed_action != 0:
                cls._record_event(current_hour, ev.ev_id, proposed_action, 0, rule_name, reason, 0.0)
            return 0, 0.0, [reason]

        time_remaining_hours = max(0.05, ev.departure_time - current_hour)
        soc_needed_pct = max(0.0, ev.target_soc - ev.current_soc)
        energy_needed_kwh = (soc_needed_pct / 100.0) * ev.battery_capacity_kwh
        hours_needed = energy_needed_kwh / (ev.max_charge_power_kw * ev.charging_efficiency + 1e-5)

        # Rule 2: Departure Urgency SLA Guarantee (Hard Rule)
        if time_remaining_hours <= (hours_needed * 1.35) and ev.current_soc < (ev.target_soc - 1.0):
            if action != 1:
                rule_name = "Departure Urgency SLA Guarantee"
                reason = f"Only {round(time_remaining_hours, 1)}h left to reach {ev.target_soc}% SOC -> Forced CHARGE"
                reasons.append(f"DEPARTURE SLA GUARANTEE: {reason}")
                cls._record_event(current_hour, ev.ev_id, proposed_action, 1, rule_name, reason, ev.max_charge_power_kw)
            action = 1

        # Rule 3: Maximum SOC Bound (Prevent Overcharge)
        if ev.current_soc >= ev.maximum_soc:
            if action == 1:
                rule_name = "Maximum SOC Limit"
                reason = f"Battery at {round(ev.current_soc, 1)}% (max {ev.maximum_soc}%) -> Blocked CHARGE"
                reasons.append(f"MAX SOC LIMIT: {reason}")
                cls._record_event(current_hour, ev.ev_id, proposed_action, 0, rule_name, reason, -ev.max_charge_power_kw)
                action = 0

        # Rule 4: Minimum SOC Bound (Prevent Deep Discharge)
        if ev.current_soc <= ev.minimum_soc:
            if action == 2:
                rule_name = "Minimum SOC Limit"
                reason = f"Battery at {round(ev.current_soc, 1)}% (min {ev.minimum_soc}%) -> Blocked DISCHARGE"
                reasons.append(f"MIN SOC LIMIT: {reason}")
                cls._record_event(current_hour, ev.ev_id, proposed_action, 0, rule_name, reason, ev.max_discharge_power_kw)
                action = 0

        # Rule 5: V2G Safeguard Buffer
        if action == 2:
            if (ev.current_soc - ev.minimum_soc) < 15.0:
                rule_name = "V2G Minimum Reserve Buffer"
                reason = f"SOC too close to minimum threshold ({ev.minimum_soc}%) -> Blocked DISCHARGE"
                reasons.append(f"V2G BUFFER CONSTRAINT: {reason}")
                cls._record_event(current_hour, ev.ev_id, proposed_action, 0, rule_name, reason, ev.max_discharge_power_kw)
                action = 0
            elif time_remaining_hours <= (hours_needed * 1.8):
                rule_name = "V2G Departure Protection"
                reason = "Time window too narrow to permit discharging before departure -> Blocked DISCHARGE"
                reasons.append(f"V2G DEPARTURE RISK: {reason}")
                cls._record_event(current_hour, ev.ev_id, proposed_action, 0, rule_name, reason, ev.max_discharge_power_kw)
                action = 0

        # Rule 6: Grid Critical Load Cap
        if grid_load_pct >= 92.0 and action == 1:
            if time_remaining_hours > (hours_needed * 1.6):
                rule_name = "Transformer Overload Cap"
                reason = f"Grid feeder at {round(grid_load_pct, 1)}% capacity -> Postponed charging to prevent grid trip"
                reasons.append(f"GRID CRITICAL CAP: {reason}")
                cls._record_event(current_hour, ev.ev_id, proposed_action, 0, rule_name, reason, -ev.max_charge_power_kw)
                action = 0

        # Rule 7: Battery Health / Anti-Cycling Guard
        if ev.battery_health < 80.0 and action == 2:
            rule_name = "Battery Health Degradation Guard"
            reason = "SOH below 80%, suppressing V2G to preserve pack life"
            reasons.append(f"BATTERY HEALTH GUARD: {reason}")
            cls._record_event(current_hour, ev.ev_id, proposed_action, 0, rule_name, reason, ev.max_discharge_power_kw)
            action = 0

        # Convert validated action to power
        if action == 1:
            power_kw = ev.max_charge_power_kw
        elif action == 2:
            power_kw = -ev.max_discharge_power_kw
        else:
            power_kw = 0.0

        return action, power_kw, reasons

    @classmethod
    def _record_event(
        cls,
        hour: float,
        ev_id: str,
        proposed_action: int,
        approved_action: int,
        rule_name: str,
        reason: str,
        power_delta_kw: float
    ):
        h = int(hour)
        m = int((hour - h) * 60)
        time_str = f"{h:02d}:{m:02d}"
        event = {
            "timestamp": time_str,
            "hour": round(hour, 2),
            "ev_id": ev_id,
            "proposed_action": cls.ACTION_MAP.get(proposed_action, "UNKNOWN"),
            "approved_action": cls.ACTION_MAP.get(approved_action, "UNKNOWN"),
            "rule_triggered": rule_name,
            "reason": reason,
            "power_delta_kw": round(power_delta_kw, 2),
            "recorded_at": datetime.utcnow().isoformat()
        }
        cls._events_log.append(event)
        if len(cls._events_log) > 200:
            cls._events_log.pop(0)
