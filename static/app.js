// GridWise AI - Light Theme Real-Time JavaScript Engine

let ws = null;
let currentSimulationState = {
    hour: 14.0,
    is_running: true,
    speed: 1.0,
    evs: [],
    energy_state: {},
    history: [],
    manual_overrides: {}
};

// Chart.js Instances
let gridLoadChart = null;
let tariffSolarChart = null;
let benchmarkGridChart = null;

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    connectWebSocket();
    fetchInitialData();
    fetchOpenAIInsight();
    setInterval(updateSimLoopIfRunning, 1000);
});

// --- OpenAI Strategic Insight Fetcher ---
async function fetchOpenAIInsight() {
    const elem = document.getElementById("openai-insight-text");
    if (elem) elem.innerText = "Querying OpenAI LLM Energy Advisor...";

    try {
        const res = await fetch('/api/ai/insight');
        const data = await res.json();
        if (elem && data.insight) {
            elem.innerText = data.insight;
        }
    } catch (err) {
        if (elem) elem.innerText = "GridWise AI Advisor: High solar availability detected. Prioritizing EV charging during daytime window to minimize peak grid draw.";
    }
}

// --- Tab Switcher ---
function switchTab(tabId) {
    document.querySelectorAll(".tab-page").forEach(page => page.classList.add("hidden"));
    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.classList.remove("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm");
        tab.classList.add("text-slate-600");
    });

    const selectedPage = document.getElementById(`page-${tabId}`);
    if (selectedPage) selectedPage.classList.remove("hidden");

    const selectedTab = document.getElementById(`tab-${tabId}`);
    if (selectedTab) {
        selectedTab.classList.add("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm");
        selectedTab.classList.remove("text-slate-600");
    }

    if (tabId === 'ai-control') loadAiScheduleMatrix();
    if (tabId === 'fleet') renderFleetTable();
}

