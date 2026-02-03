"""
AI 리포트 서비스

지점별 맞춤형 컨설팅 리포트를 생성합니다.
- 기간별 요약 분석
- 차량별 평가 분석
- 장단점 분석
- 개선 액션 아이템
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Awaitable, Callable

from pydantic import BaseModel


class PeriodTrend(BaseModel):
    """기간별 감정 추이"""
    period: str
    positive: int = 0
    neutral: int = 0
    negative: int = 0


class VehicleAnalysis(BaseModel):
    """차량별 분석"""
    model: str
    count: int = 0
    avg_sentiment: float = 0.0
    top_praise: str = ""
    top_issue: str = ""


class StrengthWeakness(BaseModel):
    """강점/약점 항목"""
    tag: str
    ratio: float = 0.0
    sample: str = ""


class ActionItem(BaseModel):
    """개선 액션 아이템"""
    priority: str
    category: str
    issue: str
    action: str


class ReportData(BaseModel):
    """리포트 전체 데이터"""
    branch_id: int
    branch_name: str
    affiliate_name: str
    period_start: str
    period_end: str
    total_reviews: int = 0
    sentiment_trend: list[PeriodTrend] = []
    top_keywords: list[str] = []
    period_summary: str = ""
    vehicle_analysis: list[VehicleAnalysis] = []
    strengths: list[StrengthWeakness] = []
    weaknesses: list[StrengthWeakness] = []
    action_items: list[ActionItem] = []
    generated_at: str = ""


class ReportService:
    """AI 리포트 비즈니스 로직"""

    def __init__(self, summary_repo, review_repo, branch_tag_repo, report_repo=None):
        self.summary_repo = summary_repo
        self.review_repo = review_repo
        self.branch_tag_repo = branch_tag_repo
        self.report_repo = report_repo

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

    async def get_or_generate_report(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[ReportData, bool]:
        """
        저장된 리포트가 있으면 반환, 없으면 생성

        Args:
            branch_id: 지점 ID
            start_date: 시작일
            end_date: 종료일

        Returns:
            (리포트 데이터, 신규 생성 여부)
        """
        # 기존 리포트 확인
        saved_report = await self.get_saved_report(branch_id, start_date, end_date)
        if saved_report:
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

    async def generate_report_with_progress(
        self,
        branch_id: int,
        start_date: datetime,
        end_date: datetime,
        progress_callback: Callable[[int], Awaitable[None]] | None = None,
    ) -> ReportData:
        """
        진행률 콜백이 포함된 AI 리포트 생성 (비동기 작업용)

        Args:
            branch_id: 지점 ID
            start_date: 분석 시작일
            end_date: 분석 종료일
            progress_callback: 진행률 업데이트 콜백 (0-100)

        Returns:
            ReportData: 리포트 데이터
        """
        from domain.analysis import KeywordExtractor, RuleBasedABSA

        async def update_progress(value: int) -> None:
            if progress_callback:
                await progress_callback(value)

        # 1. 기본 정보 조회 (5%)
        await update_progress(5)
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()
        branch_name = summary_data.get("branch_name", f"지점 {branch_id}")
        affiliate_name = summary_data.get("affiliate_name", "")

        # 2. 기간 내 리뷰 조회 (15%)
        await update_progress(15)
        reviews_result = await self.review_repo.get_by_branch(
            branch_id=branch_id,
            review_date_from=start_date,
            review_date_to=end_date,
            limit=1000,
        )
        reviews_data = reviews_result.reviews
        total_reviews = reviews_result.total

        if not reviews_data:
            await update_progress(100)
            return ReportData(
                branch_id=branch_id,
                branch_name=branch_name,
                affiliate_name=affiliate_name,
                period_start=start_date.strftime("%Y-%m-%d"),
                period_end=end_date.strftime("%Y-%m-%d"),
                total_reviews=0,
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            )

        # 3. 키워드 추출 및 감정 분석 (60%)
        await update_progress(25)
        review_texts = [r.get("content", "") or "" for r in reviews_data]

        def analyze_reviews():
            extractor = KeywordExtractor()
            classifier = RuleBasedABSA()

            all_keywords = extractor.extract_batch(review_texts)
            tag_totals: dict[str, dict] = {}
            sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}

            for keywords, review_text, review in zip(
                all_keywords, review_texts, reviews_data, strict=False
            ):
                result = classifier.classify_review(review_text, keywords[:10])

                review_sentiment = review.get("sentiment", "neutral")
                sentiment_counts[review_sentiment] = (
                    sentiment_counts.get(review_sentiment, 0) + 1
                )

                for tag, sentiments in result.items():
                    pos = len(sentiments.get("positive", []))
                    neg = len(sentiments.get("negative", []))
                    neu = len(sentiments.get("neutral", []))

                    if tag not in tag_totals:
                        tag_totals[tag] = {
                            "positive": 0,
                            "negative": 0,
                            "neutral": 0,
                            "total": 0,
                            "positive_samples": [],
                            "negative_samples": [],
                        }
                    tag_totals[tag]["positive"] += pos
                    tag_totals[tag]["negative"] += neg
                    tag_totals[tag]["neutral"] += neu
                    tag_totals[tag]["total"] += pos + neg + neu

                    if pos > 0 and len(tag_totals[tag]["positive_samples"]) < 3:
                        tag_totals[tag]["positive_samples"].append(review_text[:100])
                    if neg > 0 and len(tag_totals[tag]["negative_samples"]) < 3:
                        tag_totals[tag]["negative_samples"].append(review_text[:100])

            keyword_freq: dict[str, int] = {}
            for keywords in all_keywords:
                for kw in keywords[:5]:
                    keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

            top_keywords = sorted(
                keyword_freq.items(), key=lambda x: x[1], reverse=True
            )[:10]

            return tag_totals, sentiment_counts, [kw for kw, _ in top_keywords]

        tag_totals, sentiment_counts, top_keywords = await asyncio.to_thread(
            analyze_reviews
        )
        await update_progress(60)

        # 4. 차량별 분석 (70%)
        vehicle_analysis = await self._analyze_vehicles(reviews_data, branch_id)
        await update_progress(70)

        # 5. 강점/약점 분석
        strengths, weaknesses = self._analyze_strengths_weaknesses(tag_totals)

        # 6. 기간별 추이 (월별 집계)
        sentiment_trend = self._calculate_sentiment_trend(reviews_data)
        await update_progress(75)

        # 7. AI 개선 액션 아이템 + 기간 요약 병렬 생성 (90%)
        action_items, period_summary = await asyncio.gather(
            self._generate_action_items(weaknesses, reviews_data, branch_name),
            self._generate_period_summary(
                branch_name,
                total_reviews,
                top_keywords,
                strengths,
                weaknesses,
                start_date,
                end_date,
            ),
        )
        await update_progress(90)

        report = ReportData(
            branch_id=branch_id,
            branch_name=branch_name,
            affiliate_name=affiliate_name,
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            total_reviews=total_reviews,
            sentiment_trend=sentiment_trend,
            top_keywords=top_keywords,
            period_summary=period_summary,
            vehicle_analysis=vehicle_analysis,
            strengths=strengths,
            weaknesses=weaknesses,
            action_items=action_items,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

        # DB에 리포트 저장 (95%)
        await update_progress(95)
        if self.report_repo:
            try:
                await self.report_repo.save(
                    branch_id=branch_id,
                    branch_name=branch_name,
                    affiliate_name=affiliate_name,
                    period_start=start_date,
                    period_end=end_date,
                    total_reviews=total_reviews,
                    report_data=report.model_dump(),
                )
            except Exception as e:
                import logging

                logging.warning(f"리포트 저장 실패 (생성은 성공): {e}")

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

    async def _analyze_vehicles(
        self, reviews_data: list[dict], branch_id: int
    ) -> list[VehicleAnalysis]:
        """차량별 분석"""
        from domain.analysis import KeywordExtractor

        vehicle_stats: dict[str, dict] = {}

        for review in reviews_data:
            car_model = review.get("car_model")
            if not car_model:
                continue

            if car_model not in vehicle_stats:
                vehicle_stats[car_model] = {
                    "count": 0,
                    "sentiment_sum": 0,
                    "positive_reviews": [],
                    "negative_reviews": [],
                }

            vehicle_stats[car_model]["count"] += 1

            sentiment = review.get("sentiment", "neutral")
            sentiment_score = {"positive": 1, "neutral": 0.5, "negative": 0}
            vehicle_stats[car_model]["sentiment_sum"] += sentiment_score.get(
                sentiment, 0.5
            )

            # 리뷰 전체 수집
            content = review.get("content", "")
            if sentiment == "positive" and content:
                vehicle_stats[car_model]["positive_reviews"].append(content)
            elif sentiment == "negative" and content:
                vehicle_stats[car_model]["negative_reviews"].append(content)

        # Kiwi 키워드 추출기 초기화
        extractor = KeywordExtractor()

        result = []
        for model, stats in sorted(
            vehicle_stats.items(), key=lambda x: x[1]["count"], reverse=True
        )[:10]:
            avg_sentiment = (
                stats["sentiment_sum"] / stats["count"] if stats["count"] > 0 else 0.5
            )

            # Kiwi로 의미있는 키워드 추출
            top_praise = self._extract_meaningful_keyword(
                stats["positive_reviews"], extractor, is_positive=True
            )
            top_issue = self._extract_meaningful_keyword(
                stats["negative_reviews"], extractor, is_positive=False
            )

            result.append(
                VehicleAnalysis(
                    model=model,
                    count=stats["count"],
                    avg_sentiment=round(avg_sentiment, 2),
                    top_praise=top_praise,
                    top_issue=top_issue,
                )
            )

        return result

    def _extract_meaningful_keyword(
        self,
        reviews: list[str],
        extractor,
        is_positive: bool = True,
    ) -> str:
        """리뷰 목록에서 의미있는 키워드 추출 (Kiwi 사용)"""
        if not reviews:
            return ""

        from domain.analysis.patterns import (
            NEGATIVE_KEYWORDS_SET,
            POSITIVE_KEYWORDS_SET,
        )

        # 긍정/부정 관련 의미있는 단어 패턴
        target_keywords = (
            POSITIVE_KEYWORDS_SET if is_positive else NEGATIVE_KEYWORDS_SET
        )



        # 키워드 빈도 집계
        keyword_counts: dict[str, int] = {}

        for review in reviews[:20]:  # 최대 20개 리뷰 분석
            # Kiwi로 키워드 추출
            try:
                keywords = extractor.extract(review)
                if not keywords:
                    continue
                for kw in keywords[:10]:
                    if not kw:  # None 또는 빈 문자열 건너뛰기
                        continue
                    # 의미있는 키워드인지 확인
                    for target in target_keywords:
                        if target in kw or kw in target:
                            keyword_counts[target] = keyword_counts.get(target, 0) + 1
                            break
                    else:
                        # 2글자 이상 명사/형용사만 수집
                        if len(kw) >= 2:
                            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
            except Exception:
                continue

        if not keyword_counts:
            return ""

        # 가장 빈도 높은 의미있는 키워드 반환
        # 우선순위: 미리 정의된 키워드 > 일반 키워드
        for kw in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True):
            if kw[0] in target_keywords:
                return kw[0]

        # 미리 정의된 키워드가 없으면 가장 빈도 높은 것 반환
        top_keyword = max(keyword_counts.items(), key=lambda x: x[1])[0]
        return top_keyword

    def _analyze_strengths_weaknesses(
        self, tag_totals: dict[str, dict]
    ) -> tuple[list[StrengthWeakness], list[StrengthWeakness]]:
        """강점/약점 분석"""
        strengths = []
        weaknesses = []

        for tag, counts in tag_totals.items():
            total = counts["total"]
            if total < 2:  # 최소 2개 이상 언급된 태그만 분석
                continue

            positive_ratio = counts["positive"] / total * 100 if total > 0 else 0
            negative_ratio = counts["negative"] / total * 100 if total > 0 else 0

            if positive_ratio >= 60:  # 60% 이상 긍정이면 강점
                sample = (
                    counts["positive_samples"][0]
                    if counts["positive_samples"]
                    else ""
                )
                strengths.append(
                    StrengthWeakness(
                        tag=tag,
                        ratio=round(positive_ratio, 1),
                        sample=sample,
                    )
                )
            elif negative_ratio >= 15:  # 15% 이상 부정이면 약점 (개선 필요)
                sample = (
                    counts["negative_samples"][0]
                    if counts["negative_samples"]
                    else ""
                )
                weaknesses.append(
                    StrengthWeakness(
                        tag=tag,
                        ratio=round(negative_ratio, 1),
                        sample=sample,
                    )
                )

        # 정렬
        strengths.sort(key=lambda x: x.ratio, reverse=True)
        weaknesses.sort(key=lambda x: x.ratio, reverse=True)

        return strengths[:5], weaknesses[:5]

    def _calculate_sentiment_trend(
        self, reviews_data: list[dict]
    ) -> list[PeriodTrend]:
        """월별 감정 추이 계산"""
        monthly_counts: dict[str, dict] = {}

        for review in reviews_data:
            review_date = review.get("review_date")
            if not review_date:
                continue

            # 날짜 파싱
            if isinstance(review_date, str):
                try:
                    dt = datetime.strptime(review_date[:10], "%Y-%m-%d")
                except ValueError:
                    continue
            elif isinstance(review_date, datetime):
                dt = review_date
            else:
                continue

            month_key = dt.strftime("%Y-%m")
            if month_key not in monthly_counts:
                monthly_counts[month_key] = {
                    "positive": 0,
                    "neutral": 0,
                    "negative": 0,
                }

            sentiment = review.get("sentiment", "neutral")
            if sentiment in monthly_counts[month_key]:
                monthly_counts[month_key][sentiment] += 1

        # 정렬된 결과 반환
        result = []
        for month in sorted(monthly_counts.keys()):
            counts = monthly_counts[month]
            result.append(
                PeriodTrend(
                    period=month,
                    positive=counts["positive"],
                    neutral=counts["neutral"],
                    negative=counts["negative"],
                )
            )

        return result[-12:]  # 최근 12개월만

    async def _generate_action_items(
        self,
        weaknesses: list[StrengthWeakness],
        reviews_data: list[dict],
        branch_name: str,
    ) -> list[ActionItem]:
        """AI로 개선 액션 아이템 생성"""
        from infrastructure.llm import get_provider

        # 부정 리뷰 수집
        negative_reviews = [
            r.get("content", "")[:200]
            for r in reviews_data
            if r.get("sentiment") == "negative"
        ][:10]

        # 부정 리뷰가 없으면 중립 리뷰 중 개선 키워드 포함된 것 수집
        if not negative_reviews:
            improve_keywords = ["아쉬운", "개선", "불편", "조금", "약간"]
            for r in reviews_data:
                content = r.get("content") or ""
                if content and any(kw in content for kw in improve_keywords):
                    negative_reviews.append(content[:200])
                if len(negative_reviews) >= 5:
                    break

        # 그래도 없으면 빈 결과 반환
        if not negative_reviews:
            return []

        # 프롬프트 구성
        if weaknesses:
            weakness_text = "\n".join(
                [f"- {w.tag}: 부정 비율 {w.ratio}%" for w in weaknesses[:3]]
            )
        else:
            weakness_text = "- 명확한 약점 태그 없음 (전반적으로 양호하나 리뷰 기반 개선점 분석 필요)"
        reviews_text = "\n".join([f"- {r}" for r in negative_reviews[:5]])

        system_prompt = """당신은 렌터카 업체 컨설턴트입니다.
