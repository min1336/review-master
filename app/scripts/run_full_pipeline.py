"""전지역 CSV 파이프라인 — Step 0(upsert) 건너뛰고 분석+집계만 실행

DB에 이미 branch_reviews가 있으므로 upsert를 건너뛰고,
CSV의 content를 사용하여 감정분석/태그/키워드/통계만 처리합니다.

Usage:
    cd /home/teamo2/Downloads/Review_Summary_AI
    python app/scripts/run_full_pipeline.py
    python app/scripts/run_full_pipeline.py --chunk 1000
"""

from __future__ import annotations

import asyncio
import csv
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "review_list.csv"

STATUS_MAP = {
    "정상": "normal",
    "블라인드": "blind",
    "삭제": "deleted",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = cleaned.replace("\x00", "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def load_csv_mapped(path: Path) -> list[dict]:
    """CSV -> 파이프라인용 영어 키 변환 rows"""
    if not path.exists():
        raise FileNotFoundError(f"CSV 파일 없음: {path}")

    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status_kr = (row.get("리뷰상태") or "").strip()
            status_en = STATUS_MAP.get(status_kr, status_kr)
            content_clean = strip_html(row.get("리뷰내용") or "")

            rows.append({
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

    logger.info("CSV 로드 완료: %d건 (%s)", len(rows), path.name)
    return rows


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="전지역 파이프라인 (Step 0 건너뛰기)")
    parser.add_argument("--chunk", type=int, default=500, help="청크 사이즈 (기본: 500)")
    args = parser.parse_args()

    from core.config import get_settings
    from domain.pipeline.unified_pipeline import UnifiedPipeline
    from repository.database import init_db, close_db

    settings = get_settings()
    init_db(settings.get_database_url())

    start = time.time()
    chunk_size = args.chunk

    # 1. CSV 로드
    logger.info("=== CSV 로드 ===")
    mapped_rows = load_csv_mapped(CSV_PATH)
    total = len(mapped_rows)
    load_time = time.time() - start
    logger.info("로드 완료: %d건 (%.1fs)", total, load_time)

    # 2. UnifiedPipeline 청크 실행
    logger.info("=== 파이프라인 시작 (청크=%d) ===", chunk_size)
    pipeline = UnifiedPipeline()

    total_processed = 0
    total_branches: set[int] = set()
    chunk_count = (total + chunk_size - 1) // chunk_size
    failed_chunks: list[int] = []

    for i in range(0, total, chunk_size):
        chunk = mapped_rows[i : i + chunk_size]
        chunk_no = i // chunk_size + 1
        elapsed = time.time() - start

        logger.info(
            "청크 %d/%d  [%d~%d건]  경과: %.0fs",
            chunk_no, chunk_count,
            i + 1, min(i + chunk_size, total),
            elapsed,
        )

        try:
            result = await pipeline.run(chunk)
            total_processed += result.processed_reviews
            total_branches.update(
                int(r["branch_id"]) for r in chunk
                if r.get("branch_id") and str(r["branch_id"]).isdigit()
            )

            pct = min(i + chunk_size, total) / total * 100
            rate = total_processed / (time.time() - start) if time.time() > start else 0
            remaining = (total - min(i + chunk_size, total)) / rate if rate > 0 else 0
            status = "OK" if result.success else f"FAIL({result.error_message})"

            logger.info(
                "  → 처리: %d건  진행: %.1f%%  속도: %.1f건/s  남은시간: %.0f분  %s",
                result.processed_reviews, pct, rate, remaining / 60, status,
            )
        except Exception as e:
            logger.error("  → 청크 %d 실패: %s", chunk_no, e)
            failed_chunks.append(chunk_no)

    # 3. 최종 결과
    elapsed = time.time() - start
    logger.info("=== 완료 ===")
    logger.info(
        "총 처리: %d/%d건  |  지점: %d개  |  소요: %.1fs (%.1f분)  |  속도: %.1f건/초",
        total_processed, total, len(total_branches), elapsed,
        elapsed / 60, total_processed / elapsed if elapsed > 0 else 0,
    )
    if failed_chunks:
        logger.warning("실패한 청크: %s", failed_chunks)

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
