"""
Review Summary AI 스케줄러 모듈 v2

기능:
- APScheduler 기반 백그라운드 스케줄링
- 데이터 분석 기반 스케줄 설정 (scheduler_config.py)
- 갱신 조건 자동 검사 (update_checker.py)
- 시즌별 동적 스케줄링

스케줄링 기준 (데이터 분석 결과):
- 성수기(6-8월): 주 1회 (일요일) - 일평균 113건
- 환절기(3-5, 9-10월): 격주 (1일, 15일) - 일평균 95건
- 비수기(11-2월): 월 1회 (1일) - 일평균 80건

갱신 조건:
- 신규: 30건 이상 리뷰, 요약 없음
- 갱신: 50건 증가 OR 30% 증가

실행 모드:
- 🐇 증분 (Incremental): 자동 스케줄 실행 (API 신규 리뷰만)
- 🦣 배치 (Batch): 관리자 수동 실행 전용 (Excel 전체)
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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
    get_all_branch_summaries
)

# 스케줄러 설정 및 갱신 체커
try:
    from src.config.scheduler_config import get_scheduler_config, SchedulerConfig
    from src.pipeline.update_checker import UpdateChecker, BranchUpdateInfo
    HAS_UPDATE_CHECKER = True
except ImportError:
    HAS_UPDATE_CHECKER = False

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('scheduler')


class ReviewScheduler:
    """
    리뷰 요약 스케줄러 v2

    주요 기능:
    1. 시즌별 자동 스케줄링 (성수기/환절기/비수기)
    2. 스마트 갱신 (신규/갱신 대상만 처리)
    3. Supabase 연동 로깅

    사용법:
        scheduler = get_scheduler()
        scheduler.start()

        # 즉시 실행 (스마트 모드)
        scheduler.run_smart()

        # 전체 배치 실행
        scheduler.run_batch()
    """

    def __init__(self, app=None):
        self.scheduler = BackgroundScheduler(timezone='Asia/Seoul')
        self.app = app
        self._setup_listeners()

        # 스케줄러 설정 로드
        if HAS_UPDATE_CHECKER:
            self.sched_config = get_scheduler_config()
        else:
            self.sched_config = None

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

            # 파이프라인 실행 (자동 스케줄: 증분 모드만)
            # ⚠️ 배치 모드는 관리자 수동 실행만 허용
            result = self._execute_pipeline(use_incremental=True)

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
            from src.pipeline.batch_pipeline import BatchPipeline

            # 파이프라인 실행
            pipeline = BatchPipeline(min_reviews=30)

            # 입력 파일 찾기
            data_dir = Path(__file__).parent.parent / 'data'
            input_files = list(data_dir.glob('리뷰리스트*.xlsx'))

            if not input_files:
                raise FileNotFoundError("리뷰 데이터 파일을 찾을 수 없습니다")

            # 가장 최신 파일 사용
            input_file = max(input_files, key=lambda x: x.stat().st_mtime)
            output_dir = Path(__file__).parent.parent / 'output'

            logger.info(f"입력 파일: {input_file}")
            stats = pipeline.run(str(input_file), str(output_dir))

            return {
                'branch_count': stats.get('branch_count', 0),
                'success_count': stats.get('summaries_generated', 0),
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
        """
        배치 파이프라인 실행 (Excel 전체 처리)

        ⚠️ 관리자 수동 실행 전용!
        - 자동 스케줄에서는 실행되지 않음
        - API: POST /api/scheduler/trigger/batch
        """
        logger.info("[배치] Excel 전체 처리 시작 (관리자 수동 실행)")

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

    def run_smart(self, max_branches: int = None) -> dict:
        """
        스마트 파이프라인 실행 (신규/갱신 대상만 처리)

        데이터 분석 기반 갱신 조건:
        - 신규: 30건 이상 리뷰, 요약 없음
        - 갱신: 50건 증가 OR 30% 증가

        Args:
            max_branches: 최대 처리 지점 수 (None: 전체)

        Returns:
            실행 결과 딕셔너리
        """
        if not HAS_UPDATE_CHECKER:
            logger.warning("[스마트] update_checker 모듈 없음, 증분 모드로 대체")
            return self.run_incremental()

        logger.info("[스마트] 갱신 대상 탐지 시작")

        log = create_scheduler_log('smart')
        log_id = log['id'] if log else None

        try:
            import pandas as pd

            # 1. 리뷰 데이터 로드
            data_dir = Path(__file__).parent.parent / 'data'
            input_files = list(data_dir.glob('리뷰리스트*.xlsx'))

            if not input_files:
                raise FileNotFoundError("리뷰 데이터 파일을 찾을 수 없습니다")

            input_file = max(input_files, key=lambda x: x.stat().st_mtime)
            logger.info(f"[스마트] 입력 파일: {input_file.name}")

            reviews_df = pd.read_excel(input_file)

            # 2. 갱신 대상 탐지
            checker = UpdateChecker(self.sched_config)
            checker.load_current_counts(reviews_df)
            checker.load_from_supabase()

            queue = checker.get_processing_queue(max_items=max_branches)

            if not queue:
                logger.info("[스마트] 갱신 대상 없음")
                if log_id:
                    update_scheduler_log(log_id, status='completed',
                                        branch_count=0, success_count=0, fail_count=0)
                return {'mode': 'smart', 'branch_count': 0, 'message': '갱신 대상 없음'}

            # 3. 대상 지점 처리
            new_count = sum(1 for b in queue if b.is_new)
            update_count = len(queue) - new_count
            logger.info(f"[스마트] 처리 대상: {len(queue)}개 (신규: {new_count}, 갱신: {update_count})")

            # 대상 지점 ID 목록
            target_branch_ids = [b.branch_id for b in queue]

            # 4. 선택적 파이프라인 실행
            result = self._execute_smart_pipeline(reviews_df, target_branch_ids)

            if log_id:
                update_scheduler_log(
                    log_id,
                    branch_count=len(queue),
                    success_count=result.get('success_count', 0),
                    fail_count=result.get('fail_count', 0),
                    status='completed'
                )

            logger.info(f"[스마트] 완료: {result}")
            return result

        except Exception as e:
            logger.error(f"[스마트] 실패: {e}")
            if log_id:
                update_scheduler_log(log_id, status='failed', error_message=str(e))
            raise

    def _execute_smart_pipeline(
        self,
        reviews_df,
        target_branch_ids: List[int]
    ) -> dict:
        """
        선택적 파이프라인 실행 (지정된 지점만)

        Args:
            reviews_df: 전체 리뷰 데이터프레임
            target_branch_ids: 처리할 지점 ID 목록

        Returns:
            실행 결과
        """
        from src.pipeline.batch_pipeline import BatchPipeline

        # 대상 지점만 필터링
        filtered_df = reviews_df[reviews_df['지점번호'].isin(target_branch_ids)]

        if filtered_df.empty:
            return {'mode': 'smart', 'success_count': 0, 'fail_count': 0}

        # 임시 파일로 저장
        temp_dir = Path(__file__).parent.parent / 'output' / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f'smart_batch_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        filtered_df.to_excel(temp_file, index=False)

        try:
            # 파이프라인 실행
            pipeline = BatchPipeline(min_reviews=self.sched_config.new_summary.min_reviews)
            output_dir = Path(__file__).parent.parent / 'output'

            stats = pipeline.run(str(temp_file), str(output_dir))

            return {
                'mode': 'smart',
                'branch_count': len(target_branch_ids),
                'success_count': stats.get('summaries_generated', 0),
                'fail_count': len(target_branch_ids) - stats.get('summaries_generated', 0)
            }

        finally:
            # 임시 파일 정리
            if temp_file.exists():
                temp_file.unlink()

    def get_update_report(self) -> dict:
        """
        갱신 현황 리포트 조회

        Returns:
            현황 리포트 딕셔너리
        """
        if not HAS_UPDATE_CHECKER:
            return {'error': 'update_checker 모듈 없음'}

        try:
            import pandas as pd

            data_dir = Path(__file__).parent.parent / 'data'
            input_files = list(data_dir.glob('리뷰리스트*.xlsx'))

            if not input_files:
                return {'error': '리뷰 데이터 파일 없음'}

            input_file = max(input_files, key=lambda x: x.stat().st_mtime)
            reviews_df = pd.read_excel(input_file)

            checker = UpdateChecker(self.sched_config)
            checker.load_current_counts(reviews_df)
            checker.load_from_supabase()

            return checker.get_summary_report()

        except Exception as e:
            return {'error': str(e)}

    def load_season_schedules(self):
        """시즌별 스케줄 자동 로드 (scheduler_config 기반)"""
        if not self.sched_config:
            logger.warning("scheduler_config 없음, DB 설정 사용")
            return self.load_schedules_from_db()

        logger.info("시즌별 스케줄 로드 (scheduler_config 기반)")

        for key, season in self.sched_config.seasons.items():
            job_id = f"season_{key}"
            months_str = ','.join(map(str, season.months))

            config = {
                'config_key': job_id,
                'cron_expression': season.cron_expression,
                'is_enabled': True,
                'description': season.description,
                'months': months_str
            }

            self._add_or_update_job(config)
            logger.info(f"  - {job_id}: {season.cron_expression} ({season.name})")

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
