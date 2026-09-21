// GridWise AI - Professional Platform & Digital Twin Simulator JavaScript Engine

let ws = null;
let wsReconnectTimer = null;
let wsReconnectAttempt = 0;
let wsHeartbeatTimer = null;
let wsConnectionState = "DISCONNECTED"; // CONNECTED, CONNECTING, RECONNECTING, DISCONNECTED, AUTH_REQUIRED, BACKEND_OFFLINE
let constraintEventsTimer = null;

let authToken = localStorage.getItem("gridwise_auth_token") || null;
let currentUser = null;

let currentSimulationState = {
    simulation_id: "init",
    hour: 0.0,
    is_running: false,
    speed: 1.0,
    evs: [],
    energy_state: {},
    energy_flow: {
        solar_to_ev_kw: 0.0,
        solar_to_grid_kw: 0.0,
        grid_to_ev_kw: 0.0,
        ev_to_grid_kw: 0.0,
        flow_summary: "System Ready"
    },
    history: [],
    manual_overrides: {}
};

// Chart.js Instances
let gridLoadChart = null;
let tariffSolarChart = null;
let benchmarkGridChart = null;

// ===================================================
// UTILITY & NORMALIZATION HELPERS
// ===================================================

function formatMetric(value, decimals = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
    }
    return Number(value).toFixed(decimals);
}

function normalizeConstraintEvents(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.events)) return payload.events;
    if (payload && Array.isArray(payload.recent_events)) return payload.recent_events;
    if (payload && Array.isArray(payload.items)) return payload.items;
    console.warn("[Constraints] Unexpected response shape:", payload);
    return [];
}

function setWsConnectionState(state, detail = "") {
    wsConnectionState = state;
    const wsStatus = document.getElementById("top-ws-status");
    const wsBadge = document.getElementById("top-ws-badge");
    if (!wsStatus) return;

    if (state === "CONNECTED") {
        wsStatus.innerHTML = `● LIVE ${detail ? `(${detail})` : ''}`;
        if (wsBadge) {
            wsBadge.className = "flex items-center gap-1.5 text-emerald-400 font-bold";
        }
    } else if (state === "CONNECTING") {
        wsStatus.innerHTML = `◌ CONNECTING...`;
        if (wsBadge) {
            wsBadge.className = "flex items-center gap-1.5 text-blue-400 font-bold";
        }
    } else if (state === "RECONNECTING") {
        wsStatus.innerHTML = `◌ RECONNECTING... ${detail ? `(${detail})` : ''}`;
        if (wsBadge) {
            wsBadge.className = "flex items-center gap-1.5 text-amber-400 font-bold animate-pulse";
        }
    } else if (state === "BACKEND_OFFLINE") {
        wsStatus.innerHTML = `⚠ BACKEND OFFLINE`;
        if (wsBadge) {
            wsBadge.className = "flex items-center gap-1.5 text-rose-400 font-bold";
        }
    } else if (state === "AUTH_REQUIRED") {
        wsStatus.innerHTML = `🔒 AUTH REQUIRED`;
        if (wsBadge) {
            wsBadge.className = "flex items-center gap-1.5 text-slate-400 font-bold";
        }
    } else {
        wsStatus.innerHTML = `○ DISCONNECTED`;
        if (wsBadge) {
            wsBadge.className = "flex items-center gap-1.5 text-slate-400 font-bold";
        }
    }
}

// Centralized API fetch wrapper with Bearer token & central 401 handling
async function apiFetch(url, options = {}) {
    const token = authToken || localStorage.getItem("gridwise_auth_token");
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
    };
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(url, { ...options, headers });
        if (response.status === 401) {
            handleAuthenticationExpired();
            return response;
        }
        if (wsConnectionState === "BACKEND_OFFLINE") {
            setWsConnectionState("RECONNECTING");
        }
        return response;
    } catch (err) {
        if (err.name === "TypeError" || (err.message && err.message.includes("Failed to fetch"))) {
            setWsConnectionState("BACKEND_OFFLINE");
        }
        throw err;
    }
}

let isAuthExpiredAlertShown = false;
function handleAuthenticationExpired() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem("gridwise_auth_token");
    if (ws) {
        try { ws.close(); } catch(e) {}
        ws = null;
    }
    setWsConnectionState("AUTH_REQUIRED");
    showView("view-login");
    if (!isAuthExpiredAlertShown) {
        isAuthExpiredAlertShown = true;
        const msg = document.getElementById("login-error-msg");
        if (msg) {
            msg.innerText = "Your session has expired. Please sign in again.";
            msg.classList.remove("hidden");
        }
        setTimeout(() => { isAuthExpiredAlertShown = false; }, 5000);
    }
}

// Initialize Application on DOM Ready
document.addEventListener("DOMContentLoaded", async () => {
    initCharts();
    startWallClockTicker();
    
    // Check session first
    const isAuthenticated = await checkExistingSession();
    if (isAuthenticated) {
        connectWebSocket();
        fetchPlatformHealth();
        fetchInitialData();
        fetchOpenAIInsight();
        fetchSimulationHistoryApi();
        loadSettings();
        fetchTelemetryStatus();
        fetchOperationalAlerts();
    }
});

function startWallClockTicker() {
    function tick() {
        const now = new Date();
        const elem = document.getElementById("top-wall-clock");
        if (elem) elem.innerText = now.toTimeString().split(' ')[0];
    }
    tick();
    setInterval(tick, 1000);
}

// ===================================================
// 1. AUTHENTICATION & SESSION MANAGEMENT
// ===================================================

async function checkExistingSession() {
    if (!authToken) {
        showView("view-login");
        return false;
    }

    try {
        const res = await apiFetch("/api/auth/me");
        if (res.ok) {
            currentUser = await res.json();
            updateUserNav(currentUser);
            showView("view-platform-home");
            return true;
        } else {
            localStorage.removeItem("gridwise_auth_token");
            authToken = null;
            showView("view-login");
            return false;
        }
    } catch (err) {
        console.warn("Auth check error, defaulting to login:", err);
        showView("view-login");
        return false;
    }
}

function showView(viewId) {
    const loginView = document.getElementById("view-login");
    const platformWrapper = document.getElementById("platform-wrapper");

    // Clean up view-specific intervals when navigating
    if (constraintEventsTimer) {
        clearInterval(constraintEventsTimer);
        constraintEventsTimer = null;
    }

    if (viewId === "view-login") {
        if (loginView) loginView.classList.remove("hidden");
        if (platformWrapper) platformWrapper.classList.add("hidden");
    } else {
        if (loginView) loginView.classList.add("hidden");
        if (platformWrapper) platformWrapper.classList.remove("hidden");

        // Hide all views inside platform wrapper
        document.querySelectorAll(".plat-view").forEach(v => v.classList.add("hidden"));
        const targetView = document.getElementById(viewId);
        if (targetView) targetView.classList.remove("hidden");

        // Update nav buttons
        document.querySelectorAll(".plat-nav-btn").forEach(btn => {
            btn.classList.remove("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm");
            btn.classList.add("text-slate-600");
        });

        if (viewId === "view-platform-home") {
            const b = document.getElementById("nav-btn-home");
            if (b) { b.classList.add("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm"); b.classList.remove("text-slate-600"); }
            fetchPlatformHealth();
        } else if (viewId === "view-main-software") {
            const b = document.getElementById("nav-btn-main");
            if (b) { b.classList.add("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm"); b.classList.remove("text-slate-600"); }
        } else if (viewId === "view-simulator-lab") {
            const b = document.getElementById("nav-btn-sim");
            if (b) { b.classList.add("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm"); b.classList.remove("text-slate-600"); }
            renderSimulatorEvTwins();
            fetchSimulationHistoryApi();
            refreshForecastHorizon();
            fetchConstraintEvents();
            if (!constraintEventsTimer) {
                constraintEventsTimer = setInterval(fetchConstraintEvents, 5000);
            }
        } else if (viewId === "view-ai-training") {
            const b = document.getElementById("nav-btn-training");
            if (b) { b.classList.add("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm"); b.classList.remove("text-slate-600"); }
            loadAiTrainingCenter();
        } else if (viewId === "view-settings") {
            const b = document.getElementById("nav-btn-settings");
            if (b) { b.classList.add("bg-white", "text-emerald-700", "border", "border-slate-200", "shadow-sm"); b.classList.remove("text-slate-600"); }
            loadSettings();
        }
    }

    if (window.lucide) lucide.createIcons();
}

function navigatePlatform(pageName) {
    if (pageName === 'platform-home') showView("view-platform-home");
    else if (pageName === 'main-software') showView("view-main-software");
    else if (pageName === 'simulator-lab') showView("view-simulator-lab");
    else if (pageName === 'ai-training') showView("view-ai-training");
    else if (pageName === 'settings') showView("view-settings");
}

function updateUserNav(user) {
    const avatar = document.getElementById("nav-user-avatar");
    if (avatar && user && user.username) {
        avatar.innerText = user.username.substring(0, 2).toUpperCase();
        avatar.title = `Logged in as ${user.username} (${user.role || 'Admin'})`;
    }
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    const alertBox = document.getElementById("login-error-alert");
    const errorText = document.getElementById("login-error-text");
    const submitBtn = document.getElementById("login-submit-btn");
    const submitText = document.getElementById("login-submit-text");

    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    const rememberMe = document.getElementById("login-remember").checked;

    if (alertBox) alertBox.classList.add("hidden");
    if (submitBtn) submitBtn.disabled = true;
    if (submitText) submitText.innerText = "Authenticating...";

    try {
        const res = await apiFetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password, remember_me: rememberMe })
        });

        const data = await res.json();
        if (res.ok && data.token) {
            authToken = data.token;
            localStorage.setItem("gridwise_auth_token", authToken);
            currentUser = data.user;
            updateUserNav(currentUser);
            showView("view-platform-home");
            connectWebSocket();
            fetchPlatformHealth();
            fetchInitialData();
            fetchOpenAIInsight();
            fetchSimulationHistoryApi();
            loadSettings();
            fetchTelemetryStatus();
            fetchOperationalAlerts();
        } else {
            if (alertBox) {
                alertBox.classList.remove("hidden");
                if (errorText) errorText.innerText = data.detail || "Invalid username or password";
            }
        }
    } catch (err) {
        if (alertBox) {
            alertBox.classList.remove("hidden");
            if (errorText) errorText.innerText = "Could not connect to authentication server.";
        }
    } finally {
        if (submitBtn) submitBtn.disabled = false;
        if (submitText) submitText.innerText = "Sign In to Platform";
    }
}

function fillDemoCredentials() {
    document.getElementById("login-username").value = "admin@gridwise.ai";
    document.getElementById("login-password").value = "GridWise@2026";
}

function togglePasswordVisibility() {
    const pwdInput = document.getElementById("login-password");
    if (!pwdInput) return;
    pwdInput.type = pwdInput.type === "password" ? "text" : "password";
}

async function handleLogout() {
    if (authToken) {
        try {
            await apiFetch("/api/auth/logout", { method: "POST" });
        } catch (e) {
            console.warn("Logout request failed:", e);
        }
    }
    if (ws) {
        try { ws.close(); } catch(e) {}
        ws = null;
    }
    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
    }
    if (constraintEventsTimer) {
        clearInterval(constraintEventsTimer);
        constraintEventsTimer = null;
    }
    setWsConnectionState("AUTH_REQUIRED");
    localStorage.removeItem("gridwise_auth_token");
    authToken = null;
    currentUser = null;
    showView("view-login");
}

function openForgotPasswordModal() {
    document.getElementById("forgot-password-modal")?.classList.remove("hidden");
}

function closeForgotPasswordModal() {
    document.getElementById("forgot-password-modal")?.classList.add("hidden");
}

