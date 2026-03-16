"""전지점 요약 생성 — 리뷰 30개 이상 지점 대상 배치 처리

1. branch_summaries 기본 레코드 생성 (없는 지점)
2. 리뷰 30개 이상 지점에 AI 요약 생성 (OpenAI GPT-4o-mini)

Usage:
    cd /home/teamo2/Downloads/Review_Summary_AI
    python app/scripts/run_batch_summary.py
    python app/scripts/run_batch_summary.py --limit 10   # 테스트용
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="전지점 요약 배치 생성")
    parser.add_argument("--limit", type=int, default=0, help="처리할 지점 수 제한 (0=전체)")
    args = parser.parse_args()

    from sqlalchemy import func, select, text

    from core.config import get_settings
    from repository.database import get_session_factory, init_db
    from repository.orm_models import BranchReviewORM, BranchSummaryORM

    settings = get_settings()
    init_db(settings.get_database_url())
    factory = get_session_factory()

    start = time.time()

    # 1. 리뷰 30개 이상 지점 목록
    logger.info("=== Step 1: 대상 지점 조회 ===")
    session = factory()
    try:
        result = await session.execute(
            select(
                BranchReviewORM.branch_id,
                func.count().label("cnt"),
                func.max(BranchReviewORM.branch_name).label("branch_name"),
                func.avg(BranchReviewORM.rating_service).label("avg_rating"),
            )
            .group_by(BranchReviewORM.branch_id)
            .having(func.count() >= 30)
            .order_by(func.count().desc())
        )
        target_branches = [
            {
                "branch_id": row.branch_id,
                "count": row.cnt,
                "branch_name": row.branch_name or f"지점 {row.branch_id}",
                "avg_rating": float(row.avg_rating) if row.avg_rating else None,
            }
            for row in result.all()
        ]
    finally:
        await session.close()

    if args.limit > 0:
        target_branches = target_branches[: args.limit]

    logger.info("대상 지점: %d개", len(target_branches))

    # 2. branch_summaries 기본 레코드 upsert
    logger.info("=== Step 2: branch_summaries 기본 레코드 생성 ===")
    session = factory()
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        created = 0
        for b in target_branches:
            stmt = (
                pg_insert(BranchSummaryORM.__table__)
                .values(
                    branch_id=b["branch_id"],
                    branch_name=b["branch_name"],
                    review_count=b["count"],
                    avg_rating=b["avg_rating"],
                    status="active",
                )
                .on_conflict_do_update(
                    index_elements=["branch_id"],
                    set_={
                        "branch_name": b["branch_name"],
                        "review_count": b["count"],
                        "avg_rating": b["avg_rating"],
                    },
                )
            )
            await session.execute(stmt)
            created += 1
        await session.commit()
        logger.info("branch_summaries upsert: %d건", created)
    finally:
        await session.close()

    # 3. AI 요약 생성 (순차 처리)
    logger.info("=== Step 3: AI 요약 생성 ===")

    from repository.branch_tag_repository import BranchTagRepository
    from repository.review_repository import BranchReviewRepository
    from repository.review_repository import SentimentRepository
    from repository.summary_repository import SummaryRepository
    from services.summary_service import SummaryService

    success_count = 0
    fail_count = 0
    skip_count = 0

    async def generate_one(branch_info: dict, idx: int) -> None:
        nonlocal success_count, fail_count, skip_count

        session = factory()
        try:
            summary_repo = SummaryRepository(session)
            branch_tag_repo = BranchTagRepository(session)
            review_repo = BranchReviewRepository(session)
            sentiment_repo = SentimentRepository(session)

            # 이미 요약이 있으면 건너뛰기
            existing = await summary_repo.get_by_branch_id(branch_info["branch_id"])
            if existing:
                data = existing.model_dump() if hasattr(existing, 'model_dump') else existing
                if any(data.get(f) for f in ["summary_1m", "summary_3m", "summary_6m", "summary_1y", "summary_all"]):
                    success_count += 1
                    logger.info(
                        "  [%d/%d] 지점 %d — 이미 요약 있음 (skip)",
                        idx + 1, len(target_branches), branch_info["branch_id"],
                    )
                    return

            svc = SummaryService(
                summary_repo, branch_tag_repo, review_repo, sentiment_repo
            )

            result = await svc.generate_summary_with_data(
                branch_info["branch_id"],
                save_to_db=True,
                mode="marketing",
            )
            await session.commit()

            if result.get("success"):
                success_count += 1
                period = result.get("period", "?")
                logger.info(
                    "  [%d/%d] 지점 %d (%s) — %s 요약 생성 OK",
                    idx + 1, len(target_branches),
                    branch_info["branch_id"],
                    branch_info["branch_name"],
                    period,
                )
            else:
                error = result.get("error", "unknown")
                if "부족" in str(error):
                    skip_count += 1
                else:
                    fail_count += 1
                logger.warning(
                    "  [%d/%d] 지점 %d — %s",
                    idx + 1, len(target_branches),
                    branch_info["branch_id"],
                    error,
                )
        except Exception as e:
            fail_count += 1
            logger.error(
                "  [%d/%d] 지점 %d 오류: %s",
                idx + 1, len(target_branches),
                branch_info["branch_id"],
                e,
            )
            await session.rollback()
        finally:
            await session.close()

    # 순차 배치 실행 (API rate limit 방지)
    for i, b in enumerate(target_branches):
        await generate_one(b, i)
        # rate limit 방지: 1.5초 간격
        await asyncio.sleep(1.5)

    # 4. 결과
    elapsed = time.time() - start
    logger.info("=== 완료 ===")
    logger.info(
        "성공: %d  |  실패: %d  |  스킵(리뷰부족): %d  |  소요: %.1fs (%.1f분)",
        success_count, fail_count, skip_count, elapsed, elapsed / 60,
    )


if __name__ == "__main__":
    asyncio.run(main())
