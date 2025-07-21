from pydantic import BaseModel
from typing import Optional

class ProductCreate(BaseModel):
    name: str

class ProviderCreate(BaseModel):
    name: str

class PriceAlertCreate(BaseModel):
    product_id: int
    threshold: float

class UserPreferenceUpdate(BaseModel):
    default_currency: Optional[str]
    notify_email: Optional[bool]
