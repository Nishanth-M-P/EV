"""
Tests for GridWise AI Closed-Loop Real-Time Integration
Covers the 15 required scenarios from PRD Section 33:
1. Low price + solar available -> charge rewarded
2. High grid load + high price -> avoid unnecessary charge
3. High grid load + sufficient SOC + V2G -> V2G selected/permitted
4. EV SOC below minimum -> DISCHARGE rejected
5. Feeder overload -> charging power capped/rejected
6. Departure approaching -> agent prioritizes target SOC
7. Solar increases -> state changes
8. Electricity price changes -> state changes
9. Grid load changes -> state changes
10. AI requests unsafe discharge -> Safety Validator overrides
11. Charge action -> battery SOC increases gradually
12. Discharge action -> battery SOC decreases gradually
13. Circuit active -> wire current/power changes
14. V2G active -> power direction reverses
15. WebSocket connected -> client receives the exact same state used by AI
"""

import pytest
import numpy as np
from typing import Dict, Any

from backend.app.ai.state_space import StateSpaceModule
from backend.app.ai.ppo_model import PPOActorCritic
from backend.app.ai.reward import RewardFunction
from backend.app.ai.actions import ActionModule
from backend.app.ai.constraints import ConstraintEngine
from backend.simulation.unified_engine import (
    authoritative_simulation_engine,
    UnifiedSimulationEngine,
    SafetyValidator,
    EVBatteryModel,
    CircuitTopologyManager
)
from backend.app.telemetry.realtime_data_service import default_realtime_data_service


# ---------------------------------------------------------------------
# Scenario 1: Low price + solar available -> charge rewarded
# ---------------------------------------------------------------------
def test_scenario_1_low_price_solar_available_charge_rewarded():
    rf = RewardFunction()
    breakdown = rf.calculate_reward_breakdown(
        actual_power_kw=11.0,
        timestep_hours=0.25,
        electricity_price=5.0,  # Low price (<= 6.50)
        solar_generation_kw=15.0,  # Abundant solar
        grid_load_pct=40.0,
        is_done=False,
        current_soc=50.0,
        target_soc=80.0
    )
    assert breakdown["renewable_reward"] > 0.0, "Renewable bonus should be awarded"
    assert breakdown["cost_saving_reward"] > 0.0, "Cost saving off-peak reward should be awarded"
    assert breakdown["total_reward"] > 0.0, "Total reward for solar charging at low price must be positive"


# ---------------------------------------------------------------------
# Scenario 2: High grid load + high price -> avoid unnecessary charge
# ---------------------------------------------------------------------
def test_scenario_2_high_grid_load_high_price_avoid_charge():
    rf = RewardFunction()
    # Case A: Charging during peak load & peak price
    charge_res = rf.calculate_reward_breakdown(
        actual_power_kw=11.0,
        timestep_hours=0.25,
        electricity_price=10.0,  # High peak price
        solar_generation_kw=0.0,
        grid_load_pct=90.0,  # High grid stress (> 75%)
        is_done=False,
        current_soc=60.0,
        target_soc=80.0
    )

    # Case B: Idling during peak load & peak price
    idle_res = rf.calculate_reward_breakdown(
        actual_power_kw=0.0,
        timestep_hours=0.25,
        electricity_price=10.0,
        solar_generation_kw=0.0,
        grid_load_pct=90.0,
        is_done=False,
        current_soc=60.0,
        target_soc=80.0
    )

    assert charge_res["peak_load_penalty"] > 0.0, "Charging under peak grid load must incur penalty"
    assert idle_res["total_reward"] > charge_res["total_reward"], "Idling during peak stress must yield higher reward than charging"


# ---------------------------------------------------------------------
# Scenario 3: High grid load + sufficient SOC + V2G -> V2G permitted
# ---------------------------------------------------------------------
def test_scenario_3_high_grid_load_sufficient_soc_v2g_permitted():
    validator = SafetyValidator()
    ev = EVBatteryModel(
        ev_id="EV-001",
        name="Test EV",
        soc=75.0,  # Sufficient SOC (> 25% minimum)
        target_soc=80.0,
        departure_time="21:00",
        v2g_enabled=True,
        connected=True
    )
    decision = validator.validate_action(
        proposed_action="DISCHARGE",
        proposed_power_kw=-10.0,
        ev=ev,
        feeder_import_headroom_kw=50.0,
        grid_stress_score=85.0,
        departure_urgency=0.2,
        grid_condition="HIGH_STRESS"
    )
    assert decision.approved is True, "V2G should be approved when SOC is sufficient and grid needs support"
    assert decision.final_action == "DISCHARGE"
    assert decision.power_kw < 0.0


