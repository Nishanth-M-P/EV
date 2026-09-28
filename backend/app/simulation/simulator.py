"""
GridWise AI - Central Simulation Controller
Runs live step-by-step simulations, maintains state, and broadcasts telemetry frames.
"""

import asyncio
import threading
import time
from typing import Dict, Any, List, Optional, Set
import numpy as np

from backend.app.config import AppConfig, settings
from backend.app.simulation.grid import GridModel
from backend.app.simulation.pricing import PricingModel
from backend.app.simulation.ev import EVFleet, EV
from backend.app.simulation.v2g import V2GManager
from backend.app.strategies.uncontrolled import UncontrolledStrategy
from backend.app.strategies.rule_based import RuleBasedStrategy
from backend.app.strategies.drl import DRLStrategy
from backend.app.utils.logger import logger


class SimulationRunner:
    """Thread-safe real-time simulation manager."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or settings
        self.is_running: bool = False
        self.current_step: int = 74 # Default to peak shaving window (18:30)
        self.speed_multiplier: float = 2.0
        self.strategy_name: str = "drl"

        # Build submodels
        self.grid = GridModel(
            duration_hours=self.config.simulation.duration_hours,
            timestep_minutes=self.config.simulation.timestep_minutes,
            base_peak_mw=self.config.grid.base_peak_mw,
            substation_limit_mw=self.config.grid.substation_limit_mw,
            noise_std_mw=self.config.grid.noise_std_mw,
            random_seed=self.config.simulation.random_seed
        )
        self.pricing = PricingModel(
            pricing_type=self.config.pricing.type,
            off_peak_rate=self.config.pricing.off_peak_rate,
            normal_rate=self.config.pricing.normal_rate,
            peak_rate=self.config.pricing.peak_rate
        )
        self.fleet = EVFleet.create_synthetic_fleet(
            fleet_size=self.config.simulation.fleet_size,
            random_seed=self.config.simulation.random_seed
        )
        self.v2g = V2GManager()

        self._load_strategies()

        # Callbacks for telemetry streaming
        self._telemetry_callbacks: Set[Any] = set()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _load_strategies(self):
        self.strategies = {
            "uncontrolled": UncontrolledStrategy(),
            "rule_based": RuleBasedStrategy(),
            "drl": DRLStrategy(model=None)
        }

    def set_drl_model(self, model: Any):
        self.strategies["drl"] = DRLStrategy(model=model)

    def register_telemetry_callback(self, cb: Any):
        self._telemetry_callbacks.add(cb)

    def unregister_telemetry_callback(self, cb: Any):
        self._telemetry_callbacks.discard(cb)

    def get_current_telemetry(self) -> Dict[str, Any]:
        step = self.current_step % self.grid.total_steps
        current_time = self.grid.get_time_hours(step)
        base_demand_mw = self.grid.get_demand(step)
        price = self.pricing.get_price(current_time, base_demand_mw)

        fleet_stats = self.fleet.get_aggregate_telemetry(current_time)
        net_grid_mw = base_demand_mw + fleet_stats["total_ev_power_mw"]

        return {
            "timestamp": self.grid.get_time_str(step) + ":00",
            "step": step,
            "current_time_hours": float(np.round(current_time, 2)),
            "grid_demand_mw": float(np.round(net_grid_mw, 3)),
            "base_demand_mw": float(np.round(base_demand_mw, 3)),
            "electricity_price": float(np.round(price, 2)),
            "total_ev_power_kw": fleet_stats["total_ev_power_kw"],
            "average_soc": fleet_stats["average_soc"],
            "charging_evs": fleet_stats["charging_count"],
            "discharging_evs": fleet_stats["discharging_count"],
            "idle_evs": fleet_stats["idle_count"],
            "strategy": self.strategy_name,
            "v2g_energy_kwh": float(np.round(self.v2g.discharging_energy_kwh, 2)),
            "charging_energy_kwh": float(np.round(self.v2g.charging_energy_kwh, 2)),
            "net_cost": float(np.round(self.v2g.net_cost, 2))
        }

    def step(self) -> Dict[str, Any]:
        step = self.current_step % self.grid.total_steps
        current_time = self.grid.get_time_hours(step)
        base_demand_mw = self.grid.get_demand(step)
        price = self.pricing.get_price(current_time, base_demand_mw)

        # Select strategy
        strategy = self.strategies.get(self.strategy_name, self.strategies["drl"])
        actions = strategy.compute_power_actions(
            fleet=self.fleet,
            current_time_hours=current_time,
            dt_hours=self.grid.dt_hours,
            grid_demand_mw=base_demand_mw,
            electricity_price=price
        )

        step_net_ev_power_kw = 0.0
        for ev in self.fleet:
            req_kw = actions.get(ev.ev_id, 0.0)
            actual_kw, _ = ev.apply_power(req_kw, self.grid.dt_hours, price)
            step_net_ev_power_kw += actual_kw

        # V2G manager
        self.v2g.record_step(
            net_ev_power_kw=step_net_ev_power_kw,
            dt_hours=self.grid.dt_hours,
            electricity_price=price,
            base_grid_power_mw=base_demand_mw
        )

        telemetry = self.get_current_telemetry()
        self.current_step = (self.current_step + 1) % self.grid.total_steps

        # Notify callbacks
        for cb in list(self._telemetry_callbacks):
            try:
                cb(telemetry)
            except Exception as e:
                pass

        return telemetry

    def start(self, strategy: Optional[str] = None, speed: Optional[float] = None):
        if strategy:
            self.strategy_name = strategy
        if speed:
            self.speed_multiplier = speed

        if not self.is_running:
            self.is_running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("SimulationRunner background thread started.")

    def pause(self):
        self.is_running = False
        self._stop_event.set()
        logger.info("SimulationRunner paused.")

    def reset(self):
        self.pause()
        self.current_step = 74 # Default to 18:30
        self.fleet.reset()
        self.v2g.reset()
        logger.info("SimulationRunner state reset.")
        return self.get_current_telemetry()

    def _run_loop(self):
        while not self._stop_event.is_set() and self.is_running:
            self.step()
            sleep_sec = max(0.05, 1.0 / self.speed_multiplier)
            time.sleep(sleep_sec)


# Global singleton instance
simulator = SimulationRunner()

