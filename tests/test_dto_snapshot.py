"""DTO model_dump(by_alias=True) 출력 스냅샷 테스트.

dataclass DTO -> Pydantic BaseModel 마이그레이션 후 출력 동등성 검증용.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

# schemas/__init__.py 와 core/__init__.py 가 FastAPI/pydantic을 임포트해
# 시스템 pytest 환경(의존성 미설치)에서 실패하므로, dto.py 가 필요로 하는
# 두 심볼만 stub 모듈로 미리 등록한 뒤 dto.py 를 직접 로드한다.

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)

_core_constants = ModuleType("core.constants")
_core_constants.NEGATIVE_RATING_THRESHOLD = 3.0  # type: ignore[attr-defined]

_core_timezone = ModuleType("core.timezone")
_core_timezone.utc_now = _utc_now  # type: ignore[attr-defined]

_core_pkg = ModuleType("core")

for _name, _mod in [
    ("core", _core_pkg),
    ("core.constants", _core_constants),
    ("core.timezone", _core_timezone),
]:
    sys.modules.setdefault(_name, _mod)

_dto_path = Path(__file__).resolve().parent.parent / "app" / "schemas" / "dto.py"
_spec = importlib.util.spec_from_file_location("schemas.dto", _dto_path)
_dto_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("schemas.dto", _dto_mod)
_spec.loader.exec_module(_dto_mod)

AnalysisReviewDTO = _dto_mod.AnalysisReviewDTO
AnalysisReviewListDTO = _dto_mod.AnalysisReviewListDTO
BranchCarModelsDTO = _dto_mod.BranchCarModelsDTO
BranchOptionDTO = _dto_mod.BranchOptionDTO
BranchReviewsDTO = _dto_mod.BranchReviewsDTO
CarModelDTO = _dto_mod.CarModelDTO
CarModelTagDTO = _dto_mod.CarModelTagDTO
FilterOptionsDTO = _dto_mod.FilterOptionsDTO
PendingSummaryResultDTO = _dto_mod.PendingSummaryResultDTO
RatingDistributionDTO = _dto_mod.RatingDistributionDTO
RegionStatsDTO = _dto_mod.RegionStatsDTO
ReviewOutputDTO = _dto_mod.ReviewOutputDTO
SentimentStatsDTO = _dto_mod.SentimentStatsDTO
SummariesOutputDTO = _dto_mod.SummariesOutputDTO
SummaryStatsDTO = _dto_mod.SummaryStatsDTO
TagSentimentCountDTO = _dto_mod.TagSentimentCountDTO

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

_DT = datetime(2024, 6, 15, 9, 30, 0, tzinfo=timezone.utc)
_DT_ISO = "2024-06-15T09:30:00+00:00"


# ===========================================================================
# SummaryStatsDTO
# ===========================================================================


def test_summary_stats_dto_snapshot():
    """SummaryStatsDTO.model_dump() 출력 구조 검증."""
    dto = SummaryStatsDTO(total=10, total_reviews=100)
    result = dto.model_dump(by_alias=True)

    assert result == {"total": 10, "total_reviews": 100}
    assert isinstance(result["total"], int)
    assert isinstance(result["total_reviews"], int)


def test_summary_stats_dto_zero_values():
    """SummaryStatsDTO — 0값 엣지 케이스."""
    dto = SummaryStatsDTO(total=0, total_reviews=0)
    result = dto.model_dump(by_alias=True)

    assert result["total"] == 0
    assert result["total_reviews"] == 0


# ===========================================================================
# RegionStatsDTO
# ===========================================================================


def test_region_stats_dto_snapshot():
    """RegionStatsDTO.model_dump() 출력 구조 검증."""
    dto = RegionStatsDTO(region="서울", count=5, avg_rating=4.3, total_reviews=250)
    result = dto.model_dump(by_alias=True)

    assert result == {
        "region": "서울",
        "count": 5,
        "avg_rating": 4.3,
        "total_reviews": 250,
    }
    assert isinstance(result["avg_rating"], float)


# ===========================================================================
# RatingDistributionDTO  — 비식별자 키 검증
# ===========================================================================


def test_rating_distribution_dto_snapshot():
    """RatingDistributionDTO.model_dump() 키 이름이 비식별자("4.5-5.0" 등)임을 검증."""
    dto = RatingDistributionDTO(
        range_4_5_to_5_0=50,
        range_4_0_to_4_5=30,
        range_3_5_to_4_0=10,
        range_3_0_to_3_5=5,
        range_below_3_0=2,
    )
    result = dto.model_dump(by_alias=True)

    # 키 이름이 Python 식별자가 아닌 형태임을 검증
    assert "4.5-5.0" in result
    assert "4.0-4.5" in result
    assert "3.5-4.0" in result
    assert "3.0-3.5" in result
    assert "<3.0" in result

    assert result == {
        "4.5-5.0": 50,
        "4.0-4.5": 30,
        "3.5-4.0": 10,
        "3.0-3.5": 5,
        "<3.0": 2,
    }


def test_rating_distribution_dto_defaults():
    """RatingDistributionDTO — 기본값 모두 0."""
    dto = RatingDistributionDTO()
    result = dto.model_dump(by_alias=True)

    assert all(v == 0 for v in result.values())
    assert set(result.keys()) == {"4.5-5.0", "4.0-4.5", "3.5-4.0", "3.0-3.5", "<3.0"}


# ===========================================================================
# PendingSummaryResultDTO
# ===========================================================================


def test_pending_summary_result_dto_applied_only():
    """PendingSummaryResultDTO — applied만 있을 때 discarded 키 미포함."""
    dto = PendingSummaryResultDTO(period="1m", applied="2024-06-15")
    result = dto.model_dump(by_alias=True)

    assert "period" in result
    assert "applied" in result
    assert "discarded" not in result
    assert result["period"] == "1m"
    assert result["applied"] == "2024-06-15"


def test_pending_summary_result_dto_discarded_only():
    """PendingSummaryResultDTO — discarded만 있을 때 applied 키 미포함."""
    dto = PendingSummaryResultDTO(period="3m", discarded="2024-06-15")
    result = dto.model_dump(by_alias=True)

    assert "period" in result
    assert "discarded" in result
    assert "applied" not in result


def test_pending_summary_result_dto_both():
    """PendingSummaryResultDTO — applied, discarded 모두 있을 때."""
    dto = PendingSummaryResultDTO(period="6m", applied="A", discarded="B")
    result = dto.model_dump(by_alias=True)

    assert result == {"period": "6m", "applied": "A", "discarded": "B"}


def test_pending_summary_result_dto_neither():
    """PendingSummaryResultDTO — period만 있을 때 최소 구조."""
    dto = PendingSummaryResultDTO(period="all")
    result = dto.model_dump(by_alias=True)

    assert result == {"period": "all"}
    assert "applied" not in result
    assert "discarded" not in result


# ===========================================================================
# BranchReviewsDTO
# ===========================================================================


def test_branch_reviews_dto_snapshot():
    """BranchReviewsDTO.model_dump() 출력 구조 검증."""
    reviews = [{"id": 1, "content": "좋아요"}, {"id": 2, "content": "별로에요"}]
    dto = BranchReviewsDTO(reviews=reviews, total=2, car_models=["아반떼", "소나타"])
    result = dto.model_dump(by_alias=True)

    assert result == {
        "reviews": reviews,
        "total": 2,
        "car_models": ["아반떼", "소나타"],
    }


def test_branch_reviews_dto_empty_lists():
    """BranchReviewsDTO — 빈 리스트 엣지 케이스."""
    dto = BranchReviewsDTO(reviews=[], total=0)
    result = dto.model_dump(by_alias=True)

    assert result["reviews"] == []
    assert result["total"] == 0
    assert result["car_models"] == []


# ===========================================================================
# BranchCarModelsDTO
# ===========================================================================


def test_branch_car_models_dto_snapshot():
    """BranchCarModelsDTO.model_dump() 출력 구조 검증."""
    tag = CarModelTagDTO(name="청결", positive=10, negative=2, neutral=1, total=13)
    car = CarModelDTO(name="아반떼", review_count=15, tags=[tag])
    dto = BranchCarModelsDTO(branch_id=42, car_models=[car])
    result = dto.model_dump(by_alias=True)

    assert result == {
        "branch_id": 42,
        "car_models": [
            {
                "name": "아반떼",
                "review_count": 15,
                "tags": [
                    {
                        "name": "청결",
                        "positive": 10,
                        "negative": 2,
                        "neutral": 1,
                        "total": 13,
                    }
                ],
            }
        ],
    }
    # error 키는 없어야 함
    assert "error" not in result


def test_branch_car_models_dto_with_error():
    """BranchCarModelsDTO — error 있을 때만 error 키 포함."""
    dto = BranchCarModelsDTO(branch_id=99, car_models=[], error="데이터 없음")
    result = dto.model_dump(by_alias=True)

    assert "error" in result
    assert result["error"] == "데이터 없음"
    assert result["car_models"] == []


def test_branch_car_models_dto_no_error_key_when_none():
    """BranchCarModelsDTO — error=None이면 error 키 미포함."""
    dto = BranchCarModelsDTO(branch_id=1, car_models=[])
    result = dto.model_dump(by_alias=True)

    assert "error" not in result


# ===========================================================================
# FilterOptionsDTO
# ===========================================================================


def test_filter_options_dto_snapshot():
    """FilterOptionsDTO.model_dump() 출력 구조 검증."""
    branch = BranchOptionDTO(
        branch_id=10, branch_name="강남점", company_name="카모어", region="서울"
    )
    dto = FilterOptionsDTO(
        regions=["서울", "부산"],
        companies=["카모어", "롯데"],
        branches=[branch],
    )
    result = dto.model_dump(by_alias=True)

    assert result == {
        "regions": ["서울", "부산"],
        "companies": ["카모어", "롯데"],
        "branches": [
            {
                "branch_id": 10,
                "branch_name": "강남점",
                "company_name": "카모어",
                "region": "서울",
            }
        ],
    }


def test_filter_options_dto_empty():
    """FilterOptionsDTO — 빈 상태 엣지 케이스."""
    dto = FilterOptionsDTO()
    result = dto.model_dump(by_alias=True)

    assert result == {"regions": [], "companies": [], "branches": []}


# ===========================================================================
# AnalysisReviewListDTO
# ===========================================================================


def test_analysis_review_list_dto_snapshot():
    """AnalysisReviewListDTO.model_dump() 출력 구조 검증."""
    review = AnalysisReviewDTO(
        id=1,
        review_id=101,
        branch_id=10,
        branch_name="강남점",
        company_name="카모어",
        content="차가 깨끗했습니다",
        sentiment="positive",
        review_date="2024-06-15",
        rating_service=4.5,
        rating_car=4.0,
        rating_convenience=5.0,
        car_model="아반떼",
        is_new=False,
    )
    dto = AnalysisReviewListDTO(reviews=[review], total=1)
    result = dto.model_dump(by_alias=True)

    assert result["total"] == 1
    assert len(result["reviews"]) == 1

    r = result["reviews"][0]
    assert r["id"] == 1
    assert r["review_id"] == 101
    assert r["branch_id"] == 10
    assert r["branch_name"] == "강남점"
    assert r["company_name"] == "카모어"
    assert r["content"] == "차가 깨끗했습니다"
    assert r["sentiment"] == "positive"
    assert r["review_date"] == "2024-06-15"
    assert r["rating_service"] == 4.5
    assert r["rating_car"] == 4.0
    assert r["rating_convenience"] == 5.0
    assert r["car_model"] == "아반떼"
    assert r["is_new"] is False


def test_analysis_review_list_dto_empty():
    """AnalysisReviewListDTO — 빈 리스트 엣지 케이스."""
    dto = AnalysisReviewListDTO(reviews=[], total=0)
    result = dto.model_dump(by_alias=True)

    assert result == {"reviews": [], "total": 0}


def test_analysis_review_dto_none_fields():
    """AnalysisReviewDTO — nullable 필드가 None일 때 직렬화."""
    review = AnalysisReviewDTO(
        id=None,
        review_id=None,
        branch_id=None,
        branch_name="테스트점",
        company_name="업체",
        content="내용",
        sentiment=None,
        review_date=None,
        rating_service=None,
        rating_car=None,
        rating_convenience=None,
        car_model=None,
        is_new=False,
    )
    result = review.model_dump(by_alias=True)

    assert result["id"] is None
    assert result["review_id"] is None
    assert result["branch_id"] is None
    assert result["sentiment"] is None
    assert result["review_date"] is None
    assert result["rating_service"] is None
    assert result["rating_car"] is None
    assert result["rating_convenience"] is None
    assert result["car_model"] is None


# ===========================================================================
# SentimentStatsDTO
# ===========================================================================


def test_sentiment_stats_dto_snapshot():
    """SentimentStatsDTO.model_dump() 출력 구조 검증."""
    dto = SentimentStatsDTO(
        positive=70,
        negative=20,
        neutral=10,
        total=100,
        positive_ratio=0.70,
        negative_ratio=0.20,
    )
    result = dto.model_dump(by_alias=True)

    assert result == {
        "positive": 70,
        "negative": 20,
        "neutral": 10,
        "total": 100,
        "positive_ratio": 0.70,
        "negative_ratio": 0.20,
    }
    assert isinstance(result["positive_ratio"], float)
    assert isinstance(result["negative_ratio"], float)


# ===========================================================================
# TagSentimentCountDTO  — neutral 필드 제외 검증
# ===========================================================================


def test_tag_sentiment_count_dto_snapshot():
    """TagSentimentCountDTO.model_dump() — neutral 필드가 출력에서 제외됨을 검증."""
    dto = TagSentimentCountDTO(
        name="친절한 직원", total=100, positive=80, negative=10, neutral=10
    )
    result = dto.model_dump(by_alias=True)

    assert result == {
        "name": "친절한 직원",
        "total": 100,
        "positive": 80,
        "negative": 10,
    }
    # neutral은 BaseModel 필드이지만 model_dump()에서 제외됨
    assert "neutral" not in result


def test_tag_sentiment_count_dto_neutral_excluded_default():
    """TagSentimentCountDTO — neutral 기본값(0)도 출력에서 제외됨."""
    dto = TagSentimentCountDTO(name="청결", total=50, positive=40, negative=10)
    result = dto.model_dump(by_alias=True)

    assert "neutral" not in result
    assert set(result.keys()) == {"name", "total", "positive", "negative"}


# ===========================================================================
# ReviewOutputDTO
# ===========================================================================


def test_review_output_dto_with_datetime():
    """ReviewOutputDTO — datetime 값은 isoformat 문자열로 직렬화."""
    dto = ReviewOutputDTO(
        id="rev-001",
        date=_DT,
        content="아주 좋았습니다",
        keywords=["친절", "청결"],
        tag_sentiments="positive:친절한직원",
    )
    result = dto.model_dump(by_alias=True)

    assert result["id"] == "rev-001"
    assert result["date"] == _DT_ISO
    assert result["content"] == "아주 좋았습니다"
    assert result["keywords"] == ["친절", "청결"]
    assert result["tag_sentiments"] == "positive:친절한직원"


def test_review_output_dto_with_string_date():
    """ReviewOutputDTO — 문자열 date는 그대로 반환."""
    dto = ReviewOutputDTO(
        id=None,
        date="2024-06-15",
        content="내용",
        keywords=[],
        tag_sentiments="",
    )
    result = dto.model_dump(by_alias=True)

    assert result["date"] == "2024-06-15"
    assert result["id"] is None
    assert result["keywords"] == []


def test_review_output_dto_none_date():
    """ReviewOutputDTO — date=None 처리."""
    dto = ReviewOutputDTO(
        id="x",
        date=None,
        content="내용",
        keywords=["키워드"],
        tag_sentiments="neutral:태그",
    )
    result = dto.model_dump(by_alias=True)

    assert result["date"] is None


# ===========================================================================
# SummariesOutputDTO  — 비식별자 키 검증
# ===========================================================================


def test_summaries_output_dto_snapshot():
    """SummariesOutputDTO.model_dump() 키 이름이 "1m", "3m" 등 비식별자임을 검증."""
    dto = SummariesOutputDTO(
        summary_1m="1개월 요약",
        summary_3m="3개월 요약",
        summary_6m="6개월 요약",
        summary_1y="1년 요약",
        summary_all="전체 요약",
    )
    result = dto.model_dump(by_alias=True)

    assert result == {
        "1m": "1개월 요약",
        "3m": "3개월 요약",
        "6m": "6개월 요약",
        "1y": "1년 요약",
        "all": "전체 요약",
    }
    # 키가 Python 식별자가 아님을 확인
    assert "1m" in result
    assert "3m" in result
    assert "1y" in result


def test_summaries_output_dto_defaults():
    """SummariesOutputDTO — 기본값은 모두 빈 문자열."""
    dto = SummariesOutputDTO()
    result = dto.model_dump(by_alias=True)

    assert set(result.keys()) == {"1m", "3m", "6m", "1y", "all"}
    assert all(v == "" for v in result.values())
