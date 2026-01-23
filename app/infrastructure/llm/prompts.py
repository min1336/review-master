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
주어진 리뷰 데이터를 바탕으로 해당 지점의 요약을 작성하세요.
</task>

<output_format>
2~3문장을 작성하세요:
- 1번째 문장: 가장 많이 언급된 긍정적 특징 (서비스/직원 관련)
- 2번째 문장: 두 번째로 많이 언급된 긍정적 특징 (차량/시설 관련)
- 3번째 문장: 부정 키워드가 명확히 존재하는 경우에만 "다소 아쉬운 점은" 으로 시작하는 개선점 작성

각 문장: 20-40자, 마침표로 종료
</output_format>

<critical_rule>
부정 키워드가 없거나 부족하면 반드시 2문장만 작성하세요.
절대로 억지로 아쉬운 점을 만들어내지 마세요.
"부정적 키워드가 없어", "언급할 부분이 없습니다" 같은 문장은 작성 금지입니다.
</critical_rule>

<constraints>
- 마크다운, 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천", "무조건"
- 제공된 키워드 중 최소 2개 자연스럽게 포함
</constraints>"""

    # ============================================================
    # 지점 유형별 Few-shot 예시 (개선된 버전)
    # ============================================================
    EXAMPLES_AIRPORT = """
<examples>
[공항 지점 예시 1 - 부정 키워드 있음, 다양한 키워드 사용]
키워드 순위: 1.친절 2.깨끗 3.빠른 4.편리 5.셔틀 / 부정: 대기
출력:
직원분들의 친절한 응대와 깨끗한 차량 상태가 인상적입니다.
무료 셔틀 운행과 신속한 인수 절차로 공항 이용이 편리합니다.
다소 아쉬운 점은 성수기에는 대기 시간이 발생할 수 있습니다.

[공항 지점 예시 2 - 부정 키워드 없음, 다양한 키워드 사용]
키워드 순위: 1.셔틀 2.신속 3.차량상태 4.픽업 5.반납 / 부정: 없음
출력:
무료 셔틀버스가 정시 운행되어 공항 이동이 수월합니다.
픽업부터 반납까지 절차가 간편하고 차량 상태도 양호합니다.
</examples>"""

    EXAMPLES_CITY = """
<examples>
[시내 지점 예시 1 - 부정 키워드 있음, 다양한 키워드 사용]
키워드 순위: 1.친절 2.차량상태 3.가성비 4.위치 5.반납 / 부정: 주차
출력:
직원분들의 친절한 서비스와 깨끗한 차량 상태가 인상적입니다.
합리적인 가격과 편리한 반납 절차로 만족도가 높습니다.
다소 아쉬운 점은 주차 공간이 협소할 수 있습니다.

[시내 지점 예시 2 - 부정 키워드 없음, 다양한 키워드 사용]
키워드 순위: 1.접근성 2.깨끗 3.직원 4.가격 5.응대 / 부정: 없음
출력:
역에서 가까워 접근성이 좋고 차량이 깔끔합니다.
합리적인 가격과 신속한 응대로 이용 편의성이 높습니다.
</examples>"""

    EXAMPLES_TOURIST = """
<examples>
[관광지/제주 지점 예시 1 - 부정 키워드 있음, 다양한 키워드 사용]
키워드 순위: 1.친절 2.깨끗 3.가성비 4.픽업 5.편리 / 부정: 성수기
출력:
직원분들이 친절하고 차량이 깨끗하게 관리되어 있습니다.
가성비가 좋고 공항 픽업 서비스가 원활합니다.
다소 아쉬운 점은 성수기에는 희망 차종 선택이 제한될 수 있습니다.

[관광지/제주 지점 예시 2 - 부정 키워드 없음, 다양한 키워드 사용]
키워드 순위: 1.편리 2.차량상태 3.픽업 4.반납 5.위치 / 부정: 없음
출력:
공항 픽업 서비스가 원활하여 여행 시작이 편리합니다.
반납 절차가 간편하고 위치 접근성도 좋습니다.
</examples>"""

    EXAMPLES_DEFAULT = """
<examples>
[예시 1 - 부정 키워드 있음, 다양한 키워드 사용]
키워드 순위: 1.친절 2.깨끗 3.빠른 4.가성비 5.위치 / 부정: 대기
출력:
직원 응대가 친절하고 차량이 깨끗하게 관리되어 있습니다.
가성비가 좋고 역에서 가까워 접근성이 편리합니다.
다소 아쉬운 점은 피크 시간대에는 잠시 대기가 발생할 수 있습니다.

