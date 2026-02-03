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

        return {
            "branch_id": branch_id,
            "branch_name": summary_data.get("branch_name", f"지점 {branch_id}"),
            "affiliate_name": summary_data.get("affiliate_name", ""),
            "total_reviews": summary_data.get("review_count", 0),
            "keywords": summary_data.get("keywords", [])[:10],
        }
        # summary, summary_data 메모리 해제

    async def _step_tags(self, branch_id: int) -> dict:
        """
        Step 2: 태그별 강점/약점 조회

        Args:
            branch_id: 지점 ID

        Returns:
            dict: 강점/약점 데이터 (직렬화된 형태)
        """
        strengths, weaknesses = await self._get_strengths_weaknesses_from_db(branch_id)

        return {
            "strengths": [s.model_dump() for s in strengths],
            "weaknesses": [w.model_dump() for w in weaknesses],
        }
        # strengths, weaknesses 원본 메모리 해제

    async def _step_ai(self, data: dict) -> dict:
        """
        Step 3: AI 분석 (LLM 호출)

        Args:
            data: 이전 단계에서 수집된 데이터

        Returns:
            dict: AI 분석 결과 (직렬화된 형태)
        """
        # dict에서 StrengthWeakness 복원
        weaknesses = [StrengthWeakness(**w) for w in data.get("weaknesses", [])]
        strengths = [StrengthWeakness(**s) for s in data.get("strengths", [])]

        # 액션 아이템 생성
        action_items = await self._generate_action_items(
            weaknesses, [], data["branch_name"]
        )

        # 기간 요약 생성
        period_summary = await self._generate_period_summary(
            branch_name=data["branch_name"],
            total_reviews=data["total_reviews"],
            top_keywords=data["keywords"],
            strengths=strengths,
            weaknesses=weaknesses,
            start_date=data["start_date"],
            end_date=data["end_date"],
        )

        return {
            "action_items": [item.model_dump() for item in action_items],
            "period_summary": period_summary,
        }
        # LLM 응답 관련 변수 메모리 해제

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
        report = ReportData(
            branch_id=collected["branch_id"],
            branch_name=collected["branch_name"],
            affiliate_name=collected["affiliate_name"],
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            total_reviews=collected["total_reviews"],
            sentiment_trend=[],  # DB에 기간별 데이터 없음 - 제외
            top_keywords=collected["keywords"],
            period_summary=ai["period_summary"],
            vehicle_analysis=[],  # 실시간 계산 필요 - 제외
            strengths=[StrengthWeakness(**s) for s in tags["strengths"]],
            weaknesses=[StrengthWeakness(**w) for w in tags["weaknesses"]],
            action_items=[ActionItem(**item) for item in ai["action_items"]],
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
                import logging

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

    async def _get_strengths_weaknesses_from_db(
        self, branch_id: int
    ) -> tuple[list[StrengthWeakness], list[StrengthWeakness]]:
        """branch_tags 테이블에서 강점/약점 조회"""
        strengths = []
        weaknesses = []

        # positive 태그 조회 (강점)
        positive_tags = await self.branch_tag_repo.get_by_branch(
            branch_id, period_type="positive", limit=10
        )
        for tag in positive_tags:
            tag_data = tag.model_dump() if hasattr(tag, "model_dump") else tag
            tag_info = tag_data.get("tags", {})
            tag_name = tag_info.get("name", "") if isinstance(tag_info, dict) else ""
            count = tag_data.get("count", 0)

            if tag_name and count >= 2:
                strengths.append(StrengthWeakness(
                    tag=tag_name,
                    ratio=0.0,  # DB에 비율 없음
                    sample=""   # DB에 샘플 없음
                ))

        # negative 태그 조회 (약점)
        negative_tags = await self.branch_tag_repo.get_by_branch(
            branch_id, period_type="negative", limit=10
        )
        for tag in negative_tags:
            tag_data = tag.model_dump() if hasattr(tag, "model_dump") else tag
            tag_info = tag_data.get("tags", {})
            tag_name = tag_info.get("name", "") if isinstance(tag_info, dict) else ""
            count = tag_data.get("count", 0)

            if tag_name and count >= 2:
                weaknesses.append(StrengthWeakness(
                    tag=tag_name,
                    ratio=0.0,
                    sample=""
                ))

        return strengths[:5], weaknesses[:5]

    async def _generate_action_items(
        self,
        weaknesses: list[StrengthWeakness],
        reviews_data: list[dict],
        branch_name: str,
    ) -> list[ActionItem]:
        """AI로 개선 액션 아이템 생성"""
        from infrastructure.llm import get_provider

        # 부정 리뷰 수집
        # reviews_data가 비어있으면 빈 리스트 처리
        if not reviews_data:
            negative_reviews = []
        else:
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