# ---------------------------------------------------------------------
# Scenario 4: EV SOC below minimum -> DISCHARGE rejected
# ---------------------------------------------------------------------
def test_scenario_4_ev_soc_below_minimum_discharge_rejected():
    validator = SafetyValidator()
    ev = EVBatteryModel(
        ev_id="EV-001",
        name="Low SOC EV",
        soc=18.0,  # Below min_soc (20%)
        target_soc=80.0,
        departure_time="19:00",
        v2g_enabled=True,
        connected=True
    )
    decision = validator.validate_action(
        proposed_action="DISCHARGE",
        proposed_power_kw=-10.0,
        ev=ev,
        feeder_import_headroom_kw=50.0,
        grid_stress_score=80.0,
        departure_urgency=0.3,
        grid_condition="NORMAL"
    )
    assert decision.approved is False, "DISCHARGE must be rejected when SOC is below minimum reserve"
    assert decision.final_action == "IDLE"
    assert decision.power_kw == 0.0
    assert decision.reason_code in ["SOC_BELOW_MIN_V2G", "BATTERY_RESERVE_FLOOR"]


# ---------------------------------------------------------------------
# Scenario 5: Feeder overload -> charging power capped/rejected
# ---------------------------------------------------------------------
def test_scenario_5_feeder_overload_charging_capped_or_rejected():
    validator = SafetyValidator()
    ev = EVBatteryModel(
        ev_id="EV-001",
        name="Feeder Test EV",
        soc=40.0,
        target_soc=80.0,
        departure_time="19:00",
        v2g_enabled=True,
        connected=True
    )
    # Available feeder headroom is only 4.0 kW, but AI requests 22.0 kW charging
    decision = validator.validate_action(
        proposed_action="CHARGE",
        proposed_power_kw=22.0,
        ev=ev,
        feeder_import_headroom_kw=4.0,
        grid_stress_score=90.0,
        departure_urgency=0.4,
        grid_condition="PEAK_WARNING"
    )
    assert decision.power_kw <= 4.0, "Charging power must be capped to feeder headroom to prevent physical overload"


# ---------------------------------------------------------------------
# Scenario 6: Departure approaching -> agent prioritizes target SOC
# ---------------------------------------------------------------------
def test_scenario_6_departure_approaching_prioritizes_target_soc():
    validator = SafetyValidator()
    ev = EVBatteryModel(
        ev_id="EV-001",
        name="Urgent EV",
        soc=45.0,
        target_soc=85.0,
        departure_time="18:35",  # Approaching departure
        v2g_enabled=True,
        connected=True
    )
    # Even if AI tried to discharge or idle, departure urgency requires charging
    decision = validator.validate_action(
        proposed_action="DISCHARGE",
        proposed_power_kw=-7.0,
        ev=ev,
        feeder_import_headroom_kw=50.0,
        grid_stress_score=50.0,
        departure_urgency=0.95,  # Very high urgency
        grid_condition="NORMAL"
    )
    assert decision.approved is False, "Unsafe discharge near departure deadline must be overridden"
    assert decision.final_action == "CHARGE"
    assert decision.power_kw > 0.0


# ---------------------------------------------------------------------
# Scenario 7: Solar increases -> state changes
# ---------------------------------------------------------------------
def test_scenario_7_solar_increases_state_changes():
    ev = EVBatteryModel(ev_id="EV-001", name="Solar EV", soc=50.0, connected=True)
    grid_d = {"load_kw": 40.0, "capacity_kw": 100.0, "voltage_v": 230.0, "frequency_hz": 50.0}
    price_d = {"electricity_price": 6.50}

    vec_zero_solar, raw_zero = StateSpaceModule.build_state(
        ev=ev,
        grid_data=grid_d,
        price_data=price_d,
        solar_data={"generation_kw": 0.0, "installed_capacity_kw": 40.0, "solar_availability": 0.0},
        current_hour=12.0
    )

    vec_high_solar, raw_high = StateSpaceModule.build_state(
        ev=ev,
        grid_data=grid_d,
        price_data=price_d,
        solar_data={"generation_kw": 30.0, "installed_capacity_kw": 40.0, "solar_availability": 1.0},
        current_hour=12.0
    )

    assert vec_zero_solar[10] != vec_high_solar[10], "Solar feature in 19D vector must reflect solar increase"
    assert raw_high["solar_generation_kw"] == 30.0
    assert raw_zero["solar_generation_kw"] == 0.0


