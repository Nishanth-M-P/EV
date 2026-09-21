from abc import ABC, abstractmethod
from typing import Dict, Any
from backend.app.simulator.grid_simulator import GridSimulator
from backend.app.simulator.solar_simulator import SolarSimulator
from backend.app.simulator.price_simulator import PriceSimulator

class EnergyDataProvider(ABC):
    """
    Abstract interface decoupling the Digital Twin & AI engine from the underlying
    telemetry source (allowing drop-in hardware gateway integration in future).
    """
    @abstractmethod
    def get_grid_state(self, hour: float, charging_kw: float, v2g_kw: float, solar_surplus_kw: float) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_solar_generation(self, hour: float) -> float:
        pass

    @abstractmethod
    def get_electricity_price(self, hour: float) -> Dict[str, Any]:
        pass

class SimulationEnergyProvider(EnergyDataProvider):
    """
    Pure Python Digital Twin implementation of EnergyDataProvider.
    """
    def __init__(
        self,
        grid_capacity_kw: float = 100.0,
        solar_capacity_kw: float = 40.0,
        cloud_factor: float = 1.0
    ):
        self.grid = GridSimulator(grid_capacity_kw=grid_capacity_kw)
        self.solar = SolarSimulator(solar_peak_capacity_kw=solar_capacity_kw, cloud_factor=cloud_factor)
        self.price = PriceSimulator()

    def get_grid_state(self, hour: float, charging_kw: float = 0.0, v2g_kw: float = 0.0, solar_surplus_kw: float = 0.0) -> Dict[str, Any]:
        return self.grid.calculate_grid_state(hour, charging_kw, v2g_kw, solar_surplus_kw)

    def get_solar_generation(self, hour: float) -> float:
        return self.solar.get_generation_at_hour(hour)

    def get_electricity_price(self, hour: float) -> Dict[str, Any]:
        return self.price.get_price_at_hour(hour)

class HardwareEnergyProvider(EnergyDataProvider):
    """
    Placeholder architecture stub for future physical hardware IoT gateways
    (e.g., smart meters, Modbus CT clamps, OCPP 2.0.1 chargers).
    """
    def get_grid_state(self, hour: float, charging_kw: float, v2g_kw: float, solar_surplus_kw: float) -> Dict[str, Any]:
        raise NotImplementedError("Hardware gateway interface reserved for physical IoT deployment.")

    def get_solar_generation(self, hour: float) -> float:
        raise NotImplementedError("Hardware gateway interface reserved for physical IoT deployment.")

    def get_electricity_price(self, hour: float) -> Dict[str, Any]:
        raise NotImplementedError("Hardware gateway interface reserved for physical IoT deployment.")
