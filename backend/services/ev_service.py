import uuid
from typing import List, Dict, Optional

class EVModel:
    def __init__(
        self,
        ev_id: str,
        name: str,
        battery_capacity_kwh: float,
        current_soc: float,
        minimum_soc: float,
        maximum_soc: float,
        required_soc: float,
        arrival_time: float,
        departure_time: float,
        max_charge_power_kw: float = 7.4,
        max_discharge_power_kw: float = 5.0,
        charging_efficiency: float = 0.95,
        degradation_factor: float = 0.001
    ):
        self.ev_id = ev_id
        self.name = name
        self.battery_capacity_kwh = battery_capacity_kwh
        self.current_soc = current_soc  # Percentage 0 - 100
        self.minimum_soc = minimum_soc  # Percentage e.g. 20%
        self.maximum_soc = maximum_soc  # Percentage e.g. 100%
        self.required_soc = required_soc  # Percentage e.g. 85%
        self.arrival_time = arrival_time  # Hour e.g. 8.0
        self.departure_time = departure_time  # Hour e.g. 18.0
        self.max_charge_power_kw = max_charge_power_kw
        self.max_discharge_power_kw = max_discharge_power_kw
        self.charging_efficiency = charging_efficiency
        self.degradation_factor = degradation_factor
        
        self.status = "WAITING"  # WAITING, CHARGING, IDLE, DISCHARGING, COMPLETED
        self.total_charged_kwh = 0.0
        self.total_discharged_kwh = 0.0
        self.cycle_count = 0.0
        self.degradation_cost_incurred = 0.0

    def update_status(self, current_hour: float):
        if current_hour < self.arrival_time:
            self.status = "WAITING"
        elif current_hour >= self.departure_time:
            self.status = "COMPLETED"
        elif self.status not in ["CHARGING", "DISCHARGING", "IDLE"]:
            self.status = "IDLE"

    def apply_power_decision(self, power_kw: float, duration_hours: float = 1.0) -> Dict:
        """
        power_kw > 0 => Charging
        power_kw < 0 => Discharging (V2G)
        power_kw == 0 => Idle
        """
        energy_kwh = 0.0
        actual_power = 0.0

        if power_kw > 0:
            # Charge
            requested_energy = power_kw * duration_hours * self.charging_efficiency
            max_possible_energy = (self.maximum_soc - self.current_soc) / 100.0 * self.battery_capacity_kwh
            actual_energy = max(0.0, min(requested_energy, max_possible_energy))
            
            soc_delta = (actual_energy / self.battery_capacity_kwh) * 100.0
            self.current_soc = min(self.maximum_soc, self.current_soc + soc_delta)
            self.total_charged_kwh += actual_energy
            actual_power = actual_energy / duration_hours / self.charging_efficiency
            self.status = "CHARGING" if actual_power > 0.1 else "IDLE"

        elif power_kw < 0:
            # Discharge (V2G)
            dis_power = abs(power_kw)
            requested_energy = dis_power * duration_hours
            max_possible_energy = (self.current_soc - self.minimum_soc) / 100.0 * self.battery_capacity_kwh
            actual_energy = max(0.0, min(requested_energy, max_possible_energy))
            
            soc_delta = (actual_energy / self.battery_capacity_kwh) * 100.0
            self.current_soc = max(self.minimum_soc, self.current_soc - soc_delta)
            self.total_discharged_kwh += actual_energy
            actual_power = - (actual_energy / duration_hours)
            self.status = "DISCHARGING" if abs(actual_power) > 0.1 else "IDLE"

        else:
            # Idle
            self.status = "IDLE"
            actual_power = 0.0

        # Update battery cycling and degradation metric
        throughput_kwh = abs(actual_power) * duration_hours
        self.cycle_count += throughput_kwh / (2.0 * self.battery_capacity_kwh)
        self.degradation_cost_incurred += throughput_kwh * self.degradation_factor * 5.0 # ~₹5/kWh battery wear

        return {
            "ev_id": self.ev_id,
            "actual_power_kw": round(actual_power, 2),
            "soc": round(self.current_soc, 1),
            "status": self.status,
            "total_charged_kwh": round(self.total_charged_kwh, 2),
            "total_discharged_kwh": round(self.total_discharged_kwh, 2),
            "cycle_count": round(self.cycle_count, 3)
        }

    def to_dict(self) -> Dict:
        return {
            "ev_id": self.ev_id,
            "name": self.name,
            "battery_capacity_kwh": self.battery_capacity_kwh,
            "current_soc": round(self.current_soc, 1),
            "minimum_soc": self.minimum_soc,
            "maximum_soc": self.maximum_soc,
            "required_soc": self.required_soc,
            "arrival_time": self.arrival_time,
            "departure_time": self.departure_time,
            "max_charge_power_kw": self.max_charge_power_kw,
            "max_discharge_power_kw": self.max_discharge_power_kw,
            "charging_efficiency": self.charging_efficiency,
            "status": self.status,
            "total_charged_kwh": round(self.total_charged_kwh, 2),
            "total_discharged_kwh": round(self.total_discharged_kwh, 2),
            "cycle_count": round(self.cycle_count, 3),
            "degradation_cost_incurred": round(self.degradation_cost_incurred, 2)
        }


