"""
Carmore 연동 Service - 외부 API 연동 비즈니스 로직
"""
from typing import Optional, List

from crud import UnitOfWork


class CarmoreService:
    """Carmore API 연동 비즈니스 로직"""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def get_affiliates(
        self,
        location_type: Optional[str] = None,
        is_active: bool = True
    ) -> List[dict]:
        """업체 목록 조회"""
        affiliates = await self.uow.affiliates.get_all_with_filters(
            location_type=location_type,
            is_active=is_active
        )
        return [a.model_dump() for a in affiliates]

    async def get_affiliate(self, affiliate_index: int) -> Optional[dict]:
        """업체 상세 조회"""
        affiliate = await self.uow.affiliates.get_by_index(affiliate_index)
        return affiliate.model_dump() if affiliate else None

    async def sync_affiliates(self, api_client) -> dict:
        """Carmore API에서 업체 정보 동기화"""
        return await self.uow.affiliates.sync_from_api(api_client)

    async def get_car_models(self, category: Optional[str] = None) -> List[dict]:
        """차종 목록 조회"""
        return await self.uow.car_models.get_all_with_category(category)

    async def get_car_model(self, model_id: str) -> Optional[dict]:
        """차종 상세 조회"""
        return await self.uow.car_models.get_by_model_id(model_id)

    async def sync_car_models(self, api_client) -> dict:
        """Carmore API에서 차종 정보 동기화"""
        return await self.uow.car_models.sync_from_api(api_client)
