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
# 감정태그 통계 CRUD
# ============================================================

def upsert_sentiment_stats(stats_list: list) -> int:
    """
    지점별 감정태그 통계 저장

    Args:
        stats_list: [{
            'branch_id': int,
            'positive_count': int,
            'negative_count': int,
            'neutral_count': int
        }, ...]

    Returns:
        성공 개수
    """
    client = get_client()
    success_count = 0

    for stat in stats_list:
        try:
            total = stat['positive_count'] + stat['negative_count'] + stat['neutral_count']
            positive_ratio = (stat['positive_count'] / total * 100) if total > 0 else 0
            negative_ratio = (stat['negative_count'] / total * 100) if total > 0 else 0

            client.table('branch_sentiment_stats').upsert({
                'branch_id': stat['branch_id'],
                'positive_count': stat['positive_count'],
                'negative_count': stat['negative_count'],
                'neutral_count': stat['neutral_count'],
                'total_count': total,
                'positive_ratio': round(positive_ratio, 2),
                'negative_ratio': round(negative_ratio, 2),
                'updated_at': 'now()'
            }, on_conflict='branch_id').execute()
            success_count += 1
        except Exception as e:
            print(f"  통계 저장 오류 (지점 {stat.get('branch_id')}): {e}")

    return success_count


def get_sentiment_stats(branch_id: int = None) -> dict:
    """
    감정태그별 통계 조회

    Args:
        branch_id: 지점번호 (None이면 전체 합계)

    Returns:
        {'positive': n, 'negative': n, 'neutral': n, 'total': n, 'positive_ratio': %, 'negative_ratio': %}
    """
    client = get_client()

    if branch_id:
        # 특정 지점
        result = client.table('branch_sentiment_stats').select('*').eq('branch_id', branch_id).execute()
        if result.data:
            row = result.data[0]
            return {
                'positive': row['positive_count'],
                'negative': row['negative_count'],
                'neutral': row['neutral_count'],
                'total': row['total_count'],
                'positive_ratio': float(row['positive_ratio']),
                'negative_ratio': float(row['negative_ratio'])
            }
    else:
        # 전체 합계
        result = client.table('branch_sentiment_stats').select('*').execute()
        if result.data:
            totals = {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0}
            for row in result.data:
                totals['positive'] += row['positive_count']
                totals['negative'] += row['negative_count']
                totals['neutral'] += row['neutral_count']
                totals['total'] += row['total_count']

            if totals['total'] > 0:
                totals['positive_ratio'] = round(totals['positive'] / totals['total'] * 100, 2)
                totals['negative_ratio'] = round(totals['negative'] / totals['total'] * 100, 2)
            else:
                totals['positive_ratio'] = 0
                totals['negative_ratio'] = 0
            return totals

    return {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0, 'positive_ratio': 0, 'negative_ratio': 0}


def get_all_sentiment_stats() -> list:
    """전체 지점 감정통계 목록"""
    client = get_client()
    result = client.table('branch_sentiment_stats').select('*').order('branch_id').execute()
    return result.data


# ============================================================
# 최근 리뷰 CRUD (1개월치만 유지)
# ============================================================

def upsert_recent_reviews(reviews: list) -> int:
    """
    최근 리뷰 저장 (1개월치만 유지용)

    Args:
        reviews: [{
            'branch_id': int,
            'content': str,
            'sentiment': str,
            'sentiment_score': float,
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
            insert_data = []
            for r in batch:
                insert_data.append({
                    'branch_id': r.get('branch_id') or r.get('지점번호'),
                    'content': r.get('content') or r.get('리뷰내용'),
                    'sentiment': r.get('sentiment'),
                    'sentiment_score': r.get('sentiment_score'),
                    'review_date': r.get('review_date')
                })

            client.table('recent_reviews').insert(insert_data).execute()
            success_count += len(batch)

            if (i + batch_size) % 500 == 0 or (i + batch_size) >= total:
                print(f"   최근 리뷰 저장 중: {min(i + batch_size, total)}/{total}")

        except Exception as e:
            print(f"  리뷰 저장 오류 (batch {i}): {e}")

    return success_count


def search_recent_reviews(
    sentiment: str = None,
    branch_id: int = None,
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    최근 리뷰 검색 (1개월치)

    Args:
        sentiment: 'positive', 'negative', 'neutral' (None이면 전체)
        branch_id: 지점번호 (None이면 전체)
        limit: 결과 제한 (기본 100)
        offset: 페이지네이션 오프셋

    Returns:
        {
            'reviews': [...],
            'total': int,
            'stats': {...}
        }
    """
    client = get_client()

    query = client.table('recent_reviews').select('*', count='exact')

    if sentiment:
        query = query.eq('sentiment', sentiment)
    if branch_id:
        query = query.eq('branch_id', branch_id)

    query = query.order('created_at', desc=True).range(offset, offset + limit - 1)
    result = query.execute()

    # 통계는 branch_sentiment_stats에서 조회
    stats = get_sentiment_stats(branch_id)

    return {
        'reviews': result.data,
        'total': result.count or 0,
        'stats': stats
    }