// --- WebSocket Connection ---
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/simulation`;

    const startTime = Date.now();
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        const latency = Date.now() - startTime;
        const latElem = document.getElementById("top-latency");
        if (latElem) latElem.innerText = `${latency} ms`;
        console.log("[WS] Connected to GridWise AI real-time socket stream.");
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWebSocketMessage(msg);
        } catch (err) {
            console.error("[WS] Error parsing message:", err);
        }
    };

    ws.onclose = () => {
        setTimeout(connectWebSocket, 2000);
    };
}

function handleWebSocketMessage(msg) {
    if (msg.type === "INIT_STATE") {
        currentSimulationState.hour = msg.current_hour;
        currentSimulationState.is_running = msg.is_running;
        currentSimulationState.evs = msg.evs;
        currentSimulationState.energy_state = msg.energy_state;
        if (msg.manual_overrides) currentSimulationState.manual_overrides = msg.manual_overrides;
        updateUI();
    } else if (msg.type === "SIM_STEP") {
        const stepData = msg.data;
        currentSimulationState.hour = stepData.hour;
        currentSimulationState.energy_state = stepData.energy_state;
        if (stepData.ev_fleet_status) currentSimulationState.evs = stepData.ev_fleet_status;
        currentSimulationState.history.push(stepData);
        updateUI();
        appendLogConsole(`[TICK ${stepData.hour.toFixed(1)}h] Base Grid: ${stepData.energy_state.grid_load_kw} kW | Solar: ${stepData.energy_state.solar_generation_kw} kW | Charge: +${stepData.total_charging_power_kw} kW | V2G: -${stepData.total_v2g_power_kw} kW`);
    } else if (msg.type === "OVERRIDE_CHANGED") {
        if (msg.action) {
            currentSimulationState.manual_overrides[msg.ev_id] = msg.action;
        } else {
            delete currentSimulationState.manual_overrides[msg.ev_id];
        }
        renderFleetTable();
    } else if (msg.type === "SIM_STARTED") {
        currentSimulationState.is_running = true;
        updateHeaderSimButton(true);
    } else if (msg.type === "SIM_PAUSED") {
        currentSimulationState.is_running = false;
        updateHeaderSimButton(false);
    } else if (msg.type === "SIM_RESET") {
        currentSimulationState.hour = 0.0;
        currentSimulationState.history = [];
        updateUI();
    }
}

// --- Fetch Initial REST Data ---
async function fetchInitialData() {
    try {
        const [evsRes, gridRes, pricesRes, renewablesRes] = await Promise.all([
            fetch('/api/evs'),
            fetch('/api/grid'),
            fetch('/api/prices'),
            fetch('/api/renewables')
        ]);
        const evsData = await evsRes.json();
        const gridData = await gridRes.json();
        const pricesData = await pricesRes.json();
        const solarData = await renewablesRes.json();

        currentSimulationState.evs = evsData.evs;
        if (evsData.overrides) currentSimulationState.manual_overrides = evsData.overrides;
        currentSimulationState.energy_state = gridData.current_state;

        updateChartsWithProfiles(gridData.grid_load_profile_kw, pricesData.price_profile, solarData.solar_profile);
        updateUI();
    } catch (err) {
        console.error("Error loading initial data:", err);
    }
}

// --- Main UI Update Engine ---
function updateUI() {
    const state = currentSimulationState;
    const hourStr = `${Math.floor(state.hour).toString().padStart(2, '0')}:${Math.round((state.hour % 1) * 60).toString().padStart(2, '0')} / 24:00`;

    const clock1 = document.getElementById("header-clock");
    if (clock1) clock1.innerText = hourStr;
    const clock2 = document.getElementById("lab-clock");
    if (clock2) clock2.innerText = hourStr;

    // KPI Counters
    const chargingEvs = state.evs.filter(e => e.status === "CHARGING").length;
    const idleEvs = state.evs.filter(e => e.status === "IDLE" || e.status === "WAITING").length;
    const v2gEvs = state.evs.filter(e => e.status === "DISCHARGING").length;

    document.getElementById("kpi-active-evs").innerText = `${state.evs.length} EVs`;
    document.getElementById("kpi-charging-evs").innerText = chargingEvs;
    document.getElementById("kpi-idle-evs").innerText = idleEvs;
    document.getElementById("kpi-v2g-evs").innerText = v2gEvs;

    if (state.energy_state) {
        const es = state.energy_state;
        document.getElementById("kpi-grid-load").innerText = `${es.grid_load_kw || 0} kW`;
        const stressBadge = document.getElementById("kpi-grid-stress");
        stressBadge.innerText = es.grid_stress_level || "LOW";
        if (es.grid_stress_level === "CRITICAL") {
            stressBadge.className = "text-[10px] px-2 py-0.5 rounded bg-rose-100 text-rose-800 border border-rose-300 font-bold animate-pulse";
        } else if (es.grid_stress_level === "HIGH") {
            stressBadge.className = "text-[10px] px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300 font-bold";
        } else {
            stressBadge.className = "text-[10px] px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold";
        }

        document.getElementById("kpi-solar-gen").innerText = `${es.solar_generation_kw || 0} kW`;
        document.getElementById("kpi-tariff").innerText = `₹${es.electricity_price || 0}/kWh`;
    }

    updateAiDecisionHighlightCard();
    renderFleetTable();
    updateEnergyFlowCanvas();
}

function updateAiDecisionHighlightCard() {
    const evs = currentSimulationState.evs;
    if (!evs.length) return;

    const highlightedEv = evs.find(e => e.status === "CHARGING" || e.status === "DISCHARGING") || evs[0];
    document.getElementById("decision-ev-name").innerText = `${highlightedEv.ev_id} (${highlightedEv.name})`;

    const badge = document.getElementById("decision-action-badge");
    const reasonText = document.getElementById("decision-reason-text");

    if (highlightedEv.status === "CHARGING") {
        badge.className = "px-3.5 py-1.5 rounded-xl bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs font-bold flex items-center gap-2 font-mono pulse-charge";
        badge.innerHTML = `⚡ CHARGE (+${highlightedEv.max_charge_power_kw} kW)`;
        reasonText.innerText = "Low electricity tariff + Solar generation available -> Prioritizing charging to reach target SOC";
    } else if (highlightedEv.status === "DISCHARGING") {
        badge.className = "px-3.5 py-1.5 rounded-xl bg-amber-100 text-amber-800 border border-amber-300 text-xs font-bold flex items-center gap-2 font-mono pulse-discharge";
        badge.innerHTML = `🔋 DISCHARGE (-${highlightedEv.max_discharge_power_kw} kW V2G)`;
        reasonText.innerText = "Grid load peak stress detected -> Providing stored energy back to grid (V2G)";
    } else {
        badge.className = "px-3.5 py-1.5 rounded-xl bg-slate-100 text-slate-700 border border-slate-300 text-xs font-bold flex items-center gap-2 font-mono";
        badge.innerHTML = `⏸️ IDLE (0 kW)`;
        reasonText.innerText = "Electricity tariff is expensive or grid demand is peak -> Charging postponed";
    }
}

// --- Render Fleet Table with Operator Overrides ---
function renderFleetTable() {
    const tbody = document.getElementById("ev-fleet-table-body");
    if (!tbody) return;

    const overrides = currentSimulationState.manual_overrides || {};

    tbody.innerHTML = currentSimulationState.evs.map(ev => {
        let statusBadge = `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600">IDLE</span>`;
        if (ev.status === "CHARGING") statusBadge = `<span class="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold">⚡ CHARGING</span>`;
        if (ev.status === "DISCHARGING") statusBadge = `<span class="px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300 font-bold">🔋 V2G</span>`;
        if (ev.status === "COMPLETED") statusBadge = `<span class="px-2 py-0.5 rounded bg-sky-100 text-sky-800 border border-sky-300">✓ DEPARTED</span>`;

        const currentOverride = overrides[ev.ev_id];

        return `
            <tr class="hover:bg-slate-50 transition">
                <td class="p-4">
                    <div class="font-bold text-slate-900">${ev.ev_id}</div>
                    <div class="text-slate-500 text-[11px] font-sans">${ev.name} (${ev.battery_capacity_kwh} kWh)</div>
                </td>
                <td class="p-4">
                    <div class="flex items-center gap-2">
                        <div class="w-20 bg-slate-200 h-2.5 rounded-full overflow-hidden border border-slate-300">
                            <div class="bg-gradient-to-r from-teal-500 to-emerald-500 h-full" style="width: ${ev.current_soc}%"></div>
                        </div>
                        <span class="font-bold text-slate-900">${ev.current_soc}%</span>
                    </div>
                </td>
                <td class="p-4 text-teal-700 font-bold">${ev.required_soc}%</td>
                <td class="p-4 text-slate-700">${ev.arrival_time}:00 - ${ev.departure_time}:00</td>
                <td class="p-4 text-slate-600">+${ev.max_charge_power_kw} kW / -${ev.max_discharge_power_kw} kW</td>
                <td class="p-4">${statusBadge}</td>
                <td class="p-4 text-center">
                    <div class="flex items-center justify-center gap-1.5">
                        <button onclick="setEvOverrideApi('${ev.ev_id}', 'CHARGE')" class="px-2.5 py-1 rounded-lg ${currentOverride === 'CHARGE' ? 'bg-emerald-600 text-white font-bold' : 'bg-slate-100 hover:bg-emerald-50 text-emerald-700 border border-slate-300'}">⚡ Charge</button>
                        <button onclick="setEvOverrideApi('${ev.ev_id}', 'DISCHARGE')" class="px-2.5 py-1 rounded-lg ${currentOverride === 'DISCHARGE' ? 'bg-amber-600 text-white font-bold' : 'bg-slate-100 hover:bg-amber-50 text-amber-700 border border-slate-300'}">🔋 V2G</button>
                        <button onclick="setEvOverrideApi('${ev.ev_id}', 'IDLE')" class="px-2.5 py-1 rounded-lg ${currentOverride === 'IDLE' ? 'bg-slate-700 text-white font-bold' : 'bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300'}">⏸️ Idle</button>
                        ${currentOverride ? `<button onclick="setEvOverrideApi('${ev.ev_id}', null)" class="px-2 py-1 rounded-lg bg-rose-100 text-rose-700 hover:bg-rose-200 text-[10px] font-bold">Clear</button>` : ''}
                    </div>
                </td>
                <td class="p-4 text-right">
                    <button onclick="deleteEvApi('${ev.ev_id}')" class="text-rose-600 hover:text-rose-700 px-2 py-1 rounded hover:bg-rose-50 font-bold">Delete</button>
                </td>
            </tr>
        `;
    }).join("");
}