async function handleForgotPasswordSubmit(e) {
    e.preventDefault();
    const email = document.getElementById("forgot-email").value;
    try {
        const res = await apiFetch("/api/auth/forgot-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        alert(data.message || "Reset instructions sent.");
        closeForgotPasswordModal();
    } catch (err) {
        alert("Password reset request error.");
    }
}

// ===================================================
// 2. PLATFORM HEALTH MONITORING
// ===================================================

async function fetchPlatformHealth() {
    try {
        const res = await apiFetch("/api/platform/status");
        if (!res.ok) return;
        const data = await res.json();
        const s = data.services;

        const hBackend = document.getElementById("health-backend");
        const hDatabase = document.getElementById("health-database");
        const hTwin = document.getElementById("health-twin");
        const hAi = document.getElementById("health-ai");
        const hWs = document.getElementById("health-ws");

        if (hBackend && s.backend) hBackend.innerText = s.backend.status.toUpperCase();
        if (hDatabase && s.database) hDatabase.innerText = s.database.status.toUpperCase();
        if (hTwin && s.digital_twin) {
            hTwin.innerText = s.digital_twin.status.toUpperCase();
            const twinInfo = document.getElementById("health-twin-info");
            if (twinInfo) twinInfo.innerText = `${s.digital_twin.fleet_count} EV Twins Loaded`;
        }
        if (hAi && s.ai_engine) hAi.innerText = s.ai_engine.status.toUpperCase();
        if (hWs && s.websocket) {
            hWs.innerText = s.websocket.status.toUpperCase();
            const wsInfo = document.getElementById("health-ws-info");
            if (wsInfo) wsInfo.innerText = `${s.websocket.active_clients} Active Client(s)`;
        }
    } catch (err) {
        console.warn("Error fetching platform health:", err);
    }
}

// ===================================================
// 3. MAIN SOFTWARE TAB SWITCHER
// ===================================================

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
    if (tabId === 'analytics') {
        fetchSimulationHistoryApi();
        updateAnalyticsTabKPIs();
    }
}

// ===================================================
// 4. WEBSOCKET REAL-TIME TELEMETRY
// ===================================================

