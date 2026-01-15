"""
프롬프트 템플릿 v2
- 구조화된 XML 태그
- 지점 유형별 Few-shot 예시
"""
from typing import List, Optional
from enum import Enum


class BranchType(Enum):
    """지점 유형"""
    AIRPORT = "airport"      # 공항
    CITY = "city"            # 시내
    TOURIST = "tourist"      # 관광지/제주
    DEFAULT = "default"      # 기본


class PromptTemplates:
    """프롬프트 템플릿 관리 v2"""

    # ============================================================
    # 기본 시스템 프롬프트 (구조화)
    # ============================================================
    SUMMARY_SYSTEM_BASE = """<role>
당신은 카모아 렌터카 마케팅팀의 시니어 카피라이터입니다.
고객 리뷰를 분석하여 신뢰감 있는 지점 소개 문구를 작성합니다.
</role>

<task>
주어진 리뷰 데이터를 바탕으로 해당 지점의 3줄 요약을 작성하세요.
</task>

<output_format>
정확히 3문장을 작성하세요:
- 1번째 문장: 가장 많이 언급된 긍정적 특징 (서비스/직원 관련)
- 2번째 문장: 두 번째로 많이 언급된 긍정적 특징 (차량/시설 관련)
- 3번째 문장: "다소 아쉬운 점은" 으로 시작하는 개선점 1가지

각 문장: 20-40자, 마침표로 종료
</output_format>

<constraints>
- 마크다운, 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천", "무조건"
- 제공된 키워드 중 최소 2개 자연스럽게 포함
- 부정적 내용은 완곡하게 표현
</constraints>"""

    # ============================================================
    # 지점 유형별 Few-shot 예시
    # ============================================================
    EXAMPLES_AIRPORT = """
<examples>
[공항 지점 예시 1]
키워드: 빠른, 친절, 깨끗, 편리, 대기
→ 공항에서 가까워 이용이 편리하고 직원분들이 친절합니다.
차량 상태가 깨끗하고 인수 절차가 빠릅니다.
다소 아쉬운 점은 성수기에 대기 시간이 길어질 수 있습니다.

[공항 지점 예시 2]
키워드: 셔틀, 신속, 차량상태, 픽업, 반납
→ 셔틀 서비스가 신속하여 공항 이동이 편리합니다.
차량 상태가 양호하고 픽업 절차가 간편합니다.
다소 아쉬운 점은 반납 시 혼잡할 수 있습니다.
</examples>"""

    EXAMPLES_CITY = """
<examples>
[시내 지점 예시 1]
키워드: 가성비, 친절, 차량상태, 위치, 주차
→ 합리적인 가격에 친절한 서비스를 받을 수 있습니다.
차량 상태 관리가 잘 되어 있어 만족도가 높습니다.
다소 아쉬운 점은 주차 공간이 협소하다는 의견이 있습니다.

[시내 지점 예시 2]
키워드: 접근성, 깨끗, 직원, 가격, 대기
→ 역과 가까워 접근성이 좋고 직원이 친절합니다.
차량이 깨끗하고 가격이 합리적입니다.
다소 아쉬운 점은 대기 시간이 다소 길 수 있습니다.
</examples>"""

    EXAMPLES_TOURIST = """
<examples>
[관광지/제주 지점 예시 1]
키워드: 가성비, 차량, 깨끗, 친절, 성수기
→ 가성비가 좋고 차량 관리가 잘 되어 있습니다.
직원분들이 친절하고 설명이 자세합니다.
다소 아쉬운 점은 성수기에 원하는 차량 선택이 어려울 수 있습니다.

[관광지/제주 지점 예시 2]
키워드: 제주, 렌트, 편리, 차량상태, 가격
→ 제주 여행에 편리하고 렌트 절차가 간단합니다.
차량 상태가 양호하고 가격이 합리적입니다.
다소 아쉬운 점은 일부 차종의 재고가 한정적일 수 있습니다.
</examples>"""

    EXAMPLES_DEFAULT = """
<examples>
[예시 1]
키워드: 친절, 깨끗, 빠른, 가성비, 차량
→ 직원이 친절하고 서비스가 빠릅니다.
차량이 깨끗하고 가성비가 좋습니다.
다소 아쉬운 점은 일부 시간대에 대기가 있을 수 있습니다.

[예시 2]
키워드: 서비스, 차량상태, 가격, 위치, 직원
→ 서비스가 좋고 직원이 친절합니다.
차량 상태가 양호하고 가격이 합리적입니다.
다소 아쉬운 점은 위치가 다소 불편하다는 의견이 있습니다.
</examples>"""

    # ============================================================
    # 유저 프롬프트 템플릿
    # ============================================================
    SUMMARY_USER = """다음 데이터를 바탕으로 렌터카 지점 요약을 작성해주세요.

<data>
- 지점명: {branch_name}
- 분석 리뷰 수: {review_count}개
- 핵심 키워드: {keywords}
</data>

<representative_reviews>
{reviews_text}
</representative_reviews>

위 데이터를 기반으로 3문장 요약을 작성하세요."""

    # ============================================================
    # 지점 유형 판별 키워드
    # ============================================================
    AIRPORT_KEYWORDS = ['공항', '인천공항', '김포공항', '제주공항', '김해공항', '대구공항']
    TOURIST_KEYWORDS = ['제주', '부산', '강릉', '속초', '여수', '경주', '전주']

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
        for keyword in cls.AIRPORT_KEYWORDS:
            if keyword in branch_lower:
                return BranchType.AIRPORT

        # 관광지 지점 체크
        for keyword in cls.TOURIST_KEYWORDS:
            if keyword in branch_lower:
                return BranchType.TOURIST

        # 시내 지점 (기본)
        return BranchType.CITY

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
    def build_summary_prompt(
        cls,
        keywords: List[str],
        review_count: int,
        representative_reviews: List[str] = None,
        branch_name: str = None
    ) -> tuple:
        """
        요약 프롬프트 생성 v2

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

        # 시스템 프롬프트 = 기본 + 유형별 예시
        system_prompt = cls.SUMMARY_SYSTEM_BASE + cls.get_examples_for_type(branch_type)

        # 대표 리뷰 포맷팅
        reviews_text = ""
        if representative_reviews:
            for idx, review in enumerate(representative_reviews, 1):
                # 리뷰 100자 제한
                review_truncated = str(review)[:100]
                reviews_text += f'{idx}. "{review_truncated}"\n'

        # 유저 프롬프트 생성
        user_prompt = cls.SUMMARY_USER.format(
            branch_name=branch_name or "미지정",
            review_count=review_count,
            keywords=', '.join(keywords[:5]),
            reviews_text=reviews_text if reviews_text else "(리뷰 없음)"
        )

        return system_prompt, user_prompt

    @classmethod
    def get_default_summary(cls, keywords: List[str]) -> str:
        """기본 요약 (LLM 실패시)"""
        if keywords:
            return f"{', '.join(keywords[:3])} 관련 긍정적인 리뷰가 많으며, 일부 개선 의견도 있습니다."
        return "전반적으로 긍정적인 리뷰가 많으며, 일부 개선 의견도 있습니다."

    # ============================================================
    # 레거시 호환 (v1)
    # ============================================================
    SUMMARY_SYSTEM = SUMMARY_SYSTEM_BASE + EXAMPLES_DEFAULT
