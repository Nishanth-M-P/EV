// GridWise AI - Master Application Controller & Router

const App = (function() {
  let currentPath = 'overview';

  function init() {
    setupNavigation();
    setupHeaderControls();
    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);

    // Subscribe to Simulation Engine
    SimEngine.subscribe(updateGlobalTelemetry);

    // Subscribe to DRL Engine
    DRLEngine.subscribe(updateDRLTelemetry);
  }

  function setupNavigation() {
    const navLinks = document.querySelectorAll('aside nav a[data-path]');
    navLinks.forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const path = link.getAttribute('data-path');
        window.location.hash = `#${path}`;
      });
    });
  }

  function handleHashChange() {
    const hash = window.location.hash.replace('#', '') || 'overview';
    navigateTo(hash);
  }

  function navigateTo(path) {
    currentPath = path;

    // Update nav links styling
    const navLinks = document.querySelectorAll('aside nav a[data-path]');
    navLinks.forEach(link => {
      const p = link.getAttribute('data-path');
      if (p === path) {
        link.setAttribute('aria-current', 'page');
        link.className = "flex items-center gap-space-sm px-space-md py-space-sm rounded-lg transition-all bg-primary-container text-on-primary-container font-semibold shadow-[0_0_12px_-2px_rgba(16,185,129,0.35)]";
      } else {
        link.removeAttribute('aria-current');
        link.className = "flex items-center gap-space-sm px-space-md py-space-sm rounded-lg text-on-surface-variant font-body-sm text-body-sm hover:bg-surface-container-high hover:text-on-surface transition-all";
      }
    });

    // Hide all view containers and show current one
    const views = document.querySelectorAll('.view-container');
    views.forEach(v => {
      if (v.id === `view-${path}`) {
        v.classList.remove('hidden');
      } else {
        v.classList.add('hidden');
      }
    });

    // Run view-specific initialization
    onViewMounted(path);
  }

  function onViewMounted(path) {
    if (path === 'ev-fleet') {
      FleetManager.initListeners();
      FleetManager.renderTable('fleet-table-body', true);
    } else if (path === 'overview') {
      FleetManager.renderTable('overview-fleet-table-body', false);
    } else if (path === 'drl-training') {
      initDRLTrainingView();
    } else if (path === 'grid-simulation') {
      initGridSimView();
    } else if (path === 'v2g-control') {
      initV2GControlView();
    } else if (path === 'simulation') {
      initSimulationView();
    } else if (path === 'performance') {
      initPerformanceView();
    } else if (path === 'analytics') {
      initAnalyticsView();
    } else if (path === 'settings') {
      initSettingsView();
    }
  }

  function setupHeaderControls() {
    const playBtn = document.getElementById('hdr-play-btn');
    const pauseBtn = document.getElementById('hdr-pause-btn');
    const stepBtn = document.getElementById('hdr-step-btn');
    const resetBtn = document.getElementById('hdr-reset-btn');

    if (playBtn) playBtn.onclick = () => {
      SimEngine.start();
      FleetManager.showToast("Simulation running (24-Hour Diurnal cycle).", "play_arrow");
    };
    if (pauseBtn) pauseBtn.onclick = () => {
      SimEngine.pause();
      FleetManager.showToast("Simulation paused.", "pause");
    };
    if (stepBtn) stepBtn.onclick = () => {
      SimEngine.stepOnce();
      FleetManager.showToast("Stepped 1 interval (Δt: 15 min).", "redo");
    };
    if (resetBtn) resetBtn.onclick = () => {
      SimEngine.reset();
      FleetManager.showToast("Environment state reset to baseline (T=18:30).", "restart_alt");
    };
  }

  function updateGlobalTelemetry(state) {
    // Header Telemetry
    const gridLoadEl = document.getElementById('hdr-grid-load');
    const tariffEl = document.getElementById('hdr-tariff');
    if (gridLoadEl) gridLoadEl.textContent = `${state.demand.gridTotalMW.toFixed(2)} MW`;
    if (tariffEl) tariffEl.textContent = `₹${state.tariffRate}/kWh`;

    // Overview KPIs
    const kpiEvConnected = document.getElementById('kpi-ev-connected');
    const kpiEvV2g = document.getElementById('kpi-ev-v2g');
    const kpiGridLoad = document.getElementById('kpi-grid-load');
    const kpiPeakShave = document.getElementById('kpi-peak-shave');
    const kpiV2gEnergy = document.getElementById('kpi-v2g-energy');
    const kpiV2gReturn = document.getElementById('kpi-v2g-return');
    const kpiFleetSoc = document.getElementById('kpi-fleet-soc');
    const kpiTimePill = document.getElementById('overview-time-pill');

    if (kpiEvConnected) kpiEvConnected.textContent = `${state.fleet.connected} Connected`;
    if (kpiEvV2g) kpiEvV2g.textContent = `${state.fleet.discharging} V2G`;
    if (kpiGridLoad) kpiGridLoad.textContent = state.demand.gridTotalMW.toFixed(2);
    if (kpiPeakShave) kpiPeakShave.textContent = state.demand.peakShavePct;
    if (kpiV2gEnergy) kpiV2gEnergy.textContent = state.fleet.v2gEnergyKwh.toFixed(1);
    if (kpiV2gReturn) kpiV2gReturn.textContent = `+₹${state.fleet.financialReturn} Return`;
    if (kpiFleetSoc) kpiFleetSoc.textContent = state.fleet.meanSoc;
    if (kpiTimePill) kpiTimePill.textContent = `T+${Math.floor(state.step / 4)}h (${state.timeShort})`;

    // Current Time Marker on Overview SVG
    const timeMarker = document.getElementById('overview-time-marker');
    const timeMarkerDot = document.getElementById('overview-time-marker-dot');
    const timeMarkerText = document.getElementById('overview-time-marker-text');
    if (timeMarker && timeMarkerDot && timeMarkerText) {
      // Map step 0..95 to SVG x=40 to 980
      const x = 40 + (state.step / 95) * 940;
      timeMarker.setAttribute('x1', x);
      timeMarker.setAttribute('x2', x);
      timeMarkerDot.setAttribute('cx', x);
      timeMarkerText.setAttribute('x', Math.max(40, x - 25));
      timeMarkerText.textContent = `T=${state.timeShort}`;
    }

    // Interactive slider on simulation tab
    const simScrubber = document.getElementById('sim-scrubber');
    const simTimeLabel = document.getElementById('sim-time-label');
    if (simScrubber && document.activeElement !== simScrubber) {
      simScrubber.value = state.step;
    }
    if (simTimeLabel) {
      simTimeLabel.textContent = `${state.timeStr} (Step #${state.step})`;
    }
  }

  function updateDRLTelemetry(state) {
    const drlProgressEl = document.getElementById('main-progress-bar');
    const drlEpEl = document.getElementById('drl-ep-counter');
    const drlPctEl = document.getElementById('drl-pct-display');
    const drlRewardEl = document.getElementById('drl-curr-reward');
    const drlMaEl = document.getElementById('drl-ma-reward');
    const drlPolicyLoss = document.getElementById('drl-policy-loss');
    const drlValueLoss = document.getElementById('drl-value-loss');
    const drlEntropy = document.getElementById('drl-entropy');

    if (drlProgressEl) drlProgressEl.style.width = `${state.progressPct}%`;
    if (drlEpEl) drlEpEl.textContent = state.currentEpisode;
    if (drlPctEl) drlPctEl.textContent = `${state.progressPct}%`;
    if (drlRewardEl) drlRewardEl.textContent = `+${state.metrics.currentReward}`;
    if (drlMaEl) drlMaEl.textContent = `+${state.metrics.movingAvg}`;
    if (drlPolicyLoss) drlPolicyLoss.textContent = state.metrics.policyLoss;
    if (drlValueLoss) drlValueLoss.textContent = state.metrics.valueLoss;
    if (drlEntropy) drlEntropy.textContent = state.metrics.entropy;
  }

  function initDRLTrainingView() {
    const algoBtns = document.querySelectorAll('#view-drl-training .algo-btn');
    algoBtns.forEach(btn => {
      btn.onclick = () => {
        algoBtns.forEach(b => {
          b.classList.remove('bg-primary', 'text-on-primary', 'font-semibold', 'shadow-sm');
          b.classList.add('text-on-surface-variant');
        });
        btn.classList.add('bg-primary', 'text-on-primary', 'font-semibold', 'shadow-sm');
        btn.classList.remove('text-on-surface-variant');
        const algo = btn.innerText.trim().split('\n')[0];
        DRLEngine.setAlgorithm(algo);
        FleetManager.showToast(`Active Policy Optimizer switched to ${algo}.`);
      };
    });

    const startBtn = document.getElementById('drl-start-btn');
    const pauseBtn = document.getElementById('drl-pause-btn');
    const resetBtn = document.getElementById('drl-reset-btn');
    const checkpointBtn = document.getElementById('drl-checkpoint-btn');

    if (startBtn) startBtn.onclick = () => {
      DRLEngine.start();
      FleetManager.showToast("DRL policy optimization started.", "play_arrow");
    };
    if (pauseBtn) pauseBtn.onclick = () => {
      DRLEngine.pause();
      FleetManager.showToast("Optimizer paused.", "pause");
    };
    if (resetBtn) resetBtn.onclick = () => {
      DRLEngine.reset();
      FleetManager.showToast("Training rollout buffer reset.", "restart_alt");
    };
    if (checkpointBtn) checkpointBtn.onclick = () => {
      FleetManager.showToast("Policy weights saved to model_checkpoint_ep347.h5", "bookmark");
    };
  }

  function initGridSimView() {
    // Generate interactive IEEE 33-bus node rows
    const tbody = document.getElementById('grid-bus-tbody');
    if (!tbody) return;

    let html = '';
    GridWiseData.IEEE_33_BUS_NODES.forEach(bus => {
      const isEvNode = (bus.id === 14 || bus.id === 18 || bus.id === 22 || bus.id === 7 || bus.id === 25 || bus.id === 30);
      const isV2G = (bus.id === 14 || bus.id === 18);
      const statusColor = (bus.vPu >= 0.98) ? 'text-primary' : (bus.vPu >= 0.95) ? 'text-secondary' : 'text-tertiary';

      html += `
        <tr class="hover:bg-surface-container-high/40 transition-colors">
          <td class="py-2 px-space-md font-telemetry-md font-semibold text-on-surface">BUS-${String(bus.id).padStart(2, '0')}</td>
          <td class="py-2 px-space-md text-on-surface-variant">${bus.type}</td>
          <td class="py-2 px-space-md font-telemetry-sm ${statusColor} font-medium">${bus.vPu.toFixed(3)} p.u.</td>
          <td class="py-2 px-space-md text-right font-telemetry-sm text-on-surface">${bus.pKw} kW</td>
          <td class="py-2 px-space-md text-right font-telemetry-sm text-outline">${bus.qKvar} kVAr</td>
          <td class="py-2 px-space-md text-right font-telemetry-sm">
            ${isV2G ? '<span class="px-2 py-0.5 rounded bg-secondary/15 text-secondary font-label-caps uppercase">V2G INJECTION</span>' :
              isEvNode ? '<span class="px-2 py-0.5 rounded bg-primary/15 text-primary font-label-caps uppercase">EV CHARGING</span>' :
              '<span class="text-outline font-label-caps uppercase">PASSIVE</span>'}
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  }

  function initV2GControlView() {
    const slider = document.getElementById('v2g-shave-slider');
    const valEl = document.getElementById('v2g-shave-val');
    if (slider && valEl) {
      slider.oninput = (e) => {
        valEl.textContent = `${e.target.value} kW / EV`;
      };
    }
  }

  function initSimulationView() {
    const scrubber = document.getElementById('sim-scrubber');
    if (scrubber) {
      scrubber.oninput = (e) => {
        SimEngine.setStep(parseInt(e.target.value, 10));
      };
    }

    const speedBtns = document.querySelectorAll('.speed-btn');
    speedBtns.forEach(btn => {
      btn.onclick = () => {
        speedBtns.forEach(b => {
          b.classList.remove('bg-primary', 'text-on-primary');
          b.classList.add('bg-surface-container', 'text-on-surface-variant');
        });
        btn.classList.add('bg-primary', 'text-on-primary');
        btn.classList.remove('bg-surface-container', 'text-on-surface-variant');
        const spd = parseFloat(btn.getAttribute('data-speed') || 1.0);
        SimEngine.setSpeed(spd);
        FleetManager.showToast(`Simulation playback speed set to ${spd}x`);
      };
    });
  }

  function initPerformanceView() {
    const exportBtn = document.getElementById('export-report-btn');
    if (exportBtn) {
      exportBtn.onclick = () => {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(GridWiseData.BENCHMARK_METRICS, null, 2));
        const dlAnchor = document.createElement('a');
        dlAnchor.setAttribute("href", dataStr);
        dlAnchor.setAttribute("download", "gridwise_scientific_benchmark_report.json");
        dlAnchor.click();
        FleetManager.showToast("Benchmark report exported successfully (JSON).", "download");
      };
    }
  }

  function initAnalyticsView() {
    // Analytics listeners
  }

  function initSettingsView() {
    const saveBtn = document.getElementById('save-settings-btn');
    if (saveBtn) {
      saveBtn.onclick = () => {
        FleetManager.showToast("Simulation parameters & tariff matrix updated.", "save");
      };
    }
  }

  return {
    init,
    navigateTo
  };
})();

// Bootstrap on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

