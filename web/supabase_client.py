"""
Supabase 클라이언트 모듈
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import pandas as pd
from pathlib import Path

# 환경변수 로드 (프로젝트 루트의 .env)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Supabase 설정
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

_client: Client = None

def get_client() -> Client:
    """Supabase 클라이언트 싱글톤"""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY 환경변수가 필요합니다")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client

# ============================================================
# 요약 결과 CRUD
# ============================================================

def get_all_summaries(status: str = None, limit: int = 50, offset: int = 0):
    """전체 요약 목록 조회"""
    client = get_client()
    query = client.table('summaries').select('*')

    if status:
        query = query.eq('status', status)

    query = query.order('branch_id').range(offset, offset + limit - 1)
    result = query.execute()
    return result.data

def get_summary_by_id(summary_id: int):
    """특정 요약 조회"""
    client = get_client()
    result = client.table('summaries').select('*').eq('id', summary_id).single().execute()
    return result.data

def get_summary_by_branch(branch_id: int):
    """지점별 요약 조회"""
    client = get_client()
    result = client.table('summaries').select('*').eq('branch_id', branch_id).execute()
    return result.data[0] if result.data else None

def update_summary(summary_id: int, data: dict):
    """요약 수정"""
    client = get_client()
    data['updated_at'] = 'now()'
    result = client.table('summaries').update(data).eq('id', summary_id).execute()
    return result.data

def update_summary_status(summary_id: int, status: str):
    """요약 상태 변경"""
    return update_summary(summary_id, {'status': status})

def get_summary_stats():
    """요약 통계"""
    client = get_client()

    # 전체 수
    total = client.table('summaries').select('id', count='exact').execute()

    # 상태별 수
    draft = client.table('summaries').select('id', count='exact').eq('status', 'draft').execute()
    approved = client.table('summaries').select('id', count='exact').eq('status', 'approved').execute()
    published = client.table('summaries').select('id', count='exact').eq('status', 'published').execute()

    return {
        'total': total.count or 0,
        'draft': draft.count or 0,
        'approved': approved.count or 0,
        'published': published.count or 0
    }

# ============================================================
# 파이프라인 연동
# ============================================================

def upsert_summary(branch_id: int, ai_summary: str, keywords: list, review_count: int):
    """
    파이프라인에서 요약 결과 저장/업데이트
    - 신규: draft 상태로 저장
    - 기존: ai_summary, keywords, review_count만 업데이트 (status 유지)
    """
    client = get_client()

    # branches 테이블에 upsert (충돌 시 무시)
    try:
        client.table('branches').upsert({
            'branch_id': branch_id,
            'name': f'지점 {branch_id}'
        }, on_conflict='branch_id').execute()
    except Exception:
        pass  # 이미 존재하면 무시

    # 기존 데이터 확인
    existing = get_summary_by_branch(branch_id)

    if existing:
        # 기존 데이터가 있으면 ai_summary, keywords, review_count만 업데이트
        client.table('summaries').update({
            'ai_summary': ai_summary,
            'keywords': keywords,
            'review_count': review_count,
            'updated_at': 'now()'
        }).eq('branch_id', branch_id).execute()
    else:
        # 신규 데이터는 draft로 삽입
        client.table('summaries').insert({
            'branch_id': branch_id,
            'ai_summary': ai_summary,
            'keywords': keywords,
            'review_count': review_count,
            'status': 'draft'
        }).execute()


def upsert_summaries_batch(summaries: list):
    """
    여러 요약 결과를 일괄 저장

    Args:
        summaries: [{'branch_id': int, 'ai_summary': str, 'keywords': list, 'review_count': int}, ...]

    Returns:
        성공 개수
    """
    success_count = 0
    total = len(summaries)

    for i, summary in enumerate(summaries, 1):
        try:
            upsert_summary(
                branch_id=summary['branch_id'],
                ai_summary=summary['ai_summary'],
                keywords=summary['keywords'],
                review_count=summary['review_count']
            )
            success_count += 1

            if i % 50 == 0:
                print(f"   Supabase 저장 중: {i}/{total}")
        except Exception as e:
            print(f"  저장 오류 (지점 {summary.get('branch_id')}): {e}")

    return success_count


# ============================================================
# 데이터 마이그레이션
# ============================================================

def migrate_excel_to_db(excel_path: str = None):
    """Excel 파일을 Supabase로 마이그레이션"""
    client = get_client()

    # 기본 경로
    if excel_path is None:
        project_root = Path(__file__).parent.parent
        excel_path = project_root / 'output' / 'branch_summaries.xlsx'

    if not Path(excel_path).exists():
        raise FileNotFoundError(f"Excel 파일을 찾을 수 없습니다: {excel_path}")

    # Excel 읽기
    df = pd.read_excel(excel_path)
    print(f"Excel에서 {len(df)}개 지점 로드")

    # 기존 데이터 삭제 (선택적)
    # client.table('summaries').delete().neq('id', 0).execute()
    # client.table('branches').delete().neq('id', 0).execute()

    migrated = 0
    for _, row in df.iterrows():
        branch_id = int(row['지점번호'])

        # branches 테이블에 삽입 (이미 있으면 무시)
        try:
            client.table('branches').upsert({
                'branch_id': branch_id,
                'name': f'지점 {branch_id}'
            }).execute()
        except Exception as e:
            print(f"branches 삽입 오류 ({branch_id}): {e}")

        # 키워드 파싱
        keywords_str = str(row.get('TOP3키워드', ''))
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

        # summaries 테이블에 삽입
        try:
            client.table('summaries').upsert({
                'branch_id': branch_id,
                'ai_summary': str(row.get('AI요약', '')),
                'keywords': keywords,
                'review_count': int(row.get('리뷰수', 0)),
                'status': 'draft'
            }, on_conflict='branch_id').execute()
            migrated += 1
        except Exception as e:
            print(f"summaries 삽입 오류 ({branch_id}): {e}")

    print(f"마이그레이션 완료: {migrated}개 지점")
    return migrated

# ============================================================
# 테이블 생성 SQL (참고용)
# ============================================================

CREATE_TABLES_SQL = """
-- 지점 테이블
CREATE TABLE IF NOT EXISTS branches (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 요약 결과 테이블
CREATE TABLE IF NOT EXISTS summaries (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER UNIQUE REFERENCES branches(branch_id),
    ai_summary TEXT,
    edited_summary TEXT,
    keywords JSONB DEFAULT '[]'::jsonb,
    review_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_summaries_branch_id ON summaries(branch_id);
CREATE INDEX IF NOT EXISTS idx_summaries_status ON summaries(status);
"""

# ============================================================
# 스케줄러 설정 CRUD
# ============================================================

def get_scheduler_configs():
    """전체 스케줄러 설정 조회"""
    client = get_client()
    result = client.table('scheduler_config').select('*').order('id').execute()
    return result.data


def get_scheduler_config(config_key: str):
    """특정 스케줄러 설정 조회"""
    client = get_client()
    result = client.table('scheduler_config').select('*').eq('config_key', config_key).single().execute()
    return result.data


def update_scheduler_config(config_key: str, cron_expression: str = None, is_enabled: bool = None, description: str = None):
    """스케줄러 설정 업데이트"""
    client = get_client()

    update_data = {}
    if cron_expression is not None:
        update_data['cron_expression'] = cron_expression
    if is_enabled is not None:
        update_data['is_enabled'] = is_enabled
    if description is not None:
        update_data['description'] = description

    if update_data:
        result = client.table('scheduler_config').update(update_data).eq('config_key', config_key).execute()
        return result.data
    return None


def get_current_season_config():
    """현재 월에 해당하는 스케줄러 설정 반환"""
    from datetime import datetime
    current_month = datetime.now().month

    configs = get_scheduler_configs()
    for config in configs:
        months = config.get('months', '')
        if months:
            month_list = [int(m.strip()) for m in months.split(',')]
            if current_month in month_list:
                return config

    # 기본값: 일반기 설정
    return get_scheduler_config('normal_season')


# ============================================================
# 스케줄러 로그 CRUD
# ============================================================

def create_scheduler_log(config_key: str):
    """스케줄러 실행 로그 생성 (시작)"""
    client = get_client()
    result = client.table('scheduler_logs').insert({
        'config_key': config_key,
        'status': 'running'
    }).execute()
    return result.data[0] if result.data else None


def update_scheduler_log(log_id: int, branch_count: int = 0, success_count: int = 0,
                         fail_count: int = 0, status: str = 'completed', error_message: str = None):
    """스케줄러 실행 로그 업데이트 (완료)"""
    client = get_client()
    result = client.table('scheduler_logs').update({
        'finished_at': 'now()',
        'branch_count': branch_count,
        'success_count': success_count,
        'fail_count': fail_count,
        'status': status,
        'error_message': error_message
    }).eq('id', log_id).execute()
    return result.data


def get_scheduler_logs(limit: int = 20):
    """최근 스케줄러 실행 로그 조회"""
    client = get_client()
    result = client.table('scheduler_logs').select('*').order('started_at', desc=True).limit(limit).execute()
    return result.data


def get_last_run(config_key: str = None):
    """마지막 실행 정보 조회"""
    client = get_client()
    query = client.table('scheduler_logs').select('*').eq('status', 'completed').order('finished_at', desc=True).limit(1)

    if config_key:
        query = query.eq('config_key', config_key)

    result = query.execute()
    return result.data[0] if result.data else None


# ============================================================
# 리뷰 CRUD (감정태그 검색)
# ============================================================

def upsert_reviews_batch(reviews: list) -> int:
    """
    리뷰 일괄 저장 (감정태그 포함)

    Args:
        reviews: [{
            'branch_id': int,
            'content': str,
            'sentiment': str,  # 'positive', 'negative', 'neutral'
            'sentiment_score': float,
            'keywords': list (optional),
            'review_date': str (optional)
        }, ...]

    Returns:
        성공 개수
    """
    client = get_client()
    success_count = 0
    batch_size = 100
    total = len(reviews)

    for i in range(0, total, batch_size):
        batch = reviews[i:i + batch_size]
        try:
            # 배치 삽입
            insert_data = []
            for r in batch:
                insert_data.append({
                    'branch_id': r.get('branch_id') or r.get('지점번호'),
                    'content': r.get('content') or r.get('리뷰내용'),
                    'sentiment': r.get('sentiment'),
                    'sentiment_score': r.get('sentiment_score'),
                    'keywords': r.get('keywords', []),
                    'review_date': r.get('review_date')
                })

            client.table('reviews').insert(insert_data).execute()
            success_count += len(batch)

            if (i + batch_size) % 500 == 0 or (i + batch_size) >= total:
                print(f"   리뷰 저장 중: {min(i + batch_size, total)}/{total}")

        except Exception as e:
            print(f"  리뷰 저장 오류 (batch {i}): {e}")

    return success_count


def search_reviews_by_tag(
    sentiment: str = None,
    branch_id: int = None,
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    감정태그로 리뷰 검색

    Args:
        sentiment: 'positive', 'negative', 'neutral' (None이면 전체)
        branch_id: 지점번호 (None이면 전체)
        limit: 결과 제한 (기본 100)
        offset: 페이지네이션 오프셋

    Returns:
        {
            'reviews': [...],
            'total': int,
            'stats': {'positive': n, 'negative': n, 'neutral': n}
        }
    """
    client = get_client()

    # 기본 쿼리
    query = client.table('reviews').select('*', count='exact')

    # 필터 적용
    if sentiment:
        query = query.eq('sentiment', sentiment)
    if branch_id:
        query = query.eq('branch_id', branch_id)

    # 정렬 및 페이지네이션
    query = query.order('created_at', desc=True).range(offset, offset + limit - 1)

    result = query.execute()

    # 통계 조회
    stats = get_sentiment_stats(branch_id)

    return {
        'reviews': result.data,
        'total': result.count or 0,
        'stats': stats
    }


def get_sentiment_stats(branch_id: int = None) -> dict:
    """
    감정태그별 통계

    Args:
        branch_id: 지점번호 (None이면 전체)

    Returns:
        {'positive': n, 'negative': n, 'neutral': n, 'total': n}
    """
    client = get_client()

    stats = {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0}

    for sentiment in ['positive', 'negative', 'neutral']:
        query = client.table('reviews').select('id', count='exact').eq('sentiment', sentiment)
        if branch_id:
            query = query.eq('branch_id', branch_id)
        result = query.execute()
        stats[sentiment] = result.count or 0

    stats['total'] = stats['positive'] + stats['negative'] + stats['neutral']
    return stats


def delete_reviews_by_branch(branch_id: int) -> int:
    """
    지점별 리뷰 삭제 (재처리 전 정리용)

    Args:
        branch_id: 지점번호

    Returns:
        삭제된 개수
    """
    client = get_client()
    result = client.table('reviews').delete().eq('branch_id', branch_id).execute()
    return len(result.data) if result.data else 0


if __name__ == '__main__':
    # 테스트
    print("Supabase 연결 테스트...")
    client = get_client()
    print(f"연결 성공: {SUPABASE_URL}")

    # 마이그레이션 테스트
    # migrate_excel_to_db()
