"""
스케줄러 설정 모듈

데이터 분석 기반 스케줄링 기준:
- 전체 리뷰: 217,660건 (정상 213,639건)
- 월평균 리뷰: 2,763건 (최근 12개월)
- 지점당 월평균: 3.7건
- 30건 도달 중앙값: 7.5개월
"""
from dataclasses import dataclass, field
from typing import Dict, List, Literal
from datetime import datetime


SeasonType = Literal["peak", "transition", "off"]


@dataclass
class NewSummaryConfig:
    """신규 요약 생성 조건"""
    min_reviews: int = 30          # 최소 리뷰 수 (통계적 유의성)
    min_review_length: int = 5     # 최소 리뷰 길이 (노이즈 제거)


@dataclass
class UpdateSummaryConfig:
    """기존 요약 갱신 조건"""
    min_increase_count: int = 50   # 최소 증가 건수 (57.7% 지점 해당)
    min_increase_rate: float = 0.30  # 최소 증가율 30% (88.1% 지점 해당)
    use_and_condition: bool = False  # True: AND 조건, False: OR 조건

    def should_update(self, current_count: int, summary_count: int) -> bool:
        """
        갱신 필요 여부 판단

        Args:
            current_count: 현재 리뷰 수
            summary_count: 요약 생성 시점 리뷰 수

        Returns:
            갱신 필요 여부
        """
        if summary_count <= 0:
            return False

        increase = current_count - summary_count
        rate = increase / summary_count

        count_condition = increase >= self.min_increase_count
        rate_condition = rate >= self.min_increase_rate

        if self.use_and_condition:
            return count_condition and rate_condition
        return count_condition or rate_condition


@dataclass
class SeasonConfig:
    """시즌별 스케줄 설정"""
    name: str
    months: List[int]
    cron_expression: str
    description: str

    def is_current_season(self) -> bool:
        """현재 월이 이 시즌에 해당하는지 확인"""
        return datetime.now().month in self.months


@dataclass
class SchedulerConfig:
    """
    스케줄러 전체 설정

    데이터 분석 결과 기반:
    - 성수기(6-8월): 일평균 113건, 변화 빠름 → 주 1회
    - 환절기(3-5, 9-10월): 일평균 95건 → 격주
    - 비수기(11-2월): 일평균 80건, 변화 느림 → 월 1회
    """

    # 신규 요약 생성 조건
    new_summary: NewSummaryConfig = field(default_factory=NewSummaryConfig)

    # 기존 요약 갱신 조건
    update_summary: UpdateSummaryConfig = field(default_factory=UpdateSummaryConfig)

    # 배치 처리 설정
    batch_size: int = 50           # 한 번에 처리할 지점 수
    rate_limit_delay: int = 60     # LLM 호출 간 대기(초)

    # 시즌별 스케줄
    seasons: Dict[str, SeasonConfig] = field(default_factory=lambda: {
        "peak": SeasonConfig(
            name="성수기",
            months=[6, 7, 8],
            cron_expression="0 3 * * 0",  # 매주 일요일 03:00
            description="성수기 - 주 1회 (일요일) 새벽 3시"
        ),
        "transition": SeasonConfig(
            name="환절기",
            months=[3, 4, 5, 9, 10],
            cron_expression="0 3 1,15 * *",  # 매월 1일, 15일 03:00
            description="환절기 - 격주 (1일, 15일) 새벽 3시"
        ),
        "off": SeasonConfig(
            name="비수기",
            months=[1, 2, 11, 12],
            cron_expression="0 3 1 * *",  # 매월 1일 03:00
            description="비수기 - 월 1회 (1일) 새벽 3시"
        )
    })

    def get_current_season(self) -> SeasonConfig:
        """현재 시즌 설정 반환"""
        for season in self.seasons.values():
            if season.is_current_season():
                return season
        # 기본값: 환절기
        return self.seasons["transition"]

    def get_season_by_month(self, month: int) -> SeasonConfig:
        """특정 월의 시즌 설정 반환"""
        for season in self.seasons.values():
            if month in season.months:
                return season
        return self.seasons["transition"]


# 싱글톤 인스턴스
_config: SchedulerConfig = None


def get_scheduler_config() -> SchedulerConfig:
    """스케줄러 설정 싱글톤"""
    global _config
    if _config is None:
        _config = SchedulerConfig()
    return _config


def reset_scheduler_config():
    """설정 리셋 (테스트용)"""
    global _config
    _config = None
