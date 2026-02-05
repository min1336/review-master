"""
Supabase review_read_status 테이블 생성 마이그레이션 스크립트

Usage:
    cd app && python -m scripts.create_review_read_status_table

Description:
    리뷰 읽음 상태 추적을 위한 테이블 생성
    - review_id를 기준으로 읽음 여부 추적
    - read_at: 읽은 시간 자동 기록
    - read_by: 읽은 사용자 정보 (선택)
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
    pass  # dotenv 없으면 환경변수 직접 설정 필요


async def create_table():
    """review_read_status 테이블 생성"""
    from repository.session import get_client

    client = await get_client()

    # SQL 쿼리 실행
    sql = """
    -- review_read_status 테이블 생성
    CREATE TABLE IF NOT EXISTS review_read_status (
        id SERIAL PRIMARY KEY,
        review_id VARCHAR(255) UNIQUE NOT NULL,
        read_at TIMESTAMP DEFAULT now(),
        read_by VARCHAR(100)
    );

    -- 인덱스 생성
    CREATE INDEX IF NOT EXISTS idx_review_read_status_review_id
    ON review_read_status(review_id);
    """

    try:
        # Supabase RPC를 사용하여 SQL 실행
        result = await client.rpc('exec_sql', {'sql': sql}).execute()
        print("✅ review_read_status 테이블 생성 완료")
        print(f"   Result: {result}")
        return {"success": True, "message": "Table created successfully"}
    except Exception as e:
        error_msg = str(e)

        # 테이블이 이미 존재하는 경우
        if "already exists" in error_msg.lower():
            print("ℹ️  review_read_status 테이블이 이미 존재합니다")
            return {"success": True, "message": "Table already exists"}

        # RPC 함수가 없는 경우 - 직접 SQL 실행 시도
        if "function" in error_msg.lower() and "does not exist" in error_msg.lower():
            print("\n⚠️  exec_sql RPC 함수가 없습니다.")
            print("Supabase Dashboard에서 SQL을 직접 실행해주세요:")
            print("\n" + "="*60)
            print(sql)
            print("="*60 + "\n")
            return {"success": False, "message": "Please run SQL manually in Supabase Dashboard"}

        # 기타 에러
        print(f"❌ 테이블 생성 실패: {error_msg}")
        print("\nSupabase Dashboard에서 다음 SQL을 직접 실행해주세요:")
        print("\n" + "="*60)
        print(sql)
        print("="*60 + "\n")
        return {"success": False, "message": error_msg}


def main():
    print("=" * 60)
    print("🔄 review_read_status 테이블 생성 시작")
    print("=" * 60)

    result = asyncio.run(create_table())

    print("\n" + "=" * 60)
    print(f"📊 결과: {result}")
    print("=" * 60)


if __name__ == "__main__":
    main()
