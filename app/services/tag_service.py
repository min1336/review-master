"""
태그/카테고리 Service - 비즈니스 로직
"""
import asyncio
from typing import Optional, List

from crud import UnitOfWork


class TagService:
    """태그/카테고리 비즈니스 로직"""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    # ============================================================
    # 카테고리
    # ============================================================

    async def get_categories(self, is_active: bool = True) -> List[dict]:
        """카테고리 목록"""
        categories = await self.uow.categories.get_all_active(is_active)
        return [c.model_dump() for c in categories]

    async def get_category(self, category_id: int) -> Optional[dict]:
        """카테고리 상세"""
        category = await self.uow.categories.get_by_id(category_id)
        return category.model_dump() if category else None

    async def create_category(self, data: dict) -> dict:
        """카테고리 생성"""
        result = await self.uow.categories.create_dict(data)
        return result.model_dump() if result else None

    async def update_category(self, category_id: int, data: dict) -> dict:
        """카테고리 수정"""
        data['updated_at'] = 'now()'
        result = await self.uow.categories.update(category_id, data)
        return result.model_dump() if result else None

    async def delete_category(self, category_id: int) -> bool:
        """카테고리 삭제"""
        return await self.uow.categories.delete_with_tags(category_id)

    # ============================================================
    # 태그
    # ============================================================

    async def get_tags(
        self,
        category_id: Optional[int] = None,
        sentiment: Optional[str] = None,
        group_name: Optional[str] = None
    ) -> List[dict]:
        """태그 목록"""
        tags = await self.uow.tags.get_all_with_filters(
            category_id=category_id,
            sentiment=sentiment,
            group_name=group_name
        )
        return [t.model_dump() for t in tags]

    async def get_tag_groups(self) -> List[dict]:
        """태그 그룹 목록"""
        return await self.uow.tags.get_groups()

    async def get_tag(self, tag_id: int) -> Optional[dict]:
        """태그 상세"""
        tag = await self.uow.tags.get_with_category(tag_id)
        return tag.model_dump() if tag else None

    async def create_tag(self, data: dict) -> dict:
        """태그 생성"""
        result = await self.uow.tags.create_dict(data)
        return result.model_dump() if result else None

    async def update_tag(self, tag_id: int, data: dict) -> dict:
        """태그 수정"""
        data['updated_at'] = 'now()'
        result = await self.uow.tags.update(tag_id, data)
        return result.model_dump() if result else None

    async def delete_tag(self, tag_id: int) -> bool:
        """태그 삭제"""
        return await self.uow.tags.delete(tag_id)

    # ============================================================
    # 키워드 매핑
    # ============================================================

    async def get_mappings(
        self,
        tag_id: Optional[int] = None,
        keyword: Optional[str] = None
    ) -> List[dict]:
        """매핑 목록"""
        mappings = await self.uow.mappings.get_mappings(tag_id, keyword)
        return [m.model_dump() for m in mappings]

    async def create_mapping(
        self,
        keyword: str,
        tag_id: int,
        is_auto: bool = False
    ) -> dict:
        """매핑 생성"""
        result = await self.uow.mappings.upsert_mapping(keyword, tag_id, is_auto)
        return result.model_dump() if result else None

    async def delete_mapping(self, mapping_id: int) -> bool:
        """매핑 삭제"""
        return await self.uow.mappings.delete(mapping_id)

    async def get_unmapped_keywords(self, limit: int = 100) -> List[dict]:
        """매핑 안된 키워드"""
        return await self.uow.mappings.get_unmapped_keywords(limit)

    async def bulk_create_mappings(self, mappings: List[dict]) -> int:
        """매핑 일괄 생성"""
        return await self.uow.mappings.bulk_create(mappings)

    # ============================================================
    # 지점별 태그
    # ============================================================

    async def get_branch_tags(
        self,
        branch_id: int,
        period_type: str = 'all',
        limit: int = 10
    ) -> List[dict]:
        """지점별 태그"""
        tags = await self.uow.branch_tags.get_by_branch(branch_id, period_type, limit)
        return [t.model_dump() for t in tags]

    async def get_batch_tags(self, branch_ids: List[int]) -> dict:
        """여러 지점 태그 일괄 조회"""
        if not branch_ids:
            return {}
        return await self.uow.branch_tags.get_batch_top_tags(branch_ids)

    # ============================================================
    # 태그 분석
    # ============================================================

    async def analyze_tags(self, review_text: str) -> dict:
        """리뷰 텍스트 태그 분석"""
        def analyze():
            from analysis import KeywordExtractor
            extractor = KeywordExtractor()
            keywords = extractor.extract(review_text)

            from analysis import EmbeddingTagClassifier
            classifier = EmbeddingTagClassifier()

            results = []
            tag_groups = {}

            for kw in keywords:
                tag, score, sentiment = classifier.classify_with_sentiment(kw, context=review_text)
                results.append({
                    'keyword': kw,
                    'tag': tag,
                    'sentiment': sentiment,
                    'score': score
                })

                if tag not in tag_groups:
                    tag_groups[tag] = {'positive': [], 'negative': [], 'neutral': []}
                tag_groups[tag][sentiment].append(kw)

            return {
                'keywords': [{'keyword': r['keyword'], 'sentiment': r['sentiment']} for r in results],
                'tag_groups': tag_groups
            }

        return await asyncio.to_thread(analyze)
