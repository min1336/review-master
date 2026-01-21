"""
Review Summary AI - 운영팀 모니터링 대시보드
Supabase 기반 결과 관리 시스템
"""

from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import atexit

# 환경변수 로드
load_dotenv()

app = Flask(__name__)

# IP 화이트리스트 보안 초기화
from security import init_security
init_security(app)

# Supabase 클라이언트 임포트
from supabase_client import (
    get_client,
    get_scheduler_configs,
    get_scheduler_logs,
    get_last_run,
    get_sentiment_stats,
    get_all_sentiment_stats,
    search_recent_reviews,
    cleanup_reviews,
    # 카테고리 CRUD
    get_all_categories,
    get_category_by_id,
    create_category,
    update_category,
    delete_category,
    # 태그 CRUD
    get_all_tags,
    get_tag_by_id,
    create_tag,
    update_tag,
    delete_tag,
    # 키워드-태그 매핑
    get_keyword_mappings,
    create_keyword_mapping,
    delete_keyword_mapping,
    get_unmapped_keywords,
    bulk_create_keyword_mappings,
    # 지점별 태그
    get_branch_tags,
    # 통합 요약 테이블 (branch_summaries)
    get_all_branch_summaries,
    get_branch_summary,
    upsert_branch_summary,
    update_branch_summary_status,
    get_branch_summary_stats,
    search_branch_summaries,
    # 업체 정보
    get_all_affiliates,
    sync_affiliates_from_api
)

# 스케줄러 임포트
from scheduler import get_scheduler, init_scheduler

# ============================================================
# 페이지 라우트
# ============================================================

@app.route('/')
def index():
    """메인 대시보드"""
    return render_template('dashboard_v2.html')

@app.route('/tag-tester')
def tag_tester():
    """태그 분석 테스트 페이지"""
    return render_template('tag_tester.html')

# ============================================================
# API: 태그 분석 테스트
# ============================================================

