from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict

class EVBase(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Tesla Model 3"})
    battery_capacity_kwh: float = Field(..., gt=0, json_schema_extra={"example": 60.0})
    current_soc: float = Field(..., ge=0, le=100, json_schema_extra={"example": 45.0})
    minimum_soc: float = Field(20.0, ge=0, le=100, json_schema_extra={"example": 20.0})
    maximum_soc: float = Field(100.0, ge=0, le=100, json_schema_extra={"example": 95.0})
    target_soc: float = Field(85.0, ge=0, le=100, json_schema_extra={"example": 85.0})
    arrival_time: float = Field(8.0, ge=0, le=24, json_schema_extra={"example": 9.0})
    departure_time: float = Field(18.0, ge=0, le=24, json_schema_extra={"example": 18.0})
    max_charge_power_kw: float = Field(7.4, gt=0, json_schema_extra={"example": 7.4})
    max_discharge_power_kw: float = Field(5.0, gt=0, json_schema_extra={"example": 5.0})
    charging_efficiency: float = Field(0.95, gt=0, le=1.0)
    discharging_efficiency: float = Field(0.95, gt=0, le=1.0)
    battery_health: float = Field(100.0, ge=0, le=100)

class EVCreate(EVBase):
    ev_id: Optional[str] = None

class EVResponse(EVBase):
    id: str
    status: str
    total_charged_kwh: float = 0.0
    total_discharged_kwh: float = 0.0
    cycle_count: float = 0.0
    current_power_kw: float = 0.0

    model_config = ConfigDict(from_attributes=True)

class EVOverrideRequest(BaseModel):
    action: Optional[str] = Field(None, description="CHARGE, DISCHARGE, IDLE, or null to clear")
