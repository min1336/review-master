
import sys
from pathlib import Path
import re
import time
from dotenv import load_dotenv

load_dotenv()

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from web.supabase_client import get_client, get_affiliate_by_index

def extract_region_improved(address: str, branch_name: str = "") -> str:
    """
    주소와 지점명을 기반으로 지역 추출
    """
    # 0. 지점명 기반 해외/공항 우선 처리
    if branch_name:
        overseas_keywords = [
            '괌', 'Guam', '사이판', 'Saipan', '로스앤젤레스', 'Los Angeles', 'LA',
            '오키나와', 'Okinawa', '후쿠오카', 'Fukuoka', '삿포로', 'Sapporo',
            '하와이', 'Hawaii', '다낭', 'Danang', '방콕', 'Bangkok', '세부', 'Cebu',
            '유럽', '미국', '일본'
        ]
        for kw in overseas_keywords:
            if kw in branch_name or kw.lower() in branch_name.lower():
                return "해외"

    # 주소가 없으면 '기타' (지점명에서도 못 찾은 경우)
    if not address:
        return "기타"

    address = address.strip()

    # 1. 명시적 매핑 (우선순위 높음)
    mappings = {
        # 광역시/도
        '서울특별시': '서울', '서울시': '서울', '서울': '서울',
        '부산광역시': '부산', '부산시': '부산', '부산': '부산',
        '대구광역시': '대구', '대구시': '대구', '대구': '대구',
        '인천광역시': '인천', '인천시': '인천', '인천': '인천',
        '광주광역시': '광주', '광주시': '광주', '광주': '광주',
        '대전광역시': '대전', '대전시': '대전', '대전': '대전',
        '울산광역시': '울산', '울산시': '울산', '울산': '울산',
        '세종특별자치시': '세종', '세종시': '세종', '세종': '세종',
        '경기도': '경기', '경기': '경기',
        '강원도': '강원', '강원': '강원', '강원특별자치도': '강원',
        '충청북도': '충북', '충북': '충북',
        '충청남도': '충남', '충남': '충남',
        '전라북도': '전북', '전북': '전북', '전북특별자치도': '전북',
        '전라남도': '전남', '전남': '전남',
        '경상북도': '경북', '경북': '경북',
        '경상남도': '경남', '경남': '경남',
        '제주특별자치도': '제주', '제주시': '제주', '제주도': '제주', '제주': '제주',
        
        # 해외 주소 키워드
        'Guam': '해외', 'GUAM': '해외', '괌': '해외',
        'Saipan': '해외', 'SAIPAN': '해외', '사이판': '해외',
        'Japan': '해외', 'Fukuoka': '해외', 'Sapporo': '해외', 'Okinawa': '해외',
        'Budapest': '해외', 'Hungary': '해외', 'Tinian': '해외',
        'Hotel': '해외', 'Airport': '해외', 'Beach': '해외',
        'USA': '해외', 'CA': '해외', 'Street': '해외', 'Ave': '해외'
    }

    parts = address.split()
    if not parts:
        return "기타"

    first_word = parts[0]
    
    # 2. 첫 단어가 매핑에 있는지 확인
    for key, val in mappings.items():
        if key in first_word or first_word.startswith(key):
            if len(parts) > 1:
                second_word = parts[1]
                if any(second_word.endswith(suffix) for suffix in ['구', '군', '시']):
                    return f"{val} {second_word}"
            return val

    # 3. 매핑 실패 시, 한국 주소인지 확인
    if any(suffix in address for suffix in ['시', '도', '군', '구']):
        return parts[0]

    # 4. 영어로 시작하면 '해외'
    if re.match(r'^[A-Za-z]', address):
        return "해외"

    return "기타"

def fix_regions():
    client = get_client()
    print("Fetching branch_summaries...")
    
    # 지점명까지 가져오기
    response = client.table('branch_summaries').select('branch_id', 'branch_name', 'region').execute()
    branches = response.data
    
    print(f"Found {len(branches)} branches. Starting update...")
    
    updated_count = 0
    
    for branch in branches:
        try:
            branch_id = branch['branch_id']
            branch_name = branch.get('branch_name', '')
            
            # 원본 주소 가져오기
            affiliate = get_affiliate_by_index(branch_id)
            original_address = affiliate.get('address', '') if affiliate else ""
            
            # 개선된 로직으로 지역 추출
            new_region = extract_region_improved(original_address, branch_name)
            
            # 기존 값과 다르면 업데이트
            if branch.get('region') != new_region:
                client.table('branch_summaries').update({'region': new_region}).eq('branch_id', branch_id).execute()
                updated_count += 1
                if updated_count % 10 == 0:
                    print(f"Updated {updated_count} regions...")
            
            time.sleep(0.02) # Fast limit

        except Exception as e:
            print(f"Error updating branch {branch.get('branch_id')}: {e}")
            
    print(f"Done! Updated {updated_count} branches.")

if __name__ == "__main__":
    fix_regions()