def cleanup_old_reviews(days: int = 30) -> int:
    """
    오래된 리뷰 삭제 (1개월 이전)

    Args:
        days: 보관 기간 (기본 30일)

    Returns:
        삭제된 개수
    """
    client = get_client()
    from datetime import datetime, timedelta

    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    result = client.table('recent_reviews').delete().lt('created_at', cutoff_date).execute()
    return len(result.data) if result.data else 0


def cleanup_excess_reviews_per_branch(max_per_branch: int = 30) -> int:
    """
    지점당 리뷰 수 제한 (최신 N개만 유지)

    Args:
        max_per_branch: 지점당 최대 리뷰 수 (기본 30개)

    Returns:
        삭제된 총 개수
    """
    client = get_client()
    deleted_count = 0

    # 모든 지점 조회
    branches_result = client.table('recent_reviews').select('branch_id').execute()
    if not branches_result.data:
        return 0

    # 고유 지점 목록
    branch_ids = list(set(r['branch_id'] for r in branches_result.data if r.get('branch_id')))

    for branch_id in branch_ids:
        # 해당 지점의 리뷰를 최신순으로 조회
        reviews = client.table('recent_reviews').select('id').eq(
            'branch_id', branch_id
        ).order('created_at', desc=True).execute()

        if reviews.data and len(reviews.data) > max_per_branch:
            # 초과분의 ID 목록
            ids_to_delete = [r['id'] for r in reviews.data[max_per_branch:]]

            for review_id in ids_to_delete:
                client.table('recent_reviews').delete().eq('id', review_id).execute()
                deleted_count += 1

    return deleted_count


def cleanup_reviews(days: int = 30, max_per_branch: int = 30) -> dict:
    """
    리뷰 정리 (1개월 이전 삭제 + 지점당 30개 제한)

    Args:
        days: 보관 기간 (기본 30일)
        max_per_branch: 지점당 최대 리뷰 수 (기본 30개)

    Returns:
        {'old_deleted': int, 'excess_deleted': int, 'total': int}
    """
    old_deleted = cleanup_old_reviews(days)
    excess_deleted = cleanup_excess_reviews_per_branch(max_per_branch)

    return {
        'old_deleted': old_deleted,
        'excess_deleted': excess_deleted,
        'total': old_deleted + excess_deleted
    }


# ============================================================
# 업체/차량 정보 캐시 (Data Enrichment)
# ============================================================

def upsert_affiliates(affiliates: list) -> int:
    """
    제휴사(업체) 정보 일괄 저장/업데이트

    Args:
        affiliates: 업체 정보 리스트
            [{'affiliate_index': 123, 'name': '업체명', 'location_type': 'PARTNERS', ...}, ...]

    Returns:
        저장된 개수
    """
    if not affiliates:
        return 0

    client = get_client()

    # 데이터 정규화
    rows = []
    for aff in affiliates:
        row = {
            'affiliate_index': aff.get('affiliate_index') or aff.get('affiliateIndex'),
            'name': aff.get('name') or aff.get('affiliateName', ''),
            'location_type': aff.get('location_type') or aff.get('locationType', 'PARTNERS'),
            'address': aff.get('address', ''),
            'phone': aff.get('phone', ''),
            'latitude': aff.get('latitude'),
            'longitude': aff.get('longitude'),
            'is_active': aff.get('is_active', True),
            'raw_data': aff  # 원본 데이터 저장
        }
        if row['affiliate_index']:
            rows.append(row)

    if not rows:
        return 0

    result = client.table('affiliates').upsert(
        rows,
        on_conflict='affiliate_index'
    ).execute()

    return len(result.data) if result.data else 0


def get_affiliate_by_index(affiliate_index: int):
    """특정 업체 정보 조회"""
    client = get_client()
    result = client.table('affiliates').select('*').eq('affiliate_index', affiliate_index).execute()
    return result.data[0] if result.data else None


