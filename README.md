# ⚡ GridWise AI

### **Autonomous EV Charging, Digital Twin Circuit Simulation & Vehicle-to-Grid (V2G) Platform**

GridWise AI is an enterprise-grade energy management platform that combines a **Real-Time Digital Twin Circuit Simulation Engine**, **Deep Reinforcement Learning (PPO)**, and a **Deterministic Hard Safety Constraint Layer** to optimize EV charging and Vehicle-to-Grid (V2G) bidirectional power flow in real time.

Instead of treating EV charging as an uncontrolled on/off load, GridWise AI models electric vehicles as **intelligent, distributed flexible energy assets**. The platform continuously balances real-time electrical physics, customer departure guarantees, dynamic Time-of-Use (TOU) tariffs, solar generation, and grid feeder constraints.

---

## 📋 Table of Contents
- [System Highlights & Problem Statement](#-system-highlights--problem-statement)
- [Core Architecture & Continuous Simulation](#-core-architecture--continuous-simulation)
- [Physical Circuit Simulation & Wire Glow Dynamics](#-physical-circuit-simulation--wire-glow-dynamics)
- [PPO Reinforcement Learning & State Space](#-ppo-reinforcement-learning--state-space)
- [Hierarchical Safety Constraint Validator](#-hierarchical-safety-constraint-validator)
- [Circuit Diagnostics & Real-Time Telemetry](#-circuit-diagnostics--real-time-telemetry)
- [Tech Stack](#-tech-stack)
- [System Architecture Diagram](#-system-architecture-diagram)
- [API & WebSocket Specification](#-api--websocket-specification)
- [Getting Started & Installation](#-getting-started--installation)
- [Test Suite & Verification](#-test-suite--verification)
- [Demo Walkthrough](#-demo-walkthrough)
- [License](#-license)

---

## 🎯 System Highlights & Problem Statement

### **The Problem**
Uncontrolled EV charging creates acute strain on modern distribution networks:
- **Feeder Transformer Overload**: Simultaneous evening charging spikes trigger feeder congestion.
- **High Electricity Tariffs**: Charging during peak pricing hours inflates operating costs.
- **Renewable Curtailment**: Surplus daytime solar generation is underutilized.
- **Battery Health Degradation**: Aggressive, uncontrolled cycling accelerates cell degradation.
- **Missed V2G Value**: Failure to leverage EV battery reserves to stabilize grid frequency and supply peak power.

### **The GridWise AI Solution**
GridWise AI continuously executes a closed-loop control pipeline:
```text
REAL-TIME TELEMETRY → ENVIRONMENT → 19D STATE SPACE → PPO AGENT → SAFETY VALIDATOR → FINAL ACTION → DIGITAL TWIN CIRCUIT (PHYSICS & POWER FLOW) → BATTERY / GRID / SOLAR / LOAD → REWARD
```
- **CHARGE ⚡**: When solar generation is abundant, electricity tariffs are low, or departure deadlines require immediate energy intake.
- **IDLE ⏸️**: When dynamic electricity prices or grid feeder loads peak, holding EV state without artificial switching or oscillation.
- **DISCHARGE 🔋 (V2G)**: When the grid experiences critical peak stress and the EV has safe battery buffer above its V2G reserve floor, injecting power into the local bus/grid.

---

## ⚡ Core Architecture & Continuous Simulation

Unlike standard discrete-step dashboards that alternate states artificially, GridWise AI implements a **continuous, decoupled dual-rate simulation architecture**:

1. **Decoupled Dual-Rate Execution**:
   - **Physics Loop (1.0s interval)**: Solves Kirchhoff's current/voltage equations, Ohm's law, battery electrochemical SOC integration, and conservation of energy every second.
   - **AI Control Loop (10.0s interval)**: Evaluates the PPO policy and updates target operational states at a steady 10-second cadence.
   - **Event-Driven Early Interrupts**: If a physical safety boundary is reached (e.g., target SOC reached, V2G reserve floor hit, emergency grid curtailment), the engine intercepts immediately without waiting for the control timer.

2. **Action State Machine**:
   - Governs smooth transitions across `CHARGING`, `DISCHARGING`, `IDLE`, and `FAULT`.
   - Enforces a minimum dwell time (3.0s) and power slew rate ramping (max $1.0\text{ kW/s}$) to eliminate relay chatter and unnatural rapid toggling.

---

## 🔌 Physical Circuit Simulation & Wire Glow Dynamics

The frontend SVG electrical circuit dynamically reflects the backend physics engine calculations:

- **True Electrical Current Calculation**:
  $$I = \frac{P}{V}$$
  - **Grid $\leftrightarrow$ Charger Bus**: 400V 3-phase AC ($I = \frac{P}{\sqrt{3} \times 400\text{V}}$).
  - **Solar $\rightarrow$ Inverter Bus**: 600V DC ($I = \frac{P}{600\text{V}}$).
  - **Charger $\leftrightarrow$ EV Battery**: 400V DC traction pack ($I = \frac{P}{400\text{V}}$).
- **Physical Wire Glow Intensity**:
  - `high`: $I \ge 40\text{ A}$ (intense energetic glow).
  - `med`: $15\text{ A} \le I < 40\text{ A}$ (moderate glow).
  - `low`: $0.05\text{ A} < I < 15\text{ A}$ (subtle glow).
  - `none`: $I \le 0.05\text{ A}$ (completely idle, glow turned off, flow animation halted).
- **Bidirectional Flow & V2G Direction**:
  - During **Charging**, particles flow forward into the EV battery (`FORWARD`).
  - During **V2G Discharge**, SVG flow particles reverse direction (`REVERSE`) with dynamic amber/cyan energy accents.
  - During **Idle**, stroke dashes and glow filters turn off completely (`.wire-idle`).

---

## 🧠 PPO Reinforcement Learning & State Space

### **19-Dimensional State Space (`StateSpaceModule`)**
The PPO Actor-Critic model receives a normalized 19-dimensional continuous observation vector:
1. `battery_soc` ($0.0 - 1.0$)
2. `battery_temperature` (Normalized against thermal limits)
3. `battery_health` / SOH ($0.0 - 1.0$)
4. `battery_power` (Normalized $[-1.0, 1.0]$)
5. `grid_load` (Normalized kW)
6. `grid_capacity` (Installed feeder limit)
7. `grid_utilization` ($0.0 - 1.0$)
8. `grid_voltage` (Per-unit voltage deviation)
9. `grid_frequency` (Normalized around nominal 50.0 Hz)
10. `electricity_price` (Normalized dynamic TOU tariff)
11. `solar_generation` (Real-time kW output)
12. `solar_availability` ($0.0 - 1.0$)
13. `building_load` (Facility base load kW)
14. `ev_connected` (Binary $0/1$)
15. `time_until_departure` (Hours remaining normalized)
16. `target_soc` (User target SOC fraction)
17. `required_energy` (kWh needed to reach target)
18. `v2g_enabled` (User V2G permission flag $0/1$)
19. `previous_action` (Categorical action feedback)

### **Continuous & Discrete Policy Outputs**
- **Continuous Action**: Output in $[-1.0, 1.0]$ mapped to vehicle charger physical bounds ($[-P_{\text{max\_discharge}}, +P_{\text{max\_charge}}]$).
- **Discrete Action Mode**: `IDLE` (0), `CHARGE` (1), `DISCHARGE` (2).

---

## 🛡️ Hierarchical Safety Constraint Validator

All raw actions proposed by the PPO neural network pass through the **Safety Validator** before reaching the physical circuit:

| Rule | Validation Logic | Enforcement Action |
| :--- | :--- | :--- |
| **1. Max SOC / Target Protection** | $SOC \ge \min(max\_soc, target\_soc)$ and $P > 0$ | Intercept charge command $\rightarrow$ force **IDLE** (0 kW) |
| **2. V2G Reserve Floor Protection** | $SOC \le \max(min\_soc, v2g\_reserve)$ and $P < 0$ | Block discharge $\rightarrow$ hold battery in **IDLE** |
| **3. Departure SLA Travel Guarantee** | $t_{\text{needed}} / t_{\text{left}} \ge 0.70$ and $SOC < target\_soc$ | Override V2G/Idle $\rightarrow$ force **CHARGE** at safe power |
| **4. Feeder Capacity Overload Cap** | $P_{\text{charge}} > Feeder_{\text{headroom}}$ | Curtail charging power to available headroom |
| **5. V2G Grid Stress Gating** | Grid stress $< 70\%$ and condition is NORMAL | Prevent unnecessary discharge $\rightarrow$ switch to **IDLE** |
| **6. Topology / Connection Fault** | Broken wire or missing breaker connection | Trip circuit breaker $\rightarrow$ switch to **FAULT** safe state |

---

## 📊 Circuit Diagnostics & Real-Time Telemetry

### **Rolling Telemetry Buffer**
- Telemetry buffer maintains a rolling window of recent simulation frames.
- Streams live series into interactive Chart.js graphs:
  - **Net Feeder Load** (kW)
  - **EV Power** (+Charge / -V2G kW)
  - **Solar Generation** (kW)
  - **Primary EV Battery SOC** (%)
  - **Electricity Tariff** (₹/kWh)

### **Circuit Diagnostics Panel & Decision Stream Console**
- **Diagnostics Panel**: Monitors Grid Port, Solar Inverter, Charger, Battery Pack, Feeder Headroom, and Conservation-of-Energy balance error in real time.
- **Simulation Event Console (`#sim-log-console`)**: Logs every PPO decision, safety filter intervention, mode change, and circuit telemetry tick with precise timestamps.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.11+, FastAPI, Starlette, Uvicorn, SQLAlchemy.
- **Reinforcement Learning**: Gymnasium, Stable-Baselines3, PyTorch, NumPy.
- **Frontend**: Responsive HTML5, Tailwind CSS, Lucide Icons, Chart.js, WebSocket Client.
- **Simulation**: Custom Continuous Electrical Digital Twin Engine, Kirchhoff Power Flow Solver.
- **Testing**: Pytest, Pytest-Asyncio.

---

## 🏛️ System Architecture Diagram

```text
       ┌────────────────────────────────────────────────────────┐
       │              Browser Single-Page App (SPA)             │
       │   • Digital Twin Circuit Schematic (Glowing SVG Wires) │
       │   • Live Telemetry Charts (Rolling 60-Point Stream)    │
       │   • Circuit Diagnostics & PPO Decision Event Console   │
       └───────────────────────────┬────────────────────────────┘
                                   │
                          REST API │ WebSockets (/ws/simulation)
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │             FastAPI / Starlette Backend Engine         │
       └────┬──────────────────────┬──────────────────────┬─────┘
            │                      │                      │
            ▼                      ▼                      ▼
   ┌────────────────┐    ┌─────────────────┐    ┌──────────────────┐
   │ Real-Time Data │    │ Physical Solar  │    │ EV Battery Twin  │
   │ Service (SLDC/ │    │ Geometry Model  │    │ (Thevenin / SOC  │
   │ IEX Tariffs)   │    │ (Irradiance)    │    │ Integration)     │
   └───────┬────────┘    └────────┬────────┘    └────────┬─────────┘
           │                      │                      │
           └──────────────────────┼──────────────────────┘
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │         19-Dimensional State Vector Construction       │
       └──────────────────────────┬─────────────────────────────┘
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │          PPO Reinforcement Learning Controller         │
       │           (Continuous / Discrete Action Policy)        │
       └──────────────────────────┬─────────────────────────────┘
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │         Hierarchical Safety Constraint Validator       │
       │    (Feeder Headroom, Departure SLA, SOC Floor/Ceiling) │
       └──────────────────────────┬─────────────────────────────┘
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │          Unified Circuit Topology & Power Flow         │
       │     (Ohm's Law, Wire Currents, Conservation of Energy) │
       └────────────────────────────────────────────────────────┘
```

---

## 🔌 API & WebSocket Specification

### **Digital Twin & Telemetry Endpoints**
- `GET /api/digital-twin/state`: Full authoritative snapshot of electrical topology, wire currents, battery state, and AI decisions.
- `GET /api/telemetry/history?window=60`: Rolling historical time-series buffer for instant chart pre-fill.
- `GET /api/simulation/status`: Simulation clock state, speed multiplier (1x, 5x, 10x), and active mode.
- `POST /api/simulation/start`: Resume continuous background simulation.
- `POST /api/simulation/pause`: Pause simulation.
- `POST /api/simulation/reset`: Reset simulation clock and fleet states.
- `POST /api/evs/{ev_id}/override`: Set manual operator override (`CHARGE`, `DISCHARGE`, `IDLE`, or `null`).

### **WebSockets**
- `WS /ws/simulation`: Bi-directional real-time telemetry stream emitting `digital_twin_update` and `SIMULATION_UPDATE` packets on every physics tick.

---

## 🚀 Getting Started & Installation

### **Prerequisites**
- Python 3.11 or higher
- Git

### **Installation**
1. Clone the repository:
   ```bash
   git clone https://github.com/Nishanth-M-P/EV.git
   cd EV
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/macOS
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### **Running the Application**
Launch the server via:
```bash
python run.py
```
Open your browser at:
**`http://127.0.0.1:8000`**

---

## 🧪 Test Suite & Verification

The project includes an automated test suite covering continuous simulation physics, wire currents, safety layer interventions, and PPO closed-loop control:

```bash
# Run full pytest suite (82 unit and integration tests)
pytest

# Run multi-minute continuous simulation scenarios
python verify_simulation.py
```

All 82 tests pass cleanly with zero warnings or balance errors.

---

## 🎬 Demo Walkthrough

1. **Morning Connection & Charge**: EV connects at 45% SOC. The wire glows high forward (`FORWARD`, $57.3\text{ A}$), steadily increasing battery energy without toggle interruptions.
2. **Solar Peak Alignment**: Midday solar generation reaches peak output, directly supplying charging power and minimizing grid imports.
3. **Evening Peak & V2G Discharge**: Grid load surges during peak tariff hours. Eligible EVs switch to V2G export (`REVERSE`, $-27.1\text{ A}$), sending power back to the grid.
4. **Target Reached & Standby Idle**: Once the vehicle battery satisfies user target SOC (e.g. 80%), charging halts immediately. Current drops to $0.0\text{ A}$ and wire glow turns completely OFF (`IDLE`).

---

## 📄 License
Developed as an open-source AI energy management platform for research, smart grid optimization, and V2G commercial deployment.
