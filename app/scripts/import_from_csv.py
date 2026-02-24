"""CSV 리뷰 데이터 → 파이프라인 처리 → DB 저장

data/reviewList.csv를 읽어 UnifiedPipeline을 통해 집계 테이블을 갱신합니다.
Athena 없이 CSV만으로 전체 파이프라인(감정/태그/키워드 분석)을 구동합니다.

업데이트 테이블:
- branch_reviews       : upsert (원본 저장) + sentiment 업데이트
- branch_sentiment_stats: 지점별 감정 통계 증분 갱신
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
import csv
import logging
import re
import sys
import time
from pathlib import Path

# app/ 디렉토리를 sys.path에 추가 (run_auto_mapping.py 패턴)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# CSV 경로: 프로젝트 루트의 data/reviewList.csv
CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "review_list.csv"

# 리뷰 상태 변환 맵 (한국어 → 영어)
STATUS_MAP = {
    "정상": "normal",
    "블라인드": "blind",
    "삭제": "deleted",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_null(text: str) -> str:
    """PostgreSQL이 거부하는 null byte(\x00) 제거"""
    return text.replace("\x00", "") if text else text


def strip_html(text: str) -> str:
    """<br> 등 HTML 태그 + null byte 제거 후 공백 정리"""
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = cleaned.replace("\x00", "")
    # 연속 공백 축소
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def load_csv(path: Path) -> tuple[list[dict], list[dict]]:
    """
    CSV를 읽어 두 가지 형태로 반환.

    Returns:
        raw_rows  : 원본 CSV rows (한국어 키, upsert_batch 직접 전달용)
        mapped_rows: 영어 키 변환 rows (UnifiedPipeline.run() 전달용)
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV 파일 없음: {path}")

    raw_rows: list[dict] = []
    mapped_rows: list[dict] = []

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # raw_rows: 한국어 키 그대로, null byte만 제거
            raw_rows.append({k: strip_null(v) if isinstance(v, str) else v for k, v in row.items()})

            # mapped_rows: 파이프라인용 영어 키 변환
            status_kr = (row.get("리뷰상태") or "").strip()
            status_en = STATUS_MAP.get(status_kr, status_kr)

            content_raw = row.get("리뷰내용") or ""
            content_clean = strip_html(content_raw)

            # NOTE: from_athena_row()는 car_type 키를 사용 (dto.py:111)
            mapped_rows.append({
                "review_id": row.get("리뷰번호", "").strip(),
                "branch_id": row.get("지점번호", "").strip(),
                "content": content_clean,
                "branch_name": (row.get("예약_지점명") or "").strip(),
                "company_name": (row.get("예약_업체명") or "").strip(),
                "rating_service": (row.get("지점평점(친절/편의성)") or "").strip(),
                "rating_car": (row.get("차량평점") or "").strip(),
                "rating_convenience": (row.get("인수/반납편의성") or "").strip(),
                "helpful_count": (row.get("도움돼요수") or "0").strip(),
                "review_date": (row.get("등록일시") or "").strip(),
                "status": status_en,
                "car_type": (row.get("차량모델") or "").strip(),
                "rent_type": (row.get("렌트타입") or "").strip(),
            })

    logger.info("CSV 로드 완료: %d건 (%s)", len(raw_rows), path.name)
    return raw_rows, mapped_rows


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
    raw_rows, mapped_rows = load_csv(CSV_PATH)
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
    logger.info("  SELECT branch_id, total_count, positive_ratio FROM branch_sentiment_stats ORDER BY branch_id;")
    logger.info("  SELECT COUNT(*) FROM branch_reviews WHERE sentiment IS NOT NULL;")


if __name__ == "__main__":
    asyncio.run(main())
