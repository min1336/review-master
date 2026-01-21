"""
갱신 대상 지점 탐지 모듈

주요 기능:
1. 신규 지점 감지 (30건 이상, 요약 없음)
2. 갱신 필요 지점 감지 (50건 증가 또는 30% 증가)
3. 처리 대기열 생성
"""
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import pandas as pd

from ..config.scheduler_config import get_scheduler_config, SchedulerConfig

logger = logging.getLogger(__name__)


@dataclass
class BranchUpdateInfo:
    """지점 갱신 정보"""
    branch_id: int
    branch_name: Optional[str]
    current_review_count: int
    summary_review_count: int  # 요약 생성 시점 리뷰 수 (신규: 0)
    increase_count: int
    increase_rate: float
    update_reason: str  # 'new', 'count', 'rate', 'both'
    priority: int  # 우선순위 (낮을수록 높음)

    @property
    def is_new(self) -> bool:
        return self.update_reason == 'new'


class UpdateChecker:
    """
    갱신 대상 지점 탐지기

    사용법:
        checker = UpdateChecker()

        # 현재 리뷰 수 로드 (DataFrame 또는 딕셔너리)
        checker.load_current_counts(reviews_df)

        # 기존 요약 정보 로드
        checker.load_existing_summaries(summaries_df)

        # 처리 대기열 조회
        queue = checker.get_processing_queue()
    """

    def __init__(self, config: Optional[SchedulerConfig] = None):
        self.config = config or get_scheduler_config()
        self.current_counts: Dict[int, int] = {}  # branch_id -> review_count
        self.summary_counts: Dict[int, int] = {}  # branch_id -> review_count at summary
        self.branch_names: Dict[int, str] = {}    # branch_id -> name

    def load_current_counts(self, data: pd.DataFrame) -> int:
        """
        현재 리뷰 수 로드

        Args:
            data: 리뷰 데이터프레임 (지점번호 컬럼 필수)

        Returns:
            로드된 지점 수
        """
        if '지점번호' not in data.columns:
            raise ValueError("'지점번호' 컬럼이 필요합니다")

        # 정상 리뷰만 카운트
        if '리뷰상태' in data.columns:
            data = data[data['리뷰상태'] == '정상']

        counts = data.groupby('지점번호').size().to_dict()
        self.current_counts = {int(k): v for k, v in counts.items()}

        # 지점명 캐시
        if '지점명' in data.columns:
            names = data.groupby('지점번호')['지점명'].first().to_dict()
            self.branch_names = {int(k): v for k, v in names.items() if pd.notna(v)}

        logger.info(f"현재 리뷰 수 로드: {len(self.current_counts)}개 지점")
        return len(self.current_counts)

    def load_existing_summaries(self, data: pd.DataFrame) -> int:
        """
        기존 요약 정보 로드

        Args:
            data: 요약 데이터프레임 (지점번호, 리뷰수 컬럼 필수)

        Returns:
            로드된 요약 수
        """
        branch_col = '지점번호' if '지점번호' in data.columns else 'branch_id'
        count_col = '리뷰수' if '리뷰수' in data.columns else 'review_count'

        if branch_col not in data.columns:
            raise ValueError("지점번호 컬럼이 필요합니다")

        self.summary_counts = {}
        for _, row in data.iterrows():
            branch_id = int(row[branch_col])
            count = int(row.get(count_col, 0))
            self.summary_counts[branch_id] = count

        logger.info(f"기존 요약 로드: {len(self.summary_counts)}개 지점")
        return len(self.summary_counts)

    def load_from_supabase(self) -> Tuple[int, int]:
        """
        Supabase에서 요약 정보 로드 (branch_summaries 테이블)

        Returns:
            (로드된 요약 수, 오류 수)
        """
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'web'))
            from supabase_client import get_all_branch_summaries
        except ImportError:
            logger.warning("supabase_client 임포트 실패")
            return 0, 1

        try:
            summaries = get_all_branch_summaries(limit=2000)
            self.summary_counts = {}

            for s in summaries:
                branch_id = s.get('branch_id')
                count = s.get('review_count', 0)
                if branch_id:
                    self.summary_counts[int(branch_id)] = int(count)

            logger.info(f"Supabase에서 {len(self.summary_counts)}개 요약 로드")
            return len(self.summary_counts), 0

        except Exception as e:
            logger.error(f"Supabase 로드 실패: {e}")
            return 0, 1

    def find_new_branches(self) -> List[BranchUpdateInfo]:
        """
        신규 요약 대상 지점 탐지

        조건:
        - 현재 리뷰 수 >= min_reviews (30건)
        - 기존 요약 없음

        Returns:
            신규 지점 목록 (리뷰 수 내림차순)
        """
        min_reviews = self.config.new_summary.min_reviews
        new_branches = []

        for branch_id, count in self.current_counts.items():
            # 최소 리뷰 수 미달
            if count < min_reviews:
                continue

            # 이미 요약 존재
            if branch_id in self.summary_counts:
                continue

            new_branches.append(BranchUpdateInfo(
                branch_id=branch_id,
                branch_name=self.branch_names.get(branch_id),
                current_review_count=count,
                summary_review_count=0,
                increase_count=count,
                increase_rate=0.0,
                update_reason='new',
                priority=1  # 신규 지점 우선
            ))

        # 리뷰 수 내림차순 정렬
        new_branches.sort(key=lambda x: -x.current_review_count)

        logger.info(f"신규 지점 탐지: {len(new_branches)}개")
        return new_branches

    def find_update_candidates(self) -> List[BranchUpdateInfo]:
        """
        갱신 필요 지점 탐지

        조건 (OR):
        - 50건 이상 증가
        - 30% 이상 증가

        Returns:
            갱신 대상 목록 (증가량 내림차순)
        """
        update_config = self.config.update_summary
        candidates = []

        for branch_id, summary_count in self.summary_counts.items():
            current_count = self.current_counts.get(branch_id, 0)

            if current_count <= summary_count:
                continue

            if not update_config.should_update(current_count, summary_count):
                continue

            increase = current_count - summary_count
            rate = increase / summary_count if summary_count > 0 else 0

            # 갱신 이유 결정
            count_met = increase >= update_config.min_increase_count
            rate_met = rate >= update_config.min_increase_rate

            if count_met and rate_met:
                reason = 'both'
            elif count_met:
                reason = 'count'
            else:
                reason = 'rate'

            candidates.append(BranchUpdateInfo(
                branch_id=branch_id,
                branch_name=self.branch_names.get(branch_id),
                current_review_count=current_count,
                summary_review_count=summary_count,
                increase_count=increase,
                increase_rate=rate,
                update_reason=reason,
                priority=2  # 갱신은 신규보다 후순위
            ))

        # 증가량 내림차순 정렬
        candidates.sort(key=lambda x: -x.increase_count)

        logger.info(f"갱신 대상 탐지: {len(candidates)}개")
        return candidates

    def get_processing_queue(
        self,
        max_items: Optional[int] = None
    ) -> List[BranchUpdateInfo]:
        """
        처리 대기열 생성

        Args:
            max_items: 최대 처리 건수 (None: 전체)

        Returns:
            처리 대기열 (우선순위 순)
        """
        # 신규 + 갱신 합치기
        new_branches = self.find_new_branches()
        update_candidates = self.find_update_candidates()

        queue = new_branches + update_candidates

        # 우선순위 정렬 (1: 신규 우선, 2: 갱신)
        # 같은 우선순위 내에서는 증가량 순
        queue.sort(key=lambda x: (x.priority, -x.increase_count))

        if max_items:
            queue = queue[:max_items]

        logger.info(f"처리 대기열: {len(queue)}개 (신규: {len(new_branches)}, 갱신: {len(update_candidates)})")
        return queue

    def get_summary_report(self) -> Dict:
        """
        현황 요약 리포트 생성

        Returns:
            요약 통계 딕셔너리
        """
        new_branches = self.find_new_branches()
        update_candidates = self.find_update_candidates()

        min_reviews = self.config.new_summary.min_reviews
        eligible_count = sum(1 for c in self.current_counts.values() if c >= min_reviews)

        return {
            'timestamp': datetime.now().isoformat(),
            'config': {
                'min_reviews': self.config.new_summary.min_reviews,
                'min_increase_count': self.config.update_summary.min_increase_count,
                'min_increase_rate': self.config.update_summary.min_increase_rate,
            },
            'counts': {
                'total_branches': len(self.current_counts),
                'eligible_branches': eligible_count,
                'existing_summaries': len(self.summary_counts),
                'new_candidates': len(new_branches),
                'update_candidates': len(update_candidates),
            },
            'new_branches': [
                {
                    'branch_id': b.branch_id,
                    'name': b.branch_name,
                    'review_count': b.current_review_count
                }
                for b in new_branches[:10]  # 상위 10개만
            ],
            'update_candidates': [
                {
                    'branch_id': b.branch_id,
                    'name': b.branch_name,
                    'current': b.current_review_count,
                    'previous': b.summary_review_count,
                    'increase': b.increase_count,
                    'rate': f"{b.increase_rate:.1%}"
                }
                for b in update_candidates[:10]  # 상위 10개만
            ]
        }


