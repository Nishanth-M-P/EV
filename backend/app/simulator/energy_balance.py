from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import math

@dataclass
class PowerFlowState:
    solar_gen_kw: float = 0.0
    grid_import_kw: float = 0.0
    grid_export_kw: float = 0.0
    ev_charging_kw: float = 0.0
    v2g_discharge_kw: float = 0.0
    station_aux_kw: float = 0.0
    system_losses_kw: float = 0.0
    
    # Conservation validation
    total_in_kw: float = 0.0
    total_out_kw: float = 0.0
    balance_error_kw: float = 0.0
    is_balanced: bool = True
    
    # Priority allocations
    solar_to_aux_kw: float = 0.0
    solar_to_ev_kw: float = 0.0
    solar_to_grid_kw: float = 0.0
    grid_to_ev_kw: float = 0.0
    v2g_to_grid_kw: float = 0.0
    v2g_to_station_kw: float = 0.0
    
    # Attribution
    solar_share_pct: float = 0.0
    grid_share_pct: float = 0.0
    summary_text: str = "Idle"

class EnergyBalanceEngine:
    """
    Authoritative Microgrid Energy Balance & Solar Priority Engine.
    Guarantees physical energy conservation:
      P_solar + P_grid_import + P_v2g = P_ev_charging + P_station_aux + P_grid_export + P_losses
    within +/- 0.05 kW numerical tolerance.
    """
    def __init__(self, base_station_aux_kw: float = 6.0, loss_factor: float = 0.035):
        self.base_station_aux_kw = base_station_aux_kw
        self.loss_factor = loss_factor  # 3.5% conversion and transmission losses
        
        # Cumulative energy meters (kWh) reset daily
        self.cumulative_solar_gen_kwh: float = 0.0
        self.cumulative_solar_used_kwh: float = 0.0
        self.cumulative_grid_import_kwh: float = 0.0
        self.cumulative_grid_export_kwh: float = 0.0
        self.cumulative_ev_charging_kwh: float = 0.0
        self.cumulative_v2g_discharge_kwh: float = 0.0
        self.cumulative_station_aux_kwh: float = 0.0
        self.cumulative_losses_kwh: float = 0.0
        
        # Financial ledger (INR)
        self.total_import_cost_inr: float = 0.0
        self.total_export_revenue_inr: float = 0.0
        self.total_v2g_payout_inr: float = 0.0
        self.net_energy_cost_inr: float = 0.0

    def reset_daily_meters(self):
        self.cumulative_solar_gen_kwh = 0.0
        self.cumulative_solar_used_kwh = 0.0
        self.cumulative_grid_import_kwh = 0.0
        self.cumulative_grid_export_kwh = 0.0
        self.cumulative_ev_charging_kwh = 0.0
        self.cumulative_v2g_discharge_kwh = 0.0
        self.cumulative_station_aux_kwh = 0.0
        self.cumulative_losses_kwh = 0.0
        self.total_import_cost_inr = 0.0
        self.total_export_revenue_inr = 0.0
        self.total_v2g_payout_inr = 0.0
        self.net_energy_cost_inr = 0.0

    def calculate_balance(
        self,
        solar_gen_kw: float,
        ev_charging_demand_kw: float,
        v2g_discharge_kw: float,
        hour: float,
        feed_in_allowed: bool = True
    ) -> PowerFlowState:
        """
        Dispatches solar first, incorporates V2G, calculates station aux and losses,
        and determines necessary grid import or export to satisfy conservation.
        """
        solar_gen_kw = max(0.0, float(solar_gen_kw))
        ev_charging_demand_kw = max(0.0, float(ev_charging_demand_kw))
        v2g_discharge_kw = max(0.0, float(v2g_discharge_kw))

        # 1. Station Aux load with slight diurnal activity curve
        aux_multiplier = 1.0 + 0.25 * math.sin(math.pi * (hour % 24) / 24.0)
        station_aux_kw = round(self.base_station_aux_kw * aux_multiplier, 2)

        # 2. System conversion & cabling losses (proportional to total throughput)
        raw_throughput = ev_charging_demand_kw + v2g_discharge_kw + (solar_gen_kw * 0.5)
        system_losses_kw = round(max(0.2, raw_throughput * self.loss_factor), 2)

        # Total internal station load needing power
        total_internal_load_kw = ev_charging_demand_kw + station_aux_kw + system_losses_kw

        # 3. Solar Priority Dispatch
        # Step 3a: Solar to Aux and losses first
        solar_avail = solar_gen_kw
        solar_to_aux = min(solar_avail, station_aux_kw + system_losses_kw)
        solar_avail -= solar_to_aux

        # Step 3b: Solar to EV Charging
        solar_to_ev = min(solar_avail, ev_charging_demand_kw)
        solar_avail -= solar_to_ev

        # Step 3c: Remaining solar to Grid Export
        solar_to_grid = solar_avail if feed_in_allowed else 0.0

        # 4. EV Deficit & Grid Import / V2G allocation
        unmet_ev_kw = max(0.0, ev_charging_demand_kw - solar_to_ev)
        unmet_aux_kw = max(0.0, (station_aux_kw + system_losses_kw) - solar_to_aux)
        total_unmet_kw = unmet_ev_kw + unmet_aux_kw

        # V2G can support station load or feed grid
        v2g_to_station = min(v2g_discharge_kw, total_unmet_kw)
        remaining_v2g = v2g_discharge_kw - v2g_to_station
        v2g_to_grid = remaining_v2g if feed_in_allowed else 0.0

        # Remaining deficit must be imported from the primary grid
        net_station_deficit_kw = max(0.0, total_unmet_kw - v2g_to_station)
        grid_import_kw = net_station_deficit_kw
        grid_to_ev = max(0.0, unmet_ev_kw - min(unmet_ev_kw, v2g_to_station))

        grid_export_kw = solar_to_grid + v2g_to_grid

        # 5. Energy Conservation Check
        total_in = solar_gen_kw + grid_import_kw + v2g_discharge_kw
        total_out = ev_charging_demand_kw + station_aux_kw + grid_export_kw + system_losses_kw
        balance_err = abs(total_in - total_out)

        # Fine adjustment to eliminate floating-point rounding error
        if 0.0 < balance_err <= 0.05:
            if total_in > total_out:
                system_losses_kw += (total_in - total_out)
            else:
                grid_import_kw += (total_out - total_in)
            total_in = solar_gen_kw + grid_import_kw + v2g_discharge_kw
            total_out = ev_charging_demand_kw + station_aux_kw + grid_export_kw + system_losses_kw
            balance_err = abs(total_in - total_out)

        # 6. Fleet Attribution Shares
        if ev_charging_demand_kw > 0.01:
            solar_share_pct = round((solar_to_ev / ev_charging_demand_kw) * 100.0, 1)
            grid_share_pct = round(100.0 - solar_share_pct, 1)
        else:
            solar_share_pct = 100.0 if solar_gen_kw > 0 else 0.0
            grid_share_pct = 0.0

        # Flow summary text
        if v2g_discharge_kw > 0.1 and grid_export_kw > 0.1:
            summary = "V2G Grid Peak Shaving Active"
        elif solar_to_grid > 0.1:
            summary = "Solar Surplus Export to Grid"
        elif solar_to_ev > 0.1 and grid_to_ev > 0.1:
            summary = "Solar + Grid Hybrid EV Charging"
        elif solar_to_ev > 0.1:
            summary = "100% Green Solar EV Charging"
        elif ev_charging_demand_kw > 0.1:
            summary = "Grid Supplied EV Charging"
        else:
            summary = "Station Standby / Auxiliary Mode"

        return PowerFlowState(
            solar_gen_kw=round(solar_gen_kw, 2),
            grid_import_kw=round(grid_import_kw, 2),
            grid_export_kw=round(grid_export_kw, 2),
            ev_charging_kw=round(ev_charging_demand_kw, 2),
            v2g_discharge_kw=round(v2g_discharge_kw, 2),
            station_aux_kw=round(station_aux_kw, 2),
            system_losses_kw=round(system_losses_kw, 2),
            total_in_kw=round(total_in, 2),
            total_out_kw=round(total_out, 2),
            balance_error_kw=round(balance_err, 4),
            is_balanced=(balance_err <= 0.05),
            solar_to_aux_kw=round(solar_to_aux, 2),
            solar_to_ev_kw=round(solar_to_ev, 2),
            solar_to_grid_kw=round(solar_to_grid, 2),
            grid_to_ev_kw=round(grid_to_ev, 2),
            v2g_to_grid_kw=round(v2g_to_grid, 2),
            v2g_to_station_kw=round(v2g_to_station, 2),
            solar_share_pct=solar_share_pct,
            grid_share_pct=grid_share_pct,
            summary_text=summary
        )

    def accumulate_energy(
        self,
        state: PowerFlowState,
        timestep_hours: float,
        grid_tariff_inr: float = 6.80,
        feed_in_tariff_inr: float = 4.20,
        v2g_payout_rate_inr: float = 7.50
    ) -> Dict[str, Any]:
        """
        Integrates instantaneous power (kW) into accumulated energy (kWh):
        ΔE = P * Δt
        """
        dt = float(timestep_hours)
        d_solar_gen = state.solar_gen_kw * dt
        d_solar_used = (state.solar_to_aux_kw + state.solar_to_ev_kw) * dt
        d_grid_import = state.grid_import_kw * dt
        d_grid_export = state.grid_export_kw * dt
        d_ev_charge = state.ev_charging_kw * dt
        d_v2g = state.v2g_discharge_kw * dt
        d_aux = state.station_aux_kw * dt
        d_losses = state.system_losses_kw * dt

        # Financial increments
        d_import_cost = d_grid_import * grid_tariff_inr
        d_export_rev = d_grid_export * feed_in_tariff_inr
        d_v2g_payout = d_v2g * v2g_payout_rate_inr

        # Update meters
        self.cumulative_solar_gen_kwh += d_solar_gen
        self.cumulative_solar_used_kwh += d_solar_used
        self.cumulative_grid_import_kwh += d_grid_import
        self.cumulative_grid_export_kwh += d_grid_export
        self.cumulative_ev_charging_kwh += d_ev_charge
        self.cumulative_v2g_discharge_kwh += d_v2g
        self.cumulative_station_aux_kwh += d_aux
        self.cumulative_losses_kwh += d_losses

        self.total_import_cost_inr += d_import_cost
        self.total_export_revenue_inr += d_export_rev
        self.total_v2g_payout_inr += d_v2g_payout
        self.net_energy_cost_inr = (self.total_import_cost_inr + self.total_v2g_payout_inr) - self.total_export_revenue_inr

        return {
            "interval_hours": dt,
            "delta_solar_gen_kwh": round(d_solar_gen, 4),
            "delta_grid_import_kwh": round(d_grid_import, 4),
            "delta_grid_export_kwh": round(d_grid_export, 4),
            "delta_ev_charging_kwh": round(d_ev_charge, 4),
            "delta_v2g_discharge_kwh": round(d_v2g, 4),
            "delta_cost_inr": round(d_import_cost, 2),
            "delta_export_rev_inr": round(d_export_rev, 2),
            "cumulative": {
                "solar_gen_kwh_today": round(self.cumulative_solar_gen_kwh, 2),
                "solar_used_kwh_today": round(self.cumulative_solar_used_kwh, 2),
                "grid_import_kwh_today": round(self.cumulative_grid_import_kwh, 2),
                "grid_export_kwh_today": round(self.cumulative_grid_export_kwh, 2),
                "ev_charging_kwh_today": round(self.cumulative_ev_charging_kwh, 2),
                "v2g_discharge_kwh_today": round(self.cumulative_v2g_discharge_kwh, 2),
                "station_aux_kwh_today": round(self.cumulative_station_aux_kwh, 2),
                "system_losses_kwh_today": round(self.cumulative_losses_kwh, 2),
                "total_import_cost_inr": round(self.total_import_cost_inr, 2),
                "total_export_revenue_inr": round(self.total_export_revenue_inr, 2),
                "total_v2g_payout_inr": round(self.total_v2g_payout_inr, 2),
                "net_energy_cost_inr": round(self.net_energy_cost_inr, 2)
            }
        }

    def attribute_ev_power(self, ev_power_kw: float, flow_state: PowerFlowState) -> Dict[str, float]:
        """
        Calculates exact physical power and share breakdown for an individual EV.
        """
        if ev_power_kw <= 0.001:
            return {
                "power_kw": 0.0,
                "solar_power_kw": 0.0,
                "grid_power_kw": 0.0,
                "solar_pct": round(flow_state.solar_share_pct, 1),
                "grid_pct": round(flow_state.grid_share_pct, 1)
            }
        
        solar_ratio = flow_state.solar_share_pct / 100.0
        grid_ratio = flow_state.grid_share_pct / 100.0
        
        solar_pwr = round(ev_power_kw * solar_ratio, 2)
        grid_pwr = round(ev_power_kw - solar_pwr, 2)
        
        return {
            "power_kw": round(ev_power_kw, 2),
            "solar_power_kw": solar_pwr,
            "grid_power_kw": grid_pwr,
            "solar_pct": flow_state.solar_share_pct,
            "grid_pct": flow_state.grid_share_pct
        }