// --- Set Manual Operator Override ---
async function setEvOverrideApi(evId, action) {
    try {
        await fetch(`/api/evs/${evId}/override`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: action })
        });
        if (action) {
            currentSimulationState.manual_overrides[evId] = action;
        } else {
            delete currentSimulationState.manual_overrides[evId];
        }
        renderFleetTable();
    } catch (err) {
        console.error("Override error:", err);
    }
}

// --- 24-Hour AI Predictive Schedule Matrix ---
async function loadAiScheduleMatrix() {
    try {
        const res = await fetch('/api/ai/schedule');
        const data = await res.json();
        const matrixContainer = document.getElementById("ai-schedule-matrix");
        if (!matrixContainer) return;

        let html = `
            <div class="grid grid-cols-[160px_repeat(24,1fr)] gap-1 text-center font-semibold text-[10px] text-slate-500 border-b border-slate-200 pb-2">
                <div class="text-left font-bold text-slate-800">EV Fleet</div>
                ${Array.from({length: 24}, (_, i) => `<div>${i.toString().padStart(2, '0')}h</div>`).join("")}
            </div>
        `;

        for (const [evId, info] of Object.entries(data.schedule)) {
            html += `
                <div class="grid grid-cols-[160px_repeat(24,1fr)] gap-1 items-center py-1.5 border-b border-slate-200">
                    <div class="text-left font-bold text-slate-900 text-xs truncate">${evId} (${info.ev_name})</div>
                    ${info.timeline.map(item => {
                        let colorClass = "bg-slate-100 border-slate-200 text-slate-400";
                        let symbol = "•";
                        if (item.action.includes("CHARGE")) {
                            colorClass = "bg-emerald-100 border-emerald-300 text-emerald-800 font-bold";
                            symbol = "⚡";
                        } else if (item.action.includes("DISCHARGE")) {
                            colorClass = "bg-amber-100 border-amber-300 text-amber-800 font-bold";
                            symbol = "🔋";
                        }
                        return `<div class="p-1 rounded border text-[10px] ${colorClass}" title="Hour ${item.hour}: ${item.action}">${symbol}</div>`;
                    }).join("")}
                </div>
            `;
        }

        matrixContainer.innerHTML = html;
    } catch (err) {
        console.error("Error loading AI schedule:", err);
    }
}