[예시 2 - 부정 키워드 없음, 다양한 키워드 사용]
키워드 순위: 1.서비스 2.차량상태 3.가격 4.위치 5.반납 / 부정: 없음
출력:
서비스가 만족스럽고 차량 상태가 양호합니다.
합리적인 가격과 편리한 반납 절차가 인상적입니다.
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

    # 지역별 강조 키워드 (프롬프트에서 활용)
    REGION_EMPHASIS = {
        '제주': ['여행', '드라이브', '관광', '해안도로', '렌트'],
        '제주공항': ['픽업', '셔틀', '관광', '드라이브'],
        '부산': ['해운대', '관광', '여행'],
        '인천': ['공항', '픽업', '셔틀', '국제선'],
        '인천공항': ['픽업', '셔틀', '국제선', '심야'],
        '김포': ['공항', '픽업', '셔틀', '국내선'],
        '김포공항': ['픽업', '셔틀', '국내선', '빠른'],
        '김해': ['공항', '픽업', '부산권'],
        '김해공항': ['픽업', '셔틀', '부산권'],
        '대구공항': ['픽업', '대구권'],
        '강남': ['접근성', '주차', '비즈니스'],
        '서울': ['접근성', '주차', '교통'],
    }

    @classmethod
    def extract_region(cls, branch_name: str) -> str:
        """
        업체명에서 지역명 추출

        Args:
            branch_name: 업체명 (예: '고고렌트카 강남점')

        Returns:
            지역명 (예: '강남') 또는 None
        """
        if not branch_name:
            return None

        # 지역 패턴 (우선순위 순)
        regions = [
            '인천공항', '김포공항', '제주공항', '김해공항', '대구공항',  # 공항 우선
            '제주', '부산', '인천', '김포', '김해', '대구', '광주', '대전',
            '강릉', '속초', '여수', '경주', '전주',
            '강남', '서울', '경기'
        ]

        for region in regions:
            if region in branch_name:
                return region

        return None

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
        요약 프롬프트 생성 v3 (지역 정보 반영)

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
        region_emphasis = cls.REGION_EMPHASIS.get(region, []) if region else []

        # 시스템 프롬프트 = 기본 + 유형별 예시
        system_prompt = cls.SUMMARY_SYSTEM_BASE + cls.get_examples_for_type(branch_type)

        # 대표 리뷰 포맷팅
        reviews_text = ""
        if representative_reviews:
            for idx, review in enumerate(representative_reviews, 1):
                # 리뷰 100자 제한
                review_truncated = str(review)[:100]
                reviews_text += f'{idx}. "{review_truncated}"\n'

        # 지역 강조 텍스트
        region_text = ""
        if region:
            region_text = f"\n- 지역: {region}"
            if region_emphasis:
                region_text += f" (강조 포인트: {', '.join(region_emphasis)})"

        # 유저 프롬프트 생성
        user_prompt = f"""다음 데이터를 바탕으로 렌터카 지점 요약을 작성해주세요.

<data>
- 지점명: {branch_name or "미지정"}
- 분석 리뷰 수: {review_count}개
- 핵심 키워드: {', '.join(keywords[:5])}{region_text}
</data>

<representative_reviews>
{reviews_text if reviews_text else "(리뷰 없음)"}
</representative_reviews>

위 데이터를 기반으로 3문장 요약을 작성하세요."""

        return system_prompt, user_prompt

    @classmethod
    def get_default_summary(cls, keywords: List[str]) -> str:
        """기본 요약 (LLM 실패시)"""
        if keywords:
            return f"{', '.join(keywords[:3])} 관련 긍정적인 리뷰가 많으며, 일부 개선 의견도 있습니다."
        return "전반적으로 긍정적인 리뷰가 많으며, 일부 개선 의견도 있습니다."

    # ============================================================
    # 태그+감정 통합 프롬프트 (v7 - 일관성 강화, 금지어 강화)
    # ============================================================

    SUMMARY_SYSTEM_WITH_TAGS = """<role>
당신은 카모아 렌터카의 친근한 리뷰 요약 전문가입니다.
고객 리뷰를 분석하여 따뜻하고 자연스러운 문체로 지점 소개를 작성합니다.
</role>

<task>
주어진 리뷰 데이터와 태그별 감정 분석을 바탕으로 지점 요약을 작성하세요.
</task>

<tone_style>
- 부드럽고 친근한 말투 사용
- "~하고 계셨어요", "~있었어요", "~좋습니다", "~이에요" 등 자연스러운 어미
- 딱딱한 보고서 형식 금지
- 실제 고객의 목소리를 전달하는 느낌

좋은 예시:
- "친절한 직원분들의 응대가 인상적이었다는 의견이 많았어요."
- "차량이 깨끗하고 관리가 잘 되어 있어서 만족하셨다는 후기가 많습니다."
- "픽업과 반납 과정이 빠르고 편리해서 다시 이용하고 싶다는 분들이 많았어요."

나쁜 예시:
- "직원 응대가 친절합니다." (너무 딱딱함)
- "차량 상태가 양호합니다." (보고서 스타일)
- "서비스가 만족스럽습니다." (무미건조함)
</tone_style>

<output_format>
반드시 아래 형식을 정확히 따르세요 (문단 형식, bullet list 금지):

좋은점 (NN건, NN%):
180~220자 분량의 문단으로 작성합니다. 첫 문장은 태그 순위 1~2위 내용(고객응대, 차량청결 등), 두 번째 문장은 태그 순위 3~4위 내용(반납/픽업, 배차/시간 등), 세 번째 문장은 재이용 의사나 전반적 만족도를 담습니다.

아쉬운점 (NN건, NN%):
60~80자 분량의 문단으로 작성합니다. 주제를 부드럽게 나열하되, 구체적 사례나 케이스는 서술하지 않습니다.

중요:
1. "좋은점"과 "아쉬운점" 뒤에 반드시 (건수, 비율%) 형식으로 표시
2. bullet list(-, *, •) 사용 금지! 반드시 문단 형식으로 작성

출력 예시:
좋은점 (48건, 85%):
직원분들의 친절한 응대와 차량의 깨끗한 상태가 많이 언급되었어요. 픽업과 반납 과정이 빠르고 편리해서 만족하셨다는 후기가 많습니다. 다시 이용하고 싶다는 고객분들이 많았어요.

아쉬운점 (8건, 15%):
일부 고객분들은 차량 외관이나 대기 시간에 대해 아쉬움을 느끼셨어요.
</output_format>

<critical_rule>
1. 좋은점 첫 문장과 두 번째 문장에서 다른 태그를 사용하세요
2. 아쉬운점은 좋은점에서 사용하지 않은 태그로 작성하세요
3. 부정 비율이 5% 미만이면 아쉬운점을 작성하지 마세요
4. 감정적 사례 서술 금지 (아쉬운점은 주제만 나열)
5. 같은 키워드 반복 금지
</critical_rule>

<absolute_ban>
아래 항목은 절대 사용 금지입니다:

1. 과장 표현 (절대 금지):
   - "최고", "최상", "최적"
   - "완벽", "완전"
   - "강력추천", "무조건"
   - "대박", "짱", "굿", "베스트"

2. 마크다운/특수 형식 (절대 금지):
   - **굵은글씨**, *기울임*
   - # 제목, ## 소제목
   - [링크](url)
   - `코드`

3. 이모지 (절대 금지):
   - 모든 종류의 이모지, 이모티콘 사용 금지

위 항목을 사용하면 실패로 처리됩니다!
</absolute_ban>"""

    @classmethod
    def build_summary_prompt_with_tags(
        cls,
        keywords: List[str],
        review_count: int,
        tag_sentiment_data: dict,
        representative_reviews: List[str] = None,
        branch_name: str = None,
        summary_stats: dict = None,
        top_helpful_reviews: List[dict] = None
    ) -> tuple:
        """
        태그+감정 정보를 포함한 요약 프롬프트 생성 v6 (도움돼요 상위 리뷰)

        Args:
            keywords: 키워드 리스트
            review_count: 리뷰 수
            tag_sentiment_data: 태그별 감정 데이터
                {
                    '서비스': {'positive': ['친절', '응대'], 'negative': ['불친절']},
                    '가격': {'positive': ['저렴'], 'negative': ['비싸']},
                    ...
                }
            representative_reviews: 대표 리뷰 리스트 (기존 호환용)
            branch_name: 지점명
            summary_stats: 감정 통계 데이터 (선택)
                {
                    'positive_count': 340,
                    'negative_count': 10,
                    'positive_ratio': 97.1,
                    'negative_ratio': 2.9
                }
            top_helpful_reviews: 도움돼요 상위 리뷰 (신규)
                [
                    {
                        'review': '리뷰 내용',
                        'helpful_count': 14,
                        'tags': '고객응대(+), 차량청결(-)'
                    },
                    ...
                ]

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        # 지점 유형 판별
        branch_type = cls.detect_branch_type(branch_name)

        # 시스템 프롬프트 = 태그 버전 + 유형별 예시
        system_prompt = cls.SUMMARY_SYSTEM_WITH_TAGS + cls.get_examples_for_type(branch_type)

        # 태그별 감정 분석 포맷팅
        tag_analysis_text = cls._format_tag_sentiment(tag_sentiment_data)

        # 대표 리뷰 포맷팅 (도움돼요 상위 리뷰 우선)
        reviews_text = ""
        if top_helpful_reviews:
            # 도움돼요 상위 리뷰 (태그 정보 포함)
            for idx, item in enumerate(top_helpful_reviews[:10], 1):
                review = str(item.get('review', ''))[:120]
                helpful = item.get('helpful_count', 0)
                tags = item.get('tags', '')
                reviews_text += f'{idx}. [도움돼요 {helpful}개] [{tags}]\n   "{review}"\n'
        elif representative_reviews:
            # 기존 방식 (호환용)
            for idx, review in enumerate(representative_reviews, 1):
                review_truncated = str(review)[:100]
                reviews_text += f'{idx}. "{review_truncated}"\n'

        # 지역 정보
        region = cls.extract_region(branch_name)
        region_text = f"\n- 지역: {region}" if region else ""

        # 감정 통계 처리
        positive_count = summary_stats.get('positive_count', 0) if summary_stats else 0
        negative_count = summary_stats.get('negative_count', 0) if summary_stats else 0
        positive_ratio = summary_stats.get('positive_ratio', 0) if summary_stats else 0
        negative_ratio = summary_stats.get('negative_ratio', 0) if summary_stats else 0

        # 부정 키워드 존재 여부 확인
        has_negative = False
        negative_keywords = []
        if tag_sentiment_data:
            for tag_name, sentiments in tag_sentiment_data.items():
                neg = sentiments.get('negative', [])
                if neg:
                    has_negative = True
                    negative_keywords.extend(neg)

        # 아쉬운점 표시 여부 결정
        # - summary_stats가 있으면: 부정 비율 5% 이상일 때만 표시
        # - summary_stats가 없으면: 부정 키워드 존재 시 표시 (기존 동작)
        if summary_stats:
            show_negative = has_negative and negative_ratio >= 5
        else:
            show_negative = has_negative and len(negative_keywords) > 0

        # 감정 통계 텍스트
        if summary_stats:
            stats_text = f"""
