"""
GridWise AI - Grid Demand, Managed Impact & GridStressEngine
Complies with PRD Section 5, 6, 7, 8, 9, 39, 40, 70, 71.
"""

from typing import Dict, Any
from dataclasses import dataclass, asdict

class GridDemandManager:
    """
    Computes managed simulated demand without corrupting real-world external observations.
    
    Formula:
    managed_simulation_demand_mw = live_grid_demand_mw + simulated_ev_load_mw - simulated_v2g_export_mw
    """

    @staticmethod
    def calculate_impact(
        live_grid_demand_mw: float,
        ev_charge_power_kw: float,
        v2g_export_power_kw: float
    ) -> Dict[str, Any]:
        simulated_ev_load_mw = round(ev_charge_power_kw / 1000.0, 6)
        simulated_v2g_export_mw = round(v2g_export_power_kw / 1000.0, 6)
        net_ev_impact_kw = round(ev_charge_power_kw - v2g_export_power_kw, 2)
        net_ev_impact_mw = round(net_ev_impact_kw / 1000.0, 6)

        managed_simulation_demand_mw = round(
            live_grid_demand_mw + net_ev_impact_mw, 4
        )
        managed_simulation_demand_gw = round(
            managed_simulation_demand_mw / 1000.0, 5
        )

        return {
            "live_grid_demand_mw": live_grid_demand_mw,
            "live_grid_demand_gw": round(live_grid_demand_mw / 1000.0, 3),
            "simulated_ev_load_kw": ev_charge_power_kw,
            "simulated_v2g_export_kw": v2g_export_power_kw,
            "net_ev_impact_kw": net_ev_impact_kw,
            "net_ev_impact_mw": net_ev_impact_mw,
            "managed_simulation_demand_mw": managed_simulation_demand_mw,
            "managed_simulation_demand_gw": managed_simulation_demand_gw
        }


class GridStressEvaluator:
    @staticmethod
    def evaluate(frequency_hz: float, margin_mw: float, total_demand_mw: float) -> str:
        # Frequency droop or tight reserve triggers stress
        if frequency_hz < 49.85 or margin_mw < 150.0:
            return "CRITICAL"
        elif frequency_hz < 49.95 or margin_mw < 350.0:
            return "HIGH"
        elif frequency_hz > 50.05:
            return "LOW"
        return "NORMAL"