# ---------------------------------------------------------------------
# Scenario 8: Electricity price changes -> state changes
# ---------------------------------------------------------------------
def test_scenario_8_electricity_price_changes_state_changes():
    ev = EVBatteryModel(ev_id="EV-001", name="Price EV", soc=50.0, connected=True)
    grid_d = {"load_kw": 40.0, "capacity_kw": 100.0, "voltage_v": 230.0, "frequency_hz": 50.0}
    solar_d = {"generation_kw": 10.0, "installed_capacity_kw": 40.0}

    vec_low_p, raw_low = StateSpaceModule.build_state(
        ev=ev, grid_data=grid_d, price_data={"electricity_price": 4.0}, solar_data=solar_d, current_hour=12.0
    )
    vec_high_p, raw_high = StateSpaceModule.build_state(
        ev=ev, grid_data=grid_d, price_data={"electricity_price": 12.0}, solar_data=solar_d, current_hour=12.0
    )

    assert vec_low_p[9] != vec_high_p[9], "Electricity price feature in 19D vector must reflect price change"
    assert raw_low["electricity_price_inr"] == 4.0
    assert raw_high["electricity_price_inr"] == 12.0


# ---------------------------------------------------------------------
# Scenario 9: Grid load changes -> state changes
# ---------------------------------------------------------------------
def test_scenario_9_grid_load_changes_state_changes():
    ev = EVBatteryModel(ev_id="EV-001", name="Load EV", soc=50.0, connected=True)
    price_d = {"electricity_price": 6.80}
    solar_d = {"generation_kw": 10.0, "installed_capacity_kw": 40.0}

    vec_low_load, raw_low = StateSpaceModule.build_state(
        ev=ev, grid_data={"load_kw": 20.0, "capacity_kw": 100.0, "voltage_v": 230.0, "frequency_hz": 50.0},
        price_data=price_d, solar_data=solar_d, current_hour=12.0
    )
    vec_high_load, raw_high = StateSpaceModule.build_state(
        ev=ev, grid_data={"load_kw": 95.0, "capacity_kw": 100.0, "voltage_v": 230.0, "frequency_hz": 50.0},
        price_data=price_d, solar_data=solar_d, current_hour=12.0
    )

    assert vec_low_load[4] != vec_high_load[4], "Grid load feature in 19D vector must reflect load change"
    assert raw_low["grid_load_kw"] == 20.0
    assert raw_high["grid_load_kw"] == 95.0


# ---------------------------------------------------------------------
# Scenario 10: AI requests unsafe discharge -> Safety Validator overrides
# ---------------------------------------------------------------------
def test_scenario_10_ai_requests_unsafe_discharge_safety_validator_overrides():
    validator = SafetyValidator()
    ev = EVBatteryModel(
        ev_id="EV-001",
        name="Unsafe EV",
        soc=15.0,  # Below minimum reserve
        target_soc=80.0,
        departure_time="19:00",
        v2g_enabled=True,
        connected=True
    )
    # AI proposes discharge
    decision = validator.validate_action(
        proposed_action="DISCHARGE",
        proposed_power_kw=-11.0,
        ev=ev,
        feeder_import_headroom_kw=50.0,
        grid_stress_score=70.0,
        departure_urgency=0.4,
        grid_condition="NORMAL"
    )
    assert decision.approved is False
    assert decision.final_action == "IDLE"
    assert decision.power_kw == 0.0
    assert decision.reason_code in ["SOC_BELOW_MIN_V2G", "BATTERY_RESERVE_FLOOR"]