부정적 리뷰를 분석하여 구체적이고 실행 가능한 개선 방안을 제시합니다.

출력 형식 (JSON 배열):
[
  {"priority": "높음|중간|낮음", "category": "태그명", "issue": "문제점 요약", "action": "구체적 개선 방안"}
]

주의사항:
- 최대 5개의 액션 아이템
- 구체적이고 실행 가능한 방안만 제시
- JSON 형식으로만 응답"""

        user_prompt = f"""지점: {branch_name}

주요 약점:
{weakness_text}

부정 리뷰 샘플:
{reviews_text}

위 내용을 분석하여 개선 액션 아이템을 JSON 배열로 작성해주세요."""

        try:
            llm_provider = get_provider()
            response = await asyncio.to_thread(
                llm_provider.generate,
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=500,
                temperature=0.5,
            )

            content = (
                response.content if hasattr(response, "content") else str(response)
            )

            # JSON 파싱
            import json

            # JSON 부분 추출
            start_idx = content.find("[")
            end_idx = content.rfind("]") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                items = json.loads(json_str)

                return [
                    ActionItem(
                        priority=item.get("priority", "중간"),
                        category=item.get("category", "기타"),
                        issue=item.get("issue", ""),
                        action=item.get("action", ""),
                    )
                    for item in items[:5]
                ]
        except Exception as e:
            import logging

            logging.error(f"액션 아이템 생성 실패: {e}")

        # 기본 액션 아이템 생성
        default_items = []
        for w in weaknesses[:3]:
            default_items.append(
                ActionItem(
                    priority="중간",
                    category=w.tag,
                    issue=f"{w.tag} 관련 부정 리뷰 {w.ratio}%",
                    action=f"{w.tag} 개선을 위한 점검 및 교육 필요",
                )
            )
        return default_items

    async def _generate_period_summary(
        self,
        branch_name: str,
        total_reviews: int,
        top_keywords: list[str],
        strengths: list[StrengthWeakness],
        weaknesses: list[StrengthWeakness],
        start_date: datetime,
        end_date: datetime,
    ) -> str:
        """기간 요약 생성"""
        from infrastructure.llm import get_provider

        strength_text = (
            ", ".join([s.tag for s in strengths[:3]]) if strengths else "없음"
        )
        weakness_text = (
            ", ".join([w.tag for w in weaknesses[:3]]) if weaknesses else "없음"
        )

        system_prompt = """당신은 렌터카 업체 분석 전문가입니다.
