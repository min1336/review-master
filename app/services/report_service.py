"""
AI 리포트 서비스

지점별 맞춤형 컨설팅 리포트를 생성합니다.
- 기간별 요약 분석
- 차량별 평가 분석 (구현 예정)
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from core.timezone import to_kst, utc_now
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from repository.branch_tag_repository import BranchTagRepository
    from repository.report_repository import ReportRepository
    from repository.review_repository import BranchReviewRepository
    from repository.sentiment_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository
    from infrastructure.pdf.generator import PDFGenerator

from pydantic import BaseModel, model_validator


class EvaluationAxis(BaseModel):
    """평가 축 (친절도, 가성비 등)"""
    name: str
    positive_ratio: int = 0      # 0-100
    total_count: int = 0


class TagRankItem(BaseModel):
    """태그 순위 항목"""
    tag_name: str
    category_name: str
    count: int = 0               # 긍정 or 부정 건수
    ratio: int = 0               # 해당 감정 비율 %


class VehicleRankItem(BaseModel):
    """차량 순위 항목"""
    model: str
    count: int = 0               # 총 리뷰 건수
    ratio: int = 0               # 호평 or 불만 비율
    tags: list[str] = []         # ["냄새(85%)", "청결(72%)"] 최대 3개


class AffiliateEvaluation(BaseModel):
    """업체 평가 섹션"""
    axes: list[EvaluationAxis] = []
    top_positive: list[TagRankItem] = []   # Top 5 긍정 태그
    top_negative: list[TagRankItem] = []   # Top 5 부정 태그
    ai_text: str = ""                       # AI 평가 텍스트 (150-250자)


class VehicleEvaluation(BaseModel):
    """차량 평가 섹션"""
    axes: list[EvaluationAxis] = []
    top_liked: list[VehicleRankItem] = []   # 호평 Top 5 차량
    top_disliked: list[VehicleRankItem] = [] # 불만 Top 5 차량
    ai_text: str = ""                        # AI 평가 텍스트 (150-250자)


class VehicleAnalysis(BaseModel):
    """차량별 분석"""
    model: str
    count: int = 0
    avg_sentiment: float = 0.0
    top_praise: str = ""
    top_issue: str = ""
    like_ratio: int = 0  # 호평 비율 (0-100)
    dislike_ratio: int = 0  # 불평 비율 (0-100)


class StrengthItem(BaseModel):
    """현상유지/보완필요 구조화 항목"""
    category_name: str
    ratio: int = 0  # 긍정률 or 부정률

class TopTagItem(BaseModel):
    """Top 태그 구조화 항목"""
    name: str
    count: int = 0
    positive_ratio: int = 0


class ReportData(BaseModel):
    """리포트 전체 데이터"""
    branch_id: int
    branch_name: str
    affiliate_name: str
    period_start: str
    period_end: str
    total_reviews: int = 0
    top_tags: list[str] = []
    period_summary: str = ""
    strengths: list[str] = []       # 현상유지 (잘하고 있는 카테고리)
    improvements: list[str] = []    # 보완필요 (개선이 필요한 카테고리)
    strengths_detail: list[StrengthItem] = []       # 신규: 구조화된 현상유지
    improvements_detail: list[StrengthItem] = []    # 신규: 구조화된 보완필요
    top_tags_detail: list[TopTagItem] = []           # 신규: 구조화된 Top 태그
    vehicle_analysis: list[VehicleAnalysis] = []
    affiliate_evaluation: AffiliateEvaluation | None = None
    vehicle_evaluation: VehicleEvaluation | None = None
    generated_at: str = ""

    @model_validator(mode="before")
    @classmethod
    def _migrate_keywords(cls, data):
        """저장된 리포트의 top_keywords → top_tags 하위호환"""
        if isinstance(data, dict) and "top_keywords" in data and "top_tags" not in data:
            data["top_tags"] = data.pop("top_keywords")
        return data


# 축 매핑 상수: 7개 카테고리 → 5개 평가 축
AFFILIATE_AXES = {
    "친절도": ["직원이 친절함", "사고 처리를 잘해줌"],
    "가성비": ["주유비 부담 없음", "가격이 저렴함"],
    "배차": ["배달 서비스가 우수함"],
}
VEHICLE_AXES = {
    "청결도": ["차량이 청결함"],
    "외관/옵션": ["차량외관이 좋음"],
}
AFFILIATE_CATEGORIES = {c for cats in AFFILIATE_AXES.values() for c in cats}
VEHICLE_CATEGORIES = {c for cats in VEHICLE_AXES.values() for c in cats}

REVIEW_CHANGE_THRESHOLD = 30  # 캐싱 무효화 임계값 (CLT 기반) — get_review_count_summary() 전용

# 태그 분포 기반 캐시 무효화
CACHE_MIN_NEW_REVIEWS = 5             # 패스트 패스 최소 기준 (노이즈 방지)
CACHE_TAG_COUNT_RATIO = 0.15          # 태그 언급 수 15% 이상 변화 시 무효화
CACHE_SENTIMENT_DRIFT = 8.0           # 긍정률 8%p 이상 변화 시 무효화


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
    ) -> None:
        self.summary_repo = summary_repo
        self.review_repo = review_repo
        self.branch_tag_repo = branch_tag_repo
        self.report_repo = report_repo
        self.sentiment_repo = sentiment_repo
        self._pdf_generator = pdf_generator

    # ================================================================
    # PDF 생성 (Infrastructure 위임)
    # ================================================================

    async def generate_pdf(self, report: ReportData) -> bytes:
        """PDF 바이트 생성 (H-1: Service 레이어에서 Infrastructure 호출, H-2: 이벤트 루프 블로킹 방지)"""
        import asyncio

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
        import asyncio

        from dateutil.relativedelta import relativedelta
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
        """
        저장된 리포트 조회

        Args:
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일

        Returns:
            저장된 리포트 또는 None
        """
        if not self.report_repo:
            return None

        import json

        saved = await self.report_repo.get_by_branch_and_period(
            branch_id, start_date, end_date
        )

        if not saved:
            return None

        # JSON 파싱
        report_data = saved.get("report_data")
        if isinstance(report_data, str):
            report_data = json.loads(report_data)

        return ReportData(**report_data)

    async def get_report_list(self, branch_id: int, limit: int = 10) -> list[dict]:
        """
        지점의 리포트 목록 조회

        Args:
            branch_id: 지점 ID
            limit: 조회 개수

        Returns:
            리포트 목록 (메타데이터만)
        """
        if not self.report_repo:
            return []

        return await self.report_repo.get_all_by_branch(branch_id, limit)

    @staticmethod
    def _extract_saved_tag_stats(saved_report: ReportData) -> tuple[int, float] | None:
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

    async def _check_cache_invalidation(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
        saved_report: ReportData,
    ) -> bool:
        """
        True → 캐시 무효화 (재생성), False → 캐시 유효

        Step 1 (fast path): 리뷰 수 변화 없으면 즉시 False 반환
        Step 2: 태그 분포 비교
          - 신호 A: 태그 총 언급 수 변화 >= 15%
          - 신호 B: 긍정률 변화 >= 8%p
          → OR 조합
        """
        # Step 1: Fast path — 리뷰 변화가 아예 없으면 태그 조회 생략
        current_review_count = await self.review_repo.count_by_branch(
            branch_id=branch_id,
            review_date_from=start_date,
            review_date_to=end_date,
        )
        new_reviews = current_review_count - saved_report.total_reviews

        if new_reviews < CACHE_MIN_NEW_REVIEWS:
            return False  # 리뷰 변화 없음 → 캐시 유효

        # Step 2: 저장된 태그 기준값 추출
        saved_stats = self._extract_saved_tag_stats(saved_report)
        if saved_stats is None:
            # top_tags_detail 없는 레거시 리포트 → 기존 volume 방식 fallback
            return new_reviews >= REVIEW_CHANGE_THRESHOLD

        saved_total, saved_pos_ratio = saved_stats

        # Step 3: 현재 태그 분포 조회 (_step_tags와 동일한 소스)
        current_tags = await self.branch_tag_repo.get_by_branch(
            branch_id, period_type="all", limit=100
        )
        if not current_tags:
            return False  # 태그 데이터 없음 → 캐시 유효 (안전 방향)

        # 현재 태그 집계 계산
        current_total_pos = sum(bt.positive_count or 0 for bt in current_tags)
        current_total_neg = sum(bt.negative_count or 0 for bt in current_tags)
        current_total = current_total_pos + current_total_neg

        if current_total == 0:
            return False

        current_pos_ratio = (current_total_pos / current_total) * 100.0

        # 신호 A: 태그 총 언급 수 변화 비율
        tag_count_ratio = abs(current_total - saved_total) / max(saved_total, 1)
        signal_a = tag_count_ratio >= CACHE_TAG_COUNT_RATIO

        # 신호 B: 긍정률 변화
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
        if saved_report and self.review_repo:
            try:
                should_invalidate = await self._check_cache_invalidation(
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
        vehicle_analysis = await self._get_vehicle_analysis(branch_id, start_date, end_date)

        # 차량별 태그 raw 데이터 (VehicleRankItem 생성용, 기간 필터 적용)
        vehicle_tags_raw = await self._get_vehicle_tags_raw(branch_id)

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
        """
        Step 2: 지점별 태그 감정 데이터 조회 (오케스트레이션)

        branch_tags 테이블에서 전체 태그를 한 번에 조회하고,
        서브 메서드로 위임하여 감정 비율, 축별 집계, Top 5 태그를 산출합니다.
        """
        try:
            all_tags = await self.branch_tag_repo.get_by_branch(
                branch_id, period_type="all", limit=100
            )
        except Exception as e:
            logging.warning(f"태그 조회 실패 (branch_id={branch_id}): {e}")
            return {}

        if not all_tags:
            return {}

        # Step 2-1: 태그→감정통계+카테고리통계+태그상세
        tag_sentiments, sentiment_stats, category_stats, tag_details = (
            self._compute_category_stats(all_tags)
        )
        if not tag_sentiments:
            return {}

        # Step 2-2: 현상유지/보완필요
        strengths, improvements, strengths_detail, improvements_detail = (
            self._compute_strengths_improvements(category_stats)
        )

        # Step 2-3: 축별 감정 집계
        affiliate_axes = self._build_axes(AFFILIATE_AXES, category_stats)
        vehicle_axes = self._build_axes(VEHICLE_AXES, category_stats)

        # Step 2-4: Top 5 긍정/부정 태그
        top_positive, top_negative, top_tags_detail = (
            self._compute_top_tags(tag_details)
        )

        return {
            "tag_sentiments": tag_sentiments,
            "sentiment_stats": sentiment_stats,
            "strengths": strengths,
            "improvements": improvements,
            "strengths_detail": strengths_detail,
            "improvements_detail": improvements_detail,
            "affiliate_axes": affiliate_axes,
            "vehicle_axes": vehicle_axes,
            "top_positive_tags": top_positive,
            "top_negative_tags": top_negative,
            "top_tags_detail": top_tags_detail,
            "tag_by_category": category_stats,
        }

    @staticmethod
    def _compute_category_stats(
        all_tags: list,
    ) -> tuple[list[dict], dict, dict[str, dict], list[dict]]:
        """태그 → 감정통계 + 카테고리통계 + 태그상세 변환"""
        tag_sentiments: list[dict] = []
        total_pos = 0
        total_neg = 0
        category_stats: dict[str, dict] = {}
        tag_details: list[dict] = []

        for bt in all_tags:
            try:
                tag_info = bt.model_dump().get("tags") or {}
            except Exception:
                tag_info = {}
            name = tag_info.get("name", "")
            if not name:
                continue

            pos = bt.positive_count or 0
            neg = bt.negative_count or 0
            total = pos + neg

            tag_sentiments.append({
                "name": name,
                "positive": pos,
                "negative": neg,
                "neutral": 0,
                "total": total,
            })
            total_pos += pos
            total_neg += neg

            cat_info = tag_info.get("categories") or {}
            cat_name = cat_info.get("name", "")

            tag_details.append({
                "tag_name": name,
                "category_name": cat_name,
                "positive": pos,
                "negative": neg,
                "total": total,
            })

            if cat_name and total > 0:
                if cat_name not in category_stats:
                    category_stats[cat_name] = {"positive": 0, "negative": 0, "total": 0}
                category_stats[cat_name]["positive"] += pos
                category_stats[cat_name]["negative"] += neg
                category_stats[cat_name]["total"] += total

        total_all = total_pos + total_neg
        sentiment_stats = {
            "positive": total_pos,
            "negative": total_neg,
            "neutral": 0,
            "total": total_all,
        }

        return tag_sentiments, sentiment_stats, category_stats, tag_details

    @staticmethod
    def _compute_strengths_improvements(
        category_stats: dict[str, dict],
    ) -> tuple[list[str], list[str], list[dict], list[dict]]:
        """현상유지/보완필요 산출 (기존 list[str] + 신규 detail)"""
        strengths: list[str] = []
        strengths_detail: list[dict] = []
        sorted_positive = sorted(
            category_stats.items(),
            key=lambda x: x[1]["positive"] / x[1]["total"] if x[1]["total"] > 0 else 0,
            reverse=True,
        )
        for cat_name, stats in sorted_positive:
            if stats["total"] == 0:
                continue
            pos_ratio = round(stats["positive"] / stats["total"] * 100)
            if pos_ratio >= 60:
                strengths.append(f"{cat_name}({pos_ratio}%)")
                strengths_detail.append({"category_name": cat_name, "ratio": pos_ratio})
            if len(strengths) >= 3:
                break

        improvements: list[str] = []
        improvements_detail: list[dict] = []
        sorted_negative = sorted(
            category_stats.items(),
            key=lambda x: x[1]["negative"] / x[1]["total"] if x[1]["total"] > 0 else 0,
            reverse=True,
        )
        for cat_name, stats in sorted_negative:
            if stats["total"] == 0:
                continue
            neg_ratio = round(stats["negative"] / stats["total"] * 100)
            if neg_ratio >= 20:
                improvements.append(f"{cat_name}({neg_ratio}%)")
                improvements_detail.append({"category_name": cat_name, "ratio": neg_ratio})
            if len(improvements) >= 3:
                break

        return strengths, improvements, strengths_detail, improvements_detail

    @staticmethod
    def _build_axes(
        axes_map: dict[str, list[str]],
        category_stats: dict[str, dict],
    ) -> list[EvaluationAxis]:
        """축별 감정 집계 (재사용 가능)"""
        result = []
        for axis_name, categories in axes_map.items():
            ax_pos = sum(category_stats.get(c, {}).get("positive", 0) for c in categories)
            ax_total = sum(category_stats.get(c, {}).get("total", 0) for c in categories)
            ratio = round(ax_pos / ax_total * 100) if ax_total > 0 else 0
            result.append(EvaluationAxis(name=axis_name, positive_ratio=ratio, total_count=ax_total))
        return result

    @staticmethod
    def _compute_top_tags(
        tag_details: list[dict],
    ) -> tuple[list[TagRankItem], list[TagRankItem], list[dict]]:
        """Top 5 긍정/부정 태그 + TopTagItem detail 산출"""
        affiliate_tags = [
            t for t in tag_details
            if t["category_name"] in AFFILIATE_CATEGORIES and t["total"] > 0
        ]

        top_positive_raw = sorted(affiliate_tags, key=lambda t: t["positive"], reverse=True)[:5]
        top_negative_raw = sorted(affiliate_tags, key=lambda t: t["negative"], reverse=True)[:5]
        top_negative_raw = [t for t in top_negative_raw if t["negative"] > 0]

        top_positive = [
            TagRankItem(
                tag_name=t["tag_name"],
                category_name=t["category_name"],
                count=t["positive"],
                ratio=round(t["positive"] / t["total"] * 100) if t["total"] > 0 else 0,
            )
            for t in top_positive_raw
        ]
        top_negative = [
            TagRankItem(
                tag_name=t["tag_name"],
                category_name=t["category_name"],
                count=t["negative"],
                ratio=round(t["negative"] / t["total"] * 100) if t["total"] > 0 else 0,
            )
            for t in top_negative_raw
        ]

        # 신규: TopTagItem detail (프론트/API 구조화 제공용)
        top_tags_detail = [
            {
                "name": t["tag_name"],
                "count": t["positive"],
                "positive_ratio": round(t["positive"] / t["total"] * 100) if t["total"] > 0 else 0,
            }
            for t in top_positive_raw
        ]

        return top_positive, top_negative, top_tags_detail

    async def _step_ai(self, data: dict) -> dict:
        """
        Step 3: AI 분석 (LLM 호출 3개 병렬)

        Args:
            data: 이전 단계에서 수집된 데이터

        Returns:
            dict: AI 분석 결과 (period_summary, affiliate_ai_text, vehicle_ai_text)
        """
        import asyncio

        # 대표 리뷰 수집 (리포트 모드일 때만, 기간 필터 적용)
        sample_reviews: list[str] = []
        if data.get("tag_sentiments") and self.review_repo:
            try:
                result = await self.review_repo.get_by_branch(
                    branch_id=data.get("branch_id"),
                    review_date_from=data.get("start_date"),
                    review_date_to=data.get("end_date"),
                    limit=10,
                )
                sample_reviews = [
                    r.get("content", "") for r in result.reviews if r.get("content")
                ]
            except Exception as e:
                logging.warning(f"대표 리뷰 조회 실패: {e}")

        # 차량 분석 요약 텍스트 생성
        vehicle_summary = None
        vehicle_analysis = data.get("vehicle_analysis", [])
        if vehicle_analysis:
            lines = []
            for v in vehicle_analysis[:5]:
                model = v.get("model", "")
                count = v.get("count", 0)
                praise = v.get("top_praise", "")
                issue = v.get("top_issue", "")
                like = v.get("like_ratio", 0)
                line = f"{model}({count}건, 호평 {like}%"
                if praise:
                    line += f", 강점: {praise}"
                if issue:
                    line += f", 개선: {issue}"
                line += ")"
                lines.append(line)
            vehicle_summary = ", ".join(lines)

        # 1. 기간 요약 생성
        summary_coro = self._generate_period_summary(
            branch_name=data["branch_name"],
            total_reviews=data["total_reviews"],
            top_tags=data["tags"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            branch_id=data.get("branch_id"),
            tag_sentiments=data.get("tag_sentiments"),
            sentiment_stats=data.get("sentiment_stats"),
            sample_reviews=sample_reviews,
            vehicle_summary=vehicle_summary,
        )

        # 2. 업체 평가 텍스트 (독립 LLM 호출)
        affiliate_coro = self._generate_affiliate_text(
            branch_name=data["branch_name"],
            affiliate_axes=data.get("affiliate_axes", []),
            top_positive_tags=data.get("top_positive_tags", []),
            top_negative_tags=data.get("top_negative_tags", []),
            sample_reviews=sample_reviews,
        )

        # 3. 차량 평가 텍스트 (독립 LLM 호출)
        vehicle_coro = self._generate_vehicle_text(
            branch_name=data["branch_name"],
            vehicle_axes=data.get("vehicle_axes", []),
            top_liked_vehicles=data.get("top_liked_vehicles", []),
            top_disliked_vehicles=data.get("top_disliked_vehicles", []),
            sample_reviews=sample_reviews,
        )

        # 3개 병렬 실행
        period_summary, affiliate_text, vehicle_text = await asyncio.gather(
            summary_coro, affiliate_coro, vehicle_coro
        )

        return {
            "period_summary": period_summary,
            "affiliate_ai_text": affiliate_text,
            "vehicle_ai_text": vehicle_text,
        }

    @staticmethod
    def _to_dicts(items: list) -> list[dict]:
        """Pydantic 모델 또는 dict 리스트를 dict 리스트로 변환"""
        return [
            it.model_dump() if hasattr(it, "model_dump") else it
            for it in items
        ]

    async def _generate_affiliate_text(
        self,
        branch_name: str,
        affiliate_axes: list,
        top_positive_tags: list,
        top_negative_tags: list,
        sample_reviews: list[str] | None = None,
    ) -> str:
        """업체 평가 AI 텍스트 생성 (독립 LLM 호출)"""
        if not affiliate_axes:
            return ""

        try:
            from infrastructure.llm import get_provider
            from infrastructure.llm.prompts import RichSummaryPromptBuilder
            from infrastructure.llm.validator import strip_markdown_formatting

            system_prompt, user_prompt = RichSummaryPromptBuilder.create_affiliate_evaluation_prompt(
                branch_name=branch_name,
                affiliate_axes=self._to_dicts(affiliate_axes),
                top_positive_tags=self._to_dicts(top_positive_tags),
                top_negative_tags=self._to_dicts(top_negative_tags),
                sample_reviews=sample_reviews,
            )

            llm_provider = get_provider()
            response = await llm_provider.async_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=300,
                temperature=0.7,
            )

            content = response.content if hasattr(response, "content") else str(response)
            return strip_markdown_formatting(content).strip()

        except Exception as e:
            logging.error(f"업체 평가 텍스트 생성 실패: {e}")
            return ""

    async def _generate_vehicle_text(
        self,
        branch_name: str,
        vehicle_axes: list,
        top_liked_vehicles: list,
        top_disliked_vehicles: list,
        sample_reviews: list[str] | None = None,
    ) -> str:
        """차량 평가 AI 텍스트 생성 (독립 LLM 호출)"""
        if not vehicle_axes:
            return ""

        try:
            from infrastructure.llm import get_provider
            from infrastructure.llm.prompts import RichSummaryPromptBuilder
            from infrastructure.llm.validator import strip_markdown_formatting

            system_prompt, user_prompt = RichSummaryPromptBuilder.create_vehicle_evaluation_prompt(
                branch_name=branch_name,
                vehicle_axes=self._to_dicts(vehicle_axes),
                top_liked_vehicles=self._to_dicts(top_liked_vehicles),
                top_disliked_vehicles=self._to_dicts(top_disliked_vehicles),
                sample_reviews=sample_reviews,
            )

            llm_provider = get_provider()
            response = await llm_provider.async_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=300,
                temperature=0.7,
            )

            content = response.content if hasattr(response, "content") else str(response)
            return strip_markdown_formatting(content).strip()

        except Exception as e:
            logging.error(f"차량 평가 텍스트 생성 실패: {e}")
            return ""

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
        top_liked, top_disliked = self._build_vehicle_rankings(
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
                axes=tags.get("affiliate_axes", []),
                top_positive=tags.get("top_positive_tags", []),
                top_negative=tags.get("top_negative_tags", []),
                ai_text=ai.get("affiliate_ai_text", ""),
            ),
            vehicle_evaluation=VehicleEvaluation(
                axes=tags.get("vehicle_axes", []),
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
                logging.warning(f"리포트 저장 실패 (생성은 성공): {e}")

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
                logging.warning(f"기간별 리뷰 수 조회 실패: {e}")

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
        top_liked, top_disliked = self._build_vehicle_rankings(
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

    async def _get_vehicle_analysis(
        self,
        branch_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[VehicleAnalysis]:
        """
        차량별 평가 분석 (car_model_tags 테이블 활용 또는 기간 필터링)

        Args:
            branch_id: 지점 ID
            start_date: 시작일 (기간 필터용, None이면 전체 기간)
            end_date: 종료일 (기간 필터용, None이면 전체 기간)

        Returns:
            list[VehicleAnalysis]: 차량별 분석 리스트
        """
        from repository.session import get_client

        client = await get_client()

        # 기간 필터가 있으면 branch_reviews에서 직접 집계
        if start_date and end_date:
            return await self._get_vehicle_analysis_from_reviews(
                client, branch_id, start_date, end_date
            )

        try:
            # car_model_tags 테이블에서 차량별 태그 데이터 조회 (tags 테이블 JOIN)
            result = await (
                client.table("car_model_tags")
                .select("car_model, tag_id, positive_count, negative_count, neutral_count, total_count, tags(name)")
                .eq("branch_id", branch_id)
                .execute()
            )
        except Exception as e:
            # car_model_tags 테이블이 없으면 빈 리스트 반환
            logging.warning(f"차량별 분석 조회 실패 (branch_id={branch_id}): {e}")
            return []

        if not result.data:
            return []

        # 차량별로 그룹화
        car_data: dict[str, dict] = {}

        for row in result.data:
            car_model = row.get("car_model", "기타")
            tag_info = row.get("tags") or {}
            tag_name = tag_info.get("name", "기타")

            positive = row.get("positive_count", 0)
            negative = row.get("negative_count", 0)
            neutral = row.get("neutral_count", 0)
            total = row.get("total_count", 0)

            if car_model not in car_data:
                car_data[car_model] = {
                    "total_count": 0,
                    "total_positive": 0,
                    "total_negative": 0,
                    "tags": {}
                }

            # 차량별 전체 카운트 누적
            car_data[car_model]["total_count"] += total
            car_data[car_model]["total_positive"] += positive
            car_data[car_model]["total_negative"] += negative

            # 태그별 데이터 저장
            car_data[car_model]["tags"][tag_name] = {
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
                "total": total
            }

        # VehicleAnalysis 객체 리스트 생성
        vehicle_list: list[VehicleAnalysis] = []

        for car_model, data in sorted(car_data.items(), key=lambda x: x[1]["total_count"], reverse=True):
            total = data["total_count"]
            if total == 0:
                continue

            total_positive = data["total_positive"]
            total_negative = data["total_negative"]

            # avg_sentiment: 0.0 ~ 1.0 범위로 정규화
            # 공식: (positive_ratio - negative_ratio + 1) / 2
            # 0.0 (모두 부정) ~ 0.5 (중립) ~ 1.0 (모두 긍정)
            if total > 0:
                positive_ratio = total_positive / total
                negative_ratio = total_negative / total
                avg_sentiment = (positive_ratio - negative_ratio + 1) / 2
            else:
                avg_sentiment = 0.5  # 중립

            # top_praise: positive_count가 가장 높은 태그 (비율 포함)
            top_praise_tag = ""
            max_positive = 0
            for tag_name, tag_stats in data["tags"].items():
                if tag_stats["positive"] > max_positive:
                    max_positive = tag_stats["positive"]
                    tag_total = tag_stats["total"]
                    ratio = int(round((tag_stats["positive"] / tag_total) * 100)) if tag_total > 0 else 0
                    top_praise_tag = f"{tag_name}({ratio}%)"

            # top_issue: negative_count가 가장 높은 태그 (비율 포함)
            top_issue_tag = ""
            max_negative = 0
            for tag_name, tag_stats in data["tags"].items():
                if tag_stats["negative"] > max_negative:
                    max_negative = tag_stats["negative"]
                    tag_total = tag_stats["total"]
                    ratio = int(round((tag_stats["negative"] / tag_total) * 100)) if tag_total > 0 else 0
                    top_issue_tag = f"{tag_name}({ratio}%)"

            # 호불호 비율 계산 (퍼센트)
            like_ratio = int(round((total_positive / total) * 100)) if total > 0 else 0
            dislike_ratio = int(round((total_negative / total) * 100)) if total > 0 else 0

            vehicle_list.append(VehicleAnalysis(
                model=car_model,
                count=total,
                avg_sentiment=round(avg_sentiment, 2),
                top_praise=top_praise_tag,
                top_issue=top_issue_tag,
                like_ratio=like_ratio,
                dislike_ratio=dislike_ratio
            ))

        return vehicle_list

    async def _get_vehicle_analysis_from_reviews(
        self,
        client,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> list[VehicleAnalysis]:
        """
        branch_reviews에서 기간 필터링된 차량별 분석 (car_model_tags 대체)

        Args:
            client: Supabase 클라이언트
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일

        Returns:
            list[VehicleAnalysis]: 차량별 분석 리스트
        """
        from datetime import timedelta

        try:
            next_day = end_date + timedelta(days=1)

            # Supabase 기본 행 제한(1000건) 대응: 페이지네이션
            all_rows: list[dict] = []
            batch_size = 1000
            offset = 0

            while True:
                result = await (
                    client.table("branch_reviews")
                    .select("car_model, sentiment")
                    .eq("branch_id", branch_id)
                    .gte("review_date", start_date.isoformat())
                    .lt("review_date", next_day.isoformat())
                    .range(offset, offset + batch_size - 1)
                    .execute()
                )
                if not result.data:
                    break
                all_rows.extend(result.data)
                if len(result.data) < batch_size:
                    break
                offset += batch_size

        except Exception as e:
            logging.warning(f"기간별 차량 분석 조회 실패 (branch_id={branch_id}): {e}")
            return []

        if not all_rows:
            return []

        # 차량별 그룹화
        car_data: dict[str, dict] = {}
        for row in all_rows:
            car_model = row.get("car_model") or "기타"
            sentiment = row.get("sentiment", "neutral")

            if car_model not in car_data:
                car_data[car_model] = {"total": 0, "positive": 0, "negative": 0}

            car_data[car_model]["total"] += 1
            if sentiment == "positive":
                car_data[car_model]["positive"] += 1
            elif sentiment == "negative":
                car_data[car_model]["negative"] += 1

        # car_model_tags에서 태그 정보 가져오기 (top_praise, top_issue용)
        tag_info = await self._get_vehicle_tag_info(client, branch_id)

        # VehicleAnalysis 생성
        vehicle_list: list[VehicleAnalysis] = []
        for car_model, data in sorted(car_data.items(), key=lambda x: x[1]["total"], reverse=True):
            total = data["total"]
            if total == 0:
                continue

            positive = data["positive"]
            negative = data["negative"]

            like_ratio = int(round((positive / total) * 100)) if total > 0 else 0
            dislike_ratio = int(round((negative / total) * 100)) if total > 0 else 0

            positive_ratio = positive / total
            negative_ratio = negative / total
            avg_sentiment = round((positive_ratio - negative_ratio + 1) / 2, 2)

            # 태그 정보 (all-time 기준, 기간별 태그 데이터 없음)
            tags = tag_info.get(car_model, {})
            top_praise = tags.get("top_praise", "")
            top_issue = tags.get("top_issue", "")

            vehicle_list.append(VehicleAnalysis(
                model=car_model,
                count=total,
                avg_sentiment=avg_sentiment,
                top_praise=top_praise,
                top_issue=top_issue,
                like_ratio=like_ratio,
                dislike_ratio=dislike_ratio,
            ))

        return vehicle_list

    async def _get_vehicle_tag_info(self, client, branch_id: int) -> dict[str, dict]:
        """
        car_model_tags에서 차량별 대표 태그 정보 조회 (기간 무관)

        top_praise, top_issue 필드에 사용할 태그명+비율을 반환합니다.
        car_model_tags는 전체 기간 집계만 있으므로 기간 필터는 적용하지 않습니다.

        Args:
            client: Supabase 클라이언트
            branch_id: 지점 ID

        Returns:
            dict: {car_model: {"top_praise": "태그명(비율%)", "top_issue": "태그명(비율%)"}}
        """
        try:
            result = await (
                client.table("car_model_tags")
                .select("car_model, positive_count, negative_count, total_count, tags(name)")
                .eq("branch_id", branch_id)
                .execute()
            )
        except Exception:
            return {}

        if not result.data:
            return {}

        # 차량별 태그 데이터 그룹화
        car_tags: dict[str, dict[str, dict]] = {}
        for row in result.data:
            car_model = row.get("car_model", "기타")
            tag_info = row.get("tags") or {}
            tag_name = tag_info.get("name", "기타")

            if car_model not in car_tags:
                car_tags[car_model] = {}

            car_tags[car_model][tag_name] = {
                "positive": row.get("positive_count", 0),
                "negative": row.get("negative_count", 0),
                "total": row.get("total_count", 0),
            }

        # 차량별 top_praise, top_issue 추출
        result_map: dict[str, dict] = {}
        for car_model, tags in car_tags.items():
            top_praise = ""
            max_positive = 0
            top_issue = ""
            max_negative = 0

            for tag_name, stats in tags.items():
                if stats["positive"] > max_positive:
                    max_positive = stats["positive"]
                    tag_total = stats["total"]
                    ratio = int(round((stats["positive"] / tag_total) * 100)) if tag_total > 0 else 0
                    top_praise = f"{tag_name}({ratio}%)"
                if stats["negative"] > max_negative:
                    max_negative = stats["negative"]
                    tag_total = stats["total"]
                    ratio = int(round((stats["negative"] / tag_total) * 100)) if tag_total > 0 else 0
                    top_issue = f"{tag_name}({ratio}%)"

            result_map[car_model] = {
                "top_praise": top_praise,
                "top_issue": top_issue,
            }

        return result_map

    async def _get_vehicle_tags_raw(
        self,
        branch_id: int,
    ) -> dict[str, dict]:
        """
        car_model_tags에서 차량별 태그 데이터 조회 (VehicleRankItem용)
        카테고리 정보를 포함하여 차량 카테고리 태그만 필터링합니다.

        Returns:
            dict: {car_model: {"total_positive": N, "total_negative": N, "total_count": N,
                   "tags": {tag_name: {"positive": N, "negative": N, "total": N, "category_name": str}}}}
        """
        from repository.session import get_client

        client = await get_client()
        try:
            query = (
                client.table("car_model_tags")
                .select("car_model, positive_count, negative_count, total_count, tags(name, categories(name))")
                .eq("branch_id", branch_id)
            )
            result = await query.execute()
        except Exception as e:
            logging.warning(f"차량 태그 raw 조회 실패 (branch_id={branch_id}): {e}")
            return {}

        if not result.data:
            return {}

        car_data: dict[str, dict] = {}
        for row in result.data:
            car_model = row.get("car_model", "기타")
            tag_info = row.get("tags") or {}
            tag_name = tag_info.get("name", "기타")
            cat_info = tag_info.get("categories") or {}
            cat_name = cat_info.get("name", "")
            positive = row.get("positive_count", 0)
            negative = row.get("negative_count", 0)
            total = row.get("total_count", 0)

            if car_model not in car_data:
                car_data[car_model] = {
                    "total_positive": 0, "total_negative": 0, "total_count": 0, "tags": {},
                }
            car_data[car_model]["total_positive"] += positive
            car_data[car_model]["total_negative"] += negative
            car_data[car_model]["total_count"] += total
            car_data[car_model]["tags"][tag_name] = {
                "positive": positive, "negative": negative, "total": total,
                "category_name": cat_name,
            }

        return car_data

    def _build_vehicle_rankings(
        self,
        vehicle_tags_raw: dict[str, dict],
        vehicle_analysis: list[dict],
    ) -> tuple[list[VehicleRankItem], list[VehicleRankItem]]:
        """
        차량별 호평/불만 Top 5 + 태그 리스트 생성

        vehicle_analysis (기간 필터링 된 데이터)의 count/like_ratio를 기본으로,
        vehicle_tags_raw (all-time car_model_tags)의 태그를 보강하여 VehicleRankItem 생성.

        Returns:
            (top_liked, top_disliked)
        """
        # 기간별 차량 데이터를 dict으로 변환
        va_map = {v.get("model", ""): v for v in vehicle_analysis}

        items: list[dict] = []
        for car_model, raw in vehicle_tags_raw.items():
            va = va_map.get(car_model, {})
            count = va.get("count", 0) or raw.get("total_count", 0)
            like_ratio = va.get("like_ratio", 0)
            dislike_ratio = va.get("dislike_ratio", 0)

            # 기간별 데이터가 없으면 raw에서 계산
            if not va and raw["total_count"] > 0:
                like_ratio = round(raw["total_positive"] / raw["total_count"] * 100)
                dislike_ratio = round(raw["total_negative"] / raw["total_count"] * 100)

            # 상위 3개 태그 (차량 카테고리만, 긍정/부정 비율 포함)
            tag_entries = sorted(
                [(name, ts) for name, ts in raw.get("tags", {}).items()
                 if ts.get("category_name", "") in VEHICLE_CATEGORIES],
                key=lambda x: x[1]["total"], reverse=True,
            )
            tag_labels: list[str] = []
            for tag_name, ts in tag_entries[:3]:
                if ts["total"] > 0:
                    pos_r = round(ts["positive"] / ts["total"] * 100)
                    tag_labels.append(f"{tag_name}({pos_r}%)")

            items.append({
                "model": car_model,
                "count": count,
                "like_ratio": like_ratio,
                "dislike_ratio": dislike_ratio,
                "tags": tag_labels,
            })

        # 호평 Top 5 (like_ratio 내림차순)
        sorted_liked = sorted(items, key=lambda x: (x["like_ratio"], x["count"]), reverse=True)
        top_liked = [
            VehicleRankItem(model=it["model"], count=it["count"], ratio=it["like_ratio"], tags=it["tags"])
            for it in sorted_liked[:5]
        ]

        # 불만 Top 5 (dislike_ratio 내림차순, 0% 제외)
        sorted_disliked = sorted(
            [it for it in items if it["dislike_ratio"] > 0],
            key=lambda x: (x["dislike_ratio"], x["count"]),
            reverse=True,
        )
        top_disliked = [
            VehicleRankItem(model=it["model"], count=it["count"], ratio=it["dislike_ratio"], tags=it["tags"])
            for it in sorted_disliked[:5]
        ]

        return top_liked, top_disliked

    async def _generate_period_summary(
        self,
        branch_name: str,
        total_reviews: int,
        top_tags: list[str],
        start_date: datetime,
        end_date: datetime,
        branch_id: int | None = None,
        tag_sentiments: list[dict] | None = None,
        sentiment_stats: dict | None = None,
        sample_reviews: list[str] | None = None,
        vehicle_summary: str | None = None,
    ) -> str:
        """
        기간 요약 생성 (DB 저장된 요약 우선 사용)

        토큰 절약을 위해 branch_summaries에 저장된 요약을 먼저 확인하고,
        없는 경우에만 LLM을 호출합니다.

        Args:
            branch_name: 지점명
            total_reviews: 총 리뷰 수
            top_tags: 태그 목록
            start_date: 시작일
            end_date: 종료일
            branch_id: 지점 ID (DB 조회용)
            tag_sentiments: 태그별 감정 데이터 (Step 2에서 조회)
            sentiment_stats: 전체 감정 통계 (Step 2에서 조회)
            sample_reviews: 대표 리뷰 리스트 (리포트 모드용)
            vehicle_summary: 차량 분석 요약 텍스트 (리포트 모드용)

        Returns:
            str: 기간 요약 텍스트
        """
        # 1. DB에 저장된 요약 확인 (토큰 절약)
        # 단, 태그 데이터가 있으면 리포트 모드 → DB 유저용 요약(긍정만) 건너뛰고
        # LLM으로 긍정+부정 포함한 정확한 분석 생성
        if not tag_sentiments and branch_id and self.summary_repo:
            try:
                summary = await self.summary_repo.get_by_branch_id(branch_id)
                if summary:
                    summary_data = summary.model_dump()
                    for field in ["summary_1m", "summary_3m", "summary_6m", "summary_1y", "summary_all"]:
                        saved_summary = summary_data.get(field)
                        if saved_summary:
                            logging.info(
                                f"DB 저장 요약 사용: branch_id={branch_id}, field={field}"
                            )
                            return saved_summary
            except Exception as e:
                logging.warning(f"DB 요약 조회 실패 (branch_id={branch_id}): {e}")

        # 2. DB에 없으면 LLM 호출
        from infrastructure.llm import get_provider
        from infrastructure.llm.prompts import RichSummaryPromptBuilder

        # 실제 태그 데이터가 있으면 사용, 없으면 태그 기반 폴백
        if tag_sentiments:
            tag_sentiments_for_prompt = tag_sentiments
        else:
            tag_sentiments_for_prompt = [
                {"name": t, "positive": 1, "negative": 0, "neutral": 0, "total": 1}
                for t in top_tags[:7]
            ]

        if sentiment_stats:
            sentiment_stats_for_prompt = sentiment_stats
        else:
            sentiment_stats_for_prompt = {
                "positive": total_reviews,
                "negative": 0,
                "neutral": 0,
                "total": total_reviews,
            }

        start_date_str = start_date.strftime("%Y년 %m월 %d일")
        end_date_str = end_date.strftime("%Y년 %m월 %d일")

        # 리포트 모드(태그 데이터 있음) → 구조화된 리포트 프롬프트
        # 일반 모드 → 기존 단문 요약 프롬프트
        if tag_sentiments:
            system_prompt, user_prompt = RichSummaryPromptBuilder.create_report_prompt(
                branch_name=branch_name,
                start_date=start_date_str,
                end_date=end_date_str,
                total_reviews=total_reviews,
                tag_sentiments=tag_sentiments_for_prompt,
                sentiment_stats=sentiment_stats_for_prompt,
                sample_reviews=sample_reviews or [],
                vehicle_summary=vehicle_summary,
            )
            max_tokens = 600
        else:
            system_prompt, user_prompt = RichSummaryPromptBuilder.create_prompt(
                branch_name=branch_name,
                start_date=start_date_str,
                end_date=end_date_str,
                total_reviews=total_reviews,
                tag_sentiments=tag_sentiments_for_prompt,
                sentiment_stats=sentiment_stats_for_prompt,
                sample_reviews=[],
            )
            max_tokens = 200

        try:
            llm_provider = get_provider()
            response = await llm_provider.async_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=0.7,
            )

            content = response.content if hasattr(response, "content") else str(response)

            # LLM 응답 품질 검증 및 자동 정제
            from infrastructure.llm.validator import validate_summary, FORBIDDEN_WORDS, strip_markdown_formatting
            validation_mode = "report" if tag_sentiments else "summary"
            # 마크다운 서식 항상 제거 (검증 전에 먼저 정제)
            content = strip_markdown_formatting(content)

            is_valid, errors = validate_summary(content, mode=validation_mode)
            if not is_valid:
                logging.warning(
                    f"LLM 응답 검증 실패 (branch_id={branch_id}): {errors}"
                )
                # 금지어 자동 제거
                for word in FORBIDDEN_WORDS:
                    content = content.replace(word, "")
                # 이모지 자동 제거
                import re
                content = re.sub(
                    "["
                    "\U0001f600-\U0001f64f\U0001f300-\U0001f5ff"
                    "\U0001f680-\U0001f6ff\U0001f900-\U0001f9ff"
                    "\U00002600-\U000026ff\U00002700-\U000027bf"
                    "]+", "", content
                )
                content = content.strip()

            return content
        except Exception as e:
            logging.error(f"기간 요약 생성 실패: {e}")

        # 기본 요약
        start_str = start_date.strftime('%Y년 %m월')
        end_str = end_date.strftime('%Y년 %m월')
        base = (
            f"{branch_name}의 {start_str}부터 {end_str}까지 "
            f"총 {total_reviews}건의 리뷰를 분석했습니다."
        )
        if top_tags:
            base += f" 주요 태그는 {', '.join(top_tags[:3])}입니다."
        return base

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
