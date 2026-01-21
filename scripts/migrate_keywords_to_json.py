#!/usr/bin/env python3
"""
키워드 마이그레이션: keyword_1,2,3 → keywords (JSON 배열)

실행 방법:
    python scripts/migrate_keywords_to_json.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from web.supabase_client import get_client


def migrate_keywords():
    """기존 keyword_1,2,3를 keywords JSON 배열로 마이그레이션"""
    client = get_client()
    
    print("🔍 기존 데이터 조회 중...")
    
    # 모든 branch_summaries 조회
    result = client.table('branch_summaries').select(
        'branch_id, keyword_1, keyword_2, keyword_3'
    ).execute()
    
    if not result.data:
        print("❌ 데이터가 없습니다.")
        return
    
    total = len(result.data)
    print(f"📊 총 {total}개 지점 데이터 발견")
    
    updated = 0
    skipped = 0
    
    for row in result.data:
        branch_id = row['branch_id']
        
        # 기존 키워드 수집
        keywords = []
        for i in [1, 2, 3]:
            kw = row.get(f'keyword_{i}')
            if kw and kw.strip():
                keywords.append(kw.strip())
        
        if not keywords:
            skipped += 1
            continue
        
        # keywords JSON 배열로 업데이트
        try:
            client.table('branch_summaries').update({
                'keywords': keywords
            }).eq('branch_id', branch_id).execute()
            
            updated += 1
            print(f"✅ Branch {branch_id}: {keywords}")
        except Exception as e:
            print(f"❌ Branch {branch_id} 실패: {e}")
    
    print("\n" + "="*60)
    print(f"✅ 마이그레이션 완료!")
    print(f"   - 업데이트: {updated}개")
    print(f"   - 스킵: {skipped}개 (키워드 없음)")
    print(f"   - 총: {total}개")
    print("="*60)


def verify_migration():
    """마이그레이션 결과 확인"""
    client = get_client()
    
    print("\n🔍 마이그레이션 결과 확인 중...")
    
    result = client.table('branch_summaries').select(
        'branch_id, branch_name, keywords, keyword_1, keyword_2, keyword_3'
    ).limit(10).execute()
    
    if not result.data:
        print("❌ 데이터가 없습니다.")
        return
    
    print("\n📋 샘플 데이터 (최대 10개):")
    print("-" * 80)
    
    for row in result.data:
        print(f"Branch {row['branch_id']}: {row.get('branch_name', 'N/A')}")
        print(f"  - 기존: [{row.get('keyword_1')}, {row.get('keyword_2')}, {row.get('keyword_3')}]")
        print(f"  - 신규: {row.get('keywords')}")
        print()


if __name__ == '__main__':
    print("="*60)
    print("키워드 마이그레이션: keyword_1,2,3 → keywords (JSON)")
    print("="*60)
    print()
    
    # Step 1: 마이그레이션 실행
    migrate_keywords()
    
    # Step 2: 결과 확인
    verify_migration()
    
    print("\n💡 다음 단계:")
    print("   1. Supabase에서 keywords 컬럼이 제대로 생성되었는지 확인")
    print("   2. 기존 keyword_1,2,3 컬럼은 유지 (백업용)")
    print("   3. 코드에서 keywords 컬럼 사용하도록 수정")
