// GridWise AI -- Real-Time V2G Digital Twin Simulation Laboratory
// Fixed Engineering Architecture Edition (GECR CSE)
// Complies with PRD Sections 1-83:
// - Fixed V2G Digital Twin Architecture (Grid -> Charger <-> Battery, Meter measurement only)
// - No Component Library, No Manual Cabling, No Snap, No Auto-Connect, No Rotate, No Deletions
// - Architecture Locked by default, with [EDIT] mode for parameters & data configuration
// - 5-Tab Contextual Inspector: Overview, Parameters, Telemetry, Connections, Source
// - Separate Live Grid Demand (13.74 GW) vs Simulated EV Impact (+8.4 kW) vs Managed Load
// - Authoritative WebSocket telemetry streaming and simulation state synchronization

const LabWorkspace = (function() {
  // DOM Elements
  let canvasContainer = null;
  let canvasSvg = null;
  let nodesContainer = null;
  let inspectorContent = null;
  let timelineScrubber = null;
  let timelineLabel = null;

  // Digital Twin System State
  let nodes = [];
  let connections = [];
  let selectedNodeId = 'drl_01'; // Default selected node
  let selectedConnectionId = null;
  let activeStrategy = 'drl';
  let isRunning = false;
  let isCircuitFixed = true; // PRD: Architecture is locked by default
  let isEditMode = false;     // PRD: Toggleable edit mode for parameters
  let activeInspectorTab = 'overview'; // 'overview', 'parameters', 'telemetry', 'connections', 'source'
  let currentDataMode = 'LIVE'; // 'LIVE', 'HISTORICAL', 'SIMULATION'
  let currentStep = 74; // 18:30 setpoint (Evening Peak)
  let speedMultiplier = 2.0;
  let simTimer = null;
  let ws = null;
  let isWsConnected = false;
  let currentZoom = 1.0;
  let openBatteryNodeId = null;

  // Real-Time System Telemetry State
  const telemetryState = {
    gridDemandGw: 13.740,
    gridDemandMw: 13740.0,
    gridSupplyGw: 14.200,
    gridSupplyMw: 14200.0,
    gridMarginGw: 0.460,
    gridFrequencyHz: 49.96,
    gridVoltageKv: 400.0,
    gridStatus: 'NORMAL',
    gridSource: 'KPTCL SLDC',
    gridAgeSec: 4,

    marketPrice: 8.20,
    marketBlock: '18:45-19:00',
    priceState: 'HIGH',
    priceSource: 'IEX RTM',
    priceAgeSec: 45,

    solarGw: 1.99,
    windGw: 2.41,
    hydroGw: 0.62,
    renewableTotalGw: 5.02,
    renewableSharePct: 36.5,
    renewableSource: 'Live Grid Data (Karnataka SLDC)',
    renewableAgeSec: 8,

    evSoc: 64.2,
    evCapacityKwh: 72.0,
    evArrivalTime: '08:00',
    evDepartureTime: '19:30',
    evRequiredSoc: 80.0,
    evMinSoc: 20.0,
    evMaxSoc: 95.0,
    evV2gEnabled: true,
    evV2gReserve: 30.0,

    chargerRatedKw: 22.0,
    chargerPowerKw: 8.4,
    chargerMode: 'CHARGING', // CHARGING, V2G, IDLE
    chargerEfficiency: 0.95,
    chargerVoltageV: 400.0,
    chargerCurrentA: 21.0,

    drlAlgorithm: 'PPO',
    drlAction: 'CHARGE',
    drlPowerKw: 8.4,
    drlReward: 0.84,
    drlUrgencyPct: 42.0,
    drlMeanReward: 14.82,

    meterImportKw: 8.40,
    meterExportKw: 0.00,
    meterNetKw: 8.40,
    meterImportKwh: 14.82,
    meterExportKwh: 0.00,
    meterDirection: 'GRID -> EV',

    simManagedLoadGw: 13.7484,
    simEvImpactKw: 8.40
  };

  // 24h Telemetry History for bottom sparklines (96 steps)
  const history = {
    gridBase: new Array(96).fill(null),
    gridNet: new Array(96).fill(null),
    evSoc: new Array(96).fill(null),
    evPower: new Array(96).fill(null)
  };

  // Diurnal Synthetic Profiles (used when in SIMULATION mode)
  function getSyntheticGridDemand(step) {
    const t = (step % 96) * 0.25;
    const base = 11.8;
    const morningPeak = 1.2 * Math.exp(-Math.pow((t - 9.5) / 2.0, 2));
    const eveningPeak = 1.94 * Math.exp(-Math.pow((t - 19.0) / 2.2, 2));
    return parseFloat((base + morningPeak + eveningPeak).toFixed(3));
  }

  function getSyntheticPrice(step) {
    const hour = (step % 96) * 0.25;
    if (hour >= 17.0 && hour < 22.0) return 8.20; // Peak
    if ((hour >= 6.0 && hour < 17.0) || (hour >= 22.0 && hour < 23.5)) return 6.10; // Normal
    return 3.90; // Off-Peak night
  }

  function getSyntheticSolar(step) {
    const t = (step % 96) * 0.25;
    if (t >= 6.0 && t <= 18.0) {
      return parseFloat((2.35 * Math.sin((Math.PI * (t - 6.0)) / 12.0)).toFixed(2));
    }
    return 0.0;
  }

    // ================= 1. COMPONENT METADATA (SYSTEM ARCHITECTURE SPEC) =================
  const COMPONENT_METADATA = {
    renewable_info: {
      type: 'renewable_info', title: 'Renewable Generation', category: 'Generation Input',
      width: 280, height: 95,
      ports: [
        { id: 'renew_out', name: 'PV/Wind Data Out', type: 'data', direction: 'output', side: 'right', x: 280, y: 47 }
      ],
      defaultProps: { id: 'RENEW-RES', name: 'Renewable Generation', source: 'Live Grid Data', status: 'LIVE', solarGw: 1.99, windGw: 2.41, hydroGw: 0.62, totalGw: 5.02, sharePct: 36.5 }
    },
    price_info: {
      type: 'price_info', title: 'Electricity Price', category: 'Market Input',
      width: 280, height: 95,
      ports: [
        { id: 'price_out', name: 'Tariff Signal Out', type: 'data', direction: 'output', side: 'bottom', x: 140, y: 95 }
      ],
      defaultProps: { id: 'PRICE-RTM', name: 'Electricity Price', source: 'IEX RTM', status: 'LIVE', mcp: 8.20, currentBlock: '18:45-19:00', priceState: 'HIGH' }
    },
    ev_info: {
      type: 'ev_info', title: 'EV Information', category: 'Vehicle Telemetry',
      width: 280, height: 95,
      ports: [
        { id: 'ev_info_out', name: 'EV State Out', type: 'data', direction: 'output', side: 'bottom', x: 140, y: 95 },
        { id: 'ev_telemetry_out', name: 'BMS Telemetry Out', type: 'data', direction: 'output', side: 'left', x: 0, y: 47 }
      ],
      defaultProps: { id: 'EV-INFO', name: 'EV Information', soc: 64.2, arrivalTime: '08:00', departureTime: '19:30', requiredSoc: 80.0, v2gEnabled: true, v2gReserve: 30.0 }
    },
    drl: {
      type: 'drl', title: 'DRL CONTROLLER (Agent)', category: 'AI Intelligence',
      width: 280, height: 95,
      ports: [
        { id: 'price_in', name: 'Price In', type: 'data', direction: 'input', side: 'top', x: 140, y: 0 },
        { id: 'renew_in', name: 'Renew In', type: 'data', direction: 'input', side: 'left', x: 0, y: 30 },
        { id: 'grid_telemetry_in', name: 'Grid Telemetry In', type: 'data', direction: 'input', side: 'left', x: 0, y: 65 },
        { id: 'ev_telemetry_in', name: 'EV BMS Telemetry In', type: 'data', direction: 'input', side: 'right', x: 280, y: 20 },
        { id: 'cmd_out', name: 'Power Command Out', type: 'command', direction: 'output', side: 'bottom', x: 140, y: 95 },
        { id: 'decision_out', name: 'Decision Signal Out', type: 'control', direction: 'output', side: 'right', x: 280, y: 55 }
      ],
      defaultProps: { id: 'DRL-01', name: 'DRL CONTROLLER (Agent)', algorithm: 'PPO', action: 'CHARGE', powerKw: 8.4, reward: 0.84, urgencyPct: 42.0, meanReward: 14.82, modelStatus: 'TRAINED (EP 347)' }
    },
    decision_info: {
      type: 'decision_info', title: 'Outputs / Decision', category: 'Policy Output',
      width: 280, height: 95,
      ports: [
        { id: 'decision_in', name: 'Policy In', type: 'control', direction: 'input', side: 'left', x: 0, y: 55 },
        { id: 'ev_in', name: 'EV Telemetry In', type: 'data', direction: 'input', side: 'top', x: 140, y: 0 },
        { id: 'bms_in', name: 'BMS Status In', type: 'data', direction: 'input', side: 'bottom', x: 140, y: 95 }
      ],
      defaultProps: { id: 'DEC-01', name: 'Outputs / Decision', action: 'CHARGE', powerKw: 8.4, reason: 'Departure protection active' }
    },
    grid: {
      type: 'grid', title: 'Electrical Grid (11kV)', category: 'Power Grid',
      width: 280, height: 130,
      ports: [
        { id: 'power_ac_out', name: '11kV AC Bus', type: 'power', direction: 'output', side: 'right', x: 280, y: 65 },
        { id: 'telemetry_out', name: 'Grid Telemetry Out', type: 'data', direction: 'output', side: 'top', x: 140, y: 0 }
      ],
      defaultProps: { id: 'GRID-PHYS', name: 'Electrical Grid', baseDemandGw: 13.74, evImpactKw: 8.40, managedDemandGw: 13.7484 }
    },
    charger: {
      type: 'charger', title: 'Bidirectional EV Charger', category: 'Power Electronics',
      width: 280, height: 130,
      ports: [
        { id: 'ac_terminal', name: 'AC Terminal In/Out', type: 'power', direction: 'input', side: 'left', x: 0, y: 65 },
        { id: 'dc_terminal', name: 'DC Terminal In/Out', type: 'power', direction: 'output', side: 'right', x: 280, y: 65 },
        { id: 'control_in', name: 'Control In', type: 'command', direction: 'input', side: 'top', x: 140, y: 0 }
      ],
      defaultProps: { id: 'CHG-01', name: 'Bidirectional EV Charger', ratedPowerKw: 22.0, powerKw: 8.4, mode: 'CHARGING', direction: 'GRID -> EV', efficiency: 0.95, voltageV: 400.0, currentA: 21.0 }
    },
    battery: {
      type: 'battery', title: 'EV Battery (Integrated Car)', category: 'Energy Storage',
      width: 280, height: 130,
      ports: [
        { id: 'dc_inlet', name: 'DC Fast Charge Inlet', type: 'power', direction: 'input', side: 'left', x: 0, y: 65 },
        { id: 'bms_telemetry_out', name: 'BMS Telemetry Out', type: 'data', direction: 'output', side: 'top', x: 140, y: 0 }
      ],
      defaultProps: { id: 'BATT-01', name: 'EV Battery (Tata Nexon EV)', soc: 64.2, capacityKwh: 72.0, energyStoredKwh: 46.22, minSoc: 20.0, maxSoc: 95.0, voltageV: 400.0, currentA: 21.0, powerKw: 8.4, sohPct: 99.4 }
    },
    meter: {
      type: 'meter', title: 'Digital Energy Meter', category: 'Passive Observation',
      width: 280, height: 85,
      ports: [
        { id: 'sense_tap', name: 'Voltage & Current Sense Tap', type: 'measurement', direction: 'input', side: 'top', x: 105, y: 0 }
      ],
      defaultProps: { id: 'MTR-PASSIVE', name: 'Digital Energy Meter', importPowerKw: 8.40, exportPowerKw: 0.00, netPowerKw: 8.40, importEnergyKwh: 14.82, exportEnergyKwh: 0.00, direction: 'GRID -> EV' }
    }
  };
  // ================= 2. CONNECTION MANAGER =================
  const ConnectionManager = {
    create(source, sPort, target, tPort, meta = {}) {
      const conn = {
        id: meta.id || `conn_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
        sourceComponentId: source.id,
        sourcePortId: sPort.id,
        targetComponentId: target.id,
        targetPortId: tPort.id,
        connectionType: meta.type || 'data',
        label: meta.label || '',
        customPath: meta.customPath || null,
        status: 'ACTIVE'
      };
      connections.push(conn);
      return conn;
    }
  };

  // Absolute Port Position on Canvas
  function getPortWorldCoords(nodeId, portId) {
    const node = nodes.find(n => n.id === nodeId);
    if (!node) return { x: 0, y: 0, side: 'right' };
    const meta = COMPONENT_METADATA[node.type];
    if (!meta) return { x: node.x, y: node.y, side: 'right' };
    const port = meta.ports.find(p => p.id === portId) || meta.ports[0];
    if (!port) return { x: node.x, y: node.y, side: 'right' };

    return {
      x: node.x + port.x,
      y: node.y + port.y,
      side: port.side
    };
  }

  // Orthogonal Wire Path Generator
  function generateOrthogonalPath(p1, p2) {
    const x1 = p1.x;
    const y1 = p1.y;
    const x2 = p2.x;
    const y2 = p2.y;

    if (Math.abs(x1 - x2) < 5) {
      return `M ${x1} ${y1} L ${x2} ${y2}`;
    }
    const midY = (y1 + y2) / 2;
    return `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`;
  }

  // ================= 3. RENDER REALISTIC PHYSICAL WIRES & POWER CABLES =================
  function renderAllWires() {
    if (!canvasSvg) return;

    let svgHtml = `
      <defs>
        <filter id="glow-green" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <filter id="glow-purple" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>
    `;

    connections.forEach(conn => {
      const p1 = getPortWorldCoords(conn.sourceComponentId, conn.sourcePortId);
      const p2 = getPortWorldCoords(conn.targetComponentId, conn.targetPortId);

      let pathD = conn.customPath;
      if (!pathD) {
        pathD = generateOrthogonalPath(p1, p2);
      } else if (typeof pathD === 'function') {
        pathD = pathD(p1, p2);
      }

      // Reverse path for V2G animation (from p2 to p1)
      const reversePathD = `M ${p2.x} ${p2.y} L ${p1.x} ${p1.y}`;
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;

      if (conn.connectionType === 'power') {
        svgHtml += `
          <g class="power-cable-group" id="conn-${conn.id}" data-conn-id="${conn.id}">
            <!-- Layer 1: Outer Heavy Shield Conduit (14px) -->
            <path id="cable-sheath-${conn.id}" d="${pathD}" stroke="#0f172a" stroke-width="14" stroke-linecap="round" fill="none" class="cable-outer-sheath pointer-events-none" />
            <!-- Layer 2: Rubber/XLPE Insulator Jacket (10px) -->
            <path id="cable-insulator-${conn.id}" d="${pathD}" stroke="#334155" stroke-width="10" stroke-linecap="round" fill="none" class="cable-insulator pointer-events-none" />
            <!-- Layer 3: Solid Conductor Core (4px) -->
            <path id="cable-core-${conn.id}" d="${pathD}" stroke="#64748b" stroke-width="4" stroke-linecap="round" fill="none" class="cable-core-idle pointer-events-none" />
            <!-- Layer 4: Forward Particles (Charge: Grid -> Charger -> Battery) -->
            <g id="cable-fwd-${conn.id}" class="pointer-events-none" style="display: none;">
              <path d="${pathD}" stroke="#34d399" stroke-width="5" stroke-dasharray="8 6" fill="none" class="cable-pulse-charge" />
              <circle r="4.5" fill="#34d399" filter="url(#glow-green)">
                <animateMotion path="${pathD}" dur="1.0s" repeatCount="indefinite" />
              </circle>
              <circle r="3" fill="#ffffff">
                <animateMotion path="${pathD}" dur="1.0s" repeatCount="indefinite" />
              </circle>
              <circle r="4.5" fill="#34d399" filter="url(#glow-green)">
                <animateMotion path="${pathD}" dur="1.0s" begin="0.5s" repeatCount="indefinite" />
              </circle>
              <circle r="2.5" fill="#ffffff">
                <animateMotion path="${pathD}" dur="1.0s" begin="0.5s" repeatCount="indefinite" />
              </circle>
            </g>
            <!-- Layer 5: Reverse Particles (V2G Discharge: Battery -> Charger -> Grid) -->
            <g id="cable-rev-${conn.id}" class="pointer-events-none" style="display: none;">
              <path d="${pathD}" stroke="#38bdf8" stroke-width="5" stroke-dasharray="8 6" fill="none" class="cable-pulse-v2g" />
              <circle r="4.5" fill="#38bdf8" filter="url(#glow-cyan)">
                <animateMotion path="${reversePathD}" dur="1.0s" repeatCount="indefinite" />
              </circle>
              <circle r="3" fill="#ffffff">
                <animateMotion path="${reversePathD}" dur="1.0s" repeatCount="indefinite" />
              </circle>
              <circle r="4.5" fill="#38bdf8" filter="url(#glow-cyan)">
                <animateMotion path="${reversePathD}" dur="1.0s" begin="0.5s" repeatCount="indefinite" />
              </circle>
              <circle r="2.5" fill="#ffffff">
                <animateMotion path="${reversePathD}" dur="1.0s" begin="0.5s" repeatCount="indefinite" />
              </circle>
            </g>
            <!-- Heavy-Duty Metallic Cable Glands / Compression Terminals -->
            <circle cx="${p1.x}" cy="${p1.y}" r="6.5" fill="#1e293b" stroke="#f59e0b" stroke-width="2" class="pointer-events-none" />
            <circle cx="${p1.x}" cy="${p1.y}" r="2.5" fill="#e2e8f0" class="pointer-events-none" />
            <circle cx="${p2.x}" cy="${p2.y}" r="6.5" fill="#1e293b" stroke="#f59e0b" stroke-width="2" class="pointer-events-none" />
            <circle cx="${p2.x}" cy="${p2.y}" r="2.5" fill="#e2e8f0" class="pointer-events-none" />
            <!-- Technical Voltage/Power Label -->
            <text id="cable-lbl-${conn.id}" x="${midX}" y="${midY - 12}" fill="#94a3b8" font-family="monospace" font-size="9" font-weight="bold" text-anchor="middle" class="pointer-events-none select-none">${conn.label || ''}</text>
          </g>
        `;
      } else if (conn.connectionType === 'control' || conn.connectionType === 'control_bus') {
        svgHtml += `
          <g class="control-cable-group" id="conn-${conn.id}" data-conn-id="${conn.id}">
            <path d="${pathD}" fill="none" stroke="#a855f7" stroke-width="3" stroke-linecap="round" filter="url(#glow-purple)" class="pointer-events-none control-flow-pulse" stroke-dasharray="6 4" />
            <circle r="3" fill="#e9d5ff">
              <animateMotion path="${pathD}" dur="1.2s" repeatCount="indefinite" />
            </circle>
            <circle cx="${p1.x}" cy="${p1.y}" r="4" fill="#a855f7" class="pointer-events-none" />
            <circle cx="${p2.x}" cy="${p2.y}" r="4" fill="#a855f7" class="pointer-events-none" />
            <text x="${midX + (conn.connectionType === 'control_bus' ? 0 : 45)}" y="${midY + 3}" fill="#c084fc" font-family="monospace" font-size="8.5" font-weight="bold" text-anchor="middle" class="pointer-events-none select-none">${conn.label || ''}</text>
          </g>
        `;
      } else if (conn.connectionType === 'measurement') {
        svgHtml += `
          <g class="meter-tap-group" id="conn-${conn.id}" data-conn-id="${conn.id}">
            <!-- Sensor Tap Wire -->
            <path d="${pathD}" fill="none" stroke="#ec4899" stroke-width="2.5" stroke-dasharray="4 3" class="pointer-events-none meter-flow-pulse" />
            <!-- Measurement Flow Particles down to Meter -->
            <circle r="3" fill="#f472b6" filter="url(#glow-purple)">
              <animateMotion path="${pathD}" dur="0.9s" repeatCount="indefinite" />
            </circle>
            <!-- CT Clamp on the 11kV AC Bus Cable at (355, 322) -->
            <circle cx="355" cy="322" r="7.5" fill="#1e293b" stroke="#ec4899" stroke-width="2.5" class="pointer-events-none" />
            <circle cx="355" cy="322" r="3" fill="#f472b6" class="pointer-events-none" />
            <rect x="349" y="318" width="12" height="8" rx="2" fill="none" stroke="#f472b6" stroke-width="1.5" class="pointer-events-none" />
            <!-- Terminal Gland at Energy Meter (355, 415) -->
            <circle cx="355" cy="415" r="5" fill="#1e293b" stroke="#ec4899" stroke-width="2" class="pointer-events-none" />
            <circle cx="355" cy="415" r="2" fill="#f472b6" class="pointer-events-none" />
            <!-- Technical Measurement Label -->
            <text x="365" y="372" fill="#f472b6" font-family="monospace" font-size="8.5" font-weight="bold" text-anchor="start" class="pointer-events-none select-none">${conn.label || 'CT/PT SENSE TAP'}</text>
          </g>
        `;
      } else {
        let strokeColor = '#38bdf8';
        if (conn.connectionType === 'data_price') strokeColor = '#f59e0b';
        if (conn.connectionType === 'data_renew') strokeColor = '#10b981';
        if (conn.connectionType === 'data_ev') strokeColor = '#c084fc';
        if (conn.connectionType === 'data_grid') strokeColor = '#38bdf8';

        svgHtml += `
          <g class="data-cable-group" id="conn-${conn.id}" data-conn-id="${conn.id}">
            <path d="${pathD}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-dasharray="4 4" opacity="0.85" class="pointer-events-none data-flow-pulse" />
            <circle r="2.5" fill="${strokeColor}">
              <animateMotion path="${pathD}" dur="1.8s" repeatCount="indefinite" />
            </circle>
            <circle cx="${p1.x}" cy="${p1.y}" r="3" fill="${strokeColor}" class="pointer-events-none" />
            <circle cx="${p2.x}" cy="${p2.y}" r="3" fill="${strokeColor}" class="pointer-events-none" />
            ${conn.label ? `<text x="${midX}" y="${midY - 8}" fill="${strokeColor}" font-family="monospace" font-size="8" font-weight="bold" text-anchor="middle" class="pointer-events-none select-none">${conn.label}</text>` : ''}
          </g>
        `;
      }
    });

    canvasSvg.innerHTML = svgHtml;
  }

  // Live in-place SVG wire updater (No DOM re-creation, preserving SMIL animation loop)
  function updateWiresLiveState(pwrKw) {
    const isCharging = (pwrKw > 0.05);
    const isDischarging = (pwrKw < -0.05);

    ['grid_to_charger', 'charger_to_battery'].forEach(cid => {
      const core = document.getElementById('cable-core-' + cid);
      const fwd = document.getElementById('cable-fwd-' + cid);
      const rev = document.getElementById('cable-rev-' + cid);
      const lbl = document.getElementById('cable-lbl-' + cid);

      if (core) {
        core.setAttribute('class', isCharging ? 'cable-core-charging pointer-events-none' : (isDischarging ? 'cable-core-v2g pointer-events-none' : 'cable-core-idle pointer-events-none'));
        if (isCharging) {
          core.setAttribute('stroke', '#10b981');
          core.setAttribute('stroke-width', '4.5');
        } else if (isDischarging) {
          core.setAttribute('stroke', '#38bdf8');
          core.setAttribute('stroke-width', '4.5');
        } else {
          core.setAttribute('stroke', '#64748b');
          core.setAttribute('stroke-width', '4');
        }
      }
      if (fwd) {
        fwd.style.display = isCharging ? 'inline' : 'none';
      }
      if (rev) {
        rev.style.display = isDischarging ? 'inline' : 'none';
      }
      if (lbl) {
        const baseName = cid === 'grid_to_charger' ? '11 kV AC BUS' : '400V DC POWER BUS';
        if (isCharging) {
          const flowDir = cid === 'grid_to_charger' ? 'GRID -> CHG' : 'CHG -> BAT';
          lbl.textContent = `${baseName} [${flowDir} +${pwrKw.toFixed(1)} kW]`;
          lbl.setAttribute('fill', '#34d399');
        } else if (isDischarging) {
          const flowDir = cid === 'grid_to_charger' ? 'CHG -> GRID' : 'BAT -> CHG';
          lbl.textContent = `${baseName} [${flowDir} -${Math.abs(pwrKw).toFixed(1)} kW]`;
          lbl.setAttribute('fill', '#38bdf8');
        } else {
          lbl.textContent = `${baseName} [IDLE 0.0 kW]`;
          lbl.setAttribute('fill', '#94a3b8');
        }
      }
    });
  }

  // ================= 4. AUTHENTIC 50/50 ENGINEERING COMPONENT CARDS =================
  function renderComponentHtml(node) {
    const meta = COMPONENT_METADATA[node.type];
    const props = node.props;
    const isSelected = selectedNodeId === node.id;
    let bodyHtml = '';

    // 1. Renewable Generation (Upper Left)
    if (node.type === 'renewable_info') {
      bodyHtml = `
        <div class="arch-card-50-50 p-2 h-full border border-emerald-500/40 flex flex-row items-stretch gap-2.5 overflow-hidden select-none ${isSelected ? 'ring-2 ring-emerald-400' : ''}">
          <div class="w-[95px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center p-1 relative">
            <img src="assets/components/renewable/renewable-system.svg" class="w-full h-full object-contain pointer-events-none" alt="Renewables" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-emerald-500/30 text-emerald-300 font-bold border border-emerald-500/40">RES</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-emerald-500/20 pb-1">
              <span class="font-bold text-xs text-emerald-300 truncate">Renewables</span>
              <span class="text-[9px] px-1 py-0.2 rounded font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">LIVE</span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-0.5">
              <div class="flex justify-between"><span class="text-slate-400">Total:</span><span id="card-val-renew-total" class="font-bold text-emerald-300">${(telemetryState.renewableTotalGw || 5.02).toFixed(2)} GW</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Solar:</span><span id="card-val-renew-solar" class="text-slate-200">${(telemetryState.solarGw || 1.99).toFixed(2)} GW</span></div>
              <div class="flex justify-between text-[9px] text-slate-400"><span id="card-val-renew-wind">Wind: ${(telemetryState.windGw || 2.41).toFixed(2)} GW</span><span id="card-val-renew-pct" class="text-cyan-400">${(telemetryState.renewableSharePct || 36.5).toFixed(1)}%</span></div>
            </div>
          </div>
        </div>
      `;
    }

    // 2. Electricity Price (Upper Center)
    else if (node.type === 'price_info') {
      bodyHtml = `
        <div class="arch-card-50-50 p-2 h-full border border-amber-500/40 flex flex-row items-stretch gap-2.5 overflow-hidden select-none ${isSelected ? 'ring-2 ring-amber-400' : ''}">
          <div class="w-[95px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center p-1 relative">
            <img src="assets/components/price/electricity-market.svg" class="w-full h-full object-contain pointer-events-none" alt="Price" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-amber-500/30 text-amber-300 font-bold border border-amber-500/40">RTM</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-amber-500/20 pb-1">
              <span class="font-bold text-xs text-amber-300 truncate">Market Price</span>
              <span id="card-val-price-state" class="text-[9px] px-1 py-0.2 rounded font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">${telemetryState.priceState || 'HIGH'}</span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-0.5">
              <div class="flex justify-between"><span class="text-slate-400">MCP:</span><span id="card-val-price-mcp" class="font-bold text-amber-300">Rs.${(telemetryState.marketPrice || 8.20).toFixed(2)}/kWh</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Block:</span><span id="card-val-price-block" class="text-slate-200">${telemetryState.marketBlock || '18:45-19:00'}</span></div>
              <div class="flex justify-between text-[9px] text-slate-500"><span>IEX RTM</span><span class="text-emerald-400">Authoritative</span></div>
            </div>
          </div>
        </div>
      `;
    }

    // 3. EV Information (Upper Right)
    else if (node.type === 'ev_info') {
      bodyHtml = `
        <div class="arch-card-50-50 p-2 h-full border border-purple-500/40 flex flex-row items-stretch gap-2.5 overflow-hidden select-none ${isSelected ? 'ring-2 ring-purple-400' : ''}">
          <div class="w-[95px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center p-1 relative">
            <img src="assets/components/ev/electric-vehicle.svg" class="w-full h-full object-contain pointer-events-none" alt="EV Info" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-purple-500/30 text-purple-300 font-bold border border-purple-500/40">EV</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-purple-500/20 pb-1">
              <span class="font-bold text-xs text-purple-300 truncate">EV Information</span>
              <span class="text-[9px] px-1 py-0.2 rounded font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">CONNECTED</span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-0.5">
              <div class="flex justify-between"><span class="text-slate-400">Current SOC:</span><span id="card-val-ev-soc" class="font-bold text-emerald-400">${(telemetryState.evSoc || 64.2).toFixed(1)}%</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Target SOC:</span><span id="card-val-ev-tgt" class="font-bold text-amber-300">${(telemetryState.evRequiredSoc || 80.0).toFixed(1)}%</span></div>
              <div class="flex justify-between text-[9px] text-slate-400"><span id="card-val-ev-dep">Dep: ${telemetryState.evDepartureTime || '19:30'}</span><span class="text-purple-300">Min: 30%</span></div>
            </div>
          </div>
        </div>
      `;
    }

    // 4. DRL Controller (Middle Center)
    else if (node.type === 'drl') {
      const act = telemetryState.chargerPowerKw !== undefined ? telemetryState.chargerPowerKw : 0.0;
      const isChg = act > 0.05;
      const isDis = act < -0.05;
      const actName = telemetryState.drlAction || (isChg ? 'CHARGE' : (isDis ? 'V2G' : 'IDLE'));
      bodyHtml = `
        <div class="arch-card-50-50 p-2 h-full border border-blue-500/40 flex flex-row items-stretch gap-2.5 overflow-hidden select-none ${isSelected ? 'ring-2 ring-blue-400' : ''}">
          <div class="w-[95px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center p-1 relative">
            <img src="assets/components/controller/drl-controller.svg" class="w-full h-full object-contain pointer-events-none" alt="DRL Controller" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-blue-500/30 text-blue-300 font-bold border border-blue-500/40">AI</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-blue-500/20 pb-1">
              <span class="font-bold text-xs text-blue-300 truncate">DRL Controller</span>
              <span class="text-[9px] px-1 py-0.2 rounded font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">PPO AGENT</span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-0.5">
              <div class="flex justify-between"><span class="text-slate-400">Action:</span><span id="card-val-drl-action" class="font-bold ${isDis ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}">${actName}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Command:</span><span id="card-val-drl-cmd" class="font-bold ${isDis ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}">${act >= 0 ? '+' : ''}${act.toFixed(1)} kW</span></div>
              <div class="flex justify-between text-[9px] text-slate-400"><span id="card-val-drl-reward">Reward: +${(telemetryState.drlReward || 0.84).toFixed(2)}</span><span id="card-val-drl-urgency" class="text-amber-300">Urgency: ${(telemetryState.drlUrgencyPct !== undefined ? telemetryState.drlUrgencyPct : 42)}%</span></div>
            </div>
          </div>
        </div>
      `;
    }

    // 5. Outputs / Decision Log (Middle Right)
    else if (node.type === 'decision_info') {
      const act = telemetryState.chargerPowerKw !== undefined ? telemetryState.chargerPowerKw : 0.0;
      const isChg = act > 0.05;
      const isDis = act < -0.05;
      const actName = telemetryState.drlAction || (isChg ? 'CHARGE' : (isDis ? 'V2G' : 'IDLE'));
      const reasonText = telemetryState.decisionReason || (isChg ? 'EV SOC below target; normal charging active' : (isDis ? 'High grid stress; V2G support active' : 'Target reached; standby idle'));
      bodyHtml = `
        <div class="arch-card-50-50 p-2 h-full border border-purple-500/40 flex flex-row items-stretch gap-2.5 overflow-hidden select-none ${isSelected ? 'ring-2 ring-purple-400' : ''}">
          <div class="w-[95px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center p-1 relative">
            <img src="assets/components/decision/decision-system.svg" class="w-full h-full object-contain pointer-events-none" alt="Decision" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-purple-500/30 text-purple-300 font-bold border border-purple-500/40">LOG</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-purple-500/20 pb-1">
              <span class="font-bold text-xs text-purple-300 truncate">Live Decision</span>
              <span class="text-[9px] px-1 py-0.2 rounded font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">ACTIVE</span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-0.5">
              <div class="flex justify-between"><span class="text-slate-400">Decision:</span><span id="card-val-dec-action" class="font-bold ${isDis ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}">${actName}</span></div>
              <div id="card-val-dec-reason" class="text-[9px] text-slate-300 truncate" title="${reasonText}">Reason: ${reasonText}</div>
              <div class="flex justify-between text-[9px] text-slate-500 pt-0.5"><span>Safety: Passed</span><span class="text-emerald-400">Feasible</span></div>
            </div>
          </div>
        </div>
      `;
    }

    // 6. Electrical Grid (Left Center - Power Row)
    else if (node.type === 'grid') {
      const baseGw = telemetryState.gridDemandGw !== undefined ? telemetryState.gridDemandGw : 13.74;
      bodyHtml = `
        <div class="arch-card-50-50 p-2.5 h-full border-2 border-sky-500/60 flex flex-row items-stretch gap-3 overflow-hidden select-none ${isSelected ? 'ring-2 ring-sky-400' : ''}">
          <div class="w-[105px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-700/80 flex items-center justify-center p-1 relative shadow-inner">
            <img src="assets/components/grid/grid.svg" class="w-full h-full object-cover pointer-events-none" alt="Electrical Grid Substation" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-sky-500/40 text-sky-200 font-bold border border-sky-400/50">11 kV</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-sky-500/30 pb-1">
              <div class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span class="font-bold text-xs text-sky-200">ELECTRICAL GRID</span>
              </div>
              <span class="text-[9px] font-bold text-emerald-400 bg-emerald-500/20 px-1 rounded border border-emerald-500/30">ONLINE</span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-1">
              <div class="flex justify-between"><span class="text-slate-400">Demand:</span><span id="card-val-grid-demand" class="font-bold text-amber-300 text-[11px]">${baseGw.toFixed(2)} GW</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Supply:</span><span id="card-val-grid-supply" class="text-slate-200">${(telemetryState.gridSupplyGw || 14.20).toFixed(2)} GW</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Frequency:</span><span id="card-val-grid-freq" class="text-emerald-400">${(telemetryState.gridFrequencyHz || 49.96).toFixed(2)} Hz</span></div>
              <div class="flex justify-between text-[9px] text-slate-400 pt-0.5 border-t border-slate-800"><span id="card-val-grid-margin">Margin: +${(telemetryState.gridMarginGw || 0.46).toFixed(2)} GW</span><span class="text-sky-300">KPTCL</span></div>
            </div>
          </div>
        </div>
      `;
    }

    // 7. Bidirectional V2G Charger (Middle Center - Power Row)
    else if (node.type === 'charger') {
      const act = telemetryState.chargerPowerKw !== undefined ? telemetryState.chargerPowerKw : 0.0;
      const isV2G = act < -0.05;
      const isChg = act > 0.05;
      const modeStr = telemetryState.chargerMode || (isV2G ? 'V2G DISCHARGE' : (isChg ? 'G2V CHARGING' : 'IDLE'));
      bodyHtml = `
        <div class="arch-card-50-50 p-2.5 h-full border-2 border-cyan-500/60 flex flex-row items-stretch gap-3 overflow-hidden select-none ${isSelected ? 'ring-2 ring-cyan-400' : ''}">
          <div class="w-[105px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-700/80 flex items-center justify-center p-1 relative shadow-inner">
            <img src="assets/components/charger/v2g-charger.svg" class="w-full h-full object-cover pointer-events-none" alt="V2G Charger" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-cyan-500/40 text-cyan-200 font-bold border border-cyan-400/50">22 kW</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-cyan-500/30 pb-1">
              <span class="font-bold text-xs text-cyan-200">V2G CHARGER</span>
              <span id="card-val-charger-mode" class="text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${isV2G ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' : (isChg ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-slate-800 text-slate-400')}">
                ${modeStr}
              </span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-1">
              <div class="flex justify-between items-baseline"><span class="text-slate-400">Power:</span><span id="card-val-charger-pwr" class="font-bold text-xs ${isV2G ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}">${act >= 0 ? '+' : ''}${act.toFixed(1)} kW</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Efficiency:</span><span class="text-slate-200">95.0% (η)</span></div>
              <div class="flex justify-between"><span class="text-slate-400">AC/DC Bus:</span><span class="text-cyan-300">11kV AC <-> 400V</span></div>
              <div class="flex justify-between text-[9px] text-slate-400 pt-0.5 border-t border-slate-800"><span>Voltage: 400V</span><span class="text-emerald-400">CCS Combo 2</span></div>
            </div>
          </div>
        </div>
      `;
    }

    // 8. EV Integrated Battery (Right Center - Power Row)
    else if (node.type === 'battery') {
      const soc = telemetryState.evSoc !== undefined ? telemetryState.evSoc : 64.2;
      const cap = telemetryState.evCapacityKwh || 72.0;
      const energyStored = ((soc / 100) * cap).toFixed(1);
      const pwr = telemetryState.chargerPowerKw !== undefined ? telemetryState.chargerPowerKw : 0.0;
      const pwrStr = `${pwr >= 0 ? '+' : ''}${pwr.toFixed(1)} kW`;
      const timeTarget = telemetryState.batteryTimeToTargetStr || '00:00:00';
      const stateColor = pwr > 0.05 ? 'text-emerald-400' : (pwr < -0.05 ? 'text-cyan-400' : 'text-slate-400');
      const battState = telemetryState.batteryState || (pwr > 0.05 ? 'CHARGING' : (pwr < -0.05 ? 'V2G' : 'IDLE'));
      bodyHtml = `
        <div class="arch-card-50-50 p-2.5 h-full border-2 border-emerald-500/60 flex flex-row items-stretch gap-3 overflow-hidden select-none ${isSelected ? 'ring-2 ring-emerald-400' : ''}">
          <div class="w-[105px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-700/80 flex items-center justify-center p-1 relative shadow-inner">
            <img src="assets/components/battery/ev-battery.svg" class="w-full h-full object-cover pointer-events-none" alt="EV Battery Pack" />
            <button onclick="event.stopPropagation(); LabWorkspace.openBatteryModal('${node.id}');" class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-emerald-500/30 text-emerald-300 font-bold border border-emerald-500/40 hover:bg-emerald-500/50">CAD</button>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-emerald-500/30 pb-1">
              <span class="font-bold text-xs text-emerald-200">EV BATTERY</span>
              <span id="card-val-battery-state" class="text-[9px] font-bold ${stateColor}">${battState}</span>
            </div>
            <div class="space-y-1 py-1">
              <div class="flex justify-between items-baseline">
                <span class="text-slate-400 text-[10px]">SOC: <strong id="card-val-battery-soc" class="text-emerald-400 text-xs font-bold">${soc.toFixed(1)}%</strong></span>
                <span class="text-slate-300 text-[10px]"><strong id="card-val-battery-energy">${energyStored}</strong> / ${cap} kWh</span>
              </div>
              <div class="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-slate-700">
                <div id="card-val-battery-bar" class="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full transition-all duration-300" style="width: ${Math.min(100, Math.max(0, soc))}%"></div>
              </div>
              <div class="flex justify-between text-[9px] text-slate-300 pt-0.5 border-t border-slate-800">
                <span>Power: <strong id="card-val-battery-pwr" class="${stateColor}">${pwrStr}</strong></span>
                <span>To Target: <strong id="card-val-battery-target" class="text-cyan-300">${timeTarget}</strong></span>
              </div>
            </div>
          </div>
        </div>
      `;
    }

    // 9. Digital Energy Meter (Observation Row)
    else if (node.type === 'meter') {
      const impKw = telemetryState.meterImportKw !== undefined ? telemetryState.meterImportKw : 0.0;
      const expKw = telemetryState.meterExportKw !== undefined ? telemetryState.meterExportKw : 0.0;
      const netKw = telemetryState.meterNetKw !== undefined ? telemetryState.meterNetKw : 0.0;
      const impKwh = telemetryState.meterImportKwh !== undefined ? telemetryState.meterImportKwh : 0.0;
      bodyHtml = `
        <div class="arch-card-50-50 p-2 h-full border border-pink-500/50 flex flex-row items-stretch gap-2.5 overflow-hidden select-none ${isSelected ? 'ring-2 ring-pink-400' : ''}">
          <div class="w-[95px] shrink-0 rounded-lg overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center p-1 relative">
            <img src="assets/components/meter/energy-meter.svg" class="w-full h-full object-contain pointer-events-none" alt="Energy Meter" />
            <span class="absolute bottom-1 right-1 text-[8px] font-mono px-1 rounded bg-pink-500/30 text-pink-300 font-bold border border-pink-500/40">TAP</span>
          </div>
          <div class="flex-1 flex flex-col justify-between py-0.5 font-mono text-[10px] leading-tight min-w-0">
            <div class="flex items-center justify-between border-b border-pink-500/20 pb-1">
              <span class="font-bold text-xs text-pink-300 truncate">Energy Meter</span>
              <span class="text-[9px] px-1 py-0.2 rounded font-bold bg-pink-500/20 text-pink-300 border border-pink-500/30">MONITOR</span>
            </div>
            <div class="space-y-0.5 text-slate-300 py-0.5">
              <div class="flex justify-between"><span class="text-slate-400">Import:</span><span id="card-val-meter-import" class="text-emerald-400 font-bold">${impKw.toFixed(1)} kW</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Export:</span><span id="card-val-meter-export" class="text-cyan-400 font-bold">${expKw.toFixed(1)} kW</span></div>
              <div class="flex justify-between text-[9px] text-slate-400"><span>Net: <strong id="card-val-meter-net">${netKw >= 0 ? '+' : ''}${netKw.toFixed(1)} kW</strong></span><span id="card-val-meter-impkwh" class="text-slate-200">Imp: ${impKwh.toFixed(2)} kWh</span></div>
            </div>
          </div>
        </div>
      `;
    }

    return `
      <div id="node-${node.id}" class="sim-node is-fixed absolute cursor-pointer select-none transition-all duration-200" style="left: ${node.x}px; top: ${node.y}px; width: ${meta.width}px; height: ${meta.height}px;" data-node-id="${node.id}">
        ${bodyHtml}
      </div>
    `;
  }

  // In-place node DOM updater (avoids rebuilding innerHTML on every tick)
  function updateNodesLiveValues(data) {
    // 1. Renewable
    const rTot = document.getElementById('card-val-renew-total');
    const rSol = document.getElementById('card-val-renew-solar');
    const rWnd = document.getElementById('card-val-renew-wind');
    const rPct = document.getElementById('card-val-renew-pct');
    if (rTot) rTot.textContent = `${(telemetryState.renewableTotalGw || 5.02).toFixed(2)} GW`;
    if (rSol) rSol.textContent = `${(telemetryState.solarGw || 1.99).toFixed(2)} GW`;
    if (rWnd) rWnd.textContent = `Wind: ${(telemetryState.windGw || 2.41).toFixed(2)} GW`;
    if (rPct) rPct.textContent = `${(telemetryState.renewableSharePct || 36.5).toFixed(1)}%`;

    // 2. Market Price
    const pState = document.getElementById('card-val-price-state');
    const pMcp = document.getElementById('card-val-price-mcp');
    const pBlk = document.getElementById('card-val-price-block');
    if (pState) pState.textContent = telemetryState.priceState || 'HIGH';
    if (pMcp) pMcp.textContent = `Rs.${(telemetryState.marketPrice || 8.20).toFixed(2)}/kWh`;
    if (pBlk) pBlk.textContent = telemetryState.marketBlock || '18:45-19:00';

    // 3. EV Info
    const evSoc = document.getElementById('card-val-ev-soc');
    const evTgt = document.getElementById('card-val-ev-tgt');
    const evDep = document.getElementById('card-val-ev-dep');
    if (evSoc) evSoc.textContent = `${(telemetryState.evSoc || 64.2).toFixed(1)}%`;
    if (evTgt) evTgt.textContent = `${(telemetryState.evRequiredSoc || 80.0).toFixed(1)}%`;
    if (evDep) evDep.textContent = `Dep: ${telemetryState.evDepartureTime || '19:30'}`;

    // 4. DRL Controller
    const act = telemetryState.chargerPowerKw !== undefined ? telemetryState.chargerPowerKw : 0.0;
    const isChg = act > 0.05;
    const isDis = act < -0.05;
    const actName = telemetryState.drlAction || (isChg ? 'CHARGE' : (isDis ? 'V2G' : 'IDLE'));
    const drlAct = document.getElementById('card-val-drl-action');
    const drlCmd = document.getElementById('card-val-drl-cmd');
    const drlRew = document.getElementById('card-val-drl-reward');
    const drlUrg = document.getElementById('card-val-drl-urgency');
    if (drlAct) {
      drlAct.textContent = actName;
      drlAct.className = `font-bold ${isDis ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}`;
    }
    if (drlCmd) {
      drlCmd.textContent = `${act >= 0 ? '+' : ''}${act.toFixed(1)} kW`;
      drlCmd.className = `font-bold ${isDis ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}`;
    }
    if (drlRew) drlRew.textContent = `Reward: +${(telemetryState.drlReward || 0.84).toFixed(2)}`;
    if (drlUrg) drlUrg.textContent = `Urgency: ${telemetryState.drlUrgencyPct !== undefined ? telemetryState.drlUrgencyPct : 42}%`;

    // 5. Decision Output
    const decAct = document.getElementById('card-val-dec-action');
    const decRsn = document.getElementById('card-val-dec-reason');
    const reasonText = telemetryState.decisionReason || (isChg ? 'EV SOC below target; normal charging active' : (isDis ? 'High grid stress; V2G support active' : 'Target reached; standby idle'));
    if (decAct) {
      decAct.textContent = actName;
      decAct.className = `font-bold ${isDis ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}`;
    }
    if (decRsn) {
      decRsn.textContent = `Reason: ${reasonText}`;
      decRsn.title = reasonText;
    }

    // 6. Grid
    const gDem = document.getElementById('card-val-grid-demand');
    const gSup = document.getElementById('card-val-grid-supply');
    const gFrq = document.getElementById('card-val-grid-freq');
    const gMrg = document.getElementById('card-val-grid-margin');
    if (gDem) gDem.textContent = `${(telemetryState.gridDemandGw !== undefined ? telemetryState.gridDemandGw : 13.74).toFixed(2)} GW`;
    if (gSup) gSup.textContent = `${(telemetryState.gridSupplyGw || 14.20).toFixed(2)} GW`;
    if (gFrq) gFrq.textContent = `${(telemetryState.gridFrequencyHz || 49.96).toFixed(2)} Hz`;
    if (gMrg) gMrg.textContent = `Margin: +${(telemetryState.gridMarginGw || 0.46).toFixed(2)} GW`;

    // 7. Charger
    const cMode = document.getElementById('card-val-charger-mode');
    const cPwr = document.getElementById('card-val-charger-pwr');
    const modeStr = telemetryState.chargerMode || (isDis ? 'V2G DISCHARGE' : (isChg ? 'G2V CHARGING' : 'IDLE'));
    if (cMode) {
      cMode.textContent = modeStr;
      cMode.className = `text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${isDis ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' : (isChg ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-slate-800 text-slate-400')}`;
    }
    if (cPwr) {
      cPwr.textContent = `${act >= 0 ? '+' : ''}${act.toFixed(1)} kW`;
      cPwr.className = `font-bold text-xs ${isDis ? 'text-cyan-400' : (isChg ? 'text-emerald-400' : 'text-slate-400')}`;
    }

    // 8. Battery
    const soc = telemetryState.evSoc !== undefined ? telemetryState.evSoc : 64.2;
    const cap = telemetryState.evCapacityKwh || 72.0;
    const energyStored = ((soc / 100) * cap).toFixed(1);
    const pwrStr = `${act >= 0 ? '+' : ''}${act.toFixed(1)} kW`;
    const timeTarget = telemetryState.batteryTimeToTargetStr || '00:00:00';
    const stateColor = act > 0.05 ? 'text-emerald-400' : (act < -0.05 ? 'text-cyan-400' : 'text-slate-400');
    const battState = telemetryState.batteryState || (act > 0.05 ? 'CHARGING' : (act < -0.05 ? 'V2G' : 'IDLE'));

    const bState = document.getElementById('card-val-battery-state');
    const bSoc = document.getElementById('card-val-battery-soc');
    const bEnergy = document.getElementById('card-val-battery-energy');
    const bBar = document.getElementById('card-val-battery-bar');
    const bPwr = document.getElementById('card-val-battery-pwr');
    const bTgt = document.getElementById('card-val-battery-target');
    if (bState) {
      bState.textContent = battState;
      bState.className = `text-[9px] font-bold ${stateColor}`;
    }
    if (bSoc) bSoc.textContent = `${soc.toFixed(1)}%`;
    if (bEnergy) bEnergy.textContent = `${energyStored} / ${cap} kWh`;
    if (bBar) bBar.style.width = `${Math.min(100, Math.max(0, soc))}%`;
    if (bPwr) {
      bPwr.textContent = pwrStr;
      bPwr.className = stateColor;
    }
    if (bTgt) bTgt.textContent = timeTarget;

    // 9. Meter
    const impKw = telemetryState.meterImportKw !== undefined ? telemetryState.meterImportKw : 0.0;
    const expKw = telemetryState.meterExportKw !== undefined ? telemetryState.meterExportKw : 0.0;
    const netKw = telemetryState.meterNetKw !== undefined ? telemetryState.meterNetKw : 0.0;
    const impKwh = telemetryState.meterImportKwh !== undefined ? telemetryState.meterImportKwh : 0.0;

    const mImp = document.getElementById('card-val-meter-import');
    const mExp = document.getElementById('card-val-meter-export');
    const mNet = document.getElementById('card-val-meter-net');
    const mKwh = document.getElementById('card-val-meter-impkwh');
    if (mImp) mImp.textContent = `${impKw.toFixed(1)} kW`;
    if (mExp) mExp.textContent = `${expKw.toFixed(1)} kW`;
    if (mNet) mNet.textContent = `${netKw >= 0 ? '+' : ''}${netKw.toFixed(1)} kW`;
    if (mKwh) mKwh.textContent = `Imp: ${impKwh.toFixed(2)} kWh`;
  }

  // ================= 5. RENDER ALL NODES =================
  function renderAllNodes() {
    if (!nodesContainer) return;
    let html = '';
    nodes.forEach(n => {
      html += renderComponentHtml(n);
    });
    nodesContainer.innerHTML = html;

    // Attach click selection listeners
    nodesContainer.querySelectorAll('.sim-node').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const nid = el.getAttribute('data-node-id');
        selectNode(nid);
      });
    });
  }

  // ================= 6. 5-TAB CONTEXTUAL INSPECTOR =================
  function selectNode(nodeId) {
    selectedNodeId = nodeId;
    renderAllNodes();
    renderInspector();
  }

  function setInspectorTab(tabName) {
    activeInspectorTab = tabName;
    renderInspector();
  }

  function renderInspector() {
    if (!inspectorContent) return;

    const node = nodes.find(n => n.id === selectedNodeId) || nodes[0];
    if (!node) {
      inspectorContent.innerHTML = `
        <div class="p-6 text-center text-slate-500 font-mono text-xs">
          Click any architecture component on the canvas to inspect its parameters and telemetry.
        </div>
      `;
      return;
    }

    const meta = COMPONENT_METADATA[node.type];
    const props = node.props;

    // Build Tab Navigation Header
    const tabs = ['overview', 'parameters', 'telemetry', 'connections', 'source'];
    let tabNavHtml = `
      <div class="flex items-center gap-1 p-2 border-b border-slate-200 dark:border-slate-800 bg-slate-100/70 dark:bg-slate-950/60 overflow-x-auto no-scrollbar">
        ${tabs.map(t => `
          <button onclick="LabWorkspace.setInspectorTab('${t}')" class="insp-tab-btn capitalize ${activeInspectorTab === t ? 'active' : ''}">
            ${t}
          </button>
        `).join('')}
      </div>
    `;

    // Tab 1: Overview
    let tabBodyHtml = '';
    if (activeInspectorTab === 'overview') {
      tabBodyHtml = renderInspectorOverviewTab(node);
    } else if (activeInspectorTab === 'parameters') {
      tabBodyHtml = renderInspectorParametersTab(node);
    } else if (activeInspectorTab === 'telemetry') {
      tabBodyHtml = renderInspectorTelemetryTab(node);
    } else if (activeInspectorTab === 'connections') {
      tabBodyHtml = renderInspectorConnectionsTab(node);
    } else if (activeInspectorTab === 'source') {
      tabBodyHtml = renderInspectorSourceTab(node);
    }

    inspectorContent.innerHTML = `
      <div class="flex flex-col h-full font-mono">
        <!-- Component Header -->
        <div class="p-3.5 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 flex items-start justify-between">
          <div>
            <span class="text-[9px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">${meta.category}</span>
            <h3 class="text-sm font-bold text-slate-800 dark:text-slate-100">${props.name || meta.title}</h3>
          </div>
          <span class="px-2 py-0.5 rounded text-[9px] bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 font-bold">${props.id}</span>
        </div>

        <!-- 5 Tabs Bar -->
        ${tabNavHtml}

        <!-- Tab Body Content -->
        <div class="flex-1 overflow-y-auto p-3.5 space-y-3">
          ${isEditMode ? `
            <div class="p-2.5 rounded-lg bg-amber-500/15 border border-amber-500/40 text-amber-300 text-[11px] flex items-center gap-2">
              <span class="material-symbols-outlined text-base">edit</span>
              <span><strong>EDIT MODE ACTIVE:</strong> You may modify parameters below. System topology remains safely locked.</span>
            </div>
          ` : ''}
          ${tabBodyHtml}
        </div>
      </div>
    `;
  }

  // --- Tab 1: Overview Helper ---
  function renderInspectorOverviewTab(node) {
    const props = node.props;
    if (node.type === 'grid' || node.type === 'grid_info') {
      return `
        <div class="space-y-3 text-xs">
          <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2">
            <div class="flex justify-between"><span class="text-slate-400">Live Grid Demand:</span><span class="text-amber-400 font-bold">${telemetryState.gridDemandGw.toFixed(2)} GW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Available Supply:</span><span class="text-slate-200">${telemetryState.gridSupplyGw.toFixed(2)} GW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Operating Reserve:</span><span class="text-emerald-400 font-bold">+${telemetryState.gridMarginGw.toFixed(2)} GW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Frequency:</span><span class="text-slate-200">${telemetryState.gridFrequencyHz} Hz</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Nominal Voltage:</span><span class="text-slate-200">11.0 kV / 400V</span></div>
          </div>
          <div class="p-3 bg-indigo-950/30 rounded-xl border border-indigo-500/30 space-y-1.5 text-[11px]">
            <span class="font-bold text-indigo-300 block">Digital Twin Feedback Isolation</span>
            <p class="text-slate-400 leading-relaxed">External grid demand is measured from KPTCL SLDC. Local EV charging (+8.4 kW) or V2G (-10 kW) is isolated as Managed Feeder Impact without overwriting state-wide telemetry.</p>
          </div>
        </div>
      `;
    } else if (node.type === 'price_info') {
      return `
        <div class="space-y-3 text-xs">
          <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2">
            <div class="flex justify-between"><span class="text-slate-400">Market Price (MCP):</span><span class="text-emerald-400 font-bold">Rs.${telemetryState.marketPrice.toFixed(2)} / kWh</span></div>
            <div class="flex justify-between"><span class="text-slate-400">15-min Time Block:</span><span class="text-slate-200">${telemetryState.marketBlock}</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Tariff State:</span><span class="text-rose-400 font-bold">${telemetryState.priceState}</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Market Type:</span><span class="text-slate-300">IEX Real-Time Market (RTM)</span></div>
          </div>
        </div>
      `;
    } else if (node.type === 'renewable_info') {
      return `
        <div class="space-y-3 text-xs">
          <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2">
            <div class="flex justify-between"><span class="text-slate-400">Total Renewable:</span><span class="text-cyan-400 font-bold">${telemetryState.renewableTotalGw.toFixed(2)} GW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Solar PV:</span><span class="text-emerald-400 font-bold">${telemetryState.solarGw.toFixed(2)} GW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Wind Generation:</span><span class="text-slate-200 font-bold">${telemetryState.windGw.toFixed(2)} GW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Renewable Share:</span><span class="text-emerald-400 font-bold">${telemetryState.renewableSharePct.toFixed(1)}%</span></div>
          </div>
        </div>
      `;
    } else if (node.type === 'drl' || node.type === 'decision_info') {
      const modeColor = telemetryState.chargerMode === 'V2G' ? 'text-cyan-600 dark:text-cyan-400' : (telemetryState.chargerMode === 'CHARGING' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400');
      const isConfirmed = telemetryState.isHighLoadConfirmed;
      return `
        <div class="space-y-3 text-xs">
          <div class="p-3 bg-white dark:bg-slate-950/70 rounded-xl border border-slate-200 dark:border-slate-800 space-y-2 shadow-sm">
            <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Policy:</span><span class="text-purple-600 dark:text-purple-300 font-bold">PPO + Safety Layer</span></div>
            <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Current Mode:</span><span class="${modeColor} font-bold">${telemetryState.chargerMode || 'CHARGING'}</span></div>
            <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Active Power:</span><span class="text-amber-600 dark:text-amber-300 font-bold">${telemetryState.chargerPowerKw >= 0 ? '+' : ''}${telemetryState.chargerPowerKw.toFixed(1)} kW</span></div>
            <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Decision Reason:</span><span class="text-slate-700 dark:text-slate-200 truncate" title="${telemetryState.decisionReason || ''}">${telemetryState.decisionReason || 'EV SOC below target; normal charging active'}</span></div>
          </div>

          <!-- Section 57: Control Diagnostics Panel (2-column layout) -->
          <div class="p-3 bg-white dark:bg-slate-900/90 rounded-xl border border-purple-500/30 space-y-2 text-[11px] shadow-sm">
            <div class="flex items-center justify-between border-b border-purple-500/20 pb-1.5">
              <span class="font-bold text-purple-600 dark:text-purple-300 flex items-center gap-1">
                <span class="material-symbols-outlined text-sm">tune</span>
                CONTROL DIAGNOSTICS
              </span>
              <span class="text-[9px] text-cyan-600 dark:text-cyan-400 font-bold font-mono">NEXT EVAL: ${telemetryState.nextControlEvalSec || 10}s</span>
            </div>
            <div class="grid grid-cols-2 gap-2 pt-1">
              <div class="p-2 rounded-lg bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800">
                <span class="text-slate-500 dark:text-slate-400 text-[10px] block">Grid Stress</span>
                <span class="font-bold ${(telemetryState.gridStressScore || 42) >= 75 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'} text-xs">${Math.round(telemetryState.gridStressScore || 42)} / 100</span>
              </div>
              <div class="p-2 rounded-lg bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800">
                <span class="text-slate-500 dark:text-slate-400 text-[10px] block">Departure Urgency</span>
                <span class="font-bold ${(telemetryState.drlUrgencyPct || 42) >= 65 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-700 dark:text-slate-200'} text-xs">${(telemetryState.drlUrgencyPct || 42).toFixed(0)}%</span>
              </div>
            </div>
            <div class="space-y-1.5 pt-1 text-[11px]">
              <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">V2G Entry Threshold:</span><span class="text-amber-600 dark:text-amber-400 font-bold">>= ${telemetryState.v2gEntryStress || 75}</span></div>
              <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">V2G Exit Threshold:</span><span class="text-cyan-600 dark:text-cyan-400 font-bold"><= ${telemetryState.v2gExitStress || 60}</span></div>
              <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">High Load Gating:</span><span class="${isConfirmed ? 'text-rose-600 dark:text-rose-400 font-bold' : 'text-slate-600 dark:text-slate-300'}">${isConfirmed ? 'CONFIRMED (30s)' : `${Math.round(telemetryState.highLoadCandidateSec || 0)} / 30s`}</span></div>
              <div class="flex justify-between"><span class="text-slate-500 dark:text-slate-400">Minimum Mode Hold:</span><span class="text-slate-600 dark:text-slate-300">${telemetryState.modeDwellStr || '05:00'}</span></div>
            </div>
          </div>
        </div>
      `;
    } else if (node.type === 'charger') {
      return `
        <div class="space-y-3 text-xs">
          <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2">
            <div class="flex justify-between"><span class="text-slate-400">Operating Mode:</span><span class="text-cyan-400 font-bold">${telemetryState.chargerMode}</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Rated Power:</span><span class="text-slate-200">${telemetryState.chargerRatedKw.toFixed(1)} kW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Active Power:</span><span class="text-emerald-400 font-bold">${telemetryState.chargerPowerKw.toFixed(1)} kW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Inverter Efficiency:</span><span class="text-slate-200">95.0%</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Flow Direction:</span><span class="text-amber-300 font-bold">${telemetryState.meterDirection}</span></div>
          </div>
        </div>
      `;
    } else if (node.type === 'battery' || node.type === 'ev_info') {
      return `
        <div class="space-y-3 text-xs">
          <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2">
            <div class="flex justify-between"><span class="text-slate-400">Current SOC:</span><span class="text-emerald-400 font-bold">${telemetryState.evSoc.toFixed(1)}%</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Pack Capacity:</span><span class="text-slate-200">${telemetryState.evCapacityKwh} kWh</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Target SOC:</span><span class="text-amber-300 font-bold">${telemetryState.evRequiredSoc}% by ${telemetryState.evDepartureTime}</span></div>
            <div class="flex justify-between"><span class="text-slate-400">V2G Reserve Floor:</span><span class="text-slate-200">${telemetryState.evV2gReserve}%</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Health (SOH):</span><span class="text-emerald-400 font-bold">99.4%</span></div>
          </div>
          <button onclick="LabWorkspace.openBatteryModal('${node.id}')" class="w-full py-2 px-3 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-xs font-bold font-mono transition-all flex items-center justify-center gap-1.5">
            <span class="material-symbols-outlined text-base">battery_charging_full</span>
            <span>Open High-Voltage CAD Inspection</span>
          </button>
        </div>
      `;
    } else if (node.type === 'meter') {
      return `
        <div class="space-y-3 text-xs">
          <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2">
            <div class="flex justify-between"><span class="text-slate-400">Import Power:</span><span class="text-emerald-400 font-bold">${telemetryState.meterImportKw.toFixed(2)} kW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Export Power:</span><span class="text-cyan-400 font-bold">${telemetryState.meterExportKw.toFixed(2)} kW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Net Power:</span><span class="text-amber-400 font-bold">+${telemetryState.meterNetKw.toFixed(2)} kW</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Imported Energy:</span><span class="text-slate-200">${telemetryState.meterImportKwh.toFixed(2)} kWh</span></div>
            <div class="flex justify-between"><span class="text-slate-400">Direction:</span><span class="text-emerald-400 font-bold">${telemetryState.meterDirection}</span></div>
          </div>
          <p class="text-[11px] text-slate-400 leading-relaxed">Passive measurement only. Observes the Grid <-> Charger <-> Battery path without series impedance or bottlenecks.</p>
        </div>
      `;
    }
    return `<div class="p-3 text-xs text-slate-400">Component overview ready.</div>`;
  }

  // --- Tab 2: Parameters Helper (PRD Section 18-23, 59) ---
  function renderInspectorParametersTab(node) {
    const props = node.props;
    const editable = isEditMode;

    if (node.type === 'ev_info' || node.type === 'battery') {
      return `
        <div class="space-y-2.5 text-xs font-mono">
          <div>
            <label class="text-[10px] text-slate-400">Arrival Time</label>
            <input type="time" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.arrivalTime || '08:00'}" data-prop="arrivalTime"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">Departure Time</label>
            <input type="time" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.departureTime || '19:30'}" data-prop="departureTime"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">Battery Capacity (kWh)</label>
            <input type="number" step="1" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.capacityKwh || props.batteryCapacityKwh || 72}" data-prop="capacityKwh"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">Required Departure SOC (%)</label>
            <input type="number" step="1" min="20" max="100" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.requiredSoc || 80}" data-prop="requiredSoc"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">V2G Reserve Floor SOC (%)</label>
            <input type="number" step="1" min="10" max="60" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.v2gReserve || 30}" data-prop="v2gReserve"/>
          </div>
        </div>
      `;
    } else if (node.type === 'charger') {
      return `
        <div class="space-y-2.5 text-xs font-mono">
          <div>
            <label class="text-[10px] text-slate-400">Rated Power (kW)</label>
            <input type="number" step="1" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.ratedPowerKw || 22}" data-prop="ratedPowerKw"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">Conversion Efficiency (0.80 - 0.99)</label>
            <input type="number" step="0.01" min="0.8" max="0.99" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.efficiency || 0.95}" data-prop="efficiency"/>
          </div>
        </div>
      `;
    } else if (node.type === 'price_info') {
      return `
        <div class="space-y-2.5 text-xs font-mono">
          <div>
            <label class="text-[10px] text-slate-400">Tariff Threshold (Rs./kWh)</label>
            <input type="number" step="0.1" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.mcp || 8.20}" data-prop="mcp"/>
          </div>
        </div>
      `;
    } else if (node.type === 'drl' || node.type === 'decision_info') {
      return `
        <div class="space-y-2.5 text-xs font-mono">
          <div>
            <label class="text-[10px] text-slate-400">V2G Entry Stress Threshold (0-100)</label>
            <input type="number" step="1" min="50" max="95" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${telemetryState.v2gEntryStress || 75}" data-prop="v2g_entry_stress"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">V2G Exit Hysteresis Threshold (0-100)</label>
            <input type="number" step="1" min="30" max="75" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${telemetryState.v2gExitStress || 60}" data-prop="v2g_exit_stress"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">High-Load Confirmation Time (seconds)</label>
            <input type="number" step="5" min="5" max="120" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.highLoadConfirmationSec || 30}" data-prop="high_load_confirmation_time_sec"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">Minimum Mode Dwell Time (seconds)</label>
            <input type="number" step="30" min="30" max="600" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.minimumChargeHoldSec || 300}" data-prop="minimum_charge_hold_sec"/>
          </div>
          <div>
            <label class="text-[10px] text-slate-400">Power Ramp Rate (kW/second)</label>
            <input type="number" step="0.5" min="0.5" max="5.0" class="insp-input w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-slate-100 ${!editable ? 'opacity-60 pointer-events-none' : ''}" value="${props.rampRateKwPerSec || 1.0}" data-prop="ramp_rate_kw_per_sec"/>
          </div>
        </div>
      `;
    }
    return `
      <div class="p-3 text-xs text-slate-400 font-mono">
        ${editable ? 'Modify component attributes above. Topology remains locked.' : 'Parameters view-only. Click [EDIT] in toolbar to enable parameter edits.'}
      </div>
    `;
  }

  // --- Tab 3: Telemetry Helper ---
  function renderInspectorTelemetryTab(node) {
    return `
      <div class="p-3 bg-slate-950/80 rounded-xl border border-slate-800 text-xs font-mono space-y-1.5">
        <div class="flex justify-between"><span class="text-slate-400">Stream Status:</span><span class="text-emerald-400 font-bold">ACTIVE</span></div>
        <div class="flex justify-between"><span class="text-slate-400">Bus Voltage:</span><span class="text-slate-200">400.0 V</span></div>
        <div class="flex justify-between"><span class="text-slate-400">Current:</span><span class="text-slate-200">21.0 A</span></div>
        <div class="flex justify-between"><span class="text-slate-400">Power Factor:</span><span class="text-slate-200">0.99</span></div>
        <div class="flex justify-between"><span class="text-slate-400">Timestamp:</span><span class="text-slate-300">${new Date().toLocaleTimeString()}</span></div>
      </div>
    `;
  }

  // --- Tab 4: Connections Helper (PRD Section 51) ---
  function renderInspectorConnectionsTab(node) {
    return `
      <div class="p-3 bg-slate-950/80 rounded-xl border border-slate-800 text-xs font-mono space-y-2">
        <div class="flex items-center gap-1.5 text-purple-400 font-bold">
          <span class="material-symbols-outlined text-sm">account_tree</span>
          <span>Fixed Topological Relationships</span>
        </div>
        <div class="text-[11px] text-slate-300 space-y-1">
          <div>* Grid <-> Bidirectional Charger (Power Bus)</div>
          <div>* Charger <-> EV Battery (CCS DC Coupling)</div>
          <div>* DRL Agent -> Charger (Power Command)</div>
          <div>* Inputs (Grid, Price, Res, EV) -> DRL Agent</div>
          <div>* Energy Meter: Passive Tap observing 400V link</div>
        </div>
        <span class="text-[10px] text-slate-500 block pt-1 border-t border-slate-800">
          Connections are fixed by the Digital Twin architecture (PRD Section 51).
        </span>
      </div>
    `;
  }

  // --- Tab 5: Source Helper (PRD Section 41, 79) ---
  function renderInspectorSourceTab(node) {
    let sourceName = 'KPTCL SLDC';
    let apiEndpoint = '/api/realtime/grid';
    if (node.type === 'price_info') {
      sourceName = 'Indian Energy Exchange (IEX RTM)';
      apiEndpoint = '/api/realtime/price';
    } else if (node.type === 'renewable_info') {
      sourceName = 'Karnataka SLDC / NIWE Solar-Wind Telemetry';
      apiEndpoint = '/api/realtime/renewables';
    } else if (node.type === 'drl' || node.type === 'decision_info') {
      sourceName = 'PyTorch Gymnasium DRL PPO Engine';
      apiEndpoint = '/api/controller';
    } else if (node.type === 'battery' || node.type === 'ev_info') {
      sourceName = 'Vehicle BMS CAN Bus (400V LFP)';
      apiEndpoint = '/api/ev';
    } else if (node.type === 'meter') {
      sourceName = 'High-Precision Multifunction Energy Transducer';
      apiEndpoint = '/api/meter';
    }

    return `
      <div class="p-3 bg-slate-950/80 rounded-xl border border-slate-800 text-xs font-mono space-y-2">
        <div class="flex justify-between">
          <span class="text-slate-400">Data Source:</span>
          <span class="text-slate-200 font-bold">${sourceName}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-400">Health Status:</span>
          <span class="text-emerald-400 font-bold">o LIVE (Verified)</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-400">Sampling Interval:</span>
          <span class="text-slate-300">1.0 sec</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-400">API Endpoint:</span>
          <span class="text-purple-300 font-mono text-[10px]">${apiEndpoint}</span>
        </div>
      </div>
    `;
  }

  // ================= 7. EDIT MODE TOGGLE & PERSISTENCE =================
  function toggleEditMode() {
    isEditMode = true;
    updateLockUi();
    renderInspector();
    showToast("EDIT MODE: Adjust parameters in inspector. Topology remains locked.", "tune");
  }

  function cancelEditMode() {
    isEditMode = false;
    updateLockUi();
    renderInspector();
    showToast("Edit mode cancelled. Parameters reverted.", "close");
  }

  function saveEditMode() {
    applyInspectorChanges();
    isEditMode = false;
    updateLockUi();
    renderInspector();
    showToast("Parameters saved & applied to digital twin.", "check_circle");
  }

  function updateLockUi() {
    const lockContainer = document.getElementById('arch-lock-container');
    if (!lockContainer) return;

    if (isEditMode) {
      lockContainer.innerHTML = `
        <span class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/20 border border-amber-500/50 text-amber-300 text-xs font-mono font-bold animate-pulse">
          <span class="material-symbols-outlined text-[15px]">edit</span>
          <span>edit EDIT MODE</span>
        </span>
        <button id="tb-save-btn" onclick="LabWorkspace.saveEditMode()" class="flex items-center gap-1 px-3 py-1 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-slate-950 text-xs font-mono font-bold transition-all shadow-sm">
          <span class="material-symbols-outlined text-[15px]">save</span>
          <span>SAVE</span>
        </button>
        <button id="tb-cancel-btn" onclick="LabWorkspace.cancelEditMode()" class="flex items-center gap-1 px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono font-bold transition-all">
          <span class="material-symbols-outlined text-[15px]">close</span>
          <span>CANCEL</span>
        </button>
      `;
    } else {
      lockContainer.innerHTML = `
        <span id="arch-locked-badge" class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs font-mono font-bold">
          <span class="material-symbols-outlined text-[15px] text-amber-400">lock</span>
          <span> ARCHITECTURE LOCKED</span>
        </span>
        <button id="tb-edit-btn" onclick="LabWorkspace.toggleEditMode()" class="flex items-center gap-1 px-3 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-xs font-mono font-bold transition-all shadow-sm" title="Edit simulation parameters without breaking circuit topology.">
          <span class="material-symbols-outlined text-[15px]">tune</span>
          <span>EDIT</span>
        </button>
      `;
    }
  }

  function applyInspectorChanges() {
    if (!inspectorContent) return;
    const inputs = inspectorContent.querySelectorAll('.insp-input');
    inputs.forEach(input => {
      const prop = input.getAttribute('data-prop');
      let val = input.value;
      if (input.type === 'number') val = parseFloat(val);

      // Update active node
      const node = nodes.find(n => n.id === selectedNodeId);
      if (node) node.props[prop] = val;

      // Sync to digital twin state
      if (prop === 'departureTime') telemetryState.evDepartureTime = String(val);
      if (prop === 'requiredSoc') telemetryState.evRequiredSoc = parseFloat(val);
      if (prop === 'capacityKwh') telemetryState.evCapacityKwh = parseFloat(val);
      if (prop === 'v2gReserve') telemetryState.evV2gReserve = parseFloat(val);
      if (prop === 'ratedPowerKw') telemetryState.chargerRatedKw = parseFloat(val);
      if (prop === 'mcp') telemetryState.marketPrice = parseFloat(val);
      if (prop === 'v2g_entry_stress') telemetryState.v2gEntryStress = parseFloat(val);
      if (prop === 'v2g_exit_stress') telemetryState.v2gExitStress = parseFloat(val);
      if (prop === 'high_load_confirmation_time_sec') telemetryState.highLoadConfirmationSec = parseFloat(val);
      if (prop === 'minimum_charge_hold_sec') telemetryState.minimumChargeHoldSec = parseFloat(val);
      if (prop === 'ramp_rate_kw_per_sec') telemetryState.rampRateKwPerSec = parseFloat(val);
    });

    renderAllNodes();
    syncToBackend();
  }

  async function syncToBackend() {
    try {
      await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          data_mode: currentDataMode,
          ev: {
            departure_time: telemetryState.evDepartureTime,
            required_soc: telemetryState.evRequiredSoc,
            capacity_kwh: telemetryState.evCapacityKwh,
            v2g_reserve: telemetryState.evV2gReserve
          },
          charger: {
            rated_power_kw: telemetryState.chargerRatedKw,
            ramp_rate_kw_per_sec: telemetryState.rampRateKwPerSec
          },
          v2g_entry_stress: telemetryState.v2gEntryStress,
          v2g_exit_stress: telemetryState.v2gExitStress,
          high_load_confirmation_time_sec: telemetryState.highLoadConfirmationSec,
          minimum_charge_hold_sec: telemetryState.minimumChargeHoldSec,
          ramp_rate_kw_per_sec: telemetryState.rampRateKwPerSec
        })
      });
    } catch (e) {
      console.warn("Backend sync notice:", e);
    }
  }

  // ================= 8. DATA MODE SWITCHING (LIVE / HIST / SIM) =================
  function setDataMode(mode) {
    currentDataMode = mode;
    document.querySelectorAll('.tb-mode-tab').forEach(btn => {
      btn.className = 'tb-mode-tab px-2.5 py-1 rounded text-slate-400 hover:text-slate-200 font-mono text-[11px] transition-all';
    });

    const activeBtn = document.getElementById(`tb-mode-${mode.toLowerCase().slice(0, 4)}`);
    if (activeBtn) {
      activeBtn.className = 'tb-mode-tab px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-400 font-mono font-bold text-[11px] border border-emerald-500/40 transition-all';
    }

    const badge = document.getElementById('data-mode-badge');
    const label = document.getElementById('data-mode-label');
    if (badge && label) {
      if (mode === 'LIVE') {
        badge.className = 'px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center gap-1.5';
        label.textContent = 'o LIVE';
      } else if (mode === 'SIMULATION') {
        badge.className = 'px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-blue-500/20 text-blue-400 border border-blue-500/40 flex items-center gap-1.5';
        label.textContent = 'o SIMULATION';
      } else {
        badge.className = 'px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-purple-500/20 text-purple-400 border border-purple-500/40 flex items-center gap-1.5';
        label.textContent = 'o HISTORICAL';
      }
    }

    showToast(`Switched data mode to ${mode}.`, 'sensors');
    syncToBackend();
  }

  // ================= 9. DIGITAL TWIN SIMULATION STEP =================
  function stepSimulation() {
    currentStep = (currentStep + 1) % 96;
    const timeHours = currentStep * 0.25;
    const hourInt = Math.floor(timeHours);
    const minInt = (currentStep % 4) * 15;
    const timeShort = `${String(hourInt).padStart(2, '0')}:${String(minInt).padStart(2, '0')}`;

    if (timelineLabel) timelineLabel.textContent = `${timeShort} (Step #${currentStep})`;
    if (timelineScrubber && document.activeElement !== timelineScrubber) {
      timelineScrubber.value = currentStep;
    }

    const dt = 0.25; // 15-minute timestep in hours

    // Physics update
    let baseDemandGw = telemetryState.gridDemandGw;
    let price = telemetryState.marketPrice;
    let solarGw = telemetryState.solarGw;

    if (currentDataMode === 'SIMULATION') {
      baseDemandGw = getSyntheticGridDemand(currentStep);
      price = getSyntheticPrice(currentStep);
      solarGw = getSyntheticSolar(currentStep);
    }

    // DRL / Strategy Decision Logic (PRD Section 64-68)
    let commandedPowerKw = 8.4;
    let actionStr = 'CHARGE';
    const isPeakHour = (timeHours >= 17.0 && timeHours <= 21.0);

    // Urgent Departure Check (PRD Section 68)
    const neededSoc = Math.max(0, telemetryState.evRequiredSoc - telemetryState.evSoc);
    const timeRemainingHours = Math.max(0.2, 19.5 - timeHours);
    const neededEnergy = (neededSoc / 100.0) * telemetryState.evCapacityKwh;
    const urgency = (neededEnergy / timeRemainingHours) / 22.0;
    telemetryState.drlUrgencyPct = Math.min(100, Math.round(urgency * 100));

    if (urgency > 0.65) {
      commandedPowerKw = 11.0;
      actionStr = 'CHARGE';
    } else if (isPeakHour && telemetryState.evV2gEnabled && telemetryState.evSoc > telemetryState.evV2gReserve + 5.0) {
      commandedPowerKw = -10.0; // V2G Discharge into grid
      actionStr = 'DISCHARGE';
    } else {
      commandedPowerKw = 8.4;
      actionStr = 'CHARGE';
    }

    // Battery physics integration
    if (commandedPowerKw > 0) {
      const addedKwh = commandedPowerKw * 0.95 * dt;
      telemetryState.evSoc = Math.min(telemetryState.evMaxSoc, telemetryState.evSoc + (addedKwh / telemetryState.evCapacityKwh) * 100.0);
      telemetryState.meterImportKw = commandedPowerKw;
      telemetryState.meterExportKw = 0.0;
      telemetryState.meterNetKw = commandedPowerKw;
      telemetryState.meterImportKwh += (commandedPowerKw * dt);
      telemetryState.meterDirection = 'GRID -> EV';
      telemetryState.chargerMode = 'CHARGING';
    } else if (commandedPowerKw < 0) {
      const removedKwh = (Math.abs(commandedPowerKw) / 0.95) * dt;
      telemetryState.evSoc = Math.max(telemetryState.evMinSoc, telemetryState.evSoc - (removedKwh / telemetryState.evCapacityKwh) * 100.0);
      telemetryState.meterImportKw = 0.0;
      telemetryState.meterExportKw = Math.abs(commandedPowerKw);
      telemetryState.meterNetKw = commandedPowerKw;
      telemetryState.meterExportKwh += (Math.abs(commandedPowerKw) * dt);
      telemetryState.meterDirection = 'EV -> GRID';
      telemetryState.chargerMode = 'V2G';
    }

    telemetryState.drlAction = actionStr;
    telemetryState.drlPowerKw = commandedPowerKw;
    telemetryState.chargerPowerKw = commandedPowerKw;
    telemetryState.simEvImpactKw = commandedPowerKw;
    telemetryState.simManagedLoadGw = parseFloat((baseDemandGw + commandedPowerKw / 1000000.0).toFixed(4));

    // Update Sparklines History
    history.gridBase[currentStep] = baseDemandGw * 1000.0;
    history.gridNet[currentStep] = telemetryState.simManagedLoadGw * 1000.0;
    history.evSoc[currentStep] = telemetryState.evSoc;
    history.evPower[currentStep] = commandedPowerKw;

    // Update Live Nodes
    syncNodesFromState();
    renderAllNodes();
    renderAllWires();
    updateSystemStatusSidebar();
    updateEnergyMeterBar();
    renderSparklines();
    if (selectedNodeId) renderInspector();
  }

  function syncNodesFromState() {
    nodes.forEach(n => {
      if (n.type === 'grid_info') {
        n.props.demandGw = telemetryState.gridDemandGw;
        n.props.supplyGw = telemetryState.gridSupplyGw;
      } else if (n.type === 'price_info') {
        n.props.mcp = telemetryState.marketPrice;
        n.props.currentBlock = telemetryState.marketBlock;
      } else if (n.type === 'renewable_info') {
        n.props.solarGw = telemetryState.solarGw;
        n.props.windGw = telemetryState.windGw;
        n.props.totalGw = telemetryState.renewableTotalGw;
      } else if (n.type === 'ev_info') {
        n.props.soc = telemetryState.evSoc;
      } else if (n.type === 'drl') {
        n.props.action = telemetryState.drlAction;
        n.props.powerKw = telemetryState.drlPowerKw;
      } else if (n.type === 'decision_info') {
        n.props.action = telemetryState.drlAction;
        n.props.powerKw = telemetryState.drlPowerKw;
      } else if (n.type === 'charger') {
        n.props.powerKw = telemetryState.chargerPowerKw;
        n.props.mode = telemetryState.chargerMode;
      } else if (n.type === 'battery') {
        n.props.soc = telemetryState.evSoc;
      } else if (n.type === 'grid') {
        n.props.baseDemandGw = telemetryState.gridDemandGw;
        n.props.evImpactKw = telemetryState.simEvImpactKw;
      } else if (n.type === 'meter') {
        n.props.importPowerKw = telemetryState.meterImportKw;
        n.props.exportPowerKw = telemetryState.meterExportKw;
        n.props.netPowerKw = telemetryState.meterNetKw;
        n.props.direction = telemetryState.meterDirection;
      }
    });
  }

  // ================= 10. SYSTEM STATUS SIDEBAR UPDATES =================
  function updateSystemStatusSidebar() {
    const stGridVal = document.getElementById('st-grid-val');
    const stGridFreq = document.getElementById('st-grid-freq');
    const stGridMargin = document.getElementById('st-grid-margin');
    if (stGridVal) stGridVal.textContent = `${telemetryState.gridDemandGw.toFixed(2)} GW`;
    if (stGridFreq) stGridFreq.textContent = `${telemetryState.gridFrequencyHz.toFixed(2)} Hz`;
    if (stGridMargin) stGridMargin.textContent = `+${telemetryState.gridMarginGw.toFixed(2)} GW`;

    const stPriceVal = document.getElementById('st-price-val');
    const stPriceBlock = document.getElementById('st-price-block');
    const stPriceState = document.getElementById('st-price-state');
    if (stPriceVal) stPriceVal.textContent = `Rs.${telemetryState.marketPrice.toFixed(2)}/kWh`;
    if (stPriceBlock) stPriceBlock.textContent = telemetryState.marketBlock;
    if (stPriceState) stPriceState.textContent = telemetryState.priceState;

    const stRenewVal = document.getElementById('st-renew-val');
    if (stRenewVal) stRenewVal.textContent = `${telemetryState.renewableTotalGw.toFixed(2)} GW`;

    const stCtrlStatus = document.getElementById('st-controller-status');
    if (stCtrlStatus) stCtrlStatus.textContent = `ACTIVE (${telemetryState.drlAction})`;

    const stBattStatus = document.getElementById('st-battery-status');
    if (stBattStatus) stBattStatus.textContent = `CONNECTED (${telemetryState.evSoc.toFixed(1)}%)`;

    const stChgStatus = document.getElementById('st-charger-status');
    if (stChgStatus) stChgStatus.textContent = `${telemetryState.chargerMode} (${Math.abs(telemetryState.chargerPowerKw).toFixed(1)} kW)`;

    const stLiveDemand = document.getElementById('st-live-demand');
    const stEvImpact = document.getElementById('st-ev-impact');
    const stManagedLoad = document.getElementById('st-managed-load');
    if (stLiveDemand) stLiveDemand.textContent = `${telemetryState.gridDemandGw.toFixed(3)} GW`;
    if (stEvImpact) stEvImpact.textContent = `${telemetryState.simEvImpactKw >= 0 ? '+' : ''}${telemetryState.simEvImpactKw.toFixed(2)} kW`;
    if (stManagedLoad) stManagedLoad.textContent = `${telemetryState.simManagedLoadGw.toFixed(3)} GW`;
  }

  // ================= 11. PASSIVE ENERGY METER BAR UPDATES =================
  function updateEnergyMeterBar() {
    const elImp = document.getElementById('meter-bar-import');
    const elExp = document.getElementById('meter-bar-export');
    const elNet = document.getElementById('meter-bar-net');
    const elDir = document.getElementById('meter-bar-dir');
    const elImpKwh = document.getElementById('meter-bar-imp-kwh');
    const elExpKwh = document.getElementById('meter-bar-exp-kwh');

    const impKw = telemetryState.meterImportKw !== undefined ? telemetryState.meterImportKw : 0.0;
    const expKw = telemetryState.meterExportKw !== undefined ? telemetryState.meterExportKw : 0.0;
    const netKw = telemetryState.meterNetKw !== undefined ? telemetryState.meterNetKw : 0.0;
    const dir = telemetryState.meterDirection || 'NO EV POWER FLOW';

    if (elImp) elImp.textContent = `${impKw.toFixed(2)} kW`;
    if (elExp) elExp.textContent = `${expKw.toFixed(2)} kW`;
    if (elNet) elNet.textContent = `${netKw >= 0 ? '+' : ''}${netKw.toFixed(2)} kW`;
    if (elDir) {
      elDir.textContent = dir;
      if (dir.includes('EV ->') || dir.includes('EV →') || dir === 'EV_TO_GRID') {
        elDir.className = 'px-2 py-0.5 rounded font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30';
      } else if (dir.includes('GRID ->') || dir.includes('GRID →') || dir === 'GRID_TO_EV') {
        elDir.className = 'px-2 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
      } else {
        elDir.className = 'px-2 py-0.5 rounded font-bold bg-slate-800 text-slate-400 border border-slate-700';
      }
    }
    if (elImpKwh) elImpKwh.textContent = `${(telemetryState.meterImportKwh !== undefined ? telemetryState.meterImportKwh : 0.0).toFixed(2)} kWh`;
    if (elExpKwh) elExpKwh.textContent = `${(telemetryState.meterExportKwh !== undefined ? telemetryState.meterExportKwh : 0.0).toFixed(2)} kWh`;
  }

  // ================= 12. RESPONSIVE TIME-SERIES ANALYTICS (CHART.JS) =================
  let chartInstances = {
    demand: null,
    renewable: null,
    price: null,
    soc: null,
    batteryPower: null,
    chargerPower: null,
    meterPower: null,
    gridImpact: null
  };
  let isChartFollowPaused = false;
  let activeChartWindowSec = 'live';

  function getThemeColors() {
    const isLight = document.documentElement.classList.contains('light');
    return {
      isLight,
      gridColor: isLight ? 'rgba(15, 23, 42, 0.08)' : 'rgba(148, 163, 184, 0.12)',
      textColor: isLight ? '#475569' : '#94a3b8',
      tooltipBg: isLight ? 'rgba(255, 255, 255, 0.98)' : 'rgba(15, 23, 42, 0.95)',
      tooltipText: isLight ? '#0f172a' : '#f1f5f9',
      tooltipBorder: isLight ? 'rgba(15, 23, 42, 0.15)' : 'rgba(148, 163, 184, 0.2)'
    };
  }

  function getBaseChartOptions(unit, yMin, yMax) {
    const tc = getThemeColors();
    const opts = {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: {
            boxWidth: 8,
            boxHeight: 8,
            usePointStyle: true,
            color: tc.textColor,
            font: { family: 'JetBrains Mono', size: 10 }
          }
        },
        tooltip: {
          backgroundColor: tc.tooltipBg,
          titleColor: tc.tooltipText,
          bodyColor: tc.tooltipText,
          borderColor: tc.tooltipBorder,
          borderWidth: 1,
          padding: 8,
          titleFont: { family: 'JetBrains Mono', size: 11, weight: 'bold' },
          bodyFont: { family: 'JetBrains Mono', size: 11 },
          callbacks: {
            label: function(context) {
              return ` ${context.dataset.label}: ${context.parsed.y} ${unit}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: tc.gridColor, drawBorder: false },
          ticks: {
            color: tc.textColor,
            font: { family: 'JetBrains Mono', size: 9 },
            maxTicksLimit: 8
          }
        },
        y: {
          grid: { color: tc.gridColor, drawBorder: false },
          ticks: {
            color: tc.textColor,
            font: { family: 'JetBrains Mono', size: 9 },
            callback: (val) => `${val} ${unit}`
          }
        }
      }
    };
    if (yMin !== undefined) opts.scales.y.min = yMin;
    if (yMax !== undefined) opts.scales.y.max = yMax;
    return opts;
  }

  function initCharts() {
    if (typeof Chart === 'undefined') {
      setTimeout(initCharts, 300);
      return;
    }

    Object.values(chartInstances).forEach(c => { if (c) c.destroy(); });

    // Chart 1: Grid Demand vs Supply
    const ctx1 = document.getElementById('chart-grid-demand');
    if (ctx1) {
      chartInstances.demand = new Chart(ctx1, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Live Demand (GW)', data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.1)', borderWidth: 2, pointRadius: 0, tension: 0.2 },
            { label: 'Available Supply (GW)', data: [], borderColor: '#94a3b8', borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0, tension: 0.2 },
            { label: 'Managed Demand (GW)', data: [], borderColor: '#10b981', borderWidth: 2, pointRadius: 0, tension: 0.2 }
          ]
        },
        options: getBaseChartOptions('GW', 11.0, 16.0)
      });
    }

    // Chart 2: Renewable Generation
    const ctx2 = document.getElementById('chart-renewable');
    if (ctx2) {
      chartInstances.renewable = new Chart(ctx2, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Total Renewable (GW)', data: [], borderColor: '#14b8a6', backgroundColor: 'rgba(20, 184, 166, 0.1)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.2 },
            { label: 'Solar (GW)', data: [], borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, tension: 0.2 },
            { label: 'Wind (GW)', data: [], borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0, tension: 0.2 },
            { label: 'Hydro (GW)', data: [], borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, tension: 0.2 }
          ]
        },
        options: getBaseChartOptions('GW', 0, 8.0)
      });
    }

    // Chart 3: Electricity Price
    const ctx3 = document.getElementById('chart-price');
    if (ctx3) {
      chartInstances.price = new Chart(ctx3, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'IEX RTM MCP (Rs./kWh)', data: [], borderColor: '#f43f5e', backgroundColor: 'rgba(244, 63, 94, 0.1)', fill: true, borderWidth: 2, pointRadius: 0, stepped: true }
          ]
        },
        options: getBaseChartOptions('Rs.', 0, 14.0)
      });
    }

    // Chart 4: Battery SOC Profile
    const ctx4 = document.getElementById('chart-ev-soc');
    if (ctx4) {
      chartInstances.soc = new Chart(ctx4, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Current SOC (%)', data: [], borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.1)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.2 },
            { label: 'Target SOC (%)', data: [], borderColor: '#38bdf8', borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0 },
            { label: 'Min Floor (%)', data: [], borderColor: '#f59e0b', borderDash: [3, 3], borderWidth: 1, pointRadius: 0 },
            { label: 'Max Ceiling (%)', data: [], borderColor: '#f43f5e', borderDash: [3, 3], borderWidth: 1, pointRadius: 0 }
          ]
        },
        options: getBaseChartOptions('%', 0, 100)
      });
    }

    // Chart 5: Battery Net Power
    const ctx5 = document.getElementById('chart-battery-power');
    if (ctx5) {
      chartInstances.batteryPower = new Chart(ctx5, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Net Battery Power (kW)', data: [], borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.12)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.2 }
          ]
        },
        options: getBaseChartOptions('kW', -15.0, 25.0)
      });
    }

    // Chart 6: V2G Charger Power
    const ctx6 = document.getElementById('chart-charger-power');
    if (ctx6) {
      chartInstances.chargerPower = new Chart(ctx6, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Charger Power (kW)', data: [], borderColor: '#06b6d4', backgroundColor: 'rgba(6, 182, 212, 0.12)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.2 }
          ]
        },
        options: getBaseChartOptions('kW', -15.0, 25.0)
      });
    }

    // Chart 7: Energy Meter Power
    const ctx7 = document.getElementById('chart-meter-power');
    if (ctx7) {
      chartInstances.meterPower = new Chart(ctx7, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Net Power (kW)', data: [], borderColor: '#ec4899', backgroundColor: 'rgba(236, 72, 153, 0.1)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.2 },
            { label: 'Import Power (kW)', data: [], borderColor: '#10b981', borderWidth: 1.5, pointRadius: 0, tension: 0.2 },
            { label: 'Export Power (kW)', data: [], borderColor: '#06b6d4', borderWidth: 1.5, pointRadius: 0, tension: 0.2 }
          ]
        },
        options: getBaseChartOptions('kW', -15.0, 25.0)
      });
    }

    // Chart 8: EV Impact on Grid
    const ctx8 = document.getElementById('chart-grid-impact');
    if (ctx8) {
      chartInstances.gridImpact = new Chart(ctx8, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Managed Sim Load (GW)', data: [], borderColor: '#a855f7', backgroundColor: 'rgba(168, 85, 247, 0.12)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.2 },
            { label: 'Base Grid Demand (GW)', data: [], borderColor: '#94a3b8', borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0, tension: 0.2 }
          ]
        },
        options: getBaseChartOptions('GW', 11.0, 16.0)
      });
    }

    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => {
        Object.values(chartInstances).forEach(c => { if (c) c.resize(); });
      });
      document.querySelectorAll('.chart-canvas-wrapper').forEach(el => ro.observe(el));
    }

    fetchTelemetryHistory();
  }

  function fetchTelemetryHistory() {
    const win = activeChartWindowSec === 'live' ? 300 : activeChartWindowSec;
    fetch(`/api/telemetry/history?window=${win}`)
      .then(res => res.json())
      .then(res => {
        if (res && res.history && res.history.length > 0) {
          hydrateChartsFromHistory(res.history);
        }
      })
      .catch(() => {});
  }

  function hydrateChartsFromHistory(hist) {
    if (!hist || !hist.length) return;
    const labels = hist.map(h => h.sim_time || (h.timestamp ? h.timestamp.substring(11, 19) : '--:--:--'));

    // Chart 1: Demand
    if (chartInstances.demand) {
      chartInstances.demand.data.labels = [...labels];
      chartInstances.demand.data.datasets[0].data = hist.map(h => h.demand_gw || (h.demand_mw ? h.demand_mw / 1000 : 13.74));
      chartInstances.demand.data.datasets[1].data = hist.map(h => h.supply_gw || (h.supply_mw ? h.supply_mw / 1000 : 14.20));
      chartInstances.demand.data.datasets[2].data = hist.map(h => h.managed_gw || (h.managed_mw ? h.managed_mw / 1000 : (h.demand_gw || 13.74)));
      chartInstances.demand.update('none');

      const dVals = hist.map(h => h.demand_gw || (h.demand_mw ? h.demand_mw / 1000 : 13.74));
      const curD = dVals[dVals.length - 1] || 13.74;
      const elC1Cur = document.getElementById('c1-cur');
      const elC1Supply = document.getElementById('c1-supply');
      if (elC1Cur) elC1Cur.textContent = `${curD.toFixed(2)} GW`;
      if (elC1Supply && hist[hist.length - 1].supply_gw) elC1Supply.textContent = `${hist[hist.length - 1].supply_gw.toFixed(2)} GW`;
    }

    // Chart 2: Renewable
    if (chartInstances.renewable) {
      chartInstances.renewable.data.labels = [...labels];
      chartInstances.renewable.data.datasets[0].data = hist.map(h => h.total_renewable_gw || (h.renewable_mw ? h.renewable_mw / 1000 : 5.02));
      chartInstances.renewable.data.datasets[1].data = hist.map(h => h.solar_gw || (h.solar_mw ? h.solar_mw / 1000 : 1.99));
      chartInstances.renewable.data.datasets[2].data = hist.map(h => h.wind_gw || (h.wind_mw ? h.wind_mw / 1000 : 2.41));
      chartInstances.renewable.data.datasets[3].data = hist.map(h => h.hydro_gw || (h.hydro_mw ? h.hydro_mw / 1000 : 0.62));
      chartInstances.renewable.update('none');

      const lastRen = hist[hist.length - 1];
      const elC4Tot = document.getElementById('c4-tot');
      const elC4Share = document.getElementById('c4-share');
      if (elC4Tot) elC4Tot.textContent = `${(lastRen.total_renewable_gw || (lastRen.renewable_mw ? lastRen.renewable_mw / 1000 : 5.02)).toFixed(2)} GW`;
      if (elC4Share) elC4Share.textContent = `${(lastRen.renewable_share_pct || lastRen.renewable_share || 36.5).toFixed(1)}%`;
    }

    // Chart 3: Price
    if (chartInstances.price) {
      chartInstances.price.data.labels = [...labels];
      chartInstances.price.data.datasets[0].data = hist.map(h => h.price || h.mcp_inr_per_kwh || 8.20);
      chartInstances.price.update('none');

      const lastPrc = hist[hist.length - 1];
      const elC5Cur = document.getElementById('c5-cur');
      const elC5Block = document.getElementById('c5-block');
      if (elC5Cur) elC5Cur.textContent = `Rs.${(lastPrc.price || lastPrc.mcp_inr_per_kwh || 8.20).toFixed(2)}/kWh`;
      if (elC5Block) elC5Block.textContent = lastPrc.current_block || '18:45-19:00';
    }

    // Chart 4: SOC
    if (chartInstances.soc) {
      chartInstances.soc.data.labels = [...labels];
      chartInstances.soc.data.datasets[0].data = hist.map(h => h.soc !== undefined ? h.soc : 64.2);
      chartInstances.soc.data.datasets[1].data = hist.map(h => h.target_soc || 80.0);
      chartInstances.soc.data.datasets[2].data = hist.map(h => h.min_soc || 20.0);
      chartInstances.soc.data.datasets[3].data = hist.map(h => h.max_soc || 95.0);
      chartInstances.soc.update('none');

      const lastPt = hist[hist.length - 1];
      const elC2Cur = document.getElementById('c2-cur');
      const elC2Tgt = document.getElementById('c2-target');
      const elC2Full = document.getElementById('c2-full');
      if (elC2Cur) elC2Cur.textContent = `${(lastPt.soc !== undefined ? lastPt.soc : 64.2).toFixed(1)}%`;
      if (elC2Tgt) elC2Tgt.textContent = `${lastPt.target_soc || 80.0}%`;
      if (elC2Full && lastPt.time_to_full_str) elC2Full.textContent = lastPt.time_to_full_str;
    }

    // Chart 5: Battery Net Power
    if (chartInstances.batteryPower) {
      chartInstances.batteryPower.data.labels = [...labels];
      chartInstances.batteryPower.data.datasets[0].data = hist.map(h => h.battery_power_kw !== undefined ? h.battery_power_kw : (h.charger_power_kw || 0.0));
      chartInstances.batteryPower.update('none');

      const lastPwr = hist[hist.length - 1].battery_power_kw !== undefined ? hist[hist.length - 1].battery_power_kw : (hist[hist.length - 1].charger_power_kw || 0.0);
      const elC5PwrCur = document.getElementById('c5-pwr-cur');
      if (elC5PwrCur) elC5PwrCur.textContent = `${lastPwr >= 0 ? '+' : ''}${lastPwr.toFixed(1)} kW`;
    }

    // Chart 6: Charger Power
    if (chartInstances.chargerPower) {
      chartInstances.chargerPower.data.labels = [...labels];
      chartInstances.chargerPower.data.datasets[0].data = hist.map(h => h.charger_power_kw !== undefined ? h.charger_power_kw : 0.0);
      chartInstances.chargerPower.update('none');

      const lastChg = hist[hist.length - 1].charger_power_kw !== undefined ? hist[hist.length - 1].charger_power_kw : 0.0;
      const elC3Cur = document.getElementById('c3-cur');
      if (elC3Cur) elC3Cur.textContent = `${lastChg >= 0 ? '+' : ''}${lastChg.toFixed(1)} kW`;
    }

    // Chart 7: Meter Power
    if (chartInstances.meterPower) {
      chartInstances.meterPower.data.labels = [...labels];
      chartInstances.meterPower.data.datasets[0].data = hist.map(h => h.meter_net_kw !== undefined ? h.meter_net_kw : (h.net_kw || 0.0));
      chartInstances.meterPower.data.datasets[1].data = hist.map(h => h.imported_power_kw !== undefined ? h.imported_power_kw : 0.0);
      chartInstances.meterPower.data.datasets[2].data = hist.map(h => h.exported_power_kw !== undefined ? h.exported_power_kw : 0.0);
      chartInstances.meterPower.update('none');

      const lastM = hist[hist.length - 1];
      const mNet = lastM.meter_net_kw !== undefined ? lastM.meter_net_kw : (lastM.net_kw || 0.0);
      const mImp = lastM.imported_power_kw !== undefined ? lastM.imported_power_kw : 0.0;
      const mExp = lastM.exported_power_kw !== undefined ? lastM.exported_power_kw : 0.0;
      const elC7Net = document.getElementById('c7-net');
      const elC7Imp = document.getElementById('c7-imp');
      const elC7Exp = document.getElementById('c7-exp');
      if (elC7Net) elC7Net.textContent = `${mNet >= 0 ? '+' : ''}${mNet.toFixed(1)} kW`;
      if (elC7Imp) elC7Imp.textContent = `${mImp.toFixed(1)} kW`;
      if (elC7Exp) elC7Exp.textContent = `${mExp.toFixed(1)} kW`;
    }

    // Chart 8: Grid Impact
    if (chartInstances.gridImpact) {
      chartInstances.gridImpact.data.labels = [...labels];
      chartInstances.gridImpact.data.datasets[0].data = hist.map(h => h.managed_gw || (h.managed_mw ? h.managed_mw / 1000 : (h.demand_gw || 13.74)));
      chartInstances.gridImpact.data.datasets[1].data = hist.map(h => h.demand_gw || (h.demand_mw ? h.demand_mw / 1000 : 13.74));
      chartInstances.gridImpact.update('none');

      const lastGi = hist[hist.length - 1];
      const mGw = lastGi.managed_gw || (lastGi.managed_mw ? lastGi.managed_mw / 1000 : 13.748);
      const bGw = lastGi.demand_gw || (lastGi.demand_mw ? lastGi.demand_mw / 1000 : 13.740);
      const elC8Managed = document.getElementById('c8-managed');
      const elC8Base = document.getElementById('c8-base');
      if (elC8Managed) elC8Managed.textContent = `${mGw.toFixed(3)} GW`;
      if (elC8Base) elC8Base.textContent = `${bGw.toFixed(3)} GW`;
    }
  }

  function appendTelemetryPointToCharts(twinData) {
    if (isChartFollowPaused) return;
    const timeLabel = twinData.simulation_time || twinData.sim_time || (twinData.timestamp ? new Date(twinData.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString());
    const maxPts = activeChartWindowSec === 'live' ? 60 : (activeChartWindowSec === 300 ? 300 : 360);

    function pushData(chart, datasetIdx, val) {
      if (!chart) return;
      if (datasetIdx === 0) {
        chart.data.labels.push(timeLabel);
        if (chart.data.labels.length > maxPts) chart.data.labels.shift();
      }
      const ds = chart.data.datasets[datasetIdx];
      if (ds) {
        ds.data.push(val);
        if (ds.data.length > maxPts) ds.data.shift();
      }
    }

    // Single source authoritative power
    const pwr = telemetryState.chargerPowerKw !== undefined ? telemetryState.chargerPowerKw : 0.0;

    // Chart 1: Demand
    if (chartInstances.demand && twinData.grid) {
      const dGw = twinData.grid.demand_gw || 13.74;
      const sGw = twinData.grid.supply_gw || 14.20;
      const mGw = dGw + (pwr / 1000000);
      pushData(chartInstances.demand, 0, dGw);
      pushData(chartInstances.demand, 1, sGw);
      pushData(chartInstances.demand, 2, mGw);
      chartInstances.demand.update('none');

      const elC1Cur = document.getElementById('c1-cur');
      const elC1Supply = document.getElementById('c1-supply');
      if (elC1Cur) elC1Cur.textContent = `${dGw.toFixed(2)} GW`;
      if (elC1Supply) elC1Supply.textContent = `${sGw.toFixed(2)} GW`;
    }

    // Chart 2: Renewable
    if (chartInstances.renewable && twinData.renewable) {
      const tot = twinData.renewable.total_renewable_gw || (twinData.renewable.solar_gw + twinData.renewable.wind_gw + twinData.renewable.hydro_gw);
      pushData(chartInstances.renewable, 0, tot);
      pushData(chartInstances.renewable, 1, twinData.renewable.solar_gw);
      pushData(chartInstances.renewable, 2, twinData.renewable.wind_gw);
      pushData(chartInstances.renewable, 3, twinData.renewable.hydro_gw);
      chartInstances.renewable.update('none');

      const elC4Tot = document.getElementById('c4-tot');
      const elC4Share = document.getElementById('c4-share');
      if (elC4Tot) elC4Tot.textContent = `${tot.toFixed(2)} GW`;
      if (elC4Share) elC4Share.textContent = `${(twinData.renewable.renewable_share_pct || 36.5).toFixed(1)}%`;
    }

    // Chart 3: Price
    if (chartInstances.price && twinData.price) {
      const mcp = twinData.price.mcp_inr_per_kwh || 8.20;
      pushData(chartInstances.price, 0, mcp);
      chartInstances.price.update('none');

      const elC5Cur = document.getElementById('c5-cur');
      const elC5Block = document.getElementById('c5-block');
      if (elC5Cur) elC5Cur.textContent = `Rs.${mcp.toFixed(2)}/kWh`;
      if (elC5Block) elC5Block.textContent = twinData.price.current_block || '18:45-19:00';
    }

    // Chart 4: SOC
    if (chartInstances.soc && twinData.battery) {
      const soc = twinData.battery.soc;
      pushData(chartInstances.soc, 0, soc);
      pushData(chartInstances.soc, 1, twinData.ev ? twinData.ev.required_soc : 80.0);
      pushData(chartInstances.soc, 2, twinData.ev ? twinData.ev.min_soc : 20.0);
      pushData(chartInstances.soc, 3, twinData.ev ? twinData.ev.max_soc : 95.0);
      chartInstances.soc.update('none');

      const elC2Cur = document.getElementById('c2-cur');
      const elC2Tgt = document.getElementById('c2-target');
      const elC2Full = document.getElementById('c2-full');
      if (elC2Cur) elC2Cur.textContent = `${soc.toFixed(1)}%`;
      if (elC2Tgt) elC2Tgt.textContent = `${twinData.ev ? twinData.ev.required_soc : 80.0}%`;
      if (elC2Full && twinData.battery.time_to_full_str) elC2Full.textContent = twinData.battery.time_to_full_str;
    }

    // Chart 5: Battery Net Power
    if (chartInstances.batteryPower && twinData.battery) {
      const bPwr = twinData.battery.power_kw !== undefined ? twinData.battery.power_kw : pwr;
      pushData(chartInstances.batteryPower, 0, bPwr);
      chartInstances.batteryPower.update('none');

      const elC5PwrCur = document.getElementById('c5-pwr-cur');
      if (elC5PwrCur) elC5PwrCur.textContent = `${bPwr >= 0 ? '+' : ''}${bPwr.toFixed(1)} kW`;
    }

    // Chart 6: Charger Power
    if (chartInstances.chargerPower) {
      pushData(chartInstances.chargerPower, 0, pwr);
      chartInstances.chargerPower.update('none');

      const elC3Cur = document.getElementById('c3-cur');
      if (elC3Cur) elC3Cur.textContent = `${pwr >= 0 ? '+' : ''}${pwr.toFixed(1)} kW`;
    }

    // Chart 7: Meter Power
    if (chartInstances.meterPower) {
      const imp = telemetryState.meterImportKw !== undefined ? telemetryState.meterImportKw : (pwr > 0 ? pwr : 0.0);
      const exp = telemetryState.meterExportKw !== undefined ? telemetryState.meterExportKw : (pwr < 0 ? Math.abs(pwr) : 0.0);
      const net = telemetryState.meterNetKw !== undefined ? telemetryState.meterNetKw : pwr;
      pushData(chartInstances.meterPower, 0, net);
      pushData(chartInstances.meterPower, 1, imp);
      pushData(chartInstances.meterPower, 2, exp);
      chartInstances.meterPower.update('none');

      const elC7Net = document.getElementById('c7-net');
      const elC7Imp = document.getElementById('c7-imp');
      const elC7Exp = document.getElementById('c7-exp');
      if (elC7Net) elC7Net.textContent = `${net >= 0 ? '+' : ''}${net.toFixed(1)} kW`;
      if (elC7Imp) elC7Imp.textContent = `${imp.toFixed(1)} kW`;
      if (elC7Exp) elC7Exp.textContent = `${exp.toFixed(1)} kW`;
    }

    // Chart 8: Grid Impact
    if (chartInstances.gridImpact && twinData.grid) {
      const dGw = twinData.grid.demand_gw || 13.74;
      const mGw = dGw + (pwr / 1000000);
      pushData(chartInstances.gridImpact, 0, mGw);
      pushData(chartInstances.gridImpact, 1, dGw);
      chartInstances.gridImpact.update('none');

      const elC8Managed = document.getElementById('c8-managed');
      const elC8Base = document.getElementById('c8-base');
      if (elC8Managed) elC8Managed.textContent = `${mGw.toFixed(3)} GW`;
      if (elC8Base) elC8Base.textContent = `${dGw.toFixed(3)} GW`;
    }
  }

  // ================= THEME MANAGER (PRD Section 37-41) =================
  function initTheme() {
    let saved = null;
    try {
      saved = localStorage.getItem('gridwise_theme');
    } catch (e) {}
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = saved ? saved : (prefersDark ? 'dark' : 'light');
    applyTheme(initialTheme);
  }

  function applyTheme(theme) {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');

    if (theme === 'light') {
      html.classList.remove('dark');
      html.classList.add('light');
      if (icon) icon.textContent = 'dark_mode';
      if (label) label.textContent = 'DARK';
    } else {
      html.classList.remove('light');
      html.classList.add('dark');
      if (icon) icon.textContent = 'light_mode';
      if (label) label.textContent = 'LIGHT';
    }
    localStorage.setItem('gridwise_theme', theme);

    const tc = getThemeColors();
    Object.values(chartInstances).forEach(chart => {
      if (!chart) return;
      if (chart.options.scales && chart.options.scales.x) {
        chart.options.scales.x.grid.color = tc.gridColor;
        chart.options.scales.x.ticks.color = tc.textColor;
      }
      if (chart.options.scales && chart.options.scales.y) {
        chart.options.scales.y.grid.color = tc.gridColor;
        chart.options.scales.y.ticks.color = tc.textColor;
      }
      if (chart.options.plugins && chart.options.plugins.legend) {
        chart.options.plugins.legend.labels.color = tc.textColor;
      }
      chart.update();
    });
  }

  function toggleTheme() {
    const isLight = document.documentElement.classList.contains('light');
    applyTheme(isLight ? 'dark' : 'light');
  }

  // ================= LIVE STATUS STRIP (PRD Section 3 & 42-46) =================
  function updateLiveStatusStrip(twinData) {
    if (!twinData) return;

    // Clocks
    const simTimeEl = document.getElementById('strip-sim-time');
    const realTimeEl = document.getElementById('strip-real-time');
    const speedEl = document.getElementById('strip-speed-mult');
    const simStatusEl = document.getElementById('strip-sim-status');
    if (simTimeEl) simTimeEl.textContent = twinData.simulation_time || '18:30:00';
    if (realTimeEl) realTimeEl.textContent = twinData.real_time || new Date().toLocaleTimeString();
    if (speedEl) speedEl.textContent = `${twinData.speed_multiplier || 1.0}x`;
    if (simStatusEl) {
      if (twinData.engine_running && !twinData.engine_paused) {
        simStatusEl.className = 'text-emerald-400 text-[9px] font-bold';
        simStatusEl.textContent = 'o RUNNING';
      } else if (twinData.engine_paused) {
        simStatusEl.className = 'text-amber-400 text-[9px] font-bold';
        simStatusEl.textContent = '|| PAUSED';
      } else {
        simStatusEl.className = 'text-slate-500 text-[9px] font-bold';
        simStatusEl.textContent = '[square] STOPPED';
      }
    }

    // Battery SOC & Power
    if (twinData.battery) {
      const batt = twinData.battery;
      const socEl = document.getElementById('strip-batt-soc');
      const targetEl = document.getElementById('strip-batt-target');
      const energyEl = document.getElementById('strip-batt-energy');
      const capEl = document.getElementById('strip-batt-cap');
      const stateEl = document.getElementById('strip-batt-state');
      const powerEl = document.getElementById('strip-batt-power');
      const effPowerEl = document.getElementById('strip-eff-power');

      if (socEl) socEl.textContent = `${batt.soc.toFixed(2)}%`;
      if (targetEl && twinData.ev) targetEl.textContent = `${twinData.ev.required_soc}%`;
      if (energyEl) energyEl.textContent = batt.energy_kwh.toFixed(2);
      if (capEl) capEl.textContent = `${batt.capacity_kwh} kWh`;
      if (stateEl) {
        stateEl.textContent = batt.state || 'IDLE';
        stateEl.className = batt.state === 'CHARGING' ? 'text-emerald-400 text-[9px] font-bold' : (batt.state === 'V2G' ? 'text-cyan-400 text-[9px] font-bold' : 'text-slate-400 text-[9px] font-bold');
      }
      if (powerEl) {
        const pwr = batt.power_kw;
        powerEl.textContent = `${pwr >= 0 ? '+' : ''}${pwr.toFixed(1)} kW`;
        powerEl.className = pwr > 0 ? 'text-base font-bold text-emerald-400' : (pwr < 0 ? 'text-base font-bold text-cyan-400' : 'text-base font-bold text-slate-400');
      }
      if (effPowerEl) effPowerEl.textContent = `${batt.effective_power_kw ? batt.effective_power_kw.toFixed(1) + ' kW net' : '--'}`;

      // Countdowns
      const timeTargetEl = document.getElementById('strip-time-target');
      const timeFullEl = document.getElementById('strip-time-full');
      const estTimeEl = document.getElementById('strip-est-time');
      const depBadgeEl = document.getElementById('strip-dep-badge');
      if (timeTargetEl) timeTargetEl.textContent = batt.time_to_target_str || '--:--:--';
      if (timeFullEl) timeFullEl.textContent = batt.time_to_full_str || '--:--:--';
      if (estTimeEl) estTimeEl.textContent = batt.estimated_completion_time ? batt.estimated_completion_time.substring(0, 5) : '--:--';
      if (depBadgeEl) {
        depBadgeEl.textContent = batt.departure_status || 'check FEASIBLE';
        depBadgeEl.className = (batt.departure_feasible !== false)
          ? 'text-[9px] text-emerald-400 font-bold'
          : 'text-[9px] text-rose-400 font-bold animate-pulse';
      }
    }

    // Grid Telemetry
    if (twinData.grid) {
      const g = twinData.grid;
      const gStateEl = document.getElementById('strip-grid-state');
      const gDemandEl = document.getElementById('strip-grid-demand');
      const gMarginEl = document.getElementById('strip-grid-margin');
      const gFreqEl = document.getElementById('strip-grid-freq');
      if (gStateEl) gStateEl.textContent = g.grid_stress || 'NORMAL';
      if (gDemandEl) gDemandEl.innerHTML = `${g.demand_gw.toFixed(2)} GW <span class="text-[10px] text-slate-400">live</span>`;
      if (gMarginEl) gMarginEl.textContent = `${g.supply_margin_mw >= 0 ? '+' : ''}${(g.supply_margin_mw / 1000).toFixed(2)} GW`;
      if (gFreqEl) gFreqEl.textContent = `${g.frequency_hz.toFixed(2)}Hz`;
    }

    // Controller & Price & Diagnostics
    if (twinData.diagnostics) {
      const diag = twinData.diagnostics;
      telemetryState.gridStressScore = diag.stress_score;
      telemetryState.v2gEntryStress = diag.v2g_entry_stress;
      telemetryState.v2gExitStress = diag.v2g_exit_stress;
      telemetryState.isHighLoadConfirmed = diag.is_high_load_confirmed;
      telemetryState.highLoadCandidateSec = diag.high_load_candidate_timer;
      const dwellM = Math.floor((diag.mode_dwell_time_seconds || 0) / 60);
      const dwellS = Math.floor((diag.mode_dwell_time_seconds || 0) % 60);
      telemetryState.modeDwellStr = `${String(dwellM).padStart(2, '0')}:${String(dwellS).padStart(2, '0')}`;
      telemetryState.nextControlEvalSec = Math.ceil(diag.next_control_eval_seconds || 0);
      telemetryState.decisionReason = diag.decision_reason;
    }

    const nextEvalEl = document.getElementById('strip-next-eval');
    if (nextEvalEl) {
      const nSec = Math.ceil(twinData.next_control_eval_seconds !== undefined ? twinData.next_control_eval_seconds : (telemetryState.nextControlEvalSec || 10));
      nextEvalEl.textContent = `NEXT: 00:${String(nSec).padStart(2, '0')}`;
    }

    if (twinData.price) {
      const prcEl = document.getElementById('strip-price-badge');
      if (prcEl) prcEl.textContent = `Rs.${(twinData.price.mcp_inr_per_kwh || 8.20).toFixed(2)}/kWh`;
    }

    if (twinData.controller) {
      const c = twinData.controller;
      const actEl = document.getElementById('strip-ctrl-action');
      const rsnEl = document.getElementById('strip-ctrl-reason');
      const pwr = (twinData.charger && twinData.charger.power_kw !== undefined) ? twinData.charger.power_kw : (c.power_kw || 0.0);
      const isV2G = pwr < -0.05 || c.action === 'V2G' || c.action === 'DISCHARGE';
      const isChg = pwr > 0.05 || c.action === 'CHARGE' || c.action === 'CHARGING';

      if (actEl) {
        if (isV2G) {
          actEl.className = 'text-sm font-bold text-cyan-400';
          actEl.textContent = `V2G SUPPORT (${pwr.toFixed(1)} kW)`;
        } else if (isChg) {
          actEl.className = 'text-sm font-bold text-emerald-400';
          actEl.textContent = `CHARGING (+${pwr.toFixed(1)} kW)`;
        } else {
          actEl.className = 'text-sm font-bold text-slate-400';
          actEl.textContent = `IDLE (0.0 kW)`;
        }
      }
      if (rsnEl) {
        const reasonText = (twinData.decision && twinData.decision.reason) ? twinData.decision.reason : (telemetryState.decisionReason || 'EV SOC below target; normal charging active');
        rsnEl.textContent = reasonText;
        rsnEl.title = reasonText;
      }
    }
  }

  // ================= 13. CONTINUOUS BACKEND PLAYBACK CONTROLS =================
  function startSimulation() {
    isRunning = true;
    updateRunButtons(true);
    fetch('/api/simulation/run', { method: 'POST' }).catch(() => {});
    try { if (ws && isWsConnected) ws.send(JSON.stringify({ command: 'run', speed: speedMultiplier })); } catch(e){}
    showToast("Simulation running continuously.", "play_arrow");
  }

  function pauseSimulation() {
    isRunning = false;
    updateRunButtons(false);
    fetch('/api/simulation/pause', { method: 'POST' }).catch(() => {});
    try { if (ws && isWsConnected) ws.send(JSON.stringify({ command: 'pause' })); } catch(e){}
    showToast("Simulation paused.", "pause");
  }

  function stopSimulation() {
    isRunning = false;
    updateRunButtons(false);
    fetch('/api/simulation/stop', { method: 'POST' }).catch(() => {});
    try { if (ws && isWsConnected) ws.send(JSON.stringify({ command: 'stop' })); } catch(e){}
    showToast("Simulation stopped.", "stop");
  }

  function resetSimulation() {
    isRunning = false;
    updateRunButtons(false);
    fetch('/api/simulation/reset', { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.state) handleIncomingTelemetry(data.state);
      })
      .catch(() => {});
    try { if (ws && isWsConnected) ws.send(JSON.stringify({ command: 'reset' })); } catch(e){}
    fetchTelemetryHistory();
    showToast("Environment reset.", "restart_alt");
  }

  function setSpeed(spd) {
    speedMultiplier = spd;
    fetch('/api/simulation/speed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speed: spd })
    }).catch(() => {});
    try { if (ws && isWsConnected) ws.send(JSON.stringify({ command: 'speed', speed: spd })); } catch(e){}
    const stripSpeed = document.getElementById('strip-speed-mult');
    if (stripSpeed) stripSpeed.textContent = `${spd}x`;
    showToast(`Simulation speed: ${spd}x`);
  }

  function updateRunButtons(running) {
    const runBtn = document.getElementById('tb-run-btn');
    if (runBtn) {
      if (running) {
        runBtn.classList.remove('bg-emerald-500', 'text-slate-950');
        runBtn.classList.add('bg-emerald-600', 'text-white', 'animate-pulse');
      } else {
        runBtn.classList.remove('bg-emerald-600', 'text-white', 'animate-pulse');
        runBtn.classList.add('bg-emerald-500', 'text-slate-950');
      }
    }
  }

  // ================= 14. SETUP FIXED SYSTEM ARCHITECTURE =================
  function setupSystemArchitecture() {
    nodes = [];
    connections = [];

    // Helper to add architecture block
    function addBlock(type, x, y, id) {
      const meta = COMPONENT_METADATA[type];
      const newNode = {
        id: id || `${type}_01`,
        type: type,
        title: meta.title,
        x: x,
        y: y,
        ports: meta.ports,
        props: JSON.parse(JSON.stringify(meta.defaultProps))
      };
      nodes.push(newNode);
      return newNode;
    }

    // TOP ROW: External Observations & Inputs (Y = 18, Height = 95)
    const renewInfo = addBlock('renewable_info', 30, 18, 'renew_info_01');
    const priceInfo = addBlock('price_info', 400, 18, 'price_info_01');
    const evInfo    = addBlock('ev_info', 770, 18, 'ev_info_01');

    // MIDDLE ROW: DRL Controller & Policy Decision (Y = 135, Height = 95)
    const drl     = addBlock('drl', 400, 135, 'drl_01');
    const decInfo = addBlock('decision_info', 770, 135, 'dec_info_01');

    // MAIN POWER ROW: Electrical Grid <-> Charger <-> EV Battery (Y = 260, Height = 125)
    // Horizontal Power Center-Y is exactly 322px across all three!
    const grid    = addBlock('grid', 30, 260, 'grid_01');
    const charger = addBlock('charger', 400, 260, 'charger_01');
    const battery = addBlock('battery', 770, 260, 'battery_01');

    // MONITORING ROW: Digital Energy Meter (Passive Tap, Y = 415, Height = 85)
    const meter = addBlock('meter', 250, 415, 'meter_01');

    // ================= REALISTIC ENGINEERING CONNECTIONS (PRD Sections 1-6) =================
    // 1. High-Voltage Heavy Power Cable: Grid (310, 322) -> Charger (400, 322)
    ConnectionManager.create(grid, grid.ports[0], charger, charger.ports[0], {
      id: 'grid_to_charger',
      label: '11 kV AC BUS',
      type: 'power',
      customPath: () => 'M 310 322 L 400 322'
    });

    // 3. High-Voltage Heavy Power Cable: Charger (680, 322) -> Battery (770, 322)
    ConnectionManager.create(charger, charger.ports[1], battery, battery.ports[0], {
      id: 'charger_to_battery',
      label: '400V DC POWER BUS',
      type: 'power',
      customPath: () => 'M 680 322 L 770 322'
    });

    // 4. Dedicated Control Cable: DRL Controller (540, 230) -> Charger (540, 260)
    ConnectionManager.create(drl, drl.ports[4], charger, charger.ports[2], {
      id: 'controller_to_charger',
      label: 'POWER COMMAND',
      type: 'control',
      customPath: () => 'M 540 230 L 540 260'
    });

    // 5. Data Observation: Electricity Price (540, 113) -> DRL Controller (540, 135)
    ConnectionManager.create(priceInfo, priceInfo.ports[0], drl, drl.ports[0], {
      id: 'price_to_controller',
      label: 'Tariff Signal',
      type: 'data_price',
      customPath: () => 'M 540 113 L 540 135'
    });

    // 6. Data Observation: Renewable Generation (310, 65) -> DRL Controller (400, 165)
    ConnectionManager.create(renewInfo, renewInfo.ports[0], drl, drl.ports[1], {
      id: 'renewable_to_controller',
      label: 'Renewable Feed',
      type: 'data_renew',
      customPath: () => 'M 310 65 L 355 65 L 355 165 L 400 165'
    });

    // 7. Data Observation: Grid Telemetry (170, 260) -> DRL Controller (400, 200)
    ConnectionManager.create(grid, grid.ports[1], drl, drl.ports[2], {
      id: 'grid_to_controller',
      label: 'Grid Telemetry',
      type: 'data_grid',
      customPath: () => 'M 170 260 L 170 200 L 400 200'
    });

    // 8. Data Observation: EV BMS Telemetry (770, 65) -> DRL Controller (680, 155)
    ConnectionManager.create(evInfo, evInfo.ports[1], drl, drl.ports[3], {
      id: 'ev_to_drl',
      label: 'BMS Telemetry',
      type: 'data_ev',
      customPath: () => 'M 770 65 L 725 65 L 725 155 L 680 155'
    });

    // 9. Data Observation: EV Info (910, 113) -> Decision (910, 135)
    ConnectionManager.create(evInfo, evInfo.ports[0], decInfo, decInfo.ports[1], {
      id: 'ev_to_decision',
      label: 'Target & Dep',
      type: 'data_ev',
      customPath: () => 'M 910 113 L 910 135'
    });

    // 10. Control Bus: DRL Controller (680, 190) -> Decision Output (770, 190)
    ConnectionManager.create(drl, drl.ports[5], decInfo, decInfo.ports[0], {
      id: 'controller_to_decision',
      label: 'POLICY SIGNAL',
      type: 'control_bus',
      customPath: () => 'M 680 190 L 770 190'
    });

    // 11. Data Observation: EV Battery BMS (910, 260) -> Decision Log (910, 230)
    ConnectionManager.create(battery, battery.ports[1], decInfo, decInfo.ports[2], {
      id: 'battery_to_decision',
      label: 'BMS Feedback',
      type: 'data_ev',
      customPath: () => 'M 910 260 L 910 230'
    });

    // 12. Passive Metering Sense Tap: Meter (355, 415) -> AC Bus Cable at (355, 322)
    ConnectionManager.create(meter, meter.ports[0], charger, charger.ports[0], {
      id: 'meter_tap',
      label: 'CT/PT SENSE TAP',
      type: 'measurement',
      customPath: () => 'M 355 322 L 355 415'
    });

    // Explicitly guarantee no stale or cached green feed wire can ever exist
    connections = connections.filter(c => c && c.id !== 'renew_to_grid' && c.connectionType !== 'power_renew' && (!c.label || !c.label.includes('GREEN FEED')));

    selectedNodeId = 'drl_01';
    renderAllNodes();
    renderAllWires();
    renderInspector();
    updateSystemStatusSidebar();
    updateEnergyMeterBar();
  }

  // ================= 15. WEBSOCKET REAL-TIME SYNC & HEALTH HEARTBEAT =================
  let lastMessageTime = Date.now();
  let lastSeqNumber = -1;
  let seqStalledTicks = 0;
  let totalSamplesCount = 0;

  function checkConnectionHealth() {
    const ageSec = (Date.now() - lastMessageTime) / 1000;
    const dbgAge = document.getElementById('dbg-age');
    const dbgSamples = document.getElementById('dbg-samples');
    const wsBadge = document.getElementById('ws-status-badge');
    const sysBadge = document.getElementById('sys-status-badge');
    const dataModeLabel = document.getElementById('data-mode-label');
    const stripSimStatus = document.getElementById('strip-sim-status');
    const stHeartbeat = document.getElementById('st-heartbeat');

    if (dbgSamples) dbgSamples.textContent = `${totalSamplesCount} / 300`;

    const isOffline = !isWsConnected || ageSec > 10;
    const isStale = !isOffline && (ageSec > 3);
    const isStalled = !isOffline && !isStale && (seqStalledTicks >= 4);

    if (isOffline) {
      if (dbgAge) { dbgAge.textContent = `${ageSec.toFixed(1)}s (OFFLINE)`; dbgAge.className = 'text-rose-400 font-bold'; }
      if (wsBadge) {
        wsBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40 flex items-center gap-1';
        wsBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span> ● OFFLINE';
      }
      if (sysBadge) {
        sysBadge.className = 'text-[10px] bg-rose-500/20 text-rose-400 border border-rose-500/40 px-2 py-0.5 rounded font-mono font-bold';
        sysBadge.textContent = '● OFFLINE';
      }
      if (dataModeLabel) dataModeLabel.textContent = '● OFFLINE';
      if (stripSimStatus) { stripSimStatus.textContent = '● OFFLINE'; stripSimStatus.className = 'text-rose-400 text-[9px] font-bold'; }
      if (stHeartbeat) stHeartbeat.textContent = 'Disconnected';
    } else if (isStale) {
      if (dbgAge) { dbgAge.textContent = `${ageSec.toFixed(1)}s (STALE)`; dbgAge.className = 'text-amber-400 font-bold'; }
      if (wsBadge) {
        wsBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40 flex items-center gap-1';
        wsBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> ▲ STALE';
      }
      if (sysBadge) {
        sysBadge.className = 'text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/40 px-2 py-0.5 rounded font-mono font-bold';
        sysBadge.textContent = '▲ STALE';
      }
      if (dataModeLabel) dataModeLabel.textContent = '▲ STALE';
      if (stripSimStatus) { stripSimStatus.textContent = '▲ STALE'; stripSimStatus.className = 'text-amber-400 text-[9px] font-bold'; }
      if (stHeartbeat) stHeartbeat.textContent = `Delayed (${ageSec.toFixed(1)}s)`;
    } else if (isStalled) {
      if (dbgAge) { dbgAge.textContent = `${ageSec.toFixed(1)}s (STALLED)`; dbgAge.className = 'text-amber-400 font-bold'; }
      if (wsBadge) {
        wsBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40 flex items-center gap-1';
        wsBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> ▲ STALLED';
      }
      if (sysBadge) {
        sysBadge.className = 'text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/40 px-2 py-0.5 rounded font-mono font-bold';
        sysBadge.textContent = '▲ STALLED';
      }
      if (dataModeLabel) dataModeLabel.textContent = '▲ STALLED';
      if (stripSimStatus) { stripSimStatus.textContent = '▲ TELEMETRY STALLED'; stripSimStatus.className = 'text-amber-400 text-[9px] font-bold'; }
      if (stHeartbeat) stHeartbeat.textContent = 'Sequence Stalled';
    } else {
      if (dbgAge) { dbgAge.textContent = `${ageSec.toFixed(1)}s (LIVE)`; dbgAge.className = 'text-emerald-400 font-bold'; }
      if (wsBadge) {
        wsBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center gap-1';
        wsBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> LIVE WS';
      }
      if (sysBadge) {
        sysBadge.className = 'text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 px-2 py-0.5 rounded font-mono font-bold';
        sysBadge.textContent = 'ONLINE';
      }
      if (dataModeLabel) dataModeLabel.textContent = '● LIVE';
      if (stripSimStatus) { stripSimStatus.textContent = '● CONTINUOUS LIVE'; stripSimStatus.className = 'text-emerald-400 text-[9px] font-bold'; }
      if (stHeartbeat) stHeartbeat.textContent = 'Active WebSocket (0 latency)';
    }
  }

  function updateDebugInspector(data, authoritativePowerKw) {
    const dbgSeq = document.getElementById('dbg-seq');
    const dbgTime = document.getElementById('dbg-time');
    const dbgBat = document.getElementById('dbg-bat');
    const dbgMeter = document.getElementById('dbg-meter');
    const dbgDt = document.getElementById('dbg-dt');
    const dbgStress = document.getElementById('dbg-stress');

    const seq = data.sequence !== undefined ? data.sequence : (telemetryState.sequence || 0);
    const timeStr = data.sim_time || (data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '--:--:--');
    const soc = telemetryState.evSoc !== undefined ? Number(telemetryState.evSoc) : 64.2;
    const energy = telemetryState.evEnergyKwh !== undefined ? Number(telemetryState.evEnergyKwh) : 46.22;
    const dt = data.last_tick_dt !== undefined ? Number(data.last_tick_dt) : 1.0;
    const stressScore = data.grid && data.grid.stress_score !== undefined ? data.grid.stress_score : (telemetryState.gridStressScore || 42);
    const gridCond = data.grid && (data.grid.grid_stress || data.grid.grid_state) ? (data.grid.grid_stress || data.grid.grid_state) : (telemetryState.gridStatus || 'NORMAL');

    if (dbgSeq) dbgSeq.textContent = `#${seq}`;
    if (dbgTime) dbgTime.textContent = timeStr;
    if (dbgDt) dbgDt.textContent = `${dt.toFixed(3)}s (LIVE)`;
    if (dbgBat) dbgBat.textContent = `${soc.toFixed(2)}% / ${energy.toFixed(2)} kWh`;
    if (dbgStress) dbgStress.textContent = `${Number(stressScore).toFixed(0)}/100 (${gridCond})`;
    if (dbgMeter) {
      const net = telemetryState.meterNetKw !== undefined ? telemetryState.meterNetKw : authoritativePowerKw;
      const dir = telemetryState.meterDirection || (authoritativePowerKw > 0.05 ? 'GRID -> EV' : (authoritativePowerKw < -0.05 ? 'EV -> GRID' : 'IDLE'));
      dbgMeter.textContent = `${net >= 0 ? '+' : ''}${net.toFixed(1)} kW (${dir})`;
    }

    const hdrVal = document.getElementById('hdr-power-val');
    if (hdrVal) {
      if (authoritativePowerKw > 0.05) {
        hdrVal.textContent = `GRID → EV (+${authoritativePowerKw.toFixed(1)} kW)`;
        hdrVal.className = 'font-bold text-emerald-400';
      } else if (authoritativePowerKw < -0.05) {
        hdrVal.textContent = `EV → GRID (-${Math.abs(authoritativePowerKw).toFixed(1)} kW)`;
        hdrVal.className = 'font-bold text-cyan-400';
      } else {
        hdrVal.textContent = 'IDLE (0.0 kW)';
        hdrVal.className = 'font-bold text-slate-400';
      }
    }
  }

  function initWebSocket() {
    const host = window.location.host || '127.0.0.1:8000';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${host}/ws/simulation`;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        isWsConnected = true;
        lastMessageTime = Date.now();
        checkConnectionHealth();
        updateWiresLiveState(telemetryState.chargerPowerKw || 0.0);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleIncomingTelemetry(data);
        } catch (e) {}
      };

      ws.onclose = () => {
        isWsConnected = false;
        checkConnectionHealth();
        updateWiresLiveState(0.0);
        setTimeout(initWebSocket, 3000);
      };

      ws.onerror = () => {
        isWsConnected = false;
        checkConnectionHealth();
        updateWiresLiveState(0.0);
        if (ws) ws.close();
      };
    } catch (err) {
      console.warn("WebSocket initialization notice:", err);
    }
  }

  function handleIncomingTelemetry(rawMsg) {
    if (!rawMsg) return;
    const data = rawMsg.state || (rawMsg.data && rawMsg.data.step_data) || rawMsg.data || rawMsg;
    if (!data) return;

    lastMessageTime = Date.now();
    if (data.sequence !== undefined) {
      if (data.sequence === lastSeqNumber) {
        seqStalledTicks++;
      } else {
        seqStalledTicks = 0;
        lastSeqNumber = data.sequence;
      }
    }
    totalSamplesCount++;

    if (data.circuit) {
      telemetryState.circuit = data.circuit;
      telemetryState.circuitConnections = data.circuit.connections;
      telemetryState.circuitEnergyBalance = data.circuit.energy_balance;
      telemetryState.circuitDirection = data.circuit.direction;
      telemetryState.circuitLosses = data.circuit.losses;
    }

    if (data.sequence !== undefined) {
      telemetryState.sequence = data.sequence;
      const elSeq = document.getElementById('strip-seq');
      const elTbSeq = document.getElementById('tb-backend-seq');
      if (elSeq) elSeq.textContent = `#${data.sequence}`;
      if (elTbSeq) elTbSeq.textContent = `#${data.sequence}`;
    }

    if (data.simulation_time || data.sim_time || data.timestamp) {
      const timeStr = data.simulation_time || data.sim_time || (data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '--:--:--');
      const elSimTime = document.getElementById('strip-sim-time');
      const elTbTime = document.getElementById('tb-backend-time');
      if (elSimTime) elSimTime.textContent = timeStr;
      if (elTbTime) elTbTime.textContent = timeStr;
    }

    if (data.grid) {
      telemetryState.gridDemandGw = data.grid.demand_gw !== undefined ? data.grid.demand_gw : telemetryState.gridDemandGw;
      telemetryState.gridDemandMw = data.grid.demand_mw !== undefined ? data.grid.demand_mw : telemetryState.gridDemandMw;
      telemetryState.gridSupplyGw = data.grid.supply_gw !== undefined ? data.grid.supply_gw : telemetryState.gridSupplyGw;
      telemetryState.gridMarginGw = data.grid.margin_gw !== undefined ? data.grid.margin_gw : (telemetryState.gridSupplyGw - telemetryState.gridDemandGw);
      telemetryState.gridFrequencyHz = data.grid.frequency_hz !== undefined ? data.grid.frequency_hz : telemetryState.gridFrequencyHz;
      telemetryState.gridStatus = data.grid.grid_stress || data.grid.grid_state || telemetryState.gridStatus;
    }
    if (data.price) {
      telemetryState.marketPrice = data.price.mcp_inr_per_kwh !== undefined ? data.price.mcp_inr_per_kwh : telemetryState.marketPrice;
      telemetryState.marketBlock = data.price.current_block || telemetryState.marketBlock;
      telemetryState.priceState = data.price.price_state || telemetryState.priceState;
    }
    if (data.renewable) {
      telemetryState.solarGw = data.renewable.solar_gw !== undefined ? data.renewable.solar_gw : telemetryState.solarGw;
      telemetryState.windGw = data.renewable.wind_gw !== undefined ? data.renewable.wind_gw : telemetryState.windGw;
      telemetryState.hydroGw = data.renewable.hydro_gw !== undefined ? data.renewable.hydro_gw : telemetryState.hydroGw;
      telemetryState.renewableTotalGw = data.renewable.total_renewable_gw !== undefined ? data.renewable.total_renewable_gw : (telemetryState.solarGw + telemetryState.windGw + telemetryState.hydroGw);
      telemetryState.renewableSharePct = data.renewable.renewable_share_pct !== undefined ? data.renewable.renewable_share_pct : telemetryState.renewableSharePct;
    }
    if (data.ev) {
      telemetryState.evSoc = data.ev.soc !== undefined ? data.ev.soc : telemetryState.evSoc;
      telemetryState.evRequiredSoc = data.ev.required_soc || telemetryState.evRequiredSoc;
      telemetryState.evDepartureTime = data.ev.departure_time || telemetryState.evDepartureTime;
      telemetryState.evCapacityKwh = data.ev.capacity_kwh || telemetryState.evCapacityKwh;
      telemetryState.evEnergyKwh = data.ev.energy_kwh || ((telemetryState.evSoc / 100) * telemetryState.evCapacityKwh);
    }

    // Single Source of Truth for Power:
    let authoritativePowerKw = 0.0;
    if (data.circuit && data.circuit.circuit_power_kw !== undefined) {
      authoritativePowerKw = data.circuit.circuit_power_kw;
    } else if (data.actual_power_kw !== undefined) {
      authoritativePowerKw = data.actual_power_kw;
    } else if (data.charger && data.charger.power_kw !== undefined) {
      authoritativePowerKw = data.charger.power_kw;
    } else if (data.controller && (data.controller.command_kw !== undefined || data.controller.power_kw !== undefined)) {
      authoritativePowerKw = data.controller.command_kw !== undefined ? data.controller.command_kw : data.controller.power_kw;
    } else if (data.battery && data.battery.power_kw !== undefined) {
      authoritativePowerKw = data.battery.power_kw;
    }

    const authAction = data.current_action || (data.controller && data.controller.action) || '';
    if ((authAction === 'CHARGING' || authAction === 'CHARGE') && authoritativePowerKw <= 0.05) {
      if (data.ev && data.ev.soc < (data.ev.target_soc || 80.0)) {
        authoritativePowerKw = (data.ev && data.ev.max_charge_kw) || 22.0;
      }
    }

    telemetryState.chargerPowerKw = authoritativePowerKw;
    telemetryState.drlPowerKw = authoritativePowerKw;
    telemetryState.simEvImpactKw = authoritativePowerKw;
    telemetryState.simManagedLoadGw = (telemetryState.gridDemandGw || 13.74) + (authoritativePowerKw / 1000000.0);

    if (authoritativePowerKw > 0.05) {
      telemetryState.chargerMode = 'G2V CHARGING';
      telemetryState.drlAction = 'CHARGE';
      telemetryState.batteryState = 'CHARGING';
      telemetryState.meterDirection = 'GRID -> EV';
      telemetryState.meterImportKw = authoritativePowerKw;
      telemetryState.meterExportKw = 0.0;
      telemetryState.meterNetKw = authoritativePowerKw;
    } else if (authoritativePowerKw < -0.05) {
      telemetryState.chargerMode = 'V2G DISCHARGE';
      telemetryState.drlAction = 'V2G';
      telemetryState.batteryState = 'V2G';
      telemetryState.meterDirection = 'EV -> GRID';
      telemetryState.meterImportKw = 0.0;
      telemetryState.meterExportKw = Math.abs(authoritativePowerKw);
      telemetryState.meterNetKw = authoritativePowerKw;
    } else {
      telemetryState.chargerMode = 'IDLE';
      telemetryState.drlAction = 'IDLE';
      telemetryState.batteryState = 'IDLE';
      telemetryState.meterDirection = 'NO EV POWER FLOW';
      telemetryState.meterImportKw = 0.0;
      telemetryState.meterExportKw = 0.0;
      telemetryState.meterNetKw = 0.0;
    }

    if (data.meter) {
      if (data.meter.imported_kwh !== undefined) telemetryState.meterImportKwh = data.meter.imported_kwh;
      else if (data.meter.imported_energy_kwh !== undefined) telemetryState.meterImportKwh = data.meter.imported_energy_kwh;

      if (data.meter.exported_kwh !== undefined) telemetryState.meterExportKwh = data.meter.exported_kwh;
      else if (data.meter.exported_energy_kwh !== undefined) telemetryState.meterExportKwh = data.meter.exported_energy_kwh;

      if (data.meter.net_power_kw !== undefined) telemetryState.meterNetKw = data.meter.net_power_kw;
      if (data.meter.imported_power_kw !== undefined) telemetryState.meterImportKw = data.meter.imported_power_kw;
      if (data.meter.exported_power_kw !== undefined) telemetryState.meterExportKw = data.meter.exported_power_kw;
      if (data.meter.direction) telemetryState.meterDirection = data.meter.direction;
    }

    if (data.battery) {
      telemetryState.batteryTimeToTargetStr = data.battery.time_to_target_str || telemetryState.batteryTimeToTargetStr;
      telemetryState.batteryTimeToFullStr = data.battery.time_to_full_str || telemetryState.batteryTimeToFullStr;
      if (data.battery.state) telemetryState.batteryState = data.battery.state;
      if (data.battery.soc !== undefined) telemetryState.evSoc = data.battery.soc;
      if (data.battery.energy_kwh !== undefined) telemetryState.evEnergyKwh = data.battery.energy_kwh;
    }

    if (data.controller) {
      if (data.controller.departure_urgency !== undefined) {
        telemetryState.drlUrgencyPct = Math.round(data.controller.departure_urgency * 100);
      }
      if (data.controller.reason) {
        telemetryState.decisionReason = data.controller.reason;
      }
    }
    if (data.decision) {
      if (data.decision.reason) telemetryState.decisionReason = data.decision.reason;
      if (data.decision.reason_code) telemetryState.decisionCode = data.decision.reason_code;
    }
    if (data.health) {
      const elHealth = document.getElementById('strip-data-health');
      if (elHealth) elHealth.textContent = data.health.overall || '100% HEALTHY';
    }

    syncNodesFromState();
    updateNodesLiveValues(data);
    updateWiresLiveState(authoritativePowerKw);
    updateSystemStatusSidebar();
    updateEnergyMeterBar();
    updateLiveStatusStrip(data);
    updateDebugInspector(data, authoritativePowerKw);
    appendTelemetryPointToCharts(data);
  }

  // ================= 16. MODAL HANDLERS & NOTIFICATIONS =================
  function openBatteryModal(nodeId) {
    openBatteryNodeId = nodeId || 'battery_01';
    const modal = document.getElementById('battery-internal-modal');
    if (modal) modal.classList.remove('hidden');
    updateBatteryModalLive();
  }

  function closeBatteryModal() {
    const modal = document.getElementById('battery-internal-modal');
    if (modal) modal.classList.add('hidden');
    openBatteryNodeId = null;
  }

  function updateBatteryModalLive() {
    const soc = telemetryState.evSoc;
    document.querySelectorAll('.batt-modal-soc').forEach(el => {
      el.textContent = `${soc.toFixed(1)}%`;
    });
    document.querySelectorAll('.batt-modal-bar').forEach(el => {
      el.style.width = `${Math.min(100, Math.max(0, soc))}%`;
    });
    const stateEl = document.getElementById('batt-modal-state');
    if (stateEl) {
      stateEl.textContent = telemetryState.chargerMode === 'V2G' ? 'V2G DISCHARGING (-10 kW)' : 'G2V CHARGING (+8.4 kW)';
    }
  }

  function openComparisonModal() {
    const modal = document.getElementById('comparison-modal');
    if (modal) modal.classList.remove('hidden');
  }

  function closeComparisonModal() {
    const modal = document.getElementById('comparison-modal');
    if (modal) modal.classList.add('hidden');
  }

  function showToast(message, icon = 'check_circle') {
    const toast = document.getElementById('toast-notification');
    const toastMsg = document.getElementById('toast-message');
    const toastIcon = document.getElementById('toast-icon');
    if (!toast) return;

    toastMsg.textContent = message;
    if (toastIcon) {
      toastIcon.textContent = icon;
      toastIcon.className = icon === 'error'
        ? 'material-symbols-outlined text-rose-400 text-base'
        : 'material-symbols-outlined text-emerald-400 text-base';
    }
    toast.classList.remove('translate-y-12', 'opacity-0', 'pointer-events-none');
    toast.classList.add('translate-y-0', 'opacity-100');

    setTimeout(() => {
      toast.classList.remove('translate-y-0', 'opacity-100');
      toast.classList.add('translate-y-12', 'opacity-0', 'pointer-events-none');
    }, 3200);
  }

  // ================= VIEWPORT ZOOM & FIT CONTROLS =================
  function applyZoom(zoom) {
    currentZoom = Math.max(0.5, Math.min(1.8, Math.round(zoom * 100) / 100));
    const canvasViewport = document.getElementById('sim-canvas-viewport');
    const canvasScaler = document.getElementById('sim-canvas-scaler');
    if (canvasViewport) {
      canvasViewport.style.transform = `scale(${currentZoom})`;
      canvasViewport.style.transformOrigin = '0 0';
    }
    if (canvasScaler) {
      canvasScaler.style.width = `${Math.max(1100, Math.round(1100 * currentZoom))}px`;
      canvasScaler.style.height = `${Math.max(530, Math.round(530 * currentZoom))}px`;
    }
    document.querySelectorAll('.zoom-display-val').forEach(el => {
      el.textContent = `${Math.round(currentZoom * 100)}%`;
    });
  }

  function zoomIn() {
    applyZoom(currentZoom + 0.1);
  }

  function zoomOut() {
    applyZoom(currentZoom - 0.1);
  }

  function resetZoom() {
    applyZoom(1.0);
  }

  function fitZoom(showToastMsg = true) {
    const container = document.getElementById('sim-canvas-container');
    if (container) {
      const availableWidth = container.clientWidth - 20;
      const fitRatio = Math.max(0.55, Math.min(1.05, Math.round((availableWidth / 1100) * 100) / 100));
      applyZoom(fitRatio);
      if (showToastMsg) {
        showToast(`Canvas fitted to ${Math.round(fitRatio * 100)}%`);
      }
    }
  }

  // ================= 17. INITIALIZATION =================
  function init() {
    canvasContainer = document.getElementById('sim-canvas-container');
    canvasSvg = document.getElementById('sim-wires-svg');
    nodesContainer = document.getElementById('sim-nodes-layer');
    inspectorContent = document.getElementById('inspector-content');
    timelineScrubber = document.getElementById('sim-timeline-scrubber');
    timelineLabel = document.getElementById('sim-timeline-label');

    // Setup initial architecture
    setupSystemArchitecture();
    updateLockUi();

    // Data Mode Buttons (LIVE & HISTORICAL)
    const btnLive = document.getElementById('tb-mode-live');
    const btnHist = document.getElementById('tb-mode-hist');
    if (btnLive) btnLive.onclick = () => setDataMode('LIVE');
    if (btnHist) btnHist.onclick = () => setDataMode('HISTORICAL');

    // Viewport Zoom & Fit Controls
    document.querySelectorAll('#canvas-zoom-in, [onclick*="zoomIn"]').forEach(btn => {
      btn.onclick = () => zoomIn();
    });
    document.querySelectorAll('#canvas-zoom-out, [onclick*="zoomOut"]').forEach(btn => {
      btn.onclick = () => zoomOut();
    });
    document.querySelectorAll('#canvas-zoom-reset, [onclick*="resetZoom"]').forEach(btn => {
      btn.onclick = () => resetZoom();
    });
    document.querySelectorAll('#canvas-zoom-fit, [onclick*="fitZoom"]').forEach(btn => {
      btn.onclick = () => fitZoom(true);
    });

    // Mouse wheel zoom with Ctrl key
    const canvasContainer = document.getElementById('sim-canvas-container');
    if (canvasContainer) {
      canvasContainer.addEventListener('wheel', (e) => {
        if (e.ctrlKey) {
          e.preventDefault();
          if (e.deltaY < 0) zoomIn();
          else zoomOut();
        }
      }, { passive: false });
    }

    // Auto-fit circuit to viewport width so all 8 blocks and wires are 100% visible
    setTimeout(() => {
      fitZoom(false);
    }, 60);

    window.addEventListener('resize', () => {
      fitZoom(false);
    });

    // Analytics Drawer Collapsible Toggle
    const toggleAnalyticsBtn = document.getElementById('toggle-analytics-btn');
    const drawerCollapseBtn = document.getElementById('drawer-collapse-btn');
    const analyticsDrawer = document.getElementById('analytics-drawer');
    const drawerStatusPill = document.getElementById('analytics-drawer-status-pill');
    const drawerCollapseIcon = document.getElementById('drawer-collapse-icon');
    const drawerCollapseLabel = document.getElementById('drawer-collapse-label');
    let isDrawerOpen = true;

    function toggleAnalyticsDrawer() {
      isDrawerOpen = !isDrawerOpen;
      if (analyticsDrawer) {
        if (isDrawerOpen) {
          analyticsDrawer.classList.remove('hidden');
          if (drawerStatusPill) {
            drawerStatusPill.textContent = 'OPEN';
            drawerStatusPill.className = 'px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-emerald-500/20 text-emerald-600 dark:text-emerald-400';
          }
          if (drawerCollapseIcon) drawerCollapseIcon.textContent = 'expand_more';
          if (drawerCollapseLabel) drawerCollapseLabel.textContent = 'COLLAPSE';
          setTimeout(() => {
            Object.values(chartInstances).forEach(c => { if (c && typeof c.resize === 'function') c.resize(); });
          }, 150);
        } else {
          analyticsDrawer.classList.add('hidden');
          if (drawerStatusPill) {
            drawerStatusPill.textContent = 'CLOSED';
            drawerStatusPill.className = 'px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400';
          }
          if (drawerCollapseIcon) drawerCollapseIcon.textContent = 'expand_less';
          if (drawerCollapseLabel) drawerCollapseLabel.textContent = 'EXPAND';
        }
      }
    }

    if (toggleAnalyticsBtn) toggleAnalyticsBtn.onclick = toggleAnalyticsDrawer;
    if (drawerCollapseBtn) drawerCollapseBtn.onclick = toggleAnalyticsDrawer;

    // Sidebar Accordions
    document.querySelectorAll('.sidebar-section-header').forEach(hdr => {
      hdr.onclick = () => {
        const nextElem = hdr.nextElementSibling;
        if (nextElem) {
          nextElem.classList.toggle('hidden');
        }
      };
    });

    // Strategy Selector
    const stratSelect = document.getElementById('tb-strategy-select');
    if (stratSelect) stratSelect.onchange = (e) => {
      activeStrategy = e.target.value;
      showToast(`Strategy set to ${stratSelect.options[stratSelect.selectedIndex].text}`);
    };

    // Scenario Trigger Controls
    const btnScenNorm = document.getElementById('btn-scen-normal');
    const btnScenHigh = document.getElementById('btn-scen-highload');
    if (btnScenNorm) {
      btnScenNorm.onclick = () => {
        fetch('/api/simulation/scenario', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ scenario: 'normal' })
        }).then(() => showToast('Grid Scenario: Normal Peak (Stress ~42)'));
        try { if (ws && isWsConnected) ws.send(JSON.stringify({ command: 'scenario', scenario: 'normal' })); } catch(e){}
      };
    }
    if (btnScenHigh) {
      btnScenHigh.onclick = () => {
        fetch('/api/simulation/trigger-load', { method: 'POST' })
          .then(() => showToast('Triggered High Grid Load: Stress Surging >= 75'));
        try { if (ws && isWsConnected) ws.send(JSON.stringify({ command: 'trigger_load' })); } catch(e){}
      };
    }

    // Auto-fetch authoritative live state on startup
    fetch('/api/live/state')
      .then(res => res.json())
      .then(data => {
        if (data) handleIncomingTelemetry(data);
      })
      .catch(() => {});

    // Connect Telemetry WebSocket & Health Heartbeat Monitor
    initWebSocket();
    setInterval(checkConnectionHealth, 500);

    // Theme System
    initTheme();
    const themeBtn = document.getElementById('tb-theme-toggle');
    if (themeBtn) themeBtn.onclick = toggleTheme;

    // Responsive Analytics Charts Initialization
    initCharts();

    // Chart Window Buttons
    document.querySelectorAll('.chart-window-btn').forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll('.chart-window-btn').forEach(b => {
          b.className = 'chart-window-btn px-2 py-1 rounded text-slate-400 hover:text-slate-200 text-[11px]';
        });
        btn.className = 'chart-window-btn px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/40 text-[11px]';
        const win = btn.getAttribute('data-window');
        activeChartWindowSec = win === 'live' ? 'live' : parseInt(win, 10);
        fetchTelemetryHistory();
      };
    });

    // Chart Follow Toggle
    const followBtn = document.getElementById('chart-follow-toggle');
    if (followBtn) {
      followBtn.onclick = () => {
        isChartFollowPaused = !isChartFollowPaused;
        const icon = document.getElementById('chart-follow-icon');
        const lbl = document.getElementById('chart-follow-label');
        if (icon) icon.textContent = isChartFollowPaused ? 'play_arrow' : 'pause';
        if (lbl) lbl.textContent = isChartFollowPaused ? 'RESUME FOLLOW' : 'PAUSE FOLLOW';
      };
    }

    // Node Click Handlers
    if (nodesContainer) {
      nodesContainer.onclick = (e) => {
        const nodeEl = e.target.closest('.sim-node');
        if (nodeEl) {
          const nodeId = nodeEl.getAttribute('data-node-id');
          selectNode(nodeId);
        }
      };
    }
  }

  async function validateAndConnect(fromComp, fromPort, toComp, toPort) {
    try {
      const res = await fetch("/api/circuit/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_component: fromComp,
          from_port: fromPort,
          to_component: toComp,
          to_port: toPort
        })
      });
      const data = await res.json();
      if (!data.valid) {
        showToast(`⚠️ Electrical Error: ${data.message}`, 'error');
        return false;
      }
      showToast(`Circuit connection verified: ${fromComp} -> ${toComp}`, 'check_circle');
      return true;
    } catch(err) {
      console.warn("Connection validation notice:", err);
      return false;
    }
  }

  return {
    init,
    selectNode,
    setInspectorTab,
    toggleEditMode,
    cancelEditMode,
    saveEditMode,
    setDataMode,
    startSimulation,
    pauseSimulation,
    stopSimulation,
    resetSimulation,
    setSpeed,
    toggleTheme,
    applyTheme,
    fetchTelemetryHistory,
    openBatteryModal,
    closeBatteryModal,
    openComparisonModal,
    closeComparisonModal,
    validateAndConnect,
    zoomIn,
    zoomOut,
    resetZoom,
    fitZoom,
    applyZoom
  };
})();

// Bootstrap
document.addEventListener('DOMContentLoaded', () => {
  LabWorkspace.init();
});
