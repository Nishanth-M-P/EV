# ⚡ GridWise AI

<div align="center">

### **Autonomous EV Fleet Charging, Digital Twin Circuit Simulation & Vehicle-to-Grid (V2G) Platform**

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PyTorch](https://img.shields.io/badge/AI-PyTorch%20%7C%20PPO-EE4C2C.svg?style=for-the-badge&logo=pytorch&logoColor=white)](https://pytorch.org)
[![WebSockets](https://img.shields.io/badge/Real--Time-WebSockets-010101.svg?style=for-the-badge&logo=socketdotio&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
[![TailwindCSS](https://img.shields.io/badge/Frontend-TailwindCSS-38B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

[**🔬 Digital Twin Simulator Lab**](http://127.0.0.1:8000/simulator) • [**📊 Live Fleet Monitoring**](http://127.0.0.1:8000/) • [**📑 Interactive API Docs**](http://127.0.0.1:8000/docs)

</div>

---

## 📖 Executive Summary

**GridWise AI** is an enterprise-grade digital-twin energy management platform designed to transform electric vehicles from passive electrical loads into **intelligent, distributed, flexible energy storage assets**. 

By pairing **High-Fidelity Electrical Digital Twin Simulation** with **Deep Reinforcement Learning (Proximal Policy Optimization - PPO)** and a **Deterministic Hierarchical Safety Layer**, GridWise AI continuously optimizes fleet charging schedules, performs peak-shaving, maximizes solar renewable absorption, and delivers active Vehicle-to-Grid (V2G) power support to the electrical distribution network in real time.

---

## 🌟 Key Platform Highlights

```text
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   GRIDWISE AI PLATFORM                                 │
 ├─────────────────────────────────────────┬──────────────────────────────────────────────┤
 │  🔬 Digital Twin Circuit Simulator Lab  │  📊 Main Enterprise Monitoring Platform      │
 │  • Interactive 8-Node Electrical Canvas │  • Fleet Real-Time Telemetry & SOC Gauges    │
 │  • Multi-Battery Fleet CAD Inspection   │  • Autonomous Active Charging for All Packs  │
 │  • Hardware Relays & Contactor Telemetry│  • Live WebSocket Data Stream with Heartbeat │
 │  • Zoom, Pan & GPU CSS Wire Glow Physics│  • Dynamic TOU Tariffs, Solar & Feeder Head  │
 └─────────────────────────────────────────┴──────────────────────────────────────────────┘
```

- **⚡ Real-Time Physics & Dual-Rate Execution**: Solves Ohm’s law, Kirchhoff’s current/voltage laws, battery electrochemical Thevenin models, and conservation of energy every 1 second, with AI policy evaluation every 10 seconds.
- **🔋 Full Fleet Multi-Battery Synchronization**: Any battery added in the main monitoring dashboard immediately appears and actively charges in the Digital Twin Simulator Lab without refreshing.
- **🔬 Interactive Internal CAD Pack Inspection**: Deep inspection of modular 400V LFP battery packs (MOD-01 through MOD-06), individual cell voltages, temperatures, SOH (99.4%), cell delta $\Delta V$, and pyro-fuses.
- **🛡️ 6-Layer Hard Safety Constraint Enforcer**: Zero uncommanded violations. Guarantees departure deadlines (SLA), protects battery health, prevents transformer feeder overloads, and enforces strict V2G reserve floors.
- **🧠 Explainable AI (XAI)**: Comprehensive decision auditing and transparency breakdown for each vehicle policy action (`CHARGE`, `DISCHARGE/V2G`, or `IDLE`).
- **🎨 Modern Dual-Theme Interface**: GPU-accelerated CSS animations, high-contrast Dark and Light modes, responsive sparklines, and seamless Chart.js time-series analytics.

---

## 📋 Table of Contents
- [System Architecture](#-system-architecture)
- [Digital Twin Simulator Lab (`/simulator`)](#-digital-twin-simulator-lab-simulator)
- [Enterprise Fleet Monitoring (`/`)](#-enterprise-fleet-monitoring-)
- [Physics & Electrical Circuit Dynamics](#-physics--electrical-circuit-dynamics)
- [PPO Reinforcement Learning Engine](#-ppo-reinforcement-learning-engine)
- [Hierarchical Safety Constraint Validator](#-hierarchical-safety-constraint-validator)
- [REST API & WebSocket Protocol](#-rest-api--websocket-protocol)
- [Quick Start & Installation](#-quick-start--installation)
- [Verification & Automated Test Suite](#-verification--automated-test-suite)
- [License](#-license)

---

## 🏛️ System Architecture

```text
       ┌────────────────────────────────────────────────────────┐
       │              Browser Single-Page App (SPA)             │
       │   • Digital Twin Circuit Schematic (Glowing SVG Wires) │
       │   • Multi-Battery Internal CAD Inspection Modal        │
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

## 🔬 Digital Twin Simulator Lab (`/simulator`)

The **Digital Twin Simulator Lab** provides an interactive virtual engineering workspace for testing and observing microgrid dynamics in real time:

### **1. Schematic Canvas Architecture**
- **Electrical Grid Substation**: 11 kV transmission-to-distribution transformer, monitoring real-time SLDC demand (GW), frequency (Hz), and supply margin.
- **Renewable Generation Tap**: Solar irradiance calculations, wind farm generation, and total renewable mix percentage.
- **Electricity Market Price (IEX)**: Real-time tariff signals with peak/normal/off-peak classification.
- **DRL PPO Controller**: Continuous policy evaluation, reward indicators, confidence scores, and urgency ratings.
- **Bidirectional V2G Charger**: 22 kW rated CCS Combo 2 bidirectional inverter supporting G2V charging and V2G reverse power flow.
- **EV Integrated Battery**: Live pack SOC %, stored energy (kWh), active charging power (kW), and fleet charging summary counter.
- **Digital Energy Meter**: High-precision passive observation tap tracking import/export kW, accumulated kWh, and power flow vector.

### **2. Advanced Canvas Controls**
- **Zoom & Pan Engine**: Instant `Zoom In (+)`, `Zoom Out (-)`, `100% Reset`, and `Fit to Screen` controls.
- **GPU-Accelerated CSS Animations**: Smooth glowing electrical pulses replace legacy SVG animations, providing 60 FPS performance without CPU overhead.
- **Dynamic Connection Management**: Validates electrical rules to prevent illegal circuits.

### **3. Multi-Battery CAD Inspection Modal**
- Click **"CAD"** on any battery node or inspector card to open the internal pack enclosure view:
  - **Modular Cell Blocks (MOD-01 to MOD-06)**: 18S series cell matrix with individual cell voltage ($3.32\text{--}3.34\text{ V/cell}$) and module temperatures.
  - **Live Pack Switching**: A pack selector dropdown allows inspecting **any** vehicle in the fleet (`EV-001`, `EV-004`, `EV-F49A`, etc.).
  - **Master BMS Readouts**: Pack voltage (380V--420V), DC current (A), cell balance delta ($\Delta V = 8\text{ mV}$), state of health (99.4% SOH), and safety contactors (`HV (+) / (-) CLOSED`).

---

## 📊 Enterprise Fleet Monitoring (`/`)

The primary platform interface offers an enterprise-level operational dashboard:

- **Unified Fleet Overview**: Real-time fleet charging table detailing Model Name, Capacity, Current SOC %, Target SOC %, Arrival/Departure schedules, and active power flow.
- **Active Autonomous Charging**: All connected batteries below target SOC charge continuously and autonomously without unnatural toggling.
- **Operator Override Controls**:
  - **`CHG`**: Force direct high-priority charging.
  - **`V2G`**: Force immediate grid support discharge.
  - **`AUTO`**: Return vehicle to autonomous AI PPO optimization.
- **Explainable AI (XAI) Modal**: Deep-dive audit explaining the exact reasoning behind every AI decision, safety rule evaluations, and expected savings.
- **Live Connection Badge**: Real-time heartbeat indicator (`● LIVE` with green pulse when connected, `▲ OFFLINE` failover upon disconnection).

---

## 🔌 Physics & Electrical Circuit Dynamics

### **1. Conservation of Energy & Power Flow**
At every 1-second simulation tick, the power balance equation is strictly satisfied:
$$P_{\text{grid}} + P_{\text{solar}} = P_{\text{ev\_charging}} + P_{\text{building\_aux}} + P_{\text{losses}} - P_{\text{v2g}}$$

$$\text{Balance Error} = \left| \sum P_{\text{sources}} - \sum P_{\text{sinks}} \right| < 10^{-4}\text{ kW}$$

### **2. Electrochemical Battery Physics (Thevenin Model)**
$$V_{\text{terminal}} = V_{\text{ocv}}(SOC) + I \cdot R_{\text{internal}}$$
$$SOC(t + \Delta t) = SOC(t) + \frac{P \cdot \eta \cdot \Delta t}{C_{\text{capacity}}} \times 100$$
- Open-circuit voltage curve dynamically tracks battery chemistry ($350\text{--}425\text{ V}$).
- Thermal dynamics integrate Joule heating ($I^2 R$) and passive ambient cooling.

### **3. Wire Current & Dynamic Glow Intensity**
Wire glow on the digital twin canvas directly mirrors the physical current calculated by Ohm's Law:
$$I = \frac{P}{V}$$

| Current Magnitude | Glow Class | Visual Effect | Status |
| :--- | :--- | :--- | :--- |
| $I \ge 40.0\text{ A}$ | `.wire-high` | Vivid energetic glow (Emerald / Cyan) | Heavy Fast Charge / V2G |
| $15.0\text{ A} \le I < 40.0\text{ A}$ | `.wire-med` | Moderate steady glow | Standard Level 2 Power Flow |
| $0.05\text{ A} < I < 15.0\text{ A}$ | `.wire-low` | Subtle pulsing trace | Trickle / Gating Power |
| $I \le 0.05\text{ A}$ | `.wire-idle` | Streamers halt, glow completely OFF | Standby / Disconnected |

---

## 🧠 PPO Reinforcement Learning Engine

### **19-Dimensional Normalized State Space**
The PPO Agent observes an authoritative continuous vector on every decision step:

| Index | Feature | Description | Range |
| :---: | :--- | :--- | :---: |
| `0` | `battery_soc` | Battery state of charge | $[0.0, 1.0]$ |
| `1` | `battery_temp` | Pack temperature normalized | $[0.0, 1.0]$ |
| `2` | `battery_soh` | State of health | $[0.0, 1.0]$ |
| `3` | `battery_power` | Commanded power ratio | $[-1.0, 1.0]$ |
| `4` | `grid_demand` | Regional grid demand | Normalized GW |
| `5` | `feeder_headroom` | Remaining local feeder capacity | $[0.0, 1.0]$ |
| `6` | `feeder_utilization`| Local transformer load percentage | $[0.0, 1.0]$ |
| `7` | `grid_voltage` | Bus voltage deviation | Per-unit |
| `8` | `grid_frequency` | Frequency deviation from nominal 50Hz | Per-unit |
| `9` | `market_price` | Real-time IEX electricity price | Normalized ₹/kWh |
| `10` | `solar_output` | Current solar output | Normalized kW |
| `11` | `solar_potential`| Solar daylight factor | $[0.0, 1.0]$ |
| `12` | `building_load` | Auxiliary building consumption | Normalized kW |
| `13` | `ev_connected` | Physical plug connection state | Binary $\{0, 1\}$ |
| `14` | `time_to_dep` | Hours remaining until scheduled departure | Normalized $[0, 1]$ |
| `15` | `target_soc` | User-defined target SOC | $[0.0, 1.0]$ |
| `16` | `required_energy`| Remaining energy needed | Normalized kWh |
| `17` | `v2g_enabled` | Vehicle V2G authorization flag | Binary $\{0, 1\}$ |
| `18` | `prev_action` | Action executed in previous timestep | $\{0, 1, 2\}$ |

---

## 🛡️ Hierarchical Safety Constraint Validator

Every proposed action from the AI policy must pass through deterministic safety filters:

```text
       [ PPO Proposed Action ]
                  │
                  ▼
   [ Rule 1: Max SOC / Target Protection ]    ──▶ If SOC >= Target ──▶ Force IDLE (0 kW)
                  │
                  ▼
   [ Rule 2: V2G Reserve Floor Protection ]   ──▶ If SOC <= Floor  ──▶ Force IDLE (0 kW)
                  │
                  ▼
   [ Rule 3: Departure SLA Travel Guarantee ] ──▶ If Time Critical ──▶ Force CHARGE
                  │
                  ▼
   [ Rule 4: Feeder Capacity Overload Cap ]   ──▶ If Load > Feeder ──▶ Curtail to Headroom
                  │
                  ▼
   [ Rule 5: Low Stress Grid V2G Gating ]     ──▶ If Grid Normal   ──▶ Block V2G Discharge
                  │
                  ▼
   [ Rule 6: Circuit Topology Integrity ]     ──▶ If Broken Wire   ──▶ Trip FAULT Safe
                  │
                  ▼
         [ Executed Action ]
```

---

## 🔌 REST API & WebSocket Protocol

### **REST Endpoints**

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/simulation/current/state` | Authoritative simulation snapshot (grid, solar, fleet, meter, AI). |
| `GET` | `/api/evs` | List all vehicles, active SOC %, status, and manual overrides. |
| `POST` | `/api/evs` | Add a new EV battery twin to the simulation and circuit. |
| `DELETE`| `/api/evs/{ev_id}` | Remove a vehicle from the fleet. |
| `POST` | `/api/evs/{ev_id}/override` | Set manual operator override (`CHARGE`, `DISCHARGE`, `IDLE`, or clear). |
| `POST` | `/api/simulation/run` | Start or resume continuous background execution. |
| `POST` | `/api/simulation/pause` | Pause continuous simulation. |
| `POST` | `/api/simulation/reset` | Reset simulation clock, topology, and fleet to initial state. |
| `POST` | `/api/simulation/speed` | Set simulation speed multiplier (`1x`, `2x`, `5x`, `10x`). |
| `POST` | `/api/circuit/validate` | Verify electrical legality of candidate component connection. |

### **WebSocket Stream**
- **Endpoint**: `ws://127.0.0.1:8000/ws/simulation`
- **Broadcast Frequency**: Continuous 1.0s physics ticks emitting JSON telemetry packets:
  ```json
  {
    "type": "SIMULATION_UPDATE",
    "sequence": 1420,
    "simulation_time": "18:30:15",
    "actual_power_kw": 22.0,
    "total_charging_power_kw": 66.8,
    "evs": [
      {
        "ev_id": "EV-001",
        "name": "Tata Nexon EV",
        "soc": 68.5,
        "capacity_kwh": 72.0,
        "power_kw": 22.0,
        "charging_state": "CHARGING",
        "connected": true
      }
    ],
    "grid": { "demand_gw": 13.74, "frequency_hz": 49.98 },
    "solar": { "generation_kw": 0.0 }
  }
  ```

---

## 🚀 Quick Start & Installation

### **Prerequisites**
- **Python**: 3.11 or higher
- **Git**

### **1. Clone & Set Up Environment**
```bash
# Clone the repository
git clone https://github.com/Nishanth-M-P/EV.git
cd EV

# Create virtual environment
python -m venv .venv

# Activate on Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Or activate on Linux / macOS:
source .venv/bin/activate
```

### **2. Install Dependencies**
```bash
pip install -r requirements.txt
```

### **3. Start Platform**
```bash
python run.py
```

### **4. Open in Browser**
- **Main Monitoring Platform**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Digital Twin Simulator Lab**: [http://127.0.0.1:8000/simulator](http://127.0.0.1:8000/simulator)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Verification & Automated Test Suite

Run the full automated test suite covering unit physics, safety rules, multi-battery charging, and WebSocket streaming:

```bash
# Run all unit and integration tests
pytest

# Test fleet battery addition and active charging
python scratch/check_fleet.py
```

---

## 📄 License
This project is open-source under the **MIT License**. Created for advanced research, digital twin simulation, and industrial deployment of V2G and smart microgrid systems.
