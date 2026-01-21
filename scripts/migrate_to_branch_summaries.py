"""
기존 summaries + affiliates + 원본리뷰 데이터를 새 branch_summaries 테이블로 마이그레이션

실행 전:
1. Supabase에서 scripts/sql/create_branch_summaries_table.sql 실행
2. .env에 SUPABASE_URL, SUPABASE_KEY 설정 확인

사용법:
    python scripts/migrate_to_branch_summaries.py
    python scripts/migrate_to_branch_summaries.py --dry-run  # 테스트 모드
"""
import sys
import argparse
from pathlib import Path

import pandas as pd

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from web.supabase_client import (
    get_client,
    get_all_summaries,
    get_affiliate_by_index,
    upsert_branch_summaries_batch
)

# 원본 리뷰 Excel 경로
REVIEW_EXCEL_PATH = project_root / 'data' / '리뷰리스트_20260109.xlsx'


def extract_region(address: str) -> str:
    """
    주소에서 지역 추출 (시/도 + 구/군)

    예: "서울특별시 강남구 역삼동 123-45" -> "서울 강남구"
    """
    if not address:
        return ""

    # 주소 정규화
    address = address.strip()

    # 시/도 추출
    city_mappings = {
        '서울특별시': '서울',
        '부산광역시': '부산',
        '대구광역시': '대구',
        '인천광역시': '인천',
        '광주광역시': '광주',
        '대전광역시': '대전',
        '울산광역시': '울산',
        '세종특별자치시': '세종',
        '경기도': '경기',
        '강원도': '강원',
        '충청북도': '충북',
        '충청남도': '충남',
        '전라북도': '전북',
        '전라남도': '전남',
        '경상북도': '경북',
        '경상남도': '경남',
        '제주특별자치도': '제주',
    }

    region_parts = []

    # 시/도 찾기
    for full_name, short_name in city_mappings.items():
        if full_name in address:
            region_parts.append(short_name)
            # 구/군/시 찾기
            remaining = address.split(full_name)[-1].strip()
            parts = remaining.split()
            if parts:
                # 첫 번째 행정구역 (구/군/시)
                first_part = parts[0]
                if first_part.endswith(('구', '군', '시')):
                    region_parts.append(first_part)
            break

    return ' '.join(region_parts) if region_parts else address[:20]


def load_branch_ratings(excel_path: Path = None) -> dict:
    """
    원본 리뷰 Excel에서 지점별 평균 평점 계산

    평점 = (지점평점 + 차량평점 + 인수/반납편의성) / 3

    Args:
        excel_path: Excel 파일 경로

    Returns:
        {branch_id: {'avg_rating': float, 'review_count': int}, ...}
    """
    if excel_path is None:
        excel_path = REVIEW_EXCEL_PATH

    if not excel_path.exists():
        print(f"   [경고] Excel 파일 없음: {excel_path}")
        return {}

    print(f"   Excel 로드 중: {excel_path.name}")

    # 필요한 컬럼만 로드
    df = pd.read_excel(
        excel_path,
        usecols=['지점번호', '지점평점(친절/편의성)', '차량평점', '인수/반납편의성']
    )

    # 평점 컬럼들
    rating_cols = ['지점평점(친절/편의성)', '차량평점', '인수/반납편의성']

    # 평점 평균 계산 (각 행에서 3개 평점의 평균)
    df['avg_rating'] = df[rating_cols].mean(axis=1)

    # 유효한 평점만 필터 (NaN 제외)
    df = df.dropna(subset=['avg_rating'])

    # 지점별 집계
    branch_stats = df.groupby('지점번호').agg(
        avg_rating=('avg_rating', 'mean'),
        review_count=('avg_rating', 'count')
    ).round(2)

    # 딕셔너리로 변환
    result = {}
    for branch_id, row in branch_stats.iterrows():
        result[int(branch_id)] = {
            'avg_rating': float(row['avg_rating']),
            'review_count': int(row['review_count'])
        }

    print(f"   - {len(result)}개 지점 평점 로드 완료")
    return result


