"""
GridWise AI - Electric Vehicle (EV) and Fleet Modeling
Implements the EV data model, connection windows, and fleet orchestrator.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from backend.app.simulation.battery import Battery


@dataclass
class EV:
    ev_id: str
    battery_capacity_kwh: float
    initial_soc: float
    arrival_time: float                     # In hours (0.0 to 24.0)
    departure_time: float                   # In hours (0.0 to 24.0)
    required_departure_soc: float = 0.80
    max_charge_kw: float = 7.4
    max_discharge_kw: float = 5.0
    min_soc: float = 0.20
    max_soc: float = 1.00
    charging_efficiency: float = 0.95
    discharging_efficiency: float = 0.95
    model_name: str = "Standard EV"

    # Internal battery component
    battery: Battery = field(init=False)
    last_power_kw: float = field(init=False, default=0.0)
    total_cost: float = field(init=False, default=0.0)

    def __post_init__(self):
        if self.departure_time <= self.arrival_time:
            raise ValueError(
                f"Departure time ({self.departure_time}) must be after arrival time ({self.arrival_time})"
            )
        self.battery = Battery(
            capacity_kwh=self.battery_capacity_kwh,
            current_soc=self.initial_soc,
            min_soc=self.min_soc,
            max_soc=self.max_soc,
            charging_efficiency=self.charging_efficiency,
            discharging_efficiency=self.discharging_efficiency
        )
        self.last_power_kw = 0.0
        self.total_cost = 0.0

    @property
    def current_soc(self) -> float:
        return self.battery.current_soc

    @property
    def dwell_duration_hours(self) -> float:
        return self.departure_time - self.arrival_time

    def is_connected(self, current_time: float) -> bool:
        """EV is connected at current_time if arrival_time <= current_time < departure_time."""
        return self.arrival_time <= current_time < self.departure_time

    def has_departed(self, current_time: float) -> bool:
        return current_time >= self.departure_time

    def remaining_dwell_hours(self, current_time: float) -> float:
        if not self.is_connected(current_time):
            return 0.0
        return max(0.0, self.departure_time - current_time)

    def departure_soc_satisfied(self) -> bool:
        return self.battery.current_soc >= (self.required_departure_soc - 1e-4)

    def departure_soc_deficit(self) -> float:
        return max(0.0, self.required_departure_soc - self.battery.current_soc)

    def apply_power(self, requested_power_kw: float, dt_hours: float, electricity_price: float = 0.0) -> Tuple[float, float]:
        """
        requested_power_kw: > 0 for charging, < 0 for discharging, == 0 for idle.
        Returns: (actual_power_kw, actual_energy_kwh).
        Note: actual_power_kw > 0 means drawn from grid, < 0 means supplied to grid.
        """
        if requested_power_kw > 0:
            # Charging limit
            target_kw = min(requested_power_kw, self.max_charge_kw)
            actual_kw, energy_kwh = self.battery.charge(target_kw, dt_hours)
            self.last_power_kw = actual_kw
            cost = energy_kwh * electricity_price
            self.total_cost += cost
            return actual_kw, energy_kwh

        elif requested_power_kw < 0:
            # Discharging limit (V2G)
            target_kw = min(abs(requested_power_kw), self.max_discharge_kw)
            actual_kw, energy_kwh = self.battery.discharge(target_kw, dt_hours)
            self.last_power_kw = -actual_kw
            # Revenue credited to EV for V2G injection
            revenue = energy_kwh * electricity_price
            self.total_cost -= revenue
            return -actual_kw, energy_kwh

        else:
            self.last_power_kw = 0.0
            return 0.0, 0.0

    def reset(self):
        self.battery.reset(self.initial_soc)
        self.last_power_kw = 0.0
        self.total_cost = 0.0


class EVFleet:
    """Manages an ensemble of EVs with deterministic random generation."""

    def __init__(self, evs: Optional[List[EV]] = None):
        self.evs: List[EV] = evs or []

    def __len__(self) -> int:
        return len(self.evs)

    def __iter__(self):
        return iter(self.evs)

    def __getitem__(self, index: int) -> EV:
        return self.evs[index]

    @classmethod
    def create_synthetic_fleet(
        cls,
        fleet_size: int = 50,
        random_seed: int = 42
    ) -> "EVFleet":
        """Generates reproducible diverse EV fleet models."""
        rng = np.random.default_rng(random_seed)

        archetypes = [
            {"model": "Tata Nexon EV Max", "capacity": 40.5, "max_charge": 7.2, "max_discharge": 5.0},
            {"model": "Hyundai Ioniq 5", "capacity": 72.6, "max_charge": 11.0, "max_discharge": 10.0},
            {"model": "MG ZS EV", "capacity": 50.3, "max_charge": 7.4, "max_discharge": 5.0},
            {"model": "BYD Atto 3", "capacity": 60.48, "max_charge": 7.0, "max_discharge": 6.0},
            {"model": "Mahindra XUV400", "capacity": 39.4, "max_charge": 7.2, "max_discharge": 5.0},
            {"model": "Kia EV6 GT", "capacity": 77.4, "max_charge": 11.0, "max_discharge": 10.0},
        ]

        ev_list = []
        for i in range(1, fleet_size + 1):
            arch = archetypes[i % len(archetypes)]
            cohort = i % 3

            if cohort == 0:
                # Cohort 1: Evening residential return (40% of fleet)
                # Arrives 17:00 - 19:15 during evening grid peak window, departs late night 23:45
                arrival = float(np.round(rng.uniform(17.0, 19.25), 2))
                departure = 24.0
                initial_soc = float(np.round(rng.uniform(0.25, 0.45), 2))
                required_soc = 0.85
            elif cohort == 1:
                # Cohort 2: Commuter fleet with surplus SOC (30% of fleet)
                # Arrived early morning 07:30 - 09:00, departs 19:30 - 21:00 (available for V2G peak shaving)
                arrival = float(np.round(rng.uniform(7.5, 9.0), 2))
                departure = float(np.round(rng.uniform(19.5, 21.0), 2))
                initial_soc = float(np.round(rng.uniform(0.70, 0.88), 2))
                required_soc = 0.75
            else:
                # Cohort 3: Standard Daytime workplace (30% of fleet)
                arrival = float(np.round(rng.uniform(8.0, 10.0), 2))
                departure = float(np.round(rng.uniform(17.0, 18.5), 2))
                initial_soc = float(np.round(rng.uniform(0.35, 0.55), 2))
                required_soc = 0.80

            ev = EV(
                ev_id=f"EV-{StringPad(i)}",
                battery_capacity_kwh=arch["capacity"],
                initial_soc=initial_soc,
                arrival_time=arrival,
                departure_time=departure,
                required_departure_soc=required_soc,
                max_charge_kw=arch["max_charge"],
                max_discharge_kw=arch["max_discharge"],
                model_name=arch["model"]
            )
            ev_list.append(ev)

        return cls(evs=ev_list)

    def get_connected_evs(self, current_time: float) -> List[EV]:
        return [ev for ev in self.evs if ev.is_connected(current_time)]

    def get_aggregate_telemetry(self, current_time: float) -> Dict[str, Any]:
        connected = self.get_connected_evs(current_time)
        departed = [ev for ev in self.evs if ev.has_departed(current_time)]

        charging = [ev for ev in connected if ev.last_power_kw > 0.05]
        discharging = [ev for ev in connected if ev.last_power_kw < -0.05]
        idle = [ev for ev in connected if abs(ev.last_power_kw) <= 0.05]

        total_power_kw = sum(ev.last_power_kw for ev in connected)
        avg_soc = np.mean([ev.current_soc for ev in self.evs]) if self.evs else 0.0

        compliant_departed = [ev for ev in departed if ev.departure_soc_satisfied()]
        compliance_pct = (len(compliant_departed) / len(departed) * 100.0) if departed else 100.0

        return {
            "total_fleet": len(self.evs),
            "connected_count": len(connected),
            "charging_count": len(charging),
            "discharging_count": len(discharging),
            "idle_count": len(idle),
            "total_ev_power_kw": float(np.round(total_power_kw, 3)),
            "total_ev_power_mw": float(np.round(total_power_kw / 1000.0, 4)),
            "average_soc": float(np.round(avg_soc, 4)),
            "departed_count": len(departed),
            "compliance_pct": float(np.round(compliance_pct, 2))
        }

    def reset(self):
        for ev in self.evs:
            ev.reset()


def StringPad(i: int) -> str:
    return str(i).zfill(3)