def get_all_affiliates(location_type: str = None, is_active: bool = True):
    """
    전체 업체 목록 조회

    Args:
        location_type: 위치 타입 필터 (PARTNERS, JEJU, GLOBAL)
        is_active: 활성 상태 필터

    Returns:
        업체 목록
    """
    client = get_client()
    query = client.table('affiliates').select('*')

    if location_type:
        query = query.eq('location_type', location_type)
    if is_active is not None:
        query = query.eq('is_active', is_active)

    result = query.order('name').execute()
    return result.data


def upsert_car_models(car_models: list) -> int:
    """
    차종 정보 일괄 저장/업데이트

    Args:
        car_models: 차종 정보 리스트
            [{'model_id': 'MDL001', 'name': '아반떼', 'category': '소형', ...}, ...]

    Returns:
        저장된 개수
    """
    if not car_models:
        return 0

    client = get_client()

    # 데이터 정규화
    rows = []
    for model in car_models:
        row = {
            'model_id': model.get('model_id') or model.get('modelId') or model.get('id'),
            'name': model.get('name') or model.get('modelName', ''),
            'name_en': model.get('name_en') or model.get('nameEn', ''),
            'category': model.get('category') or model.get('carCategory', ''),
            'brand': model.get('brand') or model.get('manufacturer', ''),
            'seats': model.get('seats') or model.get('maxPassengers'),
            'fuel_type': model.get('fuel_type') or model.get('fuelType', ''),
            'transmission': model.get('transmission', ''),
            'image_url': model.get('image_url') or model.get('imageUrl', ''),
            'raw_data': model  # 원본 데이터 저장
        }
        if row['model_id']:
            rows.append(row)

    if not rows:
        return 0

    result = client.table('car_models').upsert(
        rows,
        on_conflict='model_id'
    ).execute()

    return len(result.data) if result.data else 0


def get_car_model_by_id(model_id: str):
    """특정 차종 정보 조회"""
    client = get_client()
    result = client.table('car_models').select('*').eq('model_id', model_id).execute()
    return result.data[0] if result.data else None


def get_all_car_models(category: str = None):
    """
    전체 차종 목록 조회

    Args:
        category: 차종 카테고리 필터 (소형, 중형, 대형, SUV 등)

    Returns:
        차종 목록
    """
    client = get_client()
    query = client.table('car_models').select('*')

    if category:
        query = query.eq('category', category)

    result = query.order('name').execute()
    return result.data


def sync_affiliates_from_api(api_client) -> dict:
    """
    Carmore API에서 업체 정보를 동기화

    Args:
        api_client: CarmoreAPIClient 인스턴스

    Returns:
        동기화 결과 {'total': int, 'success': int, 'error': str}
    """
    from datetime import datetime

    result = {'total': 0, 'success': 0, 'error': None, 'synced_at': datetime.now().isoformat()}

    try:
        # PARTNERS 타입 업체 조회
        response = api_client.get_affiliates(location_type="PARTNERS")
        if not response.success:
            result['error'] = response.error
            return result

        # Carmore API 응답: {"affiliates": [...]}
        if isinstance(response.data, dict):
            affiliates = response.data.get('affiliates', [])
        elif isinstance(response.data, list):
            affiliates = response.data
        else:
            affiliates = []
        result['total'] = len(affiliates)

        if affiliates:
            # affiliate_index 필드 매핑
            # Carmore API 응답: {id, companyId, name, location: {address, latitude, longitude}, tel: {number}}
            normalized = []
            for aff in affiliates:
                location = aff.get('location') or {}
                tel = aff.get('tel') or {}

                normalized.append({
                    'affiliate_index': int(aff.get('id')) if aff.get('id') else None,
                    'name': aff.get('name', ''),
                    'location_type': 'PARTNERS',
                    'address': location.get('address', ''),
                    'phone': tel.get('number', ''),
                    'latitude': float(location.get('latitude')) if location.get('latitude') else None,
                    'longitude': float(location.get('longitude')) if location.get('longitude') else None,
                    'is_active': True,
                    'raw_data': aff
                })

            result['success'] = upsert_affiliates(normalized)

    except Exception as e:
        result['error'] = str(e)

    return result


def sync_car_models_from_api(api_client) -> dict:
    """
    Carmore API에서 차종 정보를 동기화

    Args:
        api_client: CarmoreAPIClient 인스턴스

    Returns:
        동기화 결과 {'total': int, 'success': int, 'error': str}
    """
    from datetime import datetime

    result = {'total': 0, 'success': 0, 'error': None, 'synced_at': datetime.now().isoformat()}

    try:
        response = api_client.get_car_models()
        if not response.success:
            result['error'] = response.error
            return result

        models = response.data if isinstance(response.data, list) else []
        result['total'] = len(models)

        if models:
            result['success'] = upsert_car_models(models)

    except Exception as e:
        result['error'] = str(e)

    return result


