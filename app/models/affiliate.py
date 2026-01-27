from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Affiliate(BaseModel):
    """affiliates 테이블 엔티티"""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    affiliate_index: int | None = None
    name: str | None = None
    location_type: str | None = None
    address: str | None = None
    phone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_active: bool = True
    raw_data: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CarModel(BaseModel):
    """car_models 테이블 엔티티"""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    model_id: str
    name: str
    name_en: str | None = None
    category: str | None = None
    brand: str | None = None
    seats: int | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    image_url: str | None = None
    raw_data: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
