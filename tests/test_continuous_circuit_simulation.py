"""
GridWise AI - Continuous Circuit Simulation Tests
Verifies the fix for the artificial 1-second toggling bug:
- Dual-rate control loop (1s physics, 10s control decision)
- Continuous charging without toggling between CHARGE and IDLE
- Continuous idle when target reached or disconnected
- Continuous V2G discharge with reverse power flow and wire glow
- Action state machine tracking dwell time and transition history
- Circuit topology validation and structured error reporting
- Diagnostics panel fields and canonical SimulationState schema
"""

import pytest
import time
from backend.simulation.unified_engine import (
    UnifiedSimulationEngine,
    authoritative_simulation_engine,
    ActionStateMachine,
    CircuitTopologyManager,
    PortElectricalType,
    ElectricalConnection,
    SafetyValidator
)


def test_continuous_charging_no_toggling():
    """
    Critical Test 1: Verify the simulation runs continuously in CHARGING mode
    for 20 consecutive seconds without alternating back and forth to IDLE.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()
    
    # Configure EV to require charge: SOC 50%, target 80%
    ev = engine.fleet_manager.fleet.get("EV-001")
    assert ev is not None
    ev.soc = 50.0
    ev.target_soc = 80.0
    ev.connected = True

    soc_history = []
    action_history = []
    power_history = []
    dwell_history = []

    # Execute 20 consecutive 1-second steps
    for t in range(20):
        state = engine.step(wall_dt=1.0)
        
        current_action = state["current_action"]
        actual_power = state["actual_power_kw"]
        current_soc = state["battery"]["soc"]
        dwell_time = state["diagnostics"]["state_dwell_time_sec"]

        action_history.append(current_action)
        power_history.append(actual_power)
        soc_history.append(current_soc)
        dwell_history.append(dwell_time)

    # 1. Action must NEVER toggle to IDLE during these 20 seconds
    assert "IDLE" not in action_history, f"Artificial toggling detected! Actions: {action_history}"
    assert all(a == "CHARGING" for a in action_history), f"Expected all CHARGING, got: {action_history}"

    # 2. Power must be consistently positive (charging)
    assert all(p > 0.05 for p in power_history), f"Power dropped below charging threshold: {power_history}"

    # 3. SOC must increase monotonically over time
    assert soc_history[-1] > soc_history[0], f"SOC must increase: {soc_history[0]} -> {soc_history[-1]}"
    for i in range(1, len(soc_history)):
        assert soc_history[i] >= soc_history[i-1], f"SOC decreased at step {i}: {soc_history}"

    # 4. State machine dwell time must grow monotonically
    assert dwell_history[-1] >= 19.0, f"Dwell time should have grown to >= 19s, got {dwell_history[-1]}"

    # 5. Check circuit wires and physical power flow
    last_state = engine.get_full_state()
    assert last_state["power_flow_direction"] == "SOURCE_TO_BATTERY"
    assert last_state["current"] > 0.05
    assert last_state["diagnostics"]["active_wire_count"] >= 2
    
    # Grid and battery wires must be active
    charger_wire = engine.circuit.connections["charger_to_battery"]
    assert charger_wire.active is True
    assert charger_wire.current_a > 0.05
    assert charger_wire.direction == "FORWARD"
    assert charger_wire.power_flow_direction == "SOURCE_TO_BATTERY"
    assert charger_wire.glow_intensity > 0.0


def test_continuous_idle_when_target_reached():
    """
    Critical Test 2: Verify continuous IDLE operation when battery SOC reaches target.
    Power must remain 0.0 kW and wires inactive.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    ev = engine.fleet_manager.fleet.get("EV-001")
    assert ev is not None
    ev.soc = 85.0
    ev.target_soc = 80.0
    ev.connected = True

    actions = []
    powers = []
    for _ in range(10):
        state = engine.step(wall_dt=1.0)
        actions.append(state["current_action"])
        powers.append(state["actual_power_kw"])

    assert all(a == "IDLE" for a in actions), f"Expected all IDLE, got: {actions}"
    assert all(p == 0.0 for p in powers), f"Expected 0.0 kW power during idle, got: {powers}"

    last_state = engine.get_full_state()
    assert last_state["power_flow_direction"] == "IDLE"
    charger_wire = engine.circuit.connections["charger_to_battery"]
    assert charger_wire.active is False
    assert charger_wire.current_a == 0.0
    assert charger_wire.direction == "IDLE"


