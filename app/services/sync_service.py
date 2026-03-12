"""리뷰 동기화 서비스 - UnifiedPipeline 통합 (날짜 기반 청킹)"""

from __future__ import annotations

import asyncio
import gc
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from core.timezone import parse_date_str, utc_now

from domain.pipeline.unified_pipeline import UnifiedPipeline
from infrastructure.athena import AthenaClient
from repository.database import get_session_factory
from repository.review_repository import BranchReviewRepository
from repository.sync_metadata_repository import SyncMetadataRepository
from schemas.sync import SyncResultResponse

logger = logging.getLogger(__name__)

SYNC_TYPE = "daily_pipeline"


def _filter_misrouted_reviews(
    reviews: list[dict],
) -> tuple[list[dict], int]:
    """branch_id별 다수 company_name과 다른 리뷰를 제거한다.

    Athena가 잘못된 branch_id로 매핑한 리뷰(예: 해외 업체 리뷰가 국내 branch에
    혼입)를 동기화 시점에 걸러낸다.

    Returns:
        (필터링된 리뷰 리스트, 제거된 건수)
    """
    from collections import Counter

    # branch_id별 company_name 빈도 집계
    branch_company_counts: dict[int, Counter] = {}
    for r in reviews:
        bid = r.get("branch_id") or r.get("지점번호")
        cname = r.get("company_name") or r.get("예약_업체명") or ""
        if bid is None or not cname:
            continue
        try:
            bid = int(bid)
        except (ValueError, TypeError):
            continue
        if bid not in branch_company_counts:
            branch_company_counts[bid] = Counter()
        branch_company_counts[bid][cname] += 1

    # branch_id별 다수 company_name 결정
    dominant: dict[int, str] = {}
    for bid, counter in branch_company_counts.items():
        dominant[bid] = counter.most_common(1)[0][0]

    # 소수 company_name 비율이 충분히 낮을 때만 필터링 (오탐 방지)
    filtered: list[dict] = []
    dropped = 0
    for r in reviews:
        bid = r.get("branch_id") or r.get("지점번호")
        cname = r.get("company_name") or r.get("예약_업체명") or ""
        try:
            bid = int(bid)
        except (ValueError, TypeError):
            filtered.append(r)
            continue

        dom = dominant.get(bid)
        if dom and cname and cname != dom:
            total = sum(branch_company_counts[bid].values())
            dom_count = branch_company_counts[bid][dom]
            # 다수 업체가 80% 이상일 때만 소수를 오배정으로 판단
            if dom_count / total >= 0.8:
                logger.debug(
                    "오배정 필터: review_id=%s branch_id=%s expected=%s got=%s",
                    r.get("review_id"), bid, dom, cname,
                )
                dropped += 1
                continue

        filtered.append(r)

    return filtered, dropped