def get_enriched_branch_info(branch_id: int) -> dict:
    """
    지점 정보 + 업체 정보 + 요약 정보를 통합 조회

    Args:
        branch_id: 지점 ID

    Returns:
        통합 정보 딕셔너리
    """
    result = {
        'branch_id': branch_id,
        'affiliate': None,
        'summary': None,
        'sentiment_stats': None,
        'keywords': None
    }

    # 업체 정보
    result['affiliate'] = get_affiliate_by_index(branch_id)

    # 요약 정보 (branch_summaries 테이블 사용)
    result['summary'] = get_branch_summary(branch_id)

    # 감정통계
    result['sentiment_stats'] = get_sentiment_stats(branch_id)

    # 키워드 (branch_summaries 테이블에서 - JSON 배열 우선)
    if result['summary']:
        # keywords JSON 배열이 있으면 사용
        if result['summary'].get('keywords'):
            result['keywords'] = result['summary']['keywords']
        else:
            # 없으면 기존 keyword_1,2,3에서 가져오기 (하위 호환)
            result['keywords'] = [
                result['summary'].get('keyword_1'),
                result['summary'].get('keyword_2'),
                result['summary'].get('keyword_3')
            ]
            result['keywords'] = [k for k in result['keywords'] if k]

    return result


# ============================================================
# 카테고리 CRUD
# ============================================================

def get_all_categories(is_active: bool = True) -> list:
    """전체 카테고리 목록 조회"""
    client = get_client()
    query = client.table('categories').select('*')

    if is_active is not None:
        query = query.eq('is_active', is_active)

    result = query.order('display_order').execute()
    return result.data


def get_category_by_id(category_id: int) -> dict:
    """특정 카테고리 조회"""
    client = get_client()
    result = client.table('categories').select('*').eq('id', category_id).single().execute()
    return result.data


def create_category(data: dict) -> dict:
    """
    카테고리 생성

    Args:
        data: {'name': str, 'description': str, 'color': str, 'display_order': int}

    Returns:
        생성된 카테고리
    """
    client = get_client()
    result = client.table('categories').insert({
        'name': data['name'],
        'description': data.get('description', ''),
        'color': data.get('color', '#667eea'),
        'display_order': data.get('display_order', 0),
        'is_active': data.get('is_active', True)
    }).execute()
    return result.data[0] if result.data else None


def update_category(category_id: int, data: dict) -> dict:
    """
    카테고리 수정

    Args:
        category_id: 카테고리 ID
        data: 수정할 필드들

    Returns:
        수정된 카테고리
    """
    client = get_client()
    data['updated_at'] = 'now()'
    result = client.table('categories').update(data).eq('id', category_id).execute()
    return result.data[0] if result.data else None


def delete_category(category_id: int) -> bool:
    """
    카테고리 삭제 (소속 태그는 미분류로)

    Args:
        category_id: 카테고리 ID

    Returns:
        성공 여부
    """
    client = get_client()

    # 소속 태그의 category_id를 NULL로 변경
    client.table('tags').update({'category_id': None}).eq('category_id', category_id).execute()

    # 카테고리 삭제
    result = client.table('categories').delete().eq('id', category_id).execute()
    return len(result.data) > 0 if result.data else False


# ============================================================
# 태그 CRUD
# ============================================================

def get_all_tags(category_id: int = None, sentiment: str = None, is_active: bool = True, group_name: str = None) -> list:
    """
    태그 목록 조회

    Args:
        category_id: 카테고리 필터 (deprecated, use group_name)
        sentiment: 감정 필터 ('positive', 'negative', 'neutral')
        is_active: 활성 상태 필터
        group_name: 그룹명 필터 (예: '서비스', '차량')

    Returns:
        태그 목록
    """
    client = get_client()
    query = client.table('tags').select('*')

    if group_name:
        query = query.eq('group_name', group_name)
    elif category_id is not None:
        # 하위 호환: category_id로 필터링 시 categories 테이블 조인
        query = client.table('tags').select('*, categories(id, name, color)')
        query = query.eq('category_id', category_id)
    if sentiment:
        query = query.eq('sentiment', sentiment)
    if is_active is not None:
        query = query.eq('is_active', is_active)

    result = query.order('name').execute()
    return result.data


