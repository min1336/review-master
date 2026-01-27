"""
Carmore 연동 Service - 외부 API 연동 비즈니스 로직
"""

from __future__ import annotations


class CarmoreService:
    """Carmore API 연동 비즈니스 로직"""

    def __init__(self, affiliate_repo):
        self.affiliate_repo = affiliate_repo

    async def get_affiliates(
        self, location_type: str | None = None, is_active: bool = True
    ) -> list[dict]:
        """업체 목록 조회"""
        affiliates = await self.affiliate_repo.get_all_with_filters(
            location_type=location_type, is_active=is_active
        )
        return [a.model_dump() for a in affiliates]

    async def get_affiliate(self, affiliate_index: int) -> dict | None:
        """업체 상세 조회"""
        affiliate = await self.affiliate_repo.get_by_index(affiliate_index)
        return affiliate.model_dump() if affiliate else None

    async def sync_affiliates(self, api_client) -> dict:
        """Carmore API에서 업체 정보 동기화"""
        return await self.affiliate_repo.sync_from_api(api_client)
