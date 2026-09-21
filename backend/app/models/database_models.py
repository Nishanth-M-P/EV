from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from backend.app.database.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(20), default="admin")
    session_token = Column(String(255), nullable=True, index=True)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(100), default="Simulation Run")
    scenario = Column(String(100), default="default")
    duration_hours = Column(Float, default=24.0)
    timestep_minutes = Column(Integer, default=15)
    total_evs = Column(Integer, default=5)
    status = Column(String(20), default="READY")  # READY, RUNNING, PAUSED, COMPLETED, STOPPED
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    config_json = Column(JSON, nullable=True)

    steps = relationship("SimulationStep", back_populates="simulation", cascade="all, delete-orphan")
    ai_decisions = relationship("AIDecisionRecord", back_populates="simulation", cascade="all, delete-orphan")
    analytics = relationship("AnalyticsRecord", back_populates="simulation", uselist=False, cascade="all, delete-orphan")

class EVRecord(Base):
    __tablename__ = "evs"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    battery_capacity_kwh = Column(Float, nullable=False)
    current_soc = Column(Float, default=50.0)
    minimum_soc = Column(Float, default=20.0)
    maximum_soc = Column(Float, default=100.0)
    target_soc = Column(Float, default=85.0)
    arrival_time = Column(Float, default=8.0)
    departure_time = Column(Float, default=18.0)
    max_charge_power_kw = Column(Float, default=7.4)
    max_discharge_power_kw = Column(Float, default=5.0)
    charging_efficiency = Column(Float, default=0.95)
    discharging_efficiency = Column(Float, default=0.95)
    battery_health = Column(Float, default=100.0)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChargerRecord(Base):
    __tablename__ = "chargers"

    id = Column(String(50), primary_key=True, index=True)
    station_name = Column(String(100), default="Station 1")
    max_power_kw = Column(Float, default=22.0)
    current_power_kw = Column(Float, default=0.0)
    efficiency = Column(Float, default=0.95)
    status = Column(String(20), default="AVAILABLE")  # AVAILABLE, CHARGING, DISCHARGING, IDLE, FAULT
    connected_ev_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class SimulationStep(Base):
    __tablename__ = "simulation_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(36), ForeignKey("simulations.id"), index=True, nullable=False)
    step_index = Column(Integer, nullable=False)
    hour = Column(Float, nullable=False)
    time_str = Column(String(10), nullable=False)
    grid_load_kw = Column(Float, default=0.0)
    grid_capacity_kw = Column(Float, default=100.0)
    grid_stress_pct = Column(Float, default=0.0)
    solar_generation_kw = Column(Float, default=0.0)
    electricity_price = Column(Float, default=0.0)
    price_category = Column(String(20), default="Normal")
    total_charging_power_kw = Column(Float, default=0.0)
    total_v2g_power_kw = Column(Float, default=0.0)
    net_grid_load_kw = Column(Float, default=0.0)
    energy_flow_json = Column(JSON, nullable=True)
    ev_states_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    simulation = relationship("Simulation", back_populates="steps")

class AIDecisionRecord(Base):
    __tablename__ = "ai_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(36), ForeignKey("simulations.id"), index=True, nullable=False)
    hour = Column(Float, nullable=False)
    ev_id = Column(String(50), nullable=False)
    raw_action = Column(Integer, nullable=False)
    final_action = Column(Integer, nullable=False)
    action_name = Column(String(20), nullable=False)  # IDLE, CHARGE, DISCHARGE
    power_kw = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    reward = Column(Float, default=0.0)
    safety_overrides = Column(JSON, nullable=True)
    is_manual_override = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    simulation = relationship("Simulation", back_populates="ai_decisions")

class EnergyRecord(Base):
    __tablename__ = "energy_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(36), index=True, nullable=True)
    hour = Column(Float, nullable=False)
    solar_to_grid_kwh = Column(Float, default=0.0)
    solar_to_ev_kwh = Column(Float, default=0.0)
    grid_to_ev_kwh = Column(Float, default=0.0)
    ev_to_grid_kwh = Column(Float, default=0.0)
    recorded_at = Column(DateTime, default=datetime.utcnow)

