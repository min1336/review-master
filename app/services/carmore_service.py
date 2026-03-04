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