def test_continuous_v2g_discharge():
    """
    Critical Test 3: Verify continuous V2G discharge operation under grid support scenario.
    Negative power flow, reverse direction BATTERY_TO_GRID, active wire glow, monotonic SOC decrease.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    ev = engine.fleet_manager.fleet.get("EV-001")
    assert ev is not None
    ev.soc = 75.0
    ev.v2g_reserve = 30.0
    ev.v2g_enabled = True
    ev.connected = True

    # Apply manual override DISCHARGE for testing continuous V2G
    engine.apply_manual_override("EV-001", "DISCHARGE")

    soc_history = []
    actions = []
    powers = []

    for _ in range(15):
        state = engine.step(wall_dt=1.0)
        actions.append(state["current_action"])
        powers.append(state["actual_power_kw"])
        soc_history.append(state["battery"]["soc"])

    # 1. Action is continuously DISCHARGING
    assert all(a == "DISCHARGING" for a in actions), f"Expected all DISCHARGING, got {actions}"

    # 2. Power is negative (discharging to grid)
    assert all(p < -0.05 for p in powers), f"Expected negative power, got {powers}"

    # 3. SOC decreases monotonically
    assert soc_history[-1] < soc_history[0], f"SOC did not decrease: {soc_history[0]} -> {soc_history[-1]}"

    # 4. Circuit wire direction and reverse flow
    last_state = engine.get_full_state()
    assert last_state["power_flow_direction"] == "BATTERY_TO_GRID"
    
    charger_wire = engine.circuit.connections["charger_to_battery"]
    assert charger_wire.active is True
    assert charger_wire.direction == "REVERSE"
    assert charger_wire.power_flow_direction == "BATTERY_TO_GRID"
    assert charger_wire.glow_intensity > 0.0


def test_decoupled_control_loop_and_action_persistence():
    """
    Critical Test 4: Verify control decision frequency (10.0s) is decoupled
    from the 1.0s physics tick.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()
    engine.control_interval_sec = 10.0

    eval_times = []
    for step_num in range(1, 25):
        state = engine.step(wall_dt=1.0)
        eval_times.append(state["diagnostics"]["time_since_last_control_eval_sec"])

    # First step triggers eval (time resets to 0.0 on eval tick), then counts up:
    # 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0 (eval), 1, 2, ...
    assert 0.0 in eval_times, "Control evaluation must reset timer upon evaluation"
    # Verify timer advances incrementally between evaluations
    assert eval_times[2] > eval_times[1]
    assert eval_times[3] > eval_times[2]


def test_circuit_topology_validation_and_structured_errors():
    """
    Critical Test 5: Verify circuit topology validation catches electrical violations
    and produces structured error records matching Section 15.
    """
    circuit = CircuitTopologyManager()

    # Standard circuit should validate successfully
    is_valid, errors = circuit.validate_circuit()
    assert is_valid is True, f"Standard circuit should be valid: {errors}"
    assert len(errors) == 0

    # 1. Test invalid connection: DC Battery directly to AC Grid (explosive short circuit)
    valid_conn, msg = circuit.validate_connection("EV_BATTERY", "DC+", "GRID", "GRID+")
    assert valid_conn is False
    assert "explosive short circuit" in msg

    # 2. Test missing critical connection
    circuit.connections.pop("grid_to_charger")
    is_valid, errors = circuit.validate_circuit()
    assert is_valid is False
    assert len(errors) > 0
    err = errors[0]
    assert "error_type" in err
    assert "component" in err
    assert "cause" in err
    assert "severity" in err
    assert "suggested_fix" in err
    assert err["severity"] == "CRITICAL"


