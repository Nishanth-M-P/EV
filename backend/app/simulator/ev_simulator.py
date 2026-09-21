from typing import Dict, Any, Optional
from backend.app.simulator.battery_simulator import BatterySimulator

class EVDigitalTwin:
    """
    Virtual digital twin representation of an Electric Vehicle (EV).
    Encapsulates EV metadata, battery system, and arrival/departure schedule.
    """
    def __init__(
        self,
        ev_id: str,
        name: str,
        battery_capacity_kwh: float,
        current_soc: float = 50.0,
        minimum_soc: float = 20.0,
        maximum_soc: float = 100.0,
        target_soc: float = 85.0,
        arrival_time: float = 8.0,
        departure_time: float = 18.0,
        max_charge_power_kw: float = 7.4,
        max_discharge_power_kw: float = 5.0,
        charging_efficiency: float = 0.95,
        discharging_efficiency: float = 0.95,
        battery_health: float = 100.0
    ):
        self.ev_id = ev_id
        self.name = name
        self.target_soc = float(target_soc)
        self.arrival_time = float(arrival_time)
        self.departure_time = float(departure_time)
        self.max_charge_power_kw = float(max_charge_power_kw)
        self.max_discharge_power_kw = float(max_discharge_power_kw)

        # Initialize physical battery twin
        self.battery = BatterySimulator(
            capacity_kwh=battery_capacity_kwh,
            initial_soc=current_soc,
            minimum_soc=minimum_soc,
            maximum_soc=maximum_soc,
            charging_efficiency=charging_efficiency,
            discharging_efficiency=discharging_efficiency
        )
        self.battery.battery_health = float(battery_health)
        
        self.status: str = "WAITING"  # WAITING, IDLE, CHARGING, DISCHARGING, DEPARTED
        self.current_power_kw: float = 0.0

    @property
    def current_soc(self) -> float:
        return self.battery.current_soc

    @current_soc.setter
    def current_soc(self, value: float):
        self.battery.current_soc = max(0.0, min(100.0, float(value)))

    @property
    def battery_capacity_kwh(self) -> float:
        return self.battery.capacity_kwh

    @property
    def minimum_soc(self) -> float:
        return self.battery.minimum_soc

    @property
    def maximum_soc(self) -> float:
        return self.battery.maximum_soc

    @property
    def charging_efficiency(self) -> float:
        return self.battery.charging_efficiency

    @property
    def discharging_efficiency(self) -> float:
        return self.battery.discharging_efficiency

    @property
    def battery_health(self) -> float:
        return self.battery.battery_health

    @property
    def is_connected(self) -> bool:
        return self.status not in ["WAITING", "DEPARTED"]

    def update_schedule_status(self, current_hour: float):
        if current_hour < self.arrival_time:
            self.status = "WAITING"
            self.current_power_kw = 0.0
        elif current_hour >= self.departure_time:
            self.status = "DEPARTED"
            self.current_power_kw = 0.0
        elif self.status in ["WAITING", "DEPARTED"]:
            self.status = "IDLE"
            self.current_power_kw = 0.0

    def apply_power(self, power_kw: float, timestep_hours: float) -> Dict[str, Any]:
        """
        Executes physical battery charging or discharging.
        power_kw > 0 => Charge
        power_kw < 0 => Discharge (V2G)
        power_kw == 0 => Idle
        """
        if not self.is_connected:
            self.current_power_kw = 0.0
            return {
                "ev_id": self.ev_id,
                "actual_power_kw": 0.0,
                "soc": self.current_soc,
                "status": self.status
            }

        if power_kw > 0.05:
            # Bound requested power to EV max charge power
            clamped_power = min(self.max_charge_power_kw, power_kw)
            result = self.battery.charge(clamped_power, timestep_hours)
            self.current_power_kw = result["actual_power_kw"]
            self.status = "CHARGING" if self.current_power_kw > 0.05 else "IDLE"

        elif power_kw < -0.05:
            # Bound requested power to EV max discharge power
            clamped_power = min(self.max_discharge_power_kw, abs(power_kw))
            result = self.battery.discharge(clamped_power, timestep_hours)
            self.current_power_kw = result["actual_power_kw"]
            self.status = "DISCHARGING" if abs(self.current_power_kw) > 0.05 else "IDLE"

        else:
            result = self.battery.idle()
            self.current_power_kw = 0.0
            self.status = "IDLE"

        return {
            "ev_id": self.ev_id,
            "actual_power_kw": round(self.current_power_kw, 2),
            "soc": round(self.current_soc, 1),
            "status": self.status,
            "total_charged_kwh": round(self.battery.total_charged_kwh, 2),
            "total_discharged_kwh": round(self.battery.total_discharged_kwh, 2),
            "cycle_count": round(self.battery.cycle_count, 3),
            "battery_health": round(self.battery.battery_health, 1),
            "temperature_c": round(self.battery.temperature_c, 1),
            "soh_pct": round(self.battery.battery_health, 1),
            "equivalent_full_cycles": round(self.battery.equivalent_full_cycles, 3)
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.ev_id,
            "ev_id": self.ev_id,
            "name": self.name,
            "battery_capacity_kwh": self.battery_capacity_kwh,
            "current_soc": round(self.current_soc, 1),
            "minimum_soc": self.minimum_soc,
            "maximum_soc": self.maximum_soc,
            "target_soc": self.target_soc,
            "required_soc": self.target_soc,  # backwards-compatible alias
            "arrival_time": self.arrival_time,
            "departure_time": self.departure_time,
            "max_charge_power_kw": self.max_charge_power_kw,
            "max_discharge_power_kw": self.max_discharge_power_kw,
            "charging_efficiency": self.charging_efficiency,
            "discharging_efficiency": self.discharging_efficiency,
            "battery_health": round(self.battery_health, 1),
            "soh_pct": round(self.battery_health, 1),
            "temperature_c": round(self.battery.temperature_c, 1),
            "status": self.status,
            "current_power_kw": round(self.current_power_kw, 2),
            "total_charged_kwh": round(self.battery.total_charged_kwh, 2),
            "total_discharged_kwh": round(self.battery.total_discharged_kwh, 2),
            "cycle_count": round(self.battery.cycle_count, 3),
            "equivalent_full_cycles": round(self.battery.equivalent_full_cycles, 3)
        }