def migrate_data(dry_run: bool = False):
    """
    기존 데이터를 새 테이블로 마이그레이션

    Args:
        dry_run: True면 실제 저장하지 않고 미리보기만
    """
    client = get_client()
    print("=" * 60)
    print("branch_summaries 테이블 마이그레이션")
    print("=" * 60)

    # 1. 원본 Excel에서 평점 데이터 로드
    print("\n[1/5] 원본 리뷰에서 평점 데이터 로드...")
    branch_ratings = load_branch_ratings()

    # 2. 기존 summaries 데이터 조회
    print("\n[2/5] 기존 summaries 데이터 조회...")
    all_summaries = client.table('summaries').select('*').execute()
    summaries_data = all_summaries.data or []
    print(f"   - 총 {len(summaries_data)}개 레코드")

    # 3. branch_id별로 그룹화 (기간별 요약 통합)
    print("\n[3/5] 지점별 데이터 통합...")
    branch_data = {}

    for row in summaries_data:
        branch_id = row.get('branch_id')
        if not branch_id:
            continue

        if branch_id not in branch_data:
            branch_data[branch_id] = {
                'branch_id': branch_id,
                'review_count': 0,
                'keywords': [],
                'status': 'draft'
            }

        period_type = row.get('period_type', 'all')
        summary_text = row.get('ai_summary') or row.get('edited_summary')

        # 기간별 요약 매핑
        period_mapping = {
            '1m': 'summary_1m',
            '3m': 'summary_3m',
            '6m': 'summary_6m',
            '1y': 'summary_1y',
            'all': 'summary_all'
        }

        if period_type in period_mapping:
            branch_data[branch_id][period_mapping[period_type]] = summary_text

        # 가장 큰 review_count 사용
        if row.get('review_count', 0) > branch_data[branch_id]['review_count']:
            branch_data[branch_id]['review_count'] = row.get('review_count', 0)

        # 키워드 병합
        keywords = row.get('keywords', [])
        if keywords:
            branch_data[branch_id]['keywords'].extend(keywords)

        # status (가장 높은 상태 유지)
        status_priority = {'draft': 1, 'approved': 2, 'published': 3}
        current_status = branch_data[branch_id]['status']
        new_status = row.get('status', 'draft')
        if status_priority.get(new_status, 0) > status_priority.get(current_status, 0):
            branch_data[branch_id]['status'] = new_status

    print(f"   - {len(branch_data)}개 지점으로 통합")

    # 4. affiliates에서 업체명, 지역 + 평점 데이터 적용
    print("\n[4/5] affiliates에서 업체 정보 + 평점 데이터 적용...")
    enriched_count = 0

    rating_count = 0
    for branch_id, data in branch_data.items():
        affiliate = get_affiliate_by_index(branch_id)

        if affiliate:
            data['branch_name'] = affiliate.get('name', '')
            data['region'] = extract_region(affiliate.get('address', ''))
            enriched_count += 1
        else:
            data['branch_name'] = f'지점 {branch_id}'
            data['region'] = ''

        # 평점 데이터 적용
        if branch_id in branch_ratings:
            rating_info = branch_ratings[branch_id]
            data['avg_rating'] = rating_info['avg_rating']
            # review_count는 더 큰 값 사용 (기존 summaries vs Excel)
            if rating_info['review_count'] > data.get('review_count', 0):
                data['review_count'] = rating_info['review_count']
            rating_count += 1

        # 키워드 정리 (중복 제거, TOP 3)
        keywords = list(dict.fromkeys(data.pop('keywords', [])))[:3]
        data['keyword_1'] = keywords[0] if len(keywords) > 0 else None
        data['keyword_2'] = keywords[1] if len(keywords) > 1 else None
        data['keyword_3'] = keywords[2] if len(keywords) > 2 else None

    print(f"   - {enriched_count}개 지점 업체정보 매칭")
    print(f"   - {rating_count}개 지점 평점 데이터 적용")

    # 5. 새 테이블에 저장
    print("\n[5/5] branch_summaries 테이블에 저장...")

    if dry_run:
        print("\n[DRY RUN] 실제 저장하지 않음. 미리보기:")
        for i, (branch_id, data) in enumerate(list(branch_data.items())[:5]):
            print(f"\n   지점 {branch_id}:")
            print(f"      업체명: {data.get('branch_name')}")
            print(f"      지역: {data.get('region')}")
            print(f"      리뷰수: {data.get('review_count')}")
            print(f"      평균평점: {data.get('avg_rating', 'N/A')}")
            print(f"      키워드: {data.get('keyword_1')}, {data.get('keyword_2')}, {data.get('keyword_3')}")
            print(f"      요약(all): {(data.get('summary_all') or '')[:50]}...")
        print(f"\n   ... 외 {len(branch_data) - 5}개 지점")
    else:
        summaries_list = list(branch_data.values())
        success = upsert_branch_summaries_batch(summaries_list)
        print(f"   - {success}/{len(summaries_list)}개 저장 완료")

    print("\n" + "=" * 60)
    print("마이그레이션 완료!")
    print("=" * 60)

    return branch_data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='branch_summaries 마이그레이션')
    parser.add_argument('--dry-run', action='store_true', help='실제 저장하지 않고 미리보기만')
    args = parser.parse_args()

    migrate_data(dry_run=args.dry_run)