def test_circuit_fault_stops_simulation_power():
    """
    Critical Test 6: Verify that when circuit is in FAULT, the engine sets
    power to 0.0 kW and transitions the state machine to FAULT.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    # Remove critical connection to simulate circuit hardware fault
    engine.circuit.connections.pop("charger_to_battery", None)

    state = engine.step(wall_dt=1.0)
    assert state["current_action"] == "FAULT"
    assert state["actual_power_kw"] == 0.0
    assert len(state["circuit_errors"]) > 0
    assert state["diagnostics"]["circuit_status"] == "FAULT"


def test_diagnostics_and_simulation_state_schema():
    """
    Critical Test 7: Verify all Section 2 top-level fields and Section 30
    diagnostics fields exist and have correct types.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    state = engine.step(wall_dt=1.0)

    # Required top-level fields (Section 2)
    top_level_keys = [
        "timestamp", "simulation_time", "running", "timestep", "grid", "solar",
        "load", "ev", "battery", "current_action", "requested_power_kw",
        "actual_power_kw", "voltage", "current", "energy", "power_flow_direction",
        "reward", "safety_status", "diagnostics", "circuit_errors"
    ]
    for key in top_level_keys:
        assert key in state, f"Missing required top-level key: {key}"

    # Required Diagnostics fields (Section 30)
    diag = state["diagnostics"]
    diag_keys = [
        "current_step", "sim_time", "action_state", "state_dwell_time_sec",
        "time_since_last_control_eval_sec", "control_interval_sec",
        "ppo_raw_action", "safety_approved", "safety_reason", "actual_power_kw",
        "battery_soc", "battery_voltage_v", "battery_current_a",
        "grid_frequency_hz", "feeder_utilization_pct", "circuit_status",
        "active_wire_count", "power_flow_direction"
    ]
    for key in diag_keys:
        assert key in diag, f"Missing required diagnostics key: {key}"


def test_graph_telemetry_continuous_buffer():
    """
    Critical Test 8: Run 60 seconds and verify 60+ continuous, timestamped
    telemetry points in the rolling history store (Section 48, Test 8).
    """
    engine = UnifiedSimulationEngine(auto_start=False)
    engine.reset()

    for _ in range(60):
        engine.step(wall_dt=1.0)

    history = engine.get_history(window_seconds=300)
    assert len(history) >= 60, f"Expected at least 60 telemetry points, got {len(history)}"

    # Check continuous timestamps
    timestamps = [pt["simulation_time"] for pt in history]
    assert len(set(timestamps)) == len(timestamps), "Timestamps must be continuous and unique"

    # Verify each point has all required metrics for real-time graphs
    for pt in history:
        assert "net_grid_load_kw" in pt
        assert "actual_power_kw" in pt
        assert "battery" in pt and "soc" in pt["battery"]
        assert "solar" in pt and "generation_kw" in pt["solar"]
        assert "current_action" in pt


def test_wire_glow_strictly_by_current():
    """
    Critical Test 9: Verify wire glow activates ONLY when current > 0.05 A,
    and is inactive / off when current is 0.0 A (Section 48, Test 9).
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    # 1. EV charging: current > 0 -> wire active and glowing
    ev = engine.fleet_manager.fleet.get("EV-001")
    assert ev is not None
    ev.soc = 40.0
    ev.target_soc = 80.0
    ev.connected = True

    state_chg = engine.step(wall_dt=1.0)
    wires_chg = state_chg["circuit_wires"]
    ev_wire_chg = wires_chg["bus_ev"]

    assert ev_wire_chg["active"] is True
    assert ev_wire_chg["glowing"] is True
    assert ev_wire_chg["current_a"] > 0.05
    assert ev_wire_chg["direction"] == "FORWARD"

    # 2. EV idle (target reached): current = 0 -> wire inactive and stops glowing
    ev.soc = 85.0
    state_idle = engine.step(wall_dt=1.0)
    wires_idle = state_idle["circuit_wires"]
    ev_wire_idle = wires_idle["bus_ev"]

    assert ev_wire_idle["active"] is False
    assert ev_wire_idle["glowing"] is False
    assert ev_wire_idle["current_a"] == 0.0
    assert ev_wire_idle["direction"] == "IDLE"


def test_v2g_direction_and_reverse_power_flow():
    """
    Critical Test 10: Verify current and power direction reverses during V2G
    discharge, flowing Battery -> Inverter -> Grid (Section 48, Test 10).
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    ev = engine.fleet_manager.fleet.get("EV-001")
    assert ev is not None
    ev.soc = 80.0
    ev.v2g_enabled = True
    ev.connected = True

    engine.apply_manual_override("EV-001", "DISCHARGE")
    state_v2g = engine.step(wall_dt=1.0)

    wires_v2g = state_v2g["circuit_wires"]
    ev_wire_v2g = wires_v2g["bus_ev"]

    # Direction must be REVERSE (Battery to Grid)
    assert ev_wire_v2g["active"] is True
    assert ev_wire_v2g["glowing"] is True
    assert ev_wire_v2g["direction"] == "REVERSE"
    assert state_v2g["power_flow_direction"] == "BATTERY_TO_GRID"
    assert state_v2g["actual_power_kw"] < -0.05


