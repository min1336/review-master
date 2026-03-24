"""
분석 페이지 Service - 비즈니스 로직

담당:
- 필터 옵션 조회
- 필터링된 리뷰 조회
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from core.utils import TTLCache
from schemas.dto import (
    AnalysisReviewDTO,
    AnalysisReviewListDTO,
    BranchOptionDTO,
    FilterOptionsDTO,
)

if TYPE_CHECKING:
    from infrastructure.athena_client import AthenaClient
    from repository.affiliate_repository import AffiliateRepository
    from repository.review_repository import NewReviewRepository
    from repository.review_repository import BranchReviewRepository
    from repository.summary_repository import SummaryRepository

logger = logging.getLogger(__name__)

# 상수 정의
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 1000
FILTER_QUERY_LIMIT = 10000  # 필터 옵션 조회 시 최대 개수

# 필터 옵션 캐시 (5분 TTL, 무효화 없음)
# 지점/업체/지역 데이터는 동기화 시에만 변경되므로 5분 지연 허용
_filter_cache = TTLCache(300)


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


class CarmoreService:
    """Carmore API 연동 비즈니스 로직"""

    def __init__(self, affiliate_repo: AffiliateRepository):
        self.affiliate_repo = affiliate_repo

    async def get_affiliates(
        self, location_type: str | None = None, is_active: bool = True
    ) -> list[dict]:
        """업체 목록 조회"""
        affiliates = await self.affiliate_repo.get_all_with_filters(
            location_type=location_type, is_active=is_active
        )
        return [a.model_dump() for a in affiliates]


class AnalysisService:
    """분석 페이지 비즈니스 로직"""

    def __init__(
        self,
        review_repo: BranchReviewRepository,
        summary_repo: SummaryRepository,
        athena_client: AthenaClient | None = None,
        new_review_repo: NewReviewRepository | None = None,
    ):
        self.review_repo = review_repo
        self.summary_repo = summary_repo
        self.athena_client = athena_client
        self.new_review_repo = new_review_repo

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
        cached = _filter_cache.get("filter_options")
        if cached is not None:
            return cached

        try:
            # summaries를 한 번만 조회하여 재사용 (성능 최적화)
            summaries = await self.summary_repo.get_all_with_filters(
                limit=FILTER_QUERY_LIMIT
            )

            # 지역-지점 매핑 생성
            region_map = {s.branch_id: s.region for s in summaries if s.region}

            # 업체-지점 정보 조회 (경량 RPC + summaries 재활용)
            companies, branches = await self._get_company_and_branch_options_with_region(
                region_map, summaries
            )

            # 지역 목록 (branches에 있는 지역만)
            regions = sorted({b.region for b in branches if b.region})

            # 8대 분류 지역 그룹 생성 (필터 드롭다운용)
            from core.constants import REGION_GROUP_MAP, REGION_GROUP_ORDER

            groups: dict[str, list[str]] = {}
            for r in regions:
                prefix = r.split()[0] if r and r.strip() else ""
                group = REGION_GROUP_MAP.get(prefix, "해외")
                groups.setdefault(group, []).append(r)
            region_groups = {
                g: sorted(groups[g]) for g in REGION_GROUP_ORDER if g in groups
            }

            result = FilterOptionsDTO(
                regions=regions,
                region_groups=region_groups,
                companies=companies,
                branches=branches,
            )
            _filter_cache.set("filter_options", result)
            return result

        except ConnectionError as e:
            logger.error("Database connection failed: %s", e)
            raise DatabaseConnectionError(f"DB 연결 실패: {e}") from e
        except Exception as e:
            logger.error("Failed to get filter options: %s", e)
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

            # 신규 리뷰 분기: new_reviews 테이블에서 content 포함 조회
            if is_new is True and self.new_review_repo:
                new_result = await self._search_new_reviews_with_sentiment(
                    effective_branch_ids, date_from, date_to, sort_by, limit, offset
                )
                if new_result is not None:
                    return new_result
                # new_reviews가 비어있으면 branch_reviews로 폴백

            # Athena 분기: is_new만 Supabase 전용 (sentiment는 평점 기반 계산 가능)
            use_athena = (
                self.athena_client is not None
                and is_new is None
            )

            if use_athena:
                return await self._search_via_athena(
                    effective_branch_ids, date_from, date_to, sort_by, limit, offset,
                    sentiment=sentiment,
                )

            # 기존 Supabase 경로
            return await self._search_via_supabase(
                effective_branch_ids, sentiment, date_from, date_to, sort_by, limit, offset,
                is_new=is_new,
            )

        except ConnectionError as e:
            logger.error("Database connection failed: %s", e)
            raise DatabaseConnectionError(f"DB 연결 실패: {e}") from e
        except Exception as e:
            logger.error("Failed to get filtered reviews: %s", e)
            raise ReviewSearchError(f"리뷰 검색 실패: {e}") from e

    async def _search_new_reviews_with_sentiment(
        self,
        branch_ids: list[int] | None,
        date_from: str | None,
        date_to: str | None,
        sort_by: str,
        limit: int,
        offset: int,
    ) -> AnalysisReviewListDTO | None:
        """new_reviews 테이블에서 조회 후 sentiment 보강.

        결과가 있으면 AnalysisReviewListDTO 반환, 비어있으면 None 반환
        (호출자가 branch_reviews로 폴백하도록).
        """
        result = await self.new_review_repo.search_with_filters(
            branch_ids=branch_ids,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

        if result.total == 0:
            return None

        # sentiment 보강: branch_reviews에서 병합
        review_ids = [
            int(r["review_id"]) for r in result.reviews if r.get("review_id")
        ]
        sentiment_map = {}
        if review_ids:
            sentiment_map = await self.review_repo.get_sentiments_by_review_ids(review_ids)
        for row in result.reviews:
            rid = int(row["review_id"]) if row.get("review_id") else None
            if rid and rid in sentiment_map:
                row["sentiment"] = sentiment_map[rid]

        reviews = [AnalysisReviewDTO.from_db_row(row) for row in result.reviews]
        return AnalysisReviewListDTO(reviews=reviews, total=result.total)

    async def _search_via_supabase(
        self,
        branch_ids: list[int] | None,
        sentiment: str | None,
        date_from: str | None,
        date_to: str | None,
        sort_by: str,
        limit: int,
        offset: int,
        is_new: bool | None = None,
    ) -> AnalysisReviewListDTO:
        """기존 Supabase(branch_reviews) 경로로 리뷰 검색 후 DTO 변환."""
        result = await self.review_repo.search_with_filters(
            branch_ids=branch_ids,
            sentiment=sentiment,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
            is_new=is_new,
        )
        reviews = [AnalysisReviewDTO.from_db_row(row) for row in result.reviews]
        return AnalysisReviewListDTO(reviews=reviews, total=result.total)

    async def _search_via_athena(
        self,
        branch_ids: list[int] | None,
        date_from: str | None,
        date_to: str | None,
        sort_by: str,
        limit: int,
        offset: int,
        sentiment: str | None = None,
    ) -> AnalysisReviewListDTO:
        """Athena를 통한 리뷰 검색 (블로킹 방지: to_thread)

        sentiment 필터가 있으면 더 많이 가져와서 DTO의 평점 기반
        감정 계산 후 후필터링한다.
        """
        try:
            # sentiment 필터 시 over-fetch 후 후필터링
            fetch_limit = limit
            fetch_offset = offset
            if sentiment:
                fetch_limit = 500
                fetch_offset = 0

            rows, athena_total = await asyncio.to_thread(
                self.athena_client.fetch_reviews_with_filters,
                branch_ids=branch_ids,
                date_from=date_from,
                date_to=date_to,
                sort_by=sort_by,
                limit=fetch_limit,
                offset=fetch_offset,
            )

            # 파이프라인 감정 보강: branch_reviews에서 sentiment 병합
            review_ids = [int(r["review_id"]) for r in rows if r.get("review_id")]
            if review_ids:
                sentiment_map = await self.review_repo.get_sentiments_by_review_ids(review_ids)
                for row in rows:
                    rid = int(row["review_id"]) if row.get("review_id") else None
                    if rid and rid in sentiment_map:
                        row["sentiment"] = sentiment_map[rid]

            reviews = [AnalysisReviewDTO.from_db_row(row) for row in rows]

            # sentiment 후필터링 (DTO의 _calculate_sentiment 결과 기준)
            if sentiment:
                reviews = [r for r in reviews if r.sentiment == sentiment]
                total = len(reviews)
                reviews = reviews[offset:offset + limit]
            else:
                total = athena_total

            return AnalysisReviewListDTO(reviews=reviews, total=total)

        except Exception as e:
            logger.warning("Athena 검색 실패, Supabase 폴백: %s", e)
            # Supabase 폴백
            result = await self.review_repo.search_with_filters(
                branch_ids=branch_ids,
                sentiment=sentiment,
                date_from=date_from,
                date_to=date_to,
                sort_by=sort_by,
                limit=limit,
                offset=offset,
            )
            reviews = [AnalysisReviewDTO.from_db_row(row) for row in result.reviews]
            return AnalysisReviewListDTO(reviews=reviews, total=result.total)

    async def export_to_excel(
        self,
        regions: list[str] | None = None,
        companies: list[str] | None = None,
        branch_ids: list[int] | None = None,
        sentiment: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "latest",
    ) -> tuple["io.BytesIO", str]:
        """
        필터링된 리뷰를 엑셀 파일로 내보내기

        Args:
            regions~sort_by: get_filtered_reviews와 동일한 필터

        Returns:
            (BytesIO 엑셀 데이터, 파일명 문자열)
        """
        import io
        from datetime import datetime

        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        # 최대 10000개까지 내보내기
        result = await self.get_filtered_reviews(
            regions=regions,
            companies=companies,
            branch_ids=branch_ids,
            sentiment=sentiment,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            limit=10000,
            offset=0,
        )

        # 엑셀 워크북 생성
        wb = Workbook()
        ws = wb.active
        ws.title = "리뷰 목록"

        # 스타일 정의
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        # 헤더 작성
        headers = [
            "번호", "리뷰ID", "업체명", "지점명", "리뷰 날짜",
            "감정", "서비스 평점", "차량 평점", "편의성 평점", "리뷰 내용",
        ]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        sentiment_map = {
            "positive": "긍정", "negative": "부정", "neutral": "중립",
        }

        # 데이터 작성
        for row_idx, review in enumerate(result.reviews, 2):
            ws.cell(row=row_idx, column=1, value=row_idx - 1).border = thin_border
            ws.cell(row=row_idx, column=2, value=review.review_id).border = thin_border
            ws.cell(row=row_idx, column=3, value=review.company_name).border = thin_border
            ws.cell(row=row_idx, column=4, value=review.branch_name).border = thin_border

            date_str = ""
            if review.review_date:
                try:
                    date_obj = datetime.fromisoformat(review.review_date.replace("Z", "+00:00"))
                    date_str = date_obj.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    date_str = review.review_date
            ws.cell(row=row_idx, column=5, value=date_str).border = thin_border

            ws.cell(row=row_idx, column=6, value=sentiment_map.get(review.sentiment, "-")).border = thin_border
            ws.cell(row=row_idx, column=7, value=review.rating_service).border = thin_border
            ws.cell(row=row_idx, column=8, value=review.rating_car).border = thin_border
            ws.cell(row=row_idx, column=9, value=review.rating_convenience).border = thin_border

            content_cell = ws.cell(row=row_idx, column=10, value=review.content)
            content_cell.border = thin_border
            content_cell.alignment = Alignment(wrap_text=True)

        # 열 너비 조정
        column_widths = [8, 12, 15, 20, 12, 8, 12, 12, 12, 60]
        for col, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = width

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # 파일명 생성
        if companies and len(companies) == 1:
            company_part = companies[0]
        elif companies and len(companies) > 1:
            company_part = f"{companies[0]}외{len(companies)-1}"
        else:
            company_part = "전체업체"

        if branch_ids and len(branch_ids) == 1:
            branch_name = None
            for review in result.reviews:
                if review.branch_name:
                    branch_name = review.branch_name
                    break
            branch_part = branch_name if branch_name else "지점"
        elif branch_ids and len(branch_ids) > 1:
            branch_part = f"{len(branch_ids)}개지점"
        else:
            branch_part = "전체지점"

        sentiment_names = {"positive": "긍정", "negative": "부정", "neutral": "중립"}
        sentiment_part = sentiment_names.get(sentiment, "전체감정") if sentiment else "전체감정"

        sort_names = {"latest": "최신순", "rating_low": "낮은평점순"}
        sort_part = sort_names.get(sort_by, "최신순")

        if date_from and date_to:
            period_part = f"{date_from}~{date_to}"
        elif date_from:
            period_part = f"{date_from}~"
        elif date_to:
            period_part = f"~{date_to}"
        else:
            period_part = "전체기간"

        filename = f"{company_part}_{branch_part}_{sentiment_part}_{sort_part}_{period_part}_자료.xlsx"

        return output, filename

    async def _get_company_and_branch_options_with_region(
        self, region_map: dict[int, str], summaries: list
    ) -> tuple[list[str], list[BranchOptionDTO]]:
        """업체명과 지점 목록 조회 (region 포함)"""
        # 경량 RPC: branch_id → company_name 매핑만 조회
        company_map = await self.review_repo.get_branch_company_map()

        companies = set()
        branches_dict: dict[int, BranchOptionDTO] = {}

        for s in summaries:
            bid = s.branch_id
            company = company_map.get(bid, "")
            if company:
                companies.add(company)
            if bid and s.branch_name:
                branches_dict[bid] = BranchOptionDTO(
                    branch_id=bid,
                    branch_name=s.branch_name,
                    company_name=company,
                    region=region_map.get(bid) or "",
                )

        sorted_companies = sorted(companies)
        sorted_branches = sorted(
            branches_dict.values(), key=lambda x: x.branch_name
        )
        return sorted_companies, sorted_branches

    async def _get_branch_ids_by_companies(self, companies: list[str]) -> set[int]:
        """업체명에 해당하는 branch_id 목록 조회 (성능 최적화용)"""
        company_map = await self.review_repo.get_branch_company_map()
        return {
            bid for bid, company in company_map.items()
            if company in companies
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
