from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class Affiliate(BaseModel):
    """affiliates 테이블 엔티티"""
    id: Optional[int] = None
    branch_id: int
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