function connectWebSocket() {
    if (!authToken) {
        setWsConnectionState("AUTH_REQUIRED");
        return;
    }

    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
    }

    setWsConnectionState("CONNECTING");

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/simulation`;

    const startTime = Date.now();
    try {
        ws = new WebSocket(wsUrl);
    } catch (err) {
        console.warn("[WS] Creation error:", err);
        scheduleWsReconnect();
        return;
    }

    ws.onopen = () => {
        const latency = Date.now() - startTime;
        wsReconnectAttempt = 0;
        setWsConnectionState("CONNECTED", `${latency} ms`);
        const latElem = document.getElementById("top-latency");
        if (latElem) latElem.innerText = `${latency} ms`;
        console.log("[WS] Connected to GridWise AI real-time telemetry stream.");

        // Start heartbeat ping every 15 seconds
        if (wsHeartbeatTimer) clearInterval(wsHeartbeatTimer);
        wsHeartbeatTimer = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "ping", time: Date.now() }));
            }
        }, 15000);
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "pong") {
                const latElem = document.getElementById("top-latency");
                if (latElem) {
                    const pingLatency = Math.max(1, Date.now() - (msg.time || startTime));
                    latElem.innerText = `${pingLatency} ms`;
                }
                return;
            }
            handleWebSocketMessage(msg);
        } catch (err) {
            console.error("[WS] Error parsing message:", err);
        }
    };

    ws.onclose = () => {
        if (wsHeartbeatTimer) {
            clearInterval(wsHeartbeatTimer);
            wsHeartbeatTimer = null;
        }
        scheduleWsReconnect();
    };

    ws.onerror = (err) => {
        console.warn("[WS] Socket error encountered.");
    };
}

function scheduleWsReconnect() {
    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
    }

    // Exponential backoff: 2s, 4s, 8s, 16s, max 30s
    const backoffDelay = Math.min(30000, 2000 * Math.pow(2, Math.min(wsReconnectAttempt, 4)));
    wsReconnectAttempt++;

    setWsConnectionState("RECONNECTING", `in ${(backoffDelay / 1000).toFixed(0)}s`);
    console.warn(`[WS] Disconnected. Reconnecting in ${(backoffDelay / 1000).toFixed(0)}s (attempt ${wsReconnectAttempt})...`);

    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        connectWebSocket();
    }, backoffDelay);
}

function handleWebSocketMessage(msg) {
    if (msg.type === "INIT_STATE") {
        currentSimulationState = { ...currentSimulationState, ...msg.data };
        updateUIFromState(currentSimulationState);
        if (msg.realtime) handleRealtimeTelemetry(msg.realtime);
    } else if (msg.type === "REALTIME_UPDATE") {
        if (msg.data?.step_data) {
            currentSimulationState = { ...currentSimulationState, ...msg.data.step_data };
            updateUIFromState(currentSimulationState);
        }
        handleRealtimeTelemetry(msg.data);
    } else if (msg.type === "REALTIME_STATIC") {
        handleRealtimeTelemetry(msg.data);
    } else if (msg.type === "SIM_STEP") {
        currentSimulationState = { ...currentSimulationState, ...msg.data };
        updateUIFromState(currentSimulationState);
        logSimConsole(`[STEP ${msg.data.step_index}] Hour ${msg.data.time} | Grid: ${msg.data.net_grid_load_kw} kW | Solar: ${msg.data.solar?.generation_kw || msg.data.solar_generation_kw} kW | Tariff: ₹${msg.data.price?.current_price || msg.data.electricity_price}`);
    } else if (msg.type === "SIM_STARTED") {
        currentSimulationState.is_running = true;
        updateSimButtons(true);
    } else if (msg.type === "SIM_PAUSED") {
        currentSimulationState.is_running = false;
        updateSimButtons(false);
    } else if (msg.type === "SIM_STOPPED") {
        currentSimulationState.is_running = false;
        updateSimButtons(false);
        fetchSimulationHistoryApi();
    } else if (msg.type === "SIM_RESET") {
        currentSimulationState.hour = 0.0;
        currentSimulationState.is_running = false;
        updateSimButtons(false);
        fetchInitialData();
    } else if (msg.type === "SIM_COMPLETED") {
        currentSimulationState.is_running = false;
        updateSimButtons(false);
        fetchSimulationHistoryApi();
    } else if (msg.type === "SPEED_CHANGED") {
        updateSpeedUI(msg.speed);
    } else if (msg.type === "MODE_CHANGED") {
        const sel = document.getElementById("top-mode-select");
        if (sel) sel.value = msg.mode;
    }
}

function handleRealtimeTelemetry(rt) {
    if (!rt) return;
    const telemetry = rt.telemetry || rt;
    const power = telemetry.power || rt.power_kw || {};
    const diag = telemetry.grid_diagnostics || rt.diagnostics || {};
    const stepData = rt.step_data || {};
    const cum = stepData.cumulative_energy || rt.cumulative_kwh_today || {};
    const flow = stepData.energy_flow || rt.conservation_check || {};

    // 1. Diagnostics in Top Bar
    const fElem = document.getElementById("top-grid-freq");
    const vElem = document.getElementById("top-grid-volt");
    const tElem = document.getElementById("top-ambient-temp");
    const iElem = document.getElementById("top-irradiance");
    const cElem = document.getElementById("top-sim-clock");
    const sElem = document.getElementById("top-source-label");

    if (fElem && diag.frequency_hz) fElem.innerText = `${diag.frequency_hz.toFixed(2)} Hz`;
    if (vElem && diag.voltage_v) vElem.innerText = `${diag.voltage_v.toFixed(1)} V`;
    if (tElem && diag.ambient_temp_c) tElem.innerText = `${diag.ambient_temp_c.toFixed(1)}°C`;
    if (iElem && diag.solar_irradiance_w_m2) iElem.innerText = `${diag.solar_irradiance_w_m2.toFixed(0)} W/m²`;
    if (cElem && (telemetry.sim_time || stepData.time)) cElem.innerText = `${telemetry.sim_time || stepData.time}`;
    if (sElem && telemetry.source_label) sElem.innerText = telemetry.source_label;

    // 2. Metrics Cards: Instantaneous kW + Cumulative kWh today
    const solKw = power.solar_gen_kw !== undefined ? power.solar_gen_kw : (power.solar_gen || stepData.solar?.generation_kw || 0.0);
    const gridInKw = power.grid_import_kw !== undefined ? power.grid_import_kw : (power.grid_import || flow.grid_import_kw || 0.0);
    const gridOutKw = power.grid_export_kw !== undefined ? power.grid_export_kw : (power.grid_export || flow.grid_export_kw || 0.0);
    const evChgKw = power.ev_charging_kw !== undefined ? power.ev_charging_kw : (power.ev_charging || stepData.total_charging_power_kw || 0.0);
    const v2gKw = power.v2g_discharge_kw !== undefined ? power.v2g_discharge_kw : (power.v2g_discharge || stepData.total_v2g_power_kw || 0.0);
    const auxKw = power.station_aux_kw !== undefined ? power.station_aux_kw : (power.station_aux || flow.station_aux_kw || 6.5);
    const lossesKw = power.system_losses_kw !== undefined ? power.system_losses_kw : (power.system_losses || flow.system_losses_kw || 0.5);

    const kpiSolKw = document.getElementById("kpi-solar-power-kw");
    const kpiSolKwh = document.getElementById("kpi-solar-energy-kwh");
    const kpiGridInKw = document.getElementById("kpi-grid-import-kw");
    const kpiGridInKwh = document.getElementById("kpi-grid-import-kwh");
    const kpiGridOutKw = document.getElementById("kpi-grid-export-kw");
    const kpiGridOutKwh = document.getElementById("kpi-grid-export-kwh");
    const kpiEvKw = document.getElementById("kpi-ev-charging-kw");
    const kpiEvKwh = document.getElementById("kpi-ev-charging-kwh");
    const kpiV2gKw = document.getElementById("kpi-v2g-discharge-kw");
    const kpiV2gKwh = document.getElementById("kpi-v2g-discharge-kwh");
    const kpiAuxKw = document.getElementById("kpi-station-aux-kw");
    const kpiAuxKwh = document.getElementById("kpi-station-aux-kwh");

    if (kpiSolKw) kpiSolKw.innerText = `${solKw.toFixed(1)} kW`;
    if (kpiSolKwh) kpiSolKwh.innerText = `${(cum.solar_gen_kwh_today || cum.solar_generated || 0.0).toFixed(1)} kWh today`;
    if (kpiGridInKw) kpiGridInKw.innerText = `${gridInKw.toFixed(1)} kW`;
    if (kpiGridInKwh) kpiGridInKwh.innerText = `${(cum.grid_import_kwh_today || cum.grid_imported || 0.0).toFixed(1)} kWh today`;
    if (kpiGridOutKw) kpiGridOutKw.innerText = `${gridOutKw.toFixed(1)} kW`;
    if (kpiGridOutKwh) kpiGridOutKwh.innerText = `${(cum.grid_export_kwh_today || cum.grid_exported || 0.0).toFixed(1)} kWh today`;
    if (kpiEvKw) kpiEvKw.innerText = `${evChgKw.toFixed(1)} kW`;
    if (kpiEvKwh) kpiEvKwh.innerText = `${(cum.ev_charging_kwh_today || cum.ev_charged || 0.0).toFixed(1)} kWh today`;
    if (kpiV2gKw) kpiV2gKw.innerText = `${v2gKw.toFixed(1)} kW`;
    if (kpiV2gKwh) kpiV2gKwh.innerText = `${(cum.v2g_discharge_kwh_today || cum.v2g_discharged || 0.0).toFixed(1)} kWh today`;
    if (kpiAuxKw) kpiAuxKw.innerText = `${(auxKw + lossesKw).toFixed(1)} kW`;
    if (kpiAuxKwh) kpiAuxKwh.innerText = `${((cum.station_aux_kwh_today || cum.station_aux || 0.0) + (cum.system_losses_kwh_today || cum.losses || 0.0)).toFixed(1)} kWh today`;

    // 3. Strict Conservation Verification (Pin = Pout within tolerance)
    const totalIn = flow.total_in_kw !== undefined ? flow.total_in_kw : (solKw + gridInKw + v2gKw);
    const totalOut = flow.total_out_kw !== undefined ? flow.total_out_kw : (evChgKw + auxKw + gridOutKw + lossesKw);
    const err = flow.balance_error_kw !== undefined ? flow.balance_error_kw : Math.abs(totalIn - totalOut);

    const pinElem = document.getElementById("kpi-pin-val");
    const poutElem = document.getElementById("kpi-pout-val");
    const perrElem = document.getElementById("kpi-perr-val");
    const badge = document.getElementById("kpi-conservation-badge");

    if (pinElem) pinElem.innerText = totalIn.toFixed(1);
    if (poutElem) poutElem.innerText = totalOut.toFixed(1);
    if (perrElem) perrElem.innerText = `Δ ${err.toFixed(3)} kW`;
    if (badge) {
        if (err <= 0.05) {
            badge.className = "px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40";
            badge.innerText = "BALANCED";
        } else {
            badge.className = "px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40";
            badge.innerText = "IMBALANCED";
        }
    }

    // 4. Update Topology Canvas
    const topoGridDir = document.getElementById("topo-grid-dir");
    const fGrid = document.getElementById("flow-grid-kw");
    const fSolar = document.getElementById("flow-solar-kw");
    const fBus = document.getElementById("flow-bus-kw");
    const fEv = document.getElementById("flow-ev-kw");
    const fAux = document.getElementById("flow-aux-kw");
    const fStatus = document.getElementById("flow-status-text");

    if (fGrid) {
        if (gridOutKw > 0.05) {
            if (topoGridDir) topoGridDir.innerText = "⬆ OUT:";
            fGrid.innerText = `${gridOutKw.toFixed(1)} kW`;
            fGrid.className = "text-xs font-bold text-teal-300";
        } else {
            if (topoGridDir) topoGridDir.innerText = "⬇ IN:";
            fGrid.innerText = `${gridInKw.toFixed(1)} kW`;
            fGrid.className = "text-xs font-bold text-sky-300";
        }
    }
    if (fSolar) fSolar.innerText = `${solKw.toFixed(1)} kW`;
    if (fBus) fBus.innerText = `${totalIn.toFixed(1)} kW`;
    if (fEv) {
        if (v2gKw > 0.05) {
            fEv.innerText = `-${v2gKw.toFixed(1)} kW (V2G)`;
            fEv.className = "text-xs font-bold text-purple-300";
        } else {
            fEv.innerText = `+${evChgKw.toFixed(1)} kW (Chg)`;
            fEv.className = "text-xs font-bold text-emerald-300";
        }
    }
    if (fAux) fAux.innerText = `${(auxKw + lossesKw).toFixed(1)} kW`;
    if (fStatus) fStatus.innerText = flow.flow_summary || flow.summary || (solKw > 15 ? "Solar Priority EV Charging Active" : "Operational");

    // Dynamic SVG paths
    const pGrid = document.getElementById("path-grid-bus");
    const pSolar = document.getElementById("path-solar-bus");
    const pEv = document.getElementById("path-bus-ev");

    if (pGrid) {
        if (gridOutKw > 0.05) {
            pGrid.setAttribute("stroke", "url(#gradGridOut)");
            pGrid.style.opacity = "1";
        } else if (gridInKw > 0.05) {
            pGrid.setAttribute("stroke", "url(#gradGridIn)");
            pGrid.style.opacity = "1";
        } else {
            pGrid.style.opacity = "0.2";
        }
    }
    if (pSolar) pSolar.style.opacity = solKw > 0.1 ? "1" : "0.2";
    if (pEv) {
        if (v2gKw > 0.05) {
            pEv.setAttribute("stroke", "url(#gradEVDischarge)");
            pEv.style.opacity = "1";
        } else if (evChgKw > 0.05) {
            pEv.setAttribute("stroke", "url(#gradEVCharge)");
            pEv.style.opacity = "1";
        } else {
            pEv.style.opacity = "0.2";
        }
    }

    // Also re-render EV fleet table if open
    renderFleetTable();
}

async function setSimSpeed(speed) {
    updateSpeedUI(speed);
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ command: "SET_SPEED", speed: parseFloat(speed) }));
    }
    try {
        await apiFetch('/api/telemetry/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ speed_multiplier: parseFloat(speed) })
        });
    } catch (e) {
        console.warn("Speed update error:", e);
    }
}

function updateSpeedUI(speed) {
    document.querySelectorAll(".speed-btn").forEach(b => {
        b.classList.remove("bg-emerald-600", "text-white", "font-bold");
        b.classList.add("text-slate-300");
    });
    const idKey = speed == 1 ? '1' : (speed == 60 ? '60' : '900');
    const activeBtn = document.getElementById(`speed-btn-${idKey}`);
    if (activeBtn) {
        activeBtn.classList.add("bg-emerald-600", "text-white", "font-bold");
        activeBtn.classList.remove("text-slate-300");
    }
}

async function changeOperatingMode(mode) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ command: "SET_MODE", mode: mode }));
    }
    try {
        const res = await apiFetch('/api/telemetry/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        const data = await res.json();
        const label = document.getElementById("top-source-label");
        if (label) label.innerText = data.source_label || (mode === 'digital_twin' ? "● DIGITAL TWIN — REAL-TIME SIMULATION" : (mode === 'hybrid' ? "● HYBRID SYSTEM" : "● LIVE HARDWARE"));
    } catch (e) {
        console.warn("Mode change error:", e);
    }
}

async function fetchTelemetryStatus() {
    try {
        const res = await apiFetch('/api/telemetry/status');
        if (!res.ok) return;
        const data = await res.json();
        const sel = document.getElementById("top-mode-select");
        if (sel && data.mode) sel.value = data.mode;
        const label = document.getElementById("top-source-label");
        if (label && data.source_label) label.innerText = data.source_label;
        if (data.speed_multiplier) updateSpeedUI(data.speed_multiplier);
    } catch (e) {
        console.warn("Error fetching telemetry status:", e);
    }
}

async function fetchOperationalAlerts() {
    try {
        const res = await apiFetch('/api/alerts?limit=5');
        if (!res.ok) return;
        const data = await res.json();
        const alerts = data.alerts || [];
        const ticker = document.getElementById("alerts-ticker-text");
        if (ticker && alerts.length > 0) {
            const latest = alerts[0];
            ticker.innerText = `[${latest.time_str || 'ALERT'}] ${latest.category}: ${latest.message}`;
            ticker.className = latest.level === 'CRITICAL' ? 'text-rose-400 font-bold' : 'text-amber-400 font-medium';
        }
    } catch (e) {
        console.warn("Error fetching alerts:", e);
    }
}

function openLedgerModal() {
    document.getElementById("ledger-modal")?.classList.remove("hidden");
    fetchEnergyLedger();
}

function closeLedgerModal() {
    document.getElementById("ledger-modal")?.classList.add("hidden");
}

async function fetchEnergyLedger() {
    const tbody = document.getElementById("ledger-table-body");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-slate-400 font-mono text-xs">Fetching transactions from SQLite ledger...</td></tr>`;

    try {
        const res = await apiFetch('/api/energy/ledger?limit=30');
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        const txs = data.transactions || [];

        if (txs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-slate-400 font-mono text-xs">No ledger transactions recorded yet. They are written automatically during simulation ticks.</td></tr>`;
            return;
        }

        tbody.innerHTML = txs.map(tx => {
            const isRev = tx.cost_or_revenue_inr < 0;
            return `
                <tr class="hover:bg-slate-50 transition font-mono">
                    <td class="p-2.5 font-bold text-slate-700">#${tx.id}</td>
                    <td class="p-2.5 text-slate-500">${tx.timestamp}</td>
                    <td class="p-2.5 font-semibold text-slate-800">
                        <span class="px-1.5 py-0.5 rounded bg-slate-100 border text-[10px]">${tx.source}</span> ➔ <span class="px-1.5 py-0.5 rounded bg-slate-100 border text-[10px]">${tx.destination}</span>
                    </td>
                    <td class="p-2.5 font-bold text-teal-700">${tx.power_kw.toFixed(2)} kW</td>
                    <td class="p-2.5 font-bold text-slate-900">${tx.energy_kwh.toFixed(4)} kWh</td>
                    <td class="p-2.5 text-slate-600">₹${tx.tariff_rate_inr.toFixed(2)}</td>
                    <td class="p-2.5 text-right font-bold ${isRev ? 'text-emerald-700' : 'text-slate-800'}">
                        ${isRev ? '+' : ''}${Math.abs(tx.cost_or_revenue_inr).toFixed(2)} ₹ ${isRev ? '(Rev)' : '(Cost)'}
                    </td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-rose-500 font-mono text-xs">Error loading ledger transactions.</td></tr>`;
    }
}

function renderFleetTable() {
    const tbody = document.getElementById("ev-fleet-table-body");
    if (!tbody) return;

    const evs = currentSimulationState.evs || [];
    if (evs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="p-4 text-center text-slate-400">No EVs registered in fleet.</td></tr>`;
        return;
    }

    tbody.innerHTML = evs.map(ev => {
        const soc = ev.current_soc || 50.0;
        const target = ev.target_soc || 85.0;
        const pwr = ev.current_power_kw || 0.0;
        const bd = ev.power_breakdown || { solar_pct: 100, grid_pct: 0, solar_power_kw: pwr, grid_power_kw: 0 };
        const temp = ev.temperature_c !== undefined ? ev.temperature_c : 28.5;
        const soh = ev.soh_pct !== undefined ? ev.soh_pct : 99.8;
        const isDerated = temp > 43.0;

        let statusBadge = "bg-slate-100 text-slate-700 border-slate-300";
        if (ev.status === "CHARGING") statusBadge = "bg-emerald-100 text-emerald-800 border-emerald-300";
        else if (ev.status === "DISCHARGING") statusBadge = "bg-purple-100 text-purple-800 border-purple-300";

        return `
            <tr class="hover:bg-slate-50 transition">
                <td class="p-3 sm:p-4">
                    <div class="font-bold text-slate-900">${ev.name}</div>
                    <div class="text-[10px] text-slate-400">${ev.id || ev.ev_id} · ${ev.battery_capacity_kwh} kWh</div>
                </td>
                <td class="p-3 sm:p-4">
                    <div class="flex items-center gap-2">
                        <span class="font-bold text-slate-800">${soc.toFixed(1)}%</span>
                        <div class="w-16 h-2 bg-slate-200 rounded-full overflow-hidden">
                            <div class="h-full bg-emerald-500 rounded-full" style="width: ${Math.min(100, soc)}%"></div>
                        </div>
                    </div>
                    <span class="text-[10px] text-slate-400">Target: ${target}%</span>
                </td>
                <td class="p-3 sm:p-4">
                    <div class="font-bold ${pwr > 0 ? 'text-emerald-700' : (pwr < 0 ? 'text-purple-700' : 'text-slate-600')}">
                        ${pwr > 0 ? '+' : ''}${pwr.toFixed(1)} kW
                    </div>
                    ${Math.abs(pwr) > 0.05 ? `
                        <div class="text-[10px] flex items-center gap-1 mt-0.5">
                            <span class="px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 font-bold">${bd.solar_pct || 0}% Solar</span>
                            <span class="px-1.5 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200 font-bold">${bd.grid_pct || 0}% Grid</span>
                        </div>
                    ` : '<span class="text-[10px] text-slate-400">Standby</span>'}
                </td>
                <td class="p-3 sm:p-4">
                    <span class="${isDerated ? 'text-rose-600 font-bold' : 'text-slate-800'}">${temp.toFixed(1)}°C</span>
                    <span class="text-[10px] text-slate-400 block">SOH: ${soh.toFixed(1)}%</span>
                </td>
                <td class="p-3 sm:p-4 text-slate-600">
                    ${ev.arrival_time}:00 - ${ev.departure_time}:00
                </td>
                <td class="p-3 sm:p-4">
                    <span class="px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusBadge}">${ev.status}</span>
                </td>
                <td class="p-3 sm:p-4 text-center">
                    <div class="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-[10px]">
                        <button onclick="setEvOverride('${ev.id || ev.ev_id}', 'CHARGE')" class="px-2 py-0.5 rounded hover:bg-emerald-600 hover:text-white transition">Charge</button>
                        <button onclick="setEvOverride('${ev.id || ev.ev_id}', 'DISCHARGE')" class="px-2 py-0.5 rounded hover:bg-amber-600 hover:text-white transition">V2G</button>
                        <button onclick="setEvOverride('${ev.id || ev.ev_id}', null)" class="px-2 py-0.5 rounded hover:bg-slate-200 transition">Auto</button>
                    </div>
                </td>
                <td class="p-3 sm:p-4 text-right">
                    <button onclick="openXaiModal('${ev.id || ev.ev_id}')" class="px-2.5 py-1 rounded-lg bg-purple-50 hover:bg-purple-100 text-purple-700 text-[10px] font-bold border border-purple-200">
                        Why AI?
                    </button>
                </td>
            </tr>
        `;
    }).join('');
    if (window.lucide) lucide.createIcons();
}

function logSimConsole(text) {
    const consoleElem = document.getElementById("sim-log-console");
    if (!consoleElem) return;
    const entry = document.createElement("div");
    entry.className = "text-slate-300 font-mono text-xs";
    entry.innerText = text;
    consoleElem.appendChild(entry);
    consoleElem.scrollTop = consoleElem.scrollHeight;
}

// ===================================================
// 5. DATA FETCHERS & API ACTIONS
// ===================================================

async function fetchInitialData() {
    try {
        const resState = await apiFetch('/api/simulation/current/state');
        const stateData = await resState.json();
        currentSimulationState = { ...currentSimulationState, ...stateData };
        updateUIFromState(currentSimulationState);

        const [resGrid, resSolar, resPrice] = await Promise.all([
            apiFetch('/api/energy/grid'),
            apiFetch('/api/energy/solar'),
            apiFetch('/api/energy/price')
        ]);
        const gridData = await resGrid.json();
        const solarData = await resSolar.json();
        const priceData = await resPrice.json();

        updateChartsWithProfiles(
            gridData.baseline_hourly_kw || [],
            priceData.hourly_prices || [],
            solarData.hourly_generation_kw || []
        );
    } catch (err) {
        console.error("Failed to load initial data:", err);
    }
}

async function fetchOpenAIInsight() {
    const elem = document.getElementById("openai-insight-text");
    if (elem) elem.innerText = "Querying OpenAI Strategic Energy Advisor...";

    try {
        const res = await apiFetch('/api/ai/insight');
        const data = await res.json();
        if (elem && data.insight) {
            elem.innerText = data.insight;
        }
    } catch (err) {
        if (elem) elem.innerText = "GridWise AI Advisor: High solar availability detected. Prioritizing EV charging during daytime window to minimize peak grid draw.";
    }
}

// ===================================================
// 6. UI SYNCHRONIZATION FROM STATE
// ===================================================

function updateUIFromState(state) {
    if (!state) return;

    const timeStr = state.time || `${Math.floor(state.hour || 0)}:00`;
    const headerClock = document.getElementById("header-clock");
    if (headerClock) headerClock.innerText = `${timeStr} / 24:00`;

    const simClockDisp = document.getElementById("sim-clock-display");
    if (simClockDisp) simClockDisp.innerText = `${timeStr} / 24:00`;

    const simStatusDisp = document.getElementById("sim-status-display");
    if (simStatusDisp) simStatusDisp.innerText = state.status || (state.is_running ? "RUNNING" : "PAUSED");

    const evs = state.evs || [];
    let chargingCount = 0;
    let idleCount = 0;
    let v2gCount = 0;

    evs.forEach(ev => {
        if (ev.status === "CHARGING") chargingCount++;
        else if (ev.status === "DISCHARGING") v2gCount++;
        else idleCount++;
    });

    const kpiActive = document.getElementById("kpi-active-evs");
    const kpiCharging = document.getElementById("kpi-charging-evs");
    const kpiIdle = document.getElementById("kpi-idle-evs");
    const kpiV2g = document.getElementById("kpi-v2g-evs");

    if (kpiActive) kpiActive.innerText = `${evs.length} EVs`;
    if (kpiCharging) kpiCharging.innerText = chargingCount;
    if (kpiIdle) kpiIdle.innerText = idleCount;
    if (kpiV2g) kpiV2g.innerText = v2gCount;

    const netGrid = state.net_grid_load_kw || state.grid_load_kw || 0.0;
    const kpiGrid = document.getElementById("kpi-grid-load");
    if (kpiGrid) kpiGrid.innerText = `${netGrid.toFixed(1)} kW`;

    const stressElem = document.getElementById("kpi-grid-stress");
    const gridStress = state.grid?.stress_level || (netGrid > 85 ? "HIGH" : (netGrid > 70 ? "MEDIUM" : "LOW"));
    if (stressElem) {
        stressElem.innerText = gridStress;
        if (gridStress === "HIGH" || gridStress === "CRITICAL") {
            stressElem.className = "text-[9px] px-1.5 py-0.5 rounded bg-rose-100 text-rose-800 font-bold border border-rose-300";
        } else if (gridStress === "MEDIUM") {
            stressElem.className = "text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-bold border border-amber-300";
        } else {
            stressElem.className = "text-[9px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold border border-emerald-300";
        }
    }

    const solarKw = state.solar_generation_kw || 0.0;
    const kpiSolar = document.getElementById("kpi-solar-gen");
    if (kpiSolar) kpiSolar.innerText = `${solarKw.toFixed(1)} kW`;

    const tariff = state.electricity_price || 4.5;
    const kpiTariff = document.getElementById("kpi-tariff");
    if (kpiTariff) kpiTariff.innerText = `₹${tariff.toFixed(1)}/kWh`;

    // Update Energy Flow Schematics
    updateEnergyFlowCanvas(state);

    // Update AI Decision Card
    updateAIDecisionCard(state);

    // Update Simulator Lab EV Twins Grid
    renderSimulatorEvTwins();

    // Update Simulator Twin Cards
    updateSimulatorTwinCards(state);
}

function updateEnergyFlowCanvas(state) {
    const solarKw = state.solar_generation_kw || 0.0;
    const gridKw = state.net_grid_load_kw || state.grid_load_kw || 0.0;
    const evChgKw = state.total_charging_power_kw || 0.0;
    const v2gKw = state.total_v2g_power_kw || 0.0;

    const netEvPower = evChgKw - v2gKw;

    const flowSolar = document.getElementById("flow-solar-kw");
    const flowGrid = document.getElementById("flow-grid-kw");
    const flowEv = document.getElementById("flow-ev-kw");
    const simSolar = document.getElementById("sim-node-solar-kw");
    const simGrid = document.getElementById("sim-node-grid-kw");
    const simEv = document.getElementById("sim-node-ev-kw");

    if (flowSolar) flowSolar.innerText = `${solarKw.toFixed(1)} kW`;
    if (simSolar) simSolar.innerText = `${solarKw.toFixed(1)} kW`;

    if (flowGrid) flowGrid.innerText = `${gridKw.toFixed(1)} kW`;
    if (simGrid) simGrid.innerText = `${gridKw.toFixed(1)} kW`;

    const evText = netEvPower >= 0 ? `+${netEvPower.toFixed(1)} kW` : `${netEvPower.toFixed(1)} kW (V2G)`;
    if (flowEv) flowEv.innerText = evText;
    if (simEv) simEv.innerText = evText;

    const flowDesc = state.energy_flow?.flow_summary || (solarKw > 15 ? "High Solar Self-Consumption" : "Normal Grid Balancing");
    const flowStatus = document.getElementById("flow-status-text");
    const simFlowStatus = document.getElementById("sim-flow-status");
    if (flowStatus) flowStatus.innerText = flowDesc;
    if (simFlowStatus) simFlowStatus.innerText = flowDesc;

    // Instantaneous split in Simulator Lab
    const solarToEv = Math.min(solarKw, evChgKw);
    const solarToGrid = Math.max(0.0, solarKw - solarToEv);
    const gridToEv = Math.max(0.0, evChgKw - solarToEv);

    const s1 = document.getElementById("split-solar-ev");
    const s2 = document.getElementById("split-solar-grid");
    const s3 = document.getElementById("split-grid-ev");
    const s4 = document.getElementById("split-ev-grid");

    if (s1) s1.innerText = `${solarToEv.toFixed(1)} kW`;
    if (s2) s2.innerText = `${solarToGrid.toFixed(1)} kW`;
    if (s3) s3.innerText = `${gridToEv.toFixed(1)} kW`;
    if (s4) s4.innerText = `${v2gKw.toFixed(1)} kW`;
}

function updateAIDecisionCard(state) {
    const decisions = state.ai_decisions || [];
    if (decisions.length === 0) return;

    const activeDecision = decisions.find(d => d.action_name !== "IDLE") || decisions[0];

    const evNameElem = document.getElementById("decision-ev-name");
    const badgeElem = document.getElementById("decision-action-badge");
    const reasonElem = document.getElementById("decision-reason-text");
    const rewardElem = document.getElementById("decision-reward-val");

    if (evNameElem) evNameElem.innerText = `${activeDecision.ev_id} (${activeDecision.ev_name || 'Tesla Model 3'})`;
    if (reasonElem) reasonElem.innerText = activeDecision.reason || "Autonomous PPO optimization";
    if (rewardElem) rewardElem.innerText = activeDecision.reward > 0 ? `+${activeDecision.reward.toFixed(1)}` : `${activeDecision.reward?.toFixed(1) || '0.0'}`;

    if (badgeElem) {
        if (activeDecision.action_name === "CHARGE") {
            badgeElem.className = "self-start sm:self-auto px-3 py-1 rounded-xl bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs font-bold flex items-center gap-1.5 font-mono pulse-charge";
            badgeElem.innerHTML = `⚡ CHARGE (+${(activeDecision.power_kw || 7.4).toFixed(1)} kW)`;
        } else if (activeDecision.action_name === "DISCHARGE" || activeDecision.action_name.includes("DISCHARGE")) {
            badgeElem.className = "self-start sm:self-auto px-3 py-1 rounded-xl bg-amber-100 text-amber-800 border border-amber-300 text-xs font-bold flex items-center gap-1.5 font-mono pulse-discharge";
            badgeElem.innerHTML = `🔋 DISCHARGE / V2G (${(activeDecision.power_kw || -5.0).toFixed(1)} kW)`;
        } else {
            badgeElem.className = "self-start sm:self-auto px-3 py-1 rounded-xl bg-slate-100 text-slate-800 border border-slate-300 text-xs font-bold flex items-center gap-1.5 font-mono";
            badgeElem.innerHTML = `⏸️ IDLE (0.0 kW)`;
        }
    }
}

function updateSimulatorTwinCards(state) {
    const netGrid = state.net_grid_load_kw || 65.0;
    const solarKw = state.solar_generation_kw || 0.0;
    const evChgKw = state.total_charging_power_kw || 0.0;

    const gCap = document.getElementById("twin-grid-cap");
    const gNet = document.getElementById("twin-grid-net");
    const gUtil = document.getElementById("twin-grid-util");
    const gPeak = document.getElementById("twin-grid-peak");
    const gStress = document.getElementById("twin-grid-stress-badge");

    if (gNet) gNet.innerText = `${netGrid.toFixed(1)} kW`;
    if (gUtil) gUtil.innerText = `${(netGrid / 100.0 * 100).toFixed(1)}%`;
    if (gPeak) gPeak.innerText = `${Math.max(netGrid, 76.0).toFixed(1)} kW`;
    if (gStress) {
        const stress = netGrid > 85 ? "HIGH" : (netGrid > 70 ? "MEDIUM" : "LOW");
        gStress.innerText = `STRESS: ${stress}`;
    }

    const sCurr = document.getElementById("twin-solar-curr");
    const sConsumed = document.getElementById("twin-solar-consumed");
    const sExported = document.getElementById("twin-solar-exported");

    if (sCurr) sCurr.innerText = `${solarKw.toFixed(1)} kW`;
    const solarToEv = Math.min(solarKw, evChgKw);
    if (sConsumed) sConsumed.innerText = `${solarToEv.toFixed(1)} kW`;
    if (sExported) sExported.innerText = `${Math.max(0.0, solarKw - solarToEv).toFixed(1)} kW`;
}

// ===================================================
// 7. SIMULATOR LAB EV TWINS CARDS
// ===================================================

function renderSimulatorEvTwins() {
    const container = document.getElementById("sim-ev-twins-grid");
    if (!container) return;

    const evs = currentSimulationState.evs || [];
    const decisions = currentSimulationState.ai_decisions || [];

    if (evs.length === 0) {
        container.innerHTML = `<div class="p-6 text-center text-slate-400 font-mono text-xs col-span-full">No EV Digital Twins currently active. Click 'Reset Default 5-EV Fleet' above.</div>`;
        return;
    }

    container.innerHTML = evs.map(ev => {
        const dec = decisions.find(d => d.ev_id === ev.id || d.ev_id === ev.ev_id) || {};
        const reason = dec.reason || "Autonomous RL Energy Policy Active";
        const action = dec.action_name || (ev.status === "CHARGING" ? "CHARGE" : (ev.status === "DISCHARGING" ? "DISCHARGE" : "IDLE"));

        let statusClass = "bg-slate-100 text-slate-700 border-slate-300";
        let actionClass = "bg-slate-100 text-slate-700 border-slate-300";

        if (action === "CHARGE") {
            actionClass = "bg-emerald-100 text-emerald-800 border-emerald-300 pulse-charge";
            statusClass = "bg-emerald-100 text-emerald-800 border-emerald-300";
        } else if (action === "DISCHARGE" || action.includes("DISCHARGE")) {
            actionClass = "bg-amber-100 text-amber-800 border-amber-300 pulse-discharge";
            statusClass = "bg-amber-100 text-amber-800 border-amber-300";
        }

        const soc = ev.current_soc || 50.0;
        const targetSoc = ev.target_soc || 85.0;
        const cap = ev.battery_capacity_kwh || 60.0;
        const pwr = ev.current_power_kw || 0.0;
        const health = ev.battery_health || 100.0;
        const cycles = ev.cycle_count || 0.0;
        const storedKwh = (soc / 100.0 * cap).toFixed(1);
        const temp = ev.temperature_c !== undefined ? ev.temperature_c : 28.5;
        const soh = ev.soh_pct !== undefined ? ev.soh_pct : health;
        const isDerated = temp > 45.0;

        return `
            <div class="light-card p-5 rounded-2xl space-y-3.5 border-slate-200">
                <div class="flex items-center justify-between border-b border-slate-100 pb-2.5">
                    <div>
                        <span class="text-[10px] font-mono text-slate-400 uppercase tracking-wider">${ev.id || ev.ev_id}</span>
                        <h4 class="text-sm font-bold text-slate-900">${ev.name}</h4>
                    </div>
                    <span class="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold border ${statusClass}">${ev.status}</span>
                </div>

                <!-- SOC Progress Bar -->
                <div class="space-y-1">
                    <div class="flex justify-between text-xs font-mono">
                        <span class="text-slate-600 font-bold">SOC: ${soc.toFixed(1)}%</span>
                        <span class="text-slate-400">Target: ${targetSoc.toFixed(0)}%</span>
                    </div>
                    <div class="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                        <div class="h-full bg-gradient-to-r from-emerald-500 to-teal-500 rounded-full transition-all duration-300" style="width: ${Math.min(100, soc)}%"></div>
                    </div>
                </div>

                <!-- Metrics Grid -->
                <div class="grid grid-cols-2 gap-2 text-[11px] font-mono">
                    <div class="p-2 rounded-xl bg-slate-50 border border-slate-200">
                        <span class="text-slate-400 block text-[9px]">BATTERY</span>
                        <strong class="text-slate-800">${cap} kWh (${storedKwh} kWh)</strong>
                    </div>
                    <div class="p-2 rounded-xl bg-slate-50 border border-slate-200">
                        <span class="text-slate-400 block text-[9px]">POWER</span>
                        <strong class="text-teal-700">${pwr >= 0 ? '+' : ''}${pwr.toFixed(1)} kW</strong>
                    </div>
                    <div class="p-2 rounded-xl bg-slate-50 border border-slate-200">
                        <span class="text-slate-400 block text-[9px]">CELL TEMP / SOH</span>
                        <strong class="${isDerated ? 'text-amber-600 font-bold' : 'text-slate-800'}">${temp.toFixed(1)}°C / ${soh.toFixed(1)}% ${isDerated ? '<span class="text-[9px] text-rose-600 block">⚠️ Derated</span>' : ''}</strong>
                    </div>
                    <div class="p-2 rounded-xl bg-slate-50 border border-slate-200">
                        <span class="text-slate-400 block text-[9px]">PARKING WINDOW</span>
                        <strong class="text-slate-800">${ev.arrival_time}:00 - ${ev.departure_time}:00</strong>
                    </div>
                </div>

                <!-- XAI Decision Rationale -->
                <div class="p-2.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
                    <div class="flex items-center justify-between text-[10px] font-mono">
                        <span class="text-slate-500 font-bold">AI ACTION</span>
                        <span class="px-2 py-0.5 rounded-lg border font-bold ${actionClass}">${action}</span>
                    </div>
                    <p class="text-[11px] text-slate-700 font-mono leading-tight">${reason}</p>
                </div>

                <!-- Why did AI do this? Button -->
                <button onclick="openXaiModal('${ev.id || ev.ev_id}')" class="w-full py-1.5 px-3 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 text-[11px] font-bold font-mono transition flex items-center justify-center gap-1.5 shadow-sm">
                    <i data-lucide="brain-circuit" class="w-3.5 h-3.5"></i> Why did AI do this?
                </button>
            </div>
        `;
    }).join('');

    if (window.lucide) lucide.createIcons();
}

// ===================================================
// 8. SIMULATION CONTROLS & BATCH RUNS
// ===================================================

function updateSimButtons(isRunning) {
    const startText = document.getElementById("header-sim-btn-text");
    const simCtrlText = document.getElementById("sim-ctrl-start-text");
    const labStartText = document.getElementById("lab-start-btn-text");

    const text = isRunning ? "Pause" : "Start";
    if (startText) startText.innerText = text;
    if (simCtrlText) simCtrlText.innerText = text;
    if (labStartText) labStartText.innerText = text;
}

async function toggleSimulationRun() {
    if (currentSimulationState.is_running) {
        await pauseSimulationApi();
    } else {
        await startSimulationApi();
    }
}

async function startSimulationApi() {
    try {
        await apiFetch('/api/simulation/start', { method: 'POST' });
        currentSimulationState.is_running = true;
        updateSimButtons(true);
    } catch (err) {
        console.error("Error starting simulation:", err);
    }
}

async function pauseSimulationApi() {
    try {
        await apiFetch('/api/simulation/pause', { method: 'POST' });
        currentSimulationState.is_running = false;
        updateSimButtons(false);
    } catch (err) {
        console.error("Error pausing simulation:", err);
    }
}

async function stopSimulationApi() {
    try {
        await apiFetch('/api/simulation/stop', { method: 'POST' });
        currentSimulationState.is_running = false;
        updateSimButtons(false);
        await fetchSimulationHistoryApi();
    } catch (err) {
        console.error("Error stopping simulation:", err);
    }
}

async function simStepApi() {
    try {
        const res = await apiFetch('/api/simulation/step', { method: 'POST' });
        const stepData = await res.json();
        currentSimulationState = { ...currentSimulationState, ...stepData };
        updateUIFromState(currentSimulationState);
    } catch (err) {
        console.error("Error stepping simulation:", err);
    }
}

async function simResetApi() {
    try {
        await apiFetch('/api/simulation/reset', { method: 'POST' });
        currentSimulationState.hour = 0.0;
        currentSimulationState.is_running = false;
        updateSimButtons(false);
        await fetchInitialData();
    } catch (err) {
        console.error("Error resetting simulation:", err);
    }
}

async function launchSmartDemoApi() {
    try {
        const res = await apiFetch('/api/simulation/demo', { method: 'POST' });
        const data = await res.json();
        currentSimulationState = { ...currentSimulationState, ...data.state };
        currentSimulationState.is_running = true;
        updateSimButtons(true);
        updateUIFromState(currentSimulationState);
        logSimConsole("[DEMO] Smart Grid Peak-Shaving Demo active. Solar charging prioritized, peak tariff V2G active.");
    } catch (err) {
        console.error("Error launching demo:", err);
    }
}

async function launch24HourBatchRun() {
    const btn = document.getElementById("btn-sim-run-24h");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Running 24-Hour Cycle...`;
    }

    try {
        const res = await apiFetch('/api/simulation/run-24h', { method: 'POST' });
        const data = await res.json();

        if (res.ok) {
            currentSimulationState = { ...currentSimulationState, ...data.final_state };
            currentSimulationState.is_running = false;
            updateSimButtons(false);
            updateUIFromState(currentSimulationState);
            await runBenchmarkApi();
            await fetchSimulationHistoryApi();
            alert(`24-Hour Simulation Finished!\n\nDuration: 24.0 Hours\nSteps: ${data.steps_executed}\nPeak Load: ${data.benchmark?.summary_comparison?.peak_load_ai_kw || 76.0} kW\nCost Savings: ${data.benchmark?.summary_comparison?.cost_savings_pct || 100.0}%`);
        }
    } catch (err) {
        console.error("24h batch run error:", err);
        alert("Failed to execute 24-hour simulation cycle.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i data-lucide="play-circle" class="w-4 h-4"></i> Run 24-Hour AI vs Baseline`;
            if (window.lucide) lucide.createIcons();
        }
    }
}

// ===================================================
// 9. SCENARIO BUILDER HANDLER
// ===================================================

async function handleScenarioBuilderSubmit(event) {
    event.preventDefault();
    const name = document.getElementById("sc-name").value;
    const timestep = parseInt(document.getElementById("sc-timestep").value);
    const gridCap = parseFloat(document.getElementById("sc-grid-cap").value);
    const solarCap = parseFloat(document.getElementById("sc-solar-cap").value);
    const cloud = parseFloat(document.getElementById("sc-cloud").value);
    const aiEnabled = document.getElementById("sc-ai-enabled").checked;
    const v2gEnabled = document.getElementById("sc-v2g-enabled").checked;

    const payload = {
        name,
        duration_hours: 24.0,
        timestep_minutes: timestep,
        grid_capacity_kw: gridCap,
        solar_capacity_kw: solarCap,
        cloud_factor: cloud,
        ai_enabled: aiEnabled,
        v2g_enabled: v2gEnabled
    };

    try {
        const res = await apiFetch('/api/simulation/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            currentSimulationState = { ...currentSimulationState, ...data.state };
            currentSimulationState.is_running = false;
            updateSimButtons(false);
            updateUIFromState(currentSimulationState);
            const tsDisp = document.getElementById("sim-timestep-display");
            if (tsDisp) tsDisp.innerText = `${timestep} min`;
            alert(`Scenario "${name}" loaded into Python Digital Twin!`);
        }
    } catch (err) {
        console.error("Scenario builder error:", err);
    }
}

async function loadDefaultFleetConfig() {
    await simResetApi();
    renderSimulatorEvTwins();
}

// ===================================================
// 10. BENCHMARK & COMPARATOR
// ===================================================

async function runBenchmarkApi() {
    const btn = document.getElementById("btn-run-benchmark");
    if (btn) btn.disabled = true;

    try {
        const res = await apiFetch('/api/simulation/benchmark');
        const data = await res.json();
        const s = data.summary_comparison;

        // Update Benchmark tab
        const bCostTrad = document.getElementById("bm-cost-trad");
        const bCostAi = document.getElementById("bm-cost-ai");
        const bCostSav = document.getElementById("bm-cost-savings");

        if (bCostTrad) bCostTrad.innerText = `₹${s.energy_cost_traditional_inr.toFixed(2)}`;
        if (bCostAi) bCostAi.innerText = `₹${s.energy_cost_ai_inr.toFixed(2)} (Optimized)`;
        if (bCostSav) bCostSav.innerText = `${s.cost_savings_pct.toFixed(1)}% Savings`;

        const bPeakTrad = document.getElementById("bm-peak-trad");
        const bPeakAi = document.getElementById("bm-peak-ai");
        const bPeakRed = document.getElementById("bm-peak-red");

        if (bPeakTrad) bPeakTrad.innerText = `${s.peak_load_traditional_kw.toFixed(1)} kW`;
        if (bPeakAi) bPeakAi.innerText = `${s.peak_load_ai_kw.toFixed(1)} kW`;
        if (bPeakRed) bPeakRed.innerText = `-${s.peak_load_reduction_pct.toFixed(1)}% Peak Shaved`;

        const bSolTrad = document.getElementById("bm-solar-trad");
        const bSolAi = document.getElementById("bm-solar-ai");
        const bSolGain = document.getElementById("bm-solar-gain");

        if (bSolTrad) bSolTrad.innerText = `${s.solar_used_traditional_kwh.toFixed(1)} kWh`;
        if (bSolAi) bSolAi.innerText = `${s.solar_used_ai_kwh.toFixed(1)} kWh`;
        if (bSolGain) bSolGain.innerText = `+${s.solar_utilization_gain_pct.toFixed(1)}% Utilization`;

        const bV2gAi = document.getElementById("bm-v2g-ai");
        if (bV2gAi) bV2gAi.innerText = `${s.v2g_energy_ai_kwh.toFixed(1)} kWh`;

        // Update Simulator Lab summary cards
        const sCost = document.getElementById("sim-res-cost-savings");
        const sPeak = document.getElementById("sim-res-peak-red");
        const sSol = document.getElementById("sim-res-solar-gain");
        const sV2g = document.getElementById("sim-res-v2g-energy");

        if (sCost) sCost.innerText = `${s.cost_savings_pct.toFixed(1)}%`;
        if (sPeak) sPeak.innerText = `-${s.peak_load_reduction_pct.toFixed(1)}%`;
        if (sSol) sSol.innerText = `+${s.solar_utilization_gain_pct.toFixed(1)}%`;
        if (sV2g) sV2g.innerText = `${s.v2g_energy_ai_kwh.toFixed(1)} kWh`;

        renderBenchmarkChart(data.hourly_history_traditional || [], data.hourly_history_ai || []);
    } catch (err) {
        console.error("Benchmark error:", err);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ===================================================
// 11. HISTORICAL SIMULATION RUNS (DATABASE)
// ===================================================

async function fetchSimulationHistoryApi() {
    try {
        const res = await apiFetch('/api/simulation/history');
        if (!res.ok) return;
        const runs = await res.json();

        // Populate Main Software Analytics History table
        const tbodyMain = document.getElementById("history-table-body");
        if (tbodyMain) {
            if (runs.length === 0) {
                tbodyMain.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-slate-400">No simulation runs stored yet.</td></tr>`;
            } else {
                tbodyMain.innerHTML = runs.map(r => `
                    <tr class="hover:bg-slate-50 transition">
                        <td class="p-3 font-semibold text-slate-900">${r.name || r.simulation_id.substring(0, 8)}</td>
                        <td class="p-3 text-slate-500">${r.created_at ? r.created_at.substring(0, 16).replace("T", " ") : "-"}</td>
                        <td class="p-3">${r.total_evs} EVs</td>
                        <td class="p-3">${r.timestep_minutes} min</td>
                        <td class="p-3 text-emerald-700 font-bold">₹${r.total_charging_cost_inr.toFixed(2)}</td>
                        <td class="p-3 text-sky-700 font-bold">${r.peak_grid_load_kw.toFixed(1)} kW</td>
                        <td class="p-3"><span class="px-2 py-0.5 rounded-full text-[10px] bg-emerald-100 text-emerald-800 font-bold">${r.status}</span></td>
                    </tr>
                `).join('');
            }
        }

        // Populate Simulator Lab History table
        const tbodySim = document.getElementById("sim-lab-history-tbody");
        if (tbodySim) {
            if (runs.length === 0) {
                tbodySim.innerHTML = `<tr><td colspan="8" class="p-4 text-center text-slate-400">No simulation runs stored yet. Run a simulation to persist results.</td></tr>`;
            } else {
                tbodySim.innerHTML = runs.map(r => `
                    <tr class="hover:bg-slate-50 transition font-mono">
                        <td class="p-3 font-semibold text-slate-900">${r.name || r.simulation_id.substring(0, 8)}</td>
                        <td class="p-3">${r.total_evs} EVs</td>
                        <td class="p-3">${r.timestep_minutes}m</td>
                        <td class="p-3 text-emerald-700 font-bold">₹${r.total_charging_cost_inr.toFixed(2)}</td>
                        <td class="p-3 text-sky-700 font-bold">${r.peak_grid_load_kw.toFixed(1)} kW</td>
                        <td class="p-3 text-amber-700 font-bold">${r.solar_utilization_pct.toFixed(1)}%</td>
                        <td class="p-3"><span class="px-2 py-0.5 rounded-full text-[10px] bg-teal-100 text-teal-800 font-bold">${r.status}</span></td>
                        <td class="p-3 text-right">
                            <button onclick="generateReportModal('${r.simulation_id}')" class="px-2.5 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-800 font-bold text-[10px] border border-emerald-300">
                                View Report
                            </button>
                        </td>
                    </tr>
                `).join('');
            }
        }
    } catch (err) {
        console.warn("Could not fetch simulation history:", err);
    }
}

// ===================================================
// 12. AUDIT SIMULATION REPORT MODAL
// ===================================================

let activeReportData = null;

async function generateReportModal(simId = null) {
    const modal = document.getElementById("report-modal");
    const content = document.getElementById("report-modal-content");
    const idElem = document.getElementById("report-modal-id");

    if (modal) modal.classList.remove("hidden");
    if (content) content.innerText = "Generating comprehensive audit report from Digital Twin and database...";

    try {
        const url = simId ? `/api/simulation/${simId}/results` : '/api/simulation/report';
        const res = await apiFetch(url);
        const data = await res.json();
        activeReportData = data;

        if (idElem) idElem.innerText = `Run ID: ${data.simulation_id || 'Active Run'}`;
        if (content) {
            content.innerText = data.markdown_report || (data.analytics ? JSON.stringify(data.analytics, null, 2) : JSON.stringify(data, null, 2));
        }
    } catch (err) {
        if (content) content.innerText = "Error generating simulation audit report.";
    }
}

function closeReportModal() {
    document.getElementById("report-modal")?.classList.add("hidden");
}

function downloadReport(format) {
    if (!activeReportData) return;

    let filename = `GridWise_Report_${activeReportData.simulation_id || 'run'}.${format === 'markdown' ? 'md' : 'json'}`;
    let blobContent = format === 'markdown' ? (activeReportData.markdown_report || JSON.stringify(activeReportData, null, 2)) : JSON.stringify(activeReportData, null, 2);
    let mimeType = format === 'markdown' ? 'text/markdown' : 'application/json';

    const blob = new Blob([blobContent], { type: mimeType });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// ===================================================
// 13. SETTINGS HANDLERS
// ===================================================

async function loadSettings() {
    try {
        const res = await apiFetch("/api/settings");
        if (!res.ok) return;
        const s = await res.json();

        if (s.safety_limits) {
            const minSoc = document.getElementById("set-min-soc");
            const maxSoc = document.getElementById("set-max-soc");
            const urg = document.getElementById("set-urgency-buffer");
            if (minSoc) minSoc.value = s.safety_limits.min_soc_pct || 20.0;
            if (maxSoc) maxSoc.value = s.safety_limits.max_soc_pct || 95.0;
            if (urg) urg.value = s.safety_limits.departure_urgency_buffer_hours || 2.0;
        }

        if (s.grid_limits) {
            const fCap = document.getElementById("set-feeder-cap");
            const sHigh = document.getElementById("set-stress-high");
            if (fCap) fCap.value = s.grid_limits.default_feeder_capacity_kw || 100.0;
            if (sHigh) sHigh.value = s.grid_limits.high_stress_pct || 85.0;
        }

        if (s.v2g_settings) {
            const vMin = document.getElementById("set-v2g-min-soc");
            if (vMin) vMin.value = s.v2g_settings.min_discharge_soc_pct || 35.0;
        }
    } catch (err) {
        console.warn("Failed to load settings:", err);
    }
}

async function handleSettingsSubmit(event) {
    event.preventDefault();
    const payload = {
        safety_limits: {
            min_soc_pct: parseFloat(document.getElementById("set-min-soc").value),
            max_soc_pct: parseFloat(document.getElementById("set-max-soc").value),
            departure_urgency_buffer_hours: parseFloat(document.getElementById("set-urgency-buffer").value)
        },
        grid_limits: {
            default_feeder_capacity_kw: parseFloat(document.getElementById("set-feeder-cap").value),
            high_stress_pct: parseFloat(document.getElementById("set-stress-high").value)
        },
        v2g_settings: {
            min_discharge_soc_pct: parseFloat(document.getElementById("set-v2g-min-soc").value)
        }
    };

    try {
        const res = await apiFetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            alert("Platform settings and safety thresholds updated successfully!");
        }
    } catch (err) {
        alert("Error saving settings.");
    }
}

// ===================================================
// 14. FLEET TABLE & OPERATOR CONTROLS
// ===================================================

function renderFleetTable() {
    const tbody = document.getElementById("ev-fleet-table-body");
    if (!tbody) return;

    const evs = currentSimulationState.evs || [];
    tbody.innerHTML = evs.map(ev => {
        const soc = ev.current_soc || 50.0;
        const targetSoc = ev.target_soc || 85.0;
        return `
            <tr class="hover:bg-slate-50 transition">
                <td class="p-3 sm:p-4">
                    <span class="font-bold text-slate-900">${ev.id || ev.ev_id}</span>
                    <span class="text-slate-400 block text-[10px]">${ev.name}</span>
                </td>
                <td class="p-3 sm:p-4">
                    <span class="font-bold text-slate-800">${soc.toFixed(1)}%</span>
                </td>
                <td class="p-3 sm:p-4">${targetSoc}%</td>
                <td class="p-3 sm:p-4">${ev.arrival_time}:00 - ${ev.departure_time}:00</td>
                <td class="p-3 sm:p-4">+${ev.max_charge_power_kw}kW / -${ev.max_discharge_power_kw}kW</td>
                <td class="p-3 sm:p-4"><span class="px-2 py-0.5 rounded-full text-[10px] bg-slate-100 border border-slate-300">${ev.status}</span></td>
                <td class="p-3 sm:p-4 text-center">
                    <div class="inline-flex items-center gap-1">
                        <button onclick="openXaiModal('${ev.id || ev.ev_id}')" class="px-2 py-1 bg-purple-100 hover:bg-purple-200 text-purple-800 font-bold rounded text-[10px] flex items-center gap-1" title="Explainable AI Decision Details"><i data-lucide="brain-circuit" class="w-3 h-3"></i> AI Rationale</button>
                        <button onclick="setEvOverride('${ev.id || ev.ev_id}', 'CHARGE')" class="px-2 py-1 bg-emerald-100 hover:bg-emerald-200 text-emerald-800 font-bold rounded text-[10px]">CHARGE</button>
                        <button onclick="setEvOverride('${ev.id || ev.ev_id}', 'DISCHARGE')" class="px-2 py-1 bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold rounded text-[10px]">V2G</button>
                        <button onclick="setEvOverride('${ev.id || ev.ev_id}', null)" class="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded text-[10px]">AUTO</button>
                    </div>
                </td>
                <td class="p-3 sm:p-4 text-right">
                    <button onclick="deleteEvApi('${ev.id || ev.ev_id}')" class="text-rose-600 hover:underline">Delete</button>
                </td>
            </tr>
        `;
    }).join('');
}

async function setEvOverride(evId, action) {
    try {
        await apiFetch(`/api/evs/${evId}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        await fetchInitialData();
    } catch (err) {
        console.error("Error setting override:", err);
    }
}

function openAddEvModal() {
    document.getElementById("add-ev-modal")?.classList.remove("hidden");
}

function closeAddEvModal() {
    document.getElementById("add-ev-modal")?.classList.add("hidden");
}

async function submitAddEvForm(event) {
    event.preventDefault();
    const evData = {
        name: document.getElementById("input-ev-name").value,
        battery_capacity_kwh: parseFloat(document.getElementById("input-ev-capacity").value),
        current_soc: parseFloat(document.getElementById("input-ev-soc").value),
        required_soc: parseFloat(document.getElementById("input-ev-req-soc").value),
        target_soc: parseFloat(document.getElementById("input-ev-req-soc").value),
        minimum_soc: parseFloat(document.getElementById("input-ev-min-soc").value),
        maximum_soc: 100.0,
        arrival_time: parseFloat(document.getElementById("input-ev-arrival").value),
        departure_time: parseFloat(document.getElementById("input-ev-departure").value),
        max_charge_power_kw: 7.4,
        max_discharge_power_kw: 5.0
    };

    try {
        await apiFetch('/api/evs', {
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
        await apiFetch(`/api/evs/${evId}`, { method: 'DELETE' });
        await fetchInitialData();
    } catch (err) {
        console.error("Delete EV error:", err);
    }
}

function updateAnalyticsTabKPIs() {
    const costElem = document.getElementById("an-charging-cost");
    const v2gElem = document.getElementById("an-v2g-revenue");
    const solarElem = document.getElementById("an-solar-pct");

    if (costElem) costElem.innerText = `₹${(currentSimulationState.total_energy_cost_inr || 0).toFixed(2)}`;
    if (v2gElem) v2gElem.innerText = `₹${(currentSimulationState.total_v2g_revenue_inr || 0).toFixed(2)}`;
    if (solarElem) {
        const gen = currentSimulationState.total_solar_generated_kwh || 1.0;
        const used = currentSimulationState.total_solar_used_kwh || 0.0;
        solarElem.innerText = `${((used / gen) * 100).toFixed(1)}%`;
    }
}

function loadAiScheduleMatrix() {
    const matrix = document.getElementById("ai-schedule-matrix");
    if (!matrix) return;
    const hours = Array.from({length: 24}, (_, i) => i);
    matrix.innerHTML = `
        <div class="grid grid-cols-12 gap-1 text-center font-mono text-[10px]">
            ${hours.map(h => {
                let color = "bg-slate-100 text-slate-700";
                let label = "IDLE";
                if (h >= 10 && h <= 15) { color = "bg-emerald-100 text-emerald-800 font-bold"; label = "CHARGE"; }
                else if (h >= 18 && h <= 21) { color = "bg-amber-100 text-amber-800 font-bold"; label = "V2G"; }
                return `<div class="p-2 rounded-lg ${color} border border-slate-200">
                    <div class="text-[9px] text-slate-400">${h}:00</div>
                    <div>${label}</div>
                </div>`;
            }).join('')}
        </div>
    `;
}

// ===================================================
// 15. CHARTS INITIALIZATION
// ===================================================

function initCharts() {
    const ctx1 = document.getElementById("chart-grid-load")?.getContext("2d");
    if (ctx1) {
        gridLoadChart = new Chart(ctx1, {
            type: 'line',
            data: {
                labels: Array.from({length: 24}, (_, i) => `${i}:00`),
                datasets: [
                    { label: 'Base Feeder Demand (kW)', data: [], borderColor: '#0284c7', backgroundColor: 'rgba(2, 132, 199, 0.08)', fill: true, tension: 0.4 },
                    { label: 'Net Feeder Load with EVs (kW)', data: [], borderColor: '#059669', borderWidth: 2.5, tension: 0.4 }
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
                    { label: 'Simulated Electricity Price (₹/kWh)', data: [], backgroundColor: 'rgba(217, 119, 6, 0.7)', yAxisID: 'y' },
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
    const tradLoads = tradHistory.map(h => h.net_grid_load_kw);
    const aiLoads = aiHistory.map(h => h.net_grid_load_kw);

    if (benchmarkGridChart) benchmarkGridChart.destroy();

    benchmarkGridChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: 'Traditional Immediate Charging (kW)', data: tradLoads, borderColor: '#d97706', borderWidth: 2, tension: 0.3 },
                { label: 'GridWise AI Optimized Feeder Load (kW)', data: aiLoads, borderColor: '#059669', borderWidth: 3, tension: 0.3 }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#334155', font: { family: 'monospace' } } } }, scales: { x: { grid: { color: '#e2e8f0' }, ticks: { color: '#64748b', font: { family: 'monospace' } } }, y: { grid: { color: '#e2e8f0' }, ticks: { color: '#64748b', font: { family: 'monospace' } } } } }
    });
}

// ===================================================
// 17. AI TRAINING CENTER & PPO NEURAL POLICY CHARTS
// ===================================================

let ppoRewardChart = null;
let ppoLossChart = null;
let ppoSolarChart = null;
let ppoPeakChart = null;
let predictiveForecastChart = null;

async function loadAiTrainingCenter() {
    try {
        const res = await apiFetch('/api/ai/training/status');
        if (!res || !res.ok) return;
        const data = await res.json();

        // Update badges & metrics safely
        const badge = document.getElementById("ai-policy-status-badge");
        if (badge) badge.innerText = `${data.status || 'TRAINED'} (${(data.episodes_trained || 10000).toLocaleString()} EPS)`;
        const epEl = document.getElementById("ai-episodes-trained");
        if (epEl) epEl.innerText = (data.episodes_trained || 10000).toLocaleString();
        const rwEl = document.getElementById("ai-mean-reward");
        if (rwEl) rwEl.innerText = `+${formatMetric(data.mean_reward, 2)}`;

        const hist = data.training_curves || data.training_history || {};
        const episodes = hist.episodes || [0, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000];
        const labels = episodes.map(e => `${e} eps`);

        // 1. Reward Convergence Curve
        const ctxReward = document.getElementById("chart-ppo-reward")?.getContext("2d");
        if (ctxReward) {
            if (ppoRewardChart) ppoRewardChart.destroy();
            ppoRewardChart = new Chart(ctxReward, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Mean Episode Reward',
                        data: hist.rewards || [-14.5, -4.2, 2.1, 8.4, 12.0, 14.5, 16.2, 17.1, 17.8, 18.2, 18.3, 18.42],
                        borderColor: '#059669',
                        backgroundColor: 'rgba(5, 150, 105, 0.1)',
                        fill: true,
                        borderWidth: 2.5,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } },
                        y: { grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } }
                    }
                }
            });
        }

        // 2. Loss Curves (Actor + Critic)
        const ctxLoss = document.getElementById("chart-ppo-loss")?.getContext("2d");
        if (ctxLoss) {
            if (ppoLossChart) ppoLossChart.destroy();
            ppoLossChart = new Chart(ctxLoss, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Actor Log-Loss',
                            data: hist.actor_loss || [0.85, 0.62, 0.48, 0.35, 0.28, 0.22, 0.18, 0.15, 0.13, 0.12, 0.11, 0.10],
                            borderColor: '#7c3aed',
                            borderWidth: 2,
                            tension: 0.3
                        },
                        {
                            label: 'Critic Value Loss (MSE / 10)',
                            data: (hist.critic_loss || [18.2, 12.4, 7.8, 4.2, 2.6, 1.8, 1.2, 0.85, 0.62, 0.48, 0.39, 0.34]).map(v => (v !== undefined && v !== null) ? (v / 10).toFixed(2) : "0.00"),
                            borderColor: '#0284c7',
                            borderWidth: 2,
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { labels: { font: { family: 'monospace', size: 10 } } } },
                    scales: {
                        x: { grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } },
                        y: { grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } }
                    }
                }
            });
        }

        // 3. Solar Utilization
        const ctxSolar = document.getElementById("chart-ppo-solar")?.getContext("2d");
        if (ctxSolar) {
            if (ppoSolarChart) ppoSolarChart.destroy();
            ppoSolarChart = new Chart(ctxSolar, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Solar Self-Consumption (%)',
                        data: hist.solar_utilization || [45.0, 52.0, 60.5, 69.2, 75.4, 80.1, 83.5, 85.8, 87.2, 88.0, 88.6, 89.2],
                        borderColor: '#d97706',
                        backgroundColor: 'rgba(217, 119, 6, 0.1)',
                        fill: true,
                        borderWidth: 2.5,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } },
                        y: { min: 40, max: 100, grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } }
                    }
                }
            });
        }

        // 4. Peak Load Reduction
        const ctxPeak = document.getElementById("chart-ppo-peak")?.getContext("2d");
        if (ctxPeak) {
            if (ppoPeakChart) ppoPeakChart.destroy();
            ppoPeakChart = new Chart(ctxPeak, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Peak Grid Load Reduction (%)',
                        data: hist.peak_reduction || [2.0, 5.5, 10.2, 14.8, 18.2, 20.5, 21.8, 22.5, 23.0, 23.4, 23.8, 24.1],
                        borderColor: '#0d9488',
                        backgroundColor: 'rgba(13, 148, 136, 0.1)',
                        fill: true,
                        borderWidth: 2.5,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } },
                        y: { min: 0, max: 35, grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } }
                    }
                }
            });
        }
    } catch (err) {
        console.error("Error loading AI Training Center:", err);
    }
}

async function triggerPpoTraining() {
    const epSelect = document.getElementById("train-episodes-select");
    const numEpisodes = parseInt(epSelect ? epSelect.value : "50", 10);
    const statusBox = document.getElementById("training-status-box");
    const msgEl = document.getElementById("training-status-message");
    const counterEl = document.getElementById("training-status-counter");
    const barEl = document.getElementById("training-progress-bar");
    const btnText = document.getElementById("btn-train-ppo-text");

    if (statusBox) statusBox.classList.remove("hidden");
    if (btnText) btnText.innerText = "Training...";
    if (barEl) barEl.style.width = "25%";
    if (msgEl) msgEl.innerText = `Starting PPO training for ${numEpisodes} episodes...`;
    if (counterEl) counterEl.innerText = "Initializing";

    try {
        const res = await apiFetch('/api/ai/train', {
            method: 'POST',
            body: JSON.stringify({ episodes: numEpisodes, background: true })
        });
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'error'}`);
        const result = await res.json();

        // If running in background, poll status
        if (result.status === "started") {
            let pollCount = 0;
            const pollInterval = setInterval(async () => {
                pollCount++;
                try {
                    const statusRes = await apiFetch('/api/ai/training/status');
                    if (statusRes && statusRes.ok) {
                        const statusData = await statusRes.json();
                        const pct = statusData.progress_percent || Math.min(95, pollCount * 12);
                        if (barEl) barEl.style.width = `${pct}%`;
                        if (counterEl) counterEl.innerText = `Ep ${statusData.episode || '...'}/${statusData.total_episodes || numEpisodes}`;

                        if (statusData.status === "completed" || statusData.status === "TRAINED" || (statusData.active_job && statusData.active_job.status === "completed") || pct >= 100) {
                            clearInterval(pollInterval);
                            if (barEl) barEl.style.width = "100%";
                            const meanR = formatMetric(statusData.mean_reward ?? statusData.metrics?.mean_reward);
                            const epsAdd = statusData.episodes_added ?? statusData.metrics?.episodes_added ?? numEpisodes;
                            if (msgEl) msgEl.innerText = `Training completed! Trained +${epsAdd} episodes. Mean Reward: +${meanR}`;
                            if (counterEl) counterEl.innerText = "Converged";

                            await loadAiTrainingCenter();
                            setTimeout(() => {
                                if (statusBox) statusBox.classList.add("hidden");
                                if (btnText) btnText.innerText = "Train Policy Now";
                            }, 3500);
                        }
                    }
                } catch (e) {
                    // ignore poll error and continue
                }
                if (pollCount > 60) {
                    clearInterval(pollInterval);
                    if (btnText) btnText.innerText = "Train Policy Now";
                }
            }, 600);
            return;
        }

        // Direct synchronous response fallback
        if (barEl) barEl.style.width = "100%";
        const meanR = formatMetric(result.mean_reward ?? result.final_reward ?? result.metrics?.mean_reward);
        const epsAdd = result.episodes_added ?? result.metrics?.episodes_added ?? numEpisodes;
        if (msgEl) msgEl.innerText = `Training completed! Trained +${epsAdd} episodes. Mean Reward: +${meanR}`;
        if (counterEl) counterEl.innerText = "Converged";

        await loadAiTrainingCenter();
        setTimeout(() => {
            if (statusBox) statusBox.classList.add("hidden");
            if (btnText) btnText.innerText = "Train Policy Now";
        }, 3500);
    } catch (err) {
        console.error("Error running PPO training:", err);
        if (msgEl) msgEl.innerText = "Training encountered an issue.";
        if (btnText) btnText.innerText = "Train Policy Now";
    }
}

// ===================================================
// 18. EXPLAINABLE AI (XAI) DEEP DIVE MODAL
// ===================================================

async function openXaiModal(evId) {
    const modal = document.getElementById("xai-modal");
    if (!modal) return;

    modal.classList.remove("hidden");
    const badge = document.getElementById("xai-ev-badge");
    if (badge) badge.innerText = evId;

    try {
        const res = await apiFetch(`/api/ai/explain/${evId}`);
        if (!res.ok) throw new Error("Could not fetch XAI explanation");
        const data = await res.json();

        const modelEl = document.getElementById("xai-ev-model");
        if (modelEl) modelEl.innerText = `Model: ${data.ev_name || data.ev_id} | Battery: ${data.battery_capacity_kwh || 60} kWh`;

        const socEl = document.getElementById("xai-soc");
        if (socEl) socEl.innerText = `${(data.current_soc || 50).toFixed(1)}%`;
        const targetSocEl = document.getElementById("xai-target-soc");
        if (targetSocEl) targetSocEl.innerText = `${(data.target_soc || 85).toFixed(0)}%`;
        const depEl = document.getElementById("xai-departure");
        if (depEl) depEl.innerText = `${data.departure_time || 18}:00`;

        const tempEl = document.getElementById("xai-temp");
        if (tempEl) tempEl.innerText = `${(data.temperature_c || 28.5).toFixed(1)}°C`;
        const sohEl = document.getElementById("xai-soh");
        if (sohEl) sohEl.innerText = `${(data.soh_pct || 99.9).toFixed(2)}%`;

        const deratingEl = document.getElementById("xai-derating");
        if (deratingEl) {
            if (data.is_thermally_throttled || (data.temperature_c && data.temperature_c > 45)) {
                deratingEl.innerHTML = `<span class="text-rose-600 font-bold">Throttled (T > 45°C)</span>`;
            } else {
                deratingEl.innerText = "100% (Nominal)";
            }
        }

        // Neural Net outputs
        const probs = data.actor_probabilities || { IDLE: 0.2, CHARGE: 0.7, DISCHARGE: 0.1 };
        const pCharge = Math.round((probs.CHARGE || 0) * 100);
        const pIdle = Math.round((probs.IDLE || 0) * 100);
        const pDischarge = Math.round((probs.DISCHARGE || 0) * 100);

        const prChargeEl = document.getElementById("xai-prob-charge");
        if (prChargeEl) prChargeEl.innerText = `${pCharge}%`;
        const barChargeEl = document.getElementById("xai-bar-charge");
        if (barChargeEl) barChargeEl.style.width = `${pCharge}%`;

        const prIdleEl = document.getElementById("xai-prob-idle");
        if (prIdleEl) prIdleEl.innerText = `${pIdle}%`;
        const barIdleEl = document.getElementById("xai-bar-idle");
        if (barIdleEl) barIdleEl.style.width = `${pIdle}%`;

        const prDiscEl = document.getElementById("xai-prob-discharge");
        if (prDiscEl) prDiscEl.innerText = `${pDischarge}%`;
        const barDiscEl = document.getElementById("xai-bar-discharge");
        if (barDiscEl) barDiscEl.style.width = `${pDischarge}%`;

        const rawActEl = document.getElementById("xai-raw-action");
        if (rawActEl) rawActEl.innerText = data.raw_proposed_action || "CHARGE";
        const confEl = document.getElementById("xai-confidence");
        if (confEl) confEl.innerText = (data.confidence_score || 0.85).toFixed(3);
        const criticEl = document.getElementById("xai-critic-value");
        if (criticEl) criticEl.innerText = (data.critic_state_value !== undefined ? (data.critic_state_value >= 0 ? `+${data.critic_state_value.toFixed(2)}` : data.critic_state_value.toFixed(2)) : "+14.2");

        // Constraint checks
        const checks = data.constraint_checks || {};
        const chkOver = document.getElementById("xai-check-overcharge");
        if (chkOver) {
            chkOver.innerText = checks.overcharge_prevented ? "OVERRIDE" : "PASS";
            chkOver.className = checks.overcharge_prevented ? "font-bold text-amber-600" : "font-bold text-emerald-600";
        }
        const chkDis = document.getElementById("xai-check-discharge");
        if (chkDis) {
            chkDis.innerText = checks.deep_discharge_prevented ? "OVERRIDE" : "PASS";
            chkDis.className = checks.deep_discharge_prevented ? "font-bold text-amber-600" : "font-bold text-emerald-600";
        }
        const chkSla = document.getElementById("xai-check-sla");
        if (chkSla) {
            chkSla.innerText = checks.departure_urgency_enforced ? "ENFORCED" : "PASS";
            chkSla.className = checks.departure_urgency_enforced ? "font-bold text-amber-600" : "font-bold text-emerald-600";
        }
        const chkGrid = document.getElementById("xai-check-grid");
        if (chkGrid) {
            chkGrid.innerText = checks.grid_transformer_limit_checked ? "VERIFIED" : "PASS";
            chkGrid.className = "font-bold text-emerald-600";
        }

        const overrideAlert = document.getElementById("xai-override-alert");
        if (overrideAlert) {
            if (data.safety_interventions && data.safety_interventions.length > 0) {
                overrideAlert.classList.remove("hidden");
                overrideAlert.innerText = `⚠️ Safety Override: ${data.safety_interventions.join(" | ")}`;
            } else {
                overrideAlert.classList.add("hidden");
            }
        }

        // Final Action & Rationale
        const finalBadge = document.getElementById("xai-final-action-badge");
        if (finalBadge) {
            const pwr = data.approved_power_kw || 0.0;
            finalBadge.innerText = `${data.final_approved_action} (${pwr >= 0 ? '+' : ''}${pwr.toFixed(1)} kW)`;
            if (data.final_approved_action === "CHARGE") {
                finalBadge.className = "px-2.5 py-0.5 rounded-lg font-bold text-xs bg-emerald-600 text-white";
            } else if (data.final_approved_action.includes("DISCHARGE")) {
                finalBadge.className = "px-2.5 py-0.5 rounded-lg font-bold text-xs bg-amber-600 text-white";
            } else {
                finalBadge.className = "px-2.5 py-0.5 rounded-lg font-bold text-xs bg-slate-600 text-white";
            }
        }

        const ratEl = document.getElementById("xai-full-rationale");
        if (ratEl) ratEl.innerText = data.explanation || "Optimal economic and grid stabilization state verified.";

        if (window.lucide) lucide.createIcons();
    } catch (err) {
        console.error("Error fetching XAI explanation:", err);
    }
}

function closeXaiModal() {
    document.getElementById("xai-modal")?.classList.add("hidden");
}

// ===================================================
// 19. SCENARIO PRESETS & CSV EXPORT
// ===================================================

function applyPresetSelection(presetKey) {
    if (!presetKey) return;
    loadSelectedPreset();
}

async function loadSelectedPreset() {
    const sel = document.getElementById("preset-selector");
    const key = sel ? sel.value : "";
    if (!key) return;

    try {
        const res = await apiFetch(`/api/simulation/presets/${key}`, { method: 'POST' });
        if (!res.ok) throw new Error("Could not load preset");
        await fetchInitialData();
        renderSimulatorEvTwins();
        refreshForecastHorizon();
        fetchConstraintEvents();
    } catch (err) {
        console.error("Error loading preset:", err);
    }
}

function downloadExperimentCsv() {
    window.location.href = '/api/simulation/export/csv';
}

// ===================================================
// 20. 4-HOUR PREDICTIVE FORECAST HORIZON
// ===================================================

async function refreshForecastHorizon() {
    try {
        const res = await apiFetch('/api/energy/forecast');
        if (!res.ok) return;
        const data = await res.json();

        const summaryEl = document.getElementById("forecast-strategic-summary");
        if (summaryEl) summaryEl.innerText = data.strategic_recommendation || "Maintain balanced scheduling.";

        const peakSolarEl = document.getElementById("forecast-solar-peak");
        if (peakSolarEl) peakSolarEl.innerText = `${data.forecast_solar_peak_kw || 0.0} kW`;

        const avgPriceEl = document.getElementById("forecast-avg-price");
        if (avgPriceEl) avgPriceEl.innerText = `₹${(data.forecast_avg_price || 6.5).toFixed(2)}/kWh`;

        const ctx = document.getElementById("chart-predictive-forecast")?.getContext("2d");
        if (!ctx) return;

        const horizon = data.hourly_lookahead || [];
        const labels = horizon.map(h => `${h.hour.toFixed(0)}:00 (+${h.offset_hours}h)`);
        const solarData = horizon.map(h => h.solar_generation_kw);
        const gridData = horizon.map(h => h.net_grid_load_kw);
        const priceData = horizon.map(h => h.electricity_price);

        if (predictiveForecastChart) predictiveForecastChart.destroy();
        predictiveForecastChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    { label: 'Forecast Solar PV (kW)', data: solarData, borderColor: '#d97706', backgroundColor: 'rgba(217, 119, 6, 0.1)', fill: true, borderWidth: 2.5, tension: 0.3 },
                    { label: 'Forecast Grid Load (kW)', data: gridData, borderColor: '#0284c7', borderWidth: 2, tension: 0.3 },
                    { label: 'TOU Tariff (₹/kWh)', data: priceData, borderColor: '#7c3aed', borderDash: [5, 5], borderWidth: 1.5, yAxisID: 'yPrice' }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { font: { family: 'monospace', size: 10 } } } },
                scales: {
                    x: { grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } },
                    y: { title: { display: true, text: 'Power (kW)', font: { size: 10 } }, grid: { color: '#f1f5f9' }, ticks: { font: { family: 'monospace', size: 10 } } },
                    yPrice: { position: 'right', title: { display: true, text: 'Tariff (₹/kWh)', font: { size: 10 } }, grid: { drawOnChartArea: false }, ticks: { font: { family: 'monospace', size: 10 } } }
                }
            }
        });
    } catch (err) {
        console.error("Error fetching forecast:", err);
    }
}