def _generate_day_ranges(
    since: datetime, until: datetime | None
) -> list[tuple[datetime, datetime]]:
    """날짜 범위를 1일 단위로 분할.

    Athena 쿼리 경계: register_date > since AND register_date <= until
    각 청크의 since는 이전 청크의 until → 빈틈/중복 없음.
    """
    if until is None:
        until = utc_now()

    ranges: list[tuple[datetime, datetime]] = []
    chunk_start = since

    while chunk_start < until:
        next_midnight = (chunk_start + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        chunk_end = min(next_midnight, until)

        if chunk_end <= chunk_start:
            break  # 안전장치: 무한 루프 방지

        ranges.append((chunk_start, chunk_end))
        chunk_start = chunk_end

    return ranges


def _make_chunk_callback(
    parent: Callable[[int, str], Awaitable[None]] | None,
    day_idx: int,
    total_days: int,
) -> Callable[[int, str], Awaitable[None]] | None:
    """pipeline.run()의 내부 progress(0~100)를 청크별 구간으로 리매핑."""
    if parent is None:
        return None

    chunk_size = 89.0 / total_days  # 전체 5%~94% 중 이 청크의 몫
    chunk_base = 5 + day_idx * chunk_size

    async def callback(progress: int, message: str) -> None:
        absolute = int(chunk_base + (progress / 100.0) * chunk_size)
        absolute = min(absolute, 94)
        label = f"[{day_idx + 1}/{total_days}일]"
        await parent(absolute, f"{label} {message}")

    return callback


class SyncService:
    """리뷰 동기화 서비스 - 태그/감정 분석 포함"""

    def __init__(
        self,
        review_repo: BranchReviewRepository,
        athena_client: AthenaClient | None = None,
        pipeline: UnifiedPipeline | None = None,
    ) -> None:
        self._review_repo = review_repo
        self._athena_client = athena_client
        self._pipeline = pipeline or UnifiedPipeline()

    async def sync_reviews(
        self,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> SyncResultResponse:
        """
        Athena에서 리뷰 조회 → branch_reviews 저장 → UnifiedPipeline 실행

        Args:
            progress_callback: 진행률 콜백 (progress%, message). None이면 무시.
            date_from: 시작일 (YYYY-MM-DD). None이면 last_sync_at 사용.
            date_to: 종료일 (YYYY-MM-DD). None이면 제한 없음.

        1. date_from/date_to 또는 last_sync_at 기준으로 리뷰 조회
        2. branch_reviews에 is_new=true로 원본 저장 (upsert)
        3. UnifiedPipeline 실행 (감정/태그 통계 저장)
        4. last_sync_at 업데이트
        """
        start_time = utc_now()

        if not self._athena_client:
            return SyncResultResponse(
                success=False,
                message="Athena 클라이언트가 설정되지 않았습니다",
                error="athena_client_not_configured",
            )

        async with get_session_factory()() as session:
            try:
                metadata_repo = SyncMetadataRepository(session)

                # 1. 조회 기간 결정: 명시적 date_from이 있으면 사용, 없으면 last_sync_at
                if date_from:
                    since = parse_date_str(date_from)
                else:
                    since = await metadata_repo.get_last_sync_at(SYNC_TYPE)
                    if not since:
                        since = utc_now() - timedelta(days=7)

                until = None
                if date_to:
                    until = parse_date_str(date_to, end_of_day=True)

                # 2. 날짜 범위를 1일 단위로 분할
                day_ranges = _generate_day_ranges(since, until)
                total_days = len(day_ranges)

                range_desc = f"{since.strftime('%Y-%m-%d')}~{date_to or '현재'}"
                logger.info("동기화 시작: %s (%s일 청크)", range_desc, total_days)
                logger.info("[DailyPipeline] 시작: %s (%s일 청크)", range_desc, total_days)

                if progress_callback:
                    await progress_callback(5, f"동기화 시작 ({range_desc}, {total_days}일)")

                # 3. 날짜 청크별 처리: Athena 조회 → 중복 제거 → upsert → pipeline
                total_synced = 0
                total_new = 0
                total_processed = 0
                chunk_errors: list[str] = []

                for day_idx, (chunk_since, chunk_until) in enumerate(day_ranges):
                    try:
                        synced, new, processed = await self._process_day_chunk(
                            chunk_since,
                            chunk_until,
                            day_idx,
                            total_days,
                            progress_callback,
                        )
                        total_synced += synced
                        total_new += new
                        total_processed += processed
                    except Exception as e:
                        day_label = chunk_since.strftime("%m-%d")
                        logger.error(
                            f"청크 {day_idx + 1}/{total_days} ({day_label}) 실패: {e}",
                            exc_info=True,
                        )
                        chunk_errors.append(f"{day_label}: {e}")

                # 4. last_sync_at 업데이트 (모든 청크 완료 후 1회)
                if progress_callback:
                    await progress_callback(95, "메타데이터 업데이트")
                await metadata_repo.update_last_sync_at(SYNC_TYPE)

                await session.commit()
                duration = (utc_now() - start_time).total_seconds()

                # 5. 결과 응답 생성
                if total_synced == 0 and not chunk_errors:
                    return SyncResultResponse(
                        success=True,
                        message="신규 리뷰가 없습니다",
                        synced_count=0,
                        new_reviews=0,
                        duration_seconds=duration,
                    )

                failed_count = total_synced - total_processed
                logger.info(
                    f"동기화 완료: {total_synced}개 저장, {total_processed}개 분석, "
                    f"{failed_count}개 실패 ({duration:.1f}초)"
                )

                if chunk_errors:
                    return SyncResultResponse(
                        success=total_synced > 0,
                        message=f"{total_synced}개 저장 (일부 실패: {len(chunk_errors)}일)",
                        synced_count=total_synced,
                        new_reviews=total_new,
                        duration_seconds=duration,
                        error="; ".join(chunk_errors),
                    )

                return SyncResultResponse(
                    success=True,
                    message=f"{total_synced}개 리뷰 저장 + {total_processed}개 분석 완료",
                    synced_count=total_synced,
                    new_reviews=total_new,
                    duration_seconds=duration,
                )

            except Exception as e:
                logger.error("동기화 실패: %s", e, exc_info=True)
                return SyncResultResponse(
                    success=False,
                    message="동기화 실행 중 오류가 발생했습니다",
                    error="sync_failed",
                    duration_seconds=(utc_now() - start_time).total_seconds(),
                )

    async def _process_day_chunk(
        self,
        chunk_since: datetime,
        chunk_until: datetime,
        day_idx: int,
        total_days: int,
        progress_callback: Callable[[int, str], Awaitable[None]] | None,
    ) -> tuple[int, int, int]:
        """1일분 리뷰 처리: Athena 조회 → 중복 제거 → upsert → pipeline.

        Returns:
            (synced_count, new_count, processed_count)
        """
        day_label = chunk_since.strftime("%m-%d")

        # 1. Athena에서 리뷰 조회 (블로킹 방지: to_thread)
        athena_reviews = await asyncio.to_thread(
            self._athena_client.fetch_reviews_since,
            chunk_since,
            until=chunk_until,
        )

        if not athena_reviews:
            logger.info("[%s] 리뷰 없음, 건너뜀", day_label)
            return 0, 0, 0

        # 2. 중복 제거
        seen_ids: set[str] = set()
        reviews: list[dict] = []
        for row in athena_reviews:
            review_id = row.get("review_id")
            if review_id in seen_ids:
                continue
            seen_ids.add(review_id)
            reviews.append(row)
        del athena_reviews, seen_ids
        gc.collect()

        # 2-1. 오배정 리뷰 필터링: branch_id별 다수 업체와 다른 company_name 제거
        reviews, dropped = _filter_misrouted_reviews(reviews)
        if dropped:
            logger.warning("[%s] 오배정 리뷰 %s건 필터링됨", day_label, dropped)

        logger.info("[%s] Athena 조회 완료: %s개", day_label, len(reviews))

        # 3. branch_reviews에 원본 저장 (is_new=true)
        review_ids: list[int] = []
        for r in reviews:
            raw = r.get("review_id") or r.get("리뷰번호")
            if raw is None:
                continue
            try:
                review_ids.append(int(raw))
            except (ValueError, TypeError):
                continue
        existing_count = await self._review_repo.count_existing_review_ids(
            review_ids
        )
        for row in reviews:
            row["is_new"] = True
        saved_count = await self._review_repo.upsert_batch(reviews)
        new_count = max(saved_count - existing_count, 0)
        # upsert 커밋: 파이프라인이 별도 세션으로 같은 행을 UPDATE하므로
        # 행 잠금을 해제해야 데드락 방지 (upsert는 idempotent)
        await self._review_repo.commit()

        logger.info(
            f"[{day_label}] {saved_count}개 upsert "
            f"(신규 {new_count}개, 기존 {existing_count}개)"
        )

        # 4. UnifiedPipeline 실행 (감정/태그 통계 저장)
        chunk_cb = _make_chunk_callback(progress_callback, day_idx, total_days)
        result = await self._pipeline.run(reviews, chunk_cb)
        processed_count = result.processed_reviews

        if result.failed_steps:
            logger.warning(
                "[%s] 파이프라인 일부 실패: %s", day_label, result.failed_steps,
            )

        logger.info("[%s] 파이프라인 완료: %s개 처리", day_label, processed_count)

        # 5. Ghost review 정리: 해당 기간 내 로컬에만 존재하는 리뷰 삭제
        athena_id_set = set(review_ids)
        local_ids = await self._review_repo.get_review_ids_by_date_range(
            chunk_since, chunk_until,
        )
        ghost_ids = local_ids - athena_id_set
        if ghost_ids:
            deleted = await self._review_repo.delete_by_review_ids(list(ghost_ids))
            await self._review_repo.commit()
            logger.info("[%s] Ghost review %s개 삭제 (Athena 비활성)", day_label, deleted)

        # 6. 메모리 해제
        del reviews
        gc.collect()

        return saved_count, new_count, processed_count

    async def cleanup_ghost_reviews(
        self,
        progress_callback: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> int:
        """Athena에서 비활성화된 ghost review 일괄 정리

        전체 로컬 review_id와 Athena 활성 review_id를 비교하여
        비활성 리뷰를 삭제한다. 최초 1회 실행용.
        """
        if not self._athena_client:
            logger.warning("Athena 클라이언트 미설정 — ghost 정리 불가")
            return 0

        if progress_callback:
            await progress_callback(5, "Athena에서 활성 리뷰 ID 조회 중...")

        # 1. Athena 활성 review_id 조회
        active_ids = await asyncio.to_thread(
            self._athena_client.fetch_all_active_review_ids,
        )
        logger.info("Athena 활성 리뷰: %s개", len(active_ids))

        if progress_callback:
            await progress_callback(40, f"활성 리뷰 {len(active_ids)}개 확인")

        # 2. 로컬 DB 전체 review_id 조회
        local_ids = await self._review_repo.get_all_review_ids()
        logger.info("로컬 리뷰: %s개", len(local_ids))

        if progress_callback:
            await progress_callback(60, f"로컬 리뷰 {len(local_ids)}개 확인")

        # 3. Ghost review 식별
        ghost_ids = local_ids - active_ids
        if not ghost_ids:
            logger.info("Ghost review 없음")
            if progress_callback:
                await progress_callback(100, "Ghost review 없음")
            return 0

        logger.info("Ghost review %s개 감지 — 삭제 시작", len(ghost_ids))
        if progress_callback:
            await progress_callback(70, f"Ghost review {len(ghost_ids)}개 삭제 중...")

        # 4. 삭제
        deleted = await self._review_repo.delete_by_review_ids(list(ghost_ids))
        await self._review_repo.commit()

        logger.info("Ghost review 정리 완료: %s개 삭제", deleted)
        logger.warning(
            "branch_tags 통계가 삭제된 ghost review를 포함할 수 있습니다. "
            "정확한 통계를 위해 동기화를 다시 실행하거나 수동 재집계가 필요합니다."
        )
        if progress_callback:
            await progress_callback(100, f"Ghost review {deleted}개 삭제 완료")

        return deleted

    async def mark_reviews_as_read(
        self, review_ids: list[int] | None = None
    ) -> int:
        """리뷰 읽음 처리"""
        return await self._review_repo.mark_reviews_as_read(review_ids)