class EVFleetService:
    def __init__(self):
        self.evs: Dict[str, EVModel] = {}
        self.reset_default_fleet()

    def reset_default_fleet(self):
        """
        Creates a realistic simulated fleet of 5 EVs with varied schedules and capacities.
        """
        self.evs.clear()
        defaults = [
            EVModel("EV-001", "Tesla Model 3", 60.0, 35.0, 20.0, 100.0, 85.0, 8.0, 18.0, 7.4, 5.0),
            EVModel("EV-002", "Nissan Leaf", 40.0, 50.0, 25.0, 100.0, 80.0, 7.0, 16.0, 6.6, 4.0),
            EVModel("EV-003", "Hyundai Ioniq 5", 77.0, 25.0, 20.0, 100.0, 90.0, 9.0, 19.0, 11.0, 7.0),
            EVModel("EV-004", "Tata Nexon EV", 40.0, 60.0, 30.0, 100.0, 85.0, 12.0, 20.0, 7.2, 4.5),
            EVModel("EV-005", "MG ZS EV", 50.0, 45.0, 20.0, 100.0, 80.0, 10.0, 21.0, 7.4, 5.0),
        ]
        for ev in defaults:
            self.evs[ev.ev_id] = ev

    def add_ev(self, ev_data: dict) -> EVModel:
        ev_id = ev_data.get("ev_id") or f"EV-{uuid.uuid4().hex[:4].upper()}"
        ev = EVModel(
            ev_id=ev_id,
            name=ev_data.get("name", "Custom EV"),
            battery_capacity_kwh=float(ev_data.get("battery_capacity_kwh", 50.0)),
            current_soc=float(ev_data.get("current_soc", 40.0)),
            minimum_soc=float(ev_data.get("minimum_soc", 20.0)),
            maximum_soc=float(ev_data.get("maximum_soc", 100.0)),
            required_soc=float(ev_data.get("required_soc", 85.0)),
            arrival_time=float(ev_data.get("arrival_time", 8.0)),
            departure_time=float(ev_data.get("departure_time", 18.0)),
            max_charge_power_kw=float(ev_data.get("max_charge_power_kw", 7.4)),
            max_discharge_power_kw=float(ev_data.get("max_discharge_power_kw", 5.0))
        )
        self.evs[ev_id] = ev
        return ev

    def get_ev(self, ev_id: str) -> Optional[EVModel]:
        return self.evs.get(ev_id)

    def get_all_evs(self) -> List[dict]:
        return [ev.to_dict() for ev in self.evs.values()]

    def remove_ev(self, ev_id: str) -> bool:
        if ev_id in self.evs:
            del self.evs[ev_id]
            return True
        return False