// --- Digital Energy Flow SVG Canvas Animation ---
function updateEnergyFlowCanvas() {
    const text = document.getElementById("flow-status-text");
    const evs = currentSimulationState.evs || [];

    const isCharging = evs.some(e => e.status === "CHARGING");
    const isV2G = evs.some(e => e.status === "DISCHARGING");

    const gridEvParticle = document.getElementById("path-grid-ev");

    if (isV2G) {
        if (text) text.innerText = "FLOW: EV (V2G) ➔ Grid Power Feed";
        if (text) text.className = "text-xs text-amber-700 font-mono font-bold";
        if (gridEvParticle) gridEvParticle.setAttribute("stroke", "#d97706");
    } else if (isCharging) {
        if (text) text.innerText = "FLOW: Solar + Grid ➔ EV Charging";
        if (text) text.className = "text-xs text-emerald-700 font-mono font-bold";
        if (gridEvParticle) gridEvParticle.setAttribute("stroke", "#059669");
    } else {
        if (text) text.innerText = "FLOW: Grid Standard Operations";
        if (text) text.className = "text-xs text-sky-700 font-mono";
        if (gridEvParticle) gridEvParticle.setAttribute("stroke", "#0284c7");
    }
}

// --- Simulation Controls ---
async function toggleSimulationRun() {
    const isRunning = currentSimulationState.is_running;
    if (isRunning) {
        await fetch('/api/simulation/pause', { method: 'POST' });
    } else {
        await fetch('/api/simulation/start', { method: 'POST' });
    }
}

function updateHeaderSimButton(isRunning) {
    const textSpan = document.getElementById("header-sim-btn-text");
    const btn = document.getElementById("header-sim-btn");
    if (!textSpan || !btn) return;

    if (isRunning) {
        textSpan.innerText = "Pause Live";
        btn.className = "px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs uppercase tracking-wider rounded-xl transition flex items-center gap-2 shadow-md shadow-amber-600/20";
    } else {
        textSpan.innerText = "Resume Live";
        btn.className = "px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs uppercase tracking-wider rounded-xl transition flex items-center gap-2 shadow-md shadow-emerald-600/20";
    }
}

async function updateSimLoopIfRunning() {
    // Continuous background server streaming
}

