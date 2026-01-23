"""
리뷰 Repository (recent_reviews, branch_reviews 테이블)

이 모듈은 리뷰 데이터에 대한 CRUD 작업을 담당합니다.
- ReviewRepository: recent_reviews 테이블 (최근 리뷰 캐시)
- BranchReviewRepository: branch_reviews 테이블 (원본 리뷰)
"""
from typing import Optional, List
from datetime import datetime, timedelta
from collections import Counter
from models.review import Review
from .base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    """recent_reviews 테이블 Repository"""

    model = Review

    @property
    def table_name(self) -> str:
        return "recent_reviews"

    async def upsert_recent(self, reviews: List[dict], batch_size: int = 100) -> int:
        """최근 리뷰 저장"""
        success_count = 0
        total = len(reviews)

        for i in range(0, total, batch_size):
            batch = reviews[i:i + batch_size]
            try:
                insert_data = []
                for r in batch:
                    insert_data.append({
                        'branch_id': r.get('branch_id') or r.get('지점번호'),
                        'content': r.get('content') or r.get('리뷰내용'),
                        'sentiment': r.get('sentiment'),
                        'sentiment_score': r.get('sentiment_score'),
                        'review_date': r.get('review_date')
                    })

                await self._client.table(self.table_name).insert(insert_data).execute()
                success_count += len(batch)
            except Exception:
                pass

        return success_count

    async def search(
        self,
        sentiment: Optional[str] = None,
        branch_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict:
        """최근 리뷰 검색"""
        query = self._client.table(self.table_name).select('*', count='exact')

        if sentiment:
            query = query.eq('sentiment', sentiment)
        if branch_id:
            query = query.eq('branch_id', branch_id)

        query = query.order('created_at', desc=True).range(offset, offset + limit - 1)
        result = await query.execute()

        return {
            'reviews': result.data,
            'total': result.count or 0
        }

    async def cleanup_old(self, days: int = 30) -> int:
        """오래된 리뷰 삭제"""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        result = await self._client.table(self.table_name) \
            .delete().lt('created_at', cutoff_date).execute()
        return len(result.data) if result.data else 0

    async def cleanup_excess_per_branch(self, max_per_branch: int = 30) -> int:
        """지점당 리뷰 수 제한"""
        deleted_count = 0

        branches_result = await self._client.table(self.table_name) \
            .select('branch_id').execute()
        if not branches_result.data:
            return 0

        branch_ids = list(set(
            r['branch_id'] for r in branches_result.data if r.get('branch_id')
        ))

        for branch_id in branch_ids:
            reviews = await self._client.table(self.table_name) \
                .select('id').eq('branch_id', branch_id) \
                .order('created_at', desc=True).execute()

            if reviews.data and len(reviews.data) > max_per_branch:
                ids_to_delete = [r['id'] for r in reviews.data[max_per_branch:]]
                for review_id in ids_to_delete:
                    await self._client.table(self.table_name) \
                        .delete().eq('id', review_id).execute()
                    deleted_count += 1

        return deleted_count

    async def cleanup(self, days: int = 30, max_per_branch: int = 30) -> dict:
        """리뷰 정리 (오래된 삭제 + 지점당 제한)"""
        old_deleted = await self.cleanup_old(days)
        excess_deleted = await self.cleanup_excess_per_branch(max_per_branch)

        return {
            'old_deleted': old_deleted,
            'excess_deleted': excess_deleted,
            'total': old_deleted + excess_deleted
        }


class BranchReviewRepository(BaseRepository[Review]):
    """branch_reviews 테이블 Repository (원본 리뷰)"""

    model = Review

    @property
    def table_name(self) -> str:
        return "branch_reviews"

    async def upsert_batch(self, reviews: List[dict], batch_size: int = 1000) -> int:
        """원본 리뷰 일괄 저장"""
        success_count = 0
        total = len(reviews)

        for i in range(0, total, batch_size):
            batch = reviews[i:i + batch_size]
            try:
                insert_data = []
                for r in batch:
                    insert_data.append({
                        'review_id': r.get('review_id') or r.get('리뷰번호'),
                        'branch_id': r.get('branch_id') or r.get('지점번호'),
                        'branch_name': r.get('branch_name') or r.get('예약_지점명'),
                        'company_name': r.get('company_name') or r.get('예약_업체명'),
                        'content': r.get('content') or r.get('리뷰내용'),
                        'rating_service': r.get('rating_service') or r.get('지점평점(친절/편의성)'),
                        'rating_car': r.get('rating_car') or r.get('차량평점'),
                        'rating_convenience': r.get('rating_convenience') or r.get('인수/반납편의성'),
                        'review_date': r.get('review_date') or r.get('등록일시'),
                        'car_model': r.get('car_model') or r.get('차량모델'),
                        'rent_type': r.get('rent_type') or r.get('렌트타입'),
                        'sentiment': r.get('sentiment')  # 감정 (positive, neutral, negative)
                    })

                await self._client.table(self.table_name) \
                    .upsert(insert_data, on_conflict='review_id').execute()
                success_count += len(batch)
            except Exception:
                pass

        return success_count

    async def get_by_branch(
        self,
        branch_id: Optional[int] = None,
        car_model: Optional[str] = None,
        sentiment: Optional[str] = None,
        review_date_from: Optional[datetime] = None,
        review_date_to: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict:
        """
        원본 리뷰 조회 (필터링 지원)

        Args:
            branch_id: 지점 ID
            car_model: 차량 모델 필터
            sentiment: 감정 필터 (positive, neutral, negative)
            review_date_from: 시작일 (이 날짜 이후 리뷰만 조회)
            review_date_to: 종료일 (이 날짜 이전 리뷰만 조회)
            limit: 조회 개수 (기본 100)
            offset: 페이징 오프셋

        Returns:
            dict: {
                reviews: list - 리뷰 목록,
                total: int - 전체 개수,
                car_models: list - 차량 모델 목록
            }
        """
        query = self._client.table(self.table_name).select('*', count='exact')

        # 기본 필터
        if branch_id:
            query = query.eq('branch_id', branch_id)
        if car_model:
            query = query.eq('car_model', car_model)
        if sentiment:
            query = query.eq('sentiment', sentiment)

        # 날짜 범위 필터
        if review_date_from:
            query = query.gte('review_date', review_date_from.isoformat())
        if review_date_to:
            query = query.lte('review_date', review_date_to.isoformat())

        query = query.order('review_date', desc=True).range(offset, offset + limit - 1)
        result = await query.execute()

        # 차량 모델 목록 조회 (distinct)
        car_models = []
        if branch_id:
            car_query = await self._client.table(self.table_name) \
                .select('car_model') \
                .eq('branch_id', branch_id) \
                .execute()
            car_models = sorted(set(
                r['car_model'] for r in car_query.data
                if r.get('car_model')
            ))

        return {
            'reviews': result.data,
            'total': result.count or 0,
            'car_models': car_models
        }

    async def get_stats(self) -> List[dict]:
        """지점별 리뷰 통계"""
        result = await self._client.table(self.table_name) \
            .select('branch_id, branch_name').execute()

        if not result.data:
            return []

        branch_counts = Counter()
        branch_names = {}

        for r in result.data:
            bid = r['branch_id']
            branch_counts[bid] += 1
            if bid not in branch_names:
                branch_names[bid] = r['branch_name']

        return [
            {
                'branch_id': bid,
                'branch_name': branch_names.get(bid),
                'review_count': count
            }
            for bid, count in branch_counts.most_common()
        ]
