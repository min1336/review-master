from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from models.review import Review
from schemas.dto import BranchReviewsDTO

from .base import BaseRepository
from .session import execute_with_retry

logger = logging.getLogger(__name__)


class BranchReviewRepository(BaseRepository[Review]):
    """branch_reviews 테이블 Repository (원본 리뷰)"""

    model = Review

    @property
    def table_name(self) -> str:
        return "branch_reviews"

    async def upsert_batch(self, reviews: list[dict], batch_size: int = 100) -> int:
        """원본 리뷰 일괄 저장 (DB 함수 upsert_reviews 사용)"""
        success_count = 0
        total = len(reviews)

        for i in range(0, total, batch_size):
            batch = reviews[i : i + batch_size]
            try:
                insert_data = []
                for r in batch:
                    rating_svc = r.get("rating_service") or r.get(
                        "지점평점(친절/편의성)"
                    )
                    rating_conv = r.get("rating_convenience") or r.get(
                        "인수/반납편의성"
                    )
                    data = {
                        "review_id": r.get("review_id") or r.get("리뷰번호"),
                        "branch_id": r.get("branch_id") or r.get("지점번호"),
                        "branch_name": r.get("branch_name") or r.get("예약_지점명"),
                        "company_name": r.get("company_name")
                        or r.get("예약_업체명"),
                        "content": None,  # Athena에서 실시간 조회 (이중 저장 제거)
                        "rating_service": rating_svc,
                        "rating_car": r.get("rating_car") or r.get("차량평점"),
                        "rating_convenience": rating_conv,
                        "review_date": r.get("review_date") or r.get("등록일시"),
                        "car_model": r.get("car_model") or r.get("차량모델"),
                        "rent_type": r.get("rent_type") or r.get("렌트타입"),
                        "is_new": r.get("is_new", False),
                    }
                    insert_data.append(data)

                # json.dumps→loads로 datetime 직렬화 후 list로 전달
                # 이중 직렬화 방지: 문자열 대신 list 전달 시 JSONB 배열로 올바르게 전송
                safe_data = json.loads(json.dumps(insert_data, default=str))
                result = await self._client.rpc(
                    "upsert_reviews",
                    {"p_reviews": safe_data},
                ).execute()

                count = result.data if isinstance(result.data, int) else len(batch)
                success_count += count
            except Exception as e:
                logger.warning(f"Failed to upsert branch reviews batch: {e}")

        return success_count

    async def get_by_branch(
        self,
        branch_id: int | None = None,
        car_model: str | None = None,
        sentiment: str | None = None,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> BranchReviewsDTO:
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
            BranchReviewsDTO: 리뷰 목록, 전체 개수, 차량 모델 목록
        """
        query = self._client.table(self.table_name).select("*", count="exact")

        # 기본 필터
        if branch_id:
            query = query.eq("branch_id", branch_id)
        if car_model:
            query = query.eq("car_model", car_model)
        if sentiment:
            query = query.eq("sentiment", sentiment)

        # 날짜 범위 필터
        if review_date_from:
            query = query.gte("review_date", review_date_from.isoformat())
        if review_date_to:
            # 종료일 전체를 포함하기 위해 다음날 00:00:00 미만으로 비교
            next_day = review_date_to + timedelta(days=1)
            query = query.lt("review_date", next_day.isoformat())

        query = query.order("review_date", desc=True).range(offset, offset + limit - 1)
        result = await execute_with_retry(query)

        # 차량 모델 목록 조회 (distinct)
        car_models = []
        if branch_id:
            car_query = (
                await self._client.table(self.table_name)
                .select("car_model")
                .eq("branch_id", branch_id)
                .execute()
            )
            car_models = sorted(
                {r["car_model"] for r in car_query.data if r.get("car_model")}
            )

        return BranchReviewsDTO(
            reviews=result.data,
            total=result.count or 0,
            car_models=car_models,
        )

    async def get_distinct_car_models(self, branch_id: int) -> list[str]:
        """지점의 고유 차량 모델 목록 조회"""
        result = (
            await self._client.table(self.table_name)
            .select("car_model")
            .eq("branch_id", branch_id)
            .execute()
        )
        return sorted({r["car_model"] for r in result.data if r.get("car_model")})

    async def count_by_branch(
        self,
        branch_id: int,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> int:
        """기간별 리뷰 수 카운트 (head=True로 데이터 전송 없이 count만 조회)"""
        query = (
            self._client.table(self.table_name)
            .select("review_id", count="exact", head=True)
            .eq("branch_id", branch_id)
        )
        if review_date_from:
            query = query.gte("review_date", review_date_from.isoformat())
        if review_date_to:
            next_day = review_date_to + timedelta(days=1)
            query = query.lt("review_date", next_day.isoformat())
        result = await execute_with_retry(query)
        return result.count or 0

    async def get_stats(self) -> list[dict]:
        """지점별 리뷰 통계 (RPC로 DB 서버에서 집계)"""
        result = await self._client.rpc("get_review_stats_by_branch").execute()
        return result.data or []

    async def search_with_filters(
        self,
        branch_ids: list[int] | None = None,
        sentiment: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "latest",
        limit: int = 20,
        offset: int = 0,
        is_new: bool | None = None,
    ) -> BranchReviewsDTO:
        """
        다중 필터 조건으로 리뷰 검색

        Args:
            branch_ids: 지점 ID 필터 목록 (인덱스 활용)
            sentiment: 감정 필터
            date_from: 시작일 (YYYY-MM-DD)
            date_to: 종료일 (YYYY-MM-DD)
            sort_by: 정렬 기준 (latest, rating_low)
            limit: 조회 개수
            offset: 페이징 오프셋

        Returns:
            BranchReviewsDTO: 리뷰 목록과 전체 개수
        """
        query = self._client.table(self.table_name).select("*", count="exact")

        # 지점 ID 필터 (인덱스 활용으로 빠름)
        if branch_ids:
            query = query.in_("branch_id", branch_ids)

        # 감정 필터
        if sentiment:
            query = query.eq("sentiment", sentiment)

        # 신규 리뷰 필터
        if is_new is not None:
            query = query.eq("is_new", is_new)

        # 날짜 범위 필터
        if date_from:
            query = query.gte("review_date", date_from)
        if date_to:
            # 종료일 전체를 포함하기 위해 다음날 00:00:00 미만으로 비교
            next_day = (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
            query = query.lt("review_date", next_day)

        # 정렬
        sort_config = {
            "latest": ("review_date", True),
            "rating_low": ("rating_service", False),
        }
        sort_field, desc = sort_config.get(sort_by, ("review_date", True))
        query = query.order(sort_field, desc=desc)

        # 페이징
        query = query.range(offset, offset + limit - 1)

        result = await execute_with_retry(query)

        return BranchReviewsDTO(
            reviews=result.data,
            total=result.count or 0,
        )

    async def get_new_reviews(
        self,
        branch_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BranchReviewsDTO:
        """
        신규 리뷰 조회 (is_new=true)

        Args:
            branch_id: 지점 ID
            limit: 개수
            offset: 오프셋

        Returns:
            BranchReviewsDTO: 리뷰 목록과 개수
        """
        query = (
            self._client.table(self.table_name)
            .select("*", count="exact")
            .eq("is_new", True)
        )

        if branch_id:
            query = query.eq("branch_id", branch_id)

        query = query.order("review_date", desc=True).range(offset, offset + limit - 1)
        result = await execute_with_retry(query)

        return BranchReviewsDTO(
            reviews=result.data,
            total=result.count or 0,
            car_models=[],
        )

    async def get_new_review_count(self, branch_id: int | None = None) -> int:
        """
        신규 리뷰 개수 조회

        Args:
            branch_id: 지점 ID

        Returns:
            신규 리뷰 수
        """
        query = (
            self._client.table(self.table_name)
            .select("review_id", count="exact", head=True)
            .eq("is_new", True)
        )

        if branch_id:
            query = query.eq("branch_id", branch_id)

        result = await execute_with_retry(query)
        return result.count or 0

    async def get_sentiments_by_review_ids(
        self, review_ids: list[int]
    ) -> dict[int, str]:
        """review_id → sentiment 매핑 조회 (Athena 결과 보강용)"""
        if not review_ids:
            return {}

        result = await execute_with_retry(
            self._client.table(self.table_name)
            .select("review_id, sentiment")
            .in_("review_id", review_ids)
        )

        return {
            row["review_id"]: row["sentiment"]
            for row in (result.data or [])
            if row.get("sentiment")
        }

    async def mark_reviews_as_read(self, review_ids: list[int] | None = None) -> int:
        """
        리뷰 읽음 처리 (is_new=false)

        Args:
            review_ids: 대상 리뷰 ID 목록 (None이면 전체)

        Returns:
            수정된 리뷰 수
        """
        if review_ids:
            return await self._batch_mark_read(review_ids)

        # 전체 읽음: ID 조회 후 배치 업데이트 (statement timeout 방지)
        total = 0
        while True:
            id_query = (
                self._client.table(self.table_name)
                .select("review_id")
                .eq("is_new", True)
                .limit(1000)
            )
            id_result = await execute_with_retry(id_query)

            if not id_result.data:
                break

            ids = [row["review_id"] for row in id_result.data]
            total += await self._batch_mark_read(ids)

        return total

    async def _batch_mark_read(self, review_ids: list[int], batch_size: int = 500) -> int:
        """review_id 목록을 배치 단위로 is_new=false 처리"""
        total = 0
        for i in range(0, len(review_ids), batch_size):
            batch = review_ids[i : i + batch_size]
            query = (
                self._client.table(self.table_name)
                .update({"is_new": False})
                .in_("review_id", batch)
            )
            result = await execute_with_retry(query)
            total += len(result.data) if result.data else 0
        return total

    async def delete_by_review_ids(self, review_ids: list[int], batch_size: int = 100) -> int:
        """
        리뷰 ID로 삭제 (soft delete된 리뷰 동기화용)

        Args:
            review_ids: 삭제할 리뷰 ID 목록
            batch_size: 배치 크기

        Returns:
            삭제된 리뷰 수
        """
        if not review_ids:
            return 0

        deleted_count = 0
        for i in range(0, len(review_ids), batch_size):
            batch = review_ids[i : i + batch_size]
            try:
                result = await (
                    self._client.table(self.table_name)
                    .delete()
                    .in_("review_id", batch)
                    .execute()
                )
                deleted_count += len(result.data) if result.data else 0
            except Exception as e:
                logger.warning(f"Failed to delete reviews batch: {e}")

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} reviews (soft deleted in source)")

        return deleted_count

