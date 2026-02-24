"""
업체/제휴점 Repository (affiliates, car_models 테이블)
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.timezone import utc_now
from models.affiliate import Affiliate, CarModel

from .base import BaseRepository
from .orm_models import AffiliateORM, CarModelORM

logger = logging.getLogger(__name__)


class AffiliateRepository(BaseRepository[Affiliate]):
    """affiliates 테이블 Repository"""

    model = Affiliate
    orm_model = AffiliateORM

    @property
    def table_name(self) -> str:
        return "affiliates"

    async def upsert_batch(self, affiliates: list[dict]) -> int:
        """업체 정보 일괄 저장"""
        if not affiliates:
            return 0

        rows = []
        for aff in affiliates:
            aff_idx = aff.get("affiliate_index") or aff.get("affiliateIndex")
            loc_type = aff.get("location_type") or aff.get("locationType", "PARTNERS")
            row = {
                "affiliate_index": aff_idx,
                "name": aff.get("name") or aff.get("affiliateName", ""),
                "location_type": loc_type,
                "address": aff.get("address", ""),
                "phone": aff.get("phone", ""),
                "latitude": aff.get("latitude"),
                "longitude": aff.get("longitude"),
                "is_active": aff.get("is_active", True),
                "raw_data": aff,
            }
            if row["affiliate_index"]:
                rows.append(row)

        if not rows:
            return 0

        stmt = pg_insert(AffiliateORM.__table__).values(rows)
        update_cols = {
            col.name: col
            for col in stmt.excluded
            if col.name not in ("id", "affiliate_index", "created_at")
        }
        stmt = (
            stmt.on_conflict_do_update(
                index_elements=["affiliate_index"],
                set_=update_cols,
            )
            .returning(AffiliateORM.id)
        )
        result = await self._session.execute(stmt)
        return len(result.all())

    async def get_by_index(self, affiliate_index: int) -> Affiliate | None:
        """업체 인덱스로 조회"""
        stmt = (
            select(AffiliateORM)
            .where(AffiliateORM.affiliate_index == affiliate_index)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_pydantic(row) if row else None

    async def get_all_with_filters(
        self, location_type: str | None = None, is_active: bool = True
    ) -> list[Affiliate]:
        """필터링된 업체 목록"""
        stmt = select(AffiliateORM)

        if location_type:
            stmt = stmt.where(AffiliateORM.location_type == location_type)
        if is_active is not None:
            stmt = stmt.where(AffiliateORM.is_active == is_active)

        stmt = stmt.order_by(AffiliateORM.name)
        result = await self._session.execute(stmt)
        return [self._to_pydantic(row) for row in result.scalars().all()]

    async def sync_from_api(self, api_client) -> dict:
        """Carmore API에서 업체 정보 동기화"""
        sync_result = {
            "total": 0,
            "success": 0,
            "error": None,
            "synced_at": utc_now().isoformat(),
        }

        try:
            response = api_client.get_affiliates(location_type="PARTNERS")
            if not response.success:
                sync_result["error"] = response.error
                return sync_result

            if isinstance(response.data, dict):
                affiliates = response.data.get("affiliates", [])
            elif isinstance(response.data, list):
                affiliates = response.data
            else:
                affiliates = []

            sync_result["total"] = len(affiliates)

            if affiliates:
                normalized = []
                for aff in affiliates:
                    location = aff.get("location") or {}
                    tel = aff.get("tel") or {}

                    aff_id = int(aff.get("id")) if aff.get("id") else None
                    lat = location.get("latitude")
                    lng = location.get("longitude")
                    normalized.append(
                        {
                            "affiliate_index": aff_id,
                            "name": aff.get("name", ""),
                            "location_type": "PARTNERS",
                            "address": location.get("address", ""),
                            "phone": tel.get("number", ""),
                            "latitude": float(lat) if lat else None,
                            "longitude": float(lng) if lng else None,
                            "is_active": True,
                            "raw_data": aff,
                        }
                    )

                sync_result["success"] = await self.upsert_batch(normalized)

        except Exception as e:
            sync_result["error"] = str(e)

        return sync_result


class CarModelRepository(BaseRepository[CarModel]):
    """car_models 테이블 Repository"""

    model = CarModel
    orm_model = CarModelORM

    @property
    def table_name(self) -> str:
        return "car_models"

    async def upsert_batch(self, car_models: list[dict]) -> int:
        """차종 정보 일괄 저장"""
        if not car_models:
            return 0

        rows = []
        for cm in car_models:
            model_id = cm.get("model_id") or cm.get("modelId") or cm.get("id")
            row = {
                "model_id": model_id,
                "name": cm.get("name") or cm.get("modelName", ""),
                "name_en": cm.get("name_en") or cm.get("nameEn", ""),
                "category": cm.get("category") or cm.get("carCategory", ""),
                "brand": cm.get("brand") or cm.get("manufacturer", ""),
                "seats": cm.get("seats") or cm.get("maxPassengers"),
                "fuel_type": cm.get("fuel_type") or cm.get("fuelType", ""),
                "transmission": cm.get("transmission", ""),
                "image_url": cm.get("image_url") or cm.get("imageUrl", ""),
                "raw_data": cm,
            }
            if row["model_id"]:
                rows.append(row)

        if not rows:
            return 0

        stmt = pg_insert(CarModelORM.__table__).values(rows)
        update_cols = {
            col.name: col
            for col in stmt.excluded
            if col.name not in ("id", "model_id", "created_at")
        }
        stmt = (
            stmt.on_conflict_do_update(
                index_elements=["model_id"],
                set_=update_cols,
            )
            .returning(CarModelORM.id)
        )
        result = await self._session.execute(stmt)
        return len(result.all())

    async def get_by_model_id(self, model_id: str) -> CarModel | None:
        """차종 ID로 조회"""
        stmt = (
            select(CarModelORM)
            .where(CarModelORM.model_id == model_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_pydantic(row) if row else None

    async def get_all_with_category(
        self, category: str | None = None
    ) -> list[CarModel]:
        """카테고리별 차종 목록"""
        stmt = select(CarModelORM)

        if category:
            stmt = stmt.where(CarModelORM.category == category)

        stmt = stmt.order_by(CarModelORM.name)
        result = await self._session.execute(stmt)
        return [self._to_pydantic(row) for row in result.scalars().all()]

    async def sync_from_api(self, api_client) -> dict:
        """Carmore API에서 차종 정보 동기화"""
        sync_result = {
            "total": 0,
            "success": 0,
            "error": None,
            "synced_at": utc_now().isoformat(),
        }

        try:
            response = api_client.get_car_models()
            if not response.success:
                sync_result["error"] = response.error
                return sync_result

            models = response.data if isinstance(response.data, list) else []
            sync_result["total"] = len(models)

            if models:
                sync_result["success"] = await self.upsert_batch(models)

        except Exception as e:
            sync_result["error"] = str(e)

        return sync_result