# ---------------------------------------------------------------------
# Scenario 11: Charge action -> battery SOC increases gradually
# ---------------------------------------------------------------------
def test_scenario_11_charge_action_battery_soc_increases_gradually():
    ev = EVBatteryModel(
        ev_id="EV-001",
        name="Gradual Charge EV",
        capacity_kwh=60.0,
        soc=50.0,
        connected=True
    )
    soc_start = ev.soc
    # Step charge at 11 kW for 10 seconds
    res = ActionModule.execute(action="CHARGE", power_kw=11.0, ev=ev, dt_seconds=10.0)

    assert res.soc_next > soc_start, "SOC must increase after charging"
    delta_soc = res.soc_next - soc_start
    # In 10s at 11kW: energy = 11 * (10/3600) * 0.95 = 0.029 kWh -> delta SOC ~ 0.048%
    assert 0.01 < delta_soc < 0.1, f"SOC change must be gradual, was {delta_soc}%"
    assert res.circuit_direction == "FORWARD"
    assert res.wire_active is True


# ---------------------------------------------------------------------
# Scenario 12: Discharge action -> battery SOC decreases gradually
# ---------------------------------------------------------------------
def test_scenario_12_discharge_action_battery_soc_decreases_gradually():
    ev = EVBatteryModel(
        ev_id="EV-001",
        name="Gradual Discharge EV",
        capacity_kwh=60.0,
        soc=70.0,
        connected=True
    )
    soc_start = ev.soc
    # Step discharge at -11 kW for 10 seconds
    res = ActionModule.execute(action="DISCHARGE", power_kw=-11.0, ev=ev, dt_seconds=10.0)

    assert res.soc_next < soc_start, "SOC must decrease after discharging"
    delta_soc = soc_start - res.soc_next
    assert 0.01 < delta_soc < 0.1, f"SOC change must be gradual, was {delta_soc}%"
    assert res.circuit_direction == "REVERSE"
    assert res.wire_active is True


# ---------------------------------------------------------------------
# Scenario 13: Circuit active -> wire current/power changes
# ---------------------------------------------------------------------
def test_scenario_13_circuit_active_wire_current_power_changes():
    circuit = CircuitTopologyManager()

    # When Idle (0 kW)
    circuit.update_power_flow(charger_power_kw=0.0, ev_connected=True)
    wire = circuit.connections["charger_to_battery"]
    assert wire.active is False
    assert wire.current_a == 0.0
    assert wire.direction == "IDLE"

    # When Active (11 kW)
    circuit.update_power_flow(charger_power_kw=11.0, ev_connected=True)
    wire_active = circuit.connections["charger_to_battery"]
    assert wire_active.active is True
    assert wire_active.current_a > 0.0
    assert wire_active.power_kw == 11.0
    assert wire_active.direction == "FORWARD"


# ---------------------------------------------------------------------
# Scenario 14: V2G active -> power direction reverses
# ---------------------------------------------------------------------
def test_scenario_14_v2g_active_power_direction_reverses():
    circuit = CircuitTopologyManager()

    # Charging -> FORWARD direction
    circuit.update_power_flow(charger_power_kw=11.0, ev_connected=True)
    wire_chg = circuit.connections["charger_to_battery"]
    assert wire_chg.direction == "FORWARD"

    # V2G Discharging -> REVERSE direction
    circuit.update_power_flow(charger_power_kw=-11.0, ev_connected=True)
    wire_v2g = circuit.connections["charger_to_battery"]
    assert wire_v2g.direction == "REVERSE"
    assert wire_v2g.active is True
    assert wire_v2g.power_kw == -11.0


# ---------------------------------------------------------------------
# Scenario 15: WebSocket client receives exact same state used by AI
# ---------------------------------------------------------------------
def test_scenario_15_websocket_client_receives_exact_ai_state():
    engine = authoritative_simulation_engine
    received_states = []

    def callback(state):
        received_states.append(state)

    engine.register_callback(callback)
    try:
        step_state = engine.step(wall_dt=1.0)
        assert len(received_states) > 0, "Observer callback must be invoked on step"
        ws_state = received_states[-1]

        # Verify single source of truth across all modules
        assert ws_state["simulation_id"] == step_state["simulation_id"]
        assert ws_state["sequence"] == step_state["sequence"]

        # AI and Safety cards present and identical
        assert "ai" in ws_state
        assert "safety" in ws_state
        assert "reward" in ws_state
        assert "reward_breakdown" in ws_state
        assert "state_vector_19d" in ws_state
        assert "realtime_data" in ws_state

        assert ws_state["ai"]["action"] == step_state["ai"]["action"]
        assert ws_state["safety"]["approved"] == step_state["safety"]["approved"]
        assert ws_state["reward"] == step_state["reward"]
        assert ws_state["state_vector_19d"]["dimension"] == 19
    finally:
        engine.unregister_callback(callback)
