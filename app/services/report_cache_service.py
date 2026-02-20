"""리포트 캐시 서비스

저장된 리포트 조회, 목록, 캐시 무효화 판단을 담당합니다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from core.constants import (
    CACHE_MIN_NEW_REVIEWS,
    CACHE_SENTIMENT_DRIFT,
    CACHE_TAG_COUNT_RATIO,
    REVIEW_CHANGE_THRESHOLD,
)
from schemas.report import ReportData

if TYPE_CHECKING:
    from repository.branch_tag_repository import BranchTagRepository
    from repository.report_repository import ReportRepository
    from repository.review_repository import BranchReviewRepository

logger = logging.getLogger(__name__)


class ReportCacheService:
    """리포트 캐시 조회 및 무효화 판단"""

    def __init__(
        self,
        report_repo: ReportRepository,
        review_repo: BranchReviewRepository,
        branch_tag_repo: BranchTagRepository,
    ) -> None:
        self.report_repo = report_repo
        self.review_repo = review_repo
        self.branch_tag_repo = branch_tag_repo

    async def get_saved_report(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> ReportData | None:
        """저장된 리포트 조회"""
        if not self.report_repo:
            return None

        saved = await self.report_repo.get_by_branch_and_period(
            branch_id, start_date, end_date
        )

        if not saved:
            return None

        report_data = saved.get("report_data")
        if isinstance(report_data, str):
            report_data = json.loads(report_data)

        return ReportData(**report_data)

    async def get_report_list(self, branch_id: int, limit: int = 10) -> list[dict]:
        """지점의 리포트 목록 조회"""
        if not self.report_repo:
            return []

        return await self.report_repo.get_all_by_branch(branch_id, limit)

    async def should_invalidate_cache(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
        saved_report: ReportData,
    ) -> bool:
        """캐시 무효화 여부 결정"""
        new_reviews = await self._count_new_reviews(
            branch_id, start_date, end_date, saved_report
        )
        if new_reviews < CACHE_MIN_NEW_REVIEWS:
            return False

        return await self._has_significant_sentiment_drift(
            branch_id, new_reviews, saved_report
        )

    @staticmethod
    def extract_saved_tag_stats(saved_report: ReportData) -> tuple[int, float] | None:
        """
        저장된 리포트에서 (총 태그 언급 수, 긍정률%) 추출.
        top_tags_detail이 없으면 None 반환 → fallback으로 volume 체크만 수행.
        """
        tags = saved_report.top_tags_detail
        if not tags:
            return None

        total = sum(t.count for t in tags)
        if total == 0:
            return None

        weighted_pos = sum(t.positive_ratio * t.count for t in tags)
        pos_ratio = weighted_pos / total  # 0~100 스케일

        return total, pos_ratio

    async def _count_new_reviews(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
        saved_report: ReportData,
    ) -> int:
        """현재 리뷰 수와 저장 시점 차이 계산"""
        current_count = await self.review_repo.count_by_branch(
            branch_id=branch_id,
            review_date_from=start_date,
            review_date_to=end_date,
        )
        return current_count - saved_report.total_reviews

    async def _has_significant_sentiment_drift(
        self,
        branch_id: int,
        new_reviews: int,
        saved_report: ReportData,
    ) -> bool:
        """태그 분포 변화가 유의미한지 검사 (Signal A | Signal B)"""
        saved_stats = self.extract_saved_tag_stats(saved_report)
        if saved_stats is None:
            return new_reviews >= REVIEW_CHANGE_THRESHOLD

        saved_total, saved_pos_ratio = saved_stats

        current_tags = await self.branch_tag_repo.get_by_branch(
            branch_id, period_type="all", limit=100
        )
        if not current_tags:
            return False

        current_total_pos = sum(bt.positive_count or 0 for bt in current_tags)
        current_total_neg = sum(bt.negative_count or 0 for bt in current_tags)
        current_total = current_total_pos + current_total_neg

        if current_total == 0:
            return False

        current_pos_ratio = (current_total_pos / current_total) * 100.0

        # Signal A: 태그 수 변화 >= 15%
        tag_count_ratio = abs(current_total - saved_total) / max(saved_total, 1)
        signal_a = tag_count_ratio >= CACHE_TAG_COUNT_RATIO

        # Signal B: 긍정률 변화 >= 8%p
        signal_b = abs(current_pos_ratio - saved_pos_ratio) >= CACHE_SENTIMENT_DRIFT

        should_invalidate = signal_a or signal_b
        if should_invalidate:
            logger.info(
                "캐시 무효화: branch_id=%s, 태그수 변화=%.1f%% (신호A=%s), "
                "긍정률 %.1f%%→%.1f%% (신호B=%s)",
                branch_id, tag_count_ratio * 100, signal_a,
                saved_pos_ratio, current_pos_ratio, signal_b,
            )
        return should_invalidate
