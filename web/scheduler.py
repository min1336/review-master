"""
Review Summary AI 스케줄러 모듈
- APScheduler 기반
- Supabase에서 설정 로드
- 시즌별 동적 스케줄링
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from supabase_client import (
    get_scheduler_configs,
    get_current_season_config,
    create_scheduler_log,
    update_scheduler_log,
    get_all_summaries
)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('scheduler')


class ReviewScheduler:
    """리뷰 요약 스케줄러"""

    def __init__(self, app=None):
        self.scheduler = BackgroundScheduler(timezone='Asia/Seoul')
        self.app = app
        self._setup_listeners()

    def _setup_listeners(self):
        """스케줄러 이벤트 리스너 설정"""
        def job_listener(event):
            if event.exception:
                logger.error(f"작업 실패: {event.job_id} - {event.exception}")
            else:
                logger.info(f"작업 완료: {event.job_id}")

        self.scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    def load_schedules_from_db(self):
        """Supabase에서 스케줄 설정 로드"""
        try:
            configs = get_scheduler_configs()
            logger.info(f"스케줄 설정 {len(configs)}개 로드")

            for config in configs:
                if config.get('is_enabled'):
                    self._add_or_update_job(config)
                else:
                    self._remove_job_if_exists(config['config_key'])

        except Exception as e:
            logger.error(f"스케줄 로드 실패: {e}")

    def _add_or_update_job(self, config: dict):
        """작업 추가 또는 업데이트"""
        job_id = config['config_key']
        cron_expr = config['cron_expression']

        # 기존 작업 제거
        self._remove_job_if_exists(job_id)

        # cron 표현식 파싱 (분 시 일 월 요일)
        parts = cron_expr.split()
        if len(parts) >= 5:
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2] if parts[2] != '*' else None,
                month=parts[3] if parts[3] != '*' else None,
                day_of_week=parts[4] if parts[4] != '*' else None,
                timezone='Asia/Seoul'
            )

            self.scheduler.add_job(
                self._run_pipeline_job,
                trigger=trigger,
                id=job_id,
                args=[config],
                replace_existing=True,
                name=config.get('description', job_id)
            )
            logger.info(f"작업 등록: {job_id} - {cron_expr}")

    def _remove_job_if_exists(self, job_id: str):
        """기존 작업 제거"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"작업 제거: {job_id}")
        except Exception:
            pass  # 작업이 없으면 무시

    def _run_pipeline_job(self, config: dict):
        """파이프라인 실행 작업"""
        config_key = config['config_key']
        logger.info(f"[{config_key}] 파이프라인 실행 시작")

        # 로그 생성
        log = create_scheduler_log(config_key)
        log_id = log['id'] if log else None

        try:
            # 현재 월 확인
            current_month = datetime.now().month
            months = config.get('months', '')

            if months and months != 'all':
                month_list = [int(m.strip()) for m in months.split(',')]
                if current_month not in month_list:
                    logger.info(f"[{config_key}] 현재 월({current_month})은 해당 시즌이 아님. 스킵.")
                    if log_id:
                        update_scheduler_log(log_id, status='skipped', error_message=f'현재 월({current_month})은 해당 시즌 아님')
                    return

            # 파이프라인 실행 (기본: 증분 모드)
            # batch_mode 설정이 있으면 배치 모드로 실행
            use_incremental = not config.get('batch_mode', False)
            result = self._execute_pipeline(use_incremental=use_incremental)

            # 로그 업데이트
            if log_id:
                update_scheduler_log(
                    log_id,
                    branch_count=result.get('branch_count', 0),
                    success_count=result.get('success_count', 0),
                    fail_count=result.get('fail_count', 0),
                    status='completed'
                )

            logger.info(f"[{config_key}] 파이프라인 완료 ({result.get('mode', 'unknown')}): {result}")

        except Exception as e:
            logger.error(f"[{config_key}] 파이프라인 실패: {e}")
            if log_id:
                update_scheduler_log(log_id, status='failed', error_message=str(e))

    def _execute_pipeline(self, use_incremental: bool = True) -> dict:
        """
        파이프라인 실행

        Args:
            use_incremental: True면 증분 파이프라인 (API 기반)
                            False면 배치 파이프라인 (Excel 기반)
        """
        if use_incremental:
            return self._execute_incremental_pipeline()
        else:
            return self._execute_batch_pipeline()

    def _execute_incremental_pipeline(self) -> dict:
        """증분 파이프라인 실행 (API 기반 - 신규 리뷰만)"""
        try:
            from scripts.pipeline_incremental import IncrementalPipeline

            pipeline = IncrementalPipeline()
            stats = pipeline.run()

            return {
                'branch_count': len(stats.get('branches_updated', set())),
                'success_count': stats.get('processed', 0),
                'fail_count': stats.get('filtered', 0) + stats.get('negative', 0),
                'mode': 'incremental'
            }

        except Exception as e:
            logger.error(f"증분 파이프라인 실행 오류: {e}")
            raise

    def _execute_batch_pipeline(self) -> dict:
        """배치 파이프라인 실행 (Excel 기반 - 전체 처리)"""
        try:
            # pipeline_v3.py import
            from scripts.pipeline_v3 import ReviewPipeline

            # 파이프라인 실행
            pipeline = ReviewPipeline(min_reviews=30, use_deep_learning=False)

            # 입력 파일 찾기
            data_dir = Path(__file__).parent.parent / 'data'
            input_files = list(data_dir.glob('리뷰리스트*.xlsx'))

            if not input_files:
                raise FileNotFoundError("리뷰 데이터 파일을 찾을 수 없습니다")

            # 가장 최신 파일 사용
            input_file = max(input_files, key=lambda x: x.stat().st_mtime)
            output_dir = Path(__file__).parent.parent / 'output'

            logger.info(f"입력 파일: {input_file}")
            pipeline.run(str(input_file), str(output_dir))

            # 결과 통계
            summaries = get_all_summaries(limit=1000)
            return {
                'branch_count': len(summaries),
                'success_count': len(summaries),
                'fail_count': 0,
                'mode': 'batch'
            }

        except Exception as e:
            logger.error(f"배치 파이프라인 실행 오류: {e}")
            raise

    def update_schedule(self, config_key: str, cron_expression: str):
        """스케줄 동적 업데이트 (대시보드에서 호출)"""
        from supabase_client import update_scheduler_config, get_scheduler_config

        # DB 업데이트
        update_scheduler_config(config_key, cron_expression=cron_expression)

        # 메모리 스케줄 업데이트
        config = get_scheduler_config(config_key)
        if config and config.get('is_enabled'):
            self._add_or_update_job(config)
        else:
            self._remove_job_if_exists(config_key)

        logger.info(f"스케줄 업데이트: {config_key} -> {cron_expression}")

    def toggle_schedule(self, config_key: str, is_enabled: bool):
        """스케줄 활성화/비활성화"""
        from supabase_client import update_scheduler_config, get_scheduler_config

        update_scheduler_config(config_key, is_enabled=is_enabled)

        if is_enabled:
            config = get_scheduler_config(config_key)
            if config:
                self._add_or_update_job(config)
        else:
            self._remove_job_if_exists(config_key)

        logger.info(f"스케줄 {'활성화' if is_enabled else '비활성화'}: {config_key}")

    def run_now(self, config_key: str = None, batch_mode: bool = False):
        """
        즉시 실행 (수동 트리거)

        Args:
            config_key: 스케줄 설정 키 (없으면 현재 시즌)
            batch_mode: True면 배치 모드 (Excel 전체 처리)
                       False면 증분 모드 (API 신규 리뷰만)
        """
        if config_key:
            config = get_scheduler_config(config_key)
        else:
            # 현재 시즌 설정으로 실행
            config = get_current_season_config()

        if config:
            # batch_mode 플래그 추가
            config['batch_mode'] = batch_mode
            self._run_pipeline_job(config)

    def run_batch(self):
        """배치 파이프라인 실행 (Excel 전체 처리 - 초기 1회용)"""
        logger.info("[배치] Excel 전체 처리 시작")

        log = create_scheduler_log('batch_full')
        log_id = log['id'] if log else None

        try:
            result = self._execute_batch_pipeline()

            if log_id:
                update_scheduler_log(
                    log_id,
                    branch_count=result.get('branch_count', 0),
                    success_count=result.get('success_count', 0),
                    fail_count=result.get('fail_count', 0),
                    status='completed'
                )

            logger.info(f"[배치] 완료: {result}")
            return result

        except Exception as e:
            logger.error(f"[배치] 실패: {e}")
            if log_id:
                update_scheduler_log(log_id, status='failed', error_message=str(e))
            raise

    def run_incremental(self):
        """증분 파이프라인 실행 (API 신규 리뷰만)"""
        logger.info("[증분] API 신규 리뷰 처리 시작")

        log = create_scheduler_log('incremental')
        log_id = log['id'] if log else None

        try:
            result = self._execute_incremental_pipeline()

            if log_id:
                update_scheduler_log(
                    log_id,
                    branch_count=result.get('branch_count', 0),
                    success_count=result.get('success_count', 0),
                    fail_count=result.get('fail_count', 0),
                    status='completed'
                )

            logger.info(f"[증분] 완료: {result}")
            return result

        except Exception as e:
            logger.error(f"[증분] 실패: {e}")
            if log_id:
                update_scheduler_log(log_id, status='failed', error_message=str(e))
            raise

    def run_test(self):
        """테스트 실행 (파이프라인 없이 로그만 남김)"""
        import time

        config_key = 'test_run'
        logger.info(f"[테스트] 스케줄러 테스트 실행 시작")

        # 로그 생성
        log = create_scheduler_log(config_key)
        log_id = log['id'] if log else None

        try:
            # 테스트: 3초 대기 (실제 작업 시뮬레이션)
            logger.info(f"[테스트] 작업 시뮬레이션 중... (3초)")
            time.sleep(3)

            # 성공 로그
            if log_id:
                update_scheduler_log(
                    log_id,
                    branch_count=10,
                    success_count=10,
                    fail_count=0,
                    status='completed'
                )

            logger.info(f"[테스트] 스케줄러 테스트 완료!")
            return {'success': True, 'message': '테스트 실행 완료', 'log_id': log_id}

        except Exception as e:
            logger.error(f"[테스트] 실패: {e}")
            if log_id:
                update_scheduler_log(log_id, status='failed', error_message=str(e))
            return {'success': False, 'message': str(e)}

    def start(self):
        """스케줄러 시작"""
        if not self.scheduler.running:
            self.load_schedules_from_db()
            self.scheduler.start()
            logger.info("스케줄러 시작됨")

    def shutdown(self):
        """스케줄러 종료"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("스케줄러 종료됨")

    def get_jobs(self):
        """현재 등록된 작업 목록"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': str(job.next_run_time) if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs

    def get_status(self):
        """스케줄러 상태"""
        return {
            'running': self.scheduler.running,
            'jobs': self.get_jobs()
        }


# 전역 스케줄러 인스턴스
_scheduler: ReviewScheduler = None


def get_scheduler() -> ReviewScheduler:
    """스케줄러 싱글톤"""
    global _scheduler
    if _scheduler is None:
        _scheduler = ReviewScheduler()
    return _scheduler


def init_scheduler(app=None):
    """스케줄러 초기화 및 시작"""
    scheduler = get_scheduler()
    scheduler.app = app
    scheduler.start()
    return scheduler


if __name__ == '__main__':
    # 테스트
    print("스케줄러 테스트...")
    scheduler = get_scheduler()

    # DB에서 설정 로드
    scheduler.load_schedules_from_db()

    # 등록된 작업 확인
    print("\n등록된 작업:")
    for job in scheduler.get_jobs():
        print(f"  - {job['id']}: {job['name']}, 다음 실행: {job['next_run']}")

    # 스케줄러 시작
    # scheduler.start()
    # import time
    # time.sleep(60)
    # scheduler.shutdown()