def get_tag_by_id(tag_id: int) -> dict:
    """특정 태그 조회"""
    client = get_client()
    result = client.table('tags').select('*, categories(id, name, color)').eq('id', tag_id).single().execute()
    return result.data


def get_tag_by_name(name: str) -> dict:
    """태그명으로 조회"""
    client = get_client()
    result = client.table('tags').select('*').eq('name', name).execute()
    return result.data[0] if result.data else None


def create_tag(data: dict) -> dict:
    """
    태그 생성

    Args:
        data: {
            'name': str,
            'group_name': str (예: '서비스', '차량'),
            'color': str (예: '#10b981'),
            'sentiment': str,
            'category_id': int (deprecated)
        }

    Returns:
        생성된 태그
    """
    client = get_client()
    insert_data = {
        'name': data['name'],
        'sentiment': data.get('sentiment', 'positive'),
        'is_active': data.get('is_active', True)
    }

    # group_name과 color 지원
    if 'group_name' in data:
        insert_data['group_name'] = data['group_name']
    if 'color' in data:
        insert_data['color'] = data['color']

    # 하위 호환: category_id도 지원
    if 'category_id' in data:
        insert_data['category_id'] = data['category_id']

    result = client.table('tags').insert(insert_data).execute()
    return result.data[0] if result.data else None


def update_tag(tag_id: int, data: dict) -> dict:
    """
    태그 수정

    Args:
        tag_id: 태그 ID
        data: 수정할 필드들

    Returns:
        수정된 태그
    """
    client = get_client()
    data['updated_at'] = 'now()'
    result = client.table('tags').update(data).eq('id', tag_id).execute()
    return result.data[0] if result.data else None


def delete_tag(tag_id: int) -> bool:
    """
    태그 삭제 (연결된 매핑도 함께 삭제)

    Args:
        tag_id: 태그 ID

    Returns:
        성공 여부
    """
    client = get_client()
    result = client.table('tags').delete().eq('id', tag_id).execute()
    return len(result.data) > 0 if result.data else False


def get_or_create_tag(name: str, category_id: int = None, sentiment: str = 'positive') -> dict:
    """
    태그 조회 또는 생성

    Args:
        name: 태그명
        category_id: 카테고리 ID
        sentiment: 감정 ('positive', 'negative', 'neutral')

    Returns:
        태그 정보
    """
    existing = get_tag_by_name(name)
    if existing:
        return existing

    return create_tag({
        'name': name,
        'category_id': category_id,
        'sentiment': sentiment
    })


# ============================================================
# 키워드-태그 매핑 CRUD
# ============================================================

def get_keyword_mappings(tag_id: int = None, keyword: str = None) -> list:
    """
    키워드-태그 매핑 목록 조회

    Args:
        tag_id: 태그 ID로 필터
        keyword: 키워드로 필터

    Returns:
        매핑 목록 (태그 정보 포함)
    """
    client = get_client()
    query = client.table('keyword_tag_mappings').select('*, tags(id, name, category_id, sentiment)')

    if tag_id is not None:
        query = query.eq('tag_id', tag_id)
    if keyword:
        query = query.eq('keyword', keyword)

    result = query.order('keyword').execute()
    return result.data


def create_keyword_mapping(keyword: str, tag_id: int, is_auto: bool = True, confidence: float = 1.0) -> dict:
    """
    키워드 → 태그 매핑 생성

    Args:
        keyword: 키워드
        tag_id: 태그 ID
        is_auto: 자동 생성 여부
        confidence: 매핑 신뢰도 (0~1)

    Returns:
        생성된 매핑
    """
    client = get_client()
    result = client.table('keyword_tag_mappings').upsert({
        'keyword': keyword,
        'tag_id': tag_id,
        'is_auto': is_auto,
        'confidence': confidence
    }, on_conflict='keyword,tag_id').execute()
    return result.data[0] if result.data else None


def delete_keyword_mapping(mapping_id: int) -> bool:
    """매핑 삭제"""
    client = get_client()
    result = client.table('keyword_tag_mappings').delete().eq('id', mapping_id).execute()
    return len(result.data) > 0 if result.data else False


def delete_keyword_mapping_by_keyword(keyword: str, tag_id: int) -> bool:
    """키워드와 태그 ID로 매핑 삭제"""
    client = get_client()
    result = client.table('keyword_tag_mappings').delete().eq('keyword', keyword).eq('tag_id', tag_id).execute()
    return len(result.data) > 0 if result.data else False


