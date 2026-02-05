"""
프롬프트 빌더 - 긍정 요약 전용

렌터카 지점 리뷰 요약을 위한 프롬프트 생성기
"""

from __future__ import annotations

from core.config import REGION_CONFIG, BranchType


class SummaryPromptBuilder:
    """요약 프롬프트 생성기"""

    # ============================================================
    # 시스템 프롬프트 (마케팅 카피 스타일)
    # ============================================================
    SUMMARY_SYSTEM = """<role>
당신은 카모아 렌터카 마케팅팀의 시니어 카피라이터입니다.
고객 리뷰를 분석하여 자연스럽게 읽히는 지점 소개 문구를 작성합니다.
</role>

<task>
주어진 리뷰 데이터를 바탕으로 해당 지점의 매력을 하나의 문단으로 작성하세요.
</task>

<output_format>
하나의 자연스러운 문단(200~250자)으로 작성:
- 서비스/직원 강점으로 시작
- 차량/시설 품질로 이어짐
- 지점 특성(위치/편의성)으로 연결
- 추천 포인트로 마무리

문장들이 자연스럽게 흘러가도록 연결하세요.
</output_format>

<writing_style>
- 마케팅 카피처럼 매끄럽고 설득력 있게
- 문장 간 자연스러운 연결 (접속사 활용: 또한, 특히, 덕분에)
- 읽는 사람이 방문하고 싶어지는 느낌
- 핵심 키워드를 자연스럽게 녹여서 표현
</writing_style>

<constraints>
- 마크다운, 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천", "무조건"
- 부정적 내용 작성 금지
- 제공된 키워드 중 최소 3개 자연스럽게 포함
</constraints>"""

    # ============================================================
    # 지점 유형별 Few-shot 예시 (자연스러운 문단)
    # ============================================================
    EXAMPLES_AIRPORT = """
<examples>
[공항 지점 예시]
키워드: 친절, 셔틀, 깨끗, 빠른, 편리
출력:
친절한 직원들의 빠른 응대로 공항 도착 후 바로 차량을 인수받을 수 있습니다. 깨끗하게 관리된 차량 상태가 인상적이며, 무료 셔틀버스가 정시 운행되어 터미널 이동도 수월합니다. 특히 픽업부터 반납까지 모든 절차가 간편하게 진행되어, 여행의 시작과 마무리를 편리하게 할 수 있는 지점입니다.
</examples>"""

    EXAMPLES_CITY = """
<examples>
[시내 지점 예시]
키워드: 친절, 가성비, 위치, 깨끗, 반납
출력:
친절한 직원분들의 신속한 응대로 대기 시간 없이 바로 출발할 수 있습니다. 차량은 항상 깨끗하게 관리되어 있고, 합리적인 가격으로 가성비가 뛰어납니다. 역에서 가까운 위치 덕분에 접근성이 좋으며, 반납 절차도 간편해서 비즈니스 출장이나 일상적인 이용에 적합한 지점입니다.
</examples>"""

    EXAMPLES_TOURIST = """
<examples>
[관광지 지점 예시]
키워드: 친절, 픽업, 깨끗, 가성비, 편리
출력:
친절한 직원분들이 상세한 안내와 함께 여행 정보까지 제공해주셔서 든든합니다. 깨끗하게 관리된 차량으로 쾌적한 드라이브를 즐길 수 있으며, 공항 픽업 서비스도 원활하게 운영됩니다. 합리적인 가격에 편리한 서비스까지 갖춰, 여행을 더욱 즐겁게 만들어주는 지점입니다.
</examples>"""

    EXAMPLES_DEFAULT = """
<examples>
[기본 예시]
키워드: 친절, 깨끗, 가성비, 위치, 서비스
출력:
친절한 직원분들의 빠른 응대로 기분 좋게 이용을 시작할 수 있습니다. 차량은 깨끗하게 관리되어 있어 쾌적하며, 합리적인 가격으로 가성비도 뛰어납니다. 좋은 위치와 체계적인 서비스 덕분에 처음 이용하시는 분들도 편하게 이용하실 수 있는 지점입니다.
</examples>"""

    @classmethod
    def detect_branch_type(cls, branch_name: str) -> BranchType:
        """
        지점명으로 유형 판별

        Args:
            branch_name: 지점명

        Returns:
            BranchType: 지점 유형
        """
        if not branch_name:
            return BranchType.DEFAULT

        branch_lower = branch_name.lower()

        # 공항 지점 체크
        for keyword in REGION_CONFIG["airport_keywords"]:
            if keyword in branch_lower:
                return BranchType.AIRPORT

        # 관광지 지점 체크
        for keyword in REGION_CONFIG["tourist_keywords"]:
            if keyword in branch_lower:
                return BranchType.TOURIST

        # 시내 지점 (기본)
        return BranchType.CITY

    @classmethod
    def extract_region(cls, branch_name: str) -> str | None:
        """
        업체명에서 지역명 추출

        Args:
            branch_name: 업체명 (예: '고고렌트카 강남점')

        Returns:
            지역명 (예: '강남') 또는 None
        """
        if not branch_name:
            return None

        for region in REGION_CONFIG["regions"]:
            if region in branch_name:
                return region

        return None

    @classmethod
    def get_examples_for_type(cls, branch_type: BranchType) -> str:
        """지점 유형별 예시 반환"""
        examples_map = {
            BranchType.AIRPORT: cls.EXAMPLES_AIRPORT,
            BranchType.CITY: cls.EXAMPLES_CITY,
            BranchType.TOURIST: cls.EXAMPLES_TOURIST,
            BranchType.DEFAULT: cls.EXAMPLES_DEFAULT,
        }
        return examples_map.get(branch_type, cls.EXAMPLES_DEFAULT)

    @classmethod
    def create_summary_prompt(
        cls,
        keywords: list[str],
        review_count: int,
        representative_reviews: list[str] | None = None,
        branch_name: str | None = None,
    ) -> tuple:
        """
        요약 프롬프트 생성

        Args:
            keywords: 키워드 리스트
            review_count: 리뷰 수
            representative_reviews: 대표 리뷰 리스트
            branch_name: 지점명 (유형 판별용)

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        # 지점 유형 판별
        branch_type = cls.detect_branch_type(branch_name)

        # 지역 추출
        region = cls.extract_region(branch_name)
        region_emphasis = (
            REGION_CONFIG["region_emphasis"].get(region, []) if region else []
        )

        # 시스템 프롬프트 = 기본 + 유형별 예시
        system_prompt = cls.SUMMARY_SYSTEM + cls.get_examples_for_type(branch_type)

        # 대표 리뷰 포맷팅
        reviews_text = ""
        if representative_reviews:
            for idx, review in enumerate(representative_reviews, 1):
                review_truncated = str(review)[:100]
                reviews_text += f'{idx}. "{review_truncated}"\n'

        # 지역 강조 텍스트
        region_text = ""
        if region:
            region_text = f"\n- 지역: {region}"
            if region_emphasis:
                region_text += f" (강조 포인트: {', '.join(region_emphasis)})"

        # 유저 프롬프트 생성
        user_prompt = f"""다음 데이터를 바탕으로 렌터카 지점 소개 문구를 작성해주세요.