@app.route('/api/analyze-tags', methods=['POST'])
def api_analyze_tags():
    """
    리뷰 텍스트의 태그 분석 테스트

    Body:
        {"review": "리뷰 텍스트"}

    Returns:
        {
            "keywords": [{"keyword": str, "sentiment": str}, ...],
            "tag_groups": {"서비스": {"positive": [...], "negative": [...]}, ...}
        }
    """
    data = request.get_json()
    if not data or 'review' not in data:
        return jsonify({'error': 'review 텍스트가 필요합니다'}), 400

    review_text = data['review']

    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

        # 키워드 추출
        from src.analysis.keywords import KeywordExtractor
        extractor = KeywordExtractor()
        keywords = extractor.extract(review_text)

        # 태그 분류
        from src.analysis.tags.embedding_classifier import EmbeddingTagClassifier
        classifier = EmbeddingTagClassifier()

        results = []
        tag_groups = {}

        for kw in keywords:
            # 원문(context)을 전달하여 "~지 않다" 같은 부정 표현 감지
            tag, score, sentiment = classifier.classify_with_sentiment(kw, context=review_text)
            results.append({
                'keyword': kw,
                'tag': tag,
                'sentiment': sentiment,
                'score': score
            })

            # 태그별 그룹화
            if tag not in tag_groups:
                tag_groups[tag] = {'positive': [], 'negative': [], 'neutral': []}
            tag_groups[tag][sentiment].append(kw)

        return jsonify({
            'keywords': [{'keyword': r['keyword'], 'sentiment': r['sentiment']} for r in results],
            'tag_groups': tag_groups
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# API: 카테고리 관리
# ============================================================

@app.route('/api/categories')
def api_categories():
    """카테고리 목록"""
    is_active = request.args.get('is_active', 'true').lower() == 'true'
    categories = get_all_categories(is_active=is_active)
    return jsonify(categories)


@app.route('/api/categories/<int:category_id>')
def api_category_detail(category_id):
    """카테고리 상세"""
    category = get_category_by_id(category_id)
    if category:
        return jsonify(category)
    return jsonify({'error': 'Category not found'}), 404


@app.route('/api/categories', methods=['POST'])
def api_create_category():
    """
    카테고리 생성

    Body:
        {"name": str, "description": str, "color": str, "display_order": int}
    """
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'name is required'}), 400

    try:
        result = create_category(data)
        return jsonify({'success': True, 'data': result}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/categories/<int:category_id>', methods=['PUT'])
def api_update_category(category_id):
    """카테고리 수정"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    result = update_category(category_id, data)
    return jsonify({'success': True, 'data': result})


@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
def api_delete_category(category_id):
    """카테고리 삭제"""
    result = delete_category(category_id)
    return jsonify({'success': result})

# ============================================================
# API: 태그 관리
# ============================================================

@app.route('/api/tags')
def api_tags():
    """
    태그 목록

    Query Parameters:
        group_name: 그룹 필터 (예: '서비스', '차량')
        sentiment: 감정 필터 ('positive', 'negative', 'neutral')
        category_id: 카테고리 필터 (deprecated, use group_name)
    """
    group_name = request.args.get('group_name')
    category_id = request.args.get('category_id', type=int)
    sentiment = request.args.get('sentiment')
    tags = get_all_tags(category_id=category_id, sentiment=sentiment, group_name=group_name)
    return jsonify(tags)


@app.route('/api/tags/<int:tag_id>')
def api_tag_detail(tag_id):
    """태그 상세"""
    tag = get_tag_by_id(tag_id)
    if tag:
        return jsonify(tag)
    return jsonify({'error': 'Tag not found'}), 404


@app.route('/api/tags', methods=['POST'])
def api_create_tag():
    """
    태그 생성

    Body:
        {
            "name": str (필수),
            "group_name": str (그룹명, 예: '서비스', '차량'),
            "color": str (색상, 예: '#10b981'),
            "sentiment": str ('positive' 또는 'negative')
        }
    """
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'name is required'}), 400

    try:
        result = create_tag(data)
        return jsonify({'success': True, 'data': result}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/tags/<int:tag_id>', methods=['PUT'])
def api_update_tag(tag_id):
    """태그 수정"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    result = update_tag(tag_id, data)
    return jsonify({'success': True, 'data': result})


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def api_delete_tag(tag_id):
    """태그 삭제"""
    result = delete_tag(tag_id)
    return jsonify({'success': result})


@app.route('/api/tags/<int:tag_id>/keywords')
def api_tag_keywords(tag_id):
    """태그에 매핑된 키워드 목록"""
    mappings = get_keyword_mappings(tag_id=tag_id)
    return jsonify(mappings)


@app.route('/api/tags/groups')
def api_tag_groups():
    """
    태그 그룹 목록 (고유한 group_name들)

    Returns:
        [{'group_name': str, 'color': str, 'count': int}, ...]
    """
    tags = get_all_tags()
    groups = {}
    for tag in tags:
        gname = tag.get('group_name') or '기타'
        if gname not in groups:
            groups[gname] = {
                'group_name': gname,
                'color': tag.get('color') or '#667eea',
                'count': 0
            }
        groups[gname]['count'] += 1

    return jsonify(list(groups.values()))

# ============================================================
# API: 키워드-태그 매핑
# ============================================================

@app.route('/api/mappings')
def api_mappings():
    """
    키워드-태그 매핑 목록

    Query Parameters:
        tag_id: 태그 ID 필터
        keyword: 키워드 필터
    """
    tag_id = request.args.get('tag_id', type=int)
    keyword = request.args.get('keyword')
    mappings = get_keyword_mappings(tag_id=tag_id, keyword=keyword)
    return jsonify(mappings)


@app.route('/api/mappings', methods=['POST'])
def api_create_mapping():
    """
    키워드 → 태그 매핑 생성

    Body:
        {"keyword": str, "tag_id": int, "is_auto": bool}
    """
    data = request.get_json()
    if not data or 'keyword' not in data or 'tag_id' not in data:
        return jsonify({'error': 'keyword and tag_id are required'}), 400

    try:
        result = create_keyword_mapping(
            keyword=data['keyword'],
            tag_id=data['tag_id'],
            is_auto=data.get('is_auto', False)
        )
        return jsonify({'success': True, 'data': result}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/mappings/<int:mapping_id>', methods=['DELETE'])
def api_delete_mapping(mapping_id):
    """매핑 삭제"""
    result = delete_keyword_mapping(mapping_id)
    return jsonify({'success': result})


@app.route('/api/mappings/unmapped')
def api_unmapped_keywords():
    """매핑되지 않은 키워드 목록"""
    limit = request.args.get('limit', 100, type=int)
    keywords = get_unmapped_keywords(limit=limit)
    return jsonify(keywords)


@app.route('/api/mappings/bulk', methods=['POST'])
def api_bulk_mappings():
    """
    키워드 매핑 일괄 생성

    Body:
        {"mappings": [{"keyword": str, "tag_id": int}, ...]}
    """
    data = request.get_json()
    if not data or 'mappings' not in data:
        return jsonify({'error': 'mappings array is required'}), 400

    count = bulk_create_keyword_mappings(data['mappings'])
    return jsonify({'success': True, 'created': count})


@app.route('/api/mappings/auto', methods=['POST'])
def api_auto_mapping():
    """
    자동 매핑 실행

    기존 키워드를 분석하여 태그에 자동 매핑
    """
    try:
        # TagMapper 사용
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.analysis.tags.mapper import TagMapper

        mapper = TagMapper()
        result = mapper.auto_map_all_keywords()
        return jsonify({'success': True, **result})
    except ImportError:
        return jsonify({'error': 'TagMapper module not found'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
# API: 지점별 태그
# ============================================================

@app.route('/api/branch/<int:branch_id>/tags')
def api_branch_tags(branch_id):
    """
    지점별 태그 목록

    Query Parameters:
        period: 기간 필터 ('all', '1m', '3m', '6m', '1y')
        limit: 상위 N개 (기본 10)
    """
    period = request.args.get('period', 'all')
    limit = request.args.get('limit', 10, type=int)
    tags = get_branch_tags(branch_id, period_type=period, limit=limit)
    return jsonify(tags)


@app.route('/api/tags/batch')
def api_tags_batch():
    """
    여러 지점의 top3 태그 일괄 조회 (최적화: 단일 쿼리)

    Query Parameters:
        branch_ids: 콤마로 구분된 지점 ID 목록
    """
    branch_ids_str = request.args.get('branch_ids', '')
    if not branch_ids_str:
        return jsonify({})

    try:
        branch_ids = [int(x) for x in branch_ids_str.split(',') if x.strip()]
    except ValueError:
        return jsonify({'error': 'Invalid branch_ids'}), 400

    client = get_client()

    # 태그 이름 조회 (1번 쿼리)
    tags_data = client.table('tags').select('id, name').execute()
    tag_names = {t['id']: t['name'] for t in tags_data.data}

    # 모든 지점의 태그를 한 번에 조회 (1번 쿼리)
    all_tags = client.table('branch_tags').select(
        'branch_id, tag_id, count'
    ).in_('branch_id', branch_ids).eq('period_type', 'positive').order('count', desc=True).execute()

    # 지점별로 그룹화하고 top3만 선택
    from collections import defaultdict
    branch_tags = defaultdict(list)
    for t in all_tags.data:
        bid = str(t['branch_id'])
        if len(branch_tags[bid]) < 3:  # top3만
            branch_tags[bid].append({
                'name': tag_names.get(t['tag_id'], 'unknown'),
                'count': t['count']
            })

    # 요청된 모든 지점에 대해 결과 반환 (태그 없는 지점도 빈 배열)
    result = {str(bid): branch_tags.get(str(bid), []) for bid in branch_ids}

    return jsonify(result)


@app.route('/api/branch/<int:branch_id>/summary')
def api_branch_summary(branch_id):
    """지점별 요약 조회 (branch_summaries 테이블 사용)"""
    summary = get_branch_summary(branch_id)
    if summary:
        return jsonify(summary)
    return jsonify({'error': 'Not found'}), 404

# ============================================================
# API: 스케줄러 관리
# ============================================================

@app.route('/api/scheduler/status')
def api_scheduler_status():
    """스케줄러 상태 조회"""
    scheduler = get_scheduler()
    return jsonify(scheduler.get_status())

@app.route('/api/scheduler/config')
def api_scheduler_config():
    """스케줄러 설정 조회"""
    configs = get_scheduler_configs()
    return jsonify(configs)

@app.route('/api/scheduler/config/<config_key>', methods=['PUT'])
def api_update_scheduler_config(config_key):
    """스케줄러 설정 업데이트"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    scheduler = get_scheduler()

    # cron 표현식 업데이트
    if 'cron_expression' in data:
        scheduler.update_schedule(config_key, data['cron_expression'])

    # 활성화/비활성화
    if 'is_enabled' in data:
        scheduler.toggle_schedule(config_key, data['is_enabled'])

    return jsonify({'success': True, 'message': f'{config_key} 설정 업데이트 완료'})

@app.route('/api/scheduler/trigger', methods=['POST'])
def api_trigger_scheduler():
    """스케줄러 수동 실행"""
    data = request.get_json() or {}
    config_key = data.get('config_key')
    mode = data.get('mode', 'incremental')  # 'incremental' 또는 'batch'

    scheduler = get_scheduler()

    # 비동기로 실행 (블로킹 방지)
    import threading

    if mode == 'batch':
        thread = threading.Thread(target=scheduler.run_batch)
        message = '배치 파이프라인 (Excel 전체) 실행 시작됨'
    else:
        thread = threading.Thread(target=scheduler.run_now, args=(config_key, False))
        message = '증분 파이프라인 (API 신규 리뷰) 실행 시작됨'

    thread.start()

    return jsonify({
        'success': True,
        'message': message,
        'mode': mode
    })

@app.route('/api/scheduler/trigger/batch', methods=['POST'])
def api_trigger_batch():
    """배치 파이프라인 수동 실행 (Excel 전체 처리 - 초기 1회용)"""
    scheduler = get_scheduler()

    import threading
    thread = threading.Thread(target=scheduler.run_batch)
    thread.start()

    return jsonify({
        'success': True,
        'message': '배치 파이프라인 (Excel 전체) 실행 시작됨 - 시간이 오래 걸립니다',
        'mode': 'batch'
    })

@app.route('/api/scheduler/trigger/incremental', methods=['POST'])
def api_trigger_incremental():
    """증분 파이프라인 수동 실행 (API 신규 리뷰만)"""
    scheduler = get_scheduler()

    import threading
    thread = threading.Thread(target=scheduler.run_incremental)
    thread.start()

    return jsonify({
        'success': True,
        'message': '증분 파이프라인 (API 신규 리뷰) 실행 시작됨',
        'mode': 'incremental'
    })

@app.route('/api/scheduler/test', methods=['POST'])
def api_test_scheduler():
    """스케줄러 테스트 실행 (파이프라인 없이 로그만)"""
    scheduler = get_scheduler()

    # 동기 실행 (테스트라 빠름)
    result = scheduler.run_test()

    return jsonify(result)

@app.route('/api/scheduler/logs')
def api_scheduler_logs():
    """스케줄러 실행 로그 조회"""
    limit = request.args.get('limit', 20, type=int)
    logs = get_scheduler_logs(limit=limit)
    return jsonify(logs)

@app.route('/api/scheduler/last-run')
def api_scheduler_last_run():
    """마지막 실행 정보"""
    config_key = request.args.get('config_key')
    last_run = get_last_run(config_key)
    return jsonify(last_run)

# ============================================================
# API: 감정태그 통계 및 최근 리뷰
# ============================================================

@app.route('/api/sentiment/stats')
def api_sentiment_stats():
    """
    지점별 감정태그 통계

    Query Parameters:
        branch_id: 지점번호 (선택, 없으면 전체 합계)

    Returns:
        {"positive": n, "negative": n, "neutral": n, "total": n, "positive_ratio": %, "negative_ratio": %}
    """
    branch_id = request.args.get('branch_id', type=int)
    stats = get_sentiment_stats(branch_id)
    return jsonify(stats)


@app.route('/api/sentiment/stats/all')
def api_all_sentiment_stats():
    """전체 지점 감정통계 목록"""
    stats = get_all_sentiment_stats()
    return jsonify(stats)


@app.route('/api/reviews/recent')
def api_recent_reviews():
    """
    최근 리뷰 검색 (1개월치)

    Query Parameters:
        sentiment: 'positive', 'negative', 'neutral' (선택)
        branch_id: 지점번호 (선택)
        limit: 결과 제한 (기본 100, 최대 1000)
        offset: 페이지네이션 오프셋 (기본 0)

    Returns:
        {
            "reviews": [...],
            "total": 1234,
            "stats": {"positive": n, "negative": n, ...}
        }
    """
    sentiment = request.args.get('sentiment')
    branch_id = request.args.get('branch_id', type=int)
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    # 유효성 검사
    if sentiment and sentiment not in ['positive', 'negative', 'neutral']:
        return jsonify({'error': 'Invalid sentiment. Use: positive, negative, neutral'}), 400

    if limit > 1000:
        limit = 1000

    result = search_recent_reviews(
        sentiment=sentiment,
        branch_id=branch_id,
        limit=limit,
        offset=offset
    )

    return jsonify(result)


@app.route('/api/reviews/cleanup', methods=['POST'])
def api_cleanup_reviews():
    """
    리뷰 정리 (1개월 이전 삭제 + 지점당 30개 제한)

    Body (optional):
        {"days": 30, "max_per_branch": 30}

    Returns:
        {"old_deleted": n, "excess_deleted": n, "total": n}
    """
    data = request.get_json() or {}
    days = data.get('days', 30)
    max_per_branch = data.get('max_per_branch', 30)

    result = cleanup_reviews(days=days, max_per_branch=max_per_branch)
    return jsonify({
        **result,
        'message': f'{days}일 이전 {result["old_deleted"]}개, 지점당 초과분 {result["excess_deleted"]}개 삭제됨'
    })

# ============================================================
# API: 통합 요약 (branch_summaries)
# ============================================================

@app.route('/api/v2/summaries')
def api_v2_summaries():
    """
    통합 요약 목록 (새 branch_summaries 테이블)

    Query Parameters:
        status: 상태 필터 ('draft', 'approved', 'published')
        region: 지역 필터 (예: '서울', '경기')
        keyword: 키워드/업체명 검색
        min_rating: 최소 평점
        max_rating: 최대 평점
        min_reviews: 최소 리뷰 수 (기본 30, 0이면 전체)
        limit: 페이지 크기 (기본 50)
        offset: 페이지네이션 오프셋
    """
    status = request.args.get('status')
    region = request.args.get('region')
    keyword = request.args.get('keyword')
    min_rating = request.args.get('min_rating', type=float)
    max_rating = request.args.get('max_rating', type=float)
    min_reviews = request.args.get('min_reviews', 30, type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    sort_by = request.args.get('sort_by', 'branch_id')
    order = request.args.get('order', 'asc')

    # 검색 조건이 있으면 search 사용
    if keyword or min_rating or max_rating:
        summaries = search_branch_summaries(
            keyword=keyword,
            region=region,
            min_rating=min_rating,
            max_rating=max_rating,
            limit=limit,
            min_reviews=min_reviews
        )
    else:
        summaries = get_all_branch_summaries(
            status=status,
            region=region,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            min_reviews=min_reviews
        )

    return jsonify(summaries)


@app.route('/api/v2/summaries/<int:branch_id>')
def api_v2_summary_detail(branch_id):
    """특정 지점 통합 요약 상세"""
    summary = get_branch_summary(branch_id)
    if summary:
        return jsonify(summary)
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/v2/summaries/<int:branch_id>', methods=['PUT'])
def api_v2_update_summary(branch_id):
    """통합 요약 수정"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    data['branch_id'] = branch_id
    result = upsert_branch_summary(data)
    return jsonify({'success': True, 'data': result})


@app.route('/api/v2/summaries/<int:branch_id>/status', methods=['PUT'])
def api_v2_update_status(branch_id):
    """통합 요약 상태 변경"""
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'error': 'status is required'}), 400

    result = update_branch_summary_status(branch_id, data['status'])
    return jsonify({'success': True, 'data': result})


@app.route('/api/v2/summaries/<int:branch_id>/regenerate', methods=['POST'])
def api_v2_regenerate_summary(branch_id):
    """
    특정 기간의 AI 요약 재생성

    Body:
        {"period": "all"}  # all, 1y, 6m, 3m, 1m

    Returns:
        {"success": true, "summary": "생성된 요약 텍스트..."}
    """
    data = request.get_json() or {}
    period = data.get('period', 'all')

    # 유효한 기간 검증
    valid_periods = ['all', '1y', '6m', '3m', '1m']
    if period not in valid_periods:
        return jsonify({'error': f'Invalid period. Use: {valid_periods}'}), 400

    try:
        summary = regenerate_summary_for_period(branch_id, period)
        return jsonify({'success': True, 'summary': summary, 'period': period})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def regenerate_summary_for_period(branch_id: int, period: str) -> str:
    """
    단일 지점, 단일 기간에 대한 AI 요약 재생성

    Args:
        branch_id: 지점 ID
        period: 기간 ('all', '1y', '6m', '3m', '1m')

    Returns:
        생성된 요약 텍스트
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    from src.llm import get_provider
    from src.llm.prompts import PromptTemplates

    # 1. 지점 정보 조회
    summary_data = get_branch_summary(branch_id)
    if not summary_data:
        raise ValueError(f"지점 {branch_id}을(를) 찾을 수 없습니다")

    branch_name = summary_data.get('branch_name', f'지점 {branch_id}')
    review_count = summary_data.get('review_count', 0)
    keywords = summary_data.get('keywords') or []

    # 2. 태그+감정 데이터 조회 (branch_tags 테이블)
    tag_sentiment_data = {}
    try:
        client = get_client()
        tags_result = client.table('branch_tags').select(
            'tag_id, count, tags(name, sentiment)'
        ).eq('branch_id', branch_id).eq('period_type', 'all').execute()

        for row in tags_result.data:
            tag_info = row.get('tags', {})
            tag_name = tag_info.get('name')
            sentiment = tag_info.get('sentiment', 'neutral')
            count = row.get('count', 0)

            if tag_name:
                if tag_name not in tag_sentiment_data:
                    tag_sentiment_data[tag_name] = {'positive': 0, 'negative': 0, 'neutral': 0}
                tag_sentiment_data[tag_name][sentiment] = count
    except Exception as e:
        print(f"태그 데이터 조회 실패: {e}")

    # 3. 감정 통계 계산 (평점 기반)
    avg_rating = summary_data.get('avg_rating', 4.5)
    if avg_rating >= 4.0:
        positive_ratio = 85
        negative_ratio = 5
    elif avg_rating >= 3.5:
        positive_ratio = 70
        negative_ratio = 15
    else:
        positive_ratio = 50
        negative_ratio = 30

    summary_stats = {
        'positive': positive_ratio,
        'negative': negative_ratio,
        'neutral': 100 - positive_ratio - negative_ratio
    }

    # 4. 기간 정보 추가
    period_labels = {
        'all': '전체 기간',
        '1y': '최근 1년',
        '6m': '최근 6개월',
        '3m': '최근 3개월',
        '1m': '최근 1개월'
    }
    period_label = period_labels.get(period, '전체 기간')

    # 5. 프롬프트 생성
    if tag_sentiment_data:
        system_prompt, user_prompt = PromptTemplates.build_summary_prompt_with_tags(
            keywords=keywords[:10] if keywords else ['리뷰'],
            review_count=review_count,
            tag_sentiment_data=tag_sentiment_data,
            branch_name=branch_name,
            summary_stats=summary_stats
        )
    else:
        system_prompt, user_prompt = PromptTemplates.build_summary_prompt(
            keywords=keywords[:10] if keywords else ['리뷰'],
            review_count=review_count,
            representative_reviews=[],
            branch_name=branch_name
        )

    # 기간 정보를 프롬프트에 추가
    user_prompt = f"[분석 기간: {period_label}]\n\n" + user_prompt

    # 6. LLM 호출
    llm_provider = get_provider()
    response = llm_provider.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=300,
        temperature=0.7
    )

    # LLMResponse 객체에서 텍스트 추출
    if hasattr(response, 'content'):
        generated_summary = response.content
    else:
        generated_summary = str(response)

    # 7. DB 저장
    field_map = {
        'all': 'summary_all',
        '1y': 'summary_1y',
        '6m': 'summary_6m',
        '3m': 'summary_3m',
        '1m': 'summary_1m'
    }
    field_name = field_map[period]

    upsert_branch_summary({
        'branch_id': branch_id,
        field_name: generated_summary
    })

    return generated_summary


@app.route('/api/v2/stats')
def api_v2_stats():
    """통합 요약 통계"""
    stats = get_branch_summary_stats()
    return jsonify(stats)


@app.route('/api/v2/stats/region')
def api_v2_region_stats():
    """
    지역별 통계

    Returns:
        [
            {"region": "서울", "count": 39, "avg_rating": 4.72, "total_reviews": 12345},
            {"region": "경기", "count": 41, "avg_rating": 4.68, "total_reviews": 23456},
            ...
        ]
    """
    client = get_client()
    result = client.table('branch_summaries').select(
        'region, avg_rating, review_count'
    ).execute()

    if not result.data:
        return jsonify([])

    # 지역별 집계
    region_stats = {}
    for row in result.data:
        region = row.get('region') or '미분류'
        # 시/도만 추출
        city = region.split()[0] if region and region.strip() else '미분류'

        if city not in region_stats:
            region_stats[city] = {
                'region': city,
                'count': 0,
                'total_reviews': 0,
                'rating_sum': 0,
                'rating_count': 0
            }

        region_stats[city]['count'] += 1
        region_stats[city]['total_reviews'] += row.get('review_count') or 0

        if row.get('avg_rating'):
            region_stats[city]['rating_sum'] += float(row['avg_rating'])
            region_stats[city]['rating_count'] += 1

    # 평균 평점 계산 및 정리
    stats_list = []
    for city, stats in region_stats.items():
        avg_rating = 0
        if stats['rating_count'] > 0:
            avg_rating = round(stats['rating_sum'] / stats['rating_count'], 2)

        stats_list.append({
            'region': city,
            'count': stats['count'],
            'avg_rating': avg_rating,
            'total_reviews': stats['total_reviews']
        })

    # 지점 수 내림차순 정렬
    stats_list.sort(key=lambda x: x['count'], reverse=True)

    return jsonify(stats_list)


@app.route('/api/v2/stats/rating')
def api_v2_rating_stats():
    """
    평점 분포 통계

    Returns:
        {
            "min": 3.94,
            "max": 4.99,
            "avg": 4.76,
            "distribution": {
                "5.0": 12,
                "4.5-5.0": 234,
                "4.0-4.5": 89,
                "3.5-4.0": 23,
                "3.0-3.5": 5,
                "<3.0": 2
            }
        }
    """
    client = get_client()
    result = client.table('branch_summaries').select('avg_rating').execute()

    ratings = [r['avg_rating'] for r in result.data if r.get('avg_rating')]

    if not ratings:
        return jsonify({
            'min': 0, 'max': 0, 'avg': 0,
            'distribution': {}, 'total': 0
        })

    # 분포 계산
    distribution = {
        '4.5-5.0': 0,
        '4.0-4.5': 0,
        '3.5-4.0': 0,
        '3.0-3.5': 0,
        '<3.0': 0
    }

    for r in ratings:
        if r >= 4.5:
            distribution['4.5-5.0'] += 1
        elif r >= 4.0:
            distribution['4.0-4.5'] += 1
        elif r >= 3.5:
            distribution['3.5-4.0'] += 1
        elif r >= 3.0:
            distribution['3.0-3.5'] += 1
        else:
            distribution['<3.0'] += 1

    return jsonify({
        'min': min(ratings),
        'max': max(ratings),
        'avg': round(sum(ratings) / len(ratings), 2),
        'distribution': distribution,
        'total': len(ratings)
    })


# ============================================================
# API: Carmore 연동
# ============================================================

@app.route('/api/carmore/sync/affiliates', methods=['POST'])
def api_sync_affiliates():
    """
    Carmore API에서 업체 정보 동기화

    Returns:
        {'total': n, 'success': n, 'error': str}
    """
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.api.carmore_client import get_carmore_client

        client = get_carmore_client()
        result = sync_affiliates_from_api(client)

        return jsonify({
            'success': True,
            **result
        })
    except ImportError as e:
        return jsonify({'error': f'Carmore client not found: {e}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/carmore/affiliates')
def api_carmore_affiliates():
    """
    저장된 업체 목록 조회

    Query Parameters:
        location_type: 위치 타입 (PARTNERS, JEJU, GLOBAL)
    """
    location_type = request.args.get('location_type')
    affiliates = get_all_affiliates(location_type=location_type)
    return jsonify(affiliates)


# ============================================================
# 메인 실행
# ============================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("Review Summary AI - 운영팀 모니터링 대시보드")
    print("="*60)
    print("\n접속: http://localhost:5000")
    print("\nAPI 엔드포인트 (v2 - branch_summaries):")
    print("  GET  /api/v2/summaries           - 전체 목록")
    print("  GET  /api/v2/summaries/<id>      - 상세 조회")
    print("  PUT  /api/v2/summaries/<id>      - 수정")
    print("  PUT  /api/v2/summaries/<id>/status - 상태 변경")
    print("  GET  /api/v2/stats               - 통계")
    print("\n감정태그 API:")
    print("  GET  /api/sentiment/stats       - 지점별 감정통계")
    print("  GET  /api/sentiment/stats/all   - 전체 지점 통계 목록")
    print("  GET  /api/reviews/recent        - 최근 리뷰 (1개월)")
    print("       ?sentiment=positive&branch_id=123")
    print("  POST /api/reviews/cleanup       - 오래된 리뷰 삭제")
    print("\n스케줄러 API:")
    print("  GET  /api/scheduler/status  - 스케줄러 상태")
    print("  GET  /api/scheduler/config  - 스케줄 설정 조회")
    print("  PUT  /api/scheduler/config/<key> - 스케줄 설정 변경")
    print("  POST /api/scheduler/trigger - 수동 실행")
    print("  GET  /api/scheduler/logs    - 실행 로그")
    print("="*60 + "\n")

    # 스케줄러 초기화 (debug 모드에서는 reloader로 인해 2번 실행되므로 주의)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            scheduler = init_scheduler(app)
            print("스케줄러 시작됨")

            # 앱 종료 시 스케줄러 정리
            atexit.register(lambda: scheduler.shutdown())
        except Exception as e:
            print(f"스케줄러 초기화 실패 (Supabase 테이블 생성 필요): {e}")

    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
