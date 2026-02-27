"""
태그 Service - 비즈니스 로직
"""

from __future__ import annotations

import asyncio

def _get_classifier():
    from domain.analysis._singletons import get_hybrid_classifier

    return get_hybrid_classifier()


class TagService:
    """태그 비즈니스 로직"""

    def __init__(self, tag_repo, branch_tag_repo, category_repo=None, mapping_repo=None):
        self.tag_repo = tag_repo
        self.branch_tag_repo = branch_tag_repo
        self.category_repo = category_repo
        self.mapping_repo = mapping_repo

    # ============================================================
    # 태그
    # ============================================================

    async def get_tags(
        self,
        category_id: int | None = None,
        sentiment: str | None = None,
        group_name: str | None = None,
        is_active: bool = True,
    ) -> list[dict]:
        """태그 목록"""
        tags = await self.tag_repo.get_all_with_filters(
            category_id=category_id,
            sentiment=sentiment,
            group_name=group_name,
            is_active=is_active,
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

    async def get_batch_tags(
        self, branch_ids: list[int], period_type: str = "all"
    ) -> dict:
        """여러 지점 태그 일괄 조회"""
        if not branch_ids:
            return {}
        return await self.branch_tag_repo.get_batch_top_tags(
            branch_ids, period_type=period_type
        )

    # ============================================================
    # 카테고리
    # ============================================================

    def _require_category_repo(self):
        if self.category_repo is None:
            raise RuntimeError("CategoryRepository가 주입되지 않았습니다")
        return self.category_repo

    def _require_mapping_repo(self):
        if self.mapping_repo is None:
            raise RuntimeError("MappingRepository가 주입되지 않았습니다")
        return self.mapping_repo

    async def get_categories(self, is_active: bool = True) -> list:
        """카테고리 목록"""
        categories = await self._require_category_repo().get_all_active(is_active)
        return [c.model_dump() for c in categories]

    async def get_category(self, category_id: int) -> dict | None:
        """카테고리 상세"""
        category = await self._require_category_repo().get(category_id)
        return category.model_dump() if category else None

    async def create_category(self, data: dict) -> dict | None:
        """카테고리 생성"""
        result = await self._require_category_repo().create_dict(data)
        return result.model_dump() if result else None

    async def update_category(self, category_id: int, data: dict) -> dict | None:
        """카테고리 수정"""
        result = await self._require_category_repo().update(category_id, data)
        return result.model_dump() if result else None

    async def delete_category(self, category_id: int) -> bool:
        """카테고리 삭제"""
        return await self._require_category_repo().delete_with_tags(category_id)

    # ============================================================
    # 키워드 매핑
    # ============================================================

    async def get_mappings(
        self, tag_id: int | None = None, keyword: str | None = None
    ) -> list:
        """매핑 목록"""
        repo = self._require_mapping_repo()
        mappings = await repo.get_mappings(tag_id=tag_id, keyword=keyword)
        return [m.model_dump() for m in mappings]

    async def create_mapping(
        self, keyword: str, tag_id: int, is_auto: bool = False
    ) -> dict | None:
        """매핑 생성"""
        result = await self._require_mapping_repo().upsert_mapping(keyword, tag_id, is_auto)
        return result.model_dump() if result else None

    async def delete_mapping(self, mapping_id: int) -> bool:
        """매핑 삭제"""
        return await self._require_mapping_repo().delete(mapping_id)

    async def get_unmapped_keywords(self, limit: int = 100) -> list[dict]:
        """매핑되지 않은 키워드 목록"""
        return await self._require_mapping_repo().get_unmapped_keywords(limit=limit)

    async def bulk_create_mappings(self, mappings: list[dict]) -> int:
        """매핑 일괄 생성"""
        return await self._require_mapping_repo().bulk_create(mappings)

    async def auto_map_keywords(self, limit: int = 500) -> dict:
        """매핑되지 않은 키워드 자동 매핑 (HybridClassifier 사용)

        분류기 출력이 태그명이면 직접 매핑, 카테고리명이면 대표 태그로 매핑.
        """
        import logging

        from domain.analysis.patterns import CATEGORY_DEFAULT_TAG

        logger = logging.getLogger(__name__)
        repo = self._require_mapping_repo()

        # 1. 미매핑 키워드 조회
        unmapped = await repo.get_unmapped_keywords(limit=limit)
        if not unmapped:
            return {"mapped": 0, "skipped": 0, "errors": []}

        # 2. DB 태그 목록 → 이름→id 룩업 테이블
        all_tags = await self.tag_repo.get_all_with_filters(is_active=True)
        tag_name_to_id: dict[str, int] = {t.name: t.id for t in all_tags}

        # 3. HybridClassifier로 분류 (CPU-bound)
        keywords = [item["keyword"] for item in unmapped]

        def classify():
            classifier = _get_classifier()
            return classifier.classify_keywords(keywords)

        classifications = await asyncio.to_thread(classify)

        # 4. 매핑 생성
        result: dict = {"mapped": 0, "skipped": 0, "errors": []}
        for item, (tag_group, _score, _sentiment) in zip(
            unmapped, classifications, strict=False
        ):
            keyword = item["keyword"]
            try:
                if tag_group == "기타":
                    result["skipped"] += 1
                    continue

                # 태그명 직접 매칭 시도
                tag_id = tag_name_to_id.get(tag_group)

                # 카테고리명이면 대표 태그로 fallback
                if not tag_id:
                    default_tag = CATEGORY_DEFAULT_TAG.get(tag_group)
                    if default_tag:
                        tag_id = tag_name_to_id.get(default_tag)

                if tag_id:
                    await repo.upsert_mapping(keyword, tag_id, is_auto=True)
                    result["mapped"] += 1
                else:
                    result["skipped"] += 1
            except Exception as e:
                logger.warning("auto_map_keywords error for '%s': %s", keyword, e)
                result["errors"].append(f"{keyword}: {str(e)}")

        return result
