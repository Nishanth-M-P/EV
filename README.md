# ⚡ GridWise AI

### **Autonomous EV Charging & Vehicle-to-Grid (V2G) Energy Management Platform**

GridWise AI is an intelligent energy management platform that leverages **Reinforcement Learning (RL)** and a **Hard Safety Constraint Layer** to optimize EV charging and Vehicle-to-Grid (V2G) decisions in real time.

Instead of charging electric vehicles immediately upon plug-in, GridWise AI treats EVs as **intelligent distributed energy resources**. The platform dynamically balances user departure requirements, electricity tariffs (Time-of-Use dynamic pricing), solar/renewable availability, grid stress levels, and battery health degradation.

---

## 📋 Table of Contents
- [Product Vision & Problem Statement](#-product-vision--problem-statement)
- [Core Features](#-core-features)
- [AI & Reinforcement Learning Architecture](#-ai--reinforcement-learning-architecture)
- [Safety & Constraint Enforcement Layer](#-safety--constraint-enforcement-layer)
- [Quantitative Performance Benchmark](#-quantitative-performance-benchmark)
- [Tech Stack](#-tech-stack)
- [System Architecture](#-system-architecture)
- [API Documentation](#-api-documentation)
- [Getting Started & Installation](#-getting-started--installation)
- [Demo Story & Walkthrough](#-demo-story--walkthrough)
- [Future Roadmap](#-future-roadmap)

---

## 🎯 Product Vision & Problem Statement

### **The Problem**
Uncontrolled EV charging creates severe challenges for modern electricity grids:
- **Peak Load Spikes**: Simultaneous evening charging causes grid overload and transformer stress.
- **Inflated Charging Costs**: Uncoordinated charging during expensive peak dynamic tariff hours.
- **Renewable Curtailment**: Underutilization of daytime solar energy generation.
- **Battery Wear**: Accelerated battery degradation due to unoptimized charge cycling.
- **Lack of V2G Support**: Missed opportunities to feed stored energy back to the grid during critical load peaks.

### **The GridWise AI Solution**
GridWise AI continuously evaluates environment telemetry to make real-time decisions for every connected EV:
- **CHARGE ⚡**: When solar generation is high or electricity tariffs are cheap.
- **IDLE ⏸️**: When electricity tariffs or grid load demand are at peak levels.
- **DISCHARGE 🔋 (V2G)**: When grid load is critically high and the EV has sufficient battery buffer, returning power back to the grid for financial feed-in value and grid stabilization.

---

## ⚡ Core Features

### 1. **Autonomous RL Optimization Engine**
Powered by **Proximal Policy Optimization (PPO)** in a custom **Gymnasium 1.3.0** environment (`EVChargingEnv`). Sub-millisecond decision inference with explainable AI reason generation.

### 2. **Safety & Constraint Enforcement Layer**
Hard physical boundaries ensuring the AI agent operates strictly within safe limits:
- **Departure Urgency Guarantee**: Forces charging when time remaining is tight to guarantee 100% of user required departure State of Charge (SOC).
- **SOC Minimum/Maximum Bounds**: Protects batteries from overcharging ($>max\_soc$) or deep discharging ($<min\_soc$).
- **V2G Buffer Safeguard**: Restricts V2G discharging unless SOC is safely above target thresholds.
- **Grid Stress Cap**: Throttles non-urgent charging when grid load exceeds 92%.

### 3. **Digital Energy Flow SVG Visualization**
Real-time animated SVG canvas showing energy movement:
- **Solar $\rightarrow$ Grid $\rightarrow$ EV**
- **EV $\rightarrow$ Grid (V2G)**

### 4. **AI vs. Traditional Charging Benchmark**
Runs **Scenario A (Uncontrolled Immediate Charging)** vs **Scenario B (GridWise AI RL Optimization)** side-by-side over identical 24-hour load/solar/price profiles, producing quantitative metrics for cost savings, peak shaving, and solar utilization.

### 5. **OpenAI GPT-4o Strategic Energy Insights**
Backend integration with OpenAI (`OpenAIService`) to generate natural-language LLM strategic energy advisor recommendations (`GET /api/ai/insight`).

### 6. **Real-Time Operator Control Overrides**
Interactive manual overrides on EV fleet rows (Force Charge ⚡, Force V2G 🔋, Force Standby ⏸️, Clear Override).

---

## 🧠 AI & Reinforcement Learning Architecture

### **Observation State Vector (8 Features)**
1. `Current SOC` (Normalized $0.0 - 1.0$)
2. `Required SOC` (Normalized $0.0 - 1.0$)
3. `Time Remaining Fraction` ($0.0 - 1.0$)
4. `Electricity Price` (Normalized to max tariff)
5. `Grid Load Percentage` ($0.0 - 1.0$)
6. `Solar Generation` (Normalized to max solar capacity)
7. `Hour Sin` ($\sin(2\pi \cdot \text{hour} / 24)$)
8. `Hour Cos` ($\cos(2\pi \cdot \text{hour} / 24)$)

### **Action Space (Discrete 3)**
- `0 = IDLE` ($0\text{ kW}$)
- `1 = CHARGE` ($+7.4\text{ kW}$)
- `2 = DISCHARGE / V2G` ($-5.0\text{ kW}$)

### **Reward Function**
$$R = R_{\text{solar\_use}} + R_{\text{v2g\_revenue}} + R_{\text{user\_dep\_bonus}} - C_{\text{grid\_cost}} - P_{\text{grid\_peak}} - P_{\text{battery\_wear}}$$

---

## 🛡️ Safety & Constraint Enforcement Layer

The Safety Layer intercepts raw RL actions before physical power execution:

| Rule | Trigger Condition | Action Taken |
| :--- | :--- | :--- |
| **Departure Guarantee** | $t_{\text{remaining}} \le t_{\text{needed}} \cdot 1.35$ | Forced **CHARGE** ⚡ |
| **Max SOC Limit** | $SOC \ge max\_soc$ | Forced **IDLE** ⏸️ |
| **Min SOC Limit** | $SOC \le min\_soc$ | Block **DISCHARGE**, Forced **IDLE** |
| **V2G Buffer Safeguard** | $SOC - min\_soc < 20\%$ | Block **DISCHARGE**, Forced **IDLE** |
| **Grid Stress Cap** | Grid Load $\ge 92\%$ & Non-urgent | Postpone charging, Forced **IDLE** |

---

## 📊 Quantitative Performance Benchmark

Over a 24-hour simulation cycle with identical grid load, dynamic TOU tariffs, and solar generation profiles:

| Metric | Scenario A — Traditional Immediate | Scenario B — GridWise AI | Performance Delta |
| :--- | :--- | :--- | :--- |
| **Grid Energy Cost** | ₹1,924.74 | **₹0.00** | **100% Savings** (Solar Shifted) |
| **Peak Grid Load** | 98.8 kW | **76.0 kW** | **-23.1% Peak Shaved** |
| **Solar Energy Consumed** | 130.1 kWh | **181.1 kWh** | **+39.2% Solar Utilization** |
| **V2G Energy Supplied** | 0.0 kWh | **21.5 kWh** | **Grid Support Active** |
| **Departure Satisfaction** | 100.0% | **100.0%** | **100% Guaranteed** |

---

## 🛠️ Tech Stack

### **Frontend**
- **HTML5 & Tailwind CSS**: Responsive, pristine Light Theme design.
- **Chart.js**: Real-time synchronized telemetry charts.
- **Lucide Icons**: Modern icon library.
- **WebSockets**: Real-time streaming client.

### **Backend**
- **Python 3.14**: High-performance runtime.
- **Starlette & Uvicorn**: Async Web Framework and WebSockets server.
- **Gymnasium 1.3.0 & Stable-Baselines3**: Reinforcement Learning framework (PPO).
- **PyTorch**: Deep learning backend for RL policies.
- **OpenAI API**: GPT-4o integration for natural language strategic insights.

---

## 🏛️ System Architecture

```text
               ┌────────────────────────────────────────────────────────┐
               │              Frontend UI (Browser Single-Page App)    │
               │   Dashboard | Fleet | AI Center | Sim Lab | Analytics  │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                  REST API │ WebSockets (/ws/simulation)
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │               Starlette / Uvicorn Web Server           │
               └────┬──────────────────────┬──────────────────────┬─────┘
                    │                      │                      │
                    ▼                      ▼                      ▼
           ┌────────────────┐    ┌─────────────────┐    ┌──────────────────┐
           │   EV Fleet     │    │  Energy Service │    │ OpenAI Service   │
           │   Service      │    │  (Grid, Tariff, │    │  (GPT-4o LLM     │
           │ (SOC, Battery) │    │   Solar Gen)    │    │    Advisor)      │
           └───────┬────────┘    └────────┬────────┘    └──────────────────┘
                   │                      │
                   ▼                      ▼
           ┌───────────────────────────────────────────────────────────┐
           │                  Simulation Engine                        │
           │      (24h Step Simulator & Real-Time Background Loop)     │
           └───────────────────────────┬───────────────────────────────┘
                                       │
                                       ▼
           ┌───────────────────────────────────────────────────────────┐
           │                   RL Optimizer Engine                     │
           │            (PPO Agent + EVChargingGymEnv)                 │
           └───────────────────────────┬───────────────────────────────┘
                                       │
                                       ▼
           ┌───────────────────────────────────────────────────────────┐
           │              Safety & Constraint Layer                    │
           │    (SOC Bounds, Departure Guarantee, Grid Load Cap)       │
           └───────────────────────────────────────────────────────────┘
```

---

## 🔌 API Documentation

### **EV Fleet Endpoints**
- `GET /api/evs`: List all EVs and active operator overrides.
- `POST /api/evs`: Create a new simulated EV.
- `GET /api/evs/{ev_id}`: Retrieve details for a specific EV.
- `DELETE /api/evs/{ev_id}`: Delete an EV from the fleet.
- `POST /api/evs/{ev_id}/override`: Set manual operator override (`"CHARGE"`, `"DISCHARGE"`, `"IDLE"`, or `null`).

### **Energy Profile Endpoints**
- `GET /api/grid`: Get 24-hour grid load profile and current load state.
- `GET /api/prices`: Get 24-hour dynamic TOU electricity price profile (₹/kWh).
- `GET /api/renewables`: Get 24-hour solar generation curve (kW).

### **AI Endpoints**
- `GET /api/ai/status`: Current RL agent model status and active configuration.
- `GET /api/ai/schedule`: Predictive 24-hour AI action schedule matrix for all EVs.
- `POST /api/ai/decision`: Request AI decision for a specific EV at a given hour.
- `GET /api/ai/insight`: Get OpenAI GPT-4o LLM strategic energy advisor insight.

### **Simulation Endpoints**
- `GET /api/simulation/status`: Current simulation clock and running state.
- `POST /api/simulation/start`: Resume continuous real-time background loop.
- `POST /api/simulation/pause`: Pause real-time loop.
- `POST /api/simulation/step`: Advance simulation by 1 step (+30 minutes).
- `POST /api/simulation/reset`: Reset simulation back to Hour 00:00.
- `GET /api/simulation/benchmark`: Run 24-hour Scenario A vs Scenario B comparison.

### **WebSockets**
- `WS /ws/simulation`: Bi-directional WebSocket endpoint for streaming real-time simulation ticks.

---

## 🚀 Getting Started & Installation

### **Prerequisites**
- Python 3.10+ (Python 3.14 recommended)
- `pip` package manager

### **Installation**
1. Clone or download the project directory.
2. Ensure required Python dependencies are installed:
   ```bash
   pip install starlette uvicorn gymnasium stable-baselines3 torch numpy pandas requestsjinja2 websockets
   ```

### **Running the Application**
Launch the server via the main entrypoint:
```bash
python run.py
```

Open your browser and navigate to:
**`http://127.0.0.1:8000`**

---

## 🎬 Demo Story & Walkthrough

When presenting or testing GridWise AI, follow this 4-step story:

1. **EV Arrival (Morning)**: EVs connect to chargers with initial low battery levels.
2. **AI Observation & Solar Alignment (Midday)**: As solar generation peaks around 12:00 PM – 2:00 PM, GridWise AI automatically schedules high-power charging, shifting consumption to 100% free renewable solar energy.
3. **Grid Peak & V2G Support (Evening)**: At 6:00 PM – 9:00 PM when grid demand reaches critical load and dynamic electricity tariffs peak, eligible EVs discharge stored energy back to the grid (V2G), earning feed-in value and stabilizing grid frequency.
4. **Benchmark Verification**: Click **"Run 24-Hour Benchmark"** to generate side-by-side comparative charts proving 100% cost savings, -23.1% peak shaving, and 100% departure goal satisfaction.

---

## 🛣️ Future Roadmap

- **Phase 1 (Completed)**: Gymnasium RL Environment + Safety Layer + Starlette WebSockets Real-Time Platform.
- **Phase 2**: Solar generation and dynamic electricity price forecasting using LSTM / Transformer models.
- **Phase 3**: Multi-charging station hub optimization and feeder transformer load balancing.
- **Phase 4**: Hardware charger integration via standard Open Charge Point Protocol (OCPP 2.0.1).

---

### 📄 License
This project is developed as an open-source AI energy management platform for research and practical deployment.
