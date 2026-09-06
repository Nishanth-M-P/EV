from typing import Dict, Tuple
from backend.services.ev_service import EVModel

class SafetyConstraintLayer:
    """
    Enforces physical boundaries, user departure guarantees, grid stress load caps,
    and battery health protection over RL agent actions.
    
    Actions:
    0 = IDLE
    1 = CHARGE
    2 = DISCHARGE
    """

    @staticmethod
    def validate_and_override_action(
        ev: EVModel,
        proposed_action: int,
        current_hour: float,
        grid_load_pct: float,
        electricity_price: float
    ) -> Tuple[int, float, list[str]]:
        """
        Returns:
        - final_action (0=IDLE, 1=CHARGE, 2=DISCHARGE)
        - recommended_power_kw (+kw for charge, -kw for discharge, 0.0 for idle)
        - list of active safety constraint logs / overrides triggered
        """
        reasons = []
        final_action = proposed_action
        power_kw = 0.0

        # Check if EV is connected at current hour
        if current_hour < ev.arrival_time or current_hour >= ev.departure_time:
            return 0, 0.0, ["EV disconnected or past departure time"]

        time_remaining_hours = max(0.1, ev.departure_time - current_hour)
        soc_needed_pct = max(0.0, ev.required_soc - ev.current_soc)
        energy_needed_kwh = (soc_needed_pct / 100.0) * ev.battery_capacity_kwh
        hours_needed_to_charge = energy_needed_kwh / (ev.max_charge_power_kw * ev.charging_efficiency + 1e-5)

        # Constraint 1: Departure Urgency Guarantee (HARD RULE)
        # If remaining time is tight to reach required_soc, FORCE CHARGING regardless of price
        if time_remaining_hours <= (hours_needed_to_charge * 1.35) and ev.current_soc < (ev.required_soc - 1.0):
            if proposed_action != 1:
                reasons.append(f"DEPARTURE GUARANTEE: Only {round(time_remaining_hours, 1)}h left to reach {ev.required_soc}% SOC -> Forced CHARGE")
            final_action = 1

        # Constraint 2: Maximum SOC Bound
        if ev.current_soc >= ev.maximum_soc:
            if final_action == 1:
                reasons.append(f"MAX SOC LIMIT: Battery at {round(ev.current_soc, 1)}% -> Forced IDLE")
                final_action = 0

        # Constraint 3: Minimum SOC / V2G Protection Bound
        if ev.current_soc <= ev.minimum_soc:
            if final_action == 2:
                reasons.append(f"MIN SOC LIMIT: Battery at {round(ev.current_soc, 1)}% (min {ev.minimum_soc}%) -> Blocked DISCHARGE, forced IDLE")
                final_action = 0

        # Constraint 4: V2G Threshold Safeguard
        # Discharging is only allowed if current SOC is safely above required_soc/min_soc by at least 15% and time remaining permits
        if final_action == 2:
            if (ev.current_soc - ev.minimum_soc) < 20.0 or time_remaining_hours <= (hours_needed_to_charge * 1.8):
                reasons.append(f"V2G BUFFER SAFEGUARD: SOC or departure window tight -> Blocked DISCHARGE, forced IDLE")
                final_action = 0

        # Constraint 5: Grid Stress Cap
        if grid_load_pct >= 92.0 and final_action == 1:
            # If not urgent, throttle or halt charging to protect grid
            if time_remaining_hours > (hours_needed_to_charge * 1.6):
                reasons.append(f"GRID STRESS CAP: Grid load at {round(grid_load_pct, 1)}% -> Postponed charging to protect grid")
                final_action = 0

        # Convert Action to Power Output
        if final_action == 1:
            power_kw = ev.max_charge_power_kw
        elif final_action == 2:
            power_kw = -ev.max_discharge_power_kw
        else:
            power_kw = 0.0

        return final_action, power_kw, reasons
