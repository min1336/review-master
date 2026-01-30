"""리뷰 동기화 서비스"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from infrastructure.athena import AthenaClient
from repository.review_repository import BranchReviewRepository
from repository.session import get_client
from schemas.sync import SyncResultResponse, SyncStatusResponse

logger = logging.getLogger(__name__)


class SyncService:
    """리뷰 동기화 서비스"""

    def __init__(
        self,
        review_repo: BranchReviewRepository,
        athena_client: AthenaClient | None = None,
    ) -> None:
        self._review_repo = review_repo
        self._athena_client = athena_client

    async def get_athena_sync_status(self) -> SyncStatusResponse:
        """동기화 상태 조회"""
        client = await get_client()

        # 마지막 동기화 시간 조회
        last_sync_at = None
        synced_count = 0
        try:
            result = await client.table("athena_sync_status").select("*").eq(
                "sync_type", "athena_reviews"
            ).single().execute()
            if result.data:
                if result.data.get("last_sync_at"):
                    last_sync_at = datetime.fromisoformat(
                        result.data["last_sync_at"].replace("Z", "+00:00")
                    )
                synced_count = result.data.get("synced_count", 0)
        except Exception:
            pass

        # 신규 리뷰 수만 조회 (is_new=true인 것만, 인덱스 활용)
        new_reviews = 0
        try:
            new_result = await client.table("branch_reviews").select(
                "id", count="exact"
            ).eq("is_new", True).limit(1).execute()
            new_reviews = new_result.count or 0
        except Exception:
            pass

        return SyncStatusResponse(
            last_sync_at=last_sync_at,
            total_reviews=synced_count,  # 전체 대신 마지막 동기화 수
            new_reviews=new_reviews,
        )

    async def sync_reviews(self) -> SyncResultResponse:
        """Athena에서 신규 리뷰 동기화"""
        start_time = datetime.now()

        if not self._athena_client:
            return SyncResultResponse(
                success=False,
                message="Athena 클라이언트가 설정되지 않았습니다",
                error="athena_client_not_configured",
            )

        try:
            client = await get_client()

            # 마지막 동기화 시간 조회
            try:
                result = await client.table("athena_sync_status").select("*").eq(
                    "sync_type", "athena_reviews"
                ).single().execute()
                last_sync_at = (
                    datetime.fromisoformat(result.data["last_sync_at"])
                    if result.data
                    else None
                )
            except Exception:
                last_sync_at = None

            # 기본값: 7일 전부터
            if not last_sync_at:
                last_sync_at = datetime.now() - timedelta(days=7)

            logger.info(f"동기화 시작: {last_sync_at} 이후 리뷰 조회")
            print(f"[DEBUG] 동기화 시작: {last_sync_at} 이후 리뷰 조회")

            # Athena에서 리뷰 조회
            athena_reviews = self._athena_client.fetch_reviews_since(last_sync_at)
            print(f"[DEBUG] Athena 조회 결과: {len(athena_reviews)}개")
            if athena_reviews:
                print(f"[DEBUG] 첫 번째 리뷰: {athena_reviews[0]}")

            if not athena_reviews:
                return SyncResultResponse(
                    success=True,
                    message="동기화할 신규 리뷰가 없습니다",
                    synced_count=0,
                    new_reviews=0,
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                )

            # DB 저장용 데이터 변환 (중복 review_id 제거)
            seen_ids = set()
            reviews_to_save = []
            for row in athena_reviews:
                review_id = row.get("review_id")
                if review_id in seen_ids:
                    continue
                seen_ids.add(review_id)
                reviews_to_save.append({
                    "review_id": row.get("review_id"),
                    "branch_id": row.get("branch_id"),
                    "branch_name": row.get("branch_name"),
                    "company_name": row.get("company_name"),
                    "content": row.get("content"),
                    "rating_service": self._parse_float(row.get("rating_service")),
                    "rating_car": self._parse_float(row.get("rating_car")),
                    "rating_convenience": self._parse_float(row.get("rating_convenience")),
                    "review_date": row.get("review_date"),
                    "car_model": row.get("car_type"),
                    "rent_type": row.get("rent_type"),
                    "is_new": True,  # 신규 표시
                })

            # DB에 저장
            saved_count = await self._review_repo.upsert_batch(reviews_to_save)

            # 동기화 시간 업데이트
            await client.table("athena_sync_status").upsert({
                "sync_type": "athena_reviews",
                "last_sync_at": datetime.now().isoformat(),
                "synced_count": saved_count,
            }, on_conflict="sync_type").execute()

            duration = (datetime.now() - start_time).total_seconds()

            logger.info(f"동기화 완료: {saved_count}개 리뷰 저장 ({duration:.1f}초)")

            return SyncResultResponse(
                success=True,
                message=f"{saved_count}개 리뷰가 동기화되었습니다",
                synced_count=saved_count,
                new_reviews=saved_count,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"동기화 실패: {e}")
            return SyncResultResponse(
                success=False,
                message="동기화 중 오류가 발생했습니다",
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    async def mark_reviews_as_read(
        self, review_ids: list[int] | None = None
    ) -> int:
        """리뷰 읽음 처리"""
        client = await get_client()

        try:
            if review_ids:
                # 특정 리뷰만 읽음 처리
                result = await client.table("branch_reviews").update({
                    "is_new": False
                }).in_("id", review_ids).execute()
            else:
                # 전체 읽음 처리
                result = await client.table("branch_reviews").update({
                    "is_new": False
                }).eq("is_new", True).execute()

            return len(result.data) if result.data else 0

        except Exception as e:
            logger.error(f"읽음 처리 실패: {e}")
            return 0

    def _parse_float(self, value: str | None) -> float | None:
        """문자열을 float로 변환"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
