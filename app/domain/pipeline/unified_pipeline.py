import logging
import time
from datetime import datetime

from core.timezone import utc_now

from repository.session import get_client
from schemas.dto import PipelineResultDTO, PipelineStepResultDTO

from .steps.preprocessor import ReviewPreprocessor
from .steps.review_updater import ReviewSentimentUpdater
from .steps.sentiment_stats import SentimentStatsUpdater
from .steps.tag_aggregator import TagAggregator
from .steps.car_model_tags import CarModelTagAggregator
from .steps.keyword_manager import KeywordManager

logger = logging.getLogger(__name__)


class UnifiedPipeline:
    """통합 파이프라인 - Athena 리뷰를 받아 모든 집계 테이블을 한 번에 갱신"""

    def __init__(self) -> None:
        self.preprocessor = ReviewPreprocessor()
        self.review_updater = ReviewSentimentUpdater()
        self.sentiment_stats = SentimentStatsUpdater()
        self.tag_aggregator = TagAggregator()
        self.car_model_tags = CarModelTagAggregator()
        self.keyword_manager = KeywordManager()

    async def run(self, reviews: list[dict]) -> PipelineResultDTO:
        """
        통합 파이프라인 실행

        Args:
            reviews: Athena에서 가져온 리뷰 dict 리스트

        Returns:
            PipelineResultDTO: 파이프라인 실행 결과
        """
        started_at = utc_now()
        result = PipelineResultDTO(
            success=False, total_reviews=len(reviews),
            processed_reviews=0, total_branches=0,
            summaries_generated=0, started_at=started_at,
        )
        logger.info(f"통합 파이프라인 시작: {len(reviews)}개 리뷰")

        try:
            client = await get_client()
        except Exception as e:
            logger.error(f"DB 연결 실패: {e}")
            result.error_message = str(e)
            result.finished_at = utc_now()
            return result

        # Step 1: 전처리 + 키워드 + 감정 + 태그 분류 (동기)
        t0 = time.monotonic()
        try:
            processed = self.preprocessor.process_batch(reviews)
            result.add_step(PipelineStepResultDTO(
                step_name="preprocessor", success=True,
                input_count=len(reviews), output_count=len(processed),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info(f"Step 1 완료: {len(processed)}/{len(reviews)}개 처리")
        except Exception as e:
            logger.error(f"Step 1(preprocessor) 실패: {e}")
            result.add_step(PipelineStepResultDTO(
                step_name="preprocessor", success=False,
                input_count=len(reviews), output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            result.error_message = f"전처리 실패: {e}"
            result.finished_at = utc_now()
            return result

        if not processed:
            result.success = True
            result.finished_at = utc_now()
            return result

        input_count = len(processed)

        # Step 2: branch_reviews.sentiment
        t0 = time.monotonic()
        try:
            s2 = await self.review_updater.update(client, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="review_updater", success=True,
                input_count=input_count, output_count=s2,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info(f"Step 2 완료: {s2}개 sentiment 업데이트")
        except Exception as e:
            logger.error(f"Step 2(review_updater) 실패: {e}")
            result.add_step(PipelineStepResultDTO(
                step_name="review_updater", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

        # Step 3: branch_sentiment_stats
        t0 = time.monotonic()
        try:
            s3 = await self.sentiment_stats.update(client, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="sentiment_stats", success=True,
                input_count=input_count, output_count=s3,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info(f"Step 3 완료: {s3}개 지점 감정 통계 갱신")
        except Exception as e:
            logger.error(f"Step 3(sentiment_stats) 실패: {e}")
            result.add_step(PipelineStepResultDTO(
                step_name="sentiment_stats", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

        # Step 4: tags + branch_tags
        t0 = time.monotonic()
        try:
            s4 = await self.tag_aggregator.aggregate(client, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="tag_aggregator", success=True,
                input_count=input_count, output_count=s4 if isinstance(s4, int) else 0,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info(f"Step 4 완료: {s4}")
        except Exception as e:
            logger.error(f"Step 4(tag_aggregator) 실패: {e}")
            result.add_step(PipelineStepResultDTO(
                step_name="tag_aggregator", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

        # Step 5: car_model_tags
        t0 = time.monotonic()
        try:
            s5 = await self.car_model_tags.aggregate(client, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="car_model_tags", success=True,
                input_count=input_count, output_count=s5 if isinstance(s5, int) else 0,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info(f"Step 5 완료: {s5}")
        except Exception as e:
            logger.error(f"Step 5(car_model_tags) 실패: {e}")
            result.add_step(PipelineStepResultDTO(
                step_name="car_model_tags", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

        # Step 6: branch_keywords
        t0 = time.monotonic()
        try:
            s6 = await self.keyword_manager.update(client, processed)
            result.add_step(PipelineStepResultDTO(
                step_name="keyword_manager", success=True,
                input_count=input_count, output_count=s6,
                duration_seconds=round(time.monotonic() - t0, 3),
            ))
            logger.info(f"Step 6 완료: {s6}개 지점 키워드 갱신")
        except Exception as e:
            logger.error(f"Step 6(keyword_manager) 실패: {e}")
            result.add_step(PipelineStepResultDTO(
                step_name="keyword_manager", success=False,
                input_count=input_count, output_count=0,
                error_message=str(e),
                duration_seconds=round(time.monotonic() - t0, 3),
            ))

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
