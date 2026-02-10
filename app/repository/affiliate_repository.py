"""
업체/제휴점 Repository (affiliates, car_models 테이블)
"""

from __future__ import annotations

import logging
from datetime import datetime

from core.timezone import utc_now

from models.affiliate import Affiliate, CarModel

from .base import BaseRepository

logger = logging.getLogger(__name__)


class AffiliateRepository(BaseRepository[Affiliate]):
    """affiliates 테이블 Repository"""

    model = Affiliate

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

        result = (
            await self._client.table(self.table_name)
            .upsert(rows, on_conflict="affiliate_index")
            .execute()
        )

        return len(result.data) if result.data else 0

    async def get_by_index(self, affiliate_index: int) -> Affiliate | None:
        """업체 인덱스로 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("*")
            .eq("affiliate_index", affiliate_index)
            .execute()
        )
        return self.model(**result.data[0]) if result.data else None

    async def get_all_with_filters(
        self, location_type: str | None = None, is_active: bool = True
    ) -> list[Affiliate]:
        """필터링된 업체 목록"""
        query = self._client.table(self.table_name).select("*")

        if location_type:
            query = query.eq("location_type", location_type)
        if is_active is not None:
            query = query.eq("is_active", is_active)

        result = await query.order("name").execute()
        return [self.model(**row) for row in result.data]

    async def sync_from_api(self, api_client) -> dict:
        """Carmore API에서 업체 정보 동기화"""
        result = {
            "total": 0,
            "success": 0,
            "error": None,
            "synced_at": utc_now().isoformat(),
        }

        try:
            response = api_client.get_affiliates(location_type="PARTNERS")
            if not response.success:
                result["error"] = response.error
                return result

            if isinstance(response.data, dict):
                affiliates = response.data.get("affiliates", [])
            elif isinstance(response.data, list):
                affiliates = response.data
            else:
                affiliates = []

            result["total"] = len(affiliates)

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

                result["success"] = await self.upsert_batch(normalized)

        except Exception as e:
            result["error"] = str(e)

        return result


class CarModelRepository(BaseRepository[CarModel]):
    """car_models 테이블 Repository"""

    model = CarModel

    @property
    def table_name(self) -> str:
        return "car_models"

    async def upsert_batch(self, car_models: list[dict]) -> int:
        """차종 정보 일괄 저장"""
        if not car_models:
            return 0

        rows = []
        for model in car_models:
            model_id = model.get("model_id") or model.get("modelId") or model.get("id")
            row = {
                "model_id": model_id,
                "name": model.get("name") or model.get("modelName", ""),
                "name_en": model.get("name_en") or model.get("nameEn", ""),
                "category": model.get("category") or model.get("carCategory", ""),
                "brand": model.get("brand") or model.get("manufacturer", ""),
                "seats": model.get("seats") or model.get("maxPassengers"),
                "fuel_type": model.get("fuel_type") or model.get("fuelType", ""),
                "transmission": model.get("transmission", ""),
                "image_url": model.get("image_url") or model.get("imageUrl", ""),
                "raw_data": model,
            }
            if row["model_id"]:
                rows.append(row)

        if not rows:
            return 0

        result = (
            await self._client.table(self.table_name)
            .upsert(rows, on_conflict="model_id")
            .execute()
        )

        return len(result.data) if result.data else 0

    async def get_by_model_id(self, model_id: str) -> CarModel | None:
        """차종 ID로 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("*")
            .eq("model_id", model_id)
            .execute()
        )
        return self.model(**result.data[0]) if result.data else None

    async def get_all_with_category(
        self, category: str | None = None
    ) -> list[CarModel]:
        """카테고리별 차종 목록"""
        query = self._client.table(self.table_name).select("*")

        if category:
            query = query.eq("category", category)

        result = await query.order("name").execute()
        return [self.model(**row) for row in result.data]

    async def sync_from_api(self, api_client) -> dict:
        """Carmore API에서 차종 정보 동기화"""
        result = {
            "total": 0,
            "success": 0,
            "error": None,
            "synced_at": utc_now().isoformat(),
        }

        try:
            response = api_client.get_car_models()
            if not response.success:
                result["error"] = response.error
                return result

            models = response.data if isinstance(response.data, list) else []
            result["total"] = len(models)

            if models:
                result["success"] = await self.upsert_batch(models)

        except Exception as e:
            result["error"] = str(e)

        return result
