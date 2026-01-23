"""
UnitOfWork 패턴
모든 CRUD 하나로 묶어서 관리
Service 의존성을 단순화
"""
from dataclasses import dataclass
from supabase import AsyncClient

from .summary_crud import SummaryRepository
from .branch_tag_crud import BranchTagRepository
from .tag_crud import TagRepository, CategoryRepository, MappingRepository
from .review_crud import ReviewRepository, BranchReviewRepository
from .sentiment_crud import SentimentRepository
from .affiliate_crud import AffiliateRepository, CarModelRepository


@dataclass
class UnitOfWork:
    """
    모든 Repository를 하나로 묶어서 관리

    Usage:
        async def get_uow(client: AsyncClient) -> UnitOfWork:
            return UnitOfWork(client)

        class SummaryService:
            def __init__(self, uow: UnitOfWork):
                self.uow = uow

            async def get_summary_with_tags(self, branch_id: int):
                summary = await self.uow.summaries.get_by_branch_id(branch_id)
                tags = await self.uow.branch_tags.get_by_branch(branch_id)
                return {"summary": summary, "tags": tags}
    """
    client: AsyncClient

    @property
    def summaries(self) -> SummaryRepository:
        """지점 요약 Repository"""
        return SummaryRepository(self.client)

    @property
    def branch_tags(self) -> BranchTagRepository:
        """지점별 태그 Repository"""
        return BranchTagRepository(self.client)

    @property
    def tags(self) -> TagRepository:
        """태그 Repository"""
        return TagRepository(self.client)

    @property
    def categories(self) -> CategoryRepository:
        """카테고리 Repository"""
        return CategoryRepository(self.client)

    @property
    def mappings(self) -> MappingRepository:
        """키워드 매핑 Repository"""
        return MappingRepository(self.client)

    @property
    def reviews(self) -> ReviewRepository:
        """최근 리뷰 Repository"""
        return ReviewRepository(self.client)

    @property
    def branch_reviews(self) -> BranchReviewRepository:
        """원본 리뷰 Repository"""
        return BranchReviewRepository(self.client)

    @property
    def sentiments(self) -> SentimentRepository:
        """감정통계 Repository"""
        return SentimentRepository(self.client)

    @property
    def affiliates(self) -> AffiliateRepository:
        """업체 Repository"""
        return AffiliateRepository(self.client)

    @property
    def car_models(self) -> CarModelRepository:
        """차종 Repository"""
        return CarModelRepository(self.client)
