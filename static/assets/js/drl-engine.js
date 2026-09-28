// GridWise AI - Deep Reinforcement Learning (DRL) Policy Optimizer Engine

const DRLEngine = (function() {
  let activeAlgorithm = 'PPO'; // 'PPO', 'DQN', 'SAC'
  let isTraining = true;
  let currentEpisode = 347;
  const totalEpisodes = 500;
  let trainTimer = null;
  const subscribers = new Set();

  // Training Hyperparameters
  const hyperparams = {
    episodes: 500,
    learningRate: 0.0003,
    batchSize: 64,
    gamma: 0.99,
    gaeLambda: 0.95,
    clipRange: 0.2,
    envMode: "Multi-EV Fleet",
    randomSeed: 42
  };

  // Real-time Loss and Reward History for animated curves
  let rewardHistory = [];
  let maHistory = [];
  let policyLossHistory = [];
  let valueLossHistory = [];

  // Initialize synthetic historical convergence curve up to episode 347
  async function fetchLiveTrainingStatus() {
    try {
      const res = await fetch("/api/ai/training/status");
      if (res.ok) {
        const data = await res.json();
        if (data.episodes_trained) currentEpisode = data.episodes_trained;
        if (data.training_curves && Array.isArray(data.training_curves) && data.training_curves.length > 0) {
          rewardHistory = data.training_curves.map((pt, idx) => ({
            ep: pt.episode || idx + 1,
            reward: pt.reward !== undefined ? pt.reward : pt.mean_reward || 0.0
          }));
          let m = 0;
          maHistory = rewardHistory.map((pt, idx) => {
            m = idx === 0 ? pt.reward : (m * 0.9 + pt.reward * 0.1);
            return { ep: pt.ep, ma: parseFloat(m.toFixed(2)) };
          });
        }
        isTraining = data.status === "running";
        broadcast();
      }
    } catch (e) {
      // Backend status poll notice
    }
  }

  function initHistory() {
    fetchLiveTrainingStatus();
  }

  initHistory();

  function getState() {
    const progressPct = ((currentEpisode / totalEpisodes) * 100).toFixed(1);
    const lastReward = rewardHistory[rewardHistory.length - 1]?.reward || 182.4;
    const lastMA = maHistory[maHistory.length - 1]?.ma || 165.8;

    // Observation tensor s_t ∈ ℝ^12
    const obsVector = [
      0.887,  // Grid Net Demand normalized
      0.940,  // TOU price normalized
      0.923,  // Diurnal sin(t)
      -0.384, // Diurnal cos(t)
      0.720,  // Mean fleet SOC
      0.080,  // Departure reserve margin
      0.412,  // Average dwell remaining
      0.003,  // Frequency deviation
      0.120,  // Substation headroom
      0.640,  // Active charger occupancy
      0.812,  // Solar PV injection
      0.231   // Battery temperature state
    ];

    return {
      activeAlgorithm,
      isTraining,
      currentEpisode,
      totalEpisodes,
      progressPct,
      hyperparams,
      metrics: {
        currentReward: lastReward,
        movingAvg: lastMA,
        bestReward: 211.6,
        policyLoss: "0.0142",
        valueLoss: "0.0890",
        entropy: "0.342",
        stepReward: "+18.42",
        degradationPenalty: "-0.14",
        gradNorm: "0.48",
        explainedVar: "0.942"
      },
      action: {
        type: "V2G DISCHARGE",
        powerSetpointKw: -4.5,
        totalFleetInjectionKw: -135.0,
        gaussianMean: -0.608,
        gaussianVariance: 0.084
      },
      obsVector,
      rewardHistory: rewardHistory.slice(-60), // Last 60 episodes for sparklines
      maHistory: maHistory.slice(-60)
    };
  }

  function broadcast() {
    const state = getState();
    subscribers.forEach(cb => {
      try { cb(state); } catch(e) { console.error("DRL subscriber error:", e); }
    });
  }

  async function advanceStep() {
    await fetchLiveTrainingStatus();
  }

  function start() {
    if (trainTimer) clearInterval(trainTimer);
    isTraining = true;
    trainTimer = setInterval(() => {
      advanceStep();
    }, 3000);
    broadcast();
  }

  function pause() {
    isTraining = false;
    if (trainTimer) {
      clearInterval(trainTimer);
      trainTimer = null;
    }
    broadcast();
  }

  function toggleTraining() {
    if (isTraining) pause();
    else start();
  }

  function reset() {
    currentEpisode = 1;
    initHistory();
    broadcast();
  }

  function setAlgorithm(algo) {
    activeAlgorithm = algo;
    broadcast();
  }

  function updateHyperparams(newParams) {
    Object.assign(hyperparams, newParams);
    broadcast();
  }

  function subscribe(cb) {
    subscribers.add(cb);
    cb(getState());
    return () => subscribers.delete(cb);
  }

  // Start background training simulator
  start();

  return {
    start,
    pause,
    toggleTraining,
    reset,
    setAlgorithm,
    updateHyperparams,
    getState,
    subscribe
  };
})();

