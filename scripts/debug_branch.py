
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from web.supabase_client import get_client, get_affiliate_by_index

def debug_branch():
    client = get_client()
    # '로스앤젤레스' 또는 '달러'가 포함된 지점 검색
    res = client.table('branch_summaries').select('*').ilike('branch_name', '%로스앤젤레스%').execute()
    
    if not res.data:
        print("No branch found with name '%로스앤젤레스%'")
        # 달러로 재검색
        res = client.table('branch_summaries').select('*').ilike('branch_name', '%달러%').execute()

    print(f"Found {len(res.data)} branches:")
    
    for item in res.data:
        aff = get_affiliate_by_index(item['branch_id'])
        print("-" * 40)
        print(f"ID: {item['branch_id']}")
        print(f"Name: {item['branch_name']}")
        print(f"Region (Current DB): {item['region']}")
        if aff:
            print(f"Original Address: {aff.get('address')}")
        else:
            print("Original Address: None")

if __name__ == "__main__":
    debug_branch()