def get_unmapped_keywords(limit: int = 100) -> list:
    """
    매핑되지 않은 키워드 목록 조회

    branch_keywords 테이블에서 keyword_tag_mappings에 없는 키워드 반환

    Returns:
        미매핑 키워드 목록 [{'keyword': str, 'count': int}, ...]
    """
    client = get_client()

    # branch_keywords에서 모든 키워드 가져오기
    all_keywords_result = client.table('branch_keywords').select('keyword').execute()
    all_keywords = set(row['keyword'] for row in all_keywords_result.data) if all_keywords_result.data else set()

    # 이미 매핑된 키워드 가져오기
    mapped_result = client.table('keyword_tag_mappings').select('keyword').execute()
    mapped_keywords = set(row['keyword'] for row in mapped_result.data) if mapped_result.data else set()

    # 미매핑 키워드
    unmapped = all_keywords - mapped_keywords

    # 빈도수 조회
    result = []
    for kw in list(unmapped)[:limit]:
        count_result = client.table('branch_keywords').select('id', count='exact').eq('keyword', kw).execute()
        result.append({
            'keyword': kw,
            'count': count_result.count or 0
        })

    # 빈도수 내림차순 정렬
    result.sort(key=lambda x: x['count'], reverse=True)
    return result


def bulk_create_keyword_mappings(mappings: list) -> int:
    """
    키워드 매핑 일괄 생성

    Args:
        mappings: [{'keyword': str, 'tag_id': int, 'is_auto': bool}, ...]

    Returns:
        성공 개수
    """
    client = get_client()
    success_count = 0

    for mapping in mappings:
        try:
            client.table('keyword_tag_mappings').upsert({
                'keyword': mapping['keyword'],
                'tag_id': mapping['tag_id'],
                'is_auto': mapping.get('is_auto', True),
                'confidence': mapping.get('confidence', 1.0)
            }, on_conflict='keyword,tag_id').execute()
            success_count += 1
        except Exception as e:
            print(f"  매핑 저장 오류 ({mapping.get('keyword')}): {e}")

    return success_count


# ============================================================
# 지점별 태그 집계
# ============================================================

def get_branch_tags(branch_id: int, period_type: str = 'all', limit: int = 10) -> list:
    """
    지점별 태그 목록 조회

    Args:
        branch_id: 지점 ID
        period_type: 기간 타입 ('all', '1m', '3m', '6m', '1y')
        limit: 상위 N개

    Returns:
        태그 목록 (태그 정보 + 카테고리 정보 포함)
    """
    client = get_client()
    result = client.table('branch_tags').select(
        '*, tags(id, name, sentiment, categories(id, name, color))'
    ).eq('branch_id', branch_id).eq('period_type', period_type).order('count', desc=True).limit(limit).execute()
    return result.data


def upsert_branch_tags(branch_id: int, period_type: str, tags_data: list) -> int:
    """
    지점별 태그 집계 저장

    Args:
        branch_id: 지점 ID
        period_type: 기간 타입
        tags_data: [{'tag_id': int, 'count': int, 'weighted_score': float, 'rank': int}, ...]

    Returns:
        저장 개수
    """
    client = get_client()
    success_count = 0

    for tag in tags_data:
        try:
            client.table('branch_tags').upsert({
                'branch_id': branch_id,
                'tag_id': tag['tag_id'],
                'period_type': period_type,
                'count': tag.get('count', 0),
                'weighted_score': tag.get('weighted_score', 0),
                'rank': tag.get('rank')
            }, on_conflict='branch_id,tag_id,period_type').execute()
            success_count += 1
        except Exception as e:
            print(f"  지점 태그 저장 오류 ({branch_id}, {tag.get('tag_id')}): {e}")

    return success_count


# ============================================================
# 기간별 요약 저장 (branch_summaries 테이블)
# ============================================================

