"""
태그/카테고리/매핑 Repository
"""
from typing import Optional, List
from models.tag import Tag, Category, KeywordMapping
from .base import BaseRepository


class TagRepository(BaseRepository[Tag]):
    """tags 테이블 Repository"""

    model = Tag

    @property
    def table_name(self) -> str:
        return "tags"

    async def get_all_with_filters(
        self,
        category_id: Optional[int] = None,
        sentiment: Optional[str] = None,
        group_name: Optional[str] = None,
        is_active: bool = True
    ) -> List[Tag]:
        """필터링된 태그 목록"""
        query = self._client.table(self.table_name).select('*')

        if group_name:
            query = query.eq('group_name', group_name)
        elif category_id is not None:
            query = self._client.table(self.table_name) \
                .select('*, categories(id, name, color)')
            query = query.eq('category_id', category_id)
        if sentiment:
            query = query.eq('sentiment', sentiment)
        if is_active is not None:
            query = query.eq('is_active', is_active)

        result = await query.order('name').execute()
        return [self.model(**row) for row in result.data]

    async def get_by_name(self, name: str) -> Optional[Tag]:
        """이름으로 조회"""
        result = await self._client.table(self.table_name) \
            .select('*').eq('name', name).execute()
        return self.model(**result.data[0]) if result.data else None

    async def get_with_category(self, tag_id: int) -> Optional[Tag]:
        """카테고리 정보와 함께 조회"""
        result = await self._client.table(self.table_name) \
            .select('*, categories(id, name, color)').eq('id', tag_id).single().execute()
        return self.model(**result.data) if result.data else None

    async def get_or_create(
        self,
        name: str,
        category_id: Optional[int] = None,
        sentiment: str = 'positive'
    ) -> Tag:
        """조회 또는 생성"""
        existing = await self.get_by_name(name)
        if existing:
            return existing

        result = await self._client.table(self.table_name).insert({
            'name': name,
            'category_id': category_id,
            'sentiment': sentiment
        }).execute()
        return self.model(**result.data[0])

    async def get_groups(self) -> List[dict]:
        """고유 그룹 목록"""
        tags = await self.get_all_with_filters()
        groups = {}
        for tag in tags:
            gname = tag.group_name or '기타'
            if gname not in groups:
                groups[gname] = {
                    'group_name': gname,
                    'color': tag.color or '#667eea',
                    'count': 0
                }
            groups[gname]['count'] += 1
        return list(groups.values())


class CategoryRepository(BaseRepository[Category]):
    """categories 테이블 Repository"""

    model = Category

    @property
    def table_name(self) -> str:
        return "categories"

    async def get_all_active(self, is_active: bool = True) -> List[Category]:
        """활성 카테고리 목록"""
        query = self._client.table(self.table_name).select('*')
        if is_active is not None:
            query = query.eq('is_active', is_active)
        result = await query.order('display_order').execute()
        return [self.model(**row) for row in result.data]

    async def delete_with_tags(self, category_id: int) -> bool:
        """카테고리 삭제 (소속 태그는 미분류로)"""
        # 소속 태그의 category_id를 null로
        await self._client.table('tags') \
            .update({'category_id': None}).eq('category_id', category_id).execute()
        # 카테고리 삭제
        result = await self._client.table(self.table_name) \
            .delete().eq('id', category_id).execute()
        return len(result.data) > 0 if result.data else False


class MappingRepository(BaseRepository[KeywordMapping]):
    """keyword_tag_mappings 테이블 Repository"""

    model = KeywordMapping

    @property
    def table_name(self) -> str:
        return "keyword_tag_mappings"

    async def get_mappings(
        self,
        tag_id: Optional[int] = None,
        keyword: Optional[str] = None
    ) -> List[KeywordMapping]:
        """매핑 목록 조회"""
        query = self._client.table(self.table_name) \
            .select('*, tags(id, name, category_id, sentiment)')

        if tag_id is not None:
            query = query.eq('tag_id', tag_id)
        if keyword:
            query = query.eq('keyword', keyword)

        result = await query.order('keyword').execute()
        return [self.model(**row) for row in result.data]

    async def upsert_mapping(
        self,
        keyword: str,
        tag_id: int,
        is_auto: bool = True,
        confidence: float = 1.0
    ) -> Optional[KeywordMapping]:
        """매핑 생성/업데이트"""
        result = await self._client.table(self.table_name).upsert({
            'keyword': keyword,
            'tag_id': tag_id,
            'is_auto': is_auto,
            'confidence': confidence
        }, on_conflict='keyword,tag_id').execute()
        return self.model(**result.data[0]) if result.data else None

    async def delete_by_keyword(self, keyword: str, tag_id: int) -> bool:
        """키워드와 태그 ID로 삭제"""
        result = await self._client.table(self.table_name) \
            .delete().eq('keyword', keyword).eq('tag_id', tag_id).execute()
        return len(result.data) > 0 if result.data else False

    async def get_unmapped_keywords(self, limit: int = 100) -> List[dict]:
        """매핑되지 않은 키워드 목록"""
        # 모든 키워드 조회
        all_keywords_result = await self._client.table('branch_keywords') \
            .select('keyword').execute()
        all_keywords = set(
            row['keyword'] for row in all_keywords_result.data
        ) if all_keywords_result.data else set()

        # 매핑된 키워드 조회
        mapped_result = await self._client.table(self.table_name) \
            .select('keyword').execute()
        mapped_keywords = set(
            row['keyword'] for row in mapped_result.data
        ) if mapped_result.data else set()

        # 차집합
        unmapped = all_keywords - mapped_keywords

        result = []
        for kw in list(unmapped)[:limit]:
            count_result = await self._client.table('branch_keywords') \
                .select('id', count='exact').eq('keyword', kw).execute()
            result.append({
                'keyword': kw,
                'count': count_result.count or 0
            })

        result.sort(key=lambda x: x['count'], reverse=True)
        return result

    async def bulk_create(self, mappings: List[dict]) -> int:
        """일괄 생성"""
        success_count = 0
        for mapping in mappings:
            try:
                await self._client.table(self.table_name).upsert({
                    'keyword': mapping['keyword'],
                    'tag_id': mapping['tag_id'],
                    'is_auto': mapping.get('is_auto', True),
                    'confidence': mapping.get('confidence', 1.0)
                }, on_conflict='keyword,tag_id').execute()
                success_count += 1
            except Exception:
                pass
        return success_count