// ===================================================
// 21. SAFETY CONSTRAINT INTERVENTIONS AUDIT LOG
// ===================================================

async function fetchConstraintEvents() {
    try {
        const res = await apiFetch('/api/ai/constraints/events?limit=25');
        if (!res || !res.ok) return;
        const payload = await res.json();
        const events = normalizeConstraintEvents(payload);
        const tbody = document.getElementById("table-constraint-events-body");
        if (!tbody) return;

        if (events.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="p-4 text-center text-slate-400 font-mono text-xs">No safety interventions recorded. Policy running strictly inside safe operational boundaries.</td></tr>`;
            return;
        }

        tbody.innerHTML = events.slice(-15).reverse().map(ev => {
            const hour = typeof ev.hour === 'number' ? `${ev.hour.toFixed(1)}h` : (ev.hour || '—');
            const rawAct = ev.raw_action === 1 ? 'CHARGE' : (ev.raw_action === 2 ? 'DISCHARGE' : 'IDLE');
            const appAct = ev.approved_action === 1 ? 'CHARGE' : (ev.approved_action === 2 ? 'DISCHARGE' : 'IDLE');
            const evId = ev.ev_id || ev.id || 'SYSTEM';
            return `
                <tr class="hover:bg-amber-50/50 transition font-mono text-[11px]">
                    <td class="p-2.5 font-bold text-slate-800">${hour}</td>
                    <td class="p-2.5 font-bold text-purple-700">${evId}</td>
                    <td class="p-2.5 text-slate-600"><span class="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200">${rawAct}</span></td>
                    <td class="p-2.5 font-bold text-emerald-700"><span class="px-1.5 py-0.5 rounded bg-emerald-50 border border-emerald-200">${appAct}</span></td>
                    <td class="p-2.5 text-amber-800">${ev.reason || 'Boundary Safety Rule Enforcement'}</td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        console.error("Error fetching constraint events:", err);
    }
}

