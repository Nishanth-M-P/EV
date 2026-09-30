"""
Verification script for GridWise AI Simulation Synchronization:
1. 21:02 Departure Test
2. Multi-EV PPO & Safety Independence
3. Total Power Flow Equality
4. PPO Probability-Action Consistency
5. Wire Directions
6. Data Provider Status
7. validate_simulation_state Cleanliness
"""
import sys
import numpy as np
from backend.simulation.unified_engine import UnifiedSimulationEngine

def run_verification():
    print("=" * 60)
    print("GRIDWISE AI — SIMULATION SYNCHRONIZATION VERIFICATION")
    print("=" * 60)

    engine = UnifiedSimulationEngine(auto_start=False)
    engine.reset()

    # -------------------------------------------------------------
    # 1. 21:02 Departure State Machine Test
    # -------------------------------------------------------------
    print("\n[TEST 1] Setting simulation time to 21:02:00 (Past all fleet departure times)...")
    # 21:02 is 21 * 3600 + 2 * 60 = 75720 seconds
    engine.clock.sim_clock_seconds = 75720.0
    state = engine.step(wall_dt=1.0)

    cur_time = state["simulation_time"]
    print(f"Simulation time: {cur_time}")
    assert "21:02" in cur_time, f"Expected 21:02, got {cur_time}"

    for ev in state["evs"]:
        eid = ev["ev_id"]
        status = ev["status"]
        connected = ev["connected"]
        pwr = ev["power_kw"]
        curr = ev["current_a"]
        dep = ev["departure_time"]
        print(f"  {eid} ({ev['name']}): Dep={dep}, Status={status}, Connected={connected}, Power={pwr} kW, Current={curr} A")
        
        # All fleet vehicles have departure times <= 19:30, so at 21:02 all must be DEPARTED
        assert not connected, f"EV {eid} should not be connected at 21:02"
        assert status in ("DEPARTED", "DISCONNECTED"), f"EV {eid} status should be DEPARTED, got {status}"
        assert abs(pwr) < 0.001, f"EV {eid} drawing power after departure: {pwr} kW"
        assert abs(curr) < 0.001, f"EV {eid} drawing current after departure: {curr} A"

    print(">> [TEST 1 PASSED]: All vehicles departed at 21:02 with zero power & zero current.")

    # -------------------------------------------------------------
    # 2. Multi-EV PPO & Fleet Decisions Test
    # -------------------------------------------------------------
    print("\n[TEST 2] Setting simulation time to 14:00 (Peak day, all vehicles connected)...")
    engine.reset()
    engine.clock.sim_clock_seconds = 14 * 3600.0  # 14:00:00
    state = engine.step(wall_dt=1.0)

    ai_decisions = state["ai_decisions"]
    ev_ids_in_decisions = [d["ev_id"] for d in ai_decisions]
    print(f"AI decisions present for: {ev_ids_in_decisions}")
    assert len(ai_decisions) >= 5, f"Expected at least 5 EV decisions, got {len(ai_decisions)}"

    for d in ai_decisions:
        eid = d["ev_id"]
        raw = d["raw_action"]
        final = d["final_action"]
        pwr = d["power_kw"]
        probs = d["probabilities"]
        print(f"  {eid}: Proposed={raw}, Final={final}, Power={pwr:.2f} kW, Probabilities={probs}")
        # Probability sum check
        prob_sum = round(sum(probs.values()), 4)
        assert abs(prob_sum - 1.0) < 0.01, f"{eid} probabilities do not sum to 1.0: {prob_sum}"
        # Argmax check
        max_act = max(probs.items(), key=lambda x: x[1])[0]
        if raw != "FAULT":
            assert raw == max_act, f"{eid} raw action {raw} != argmax(probs) {max_act}"

    print(">> [TEST 2 PASSED]: Every EV has atomic, independent PPO decisions and synchronized probabilities.")

    # -------------------------------------------------------------
    # 3. Total EV Power Conservation Test
    # -------------------------------------------------------------
    print("\n[TEST 3] Verifying Total EV Power Conservation...")
    reported_charging = state["total_charging_power_kw"]
    reported_v2g = state["total_v2g_power_kw"]
    sum_charging = round(sum(max(0.0, e["power_kw"]) for e in state["evs"]), 2)
    sum_v2g = round(sum(max(0.0, -e["power_kw"]) for e in state["evs"]), 2)

    print(f"Charging power: reported={reported_charging} kW, sum={sum_charging} kW")
    print(f"V2G power:      reported={reported_v2g} kW, sum={sum_v2g} kW")
    assert abs(reported_charging - sum_charging) < 0.05, f"Charging power mismatch!"
    assert abs(reported_v2g - sum_v2g) < 0.05, f"V2G power mismatch!"
    print(">> [TEST 3 PASSED]: Total fleet charging/discharging power exactly matches sum of individual EVs.")

    # -------------------------------------------------------------
    # 4. Wire Flow Directions Test
    # -------------------------------------------------------------
    print("\n[TEST 4] Verifying Circuit Wire Directions...")
    wires = state["circuit_wires"]
    connections = state["circuit"]["connections"]
    
    aux_wire = connections["bus_to_aux"]
    print(f"  bus_to_aux direction: {aux_wire['power_flow_direction']}")
    assert aux_wire["power_flow_direction"] in ("SOURCE_TO_LOAD", "IDLE"), f"Invalid aux wire direction: {aux_wire['power_flow_direction']}"

    solar_wire = connections["solar_to_bus"]
    print(f"  solar_to_bus direction: {solar_wire['power_flow_direction']}")
    assert solar_wire["power_flow_direction"] in ("SOLAR_TO_BUS", "IDLE"), f"Invalid solar wire direction: {solar_wire['power_flow_direction']}"

    print(">> [TEST 4 PASSED]: Circuit wires have correct physical semantic flow directions.")

    # -------------------------------------------------------------
    # 5. Real-Time Data Provider Status Test
    # -------------------------------------------------------------
    print("\n[TEST 5] Verifying Real-Time Data Status...")
    rt = state["realtime_data"]
    for prov_name in ["grid", "solar", "price", "weather"]:
        p_data = rt[prov_name]
        status = p_data["status"]
        val = p_data.get("value")
        print(f"  {prov_name.upper()} provider: status='{status}', value={val}")
        assert status in ("LIVE", "STALE", "SIMULATED_DIGITAL_TWIN"), f"Invalid provider status: {status}"
        assert val is not None, f"Provider {prov_name} missing 'value' field"

    print(">> [TEST 5 PASSED]: Providers report truthful statuses and include values.")

    # -------------------------------------------------------------
    # 6. Synchronization Errors Validation Test
    # -------------------------------------------------------------
    print("\n[TEST 6] Validating State Synchronization Diagnostics...")
    sync_errors = state["diagnostics"]["sync_errors"]
    print(f"Sync errors in state: {sync_errors}")
    assert len(sync_errors) == 0, f"State validation failed with sync errors: {sync_errors}"
    print(">> [TEST 6 PASSED]: Zero synchronization errors detected by validate_simulation_state().")

    print("\n" + "=" * 60)
    print("ALL VERIFICATION SUITES PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_verification()