async function simStepApi() {
    try {
        const res = await fetch('/api/simulation/step', { method: 'POST' });
        await res.json();
    } catch (err) {
        console.error("Step error:", err);
    }
}

async function simResetApi() {
    await fetch('/api/simulation/reset', { method: 'POST' });
    appendLogConsole("[SYSTEM] Simulation state reset to Hour 00:00.");
}

function appendLogConsole(text) {
    const consoleElem = document.getElementById("sim-log-console");
    if (!consoleElem) return;
    const div = document.createElement("div");
    div.innerText = text;
    consoleElem.appendChild(div);
    consoleElem.scrollTop = consoleElem.scrollHeight;
}

// --- Benchmark Runner API ---
async function runBenchmarkApi() {
    const btn = document.getElementById("btn-run-benchmark");
    if (btn) btn.innerHTML = `<i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i> Simulating 24h Benchmark...`;

    try {
        const res = await fetch('/api/simulation/benchmark');
        const data = await res.json();
        const comp = data.summary_comparison;

        document.getElementById("bm-cost-trad").innerText = `₹${comp.energy_cost_traditional_inr.toFixed(2)}`;
        document.getElementById("bm-cost-ai").innerText = `₹${comp.energy_cost_ai_inr.toFixed(2)} (Solar Shifted)`;
        document.getElementById("bm-cost-savings").innerText = `${comp.cost_savings_pct}% Savings`;

        document.getElementById("bm-peak-trad").innerText = `${comp.peak_load_traditional_kw} kW`;
        document.getElementById("bm-peak-ai").innerText = `${comp.peak_load_ai_kw} kW`;
        document.getElementById("bm-peak-red").innerText = `-${comp.peak_load_reduction_pct}% Peak Shaved`;

        document.getElementById("bm-solar-trad").innerText = `${comp.solar_used_traditional_kwh} kWh`;
        document.getElementById("bm-solar-ai").innerText = `${comp.solar_used_ai_kwh} kWh`;
        document.getElementById("bm-solar-gain").innerText = `+${((comp.solar_used_ai_kwh - comp.solar_used_traditional_kwh) / max1(comp.solar_used_traditional_kwh) * 100).toFixed(1)}% Utilization`;

        document.getElementById("bm-v2g-trad").innerText = `${comp.v2g_energy_traditional_kwh} kWh`;
        document.getElementById("bm-v2g-ai").innerText = `${comp.v2g_energy_ai_kwh} kWh`;

        document.getElementById("bm-sat-trad").innerText = `${comp.ev_satisfaction_traditional_pct}%`;
        document.getElementById("bm-sat-ai").innerText = `${comp.ev_satisfaction_ai_pct}%`;

        renderBenchmarkChart(data.hourly_history_traditional, data.hourly_history_ai);
    } catch (err) {
        console.error("Benchmark error:", err);
    } finally {
        if (btn) {
            btn.innerHTML = `<i data-lucide="play-circle" class="w-5 h-5"></i> Run 24-Hour Benchmark`;
            lucide.createIcons();
        }
    }
}

function max1(val) { return Math.max(1, val); }

// --- EV Modal & API ---
function openAddEvModal() {
    document.getElementById("add-ev-modal").classList.remove("hidden");
}
function closeAddEvModal() {
    document.getElementById("add-ev-modal").classList.add("hidden");
}

async function submitAddEvForm(event) {
    event.preventDefault();
    const evData = {
        name: document.getElementById("input-ev-name").value,
        battery_capacity_kwh: parseFloat(document.getElementById("input-ev-capacity").value),
        current_soc: parseFloat(document.getElementById("input-ev-soc").value),
        required_soc: parseFloat(document.getElementById("input-ev-req-soc").value),
        minimum_soc: parseFloat(document.getElementById("input-ev-min-soc").value),
        arrival_time: parseFloat(document.getElementById("input-ev-arrival").value),
        departure_time: parseFloat(document.getElementById("input-ev-departure").value)
    };

    try {
        await fetch('/api/evs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(evData)
        });
        closeAddEvModal();
        await fetchInitialData();
    } catch (err) {
        console.error("Add EV error:", err);
    }
}

