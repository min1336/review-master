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

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .pipeline import BasePipeline

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)


@dataclass
class RealtimeResultDTO:
    """실시간 처리 결과 DTO"""

    branch_id: int
    sentiment: Literal["positive", "neutral", "negative"]
    tags: list[dict]  # [{"name": "친절도", "sentiment": "positive"}, ...]
    saved: bool
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "branch_id": self.branch_id,
            "sentiment": self.sentiment,
            "tags": self.tags,
            "saved": self.saved,
            "error": self.error,
        }


class RealtimePipeline(BasePipeline):
    """
    실시간 단건 리뷰 처리 파이프라인

    - 리뷰 1개를 받아 즉시 처리
    - 내용 유무에 따라 분기 처리
    - branch_sentiment_stats + branch_tags 증분 업데이트
    """

    def __init__(self) -> None:
        super().__init__()
        self._hybrid_classifier = None
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

            # 2. DB 저장 (증분 업데이트)
            await self._save_results(branch_id, sentiment, tags)

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
            logger.error(f"리뷰 처리 실패: {e}")
            return RealtimeResultDTO(
                branch_id=branch_id,
                sentiment="neutral",
                tags=[],
                saved=False,
                error=str(e),
            )

    async def _analyze_with_content(
        self, text: str, ratings: dict
    ) -> tuple[str, list[dict]]:
        """
        내용 있을 때: Kiwi → 태그 → 감정 분석

        Returns:
            (sentiment, tags)
        """
        # 1. 키워드 추출
        keywords = self.extract_keywords(text)

        # 2. HybridClassifier로 태그+감정 분류
        if self._hybrid_classifier is None:
            from ..analysis import HybridClassifier

            self._hybrid_classifier = HybridClassifier(lazy_load=True)

        tag_result = self._hybrid_classifier.classify_review(
            review=text, keywords=keywords
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

        # 4. 전체 감정 결정 (내용 분석 + 별점 결합)
        content_sentiment, _ = self.analyze_sentiment(text, keywords)
        final_sentiment = self._combine_sentiment_with_rating(
            content_sentiment, ratings
        )

        return final_sentiment, tags

    def _analyze_by_rating(self, ratings: dict) -> str:
        """
        내용 없을 때: 별점만으로 감정 판단

        규칙:
        - 평균 별점 >= 4.0 → positive
        - 평균 별점 >= 3.0 → neutral
        - 평균 별점 < 3.0 → negative
        """
        valid_ratings = [
            r for r in [ratings.get("service"), ratings.get("car"), ratings.get("convenience")]
            if r is not None
        ]

        if not valid_ratings:
            return "neutral"

        avg_rating = sum(valid_ratings) / len(valid_ratings)

        if avg_rating >= 4.0:
            return "positive"
        elif avg_rating >= 3.0:
            return "neutral"
        else:
            return "negative"

    def _combine_sentiment_with_rating(
        self, content_sentiment: str, ratings: dict
    ) -> str:
        """
        내용 분석 결과와 별점을 결합하여 최종 감정 결정

        규칙:
        1. 별점 3점 이하 1개라도 있으면 → negative
        2. 내용 negative + 별점 높음 → neutral
        3. 그 외 → 내용 분석 결과 유지
        """
        LOW_RATING_THRESHOLD = 3.0

        valid_ratings = [
            r for r in [ratings.get("service"), ratings.get("car"), ratings.get("convenience")]
            if r is not None
        ]

        # 별점 하나라도 낮으면 negative
        if valid_ratings and any(r <= LOW_RATING_THRESHOLD for r in valid_ratings):
            return "negative"

        # 내용은 부정인데 별점이 다 높으면 neutral
        if content_sentiment == "negative" and valid_ratings:
            if all(r > LOW_RATING_THRESHOLD for r in valid_ratings):
                return "neutral"

        return content_sentiment

    async def _save_results(
        self,
        branch_id: int,
        sentiment: str,
        tags: list[dict],
    ) -> None:
        """
        DB 저장 (트랜잭션으로 증분 업데이트)

        1. branch_sentiment_stats: 전체 감정 +1
        2. branch_tags: 태그별 감정 +1
        """
        client = await self._get_supabase()

        # 1. 전체 감정 통계 증분
        await self._increment_sentiment_stats(client, branch_id, sentiment)

        # 2. 태그별 감정 증분
        for tag in tags:
            tag_name = tag["name"]
            tag_sentiment = tag["sentiment"]

            tag_id = await self._get_tag_id(client, tag_name)
            if tag_id:
                await self._increment_tag_sentiment(
                    client, branch_id, tag_id, tag_sentiment
                )

    async def _increment_sentiment_stats(
        self, client: AsyncClient, branch_id: int, sentiment: str
    ) -> None:
        """branch_sentiment_stats 증분 업데이트"""
        # 현재 값 조회
        result = await (
            client.table("branch_sentiment_stats")
            .select("*")
            .eq("branch_id", branch_id)
            .execute()
        )

        if result.data:
            # UPDATE (증분)
            row = result.data[0]
            positive = row.get("positive_count", 0)
            negative = row.get("negative_count", 0)
            neutral = row.get("neutral_count", 0)

            if sentiment == "positive":
                positive += 1
            elif sentiment == "negative":
                negative += 1
            else:
                neutral += 1

            total = positive + negative + neutral
            pos_ratio = round(positive / total * 100, 2) if total > 0 else 0
            neg_ratio = round(negative / total * 100, 2) if total > 0 else 0

            await (
                client.table("branch_sentiment_stats")
                .update({
                    "positive_count": positive,
                    "negative_count": negative,
                    "neutral_count": neutral,
                    "total_count": total,
                    "positive_ratio": pos_ratio,
                    "negative_ratio": neg_ratio,
                    "updated_at": "now()",
                })
                .eq("branch_id", branch_id)
                .execute()
            )
        else:
            # INSERT (신규)
            positive = 1 if sentiment == "positive" else 0
            negative = 1 if sentiment == "negative" else 0
            neutral = 1 if sentiment == "neutral" else 0

            await (
                client.table("branch_sentiment_stats")
                .insert({
                    "branch_id": branch_id,
                    "positive_count": positive,
                    "negative_count": negative,
                    "neutral_count": neutral,
                    "total_count": 1,
                    "positive_ratio": positive * 100,
                    "negative_ratio": negative * 100,
                })
                .execute()
            )

    async def _get_tag_id(self, client: AsyncClient, tag_name: str) -> int | None:
        """태그 이름으로 ID 조회 (캐시 사용)"""
        if tag_name in self._tag_id_cache:
            return self._tag_id_cache[tag_name]

        result = await (
            client.table("tags")
            .select("id")
            .eq("name", tag_name)
            .eq("is_active", True)
            .execute()
        )

        if result.data:
            tag_id = result.data[0]["id"]
            self._tag_id_cache[tag_name] = tag_id
            return tag_id

        return None

    async def _increment_tag_sentiment(
        self,
        client: AsyncClient,
        branch_id: int,
        tag_id: int,
        sentiment: str,
    ) -> None:
        """branch_tags 증분 업데이트 (UPSERT)"""
        # 현재 값 조회
        result = await (
            client.table("branch_tags")
            .select("*")
            .eq("branch_id", branch_id)
            .eq("tag_id", tag_id)
            .eq("period_type", "all")
            .execute()
        )

        if result.data:
            # UPDATE (증분)
            row = result.data[0]
            positive = row.get("positive_count", 0) or 0
            negative = row.get("negative_count", 0) or 0
            count = row.get("count", 0) or 0

            if sentiment == "positive":
                positive += 1
            elif sentiment == "negative":
                negative += 1

            await (
                client.table("branch_tags")
                .update({
                    "positive_count": positive,
                    "negative_count": negative,
                    "count": count + 1,
                })
                .eq("branch_id", branch_id)
                .eq("tag_id", tag_id)
                .eq("period_type", "all")
                .execute()
            )
        else:
            # INSERT (신규)
            positive = 1 if sentiment == "positive" else 0
            negative = 1 if sentiment == "negative" else 0

            await (
                client.table("branch_tags")
                .insert({
                    "branch_id": branch_id,
                    "tag_id": tag_id,
                    "period_type": "all",
                    "positive_count": positive,
                    "negative_count": negative,
                    "count": 1,
                    "weighted_score": 1.0,
                })
                .execute()
            )

    # BasePipeline의 추상 메서드 구현
    async def run(self, *args, **kwargs):
        """단건 처리용이므로 process() 사용"""
        if args and isinstance(args[0], dict):
            return await self.process(args[0])
        return await self.process(kwargs)