class AnalyticsRecord(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(36), ForeignKey("simulations.id"), unique=True, index=True, nullable=False)
    total_energy_consumed_kwh = Column(Float, default=0.0)
    total_charging_cost_inr = Column(Float, default=0.0)
    average_electricity_price = Column(Float, default=0.0)
    peak_grid_load_kw = Column(Float, default=0.0)
    peak_reduction_pct = Column(Float, default=0.0)
    solar_energy_generated_kwh = Column(Float, default=0.0)
    solar_energy_utilized_kwh = Column(Float, default=0.0)
    renewable_utilization_pct = Column(Float, default=0.0)
    v2g_energy_supplied_kwh = Column(Float, default=0.0)
    v2g_revenue_earned_inr = Column(Float, default=0.0)
    total_battery_cycles = Column(Float, default=0.0)
    average_ev_soc = Column(Float, default=0.0)
    target_soc_achievement_pct = Column(Float, default=0.0)
    rl_total_reward = Column(Float, default=0.0)
    baseline_total_cost_inr = Column(Float, default=0.0)
    ai_total_cost_inr = Column(Float, default=0.0)
    cost_difference_inr = Column(Float, default=0.0)
    cost_savings_pct = Column(Float, default=0.0)
    full_report_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    simulation = relationship("Simulation", back_populates="analytics")

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(50), primary_key=True, index=True)
    value = Column(JSON, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TelemetrySnapshot(Base):
    __tablename__ = "telemetry_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    source_mode = Column(String(20), default="digital_twin")  # digital_twin, hardware, hybrid
    solar_power_kw = Column(Float, default=0.0)
    grid_import_power_kw = Column(Float, default=0.0)
    grid_export_power_kw = Column(Float, default=0.0)
    ev_charging_power_kw = Column(Float, default=0.0)
    v2g_power_kw = Column(Float, default=0.0)
    station_aux_power_kw = Column(Float, default=0.0)
    system_losses_kw = Column(Float, default=0.0)
    net_power_balance_kw = Column(Float, default=0.0)
    grid_frequency_hz = Column(Float, default=50.0)
    grid_voltage_v = Column(Float, default=230.0)
    ambient_temp_c = Column(Float, default=25.0)
    solar_irradiance_w_m2 = Column(Float, default=0.0)
    raw_telemetry_json = Column(JSON, nullable=True)

class EnergyTransaction(Base):
    __tablename__ = "energy_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    interval_seconds = Column(Float, default=1.0)
    source_category = Column(String(50), nullable=False)  # SOLAR, GRID_IMPORT, V2G_DISCHARGE
    destination_category = Column(String(50), nullable=False)  # EV_CHARGING, STATION_AUX, GRID_EXPORT, LOSSES
    power_kw = Column(Float, nullable=False)
    energy_kwh = Column(Float, nullable=False)
    tariff_rate_inr = Column(Float, default=6.0)
    cost_or_revenue_inr = Column(Float, default=0.0)
    simulation_id = Column(String(36), nullable=True, index=True)

class ChargingSession(Base):
    __tablename__ = "charging_sessions"

    id = Column(String(50), primary_key=True, index=True)
    ev_id = Column(String(50), nullable=False, index=True)
    charger_id = Column(String(50), nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    initial_soc = Column(Float, default=0.0)
    current_or_final_soc = Column(Float, default=0.0)
    target_soc = Column(Float, default=85.0)
    total_energy_kwh = Column(Float, default=0.0)
    solar_energy_kwh = Column(Float, default=0.0)
    grid_energy_kwh = Column(Float, default=0.0)
    total_cost_inr = Column(Float, default=0.0)
    status = Column(String(20), default="ACTIVE")  # ACTIVE, COMPLETED, INTERRUPTED

class V2GSession(Base):
    __tablename__ = "v2g_sessions"

    id = Column(String(50), primary_key=True, index=True)
    ev_id = Column(String(50), nullable=False, index=True)
    charger_id = Column(String(50), nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    start_soc = Column(Float, default=0.0)
    end_soc = Column(Float, nullable=True)
    total_discharged_kwh = Column(Float, default=0.0)
    revenue_earned_inr = Column(Float, default=0.0)
    peak_support_kw = Column(Float, default=0.0)
    status = Column(String(20), default="ACTIVE")  # ACTIVE, COMPLETED

class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String(20), default="INFO")  # INFO, WARNING, CRITICAL
    category = Column(String(50), nullable=False)  # GRID_OVERLOAD, V2G_INHIBIT, THERMAL_DERATE, BATTERY_LOW, CONSERVATION_FAIL
    message = Column(String(255), nullable=False)
    details_json = Column(JSON, nullable=True)

