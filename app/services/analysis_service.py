"""
분석 페이지 Service - 비즈니스 로직

담당:
- 필터 옵션 조회
- 필터링된 리뷰 조회
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from schemas.dto import (
    AnalysisReviewDTO,
    AnalysisReviewListDTO,
    BranchOptionDTO,
    FilterOptionsDTO,
)

if TYPE_CHECKING:
    from repository.review_repository import BranchReviewRepository
    from repository.summary_repository import SummaryRepository

logger = logging.getLogger(__name__)

# 상수 정의
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
FILTER_QUERY_LIMIT = 10000  # 필터 옵션 조회 시 최대 개수


# ==============================================================================
# 커스텀 예외 클래스
# ==============================================================================


class AnalysisServiceError(Exception):
    """분석 서비스 기본 예외"""

    pass


class FilterOptionsError(AnalysisServiceError):
    """필터 옵션 조회 실패"""

    pass


class ReviewSearchError(AnalysisServiceError):
    """리뷰 검색 실패"""

    pass


class DatabaseConnectionError(AnalysisServiceError):
    """DB 연결 실패"""

    pass


class AnalysisService:
    """분석 페이지 비즈니스 로직"""

    def __init__(
        self,
        review_repo: BranchReviewRepository,
        summary_repo: SummaryRepository,
    ):
        self.review_repo = review_repo
        self.summary_repo = summary_repo

    async def get_filter_options(self) -> FilterOptionsDTO:
        """
        필터 옵션 조회 (계층형 필터 지원)

        Returns:
            FilterOptionsDTO: 필터 옵션 데이터
                - regions: 지역 목록
                - companies: 업체 목록
                - branches: 지점 목록 (branch_id, branch_name, region, company_name 포함)

        Raises:
            FilterOptionsError: 필터 옵션 조회 실패 시
            DatabaseConnectionError: DB 연결 실패 시
        """
        try:
            # summaries를 한 번만 조회하여 재사용 (성능 최적화)
            summaries = await self.summary_repo.get_all_with_filters(
                limit=FILTER_QUERY_LIMIT
            )

            # 지역-지점 매핑 생성
            region_map = {s.branch_id: s.region for s in summaries if s.region}

            # 업체-지점 정보 조회 (branch_reviews)
            companies, branches = await self._get_company_and_branch_options_with_region(
                region_map
            )

            # 지역 목록 (branches에 있는 지역만)
            regions = sorted({b.region for b in branches if b.region})

            return FilterOptionsDTO(
                regions=regions,
                companies=companies,
                branches=branches,
            )

        except ConnectionError as e:
            logger.error(f"Database connection failed: {e}")
            raise DatabaseConnectionError(f"DB 연결 실패: {e}") from e
        except Exception as e:
            logger.error(f"Failed to get filter options: {e}")
            raise FilterOptionsError(f"필터 옵션 조회 실패: {e}") from e

    async def get_filtered_reviews(
        self,
        regions: list[str] | None = None,
        companies: list[str] | None = None,
        branch_ids: list[int] | None = None,
        sentiment: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "latest",
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        is_new: bool | None = None,
    ) -> AnalysisReviewListDTO:
        """
        필터링된 리뷰 조회

        Args:
            regions: 지역 필터 목록
            companies: 업체명 필터 목록
            branch_ids: 지점 ID 필터 목록
            sentiment: 감정 필터 (positive, negative, neutral)
            date_from: 시작일 (YYYY-MM-DD)
            date_to: 종료일 (YYYY-MM-DD)
            sort_by: 정렬 기준 (latest, rating, review_count, name)
            limit: 조회 개수 (기본 20, 최대 100)
            offset: 페이징 오프셋

        Returns:
            AnalysisReviewListDTO: 리뷰 목록과 전체 개수

        Raises:
            ReviewSearchError: 리뷰 검색 실패 시
            DatabaseConnectionError: DB 연결 실패 시
        """
        try:
            # limit 검증
            limit = min(limit, MAX_PAGE_SIZE)

            # summaries는 지역 필터가 있을 때만 조회 (성능 최적화)
            summaries = None
            if regions:
                summaries = await self.summary_repo.get_all_with_filters(
                    limit=FILTER_QUERY_LIMIT
                )

            # 지역 필터가 있으면 해당 지역의 branch_id 조회
            region_branch_ids = None
            if regions and summaries is not None:
                region_branch_ids = {
                    s.branch_id for s in summaries if s.region in regions
                }
                if not region_branch_ids:
                    return AnalysisReviewListDTO(reviews=[], total=0)

            # 업체명 필터가 있으면 해당 업체의 branch_id 조회
            # (company_name은 인덱스가 없어 느림 → branch_id로 변환)
            company_branch_ids = None
            if companies:
                company_branch_ids = await self._get_branch_ids_by_companies(companies)
                if not company_branch_ids:
                    return AnalysisReviewListDTO(reviews=[], total=0)

            # 모든 branch_ids 조건 결합 (교집합)
            effective_branch_ids = self._merge_all_branch_ids(
                branch_ids, region_branch_ids, company_branch_ids
            )

            # 결합 결과가 빈 리스트면 빈 결과 반환
            if effective_branch_ids is not None and len(effective_branch_ids) == 0:
                return AnalysisReviewListDTO(reviews=[], total=0)

            # 리뷰 조회 (company_names 대신 branch_ids 사용)
            result = await self.review_repo.search_with_filters(
                branch_ids=effective_branch_ids,
                sentiment=sentiment,
                date_from=date_from,
                date_to=date_to,
                sort_by=sort_by,
                limit=limit,
                offset=offset,
                is_new=is_new,
            )

            # DTO 변환
            reviews = [AnalysisReviewDTO.from_db_row(row) for row in result.reviews]

            return AnalysisReviewListDTO(
                reviews=reviews,
                total=result.total,
            )

        except ConnectionError as e:
            logger.error(f"Database connection failed: {e}")
            raise DatabaseConnectionError(f"DB 연결 실패: {e}") from e
        except Exception as e:
            logger.error(f"Failed to get filtered reviews: {e}")
            raise ReviewSearchError(f"리뷰 검색 실패: {e}") from e

    async def _get_company_and_branch_options_with_region(
        self, region_map: dict[int, str]
    ) -> tuple[list[str], list[BranchOptionDTO]]:
        """업체명과 지점 목록 조회 (region 포함)"""
        stats = await self.review_repo.get_stats()

        companies = set()
        branches_dict: dict[int, BranchOptionDTO] = {}

        for s in stats:
            if s.get("company_name"):
                companies.add(s["company_name"])
            if s.get("branch_id") and s.get("branch_name"):
                bid = s["branch_id"]
                branches_dict[bid] = BranchOptionDTO(
                    branch_id=bid,
                    branch_name=s["branch_name"],
                    company_name=s.get("company_name") or "",
                    region=region_map.get(bid) or "",
                )

        # 정렬된 목록 반환
        sorted_companies = sorted(companies)
        sorted_branches = sorted(
            branches_dict.values(), key=lambda x: x.branch_name
        )

        return sorted_companies, sorted_branches

    async def _get_branch_ids_by_companies(self, companies: list[str]) -> set[int]:
        """업체명에 해당하는 branch_id 목록 조회 (성능 최적화용)"""
        stats = await self.review_repo.get_stats()
        return {
            s["branch_id"]
            for s in stats
            if s.get("company_name") in companies and s.get("branch_id")
        }

    def _merge_all_branch_ids(
        self,
        branch_ids: list[int] | None,
        region_branch_ids: set[int] | None,
        company_branch_ids: set[int] | None,
    ) -> list[int] | None:
        """모든 branch_ids 조건을 교집합으로 결합"""
        sets_to_merge = []

        if branch_ids is not None:
            sets_to_merge.append(set(branch_ids))
        if region_branch_ids is not None:
            sets_to_merge.append(region_branch_ids)
        if company_branch_ids is not None:
            sets_to_merge.append(company_branch_ids)

        if not sets_to_merge:
            return None

        # 모든 집합의 교집합
        result = sets_to_merge[0]
        for s in sets_to_merge[1:]:
            result = result & s

        return list(result)