<data>
- 지점명: {branch_name or "미지정"}
- 분석 리뷰 수: {review_count}개
- 핵심 키워드: {", ".join(keywords[:5])}{region_text}
</data>

<representative_reviews>
{reviews_text if reviews_text else "(리뷰 없음)"}
</representative_reviews>

위 데이터를 기반으로 자연스럽게 이어지는 하나의 문단(200~250자)을 작성하세요."""

        return system_prompt, user_prompt

    @classmethod
    def get_default_summary(cls, keywords: list[str]) -> str:
        """기본 요약 (LLM 실패시)"""
        if keywords:
            return f"{', '.join(keywords[:3])} 관련 긍정적인 리뷰가 많습니다."
        return "전반적으로 긍정적인 리뷰가 많습니다."


class RichSummaryPromptBuilder:
    """태그+감정+리뷰 기반 풍부한 요약 프롬프트 생성기"""

    SYSTEM_PROMPT = """<role>
당신은 카모아 렌터카 리뷰 분석 전문가입니다.
태그별 감정 데이터와 실제 리뷰를 분석하여 객관적이고 균형 잡힌 요약을 작성합니다.
</role>

<task>
주어진 태그별 감정 통계와 대표 리뷰를 바탕으로 해당 지점의 기간별 요약을 작성하세요.
</task>

