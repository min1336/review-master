"""
AI 리포트 서비스

지점별 맞춤형 컨설팅 리포트를 생성합니다.
- 기간별 요약 분석
- 차량별 평가 분석 (구현 예정)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

from core.constants import REVIEW_CHANGE_THRESHOLD
from core.timezone import to_kst, utc_now
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from repository.branch_tag_repository import BranchTagRepository
    from repository.report_repository import ReportRepository
    from repository.review_repository import BranchReviewRepository
    from repository.sentiment_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository
    from infrastructure.pdf.generator import PDFGenerator
    from services.report_ai_generator import ReportAIGenerator
    from services.report_cache_service import ReportCacheService
    from services.tag_stats_calculator import TagStatsCalculator
    from services.vehicle_analyzer import VehicleAnalyzer

# 데이터 모델 — schemas/report.py 에서 정의, 하위호환용 re-export
from schemas.report import (  # noqa: F401
    TagRankItem,
    VehicleRankItem,
    AffiliateEvaluation,
    VehicleEvaluation,
    VehicleAnalysis,
    StrengthItem,
    TopTagItem,
    ReportData,
)




class ReportService:
    """AI 리포트 비즈니스 로직"""

    def __init__(
        self,
        summary_repo: SummaryRepository,
        review_repo: BranchReviewRepository,
        branch_tag_repo: BranchTagRepository,
        report_repo: ReportRepository | None = None,
        sentiment_repo: SentimentRepository | None = None,
        pdf_generator: PDFGenerator | None = None,
        vehicle_analyzer: VehicleAnalyzer | None = None,
        cache_service: ReportCacheService | None = None,
        tag_calculator: TagStatsCalculator | None = None,
        ai_generator: ReportAIGenerator | None = None,
    ) -> None:
        self.summary_repo = summary_repo
        self.review_repo = review_repo
        self.branch_tag_repo = branch_tag_repo
        self.report_repo = report_repo
        self.sentiment_repo = sentiment_repo
        self._pdf_generator = pdf_generator
        if vehicle_analyzer is None:
            from services.vehicle_analyzer import VehicleAnalyzer as _VA
            vehicle_analyzer = _VA()
        self.vehicle_analyzer = vehicle_analyzer
        self.cache_service = cache_service
        self.tag_calculator = tag_calculator
        self.ai_generator = ai_generator

    # ================================================================
    # PDF 생성 (Infrastructure 위임)
    # ================================================================

    async def generate_pdf(self, report: ReportData) -> bytes:
        """PDF 바이트 생성 (H-1: Service 레이어에서 Infrastructure 호출, H-2: 이벤트 루프 블로킹 방지)"""
        if self._pdf_generator is None:
            from infrastructure.pdf.generator import PDFGenerator
            self._pdf_generator = PDFGenerator()

        return await asyncio.to_thread(self._pdf_generator.generate_simple, report)

    # ================================================================
    # Repository 래핑 메서드 (레이어드 아키텍처 준수)
    # ================================================================

    async def mark_as_viewed(self, report_id: int) -> bool:
        """리포트 조회 표시 (NEW 뱃지 제거)"""
        return await self.report_repo.mark_as_viewed(report_id)

    async def get_report_history(
        self,
        branch_id: int,
        period_start: datetime,
        period_end: datetime,
        limit: int = 10,
    ) -> list[dict]:
        """특정 기간의 리포트 버전 히스토리 조회"""
        return await self.report_repo.get_report_history(
            branch_id=branch_id,
            period_start=period_start,
            period_end=period_end,
            limit=limit,
        )

    async def get_unviewed_count(self, branch_id: int | None = None) -> int:
        """미조회 리포트 개수 조회"""
        return await self.report_repo.get_unviewed_count(branch_id)

    async def get_review_count_summary(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        """
        리포트 생성 전 리뷰 수 사전 확인

        선택된 기간과 표준 4개 기간(1m/3m/6m/12m) + all의 리뷰 수를 한번에 반환합니다.
        """
        from core.timezone import utc_now

        today = utc_now()
        today_date = datetime(today.year, today.month, today.day)
        period_defs = [
            ("1m", 1), ("3m", 3), ("6m", 6), ("12m", 12),
        ]

        # 모든 쿼리를 병렬로 실행
        selected_coro = self.review_repo.count_by_branch(
            branch_id, review_date_from=start_date, review_date_to=end_date,
        )
        period_coros = [
            self.review_repo.count_by_branch(
                branch_id,
                review_date_from=today_date - relativedelta(months=months),
                review_date_to=today,
            )
            for _label, months in period_defs
        ]
        all_coro = self.review_repo.count_by_branch(branch_id)

        results = await asyncio.gather(selected_coro, *period_coros, all_coro)

        selected_count = results[0]
        period_counts: dict[str, int] = {
            label: results[i + 1] for i, (label, _) in enumerate(period_defs)
        }
        period_counts["all"] = results[-1]

        # 추천 기간: threshold 이상인 최단 기간
        recommended_period = None
        for label, _months in period_defs:
            if period_counts[label] >= REVIEW_CHANGE_THRESHOLD:
                recommended_period = label
                break
        if recommended_period is None:
            recommended_period = "all"

        return {
            "selected_count": selected_count,
            "period_counts": period_counts,
            "threshold": REVIEW_CHANGE_THRESHOLD,
            "recommended_period": recommended_period,
        }

    @staticmethod
    def get_top_vehicles(
        vehicle_analysis: list,
        top_n: int = 5,
    ) -> list[dict]:
        """차량 분석 목록에서 건수 내림차순 상위 N개 추출"""
        sorted_vehicles = sorted(
            vehicle_analysis, key=lambda v: v.count, reverse=True,
        )
        return [
            {
                "model": v.model,
                "count": v.count,
                "like_ratio": v.like_ratio,
                "dislike_ratio": v.dislike_ratio,
                "top_praise": v.top_praise,
                "top_issue": v.top_issue,
            }
            for v in sorted_vehicles[:top_n]
        ]

    async def get_branch_region(self, branch_id: int) -> str:
        """지점의 지역 정보 조회"""
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        return summary.region if summary else ""

    # ================================================================
    # 비즈니스 로직
    # ================================================================

    async def get_saved_report(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> ReportData | None:
        """저장된 리포트 조회 (cache_service 위임)"""
        if self.cache_service:
            return await self.cache_service.get_saved_report(branch_id, start_date, end_date)
        if not self.report_repo:
            return None
        import json as _json
        saved = await self.report_repo.get_by_branch_and_period(branch_id, start_date, end_date)
        if not saved:
            return None
        report_data = saved.get("report_data")
        if isinstance(report_data, str):
            report_data = _json.loads(report_data)
        return ReportData(**report_data)

    async def get_report_list(self, branch_id: int, limit: int = 10) -> list[dict]:
        """지점의 리포트 목록 조회 (cache_service 위임)"""
        if self.cache_service:
            return await self.cache_service.get_report_list(branch_id, limit)
        if not self.report_repo:
            return []
        return await self.report_repo.get_all_by_branch(branch_id, limit)

    async def get_or_generate_report(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[ReportData, bool]:
        """
        저장된 리포트가 있으면 반환, 없으면 생성.
        30건 이상 새 리뷰가 쌓이면 캐시를 무효화하고 재생성합니다 (CLT 기반).

        Args:
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일

        Returns:
            (리포트 데이터, 신규 생성 여부)
        """
        saved_report = await self.get_saved_report(branch_id, start_date, end_date)
        if saved_report and self.cache_service:
            try:
                should_invalidate = await self.cache_service.should_invalidate_cache(
                    branch_id, start_date, end_date, saved_report
                )
                if not should_invalidate:
                    return saved_report, False
            except Exception as e:
                logger.warning("캐시 무효화 체크 실패, 캐시 서빙: %s", e)
                return saved_report, False
        elif saved_report:
            return saved_report, False

        # 신규 생성
        report = await self.generate_report(branch_id, start_date, end_date)
        return report, True

    async def regenerate_report(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> ReportData:
        """
        리포트 재생성 (기존 리포트 덮어쓰기)

        Args:
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일

        Returns:
            새로 생성된 리포트
        """
        return await self.generate_report(branch_id, start_date, end_date)

    async def _step_collect(self, branch_id: int, start_date: datetime | None = None, end_date: datetime | None = None) -> dict:
        """
        Step 1: 지점 기본 정보 수집

        Args:
            branch_id: 지점 ID
            start_date: 시작일 (차량 분석 기간 필터용)
            end_date: 종료일 (차량 분석 기간 필터용)

        Returns:
            dict: 수집된 기본 정보 (tags는 _step_tags에서 태그명으로 채워짐)
        """
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()

        # 차량별 분석 데이터 수집
        vehicle_analysis = await self.vehicle_analyzer.get_vehicle_analysis(branch_id, start_date, end_date)

        # 차량별 태그 raw 데이터 (VehicleRankItem 생성용, 기간 필터 적용)
        vehicle_tags_raw = await self.vehicle_analyzer.get_vehicle_tags_raw(branch_id)

        return {
            "branch_id": branch_id,
            "branch_name": summary_data.get("branch_name", f"지점 {branch_id}"),
            "affiliate_name": summary_data.get("affiliate_name", ""),
            "total_reviews": summary_data.get("review_count", 0),
            "tags": [],
            "vehicle_analysis": [v.model_dump() for v in vehicle_analysis],
            "vehicle_tags_raw": vehicle_tags_raw,
        }

    async def _step_tags(self, branch_id: int) -> dict:
        """Step 2: 지점별 태그 감정 데이터 (tag_calculator 위임)"""
        if self.tag_calculator:
            return await self.tag_calculator.compute(branch_id)
        # fallback: tag_calculator 미주입 시 직접 수행
        from services.tag_stats_calculator import TagStatsCalculator
        calc = TagStatsCalculator(self.branch_tag_repo)
        return await calc.compute(branch_id)

    async def _step_ai(self, data: dict) -> dict:
        """Step 3: AI 분석 (ai_generator 위임)"""
        if self.ai_generator:
            return await self.ai_generator.generate_all(data)
        # fallback: ai_generator 미주입 시 직접 수행
        from services.report_ai_generator import ReportAIGenerator
        gen = ReportAIGenerator(self.summary_repo, self.review_repo)
        return await gen.generate_all(data)

    async def _step_build(
        self,
        collected: dict,
        tags: dict,
        ai: dict,
        start_date: datetime,
        end_date: datetime,
    ) -> ReportData:
        """
        Step 4: 리포트 조립 및 저장

        Args:
            collected: Step 1에서 수집된 기본 정보
            tags: Step 2에서 조회된 태그 데이터
            ai: Step 3에서 생성된 AI 분석 결과
            start_date: 시작일
            end_date: 종료일

        Returns:
            ReportData: 최종 리포트
        """
        # 차량 순위 생성
        vehicle_tags_raw = collected.get("vehicle_tags_raw", {})
        vehicle_analysis_list = collected.get("vehicle_analysis", [])
        top_liked, top_disliked = self.vehicle_analyzer.build_vehicle_rankings(
            vehicle_tags_raw, vehicle_analysis_list
        )

        report = ReportData(
            branch_id=collected["branch_id"],
            branch_name=collected["branch_name"],
            affiliate_name=collected["affiliate_name"],
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            total_reviews=collected["total_reviews"],
            top_tags=collected["tags"],
            period_summary=ai["period_summary"],
            strengths=tags.get("strengths", []),
            improvements=tags.get("improvements", []),
            strengths_detail=[
                StrengthItem(**d) for d in tags.get("strengths_detail", [])
            ],
            improvements_detail=[
                StrengthItem(**d) for d in tags.get("improvements_detail", [])
            ],
            top_tags_detail=[
                TopTagItem(**d) for d in tags.get("top_tags_detail", [])
            ],
            vehicle_analysis=[VehicleAnalysis(**v) for v in vehicle_analysis_list],
            affiliate_evaluation=AffiliateEvaluation(
                top_positive=tags.get("top_positive_tags", []),
                top_negative=tags.get("top_negative_tags", []),
                ai_text=ai.get("affiliate_ai_text", ""),
            ),
            vehicle_evaluation=VehicleEvaluation(
                top_liked=top_liked,
                top_disliked=top_disliked,
                ai_text=ai.get("vehicle_ai_text", ""),
            ),
            generated_at=to_kst(utc_now()).strftime("%Y-%m-%d %H:%M"),
        )

        # DB 저장
        if self.report_repo:
            try:
                await self.report_repo.save(
                    branch_id=collected["branch_id"],
                    branch_name=collected["branch_name"],
                    affiliate_name=collected["affiliate_name"],
                    period_start=start_date,
                    period_end=end_date,
                    total_reviews=collected["total_reviews"],
                    report_data=report.model_dump(),
                )
            except Exception as e:
                logger.warning(f"리포트 저장 실패 (생성은 성공): {e}")

        return report

    async def generate_report_with_progress(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
        progress_callback: Callable[[int], Awaitable[None]] | None = None,
    ) -> ReportData:
        """
        리팩토링된 리포트 생성 (단계별 함수 호출)

        각 단계가 별도 함수로 분리되어 단계 완료 시 로컬 변수가
        가비지 컬렉션 대상이 됨 → OOM 방지

        Args:
            branch_id: 지점 ID
            start_date: 분석 시작일
            end_date: 분석 종료일
            progress_callback: 진행률 업데이트 콜백 (0-100)

        Returns:
            ReportData: 리포트 데이터
        """

        async def update_progress(value: int) -> None:
            if progress_callback:
                await progress_callback(value)

        # Step 1: 데이터 수집 (10-20%)
        await update_progress(10)
        collected = await self._step_collect(branch_id, start_date, end_date)
        await update_progress(20)

        # 리뷰가 없는 경우 빈 리포트 반환
        if collected["total_reviews"] == 0:
            await update_progress(100)
            return ReportData(
                branch_id=branch_id,
                branch_name=collected["branch_name"],
                affiliate_name=collected["affiliate_name"],
                period_start=start_date.strftime("%Y-%m-%d"),
                period_end=end_date.strftime("%Y-%m-%d"),
                total_reviews=0,
                generated_at=to_kst(utc_now()).strftime("%Y-%m-%d %H:%M"),
            )

        # 기간별 실제 리뷰 수 조회 (all-time count 대신)
        if self.review_repo:
            try:
                period_count = await self.review_repo.count_by_branch(
                    branch_id=branch_id,
                    review_date_from=start_date,
                    review_date_to=end_date,
                )
                collected["total_reviews"] = period_count
            except Exception as e:
                logger.warning(f"기간별 리뷰 수 조회 실패: {e}")

        # Step 2: 태그 분석 (20-40%)
        await update_progress(20)
        tags = await self._step_tags(branch_id)
        await update_progress(40)

        # 태그 데이터가 있으면 태그명으로 tags 대체 (과거 NLP 키워드 대신 최신 태그 사용)
        if tags.get("tag_sentiments"):
            collected["tags"] = [
                t["name"] for t in tags["tag_sentiments"] if t.get("name")
            ]

        # 차량 순위 데이터 생성 (ai_data에 전달)
        vehicle_tags_raw = collected.get("vehicle_tags_raw", {})
        top_liked, top_disliked = self.vehicle_analyzer.build_vehicle_rankings(
            vehicle_tags_raw, collected.get("vehicle_analysis", [])
        )

        # Step 3: AI 분석 ×2 병렬 (40-85%)
        await update_progress(40)
        ai_data = {
            **collected,
            **tags,
            "start_date": start_date,
            "end_date": end_date,
            "top_liked_vehicles": [v.model_dump() for v in top_liked],
            "top_disliked_vehicles": [v.model_dump() for v in top_disliked],
        }
        ai = await self._step_ai(ai_data)
        await update_progress(85)

        # Step 4: 리포트 조립 및 저장 (85-100%)
        await update_progress(85)
        report = await self._step_build(collected, tags, ai, start_date, end_date)
        await update_progress(100)

        return report

    async def generate_report(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> ReportData:
        """
        AI 리포트 생성

        Args:
            branch_id: 지점 ID
            start_date: 분석 시작일
            end_date: 분석 종료일

        Returns:
            ReportData: 리포트 데이터
        """
        # 진행률 콜백 없이 generate_report_with_progress 호출
        return await self.generate_report_with_progress(
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
            progress_callback=None,
        )

    async def delete_report(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> bool:
        """
        리포트 삭제

        Args:
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일

        Returns:
            삭제 성공 여부
        """
        if not self.report_repo:
            raise ValueError("리포트 repository가 초기화되지 않았습니다.")

        return await self.report_repo.delete_by_branch_and_period(
            branch_id, start_date, end_date
        )
