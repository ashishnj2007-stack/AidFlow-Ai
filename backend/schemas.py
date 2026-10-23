from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class DonationCreate(BaseModel):
    donor_name: str = Field(min_length=1, max_length=120)
    item_type: str = Field(pattern="^(prepared_meals|raw_ration_kit)$")
    quantity: int = Field(gt=0, le=100000)
    expires_at: datetime
    requires_water: bool = False
    requires_cooking: bool = False

class RiderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(gt=0, le=10000)

class ShelterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    demand: int = Field(ge=0, le=100000)
    water_available: bool = True
    cooking_available: bool = True

class DemandUpdate(BaseModel):
    demand: int = Field(ge=0, le=100000)

class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)