def check_updates_from_excel(
    reviews_path: str,
    summaries_path: str = None
) -> Dict:
    """
    Excel 파일에서 갱신 대상 확인 (유틸리티 함수)

    Args:
        reviews_path: 리뷰 엑셀 경로
        summaries_path: 요약 엑셀 경로 (None: Supabase 사용)

    Returns:
        현황 리포트
    """
    checker = UpdateChecker()

    # 리뷰 데이터 로드
    reviews_df = pd.read_excel(reviews_path)
    checker.load_current_counts(reviews_df)

    # 요약 데이터 로드
    if summaries_path:
        summaries_df = pd.read_excel(summaries_path)
        checker.load_existing_summaries(summaries_df)
    else:
        checker.load_from_supabase()

    return checker.get_summary_report()


if __name__ == '__main__':
    # 테스트 실행
    import sys
    from pathlib import Path

    logging.basicConfig(level=logging.INFO)

    project_root = Path(__file__).parent.parent.parent
    reviews_path = project_root / 'data' / '리뷰리스트_20260109.xlsx'
    summaries_path = project_root / 'output' / 'branch_summaries.xlsx'

    if reviews_path.exists():
        report = check_updates_from_excel(
            str(reviews_path),
            str(summaries_path) if summaries_path.exists() else None
        )

        print("\n=== 갱신 현황 리포트 ===")
        print(f"전체 지점: {report['counts']['total_branches']}")
        print(f"요약 가능: {report['counts']['eligible_branches']}")
        print(f"기존 요약: {report['counts']['existing_summaries']}")
        print(f"신규 대상: {report['counts']['new_candidates']}")
        print(f"갱신 대상: {report['counts']['update_candidates']}")

        if report['new_branches']:
            print("\n신규 지점 (상위 10개):")
            for b in report['new_branches']:
                print(f"  - {b['branch_id']}: {b['review_count']}건")

        if report['update_candidates']:
            print("\n갱신 대상 (상위 10개):")
            for b in report['update_candidates']:
                print(f"  - {b['branch_id']}: {b['previous']} → {b['current']} (+{b['increase']}, {b['rate']})")
    else:
        print(f"파일 없음: {reviews_path}")
