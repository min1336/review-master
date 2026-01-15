"""
프롬프트 템플릿
"""
from typing import List


class PromptTemplates:
    """프롬프트 템플릿 관리"""

    SUMMARY_SYSTEM = """당신은 20년차 베테랑 프리미엄 렌터카 카모아 마케터입니다.
렌터카 이용 리뷰를 분석하여 신뢰감 있는 균형 잡힌 요약 문구를 작성합니다.

가이드라인:
1. 핵심 키워드를 자연스럽게 녹여내세요.
2. 고객에게 확실한 정보 전달을 한다는 뉘앙스를 담아 전문적인 어조를 사용하세요.
3. 반드시 3줄로 작성하세요: 긍정적인 내용 2줄 + 가벼운 아쉬운 점 1줄 (2:1 비율)
4. 아쉬운 점은 부드럽게 표현하세요 (예: "다소 아쉬운 점은...", "일부 이용객은...").
5. 마크다운, 이모지, 특수문자 없이 순수 텍스트만 작성하세요."""

    SUMMARY_USER = """다음 데이터를 바탕으로 렌터카 지점 요약을 작성해주세요.

- 분석 리뷰 수: {review_count}개
- 핵심 키워드: {keywords}
- 대표 리뷰:{reviews_text}

예시:
친절하고 신속한 서비스로 고객 만족도가 높습니다. 차량 상태가 깨끗하고 가격 대비 가성비가 뛰어납니다.
다소 아쉬운 점은 일부 이용객이 픽업 시 대기 시간이 길다고 느꼈습니다."""

    @classmethod
    def build_summary_prompt(
        cls,
        keywords: List[str],
        review_count: int,
        representative_reviews: List[str] = None
    ) -> tuple:
        """
        요약 프롬프트 생성

        Args:
            keywords: 키워드 리스트
            review_count: 리뷰 수
            representative_reviews: 대표 리뷰 리스트

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        # 대표 리뷰 포맷팅
        reviews_text = ""
        if representative_reviews:
            reviews_text = "\n\n[대표 리뷰]\n"
            for idx, review in enumerate(representative_reviews, 1):
                reviews_text += f'{idx}. "{review}"\n'

        user_prompt = cls.SUMMARY_USER.format(
            review_count=review_count,
            keywords=', '.join(keywords[:5]),
            reviews_text=reviews_text
        )

        return cls.SUMMARY_SYSTEM, user_prompt

    @classmethod
    def get_default_summary(cls, keywords: List[str]) -> str:
        """기본 요약 (LLM 실패시)"""
        if keywords:
            return f"{', '.join(keywords[:3])} 관련 긍정적인 리뷰가 많으며, 일부 개선 의견도 있습니다."
        return "전반적으로 긍정적인 리뷰가 많으며, 일부 개선 의견도 있습니다."
