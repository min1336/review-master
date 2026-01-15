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

# Supabase 클라이언트 임포트
from supabase_client import (
    get_all_summaries,
    get_summary_by_id,
    get_summary_by_branch,
    update_summary,
    update_summary_status,
    get_summary_stats,
    get_client,
    get_scheduler_configs,
    get_scheduler_logs,
    get_last_run,
    search_reviews_by_tag,
    get_sentiment_stats
)

# 스케줄러 임포트
from scheduler import get_scheduler, init_scheduler

# ============================================================
# 페이지 라우트
# ============================================================

@app.route('/')
def index():
    """메인 대시보드"""
    return render_template('dashboard.html')

# ============================================================
# API: 요약 관리
# ============================================================

@app.route('/api/summaries')
def api_summaries():
    """전체 요약 목록 (페이징, 필터)"""
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    summaries = get_all_summaries(status=status, limit=limit, offset=offset)
    return jsonify(summaries)

@app.route('/api/summaries/<int:summary_id>')
def api_summary_detail(summary_id):
    """특정 요약 상세"""
    summary = get_summary_by_id(summary_id)
    if summary:
        return jsonify(summary)
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/summaries/<int:summary_id>', methods=['PUT'])
def api_update_summary(summary_id):
    """요약 수정"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # 허용된 필드만 업데이트
    allowed_fields = ['edited_summary', 'status']
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        return jsonify({'error': 'No valid fields to update'}), 400

    result = update_summary(summary_id, update_data)
    return jsonify({'success': True, 'data': result})

@app.route('/api/summaries/<int:summary_id>/approve', methods=['POST'])
def api_approve_summary(summary_id):
    """요약 승인"""
    result = update_summary_status(summary_id, 'approved')
    return jsonify({'success': True, 'data': result})

@app.route('/api/summaries/<int:summary_id>/publish', methods=['POST'])
def api_publish_summary(summary_id):
    """요약 게시"""
    result = update_summary_status(summary_id, 'published')
    return jsonify({'success': True, 'data': result})

@app.route('/api/summaries/<int:summary_id>/draft', methods=['POST'])
def api_draft_summary(summary_id):
    """요약을 draft로 되돌리기"""
    result = update_summary_status(summary_id, 'draft')
    return jsonify({'success': True, 'data': result})

# ============================================================
# API: 통계
# ============================================================

@app.route('/api/stats')
def api_stats():
    """통계 정보"""
    stats = get_summary_stats()
    return jsonify(stats)

# ============================================================
# API: 지점별 조회 (하위 호환)
# ============================================================

@app.route('/api/branch/<int:branch_id>')
def api_branch(branch_id):
    """지점별 요약 조회"""
    summary = get_summary_by_branch(branch_id)
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
# API: 리뷰 검색 (감정태그)
# ============================================================

@app.route('/api/reviews/search')
def api_search_reviews():
    """
    감정태그로 리뷰 검색

    Query Parameters:
        sentiment: 'positive', 'negative', 'neutral' (선택)
        branch_id: 지점번호 (선택)
        limit: 결과 제한 (기본 100)
        offset: 페이지네이션 오프셋 (기본 0)

    Returns:
        {
            "reviews": [...],
            "total": 1234,
            "stats": {"positive": 800, "negative": 300, "neutral": 134, "total": 1234}
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
        limit = 1000  # 최대 1000개

    result = search_reviews_by_tag(
        sentiment=sentiment,
        branch_id=branch_id,
        limit=limit,
        offset=offset
    )

    return jsonify(result)


@app.route('/api/reviews/stats')
def api_review_stats():
    """
    리뷰 감정태그 통계

    Query Parameters:
        branch_id: 지점번호 (선택, 없으면 전체)

    Returns:
        {"positive": n, "negative": n, "neutral": n, "total": n}
    """
    branch_id = request.args.get('branch_id', type=int)
    stats = get_sentiment_stats(branch_id)
    return jsonify(stats)

# ============================================================
# 메인 실행
# ============================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("Review Summary AI - 운영팀 모니터링 대시보드")
    print("="*60)
    print("\n접속: http://localhost:5000")
    print("\nAPI 엔드포인트:")
    print("  GET  /api/summaries         - 전체 목록")
    print("  GET  /api/summaries/<id>    - 상세 조회")
    print("  PUT  /api/summaries/<id>    - 수정")
    print("  POST /api/summaries/<id>/approve - 승인")
    print("  POST /api/summaries/<id>/publish - 게시")
    print("  GET  /api/stats             - 통계")
    print("\n리뷰 검색 API:")
    print("  GET  /api/reviews/search    - 감정태그로 검색")
    print("       ?sentiment=positive|negative|neutral")
    print("       &branch_id=123&limit=100&offset=0")
    print("  GET  /api/reviews/stats     - 감정태그 통계")
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

    app.run(host='0.0.0.0', port=5000, debug=True)
