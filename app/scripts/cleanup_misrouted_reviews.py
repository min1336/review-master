"""오염 리뷰 정리: branch_id별 다수 업체와 다른 company_name을 가진 리뷰 삭제.

Athena API가 잘못된 branch_id로 매핑한 해외 리뷰가 국내 branch에 혼입된 건을 정리한다.

사용법:
    cd app && ../.venv/bin/python scripts/cleanup_misrouted_reviews.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repository.database import get_session_factory  # noqa: E402

logger = logging.getLogger(__name__)

# branch_summaries.branch_name 의 첫 토큰(업체명)을 정답 기준으로 사용.
# 다수결(dominant) 대신 summary 이름 기반이므로 해외 리뷰가 다수인 역전 케이스도 올바르게 처리.
CLEANUP_SQL = text("""
DELETE FROM branch_reviews br
USING branch_summaries bs
WHERE bs.branch_id = br.branch_id
  AND bs.region <> '해외'
  AND br.company_name IS NOT NULL
  AND br.company_name <> ''
  AND bs.branch_name NOT ILIKE '%' || br.company_name || '%'
  AND br.company_name NOT ILIKE '%' || SPLIT_PART(bs.branch_name, ' ', 1) || '%'
RETURNING br.id, br.review_id, br.branch_id, br.company_name, br.branch_name
""")

COUNT_SQL = text("""
SELECT br.branch_id, bs.branch_name AS summary_name, bs.region,
       SPLIT_PART(bs.branch_name, ' ', 1) AS expected_company,
       br.company_name AS mismatch,
       COUNT(*) AS cnt
FROM branch_reviews br
JOIN branch_summaries bs ON bs.branch_id = br.branch_id
WHERE bs.region <> '해외'
  AND br.company_name IS NOT NULL
  AND br.company_name <> ''
  AND bs.branch_name NOT ILIKE '%' || br.company_name || '%'
  AND br.company_name NOT ILIKE '%' || SPLIT_PART(bs.branch_name, ' ', 1) || '%'
GROUP BY br.branch_id, bs.branch_name, bs.region, br.company_name
ORDER BY cnt DESC
""")


async def main(dry_run: bool = True) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from core.config import get_settings
    from repository.database import init_db

    settings = get_settings()
    init_db(settings.get_database_url())
    session_factory = get_session_factory()

    async with session_factory() as session:
        # 1. 영향 범위 출력
        result = await session.execute(COUNT_SQL)
        rows = result.fetchall()
        total = sum(r.cnt for r in rows)

        if not rows:
            logger.info("오염 리뷰 없음. 정리할 항목이 없습니다.")
            return

        logger.info("=== 오염 리뷰 현황 (국내 branch만) ===")
        for r in rows:
            logger.info(
                "  branch_id=%s (%s, %s) expected=%s mismatch=%s cnt=%s",
                r.branch_id, r.summary_name, r.region,
                r.expected_company, r.mismatch, r.cnt,
            )
        logger.info("총 %s건 대상", total)

        if dry_run:
            logger.info("\n[DRY-RUN] 실제 삭제하지 않았습니다. --execute 로 실행하세요.")
            return

        # 2. 삭제 실행
        result = await session.execute(CLEANUP_SQL)
        deleted = result.fetchall()
        await session.commit()
        logger.info("\n%s건 삭제 완료.", len(deleted))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="오염 리뷰 정리")
    parser.add_argument(
        "--execute", action="store_true",
        help="실제 삭제 실행 (기본: dry-run)",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=not args.execute))
