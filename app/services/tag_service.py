"""
태그 Service - 비즈니스 로직
"""

from __future__ import annotations

import asyncio

from schemas.dto import (
    KeywordSentimentDTO,
    TagAnalysisResultDTO,
    TagGroupDTO,
)


class TagService:
    """태그 비즈니스 로직"""

    def __init__(self, tag_repo, branch_tag_repo):
        self.tag_repo = tag_repo
        self.branch_tag_repo = branch_tag_repo

    # ============================================================
    # 태그
    # ============================================================

    async def get_tags(
        self,
        category_id: int | None = None,
        sentiment: str | None = None,
        group_name: str | None = None,
    ) -> list[dict]:
        """태그 목록"""
        tags = await self.tag_repo.get_all_with_filters(
            category_id=category_id, sentiment=sentiment, group_name=group_name
        )
        return [t.model_dump() for t in tags]

    async def get_tag_groups(self) -> list[dict]:
        """태그 그룹 목록"""
        return await self.tag_repo.get_groups()

    async def get_tag(self, tag_id: int) -> dict | None:
        """태그 상세"""
        tag = await self.tag_repo.get_with_category(tag_id)
        return tag.model_dump() if tag else None

    async def create_tag(self, data: dict) -> dict | None:
        """태그 생성"""
        result = await self.tag_repo.create_dict(data)
        return result.model_dump() if result else None

    async def update_tag(self, tag_id: int, data: dict) -> dict | None:
        """태그 수정"""
        data["updated_at"] = "now()"
        result = await self.tag_repo.update(tag_id, data)
        return result.model_dump() if result else None

    async def delete_tag(self, tag_id: int) -> bool:
        """태그 삭제"""
        return await self.tag_repo.delete(tag_id)

    # ============================================================
    # 지점별 태그
    # ============================================================

    async def get_branch_tags(
        self, branch_id: int, period_type: str = "all", limit: int = 10
    ) -> list[dict]:
        """지점별 태그"""
        tags = await self.branch_tag_repo.get_by_branch(branch_id, period_type, limit)
        return [t.model_dump() for t in tags]

    async def get_batch_tags(self, branch_ids: list[int]) -> dict:
        """여러 지점 태그 일괄 조회"""
        if not branch_ids:
            return {}
        return await self.branch_tag_repo.get_batch_top_tags(branch_ids)

    # ============================================================
    # 태그 분석
    # ============================================================

    async def analyze_tags(self, review_text: str) -> TagAnalysisResultDTO:
        """리뷰 텍스트 태그 분석"""

        def analyze():
            from domain.analysis import KeywordExtractor

            extractor = KeywordExtractor()
            keywords = extractor.extract(review_text)

            from domain.analysis import HybridTagClassifier

            classifier = HybridTagClassifier()

            keyword_results = []
            tag_groups: dict[str, TagGroupDTO] = {}

            for kw in keywords:
                tag, score, sentiment = classifier.classify_with_sentiment(
                    kw, context=review_text
                )
                keyword_results.append(
                    KeywordSentimentDTO(keyword=kw, sentiment=sentiment)
                )

                if tag not in tag_groups:
                    tag_groups[tag] = TagGroupDTO()

                group = tag_groups[tag]
                if sentiment == "positive":
                    group.positive.append(kw)
                elif sentiment == "negative":
                    group.negative.append(kw)
                else:
                    group.neutral.append(kw)

            return TagAnalysisResultDTO(
                keywords=keyword_results,
                tag_groups=tag_groups,
            )

        return await asyncio.to_thread(analyze)
