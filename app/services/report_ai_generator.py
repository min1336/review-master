"""리포트 AI 텍스트 생성기

3개 LLM 호출(기간 요약, 업체 평가, 차량 평가)을 순차로 실행합니다.
_generate_affiliate_text / _generate_vehicle_text의 공통 구조를
_generate_evaluation_text로 통합하여 중복을 제거합니다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

from domain.analysis.patterns import AFFILIATE_CATEGORIES, VEHICLE_CATEGORIES

if TYPE_CHECKING:
    from repository.review_repository import BranchReviewRepository
    from repository.summary_repository import SummaryRepository

logger = logging.getLogger(__name__)


class ReportAIGenerator:
    """AI 분석 텍스트 생성 (Step 3)"""

    def __init__(
        self,
        summary_repo: SummaryRepository,
        review_repo: BranchReviewRepository,
        athena_client=None,
    ) -> None:
        self.summary_repo = summary_repo
        self.review_repo = review_repo
        self.athena_client = athena_client

    async def generate_all(self, data: dict, report_config=None) -> dict:
        """3개 LLM 호출 순차 실행 (Step 3 오케스트레이터)

        Args:
            data: 이전 단계에서 수집된 데이터
            report_config: ResolvedReportConfig (커스텀 설정)

        Returns:
            dict: {period_summary, affiliate_ai_text, vehicle_ai_text}
        """
        from schemas.report import ResolvedReportConfig
        cfg = report_config or ResolvedReportConfig()

        # 대표 리뷰 수집 (config에 따라 스킵 가능)
        sample_reviews = []
        if cfg.data.include_sample_reviews:
            sample_reviews = await self._collect_sample_reviews(data, limit=cfg.data.sample_review_count)

        # 차량 분석 요약 텍스트 생성
        vehicle_summary = self._build_vehicle_summary(data.get("vehicle_analysis", []))

        # 순차 생성: 이전 텍스트를 다음 프롬프트에 전달하여 중복 방지
        period_summary = ""
        affiliate_ai_text = ""
        vehicle_ai_text = ""

        # 1. 기간 요약 생성
        if cfg.output.include_period_summary:
            period_summary = await self._generate_period_summary(
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
                report_config=cfg,
            )

        # 업체/차량 평가 AI 텍스트는 사용하지 않으므로 생성 스킵

        return {
            "period_summary": period_summary,
            "affiliate_ai_text": affiliate_ai_text,
            "vehicle_ai_text": vehicle_ai_text,
        }

    # ----------------------------------------------------------------
    # 통합 평가 텍스트 생성 (affiliate / vehicle 공통)
    # ----------------------------------------------------------------

    @staticmethod
    def _to_dicts(items: list) -> list[dict]:
        """Pydantic 모델 또는 dict 리스트를 dict 리스트로 변환"""
        return [
            it.model_dump() if hasattr(it, "model_dump") else it
            for it in items
        ]

    async def _generate_evaluation_text(
        self,
        branch_name: str,
        tag_details: list[dict],
        category_filter: set,
        prompt_method: str,
        top_positive: list,
        top_negative: list,
        sample_reviews: list[str] | None,
        label: str,
        report_config=None,
        prior_texts: list[str] | None = None,
    ) -> str:
        """업체/차량 평가 공통 LLM 호출"""
        filtered_tags = [
            t for t in tag_details
            if t.get("category_name") in category_filter
        ]
        if not filtered_tags:
            return ""

        try:
            from infrastructure.llm import get_provider
            from infrastructure.llm.prompts import RichSummaryPromptBuilder
            from infrastructure.llm.validator import strip_markdown_formatting

            builder_method = getattr(RichSummaryPromptBuilder, prompt_method)
            system_prompt, user_prompt = builder_method(
                branch_name=branch_name,
                tag_details=filtered_tags,
                **{
                    ("top_positive_tags" if "affiliate" in prompt_method else "top_liked_vehicles"):
                        self._to_dicts(top_positive),
                    ("top_negative_tags" if "affiliate" in prompt_method else "top_disliked_vehicles"):
                        self._to_dicts(top_negative),
                },
                sample_reviews=sample_reviews,
                prior_texts=prior_texts,
            )

            # 커스텀 설정 적용
            # 한국어 1글자 ≈ 2~3 토큰이므로 글자수 × 2 로 계산
            temperature = 0.5
            max_tokens = 600
            if report_config:
                system_prompt, user_prompt = RichSummaryPromptBuilder.apply_custom_config(
                    system_prompt, user_prompt,
                    custom_instruction=report_config.prompt.custom_instruction,
                    perspective=report_config.prompt.analysis_perspective,
                    tone=report_config.prompt.tone,
                    max_length=report_config.output.eval_max_length,
                    detail_level=report_config.prompt.detail_level,
                    focus_areas=report_config.prompt.focus_areas,
                )
                temperature = report_config.prompt.temperature
                max_tokens = report_config.output.eval_max_length * 2

            llm_provider = get_provider()
            response = await llm_provider.async_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.content if hasattr(response, "content") else str(response)
            content = strip_markdown_formatting(content).strip()

            # 숫자 할루시네이션 교정: 테이블에 표시되는 건수만 기준으로 사용
            # (tag_details의 개별 태그 건수는 카테고리 집계와 다를 수 있으므로 제외)
            canonical = set()
            for t in self._to_dicts(top_positive):
                c = t.get("count", 0)
                if c > 0:
                    canonical.add(c)
            for t in self._to_dicts(top_negative):
                c = t.get("count", 0)
                if c > 0:
                    canonical.add(c)
            return self._fix_number_hallucinations(content, canonical)

        except Exception as e:
            logger.error("%s 평가 텍스트 생성 실패: %s", label, e)
            return ""

    # ----------------------------------------------------------------
    # 기간 요약
    # ----------------------------------------------------------------

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
        report_config=None,
    ) -> str:
        """기간 요약 생성 (DB 저장된 요약 우선 사용)"""
        # 1. DB에 저장된 요약 확인 (토큰 절약)
        cached = await self._fetch_cached_summary(branch_id, tag_sentiments)
        if cached:
            return cached

        # 2. DB에 없으면 LLM 호출
        from infrastructure.llm import get_provider

        tag_sentiments_for_prompt, sentiment_stats_for_prompt, start_date_str, end_date_str = (
            self._prepare_prompt_data(
                top_tags, tag_sentiments, sentiment_stats, total_reviews, start_date, end_date
            )
        )

        system_prompt, user_prompt, max_tokens = self._build_period_prompt(
            branch_name=branch_name,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            total_reviews=total_reviews,
            tag_sentiments=tag_sentiments,
            tag_sentiments_for_prompt=tag_sentiments_for_prompt,
            sentiment_stats_for_prompt=sentiment_stats_for_prompt,
            sample_reviews=sample_reviews,
            vehicle_summary=vehicle_summary,
        )

        report_mode = tag_sentiments is not None
        temperature = 0.5 if report_mode else 0.7

        try:
            # 커스텀 설정 적용
            if report_config and report_mode:
                system_prompt, user_prompt, temperature, max_tokens = (
                    self._apply_custom_config_period(
                        system_prompt, user_prompt, report_config, temperature
                    )
                )

            llm_provider = get_provider()
            response = await llm_provider.async_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.content if hasattr(response, "content") else str(response)

            # LLM 응답 품질 검증 및 자동 정제
            validation_mode = "report" if tag_sentiments else "summary"
            content = self._clean_llm_response(content, validation_mode)

            # 숫자 할루시네이션 교정
            # sentiment_stats/tag_sentiments의 건수는 태그 멘션 합계이므로
            # canonical에 포함하지 않음 (리뷰 수와 혼동 방지)
            canonical_nums: set[int] = {total_reviews}
            content = self._fix_number_hallucinations(content, canonical_nums)

            # 리포트 모드 내용 품질 검증
            self._validate_period_content(content, tag_sentiments, sentiment_stats, branch_id)

            return content
        except Exception as e:
            logger.error("기간 요약 생성 실패: %s", e)

        return self._fallback_summary(branch_name, start_date, end_date, total_reviews, top_tags)

    async def _fetch_cached_summary(
        self,
        branch_id: int | None,
        tag_sentiments: list[dict] | None,
    ) -> str | None:
        """DB에 저장된 기간 요약 반환 (없으면 None)"""
        if tag_sentiments or not branch_id or not self.summary_repo:
            return None
        try:
            summary = await self.summary_repo.get_by_branch_id(branch_id)
            if summary:
                summary_data = summary.model_dump()
                for field in ["summary_1m", "summary_3m", "summary_6m", "summary_1y", "summary_all"]:
                    saved_summary = summary_data.get(field)
                    if saved_summary:
                        logger.info(
                            f"DB 저장 요약 사용: branch_id={branch_id}, field={field}"
                        )
                        return saved_summary
        except Exception as e:
            logger.warning("DB 요약 조회 실패 (branch_id=%s): %s", branch_id, e)
        return None

    @staticmethod
    def _prepare_prompt_data(
        top_tags: list[str],
        tag_sentiments: list[dict] | None,
        sentiment_stats: dict | None,
        total_reviews: int,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[list[dict], dict, str, str]:
        """프롬프트 입력 데이터 준비 (tag_sentiments, sentiment_stats, 날짜 문자열)"""
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
        return tag_sentiments_for_prompt, sentiment_stats_for_prompt, start_date_str, end_date_str

    @staticmethod
    def _build_period_prompt(
        branch_name: str,
        start_date_str: str,
        end_date_str: str,
        total_reviews: int,
        tag_sentiments: list[dict] | None,
        tag_sentiments_for_prompt: list[dict],
        sentiment_stats_for_prompt: dict,
        sample_reviews: list[str] | None,
        vehicle_summary: str | None,
    ) -> tuple[str, str, int]:
        """기간 요약 프롬프트 구성, (system_prompt, user_prompt, max_tokens) 반환"""
        from infrastructure.llm.prompts import RichSummaryPromptBuilder

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
            # 한국어 1글자 ≈ 2~3 토큰이므로 글자수 × 2 로 계산
            max_tokens = 1200
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
            max_tokens = 500

        return system_prompt, user_prompt, max_tokens

    @staticmethod
    def _apply_custom_config_period(
        system_prompt: str,
        user_prompt: str,
        report_config,
        temperature: float,
    ) -> tuple[str, str, float, int]:
        """커스텀 설정 적용 후 (system_prompt, user_prompt, temperature, max_tokens) 반환"""
        from infrastructure.llm.prompts import RichSummaryPromptBuilder

        system_prompt, user_prompt = RichSummaryPromptBuilder.apply_custom_config(
            system_prompt, user_prompt,
            custom_instruction=report_config.prompt.custom_instruction,
            perspective=report_config.prompt.analysis_perspective,
            tone=report_config.prompt.tone,
            max_length=report_config.output.summary_max_length,
            detail_level=report_config.prompt.detail_level,
            focus_areas=report_config.prompt.focus_areas,
        )
        temperature = report_config.prompt.temperature
        max_tokens = report_config.output.summary_max_length * 2
        return system_prompt, user_prompt, temperature, max_tokens

    @staticmethod
    def _validate_period_content(
        content: str,
        tag_sentiments: list[dict] | None,
        sentiment_stats: dict | None,
        branch_id: int | None,
    ) -> None:
        """리포트 모드 내용 품질 검증 (경고 로깅만 수행)"""
        if not (tag_sentiments and sentiment_stats):
            return
        from infrastructure.llm.validator import validate_report_content

        neg_ratio = 0
        total = sentiment_stats.get("total", 0)
        if total > 0:
            neg_ratio = sentiment_stats.get("negative", 0) / total * 100

        is_content_valid, content_warnings = validate_report_content(
            content, negative_ratio=neg_ratio
        )
        if not is_content_valid:
            logger.warning(
                f"리포트 내용 검증 경고 (branch_id={branch_id}): {content_warnings}"
            )

    @staticmethod
    def _fallback_summary(
        branch_name: str,
        start_date: datetime,
        end_date: datetime,
        total_reviews: int,
        top_tags: list[str],
    ) -> str:
        """LLM 호출 실패 시 기본 요약 텍스트 반환"""
        start_str = start_date.strftime('%Y년 %m월')
        end_str = end_date.strftime('%Y년 %m월')
        base = (
            f"{branch_name}의 {start_str}부터 {end_str}까지 "
            f"총 {total_reviews}건의 리뷰를 분석했습니다."
        )
        if top_tags:
            base += f" 주요 태그는 {', '.join(top_tags[:3])}입니다."
        return base

    # ----------------------------------------------------------------
    # LLM 응답 정제
    # ----------------------------------------------------------------

    def _clean_llm_response(self, content: str, validation_mode: str = "summary") -> str:
        """LLM 응답 정제 (마크다운 제거, 금지어 제거, 이모지 제거) + 재검증"""
        from infrastructure.llm.validator import (
            validate_summary, FORBIDDEN_WORDS, strip_markdown_formatting,
        )

        content = strip_markdown_formatting(content)

        is_valid, errors = validate_summary(content, mode=validation_mode)
        if is_valid:
            return content

        logger.warning("LLM 응답 검증 실패: %s", errors)

        for word in FORBIDDEN_WORDS:
            content = content.replace(word, "")
        content = re.sub(
            "["
            "\U0001f600-\U0001f64f\U0001f300-\U0001f5ff"
            "\U0001f680-\U0001f6ff\U0001f900-\U0001f9ff"
            "\U00002600-\U000026ff\U00002700-\U000027bf"
            "]+", "", content
        )
        content = content.strip()

        is_valid_after, errors_after = validate_summary(content, mode=validation_mode)
        if not is_valid_after:
            logger.warning("정제 후에도 검증 실패: %s", errors_after)

        return content

    # ----------------------------------------------------------------
    # 숫자 할루시네이션 교정
    # ----------------------------------------------------------------

    @staticmethod
    def _fix_number_hallucinations(
        text: str,
        canonical_numbers: set[int],
        threshold: float = 0.05,
    ) -> str:
        """LLM 텍스트의 숫자 할루시네이션 교정 (N건 패턴).

        canonical_numbers(원본 데이터의 정확한 건수)와 비교하여
        ±threshold(기본 5%) 이내의 근사값을 정확한 값으로 교체한다.
        10 미만의 숫자는 무시한다.
        """
        valid = {n for n in canonical_numbers if n >= 10}
        if not valid:
            return text

        def _replace(match: re.Match) -> str:
            raw = match.group(1).replace(",", "")
            try:
                n = int(raw)
            except ValueError:
                return match.group(0)
            if n < 10 or n in valid:
                return match.group(0)
            best, best_diff = None, float("inf")
            for canon in valid:
                diff = abs(n - canon)
                if diff / canon <= threshold and diff < best_diff:
                    best, best_diff = canon, diff
            if best is not None:
                logger.info("숫자 할루시네이션 교정: %s건 → %s건", n, best)
                fmt = f"{best:,}" if "," in match.group(1) else str(best)
                return f"{fmt}건"
            return match.group(0)

        return re.sub(r"([\d,]+)건", _replace, text)

    # ----------------------------------------------------------------
    # 헬퍼
    # ----------------------------------------------------------------

    async def _collect_sample_reviews(self, data: dict, limit: int = 10) -> list[str]:
        """대표 리뷰 수집 (Athena primary, Supabase fallback)"""
        sample_reviews: list[str] = []
        if not data.get("tag_sentiments"):
            return sample_reviews

        branch_id = data.get("branch_id")
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        # Athena 경로
        if self.athena_client is not None and branch_id:
            try:
                date_from = start_date.strftime("%Y-%m-%d") if start_date else None
                date_to = end_date.strftime("%Y-%m-%d") if end_date else None
                sample_reviews = await asyncio.to_thread(
                    self.athena_client.fetch_sample_reviews,
                    branch_id=branch_id,
                    date_from=date_from,
                    date_to=date_to,
                    limit=limit,
                )
                if sample_reviews:
                    return sample_reviews
            except Exception as e:
                logger.warning("Athena 대표 리뷰 조회 실패, Supabase 폴백: %s", e)

        # Supabase 폴백
        if self.review_repo:
            try:
                result = await self.review_repo.get_by_branch(
                    branch_id=branch_id,
                    review_date_from=start_date,
                    review_date_to=end_date,
                    limit=limit,
                )
                sample_reviews = [
                    r.get("content", "") for r in result.reviews if r.get("content")
                ]
            except Exception as e:
                logger.warning("대표 리뷰 조회 실패: %s", e)
        return sample_reviews

    @staticmethod
    def _build_vehicle_summary(vehicle_analysis: list[dict]) -> str | None:
        """차량 분석 요약 텍스트 생성"""
        if not vehicle_analysis:
            return None
        lines = []
        for v in vehicle_analysis[:5]:
            model = v.get("model", "")
            count = v.get("count", 0)
            praise = v.get("top_praise", "")
            issue = v.get("top_issue", "")
            like = v.get("like_ratio", 0)
            like_count = round(count * like / 100) if count > 0 else 0
            line = f"{model}({count}건, 호평 {like_count}건"
            if praise:
                line += f", 강점: {praise}"
            if issue:
                line += f", 개선: {issue}"
            line += ")"
            lines.append(line)
        return ", ".join(lines)
