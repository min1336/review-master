"""
기존 리뷰 sentiment 마이그레이션 스크립트

Usage:
    cd app && python -m scripts.migrate_sentiments

    # 특정 지점만 처리
    cd app && python -m scripts.migrate_sentiments --branch-id 45

    # dry-run (실제 업데이트 없이 확인만)
    cd app && python -m scripts.migrate_sentiments --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv 없으면 환경변수 직접 설정 필요


async def migrate_sentiments(
    branch_id: int | None = None,
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict:
    """sentiment가 null인 리뷰들을 일괄 업데이트"""
    from sqlalchemy import select, update

    from core.config import get_settings
    from domain.analysis import HybridClassifier
    from repository.database import get_session_factory, init_db
    from repository.orm_models import BranchReviewORM

    settings = get_settings()
    init_db(settings.get_database_url())
    factory = get_session_factory()

    classifier = HybridClassifier(lazy_load=True)

    session = factory()
    try:
        # sentiment가 null인 리뷰 조회
        stmt = select(BranchReviewORM).where(BranchReviewORM.sentiment.is_(None))
        if branch_id:
            stmt = stmt.where(BranchReviewORM.branch_id == branch_id)

        result = await session.execute(stmt)
        reviews = result.scalars().all()

        total = len(reviews)
        print(f"\nsentiment가 null인 리뷰: {total:,}개")

        if dry_run:
            print("Dry-run 모드 - 실제 업데이트 없음")
            return {"total": total, "updated": 0, "dry_run": True}

        updated = 0
        errors = 0

        for i, review in enumerate(reviews, 1):
            content = review.content or ""

            if not content or len(content.strip()) < 5:
                continue

            # 감정 분석
            analysis = classifier.get_review_summary(content)
            sentiment = analysis.get("overall_sentiment", "neutral")

            try:
                await session.execute(
                    update(BranchReviewORM)
                    .where(BranchReviewORM.id == review.id)
                    .values(sentiment=sentiment)
                )
                updated += 1
            except Exception:
                errors += 1
                continue

            if i % 100 == 0:
                await session.commit()
                print(f"   {i:,}/{total:,} 처리 중... ({updated:,}개 업데이트)")

        await session.commit()
        print(f"\n완료: {updated:,}개 업데이트, {errors:,}개 오류")
        return {"total": total, "updated": updated, "errors": errors}
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def main():
    parser = argparse.ArgumentParser(description="Sentiment 마이그레이션")
    parser.add_argument("--branch-id", type=int, help="특정 지점만 처리")
    parser.add_argument("--batch-size", type=int, default=100, help="배치 크기")
    parser.add_argument("--dry-run", action="store_true", help="실제 업데이트 없이 확인만")

    args = parser.parse_args()

    print("=" * 60)
    print("Sentiment 마이그레이션 시작")
    print("=" * 60)

    result = asyncio.run(migrate_sentiments(
        branch_id=args.branch_id,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    ))

    print("\n" + "=" * 60)
    print(f"결과: {result}")
    print("=" * 60)


if __name__ == "__main__":
    main()
