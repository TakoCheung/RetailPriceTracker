from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List

class ProductProviderLink(SQLModel, table=True):
    product_id: int | None = Field(default=None, foreign_key="product.id", primary_key=True)
    provider_id: int | None = Field(default=None, foreign_key="provider.id", primary_key=True)

class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    providers: List["Provider"] = Relationship(back_populates="products", link_model=ProductProviderLink)

class Provider(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    products: List[Product] = Relationship(back_populates="providers", link_model=ProductProviderLink)

class PriceRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    provider_id: int = Field(foreign_key="provider.id")
    price: float
    timestamp: str

class PriceAlert(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int
    product_id: int = Field(foreign_key="product.id")
    threshold: float

class UserPreference(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int
    default_currency: str
    notify_email: bool = True
