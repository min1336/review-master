"""
Review Read Status Repository 테스트 스크립트

Usage:
    # 테이블 생성 후 실행
    cd app && python -m scripts.test_review_read_status

Description:
    review_read_status_repository 기능 검증:
    - mark_as_read 테스트
    - get_read_ids 테스트
    - is_read 테스트
    - get_read_count 테스트
"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass


async def test_repository():
    """Repository 기능 테스트"""
    from repository.session import get_client
    from repository.review_read_status_repository import ReviewReadStatusRepository

    client = await get_client()
    repo = ReviewReadStatusRepository(client)

    print("\n1️⃣  초기 상태 확인")
    initial_count = await repo.get_read_count()
    print(f"   초기 읽은 리뷰 개수: {initial_count}")

    # 테스트용 review_id 목록
    test_ids = [
        "TEST_REV_001",
        "TEST_REV_002",
        "TEST_REV_003",
        "TEST_REV_004",
        "TEST_REV_005",
    ]

    print("\n2️⃣  리뷰 읽음 처리 테스트")
    marked = await repo.mark_as_read(test_ids[:3], read_by="test_user")
    print(f"   처리된 리뷰 개수: {marked}")

    print("\n3️⃣  읽은 리뷰 조회 테스트")
    read_ids = await repo.get_read_ids(test_ids)
    print(f"   읽은 리뷰 ID: {read_ids}")

    print("\n4️⃣  개별 리뷰 읽음 확인 테스트")
    for rid in test_ids:
        is_read = await repo.is_read(rid)
        status = "✓ 읽음" if is_read else "✗ 안 읽음"
        print(f"   {rid}: {status}")

    print("\n5️⃣  읽은 리뷰 개수 확인")
    count = await repo.get_read_count()
    print(f"   전체 읽은 리뷰 개수: {count}")

    print("\n6️⃣  추가 읽음 처리 테스트 (중복 포함)")
    additional_marked = await repo.mark_as_read(test_ids[2:], read_by="test_user_2")
    print(f"   추가 처리된 리뷰 개수: {additional_marked}")

    print("\n7️⃣  최종 읽은 리뷰 조회")
    final_read_ids = await repo.get_read_ids(test_ids)
    print(f"   최종 읽은 리뷰 ID: {final_read_ids}")

    print("\n8️⃣  읽음 해제 테스트")
    unmarked = await repo.unmark_as_read(test_ids[:2])
    print(f"   읽음 해제된 리뷰 개수: {unmarked}")

    print("\n9️⃣  해제 후 상태 확인")
    after_unmark = await repo.get_read_ids(test_ids)
    print(f"   현재 읽은 리뷰 ID: {after_unmark}")

    print("\n🔟 최종 개수 확인")
    final_count = await repo.get_read_count()
    print(f"   최종 읽은 리뷰 개수: {final_count}")

    return {
        "initial_count": initial_count,
        "marked": marked,
        "additional_marked": additional_marked,
        "unmarked": unmarked,
        "final_count": final_count,
        "read_ids": list(after_unmark),
    }


def main():
    print("=" * 60)
    print("🧪 Review Read Status Repository 테스트")
    print("=" * 60)

    try:
        result = asyncio.run(test_repository())

        print("\n" + "=" * 60)
        print("✅ 테스트 완료")
        print("=" * 60)
        print(f"\n결과:")
        for key, value in result.items():
            print(f"  - {key}: {value}")

    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ 테스트 실패")
        print("=" * 60)
        print(f"\n에러: {e}")

        if "does not exist" in str(e).lower():
            print("\n⚠️  review_read_status 테이블이 없습니다.")
            print("먼저 MIGRATION_INSTRUCTIONS.md의 SQL을 실행해주세요.")


if __name__ == "__main__":
    main()