def upsert_summary_with_period(
    branch_id: int,
    period_type: str,
    ai_summary: str,
    keywords: list,
    review_count: int,
    period_start: str = None,
    period_end: str = None
) -> dict:
    """
    기간별 요약 저장/업데이트 (branch_summaries 테이블 사용)

    Args:
        branch_id: 지점 ID
        period_type: 기간 타입 ('all', '1m', '3m', '6m', '1y')
        ai_summary: AI 생성 요약
        keywords: 키워드 리스트
        review_count: 리뷰 수
        period_start: 기간 시작일 (미사용)
        period_end: 기간 종료일 (미사용)

    Returns:
        저장된 요약
    """
    client = get_client()

    # branches 테이블에 upsert
    try:
        client.table('branches').upsert({
            'branch_id': branch_id,
            'name': f'지점 {branch_id}'
        }, on_conflict='branch_id').execute()
    except Exception:
        pass

    # period_type에 따른 컬럼명 결정
    summary_col = f'summary_{period_type}'  # summary_all, summary_1m, ...

    # 업데이트 데이터 구성
    update_data = {
        summary_col: ai_summary,
        'review_count': review_count,
        'updated_at': 'now()'
    }

    # all 기간인 경우 키워드도 저장 (JSON 배열로)
    if period_type == 'all' and keywords:
        update_data['keywords'] = keywords  # JSON 배열로 저장
        # 하위 호환성을 위해 keyword_1,2,3도 유지
        update_data['keyword_1'] = keywords[0] if len(keywords) > 0 else None
        update_data['keyword_2'] = keywords[1] if len(keywords) > 1 else None
        update_data['keyword_3'] = keywords[2] if len(keywords) > 2 else None

    # 기존 데이터 확인
    existing = client.table('branch_summaries').select('id').eq('branch_id', branch_id).execute()

    if existing.data:
        # 업데이트
        result = client.table('branch_summaries').update(update_data).eq('branch_id', branch_id).execute()
    else:
        # 신규 삽입
        update_data['branch_id'] = branch_id
        update_data['status'] = 'draft'
        result = client.table('branch_summaries').insert(update_data).execute()

    return result.data[0] if result.data else None


# ============================================================
# 통합 요약 테이블 (branch_summaries) CRUD
# ============================================================

def get_all_branch_summaries(
    status: str = None,
    region: str = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = 'branch_id',
    order: str = 'asc',
    min_reviews: int = 30
) -> list:
    """
    전체 지점 요약 목록 조회

    Args:
        status: 상태 필터 ('draft', 'approved', 'published')
        region: 지역 필터
        limit: 결과 제한
        offset: 페이지네이션 오프셋
        sort_by: 정렬 필드 (branch_id, review_count, avg_rating, updated_at)
        order: 정렬 순서 (asc, desc)
        min_reviews: 최소 리뷰 수 (기본 30, 0이면 필터 없음)

    Returns:
        지점 요약 목록
    """
    client = get_client()
    query = client.table('branch_summaries').select('*')

    # 최소 리뷰 수 필터 (0이면 필터링 안함)
    if min_reviews > 0:
        query = query.gte('review_count', min_reviews)

    if status:
        query = query.eq('status', status)
    if region:
        query = query.ilike('region', f'%{region}%')

    # 정렬 적용
    is_desc = order.lower() == 'desc'
    query = query.order(sort_by, desc=is_desc)
    
    # 페이지네이션
    query = query.range(offset, offset + limit - 1)
    
    result = query.execute()
    return result.data


def get_branch_summary(branch_id: int) -> dict:
    """
    특정 지점 요약 조회

    Args:
        branch_id: 지점 번호

    Returns:
        지점 요약 정보
    """
    client = get_client()
    result = client.table('branch_summaries').select('*').eq('branch_id', branch_id).execute()
    return result.data[0] if result.data else None


def upsert_branch_summary(data: dict) -> dict:
    """
    지점 요약 저장/업데이트

    Args:
        data: {
            'branch_id': int,           # 필수
            'branch_name': str,         # 업체명
            'region': str,              # 지역
            'review_count': int,        # 리뷰 개수
            'avg_rating': float,        # 평균평점
            'keyword_1': str,           # 키워드 1
            'keyword_2': str,           # 키워드 2
            'keyword_3': str,           # 키워드 3
            'summary_1m': str,          # 1개월 요약
            'summary_3m': str,          # 3개월 요약
            'summary_6m': str,          # 6개월 요약
            'summary_1y': str,          # 1년 요약
            'summary_all': str,         # 전체 요약
            'status': str               # 상태
        }

    Returns:
        저장된 데이터
    """
    client = get_client()

    # 필수 필드 확인
    if 'branch_id' not in data:
        raise ValueError("branch_id는 필수입니다")

    # 기존 데이터 확인
    existing = client.table('branch_summaries').select('status').eq('branch_id', data['branch_id']).execute()
    
    # 기본값 설정: 신규 생성 시에만 draft로 설정
    if 'status' not in data:
        if not existing.data:
            # 신규 생성
            data['status'] = 'draft'
        # 기존 데이터 업데이트 시에는 status를 포함하지 않음 (기존 값 유지)

    result = client.table('branch_summaries').upsert(
        data,
        on_conflict='branch_id'
    ).execute()

    return result.data[0] if result.data else None