<output_format>
하나의 자연스러운 문단(200~300자)으로 작성:
1. 기간과 총 리뷰 수 소개
2. 긍정적 피드백이 많은 태그 언급
3. 전반적인 평가로 마무리
</output_format>

<writing_style>
- 객관적이고 분석적인 톤
- 긍정과 부정을 균형 있게 서술
- "~에 대한 긍정적인 피드백이 주를 이루는 반면" 같은 자연스러운 연결
- 숫자 데이터를 활용한 구체적 표현
</writing_style>

<constraints>
- 마크다운, 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천"
- 제공되지 않은 정보 추측 금지
</constraints>"""

    @classmethod
    def create_prompt(
        cls,
        branch_name: str,
        start_date: str,
        end_date: str,
        total_reviews: int,
        tag_sentiments: list[dict],
        sentiment_stats: dict,
        sample_reviews: list[str],
    ) -> tuple[str, str]:
        """
        풍부한 요약 프롬프트 생성

        Args:
            branch_name: 지점명
            start_date: 시작일 (YYYY년 M월 D일 형식)
            end_date: 종료일
            total_reviews: 총 리뷰 수
            tag_sentiments: 태그별 감정 [{name, positive, negative, neutral, total}]
            sentiment_stats: 전체 감정 통계 {positive, negative, neutral, total}
            sample_reviews: 대표 리뷰 텍스트 리스트

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        # 태그 감정 분석 텍스트 생성
        positive_tags = []
        negative_tags = []

        for tag in tag_sentiments:
            name = tag.get("name", "")
            pos = tag.get("positive", 0)
            neg = tag.get("negative", 0)
            total = tag.get("total", 0)

            if total == 0:
                continue

            pos_ratio = round(pos / total * 100) if total > 0 else 0
            neg_ratio = round(neg / total * 100) if total > 0 else 0

            if pos_ratio >= 60:
                positive_tags.append(f"{name}(긍정 {pos_ratio}%)")
            if neg_ratio >= 30:
                negative_tags.append(f"{name}(부정 {neg_ratio}%)")

        # 전체 감정 비율
        total_sentiment = sentiment_stats.get("total", 0)
        if total_sentiment > 0:
            overall_positive = round(
                sentiment_stats.get("positive", 0) / total_sentiment * 100
            )
            overall_negative = round(
                sentiment_stats.get("negative", 0) / total_sentiment * 100
            )
        else:
            overall_positive = 0
            overall_negative = 0

        # 대표 리뷰 포맷팅
        reviews_text = ""
        if sample_reviews:
            for idx, review in enumerate(sample_reviews[:5], 1):
                review_truncated = str(review)[:100]
                reviews_text += f'{idx}. "{review_truncated}"\n'

        user_prompt = f"""다음 데이터를 바탕으로 렌터카 지점의 기간별 요약을 작성해주세요.

<data>
- 지점명: {branch_name}
- 분석 기간: {start_date} ~ {end_date}
- 총 리뷰 수: {total_reviews}건
- 전체 긍정률: {overall_positive}%, 부정률: {overall_negative}%
</data>

<tag_analysis>
긍정 평가 높은 태그: {', '.join(positive_tags) if positive_tags else '없음'}
부정 평가 있는 태그: {', '.join(negative_tags) if negative_tags else '없음'}
</tag_analysis>

<sample_reviews>
{reviews_text if reviews_text else "(대표 리뷰 없음)"}
</sample_reviews>

위 데이터를 기반으로 자연스럽게 이어지는 하나의 문단(200~300자)을 작성하세요."""

        return cls.SYSTEM_PROMPT, user_prompt

    @classmethod
    def get_insufficient_reviews_message(
        cls, branch_name: str, review_count: int
    ) -> str:
        """리뷰 부족 시 기본 메시지"""
        return (
            f"{branch_name}의 분석 가능한 리뷰가 {review_count}건으로 충분하지 않습니다. "
            "더 많은 리뷰가 축적되면 상세한 분석이 가능합니다."
        )