def test_grid_stress_hysteresis_and_v2g_entry_exit():
    """
    Critical Test 11: Verify GridStressEngine hysteresis, candidate timer accumulation,
    confirmation threshold (15s), automatic V2G entry, and recovery hysteresis exit.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    ev = engine.fleet_manager.fleet.get("EV-001")
    assert ev is not None
    ev.soc = 75.0
    ev.target_soc = 80.0
    ev.v2g_reserve = 30.0
    ev.v2g_enabled = True
    ev.connected = True

    # 1. Start normal charging
    state = engine.step(wall_dt=1.0)
    assert state["current_action"] == "CHARGING"
    assert state["actual_power_kw"] > 0.05

    # 2. Simulate high grid load spike: stress >= 75.0
    # Candidate timer should advance without immediately flipping state until confirmed
    engine.grid_stress_engine.high_load_confirmation_time_sec = 5.0
    engine.grid_stress_engine.v2g_recovery_time_sec = 5.0
    engine.simulated_grid_stress = 80.0

    # Advance 4 seconds: not yet confirmed, stays in CHARGING
    for _ in range(4):
        st = engine.step(wall_dt=1.0)
        assert st["current_action"] == "CHARGING"
        assert engine.grid_stress_engine.is_high_load_confirmed is False

    # Advance 2 more seconds: total candidate timer >= 5.0s -> high load confirmed -> V2G entry
    st = engine.step(wall_dt=2.0)
    assert engine.grid_stress_engine.is_high_load_confirmed is True
    assert st["current_action"] == "DISCHARGING"
    assert st["actual_power_kw"] < -0.05

    # 3. Simulate recovery: stress drops below exit threshold (<= 60.0)
    engine.simulated_grid_stress = 40.0
    # Hysteresis recovery timer requires 5.0s of confirmed recovery before exiting V2G
    st_rec1 = engine.step(wall_dt=3.0)
    assert engine.grid_stress_engine.is_high_load_confirmed is True  # Still in V2G during recovery timer
    assert st_rec1["current_action"] == "DISCHARGING"

    # Sustained recovery completes (total >= 5.0s) -> high load cleared -> resumes CHARGING (since SOC < target)
    st_rec2 = engine.step(wall_dt=3.0)
    assert engine.grid_stress_engine.is_high_load_confirmed is False
    assert st_rec2["current_action"] == "CHARGING"


def test_dynamic_countdown_timer():
    """
    Critical Test 12: Verify time_to_target_str and time_to_full_str count down dynamically.
    """
    engine = UnifiedSimulationEngine()
    engine.reset()

    ev = engine.fleet_manager.fleet.get("EV-001")
    assert ev is not None
    ev.soc = 50.0
    ev.target_soc = 80.0
    ev.max_soc = 95.0
    ev.connected = True

    st1 = engine.step(wall_dt=1.0)
    cd1 = st1["battery"]["time_to_target_str"]
    full1 = st1["battery"]["time_to_full_str"]
    assert cd1 != "00:00:00"
    assert full1 != "00:00:00"

    # Step forward 10 seconds of charging
    st2 = engine.step(wall_dt=10.0)
    cd2 = st2["battery"]["time_to_target_str"]
    assert cd2 < cd1, f"Countdown must decrease: {cd2} vs {cd1}"

    # Target reached -> countdown becomes 00:00:00
    ev.soc = 80.5
    st3 = engine.step(wall_dt=1.0)
    assert st3["battery"]["time_to_target_str"] == "00:00:00"


def test_action_state_machine_transition_diagnostics():
    """
    Critical Test 13: Verify ActionStateMachine records transitions and dwell time accurately.
    """
    sm = ActionStateMachine()
    assert sm.current_state == "IDLE"
    assert sm.dwell_time_sec == 0.0

    sm.update("CHARGING", 5.0, reason="Charge started")
    assert sm.current_state == "CHARGING"
    assert len(sm.transition_history) == 1
    assert sm.transition_history[-1]["to_state"] == "CHARGING"

    # Dwell in CHARGING for 10 more seconds
    sm.update("CHARGING", 10.0)
    assert sm.dwell_time_sec == 10.0
    assert len(sm.transition_history) == 1  # No new transition

    # Transition to IDLE
    sm.update("IDLE", 0.0, reason="Target reached")
    assert sm.current_state == "IDLE"
    assert len(sm.transition_history) == 2
    assert sm.transition_history[-1]["dwell_time_sec"] == 10.0


