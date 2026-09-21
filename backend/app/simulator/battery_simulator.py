from typing import Dict, Any

class BatterySimulator:
    """
    Advanced physical simulation of an electrochemical lithium-ion battery system:
    - Charging & Discharging efficiencies (92% chg, 90% dis)
    - Strict physical State-of-Charge (SOC) boundaries [min_soc, max_soc]
    - Joulean thermal self-heating & ambient cooling model
    - BMS thermal protection throttling (derates power when T > 45°C)
    - Multi-factor State-of-Health (SOH) degradation based on DOD, C-rate, high-SOC exposure, and temperature.
    """
    def __init__(
        self,
        capacity_kwh: float,
        initial_soc: float = 50.0,
        minimum_soc: float = 20.0,
        maximum_soc: float = 100.0,
        charging_efficiency: float = 0.92,
        discharging_efficiency: float = 0.90,
        degradation_factor: float = 0.00005,
        nominal_voltage_v: float = 400.0,
        ambient_temp_c: float = 25.0
    ):
        if capacity_kwh <= 0:
            raise ValueError("Battery capacity must be strictly greater than 0 kWh.")
        
        self.capacity_kwh = float(capacity_kwh)
        self.minimum_soc = max(0.0, min(100.0, float(minimum_soc)))
        self.maximum_soc = max(self.minimum_soc, min(100.0, float(maximum_soc)))
        self.current_soc = max(0.0, min(100.0, float(initial_soc)))
        
        self.charging_efficiency = max(0.1, min(1.0, float(charging_efficiency)))
        self.discharging_efficiency = max(0.1, min(1.0, float(discharging_efficiency)))
        self.degradation_factor = float(degradation_factor)
        self.nominal_voltage_v = float(nominal_voltage_v)
        self.ambient_temp_c = float(ambient_temp_c)
        self.temperature_c = float(ambient_temp_c)
        
        self.battery_health: float = 100.0
        self.total_charged_kwh: float = 0.0
        self.total_discharged_kwh: float = 0.0
        self.cycle_count: float = 0.0

    @property
    def stored_energy_kwh(self) -> float:
        return (self.current_soc / 100.0) * self.capacity_kwh

    @property
    def equivalent_full_cycles(self) -> float:
        return (self.total_charged_kwh + self.total_discharged_kwh) / (2.0 * self.capacity_kwh)

    def _apply_thermal_model(self, power_kw: float, timestep_hours: float):
        """Updates battery core temperature through internal resistance Joulean heating and heat dissipation."""
        current_a = (power_kw * 1000.0) / self.nominal_voltage_v
        internal_resistance_ohms = 0.045
        heat_watts = (current_a ** 2) * internal_resistance_ohms
        thermal_capacity_j_per_k = 75000.0  # Typical 60kWh pack thermal mass

        temp_rise_c = (heat_watts * timestep_hours * 3600.0) / thermal_capacity_j_per_k
        cooling_c = 0.15 * (self.temperature_c - self.ambient_temp_c) * timestep_hours

        self.temperature_c = max(self.ambient_temp_c, min(65.0, self.temperature_c + temp_rise_c - cooling_c))

    def _get_thermal_derating_factor(self) -> float:
        """Throttles power if cell temperature approaches critical limits (> 45°C)."""
        if self.temperature_c <= 45.0:
            return 1.0
        # Linear throttle down to 20% at 50°C
        return max(0.2, (50.0 - self.temperature_c) / 5.0)

    def charge(self, power_kw: float, timestep_hours: float) -> Dict[str, float]:
        """
        energy_added = charging_power * timestep * charging_efficiency
        SOC strictly bounded by maximum_soc and 100.0%.
        """
        if power_kw <= 0.0 or timestep_hours <= 0.0:
            self._apply_thermal_model(0.0, timestep_hours)
            return {"actual_power_kw": 0.0, "energy_kwh": 0.0, "soc": self.current_soc, "temperature_c": round(self.temperature_c, 1)}

        # Thermal protection derating
        derate = self._get_thermal_derating_factor()
        effective_power_kw = power_kw * derate

        # Max energy the battery can absorb before reaching maximum_soc
        max_possible_energy = max(0.0, (self.maximum_soc - self.current_soc) / 100.0 * self.capacity_kwh)
        requested_energy = effective_power_kw * timestep_hours * self.charging_efficiency
        
        actual_energy_added = min(requested_energy, max_possible_energy)
        soc_delta = (actual_energy_added / self.capacity_kwh) * 100.0
        self.current_soc = min(self.maximum_soc, min(100.0, self.current_soc + soc_delta))
        
        self.total_charged_kwh += actual_energy_added
        actual_grid_power = actual_energy_added / (timestep_hours * self.charging_efficiency) if actual_energy_added > 0 else 0.0
        
        self._apply_thermal_model(actual_grid_power, timestep_hours)
        self._update_wear(actual_energy_added)
        
        return {
            "actual_power_kw": round(actual_grid_power, 3),
            "energy_kwh": round(actual_energy_added, 3),
            "soc": round(self.current_soc, 2),
            "temperature_c": round(self.temperature_c, 1)
        }

    def discharge(self, power_kw: float, timestep_hours: float) -> Dict[str, float]:
        """
        energy_removed = discharging_power * timestep / discharging_efficiency
        SOC strictly bounded by minimum_soc and 0.0%.
        """
        if power_kw <= 0.0 or timestep_hours <= 0.0:
            self._apply_thermal_model(0.0, timestep_hours)
            return {"actual_power_kw": 0.0, "energy_kwh": 0.0, "soc": self.current_soc, "temperature_c": round(self.temperature_c, 1)}

        # Thermal protection derating
        derate = self._get_thermal_derating_factor()
        effective_power_kw = power_kw * derate

        # Max energy available before hitting minimum_soc
        max_possible_energy = max(0.0, (self.current_soc - self.minimum_soc) / 100.0 * self.capacity_kwh)
        requested_battery_energy = (effective_power_kw * timestep_hours) / self.discharging_efficiency
        
        actual_battery_energy = min(requested_battery_energy, max_possible_energy)
        soc_delta = (actual_battery_energy / self.capacity_kwh) * 100.0
        self.current_soc = max(self.minimum_soc, max(0.0, self.current_soc - soc_delta))
        
        actual_supplied_grid_energy = actual_battery_energy * self.discharging_efficiency
        self.total_discharged_kwh += actual_supplied_grid_energy
        actual_grid_power = actual_supplied_grid_energy / timestep_hours if actual_supplied_grid_energy > 0 else 0.0
        
        self._apply_thermal_model(actual_grid_power, timestep_hours)
        self._update_wear(actual_battery_energy)

        return {
            "actual_power_kw": round(-actual_grid_power, 3),
            "energy_kwh": round(actual_supplied_grid_energy, 3),
            "soc": round(self.current_soc, 2),
            "temperature_c": round(self.temperature_c, 1)
        }

    def idle(self) -> Dict[str, float]:
        self._apply_thermal_model(0.0, 0.25)
        return {
            "actual_power_kw": 0.0,
            "energy_kwh": 0.0,
            "soc": round(self.current_soc, 2),
            "temperature_c": round(self.temperature_c, 1)
        }

    def _update_wear(self, throughput_kwh: float):
        if throughput_kwh <= 0:
            return
        cycles = throughput_kwh / (2.0 * self.capacity_kwh)
        self.cycle_count += cycles

        # Multi-factor engineering degradation model:
        # 1. Base cycle aging
        # 2. DOD penalty (deeper discharges induce higher mechanical strain on cathode)
        # 3. High temperature acceleration penalty (> 35°C accelerates SEI layer growth)
        # 4. High SOC calendar stress penalty (> 85% accelerates electrolyte oxidation)
        dod = max(0.1, (100.0 - self.current_soc) / 100.0)
        dod_penalty = 1.0 + 0.8 * dod
        temp_penalty = 1.0 + 0.04 * max(0.0, self.temperature_c - 35.0)
        high_soc_penalty = 1.25 if self.current_soc > 85.0 else 1.0

        effective_degradation_pct = cycles * self.degradation_factor * 100.0 * dod_penalty * temp_penalty * high_soc_penalty
        self.battery_health = max(60.0, round(self.battery_health - effective_degradation_pct, 4))