async function deleteEvApi(evId) {
    if (!confirm(`Delete ${evId}?`)) return;
    try {
        await fetch(`/api/evs/${evId}`, { method: 'DELETE' });
        await fetchInitialData();
    } catch (err) {
        console.error("Delete EV error:", err);
    }
}

// --- Chart.js Initializer for Light Theme ---
function initCharts() {
    const ctx1 = document.getElementById("chart-grid-load")?.getContext("2d");
    if (ctx1) {
        gridLoadChart = new Chart(ctx1, {
            type: 'line',
            data: {
                labels: Array.from({length: 24}, (_, i) => `${i}:00`),
                datasets: [
                    { label: 'Base Grid Load (kW)', data: [], borderColor: '#0284c7', backgroundColor: 'rgba(2, 132, 199, 0.08)', fill: true, tension: 0.4 },
                    { label: 'GridWise AI Total Net Load (kW)', data: [], borderColor: '#059669', borderWidth: 2.5, tension: 0.4 }
                ]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#334155', font: { family: 'monospace' } } } }, scales: { x: { grid: { color: '#e2e8f0' }, ticks: { color: '#64748b', font: { family: 'monospace' } } }, y: { grid: { color: '#e2e8f0' }, ticks: { color: '#64748b', font: { family: 'monospace' } } } } }
        });
    }

    const ctx2 = document.getElementById("chart-tariff-solar")?.getContext("2d");
    if (ctx2) {
        tariffSolarChart = new Chart(ctx2, {
            type: 'bar',
            data: {
                labels: Array.from({length: 24}, (_, i) => `${i}:00`),
                datasets: [
                    { label: 'Tariff Rate (₹/kWh)', data: [], backgroundColor: 'rgba(217, 119, 6, 0.7)', yAxisID: 'y' },
                    { label: 'Solar Power (kW)', data: [], type: 'line', borderColor: '#d97706', borderWidth: 2.5, yAxisID: 'y1', tension: 0.4 }
                ]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#334155', font: { family: 'monospace' } } } }, scales: { y: { position: 'left', grid: { color: '#e2e8f0' }, ticks: { color: '#64748b', font: { family: 'monospace' } } }, y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#64748b', font: { family: 'monospace' } } } } }
        });
    }
}

function updateChartsWithProfiles(gridLoad, prices, solar) {
    if (gridLoadChart) {
        gridLoadChart.data.datasets[0].data = gridLoad;
        gridLoadChart.data.datasets[1].data = gridLoad;
        gridLoadChart.update();
    }
    if (tariffSolarChart) {
        tariffSolarChart.data.datasets[0].data = prices;
        tariffSolarChart.data.datasets[1].data = solar;
        tariffSolarChart.update();
    }
}

function renderBenchmarkChart(tradHistory, aiHistory) {
    const ctx = document.getElementById("chart-benchmark-grid")?.getContext("2d");
    if (!ctx) return;

    const labels = tradHistory.map(h => `${h.hour}h`);
    const tradLoads = tradHistory.map(h => {
        const chargingPwr = h.ev_decisions.reduce((acc, d) => acc + (d.power_kw > 0 ? d.power_kw : 0), 0);
        return h.energy_state.grid_load_kw + chargingPwr;
    });

    const aiLoads = aiHistory.map(h => {
        const chargingPwr = h.ev_decisions.reduce((acc, d) => acc + (d.power_kw > 0 ? d.power_kw : 0), 0);
        const v2gPwr = h.ev_decisions.reduce((acc, d) => acc + (d.power_kw < 0 ? Math.abs(d.power_kw) : 0), 0);
        return h.energy_state.grid_load_kw + chargingPwr - v2gPwr;
    });

    if (benchmarkGridChart) benchmarkGridChart.destroy();

    benchmarkGridChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: 'Traditional Immediate Charging Grid Load (kW)', data: tradLoads, borderColor: '#d97706', borderWidth: 2, tension: 0.3 },
                { label: 'GridWise AI Optimized Net Grid Load (kW)', data: aiLoads, borderColor: '#059669', borderWidth: 3, tension: 0.3 }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#334155', font: { family: 'monospace' } } } }, scales: { x: { grid: { color: '#e2e8f0' }, ticks: { color: '#64748b', font: { family: 'monospace' } } }, y: { grid: { color: '#e2e8f0' }, ticks: { color: '#64748b', font: { family: 'monospace' } } } } }
    });
}