주어진 데이터를 바탕으로 간결한 기간 요약을 작성합니다.

출력 형식:
- 2~3문장의 자연스러운 문단
- 핵심 성과와 개선점을 균형있게 언급
- 마크다운, 이모지 사용 금지"""

        user_prompt = f"""지점: {branch_name}
분석 기간: {start_date.strftime("%Y-%m-%d")} ~ {end_date.strftime("%Y-%m-%d")}
총 리뷰 수: {total_reviews}건
핵심 키워드: {', '.join(top_keywords[:5])}
강점: {strength_text}
약점: {weakness_text}

위 데이터를 바탕으로 기간 요약을 작성해주세요."""

        try:
            llm_provider = get_provider()
            response = await asyncio.to_thread(
                llm_provider.generate,
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=200,
                temperature=0.7,
            )

            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            import logging

            logging.error(f"기간 요약 생성 실패: {e}")

        # 기본 요약
        start_str = start_date.strftime('%Y년 %m월')
        end_str = end_date.strftime('%Y년 %m월')
        keywords_str = ', '.join(top_keywords[:3])
        return (
            f"{branch_name}의 {start_str}부터 {end_str}까지 "
            f"총 {total_reviews}건의 리뷰를 분석했습니다. "
            f"주요 키워드는 {keywords_str}입니다."
        )
