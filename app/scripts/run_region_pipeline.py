"""지역별 파이프라인 실행 — Athena에서 특정 지역 리뷰를 추출하여 UnifiedPipeline 실행

branch_summaries.region 기준으로 대상 지점을 선정하고,
Athena에서 리뷰 본문(content)을 포함한 전체 데이터를 조회하여 파이프라인을 실행합니다.
결과는 기존 파이프라인과 동일하게 DB에 저장됩니다.

NOTE: branch_reviews.content는 DB 아키텍처 변경(73ab4aa)으로 NULL이므로
      반드시 Athena에서 조회해야 합니다.

업데이트 테이블:
- branch_reviews       : sentiment 업데이트
- branch_tags          : 지점별 태그 집계
- car_models_master    : 차종 마스터
- branch_car_models    : 지점-차종 관계
- branch_keywords      : 지점별 키워드
- review_tag_mappings  : 리뷰-태그 매핑
- monthly_rating_stats : 월별 평점 통계
- monthly_sentiment_stats : 월별 감정 통계
- monthly_tag_stats    : 월별 태그 통계
- monthly_car_model_tag_stats : 월별 차종 태그 통계

Usage:
    cd /home/teamo2/Downloads/Review_Summary_AI
    python app/scripts/run_region_pipeline.py                    # 제주 (기본)
    python app/scripts/run_region_pipeline.py --region 부산
    python app/scripts/run_region_pipeline.py --region 서울 --chunk 1000
"""

from __future__ import annotations

import argparse
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

PIPELINE_CHUNK = 500
ATHENA_PAGE_SIZE = 50000


async def fetch_all_branch_ids(session) -> list[int]:
    """branch_summaries에서 전체 branch_id 목록 조회"""
    from sqlalchemy import select

    from repository.orm_models import BranchSummaryORM

    logger.info("전체 지점 조회")

    result = await session.execute(
        select(BranchSummaryORM.branch_id).order_by(BranchSummaryORM.branch_id)
    )
    branch_ids = list(result.scalars().all())
    logger.info("  대상 지점: %d개", len(branch_ids))
    return branch_ids


async def fetch_region_branch_ids(session, region: str) -> list[int]:
    """branch_summaries.region 기준으로 branch_id 목록 조회"""
    from sqlalchemy import select

    from repository.orm_models import BranchSummaryORM

    logger.info("지점 조회: region LIKE '%s%%'", region)

    result = await session.execute(
        select(BranchSummaryORM.branch_id).where(
            BranchSummaryORM.region.like(f"{region}%")
        )
    )
    branch_ids = list(result.scalars().all())
    logger.info("  대상 지점: %d개", len(branch_ids))
    return branch_ids


def fetch_reviews_from_athena(branch_ids: list[int]) -> list[dict]:
    """Athena에서 branch_ids에 해당하는 리뷰 조회 (content 포함)

    fetch_reviews_with_filters를 페이지네이션하여 전체 리뷰를 가져옵니다.
    Athena 결과 키(review_id, content, car_type 등)가 ReviewDTO.from_athena_row()와
    호환되므로 별도 매핑 없이 파이프라인에 직접 전달 가능합니다.
    """
    from infrastructure.athena.client import AthenaClient

    athena = AthenaClient()
    all_reviews: list[dict] = []
    offset = 0

    while True:
        logger.info("  Athena 조회: offset=%s, limit=%s", offset, ATHENA_PAGE_SIZE)
        reviews, total = athena.fetch_reviews_with_filters(
            branch_ids=branch_ids,
            limit=ATHENA_PAGE_SIZE,
            offset=offset,
        )
        all_reviews.extend(reviews)
        logger.info("  → %s건 (누적: %s/%s)", len(reviews), len(all_reviews), total)

        if len(reviews) < ATHENA_PAGE_SIZE:
            break
        offset += ATHENA_PAGE_SIZE

    return all_reviews


async def main() -> None:
    parser = argparse.ArgumentParser(description="지역별 파이프라인 실행")
    parser.add_argument("--region", default="제주", help="대상 지역 (기본: 제주)")
    parser.add_argument("--all", action="store_true", help="전체 지점 대상 실행")
    parser.add_argument("--chunk", type=int, default=PIPELINE_CHUNK, help="청크 사이즈 (기본: 500)")
    args = parser.parse_args()

    from core.config import get_settings
    from domain.pipeline.unified_pipeline import UnifiedPipeline
    from repository.database import get_session_factory, init_db

    settings = get_settings()
    init_db(settings.get_database_url())
    factory = get_session_factory()

    start = time.time()
    run_all = getattr(args, "all")
    region = args.region
    chunk_size = args.chunk

    label = "전체 지점" if run_all else region
    logger.info("=== 파이프라인 시작: %s ===", label)

    # 1. branch_summaries에서 대상 지점 조회
    session = factory()
    try:
        if run_all:
            branch_ids = await fetch_all_branch_ids(session)
        else:
            branch_ids = await fetch_region_branch_ids(session, region)
    finally:
        await session.close()

    if not branch_ids:
        logger.info("해당 지역에 지점이 없습니다.")
        return

    # 2. Athena에서 리뷰 조회 (content 포함)
    logger.info("Athena에서 리뷰 조회 중...")
    reviews = fetch_reviews_from_athena(branch_ids)

    if not reviews:
        logger.info("처리할 리뷰가 없습니다.")
        return

    total = len(reviews)
    logger.info("파이프라인 입력: %d건 (Athena 조회 소요: %.1fs)", total, time.time() - start)

    # 3. UnifiedPipeline 청크 실행
    pipeline = UnifiedPipeline()
    total_processed = 0
    total_branches = set()
    chunk_count = (total + chunk_size - 1) // chunk_size

    for i in range(0, total, chunk_size):
        chunk = reviews[i : i + chunk_size]
        chunk_no = i // chunk_size + 1
        elapsed = time.time() - start

        logger.info(
            "청크 %d/%d  [%d~%d건]  경과: %.0fs",
            chunk_no, chunk_count,
            i + 1, min(i + chunk_size, total),
            elapsed,
        )

        result = await pipeline.run(chunk)
        total_processed += result.processed_reviews
        total_branches.update(
            r.get("branch_id") for r in chunk if r.get("branch_id")
        )

        status = "OK" if result.success else f"FAIL({result.error_message})"
        pct = min(i + chunk_size, total) / total * 100
        logger.info(
            "  → 처리: %d건  진행: %.1f%%  %s",
            result.processed_reviews, pct, status,
        )

    # 4. 최종 결과
    elapsed = time.time() - start
    logger.info("=== 완료 ===")
    logger.info(
        "대상: %s | 총 리뷰: %d | 처리: %d | 지점: %d | 소요: %.1fs",
        label, total, total_processed, len(total_branches), elapsed,
    )


if __name__ == "__main__":
    asyncio.run(main())
