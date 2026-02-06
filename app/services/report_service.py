"""
AI 리포트 서비스

지점별 맞춤형 컨설팅 리포트를 생성합니다.
- 기간별 요약 분석
- 차량별 평가 분석 (구현 예정)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable

from pydantic import BaseModel


class VehicleAnalysis(BaseModel):
    """차량별 분석"""
    model: str
    count: int = 0
    avg_sentiment: float = 0.0
    top_praise: str = ""
    top_issue: str = ""
    like_ratio: int = 0  # 호평 비율 (0-100)
    dislike_ratio: int = 0  # 불평 비율 (0-100)


class ReportData(BaseModel):
    """리포트 전체 데이터"""
    branch_id: int
    branch_name: str
    affiliate_name: str
    period_start: str
    period_end: str
    total_reviews: int = 0
    top_keywords: list[str] = []
    period_summary: str = ""
    vehicle_analysis: list[VehicleAnalysis] = []
    generated_at: str = ""


class ReportService:
    """AI 리포트 비즈니스 로직"""

    def __init__(self, summary_repo, review_repo, branch_tag_repo, report_repo=None, sentiment_repo=None):
        self.summary_repo = summary_repo
        self.review_repo = review_repo
        self.branch_tag_repo = branch_tag_repo
        self.report_repo = report_repo
        self.sentiment_repo = sentiment_repo

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

    async def _step_collect(self, branch_id: int) -> dict:
        """
        Step 1: 지점 기본 정보 및 키워드 수집

        Args:
            branch_id: 지점 ID

        Returns:
            dict: 수집된 기본 정보
        """
        summary = await self.summary_repo.get_by_branch_id(branch_id)
        if not summary:
            raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

        summary_data = summary.model_dump()

        # 차량별 분석 데이터 수집
        vehicle_analysis = await self._get_vehicle_analysis(branch_id)

        return {
            "branch_id": branch_id,
            "branch_name": summary_data.get("branch_name", f"지점 {branch_id}"),
            "affiliate_name": summary_data.get("affiliate_name", ""),
            "total_reviews": summary_data.get("review_count", 0),
            "keywords": summary_data.get("keywords", [])[:10],
            "vehicle_analysis": [v.model_dump() for v in vehicle_analysis],
        }
        # summary, summary_data 메모리 해제

    async def _step_tags(self, branch_id: int) -> dict:
        """
        Step 2: 태그 조회 (현재는 사용하지 않음, 향후 확장 가능)

        Args:
            branch_id: 지점 ID

        Returns:
            dict: 빈 딕셔너리
        """
        return {}

    async def _step_ai(self, data: dict) -> dict:
        """
        Step 3: AI 분석 (LLM 호출)

        Args:
            data: 이전 단계에서 수집된 데이터

        Returns:
            dict: AI 분석 결과 (직렬화된 형태)
        """
        # 기간 요약 생성 (DB 저장 요약 우선 사용으로 토큰 절약)
        period_summary = await self._generate_period_summary(
            branch_name=data["branch_name"],
            total_reviews=data["total_reviews"],
            top_keywords=data["keywords"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            branch_id=data.get("branch_id"),
        )

        return {
            "period_summary": period_summary,
        }

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
            tags: Step 2에서 조회된 태그 데이터 (현재 미사용)
            ai: Step 3에서 생성된 AI 분석 결과
            start_date: 시작일
            end_date: 종료일

        Returns:
            ReportData: 최종 리포트
        """
        report = ReportData(
            branch_id=collected["branch_id"],
            branch_name=collected["branch_name"],
            affiliate_name=collected["affiliate_name"],
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            total_reviews=collected["total_reviews"],
            top_keywords=collected["keywords"],
            period_summary=ai["period_summary"],
            vehicle_analysis=[VehicleAnalysis(**v) for v in collected.get("vehicle_analysis", [])],
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
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
        collected = await self._step_collect(branch_id)
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
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            )

        # Step 2: 태그 분석 (30-50%)
        await update_progress(30)
        tags = await self._step_tags(branch_id)
        await update_progress(50)

        # Step 3: AI 분석 (70-90%)
        await update_progress(70)
        ai_data = {
            **collected,
            **tags,
            "start_date": start_date,
            "end_date": end_date,
        }
        ai = await self._step_ai(ai_data)
        await update_progress(90)

        # Step 4: 리포트 조립 및 저장 (95-100%)
        await update_progress(95)
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

    async def _get_vehicle_analysis(self, branch_id: int) -> list[VehicleAnalysis]:
        """
        차량별 평가 분석 (car_model_tags 테이블 활용)

        Args:
            branch_id: 지점 ID

        Returns:
            list[VehicleAnalysis]: 차량별 분석 리스트
        """
        from repository.session import get_client

        client = await get_client()

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

    async def _generate_period_summary(
        self,
        branch_name: str,
        total_reviews: int,
        top_keywords: list[str],
        start_date: datetime,
        end_date: datetime,
        branch_id: int | None = None,
    ) -> str:
        """
        기간 요약 생성 (DB 저장된 요약 우선 사용)

        토큰 절약을 위해 branch_summaries에 저장된 요약을 먼저 확인하고,
        없는 경우에만 LLM을 호출합니다.

        Args:
            branch_name: 지점명
            total_reviews: 총 리뷰 수
            top_keywords: 핵심 키워드
            start_date: 시작일
            end_date: 종료일
            branch_id: 지점 ID (DB 조회용)

        Returns:
            str: 기간 요약 텍스트
        """
        # 1. DB에 저장된 요약 확인 (토큰 절약)
        if branch_id and self.summary_repo:
            try:
                summary = await self.summary_repo.get_by_branch_id(branch_id)
                if summary:
                    summary_data = summary.model_dump()
                    # 기간에 맞는 요약 찾기 (3m → 6m → 1y → all 순서)
                    for field in ["summary_3m", "summary_6m", "summary_1y", "summary_all"]:
                        saved_summary = summary_data.get(field)
                        if saved_summary:
                            logging.info(
                                f"DB 저장 요약 사용: branch_id={branch_id}, field={field}"
                            )
                            return saved_summary
            except Exception as e:
                logging.warning(f"DB 요약 조회 실패 (branch_id={branch_id}): {e}")

        # 2. DB에 없으면 LLM 호출 (RichSummaryPromptBuilder 사용)
        from infrastructure.llm import get_provider
        from infrastructure.llm.prompts import RichSummaryPromptBuilder

        tag_sentiments_for_prompt = [
            {"name": kw, "positive": 1, "negative": 0, "neutral": 0, "total": 1}
            for kw in top_keywords[:7]
        ]
        sentiment_stats_for_prompt = {
            "positive": total_reviews,
            "negative": 0,
            "neutral": 0,
            "total": total_reviews,
        }

        start_date_str = start_date.strftime("%Y년 %m월 %d일")
        end_date_str = end_date.strftime("%Y년 %m월 %d일")

        system_prompt, user_prompt = RichSummaryPromptBuilder.create_prompt(
            branch_name=branch_name,
            start_date=start_date_str,
            end_date=end_date_str,
            total_reviews=total_reviews,
            tag_sentiments=tag_sentiments_for_prompt,
            sentiment_stats=sentiment_stats_for_prompt,
            sample_reviews=[],
        )

        try:
            llm_provider = get_provider()
            response = await llm_provider.async_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=200,
                temperature=0.7,
            )

            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
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
