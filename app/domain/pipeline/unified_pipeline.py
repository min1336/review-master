from __future__ import annotations

import asyncio
import gc
import logging
import time
from collections.abc import Awaitable, Callable

from core.timezone import utc_now
from repository.database import get_session_factory
from schemas.dto import PipelineResultDTO, PipelineStepResultDTO

from .steps.preprocessor import ReviewPreprocessor
from .steps.review_updater import ReviewSentimentUpdater
from .steps.tag_aggregator import TagAggregator
from .steps.car_model_tags import CarModelTagAggregator
from .steps.keyword_manager import KeywordManager
from .steps.review_tag_mapper import ReviewTagMapper
from .steps.monthly_stats import MonthlyStatsUpdater
from .steps.monthly_car_model_stats import MonthlyCarModelStatsUpdater

logger = logging.getLogger(__name__)


class UnifiedPipeline:
    """통합 파이프라인 - Athena 리뷰를 받아 모든 집계 테이블을 한 번에 갱신"""

    def __init__(self) -> None:
        self.preprocessor = ReviewPreprocessor()
        self.review_updater = ReviewSentimentUpdater()
        self.tag_aggregator = TagAggregator()
        self.car_model_tags = CarModelTagAggregator()
        self.keyword_manager = KeywordManager()
        self.review_tag_mapper = ReviewTagMapper()
        self.monthly_stats = MonthlyStatsUpdater()
        self.monthly_car_model_stats = MonthlyCarModelStatsUpdater()

    async def _step_preprocess(
        self,
        reviews: list[dict],
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> list | None:
        """Step 1: 전처리 + 키워드 + 감정 + 태그 분류 (동기). 실패 시 None 반환."""
        t0 = time.monotonic()
        try:
            processed = await asyncio.to_thread(
                self.preprocessor.process_batch, reviews
            )
            result.add_step(PipelineStepResultDTO(
                step_name="preprocessor", success=True,
                input_count=len(reviews), output_count=len(processed),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 1 완료: %s/%s개 처리", len(processed), len(reviews))
            # 전처리 후 raw dict 리스트 해제 (ProcessedReviewDTO로 변환 완료)
            reviews.clear()
            gc.collect()
            if progress_callback:
                await progress_callback(50, "전처리 완료")
            return processed
        except Exception as e:
            logger.error("Step 1(preprocessor) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="preprocessor", success=False,
                input_count=len(reviews), output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            result.error_message = f"전처리 실패: {e}"
            result.finished_at = utc_now()
            return None

    async def _step_update_review_sentiment(
        self,
        session,
        processed: list,
        input_count: int,
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> None:
        """Step 2: branch_reviews.sentiment 업데이트."""
        t0 = time.monotonic()
        try:
            async with session.begin_nested():
                s2 = await self.review_updater.update(session, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="review_updater", success=True,
                input_count=input_count, output_count=s2,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 2 완료: %s개 sentiment 업데이트", s2)
            if progress_callback:
                await progress_callback(60, "감정 업데이트 완료")
        except Exception as e:
            logger.error("Step 2(review_updater) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="review_updater", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

    async def _step_aggregate_tags(
        self,
        session,
        processed: list,
        input_count: int,
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> bool:
        """Step 4: tags + branch_tags 집계. 성공 여부 반환."""
        t0 = time.monotonic()
        try:
            async with session.begin_nested():
                s4 = await self.tag_aggregator.aggregate(session, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="tag_aggregator", success=True,
                input_count=input_count, output_count=s4 if isinstance(s4, int) else 0,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 4 완료: %s", s4)
            if progress_callback:
                await progress_callback(80, "태그 집계 완료")
            return True
        except Exception as e:
            logger.error("Step 4(tag_aggregator) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="tag_aggregator", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            return False

    async def _step_aggregate_car_models(
        self,
        session,
        processed: list,
        input_count: int,
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> None:
        """Step 5: car_models_master + branch_car_models 갱신."""
        t0 = time.monotonic()
        try:
            async with session.begin_nested():
                s5 = await self.car_model_tags.aggregate(session, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="car_model_master", success=True,
                input_count=input_count, output_count=s5 if isinstance(s5, int) else 0,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 5 완료: %s", s5)
            if progress_callback:
                await progress_callback(85, "차량 마스터/관계 갱신 완료")
        except Exception as e:
            logger.error("Step 5(car_model_master) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="car_model_master", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

    async def _step_update_keywords(
        self,
        session,
        processed: list,
        input_count: int,
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> None:
        """Step 6: branch_keywords 갱신."""
        t0 = time.monotonic()
        try:
            async with session.begin_nested():
                s6 = await self.keyword_manager.update(session, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="keyword_manager", success=True,
                input_count=input_count, output_count=s6,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 6 완료: %s개 지점 키워드 갱신", s6)
            if progress_callback:
                await progress_callback(90, "키워드 갱신 완료")
        except Exception as e:
            logger.error("Step 6(keyword_manager) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="keyword_manager", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

    async def _step_map_review_tags(
        self,
        session,
        processed: list,
        input_count: int,
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> None:
        """Step 7: review_tag_mappings 저장."""
        t0 = time.monotonic()
        try:
            async with session.begin_nested():
                s7 = await self.review_tag_mapper.save(session, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="review_tag_mapper", success=True,
                input_count=input_count, output_count=s7,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 7 완료: %s개 review_tag_mappings 저장", s7)
            if progress_callback:
                await progress_callback(92, "리뷰 태그 매핑 완료")
        except Exception as e:
            logger.error("Step 7(review_tag_mapper) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="review_tag_mapper", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

    async def _step_update_monthly_stats(
        self,
        session,
        processed: list,
        input_count: int,
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> None:
        """Step 8: monthly_rating/sentiment/tag_stats 갱신."""
        t0 = time.monotonic()
        try:
            async with session.begin_nested():
                s8 = await self.monthly_stats.update(session, processed)
            total_monthly = sum(s8.values()) if isinstance(s8, dict) else 0
            result.add_step(PipelineStepResultDTO(
                step_name="monthly_stats", success=True,
                input_count=input_count, output_count=total_monthly,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 8 완료: %s", s8)
            if progress_callback:
                await progress_callback(95, "월별 통계 완료")
        except Exception as e:
            logger.error("Step 8(monthly_stats) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="monthly_stats", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

    async def _step_update_monthly_car_model_stats(
        self,
        session,
        processed: list,
        input_count: int,
        result: PipelineResultDTO,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> None:
        """Step 9: monthly_car_model_tag_stats 저장."""
        t0 = time.monotonic()
        try:
            async with session.begin_nested():
                s9 = await self.monthly_car_model_stats.update(session, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="monthly_car_model_stats", success=True,
                input_count=input_count, output_count=s9,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info("Step 9 완료: %s개 monthly_car_model_tag_stats 저장", s9)
            if progress_callback:
                await progress_callback(98, "차량 월별 통계 완료")
        except Exception as e:
            logger.error("Step 9(monthly_car_model_stats) 실패: %s", e)
            result.add_step(PipelineStepResultDTO(
                step_name="monthly_car_model_stats", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

    async def run(
        self,
        reviews: list[dict],
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> PipelineResultDTO:
        """
        통합 파이프라인 실행

        Args:
            reviews: Athena에서 가져온 리뷰 dict 리스트
            progress_callback: 진행률 콜백 (progress%, message)

        Returns:
            PipelineResultDTO: 파이프라인 실행 결과
        """
        started_at = utc_now()
        result = PipelineResultDTO(
            success=False, total_reviews=len(reviews),
            processed_reviews=0, total_branches=0,
            summaries_generated=0, started_at=started_at,
        )
        logger.info("통합 파이프라인 시작: %s개 리뷰", len(reviews))

        try:
            factory = get_session_factory()
            session = factory()
        except Exception as e:
            logger.error("DB 연결 실패: %s", e)
            result.error_message = str(e)
            result.finished_at = utc_now()
            return result

        try:
            # Step 1: 전처리
            processed = await self._step_preprocess(reviews, result, progress_callback)
            if processed is None:
                return result

            if not processed:
                result.success = True
                result.finished_at = utc_now()
                return result

            input_count = len(processed)

            # Step 2: branch_reviews.sentiment
            await self._step_update_review_sentiment(session, processed, input_count, result, progress_callback)

            # Step 3: (제거됨 -- monthly_stats Step 8에서 monthly_sentiment_stats 처리)

            # Step 4: tags + branch_tags
            tag_aggregation_ok = await self._step_aggregate_tags(session, processed, input_count, result, progress_callback)

            # Step 5: car_models_master + branch_car_models
            await self._step_aggregate_car_models(session, processed, input_count, result, progress_callback)

            # Step 6: branch_keywords
            await self._step_update_keywords(session, processed, input_count, result, progress_callback)

            # Step 7: review_tag_mappings
            if not tag_aggregation_ok:
                logger.warning("Step 4(태그 집계) 실패로 Step 7(review_tag_mapper) 스킵")
            else:
                await self._step_map_review_tags(session, processed, input_count, result, progress_callback)

            # Step 8: monthly_rating/sentiment/tag_stats
            if not tag_aggregation_ok:
                logger.warning("Step 4(태그 집계) 실패로 Step 8(monthly_stats) 스킵")
            else:
                await self._step_update_monthly_stats(session, processed, input_count, result, progress_callback)

            # Step 9: monthly_car_model_tag_stats
            if not tag_aggregation_ok:
                logger.warning("Step 4(태그 집계) 실패로 Step 9(monthly_car_model_stats) 스킵")
            else:
                await self._step_update_monthly_car_model_stats(session, processed, input_count, result, progress_callback)

            # 성공한 step은 커밋 (실패한 step은 savepoint에서 이미 rollback됨)
            await session.commit()
            if result.failed_steps:
                logger.warning("일부 단계 실패 (savepoint rollback): %s", result.failed_steps)

        except Exception as e:
            await session.rollback()
            logger.error("파이프라인 트랜잭션 실패: %s", e)
            result.error_message = str(e)
            result.finished_at = utc_now()
            return result
        finally:
            await session.close()

        # 최종 결과
        elapsed = (utc_now() - started_at).total_seconds()
        branch_ids = {pr.branch_id for pr in processed}

        result.processed_reviews = len(processed)
        result.total_branches = len(branch_ids)
        result.total_duration_seconds = elapsed
        result.finished_at = utc_now()

        if result.failed_steps:
            result.success = False
            result.error_message = f"실패 단계: {', '.join(result.failed_steps)}"
        else:
            result.success = True

        return result
