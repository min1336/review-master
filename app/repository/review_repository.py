from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.review import Review
from schemas.dto import BranchReviewsDTO

from .base import BaseRepository
from .orm_models import BranchReviewORM

logger = logging.getLogger(__name__)


class BranchReviewRepository(BaseRepository[Review]):
    """branch_reviews 테이블 Repository (원본 리뷰)"""

    model = Review
    orm_model = BranchReviewORM

    @property
    def table_name(self) -> str:
        return "branch_reviews"

    @staticmethod
    def _safe_int(val: str | int | None) -> int | None:
        """asyncpg strict typing 대응: 문자열 → int 변환"""
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val: str | float | None) -> float | None:
        """asyncpg strict typing 대응: 문자열 → float 변환"""
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_datetime(val: str | datetime | None) -> datetime | None:
        """asyncpg strict typing 대응: 문자열 → datetime 변환"""
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        try:
            from dateutil.parser import parse
            return parse(val)
        except (ValueError, TypeError):
            return None

    async def count_existing_review_ids(self, review_ids: list[int]) -> int:
        """주어진 review_id 목록 중 DB에 활성 상태로 존재하는 건수 반환

        soft-deleted(deleted_at IS NOT NULL) 행은 제외한다.
        upsert가 deleted_at=None으로 복원하므로, 복원 건은 신규로 카운트해야 한다.
        """
        if not review_ids:
            return 0
        stmt = (
            select(func.count())
            .select_from(BranchReviewORM)
            .where(
                BranchReviewORM.review_id.in_(review_ids),
                BranchReviewORM.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def upsert_batch(self, reviews: list[dict], batch_size: int = 100) -> int:
        """원본 리뷰 일괄 저장 (SQLAlchemy ON CONFLICT upsert)"""
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
                        "review_id": self._safe_int(
                            r.get("review_id") or r.get("리뷰번호")
                        ),
                        "branch_id": self._safe_int(
                            r.get("branch_id") or r.get("지점번호")
                        ),
                        "branch_name": r.get("branch_name") or r.get("예약_지점명"),
                        "company_name": r.get("company_name")
                        or r.get("예약_업체명"),
                        "content": r.get("content") or r.get("리뷰내용"),
                        "rating_service": self._safe_float(rating_svc),
                        "rating_car": self._safe_float(
                            r.get("rating_car") or r.get("차량평점")
                        ),
                        "rating_convenience": self._safe_float(rating_conv),
                        "review_date": self._safe_datetime(
                            r.get("review_date") or r.get("등록일시")
                        ),
                        "car_model": r.get("car_model") or r.get("차량모델") or r.get("car_type") or r.get("차종"),
                        "rent_type": r.get("rent_type") or r.get("렌트타입"),
                        "is_new": r.get("is_new", False),
                    }
                    insert_data.append(data)

                stmt = pg_insert(BranchReviewORM).values(insert_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["review_id"],
                    set_={
                        "branch_name": stmt.excluded.branch_name,
                        "company_name": stmt.excluded.company_name,
                        "content": stmt.excluded.content,
                        "rating_service": stmt.excluded.rating_service,
                        "rating_car": stmt.excluded.rating_car,
                        "rating_convenience": stmt.excluded.rating_convenience,
                        "review_date": stmt.excluded.review_date,
                        "car_model": stmt.excluded.car_model,
                        "rent_type": stmt.excluded.rent_type,
                        "updated_at": func.now(),
                        "deleted_at": None,
                    },
                )
                await self._session.execute(stmt)
                success_count += len(batch)
            except Exception as e:
                logger.warning("Failed to upsert branch reviews batch: %s", e)

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
        """원본 리뷰 조회 (필터링 지원)"""
        conditions = []

        if branch_id:
            conditions.append(BranchReviewORM.branch_id == branch_id)
        if car_model:
            conditions.append(BranchReviewORM.car_model == car_model)
        if sentiment:
            conditions.append(BranchReviewORM.sentiment == sentiment)
        if review_date_from:
            conditions.append(BranchReviewORM.review_date >= review_date_from)
        if review_date_to:
            # 종료일 전체를 포함하기 위해 다음날 00:00:00 미만으로 비교
            next_day = review_date_to + timedelta(days=1)
            conditions.append(BranchReviewORM.review_date < next_day)

        # 데이터 쿼리
        data_stmt = (
            select(BranchReviewORM)
            .where(*conditions)
            .order_by(BranchReviewORM.review_date.desc())
            .offset(offset)
            .limit(limit)
        )
        data_result = await self._session.execute(data_stmt)
        rows = data_result.scalars().all()
        reviews = [self._to_dict(row) for row in rows]

        # 카운트 쿼리
        count_stmt = (
            select(func.count())
            .select_from(BranchReviewORM)
            .where(*conditions)
        )
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        # 차량 모델 목록 조회 (distinct)
        car_models: list[str] = []
        if branch_id:
            car_stmt = (
                select(BranchReviewORM.car_model)
                .where(BranchReviewORM.branch_id == branch_id)
                .distinct()
            )
            car_result = await self._session.execute(car_stmt)
            car_models = sorted(
                {m for m in car_result.scalars().all() if m is not None}
            )

        return BranchReviewsDTO(
            reviews=reviews,
            total=total,
            car_models=car_models,
        )

    async def get_distinct_car_models(self, branch_id: int) -> list[str]:
        """지점의 고유 차량 모델 목록 조회"""
        stmt = (
            select(BranchReviewORM.car_model)
            .where(BranchReviewORM.branch_id == branch_id)
            .distinct()
        )
        result = await self._session.execute(stmt)
        return sorted({m for m in result.scalars().all() if m is not None})

    async def count_by_branch(
        self,
        branch_id: int,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> int:
        """기간별 리뷰 수 카운트"""
        stmt = (
            select(func.count())
            .select_from(BranchReviewORM)
            .where(BranchReviewORM.branch_id == branch_id)
        )
        if review_date_from:
            stmt = stmt.where(BranchReviewORM.review_date >= review_date_from)
        if review_date_to:
            next_day = review_date_to + timedelta(days=1)
            stmt = stmt.where(BranchReviewORM.review_date < next_day)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_tagged_reviews(
        self,
        branch_id: int,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> int:
        """태그가 1개 이상 매핑된 리뷰 수 카운트 (신뢰도 표기용)"""
        from .orm_models import ReviewTagMappingORM

        subq = (
            select(ReviewTagMappingORM.review_id)
            .join(BranchReviewORM, BranchReviewORM.review_id == ReviewTagMappingORM.review_id)
            .where(BranchReviewORM.branch_id == branch_id)
            .where(BranchReviewORM.deleted_at.is_(None))
        )
        if review_date_from:
            subq = subq.where(BranchReviewORM.review_date >= review_date_from)
        if review_date_to:
            next_day = review_date_to + timedelta(days=1)
            subq = subq.where(BranchReviewORM.review_date < next_day)

        subq = subq.distinct().subquery()
        stmt = select(func.count()).select_from(subq)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_negative_reviews(
        self,
        branch_id: int,
        review_date_from: datetime | None = None,
        review_date_to: datetime | None = None,
    ) -> list[dict]:
        """부정 리뷰 조회 (리포트 하단 나열용) — 3점 이하 OR sentiment=negative, 전건"""
        conditions = [
            BranchReviewORM.branch_id == branch_id,
            or_(
                BranchReviewORM.sentiment == "negative",
                BranchReviewORM.rating_service <= 3,
                BranchReviewORM.rating_car <= 3,
                BranchReviewORM.rating_convenience <= 3,
            ),
            BranchReviewORM.content.isnot(None),
            BranchReviewORM.content != "",
            BranchReviewORM.deleted_at.is_(None),
        ]
        if review_date_from:
            conditions.append(BranchReviewORM.review_date >= review_date_from)
        if review_date_to:
            next_day = review_date_to + timedelta(days=1)
            conditions.append(BranchReviewORM.review_date < next_day)

        stmt = (
            select(
                BranchReviewORM.content,
                BranchReviewORM.rating_service,
                BranchReviewORM.review_date,
                BranchReviewORM.car_model,
            )
            .where(*conditions)
            .order_by(BranchReviewORM.review_date.desc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "content": row.content or "",
                "rating": float(row.rating_service) if row.rating_service else 0.0,
                "review_date": row.review_date.strftime("%Y-%m-%d") if row.review_date else "",
                "vehicle_model": row.car_model or "",
            }
            for row in result.all()
        ]

    async def get_stats(self) -> list[dict]:
        """지점별 리뷰 통계 (RPC로 DB 서버에서 집계)"""
        result = await self._session.execute(
            text("SELECT * FROM get_review_stats_by_branch()")
        )
        return [dict(row._mapping) for row in result.all()]

    async def get_branch_company_map(self) -> dict[int, str]:
        """지점별 업체명 매핑 (경량 조회)"""
        result = await self._session.execute(
            text("SELECT * FROM get_branch_company_map()")
        )
        return {
            row._mapping["branch_id"]: row._mapping["company_name"]
            for row in result.all()
        }

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
        """다중 필터 조건으로 리뷰 검색"""
        conditions = []

        # 지점 ID 필터 (인덱스 활용으로 빠름)
        if branch_ids:
            conditions.append(BranchReviewORM.branch_id.in_(branch_ids))

        # 감정 필터
        if sentiment:
            conditions.append(BranchReviewORM.sentiment == sentiment)

        # 신규 리뷰 필터
        if is_new is not None:
            conditions.append(BranchReviewORM.is_new == is_new)  # noqa: E712

        # 날짜 범위 필터 (asyncpg는 DateTime 컬럼에 문자열 바인딩 불가)
        if date_from:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            conditions.append(BranchReviewORM.review_date >= dt_from)
        if date_to:
            # 종료일 전체를 포함하기 위해 다음날 00:00:00 미만으로 비교
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            conditions.append(BranchReviewORM.review_date < dt_to)

        # 정렬
        sort_config = {
            "latest": BranchReviewORM.review_date.desc(),
            "rating_low": BranchReviewORM.rating_service.asc(),
        }
        order_clause = sort_config.get(
            sort_by, BranchReviewORM.review_date.desc()
        )

        # 데이터 쿼리
        data_stmt = (
            select(BranchReviewORM)
            .where(*conditions)
            .order_by(order_clause)
            .offset(offset)
            .limit(limit)
        )
        data_result = await self._session.execute(data_stmt)
        rows = data_result.scalars().all()
        reviews = [self._to_dict(row) for row in rows]

        # 카운트 쿼리
        count_stmt = (
            select(func.count())
            .select_from(BranchReviewORM)
            .where(*conditions)
        )
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        return BranchReviewsDTO(
            reviews=reviews,
            total=total,
        )

    async def get_new_reviews(
        self,
        branch_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> BranchReviewsDTO:
        """신규 리뷰 조회 (is_new=true)"""
        conditions = [BranchReviewORM.is_new == True]  # noqa: E712

        if branch_id:
            conditions.append(BranchReviewORM.branch_id == branch_id)

        # 데이터 쿼리
        data_stmt = (
            select(BranchReviewORM)
            .where(*conditions)
            .order_by(BranchReviewORM.review_date.desc())
            .offset(offset)
            .limit(limit)
        )
        data_result = await self._session.execute(data_stmt)
        rows = data_result.scalars().all()
        reviews = [self._to_dict(row) for row in rows]

        # 카운트 쿼리
        count_stmt = (
            select(func.count())
            .select_from(BranchReviewORM)
            .where(*conditions)
        )
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        return BranchReviewsDTO(
            reviews=reviews,
            total=total,
            car_models=[],
        )

    async def get_new_review_count(self, branch_id: int | None = None) -> int:
        """신규 리뷰 개수 조회"""
        stmt = (
            select(func.count())
            .select_from(BranchReviewORM)
            .where(BranchReviewORM.is_new == True)  # noqa: E712
        )

        if branch_id:
            stmt = stmt.where(BranchReviewORM.branch_id == branch_id)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_sentiments_by_review_ids(
        self, review_ids: list[int]
    ) -> dict[int, str]:
        """review_id -> sentiment 매핑 조회 (Athena 결과 보강용)"""
        if not review_ids:
            return {}

        stmt = select(
            BranchReviewORM.review_id,
            BranchReviewORM.sentiment,
        ).where(BranchReviewORM.review_id.in_(review_ids))

        result = await self._session.execute(stmt)
        return {
            row._mapping["review_id"]: row._mapping["sentiment"]
            for row in result.all()
            if row._mapping.get("sentiment")
        }

    async def mark_reviews_as_read(self, review_ids: list[int] | None = None) -> int:
        """리뷰 읽음 처리 (is_new=false)"""
        if review_ids:
            return await self._batch_mark_read(review_ids)

        # 전체 읽음: ID 조회 후 배치 업데이트 (statement timeout 방지)
        total = 0
        while True:
            id_stmt = (
                select(BranchReviewORM.review_id)
                .where(BranchReviewORM.is_new == True)  # noqa: E712
                .limit(1000)
            )
            id_result = await self._session.execute(id_stmt)
            ids = id_result.scalars().all()

            if not ids:
                break

            total += await self._batch_mark_read(list(ids))

        return total

    async def _batch_mark_read(self, review_ids: list[int], batch_size: int = 500) -> int:
        """review_id 목록을 배치 단위로 is_new=false 처리"""
        total = 0
        for i in range(0, len(review_ids), batch_size):
            batch = review_ids[i : i + batch_size]
            stmt = (
                update(BranchReviewORM)
                .where(BranchReviewORM.review_id.in_(batch))
                .values(is_new=False)
            )
            result = await self._session.execute(stmt)
            total += result.rowcount
        return total

    async def get_review_ids_by_date_range(
        self, since: datetime, until: datetime,
    ) -> set[int]:
        """지정 기간의 활성 review_id 집합 조회 (ghost review 감지용)

        Athena REVIEW_QUERY와 동일한 경계: review_date > since AND review_date <= until
        soft-deleted 행은 제외한다.
        """
        stmt = (
            select(BranchReviewORM.review_id)
            .where(
                BranchReviewORM.review_date > since,
                BranchReviewORM.review_date <= until,
                BranchReviewORM.review_id.isnot(None),
                BranchReviewORM.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return {row[0] for row in result.all()}

    async def get_all_review_ids(self) -> set[int]:
        """전체 활성 review_id 집합 조회 (일괄 ghost review 정리용)

        soft-deleted 행은 제외한다.
        """
        stmt = (
            select(BranchReviewORM.review_id)
            .where(
                BranchReviewORM.review_id.isnot(None),
                BranchReviewORM.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return {row[0] for row in result.all()}

    async def delete_by_review_ids(self, review_ids: list[int], batch_size: int = 500) -> int:
        """리뷰 ID로 삭제 + 관련 review_tag_mappings 정리

        FK 제약 조건이 없으므로 review_tag_mappings도 명시적으로 삭제한다.
        """
        if not review_ids:
            return 0

        from .orm_models import ReviewTagMappingORM

        deleted_count = 0
        for i in range(0, len(review_ids), batch_size):
            batch = review_ids[i : i + batch_size]
            try:
                # 1. review_tag_mappings 먼저 삭제 (고아 행 방지)
                tag_stmt = delete(ReviewTagMappingORM).where(
                    ReviewTagMappingORM.review_id.in_(batch)
                )
                await self._session.execute(tag_stmt)

                # 2. branch_reviews 삭제
                stmt = delete(BranchReviewORM).where(
                    BranchReviewORM.review_id.in_(batch)
                )
                result = await self._session.execute(stmt)
                deleted_count += result.rowcount
            except Exception as e:
                logger.error(
                    f"Failed to delete reviews batch (data integrity risk): {e}"
                )
                raise

        if deleted_count > 0:
            logger.info("Deleted %s ghost reviews + related tag mappings", deleted_count)

        return deleted_count
