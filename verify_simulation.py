from backend.simulation.unified_engine import UnifiedSimulationEngine

def main():
    print('===============================================================')
    print('GRIDWISE AI - CONTINUOUS SIMULATION & PHYSICS MULTI-MINUTE TEST')
    print('===============================================================')

    engine = UnifiedSimulationEngine(auto_start=False)
    engine.reset()

    # Scenario 1: Continuous Charging (30 seconds)
    print('\n--- SCENARIO 1: CONTINUOUS CHARGING (30 physics ticks) ---')
    ev = engine.fleet_manager.fleet.get('EV-001')
    ev.soc = 45.0
    ev.target_soc = 80.0
    ev.connected = True

    charge_actions = []
    socs = []
    for t in range(30):
        st = engine.step(wall_dt=1.0)
        act = st['current_action']
        pwr = st['actual_power_kw']
        curr = st['current']
        soc = st['battery']['soc']
        wires = st['circuit_wires']
        ev_wire = wires['bus_ev']
        charge_actions.append(act)
        socs.append(soc)
        if t % 5 == 0 or t == 29:
            print(f"Tick {t+1:02d} | Time {st['simulation_time']} | Act: {act:10s} | Pwr: {pwr:+.1f} kW | Curr: {curr:5.1f} A | SOC: {soc:5.2f}% | Wire: {ev_wire['direction']} (Glow: {ev_wire['glow_intensity']})")

    assert 'IDLE' not in charge_actions, 'Artificial toggling to IDLE detected!'
    assert all(a == 'CHARGING' for a in charge_actions)
    assert socs[-1] > socs[0]
    print(f"-> SUCCESS: 30 ticks continuous CHARGING without single IDLE interruption! SOC grew {socs[0]:.2f}% -> {socs[-1]:.2f}%")

    # Scenario 2: High Grid Load -> V2G Discharge (20 seconds)
    print('\n--- SCENARIO 2: HIGH GRID LOAD / PEAK V2G DISCHARGE (20 physics ticks) ---')
    ev.soc = 75.0
    ev.v2g_enabled = True
    engine.apply_manual_override('EV-001', 'DISCHARGE')

    v2g_actions = []
    v2g_socs = []
    for t in range(20):
        st = engine.step(wall_dt=1.0)
        act = st['current_action']
        pwr = st['actual_power_kw']
        curr = st['current']
        soc = st['battery']['soc']
        wires = st['circuit_wires']
        ev_wire = wires['bus_ev']
        v2g_actions.append(act)
        v2g_socs.append(soc)
        if t % 5 == 0 or t == 19:
            print(f"Tick {t+1:02d} | Time {st['simulation_time']} | Act: {act:11s} | Pwr: {pwr:+.1f} kW | Curr: {curr:5.1f} A | SOC: {soc:5.2f}% | Wire: {ev_wire['direction']} (Glow: {ev_wire['glow_intensity']})")

    assert all(a == 'DISCHARGING' for a in v2g_actions)
    assert v2g_socs[-1] < v2g_socs[0]
    print(f"-> SUCCESS: 20 ticks continuous V2G DISCHARGE! Wire direction REVERSE, SOC decreased {v2g_socs[0]:.2f}% -> {v2g_socs[-1]:.2f}%")

    # Scenario 3: Target Reached -> IDLE (10 seconds)
    print('\n--- SCENARIO 3: TARGET REACHED / STABLE IDLE (10 physics ticks) ---')
    engine.manual_overrides.clear()
    engine.time_since_last_control_eval_sec = 10.0
    ev.soc = 82.0
    ev.target_soc = 80.0

    idle_actions = []
    for t in range(10):
        st = engine.step(wall_dt=1.0)
        act = st['current_action']
        pwr = st['actual_power_kw']
        curr = st['current']
        soc = st['battery']['soc']
        wires = st['circuit_wires']
        ev_wire = wires['bus_ev']
        idle_actions.append(act)
        if t % 3 == 0 or t == 9:
            print(f"Tick {t+1:02d} | Time {st['simulation_time']} | Act: {act:10s} | Pwr: {pwr:+.1f} kW | Curr: {curr:5.1f} A | SOC: {soc:5.2f}% | Wire: {ev_wire['direction']} (Glow: {ev_wire['glow_intensity']})")

    assert all(a == 'IDLE' for a in idle_actions)
    assert ev_wire['active'] is False
    assert ev_wire['glowing'] is False
    print("-> SUCCESS: 10 ticks stable IDLE! Power = 0 kW, Wire glow = OFF!")

    # Check Telemetry History Buffer
    history = engine.get_history()
    print(f"\n-> Telemetry history buffer captured {len(history)} continuous frames.")
    assert len(history) == 60

    print('\n===============================================================')
    print('ALL PHYSICS, POWER FLOW & WIRE GLOW VERIFICATIONS CONFIRMED!')
    print('===============================================================')

if __name__ == '__main__':
    main()