def upsert_branch_summaries_batch(summaries: list) -> int:
    """
    여러 지점 요약 일괄 저장

    Args:
        summaries: 지점 요약 데이터 리스트

    Returns:
        성공 개수
    """
    client = get_client()
    success_count = 0
    total = len(summaries)

    for i, summary in enumerate(summaries, 1):
        try:
            if 'status' not in summary:
                summary['status'] = 'draft'

            client.table('branch_summaries').upsert(
                summary,
                on_conflict='branch_id'
            ).execute()
            success_count += 1

            if i % 50 == 0:
                print(f"   branch_summaries 저장 중: {i}/{total}")

        except Exception as e:
            print(f"  저장 오류 (지점 {summary.get('branch_id')}): {e}")

    return success_count


def update_branch_summary_field(branch_id: int, field: str, value) -> dict:
    """
    특정 필드만 업데이트

    Args:
        branch_id: 지점 번호
        field: 필드명 (예: 'summary_1m', 'status')
        value: 값

    Returns:
        업데이트된 데이터
    """
    client = get_client()
    result = client.table('branch_summaries').update({
        field: value
    }).eq('branch_id', branch_id).execute()

    return result.data[0] if result.data else None


def update_branch_summary_status(branch_id: int, status: str) -> dict:
    """지점 요약 상태 변경"""
    return update_branch_summary_field(branch_id, 'status', status)


def get_branch_summary_stats() -> dict:
    """
    지점 요약 통계 (전체)

    Returns:
        {'total': int, 'draft': int, 'approved': int, 'published': int, 'total_reviews': int}
    """
    client = get_client()

    # 전체 지점 집계
    total = client.table('branch_summaries').select('id', count='exact').execute()
    draft = client.table('branch_summaries').select('id', count='exact').eq('status', 'draft').execute()
    approved = client.table('branch_summaries').select('id', count='exact').eq('status', 'approved').execute()
    published = client.table('branch_summaries').select('id', count='exact').eq('status', 'published').execute()

    # 총 리뷰 수 계산 (페이지네이션으로 전체 조회)
    total_reviews = 0
    offset = 0
    page_size = 1000
    while True:
        reviews = client.table('branch_summaries').select('review_count').range(offset, offset + page_size - 1).execute()
        if not reviews.data:
            break
        total_reviews += sum(r.get('review_count', 0) or 0 for r in reviews.data)
        if len(reviews.data) < page_size:
            break
        offset += page_size

    return {
        'total': total.count or 0,
        'draft': draft.count or 0,
        'approved': approved.count or 0,
        'published': published.count or 0,
        'total_reviews': total_reviews
    }


def search_branch_summaries(
    keyword: str = None,
    region: str = None,
    min_rating: float = None,
    max_rating: float = None,
    limit: int = 50,
    min_reviews: int = 30
) -> list:
    """
    지점 요약 검색

    Args:
        keyword: 키워드 검색 (업체명, 키워드1~3에서 검색)
        region: 지역 필터
        min_rating: 최소 평점
        max_rating: 최대 평점
        limit: 결과 제한
        min_reviews: 최소 리뷰 수 (기본 30, 0이면 필터 없음)

    Returns:
        검색 결과 목록
    """
    client = get_client()
    query = client.table('branch_summaries').select('*')

    # 최소 리뷰 수 필터 (0이면 필터링 안함)
    if min_reviews > 0:
        query = query.gte('review_count', min_reviews)

    if region:
        query = query.ilike('region', f'%{region}%')
    if min_rating is not None:
        query = query.gte('avg_rating', min_rating)
    if max_rating is not None:
        query = query.lte('avg_rating', max_rating)

    result = query.order('branch_id').limit(limit).execute()
    data = result.data

    # 키워드 필터링 (후처리)
    if keyword and data:
        keyword_lower = keyword.lower()
        data = [
            row for row in data
            if keyword_lower in (row.get('branch_name') or '').lower()
            or keyword_lower in (row.get('keyword_1') or '').lower()
            or keyword_lower in (row.get('keyword_2') or '').lower()
            or keyword_lower in (row.get('keyword_3') or '').lower()
        ]

    return data


def delete_branch_summary(branch_id: int) -> bool:
    """
    지점 요약 삭제

    Args:
        branch_id: 지점 번호

    Returns:
        성공 여부
    """
    client = get_client()
    result = client.table('branch_summaries').delete().eq('branch_id', branch_id).execute()
    return len(result.data) > 0 if result.data else False


if __name__ == '__main__':
    # 테스트
    print("Supabase 연결 테스트...")
    client = get_client()
    print(f"연결 성공: {SUPABASE_URL}")

    # 마이그레이션 테스트
    # migrate_excel_to_db()