class GridStressEngine:
    """
    Dedicated High-Load & Grid Stress Evaluation Engine.
    Implements thresholds, persistence (confirmation time), hysteresis, and recovery timer.
    Complies with PRD Sections 5, 6, 7, 8, 9, 32, 33, 41.
    """
    def __init__(
        self,
        v2g_entry_stress: float = 75.0,
        v2g_exit_stress: float = 60.0,
        supply_margin_threshold_pct: float = 5.0,
        high_load_confirmation_time_sec: float = 30.0,
        v2g_recovery_time_sec: float = 30.0
    ):
        # Configurable Thresholds
        self.v2g_entry_stress = float(v2g_entry_stress)
        self.v2g_exit_stress = float(v2g_exit_stress)
        self.supply_margin_threshold_pct = float(supply_margin_threshold_pct)
        self.high_load_confirmation_time_sec = float(high_load_confirmation_time_sec)
        self.v2g_recovery_time_sec = float(v2g_recovery_time_sec)

        # Evaluated Metrics
        self.demand_mw: float = 13740.0
        self.supply_mw: float = 14200.0
        self.frequency_hz: float = 49.96
        self.margin_mw: float = 460.0
        self.margin_pct: float = 3.24
        self.demand_percentile: float = 94.7
        self.stress_score: float = 42.0
        self.grid_condition: str = "NORMAL" # SURPLUS, NORMAL, HIGH_LOAD, CRITICAL

        # Persistence & Hysteresis State Timers (in simulation seconds)
        self.high_load_candidate_timer: float = 0.0
        self.is_high_load_confirmed: bool = False
        self.recovery_timer: float = 0.0

    def update(
        self,
        dt_seconds: float,
        demand_mw: float,
        supply_mw: float,
        frequency_hz: float,
        is_v2g_active: bool = False,
        external_stress_score: float = None
    ) -> Dict[str, Any]:
        """
        Updates grid stress, persistence timer, hysteresis, and derived condition.
        """
        self.demand_mw = float(demand_mw)
        self.supply_mw = max(1.0, float(supply_mw))
        self.frequency_hz = float(frequency_hz)
        self.margin_mw = max(0.0, self.supply_mw - self.demand_mw)
        self.margin_pct = round((self.margin_mw / self.supply_mw) * 100.0, 2)
        self.demand_percentile = round(min(100.0, (self.demand_mw / 14500.0) * 100.0), 1)

        # 1. Calculate Grid Stress (0 - 100) if not explicitly provided
        if external_stress_score is not None:
            self.stress_score = float(external_stress_score)
        else:
            base = 20.0
            # Margin factor (tight reserve < 500 MW increases stress up to 35 pts)
            margin_factor = max(0.0, min(35.0, (500.0 - self.margin_mw) * 0.085))
            # Frequency droop factor (droop below 50.00 Hz adds up to 30 pts)
            freq_dev = max(0.0, 50.00 - self.frequency_hz)
            freq_factor = min(30.0, freq_dev * 200.0)
            # Demand factor (demand above 13000 MW adds up to 20 pts)
            demand_factor = max(0.0, min(20.0, (self.demand_mw - 13000.0) / 75.0))
            self.stress_score = round(min(100.0, max(10.0, base + margin_factor + freq_factor + demand_factor)), 1)

        # 2. Evaluate Raw High Load Candidate Condition (Section 6)
        # Strictly governed by V2G entry stress threshold (>= 75.0)
        is_raw_high_load = (self.stress_score >= self.v2g_entry_stress)

        # 3. Persistence Requirement (Section 7: 30s confirmation)
        if is_raw_high_load:
            self.high_load_candidate_timer += dt_seconds
            if self.high_load_candidate_timer >= self.high_load_confirmation_time_sec:
                self.is_high_load_confirmed = True
        else:
            # Fluctuation / spike ended before confirmation time
            self.high_load_candidate_timer = max(0.0, self.high_load_candidate_timer - dt_seconds * 2.0)

        # 4. V2G Hysteresis & Recovery Timer (Section 8, 9)
        if is_v2g_active:
            # Once in V2G, exit condition requires stress <= exit_stress (e.g. 60)
            if self.stress_score <= self.v2g_exit_stress:
                self.recovery_timer += dt_seconds
                if self.recovery_timer >= self.v2g_recovery_time_sec:
                    # Sustained recovery confirmed -> clear high-load state
                    self.is_high_load_confirmed = False
            else:
                # Still stressed, cancel recovery timer
                self.recovery_timer = 0.0
        else:
            self.recovery_timer = 0.0
            if not is_raw_high_load and self.stress_score < self.v2g_entry_stress:
                self.is_high_load_confirmed = False

        # 5. Derive Simulator State (Section 5)
        if self.stress_score >= 85.0 or self.frequency_hz < 49.85 or self.margin_pct <= 2.0:
            self.grid_condition = "CRITICAL"
        elif self.is_high_load_confirmed or (is_raw_high_load and self.is_high_load_confirmed):
            self.grid_condition = "HIGH_LOAD"
        elif self.margin_pct > 12.0 and self.stress_score < 30.0:
            self.grid_condition = "SURPLUS"
        else:
            self.grid_condition = "NORMAL"

        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "demand_mw": self.demand_mw,
            "supply_mw": self.supply_mw,
            "frequency_hz": self.frequency_hz,
            "margin_mw": self.margin_mw,
            "margin_pct": self.margin_pct,
            "demand_percentile": self.demand_percentile,
            "stress_score": self.stress_score,
            "grid_condition": self.grid_condition,
            "v2g_entry_stress": self.v2g_entry_stress,
            "v2g_exit_stress": self.v2g_exit_stress,
            "supply_margin_threshold_pct": self.supply_margin_threshold_pct,
            "high_load_confirmation_time_sec": self.high_load_confirmation_time_sec,
            "high_load_candidate_timer": round(self.high_load_candidate_timer, 1),
            "is_high_load_confirmed": self.is_high_load_confirmed,
            "v2g_recovery_time_sec": self.v2g_recovery_time_sec,
            "recovery_timer": round(self.recovery_timer, 1)
        }
