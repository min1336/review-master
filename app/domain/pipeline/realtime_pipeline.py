"""
실시간 단건 리뷰 처리 파이프라인

신규 리뷰 1개를 받아 즉시 처리하고 집계 데이터를 DB에 저장합니다.
감정 통계와 태그별 통계를 증분 업데이트합니다.
리뷰 원본 저장은 SyncService가 담당합니다.

Usage:
    pipeline = RealtimePipeline()
    result = await pipeline.process({
        "branch_id": 1234,
        "content": "친절하고 좋았어요",
        "rating_service": 5.0,
        "rating_car": 4.5,
        "rating_convenience": 4.0
    })
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from repository.orm_models import (
    BranchReviewORM,
    BranchTagORM,
    MonthlySentimentStatsORM,
    TagORM,
)
from .pipeline import BasePipeline

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RealtimeResultDTO(BaseModel):
    """실시간 처리 결과 DTO"""

    branch_id: int
    sentiment: Literal["positive", "neutral", "negative"]
    tags: list[dict]  # [{"name": "직원친절", "sentiment": "positive"}, ...]
    saved: bool
    error: str | None = None


class RealtimePipeline(BasePipeline):
    """
    실시간 단건 리뷰 처리 파이프라인

    - 리뷰 1개를 받아 즉시 처리
    - 내용 유무에 따라 분기 처리
    - monthly_sentiment_stats + branch_tags 증분 업데이트
    """

    def __init__(self) -> None:
        super().__init__()
        self._tag_id_cache: dict[str, int] = {}  # tag_name -> tag_id

    async def process(self, review_data: dict) -> RealtimeResultDTO:
        """
        메인 진입점 - 리뷰 1개 처리

        Args:
            review_data: {
                "branch_id": int,
                "content": str (선택),
                "rating_service": float (선택),
                "rating_car": float (선택),
                "rating_convenience": float (선택)
            }

        Returns:
            RealtimeResultDTO
        """
        branch_id = review_data.get("branch_id")
        if not branch_id:
            return RealtimeResultDTO(
                branch_id=0,
                sentiment="neutral",
                tags=[],
                saved=False,
                error="branch_id 필수",
            )

        review_id = review_data.get("review_id")
        content = review_data.get("content", "").strip()
        ratings = {
            "service": review_data.get("rating_service"),
            "car": review_data.get("rating_car"),
            "convenience": review_data.get("rating_convenience"),
        }

        try:
            # 1. 감정 분석 + 태그 매핑
            if content and len(content) >= 5:
                sentiment, tags = await self._analyze_with_content(content, ratings)
            else:
                sentiment = self._analyze_by_rating(ratings)
                tags = []

            # 2. DB 저장 (증분 업데이트 + 개별 리뷰 sentiment 업데이트)
            await self._save_results(branch_id, sentiment, tags, review_id)

            logger.info(
                f"리뷰 처리 완료: branch={branch_id}, sentiment={sentiment}, tags={len(tags)}개"
            )

            return RealtimeResultDTO(
                branch_id=branch_id,
                sentiment=sentiment,
                tags=tags,
                saved=True,
            )

        except Exception as e:
            logger.error("리뷰 처리 실패: %s", e, exc_info=True)
            return RealtimeResultDTO(
                branch_id=branch_id,
                sentiment="neutral",
                tags=[],
                saved=False,
                error="processing_failed",
            )

    async def _analyze_with_content(
        self, text: str, ratings: dict
    ) -> tuple[str, list[dict]]:
        """
        내용 있을 때: Kiwi -> 태그 -> 감정 분석

        Returns:
            (sentiment, tags)
        """
        # 1. 키워드 추출 (CPU-bound → 별도 스레드)
        keywords = await asyncio.to_thread(self.extract_keywords, text)

        # 2. HybridClassifier로 태그+감정 분류 (CPU-bound → 별도 스레드)
        tag_result = await asyncio.to_thread(
            self._hybrid_classifier.classify_review, text, keywords
        )

        # 3. 태그별 감정 정리
        tags = []
        for tag_name, sentiments in tag_result.items():
            if tag_name == "기타":
                continue

            # 해당 태그의 주요 감정 결정
            pos_count = len(sentiments.get("positive", []))
            neg_count = len(sentiments.get("negative", []))

            if pos_count > neg_count:
                tag_sentiment = "positive"
            elif neg_count > pos_count:
                tag_sentiment = "negative"
            else:
                tag_sentiment = "neutral"

            tags.append({"name": tag_name, "sentiment": tag_sentiment})

        # 4. 전체 감정 결정 (CPU-bound → 별도 스레드)
        final_sentiment, _ = await asyncio.to_thread(
            self.analyze_sentiment_with_ratings,
            text,
            keywords,
            ratings.get("service"),
            ratings.get("car"),
            ratings.get("convenience"),
        )

        return final_sentiment, tags

    def _analyze_by_rating(self, ratings: dict) -> str:
        """
        내용 없을 때: 별점만으로 감정 판단

        규칙:
        - 개별 별점 3.0 미만 존재 시 positive 불가
        - 평균 별점 >= 3.5 -> positive
        - 평균 별점 >= 3.0 -> neutral
        - 평균 별점 < 3.0 -> negative
        """
        valid_ratings = [
            r for r in [ratings.get("service"), ratings.get("car"), ratings.get("convenience")]
            if r is not None
        ]

        if not valid_ratings:
            return "neutral"

        from core.constants import NEGATIVE_RATING_THRESHOLD

        # 개별 차원 하한 검증: 하나라도 3.0 미만이면 positive 불가
        if any(r < NEGATIVE_RATING_THRESHOLD for r in valid_ratings):
            avg_rating = sum(valid_ratings) / len(valid_ratings)
            if avg_rating >= 3.5:
                return "neutral"
            return "negative"

        avg_rating = sum(valid_ratings) / len(valid_ratings)

        if avg_rating >= 3.5:
            return "positive"
        elif avg_rating >= NEGATIVE_RATING_THRESHOLD:
            return "neutral"
        else:
            return "negative"

    async def _save_results(
        self,
        branch_id: int,
        sentiment: str,
        tags: list[dict],
        review_id: int | None = None,
    ) -> None:
        """
        DB 저장 (트랜잭션으로 증분 업데이트)

        1. branch_reviews.sentiment: 개별 리뷰 감정 업데이트
        2. monthly_sentiment_stats: 전체 감정 +1
        3. branch_tags: 태그별 감정 +1
        """
        session = await self._get_session()

        try:
            # 1. 개별 리뷰 sentiment 업데이트
            if review_id:
                await session.execute(
                    update(BranchReviewORM)
                    .where(BranchReviewORM.review_id == review_id)
                    .values(sentiment=sentiment)
                )

            # 2. 전체 감정 통계 증분
            await self._increment_sentiment_stats(session, branch_id, sentiment)

            # 3. 태그별 감정 증분
            for tag in tags:
                tag_name = tag["name"]
                tag_sentiment = tag["sentiment"]

                tag_id = await self._get_tag_id(session, tag_name)
                if tag_id:
                    await self._increment_tag_sentiment(
                        session, branch_id, tag_id, tag_sentiment
                    )

            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def _increment_sentiment_stats(
        self, session: AsyncSession, branch_id: int, sentiment: str
    ) -> None:
        """monthly_sentiment_stats SQL-level 증분 업데이트 (SELECT 불필요)"""
        from datetime import datetime

        period = datetime.now().strftime("%Y-%m")
        tbl = MonthlySentimentStatsORM.__table__

        pos_delta = 1 if sentiment == "positive" else 0
        neg_delta = 1 if sentiment == "negative" else 0
        neu_delta = 1 if sentiment == "neutral" else 0

        stmt = pg_insert(tbl).values(
            branch_id=branch_id,
            period=period,
            positive_count=pos_delta,
            negative_count=neg_delta,
            neutral_count=neu_delta,
            review_count=1,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["branch_id", "period"],
            set_={
                "positive_count": tbl.c.positive_count + stmt.excluded.positive_count,
                "negative_count": tbl.c.negative_count + stmt.excluded.negative_count,
                "neutral_count": tbl.c.neutral_count + stmt.excluded.neutral_count,
                "review_count": tbl.c.review_count + stmt.excluded.review_count,
            },
        )
        await session.execute(stmt)

    async def _get_tag_id(self, session: AsyncSession, tag_name: str) -> int | None:
        """태그 이름으로 ID 조회 (캐시 사용)"""
        if tag_name in self._tag_id_cache:
            return self._tag_id_cache[tag_name]

        result = await session.execute(
            select(TagORM.id)
            .where(TagORM.name == tag_name)
            .where(TagORM.is_active == True)  # noqa: E712
        )
        tag_id = result.scalar_one_or_none()

        if tag_id is not None:
            self._tag_id_cache[tag_name] = tag_id
            return tag_id

        return None

    async def _increment_tag_sentiment(
        self,
        session: AsyncSession,
        branch_id: int,
        tag_id: int,
        sentiment: str,
    ) -> None:
        """branch_tags SQL-level 증분 업데이트 (SELECT 불필요)"""
        bt_tbl = BranchTagORM.__table__

        pos_delta = 1 if sentiment == "positive" else 0
        neg_delta = 1 if sentiment == "negative" else 0
        neu_delta = 1 if sentiment == "neutral" else 0

        stmt = pg_insert(bt_tbl).values(
            branch_id=branch_id,
            tag_id=tag_id,
            period_type="all",
            positive_count=pos_delta,
            negative_count=neg_delta,
            neutral_count=neu_delta,
            count=1,
            weighted_score=1.0,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["branch_id", "tag_id", "period_type"],
            set_={
                "positive_count": bt_tbl.c.positive_count + stmt.excluded.positive_count,
                "negative_count": bt_tbl.c.negative_count + stmt.excluded.negative_count,
                "neutral_count": bt_tbl.c.neutral_count + stmt.excluded.neutral_count,
                "count": bt_tbl.c.count + stmt.excluded.count,
                "weighted_score": func.coalesce(bt_tbl.c.weighted_score, 0.0) + stmt.excluded.weighted_score,
            },
        )
        await session.execute(stmt)

    # BasePipeline의 추상 메서드 구현
    async def run(self, *args, **kwargs):
        """단건 처리용이므로 process() 사용"""
        if args and isinstance(args[0], dict):
            return await self.process(args[0])
        return await self.process(kwargs)
