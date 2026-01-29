"""
기존 리뷰 sentiment 마이그레이션 스크립트

Usage:
    cd app && python -m scripts.migrate_sentiments

    # 특정 지점만 처리
    cd app && python -m scripts.migrate_sentiments --branch-id 45

    # dry-run (실제 업데이트 없이 확인만)
    cd app && python -m scripts.migrate_sentiments --dry-run
"""

import asyncio
import argparse
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
    dry_run: bool = False
) -> dict:
    """sentiment가 null인 리뷰들을 일괄 업데이트"""
    from repository.session import get_client
    from domain.analysis import HybridClassifier

    client = await get_client()
    classifier = HybridClassifier(lazy_load=True)

    # sentiment가 null인 리뷰 조회
    query = client.table("branch_reviews").select("*").is_("sentiment", "null")
    if branch_id:
        query = query.eq("branch_id", branch_id)

    result = await query.execute()
    reviews = result.data or []

    total = len(reviews)
    print(f"\n📊 sentiment가 null인 리뷰: {total:,}개")

    if dry_run:
        print("🔍 Dry-run 모드 - 실제 업데이트 없음")
        return {"total": total, "updated": 0, "dry_run": True}

    updated = 0
    errors = 0

    for i, review in enumerate(reviews, 1):
        content = review.get("content") or ""
        review_id = review.get("id")

        if not content or len(content.strip()) < 5:
            continue

        # 감정 분석
        result = classifier.get_review_summary(content)
        sentiment = result.get("overall_sentiment", "neutral")

        try:
            await client.table("branch_reviews").update({
                "sentiment": sentiment
            }).eq("id", review_id).execute()
            updated += 1
        except Exception as e:
            errors += 1
            continue

        if i % 100 == 0:
            print(f"   {i:,}/{total:,} 처리 중... ({updated:,}개 업데이트)")

    print(f"\n✅ 완료: {updated:,}개 업데이트, {errors:,}개 오류")
    return {"total": total, "updated": updated, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Sentiment 마이그레이션")
    parser.add_argument("--branch-id", type=int, help="특정 지점만 처리")
    parser.add_argument("--batch-size", type=int, default=100, help="배치 크기")
    parser.add_argument("--dry-run", action="store_true", help="실제 업데이트 없이 확인만")

    args = parser.parse_args()

    print("=" * 60)
    print("🔄 Sentiment 마이그레이션 시작")
    print("=" * 60)

    result = asyncio.run(migrate_sentiments(
        branch_id=args.branch_id,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    ))

    print("\n" + "=" * 60)
    print(f"📊 결과: {result}")
    print("=" * 60)


if __name__ == "__main__":
    main()