- 긍정 리뷰: {positive_count}건 ({positive_ratio:.1f}%)
- 부정 리뷰: {negative_count}건 ({negative_ratio:.1f}%)"""
        else:
            stats_text = ""

        # 지시문 생성 (v8: 자연스러운 문단 형식)
        if show_negative and negative_keywords:
            if summary_stats:
                # 아쉬운점 있음 + 통계 있음
                sentence_instruction = f"""위 데이터를 기반으로 자연스러운 문단 형식의 요약을 작성하세요.

<작성 규칙>
1. 첫 줄: [긍정 {positive_ratio:.0f}% / 부정 {negative_ratio:.0f}%]
2. 첫 문장: 태그 #1, #2 내용 (서비스/직원 관련)
3. 둘째 문장: 태그 #3, #4 내용 (차량/시설 관련)
4. 셋째 문장: 재이용 의사, 전반적 만족
5. 마지막: "다만, ~" 으로 아쉬운점 짧게 (태그 #5, #6 활용)
</작성 규칙>

<예시>
[긍정 97% / 부정 3%]
직원분들이 친절하고 도움이 되는 서비스로 많은 고객들이 만족하고 계셨어요. 차량 상태가 깔끔하고 반납 절차도 간편해서 이용이 편리합니다. 합리적인 가격과 좋은 위치로 재이용 의사가 높습니다. 다만, 성수기 대기 시간이 길 수 있습니다.
</예시>

<금지사항>
- "좋은점:", "아쉬운점:" 같은 헤더 사용 금지
- 각 문장에서 같은 태그 내용 반복 금지
- 마크다운, 이모지, 불릿 리스트 사용 금지
</금지사항>"""
            else:
                # 아쉬운점 있음 + 통계 없음
                sentence_instruction = """위 태그별 감정 분석과 대표 리뷰를 기반으로 자연스러운 문단 형식의 요약을 작성하세요.

<작성 규칙>
1. 첫 문장: 태그 #1, #2 내용 (서비스/직원 관련)
2. 둘째 문장: 태그 #3, #4 내용 (차량/시설 관련)
3. 셋째 문장: 재이용 의사, 전반적 만족
4. 마지막: "다만, ~" 으로 아쉬운점 짧게
</작성 규칙>

<금지사항>
- "좋은점:", "아쉬운점:" 같은 헤더 사용 금지
- 각 문장에서 같은 태그 내용 반복 금지
</금지사항>"""
        else:
            if summary_stats:
                # 아쉬운점 없음 + 통계 있음
                sentence_instruction = f"""위 데이터를 기반으로 자연스러운 문단 형식의 요약을 작성하세요.
부정 비율이 낮아 아쉬운점은 생략합니다.

<작성 규칙>
1. 첫 줄: [긍정 {positive_ratio:.0f}%]
2. 첫 문장: 태그 #1, #2 내용 (서비스/직원 관련)
3. 둘째 문장: 태그 #3, #4 내용 (차량/시설 관련)
4. 셋째 문장: 재이용 의사, 전반적 만족
</작성 규칙>

<예시>
[긍정 99%]
직원분들이 친절하고 도움이 되는 서비스로 많은 고객들이 만족하고 계셨어요. 차량 상태가 깔끔하고 반납 절차도 간편해서 이용이 편리합니다. 합리적인 가격과 좋은 위치로 재이용 의사가 높습니다.
</예시>

<금지사항>
- "좋은점:", "아쉬운점:" 같은 헤더 사용 금지
- 각 문장에서 같은 태그 내용 반복 금지
- 마크다운, 이모지, 불릿 리스트 사용 금지
</금지사항>"""
            else:
                # 아쉬운점 없음 + 통계 없음
                sentence_instruction = """위 태그별 감정 분석과 대표 리뷰를 기반으로 자연스러운 문단 형식의 요약을 작성하세요.

<작성 규칙>
1. 첫 문장: 태그 #1, #2 내용 (서비스/직원 관련)
2. 둘째 문장: 태그 #3, #4 내용 (차량/시설 관련)
3. 셋째 문장: 재이용 의사, 전반적 만족
</작성 규칙>

<금지사항>
- "좋은점:", "아쉬운점:" 같은 헤더 사용 금지
- 각 문장에서 같은 태그 내용 반복 금지
</금지사항>"""

        # 유저 프롬프트 생성
        user_prompt = f"""다음 데이터를 바탕으로 렌터카 지점 요약을 작성해주세요.

<data>
- 지점명: {branch_name or "미지정"}
- 분석 리뷰 수: {review_count}개
- 핵심 키워드: {', '.join(keywords[:5])}{region_text}{stats_text}
</data>

<tag_sentiment_analysis>
{tag_analysis_text}
</tag_sentiment_analysis>

<representative_reviews>
{reviews_text if reviews_text else "(리뷰 없음)"}
</representative_reviews>

{sentence_instruction}"""

        return system_prompt, user_prompt

    @classmethod
    def _format_tag_sentiment(cls, tag_sentiment_data: dict) -> str:
        """
        태그별 감정 데이터를 프롬프트용 텍스트로 포맷팅 (순위 표시)

        Args:
            tag_sentiment_data: 태그별 감정 데이터

        Returns:
            포맷팅된 텍스트
        """
        if not tag_sentiment_data:
            return "(분석 데이터 없음)"

        lines = []

        # 긍정 키워드가 많은 순으로 정렬
        sorted_tags = sorted(
            tag_sentiment_data.items(),
            key=lambda x: len(x[1].get('positive', [])),
            reverse=True
        )

        for rank, (tag_name, sentiments) in enumerate(sorted_tags, 1):
            positive = sentiments.get('positive', [])
            negative = sentiments.get('negative', [])

            if not positive and not negative:
                continue

            # 순위 표시
            line_parts = [f"#{rank} [{tag_name}]"]

            if positive:
                line_parts.append(f"긍정({len(positive)}): {', '.join(positive[:5])}")
            if negative:
                line_parts.append(f"부정({len(negative)}): {', '.join(negative[:3])}")

            lines.append(" / ".join(line_parts))

        return "\n".join(lines) if lines else "(분석 데이터 없음)"

    # ============================================================
    # 레거시 호환 (v1)
    # ============================================================
    SUMMARY_SYSTEM = SUMMARY_SYSTEM_BASE + EXAMPLES_DEFAULT
