"""
태그 자동 분류 스크립트
키워드 기반으로 tags 테이블의 group_name을 자동 설정

실행: python scripts/categorize_tags.py
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'web'))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

from supabase_client import get_client

# ============================================================
# 태그 그룹 정의 (키워드 → 그룹 매핑)
# ============================================================
TAG_GROUPS = {
    '서비스': {
        'color': '#10b981',
        'keywords': [
            '친절', '응대', '설명', '안내', '배웅', '인사', '서비스', '직원',
            '사장', '대표', '매니저', '상담', '문의', '답변', '연락', '전화',
            '도움', '배려', '센스', '감사', '고마', '만족', '추천', '고객',
            '손님', '여사', '아저씨', '언니', '오빠', '형', '누나', '사모님',
            '기사', '웃음', '미소', '반갑', '환영', '존경', '예의', '공손',
            '정성', '세심', '신경', '케어', '확인', '체크', '점검'
        ]
    },
    '차량': {
        'color': '#3b82f6',
        'keywords': [
            '차량', '상태', '깨끗', '청결', '신차', '연식', '외관', '내부',
            '세차', '냄새', '에어컨', '히터', '네비', '블루투스', '오디오',
            '트렁크', '시트', '핸들', '브레이크', '엔진', '연비', '기름',
            '타이어', '휠', '범퍼', '흠집', '스크래치', '사고', '정비',
            '차', '자동차', '렌트카', '렌터카', '카', '소나타', '아반떼',
            '그랜저', 'K5', 'K3', 'K7', '카니발', '스타렉스', 'SUV',
            '세단', '중형', '소형', '대형', '경차', '모닝', '스파크',
            '가솔린', '디젤', '전기차', '하이브리드', '변속기', '오토',
            '수동', '기어', '악셀', '미러', '백미러', '사이드', '앞유리',
            '뒷유리', '창문', '도어', '문', '열쇠', '키', '스마트키',
            '주행', '운전', '드라이브', '달리', '속도', '안전', '편하',
            '편안', '편리', '쾌적', '넓', '좁', '공간', '안락'
        ]
    },
    '가격': {
        'color': '#f59e0b',
        'keywords': [
            '가격', '가성비', '저렴', '합리', '비용', '할인', '쿠폰',
            '무료', '추가', '요금', '보험', '면책', '결제', '카드',
            '돈', '원', '만원', '싸', '비싸', '적당', '경제', '절약',
            '이득', '손해', '페이', '현금', '계산', '청구', '영수증',
            '정산', '환불', '포인트', '적립', '마일리지'
        ]
    },
    '위치/접근성': {
        'color': '#8b5cf6',
        'keywords': [
            '위치', '접근', '거리', '가까', '공항', '역', '터미널',
            '도보', '버스', '지하철', '교통', '찾기', '네비게이션',
            '지도', '길', '방향', '입구', '출구', '주소', '건물',
            '제주', '인천', '김포', '김해', '대구', '부산', '광주',
            '대전', '울산', '청주', '여수', '강릉', '속초', '경주',
            '전주', '서울', '이동', '도착', '출발'
        ]
    },
    '편의시설': {
        'color': '#ec4899',
        'keywords': [
            '주차', '대기실', '셔틀', '시설', '화장실', '휴게', '음료',
            '커피', '의자', '와이파이', '충전', '간식', '물', '차',
            '소파', '테이블', 'TV', '잡지', '신문', '냉장고', '정수기'
        ]
    },
    '반납/픽업': {
        'color': '#06b6d4',
        'keywords': [
            '반납', '픽업', '인수', '배차', '절차', '수속', '대기',
            '빠른', '신속', '간편', '간단', '복잡', '출고', '입고',
            '전달', '인계', '수령', '탁송', '배달', '마중', '데려다',
            '모셔다', '태워', '내려', '기다', '대기'
        ]
    },
    '예약': {
        'color': '#64748b',
        'keywords': [
            '예약', '확정', '변경', '취소', '앱', '사이트', '홈페이지',
            '예정', '일정', '날짜', '시간', '기간', '연장', '단축'
        ]
    },
    '여행/관광': {
        'color': '#14b8a6',
        'keywords': [
            '여행', '관광', '휴가', '휴일', '연휴', '주말', '출장',
            '가족', '친구', '커플', '신혼', '여정', '일정', '코스',
            '맛집', '명소', '드라이브', '해변', '산', '바다', '섬'
        ]
    }
}

# 미분류 태그를 위한 기본 그룹
DEFAULT_GROUP = {
    'name': '기타',
    'color': '#94a3b8'
}


def classify_tag(tag_name: str) -> tuple:
    """
    태그명을 분석하여 적절한 그룹과 색상 반환
    
    Returns:
        (group_name, color) or (None, None)
    """
    tag_lower = tag_name.lower()
    
    for group_name, config in TAG_GROUPS.items():
        for keyword in config['keywords']:
            if keyword in tag_lower:
                return group_name, config['color']
    
    return None, None


def run_categorization(dry_run: bool = False, include_others: bool = False):
    """
    모든 태그를 분류하고 DB 업데이트
    
    Args:
        dry_run: True면 실제 업데이트 없이 시뮬레이션만
        include_others: True면 미분류 태그도 '기타'로 분류
    """
    client = get_client()
    
    # 그룹 미지정 태그만 조회
    result = client.table('tags').select('id, name, group_name').is_('group_name', 'null').execute()
    unclassified = result.data
    
    print(f"\n📊 미분류 태그: {len(unclassified)}개")
    
    if not unclassified:
        print("✅ 모든 태그가 이미 분류되어 있습니다.")
        return
    
    # 분류 결과 집계
    stats = {g: 0 for g in TAG_GROUPS}
    stats['기타'] = 0
    updates = []
    
    for tag in unclassified:
        group_name, color = classify_tag(tag['name'])
        
        if group_name:
            stats[group_name] += 1
            updates.append({
                'id': tag['id'],
                'group_name': group_name,
                'color': color
            })
        elif include_others:
            # 미분류 태그를 '기타'로 분류
            stats['기타'] += 1
            updates.append({
                'id': tag['id'],
                'group_name': DEFAULT_GROUP['name'],
                'color': DEFAULT_GROUP['color']
            })
        else:
            stats['기타'] += 1
    
    # 결과 출력
    print("\n📋 분류 결과:")
    for group, count in sorted(stats.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"   {group}: {count}개")
    
    if dry_run:
        print(f"\n🔍 Dry run 모드 - 실제 업데이트 없음")
        print(f"   업데이트 예정: {len(updates)}개")
        return
    
    # DB 업데이트
    print(f"\n💾 DB 업데이트 중... ({len(updates)}개)")
    
    success = 0
    for update in updates:
        try:
            client.table('tags').update({
                'group_name': update['group_name'],
                'color': update['color']
            }).eq('id', update['id']).execute()
            success += 1
        except Exception as e:
            print(f"   ⚠️ 업데이트 실패 (ID {update['id']}): {e}")
    
    print(f"\n✅ 완료: {success}/{len(updates)}개 태그 분류됨")
    print(f"   남은 미분류: {stats['기타']}개")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='태그 자동 분류')
    parser.add_argument('--dry-run', action='store_true', help='시뮬레이션 모드 (DB 변경 없음)')
    parser.add_argument('--include-others', action='store_true', help='미분류 태그도 "기타"로 분류')
    args = parser.parse_args()
    
    print("=" * 60)
    print("🏷️  태그 자동 분류 스크립트")
    print("=" * 60)
    
    run_categorization(dry_run=args.dry_run, include_others=args.include_others)

