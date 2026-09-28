// GridWise AI - 24-Hour Diurnal Microgrid Simulation Engine

const SimEngine = (function() {
  let isRunning = true;
  let currentStep = 74; // Step 74 corresponds to 18:30:00 (Peak Shaving window)
  let speedMultiplier = 2.0;
  let intervalTimer = null;
  const subscribers = new Set();

  const demandProfiles = GridWiseData.get24hDemandProfiles();
  let fleetState = GridWiseData.generateFleet();

  // Calculate current state metrics based on active step
  function getState() {
    const step = currentStep % 96;
    const hourInt = Math.floor(step / 4);
    const minInt = (step % 4) * 15;
    const timeStr = `${String(hourInt).padStart(2, '0')}:${String(minInt).padStart(2, '0')}:00`;
    const timeShort = `${String(hourInt).padStart(2, '0')}:${String(minInt).padStart(2, '0')}`;

    const baselineMW = demandProfiles.baseline[step];
    const ruleMW = demandProfiles.ruleBased[step];
    const drlMW = demandProfiles.drlV2G[step];
    const tariffRate = demandProfiles.tariff[step];

    // Compute dynamic fleet telemetry
    let chargingCount = 0;
    let dischargingCount = 0;
    let idleCount = 0;
    let totalChargeKw = 0;
    let totalDischargeKw = 0;
    let totalSoc = 0;

    fleetState.forEach((ev) => {
      totalSoc += ev.soc;
      if (ev.power > 0) {
        chargingCount++;
        totalChargeKw += ev.power;
      } else if (ev.power < 0) {
        dischargingCount++;
        totalDischargeKw += Math.abs(ev.power);
      } else {
        idleCount++;
      }
    });

    const meanSoc = (totalSoc / fleetState.length).toFixed(1);
    const peakShavePct = (((baselineMW - drlMW) / baselineMW) * 100).toFixed(1);
    const busVoltagePu = (0.995 - (drlMW / 7.0) * 0.03).toFixed(3);
    const busVoltageKv = (11.45 * parseFloat(busVoltagePu)).toFixed(2);

    return {
      step,
      timeStr,
      timeShort,
      isRunning,
      speedMultiplier,
      demand: {
        baselineMW,
        ruleMW,
        drlMW,
        gridTotalMW: drlMW,
        peakMW: 6.41,
        substationLimitMW: 7.00,
        peakShavePct: `-${peakShavePct}%`
      },
      tariffRate: tariffRate.toFixed(2),
      fleet: {
        total: fleetState.length,
        connected: chargingCount + dischargingCount + idleCount,
        charging: chargingCount,
        discharging: dischargingCount,
        idle: idleCount,
        totalChargeKw: totalChargeKw.toFixed(1),
        totalDischargeKw: totalDischargeKw.toFixed(1),
        netEvKw: (totalChargeKw - totalDischargeKw).toFixed(1),
        meanSoc: `${meanSoc}%`,
        v2gEnergyKwh: 342.6 + (step * 0.8),
        financialReturn: (2542 + (step * 8.5)).toFixed(0)
      },
      grid: {
        busVoltagePu,
        busVoltageKv,
        busVoltageDelta: `Δ ${(parseFloat(busVoltagePu) - 1.000).toFixed(3)} p.u.`
      }
    };
  }

  function broadcast() {
    const state = getState();
    subscribers.forEach(cb => {
      try { cb(state); } catch (e) { console.error("Sim subscriber error:", e); }
    });
  }

  function advance() {
    currentStep = (currentStep + 1) % 96;

    // Simulate micro SOC and power shifts
    fleetState.forEach(ev => {
      if (ev.power > 0 && ev.soc < ev.targetSoc) {
        ev.soc = Math.min(100, parseFloat((ev.soc + 0.15).toFixed(1)));
        ev.energyExchanged = parseFloat((ev.energyExchanged + 0.1).toFixed(1));
      } else if (ev.power < 0 && ev.soc > 20.0) {
        ev.soc = Math.max(20, parseFloat((ev.soc - 0.12).toFixed(1)));
        ev.energyExchanged = parseFloat((ev.energyExchanged - 0.1).toFixed(1));
      }
    });

    broadcast();
  }

  function start() {
    if (intervalTimer) clearInterval(intervalTimer);
    isRunning = true;
    const intervalMs = Math.max(200, 2000 / speedMultiplier);
    intervalTimer = setInterval(() => {
      advance();
    }, intervalMs);
    broadcast();
  }

  function pause() {
    isRunning = false;
    if (intervalTimer) {
      clearInterval(intervalTimer);
      intervalTimer = null;
    }
    broadcast();
  }

  function togglePlay() {
    if (isRunning) pause();
    else start();
  }

  function stepOnce() {
    pause();
    advance();
  }

  function reset() {
    currentStep = 74; // Reset to 18:30 setpoint
    fleetState = GridWiseData.generateFleet();
    broadcast();
  }

  function setSpeed(spd) {
    speedMultiplier = spd;
    if (isRunning) start();
    else broadcast();
  }

  function setStep(newStep) {
    currentStep = Math.max(0, Math.min(95, newStep));
    broadcast();
  }

  function getFleet() {
    return fleetState;
  }

  function addEv(evData) {
    fleetState.unshift(evData);
    broadcast();
  }

  function updateEv(id, updates) {
    const ev = fleetState.find(e => e.id === id);
    if (ev) {
      Object.assign(ev, updates);
      broadcast();
    }
  }

  function removeEv(id) {
    fleetState = fleetState.filter(e => e.id !== id);
    broadcast();
  }

  function subscribe(callback) {
    subscribers.add(callback);
    callback(getState());
    return () => subscribers.delete(callback);
  }

  // Initialize background simulation loop
  start();

  return {
    start,
    pause,
    togglePlay,
    stepOnce,
    reset,
    setSpeed,
    setStep,
    getState,
    getFleet,
    addEv,
    updateEv,
    removeEv,
    subscribe,
    demandProfiles
  };
})();

