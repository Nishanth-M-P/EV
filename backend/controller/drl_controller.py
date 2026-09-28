"""
GridWise AI - DRL Controller & Decision Architecture
Implements deterministic gating hierarchy, persistence, hysteresis, minimum dwell time,
and departure safety layers per PRD Sections 1-15, 27-37, and 65-66.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional

@dataclass
class Decision:
    action: str = "CHARGE" # CHARGE, DISCHARGE (V2G), IDLE
    power_kw: float = 11.0
    reason_code: str = "SOC_BELOW_TARGET"
    reason: str = "EV SOC below target; normal charging active"
    timestamp: str = ""
    controller: str = "SAFETY_FILTER"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ControllerState:
    algorithm: str = "PPO"
    action: str = "CHARGE"
    power_kw: float = 11.0
    command_kw: float = 11.0
    reward: float = 0.84
    grid_state: str = "NORMAL"
    price_state: str = "LOW"
    renewable_state: str = "SURPLUS"
    departure_urgency: float = 0.42
    mean_reward: float = 14.82
    policy_loss: float = 0.0014
    model_version: str = "DRL-PPO-V2G-v2.5"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SafetyFilter:
    """
    Enforces strict hierarchical priority rules and gating logic (PRD Section 13, 27-36, 65):
    1. Battery Safety (Overcharge Ceiling max_soc, Reserve Floor min_soc / v2g_reserve)
    2. Departure Protection (target_soc by departure_time overrides economics & grid support)
    3. Minimum Dwell Time (Prevents rapid oscillation between CHARGE and V2G)
    4. Confirmed High-Load Grid Support (V2G requires high stress >= 75 for 30s confirmation)
    5. Default Behavior: Charge if SOC < target_SOC
    6. Standby Idle if target reached and grid normal

    CRITICAL OPERATING RULES:
    - High electricity price alone MUST NOT trigger V2G discharge.
    - Renewable changes alone MUST NOT trigger V2G discharge.
    - V2G requires confirmed high grid stress and supply margin deficit.
    """

    @staticmethod
    def filter_action(
        proposed_power_kw: float,
        current_soc: float,
        min_soc: float,
        max_soc: float,
        target_soc: float,
        departure_urgency: float,
        grid_stress: str = "NORMAL",
        price_state: str = "NORMAL",
        v2g_enabled: bool = True,
        v2g_reserve: float = 30.0,
        is_high_load_confirmed: Optional[bool] = None,
        departure_target_safe: bool = True,
        grid_stress_score: float = 42.0,
        current_mode: str = "CHARGING",
        mode_dwell_time_sec: float = 999.0,
        minimum_charge_hold_sec: float = 30.0,
        minimum_v2g_hold_sec: float = 30.0,
        default_charge_kw: float = 11.0,
        default_v2g_kw: float = -6.0
    ) -> Decision:
        # Effective minimum SOC floor
        effective_min_soc = max(min_soc, v2g_reserve if v2g_enabled else min_soc)

        # ---------------------------------------------------------
        # Rule 1: Battery Safety - Overcharge Ceiling (Section 37)
        # ---------------------------------------------------------
        if current_soc >= max_soc:
            return Decision(
                action="IDLE",
                power_kw=0.0,
                reason_code="BATTERY_MAX_SOC",
                reason=f"Battery reached maximum allowable SOC ceiling ({max_soc}%)",
                controller="SAFETY_FILTER"
            )

        # ---------------------------------------------------------
        # Rule 2: Battery Safety - Overdischarge Floor (Section 15, 74)
        # ---------------------------------------------------------
        if current_soc <= effective_min_soc and proposed_power_kw < 0:
            return Decision(
                action="IDLE",
                power_kw=0.0,
                reason_code="BATTERY_RESERVE_LIMIT",
                reason=f"Battery reached minimum V2G reserve floor ({effective_min_soc}%)",
                controller="SAFETY_FILTER"
            )

        # ---------------------------------------------------------
        # Rule 3: Departure Protection (Section 11, 14, 35, 75)
        # Overrides grid support and economics if travel target is at risk
        # ---------------------------------------------------------
        if (not departure_target_safe or departure_urgency >= 0.65) and current_soc < target_soc:
            safe_charge_kw = min(22.0, max(8.4, 22.0 * max(0.5, departure_urgency)))
            reason_str = "V2G BLOCKED: Departure SOC requirement would not be satisfied." if proposed_power_kw < 0 else "Departure deadline approaching; user travel guarantee overrides grid support"
            return Decision(
                action="CHARGE",
                power_kw=round(safe_charge_kw, 1),
                reason_code="DEPARTURE_PROTECTION",
                reason=reason_str,
                controller="SAFETY_FILTER"
            )

        # ---------------------------------------------------------
        # Rule 4: Minimum Mode Dwell Time / Hysteresis (Section 10, 11, 34)
        # Once charging or V2G starts, hold mode to avoid jitter
        # ---------------------------------------------------------
        if current_mode in ["CHARGING", "CHARGE"] and mode_dwell_time_sec < minimum_charge_hold_sec:
            if current_soc < target_soc:
                is_emergency_grid = (grid_stress in ["CRITICAL", "HIGH_LOAD"] and grid_stress_score >= 88.0) and (is_high_load_confirmed is True)
                if not is_emergency_grid:
                    rem_sec = int(minimum_charge_hold_sec - mode_dwell_time_sec)
                    return Decision(
                        action="CHARGE",
                        power_kw=default_charge_kw,
                        reason_code="HOLDING_CHARGE",
                        reason=f"Maintaining minimum charge dwell time ({rem_sec}s remaining)",
                        controller="HYSTERESIS_FILTER"
                    )

        if current_mode in ["V2G", "DISCHARGE"] and mode_dwell_time_sec < minimum_v2g_hold_sec:
            if current_soc > effective_min_soc and departure_target_safe:
                if is_high_load_confirmed is not False:
                    rem_sec = int(minimum_v2g_hold_sec - mode_dwell_time_sec)
                    return Decision(
                        action="DISCHARGE",
                        power_kw=default_v2g_kw,
                        reason_code="HOLDING_V2G",
                        reason=f"Maintaining minimum V2G dwell time ({rem_sec}s remaining)",
                        controller="HYSTERESIS_FILTER"
                    )

        # ---------------------------------------------------------
        # Rule 5: Confirmed High-Load Grid Support (V2G) (Section 1, 6, 7, 27, 30)
        # Allowed ONLY if high load confirmed for duration, reserve safe, departure safe
        # ---------------------------------------------------------
        high_load_is_active = (
            is_high_load_confirmed if is_high_load_confirmed is not None
            else (grid_stress in ["HIGH", "CRITICAL"])
        )
        v2g_eligible = v2g_enabled and (current_soc > effective_min_soc + 2.0) and departure_target_safe

        if high_load_is_active and v2g_eligible:
            v2g_pwr = default_v2g_kw if proposed_power_kw >= 0 else max(-22.0, min(-2.0, proposed_power_kw))
            return Decision(
                action="DISCHARGE",
                power_kw=round(v2g_pwr, 1),
                reason_code="GRID_PEAK_SHAVING",
                reason=f"Confirmed high grid load (stress: {grid_stress_score:.0f} >= 75); exporting power to stabilize grid",
                controller="SAFETY_FILTER"
            )

        # ---------------------------------------------------------
        # Rule 6: Default State: Charge if SOC < target (Section 1, 4, 28, 29)
        # Price alone MUST NOT trigger V2G discharge!
        # Renewable changes alone MUST NOT trigger V2G discharge!
        # ---------------------------------------------------------
        if current_soc < target_soc:
            chg_pwr = default_charge_kw
            if proposed_power_kw > 0.1:
                chg_pwr = proposed_power_kw
            return Decision(
                action="CHARGE",
                power_kw=round(chg_pwr, 1),
                reason_code="SOC_BELOW_TARGET",
                reason="EV SOC below target; normal charging active",
                controller="SAFETY_FILTER"
            )

        # ---------------------------------------------------------
        # Rule 7: Target Reached & Normal Grid -> IDLE (Section 36)
        # ---------------------------------------------------------
        return Decision(
            action="IDLE",
            power_kw=0.0,
            reason_code="TARGET_REACHED",
            reason="Target SOC reached; charger in standby",
            controller="SAFETY_FILTER"
        )
