"""CSV 리뷰 데이터 → 파이프라인 처리 → DB 저장

data/review_list.csv를 읽어 UnifiedPipeline을 통해 집계 테이블을 갱신합니다.
Athena 없이 CSV만으로 전체 파이프라인(감정/태그/키워드 분석)을 구동합니다.

업데이트 테이블:
- branch_reviews       : upsert (원본 저장) + sentiment 업데이트
- monthly_sentiment_stats: 월별 감정 통계 증분 갱신
- branch_tags          : 지점별 태그 집계 갱신
- keyword_mappings     : 키워드→태그 매핑 추가
- car_model_tags       : 차종별 태그 집계 갱신
- branch_keywords      : 지점별 키워드 누적 갱신

Usage:
    cd /home/teamo2/Downloads/Review_Summary_AI
    python app/scripts/import_from_csv.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

# app/ 디렉토리를 sys.path에 추가 (run_auto_mapping.py 패턴)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._csv_utils import load_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# CSV 경로: 프로젝트 루트의 data/reviewList.csv
CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "review_list.csv"


async def progress(pct: int, message: str) -> None:
    """파이프라인 진행률 콜백"""
    logger.info("  진행: %d%% — %s", pct, message)


PIPELINE_CHUNK = 500  # 청크당 처리 건수 (진행률 표시 + 부분 저장)


async def main() -> None:
    # 지연 임포트 (run_auto_mapping.py 패턴 — 모델 로딩 전 sys.path 확보)
    from core.config import get_settings
    from domain.pipeline.unified_pipeline import UnifiedPipeline
    from repository.database import get_session_factory, init_db
    from repository.review_repository import BranchReviewRepository

    settings = get_settings()
    init_db(settings.get_database_url())
    factory = get_session_factory()

    start = time.time()

    # 1. CSV 로드
    logger.info("=== CSV 로드 시작 ===")
    raw_rows, mapped_rows = load_csv(CSV_PATH, include_raw=True)
    total = len(raw_rows)
    logger.info("총 %d건 로드 완료", total)

    if total == 0:
        logger.warning("CSV에 데이터가 없습니다.")
        return

    # 2. branch_reviews 원본 upsert
    logger.info("=== Step 0: branch_reviews 원본 저장 ===")
    session = factory()
    try:
        review_repo = BranchReviewRepository(session)

        upsert_rows = [{**r, "is_new": True} for r in raw_rows]
        saved = await review_repo.upsert_batch(upsert_rows)
        await session.commit()
        logger.info("  저장: %d건 (요청: %d건)", saved, total)
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

    # 3. UnifiedPipeline 청크 단위 실행 (진행률 표시)
    logger.info("=== Step 1~6: UnifiedPipeline 실행 (청크=%d) ===", PIPELINE_CHUNK)
    pipeline = UnifiedPipeline()

    total_processed = 0
    chunk_count = (total + PIPELINE_CHUNK - 1) // PIPELINE_CHUNK

    for i in range(0, total, PIPELINE_CHUNK):
        chunk = mapped_rows[i : i + PIPELINE_CHUNK]
        chunk_no = i // PIPELINE_CHUNK + 1
        elapsed_so_far = time.time() - start

        logger.info(
            "청크 %d/%d  [%d~%d건]  경과: %.0fs",
            chunk_no, chunk_count,
            i + 1, min(i + PIPELINE_CHUNK, total),
            elapsed_so_far,
        )

        result = await pipeline.run(chunk)
        total_processed += result.processed_reviews

        pct = min(i + PIPELINE_CHUNK, total) / total * 100
        status = "OK" if result.success else f"FAIL({result.error_message})"
        logger.info(
            "  → 처리: %d건  지점: %d개  진행: %.1f%%  %s",
            result.processed_reviews, result.total_branches, pct, status,
        )

    # 4. 최종 결과
    elapsed = time.time() - start
    logger.info("=== 완료 ===")
    logger.info(
        "총 처리: %d/%d건  |  소요: %.1fs  (%.1f건/초)",
        total_processed, total, elapsed,
        total_processed / elapsed if elapsed > 0 else 0,
    )
    logger.info("")
    logger.info("DB 검증 쿼리:")
    logger.info("  SELECT branch_id, COUNT(*) FROM monthly_sentiment_stats GROUP BY branch_id ORDER BY branch_id;")
    logger.info("  SELECT COUNT(*) FROM branch_reviews WHERE sentiment IS NOT NULL;")


if __name__ == "__main__":
    asyncio.run(main())
