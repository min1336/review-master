"""
프롬프트 빌더 - 긍정 요약 전용

렌터카 지점 리뷰 요약을 위한 프롬프트 생성기
"""

from __future__ import annotations

from core.config import REGION_CONFIG, BranchType
from core.constants import IMPROVEMENT_NEGATIVE_RATIO, STRENGTH_POSITIVE_RATIO


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
- 핵심 태그를 자연스럽게 녹여서 표현
</writing_style>

<constraints>
- 마크다운, 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천", "무조건"
- 부정적 내용 작성 금지
- 제공된 태그 중 최소 4개 자연스럽게 포함
- "~합니다", "~입니다" 문체로 통일
- 지점명이나 지역 특성을 반영한 차별화 포인트 포함
</constraints>"""

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

    # ============================================================
    # Enhanced Few-shot 예시 (카테고리 + 세분화 태그 형식)
    # ============================================================
    ENHANCED_EXAMPLES_AIRPORT = """
<examples>
[공항 지점 예시]
태그 분석:
[직원이 친절함]
- 친절 (긍정 88%, 150건)
- 안내 (긍정 75%, 60건)
- 예약 (긍정 70%, 35건)

[배달 서비스가 우수함]
- 딜리버리 (긍정 82%, 90건)
- 픽업 (긍정 78%, 55건)

[차량이 청결함]
- 청결 (긍정 80%, 70건)

출력:
친절한 직원들의 빠른 응대와 상세한 안내로 공항 도착 후 바로 차량을 인수받을 수 있습니다. 딜리버리 서비스가 정시에 운행되어 터미널 이동도 수월하며, 픽업 과정이 간편합니다. 청결하게 관리된 차량 상태가 인상적이고, 합리적인 가격에 예약부터 반납까지 모든 절차가 편리하게 진행되는 지점입니다.
</examples>"""

    ENHANCED_EXAMPLES_CITY = """
<examples>
[시내 지점 예시 1]
태그 분석:
[직원이 친절함]
- 친절 (긍정 85%, 120건)
- 응대속도 (긍정 78%, 50건)

[가격이 저렴함]
- 가격 (긍정 80%, 90건)

[차량이 청결함]
- 청결 (긍정 75%, 65건)

출력:
친절한 직원분들의 신속한 응대로 대기 시간 없이 바로 출발할 수 있습니다. 차량은 항상 청결하게 관리되어 있고, 합리적인 가격으로 가성비가 뛰어납니다. 차량 상태도 양호하여 안심하고 이용할 수 있으며, 반납 절차도 간편해서 비즈니스 출장이나 일상적인 이용에 적합한 지점입니다.

[시내 지점 예시 2 - 리뷰 수 적음]
태그 분석:
[직원이 친절함]
- 친절 (긍정 82%, 25건)

[차량이 청결함]
- 청결 (긍정 76%, 18건)

[가격이 저렴함]
- 가격 (긍정 79%, 20건)

출력:
친절한 직원분들의 세심한 응대가 돋보이는 지점입니다. 차량 상태가 깔끔하게 관리되어 있으며, 합리적인 가격으로 이용하실 수 있습니다. 시내 중심에 위치하여 접근성이 좋고, 간편한 절차로 편리하게 이용 가능한 곳입니다.
</examples>"""

    ENHANCED_EXAMPLES_TOURIST = """
<examples>
[관광지 지점 예시]
태그 분석:
[직원이 친절함]
- 친절 (긍정 86%, 130건)
- 안내 (긍정 80%, 70건)

[배달 서비스가 우수함]
- 딜리버리 (긍정 84%, 85건)

[차량이 청결함]
- 청결 (긍정 78%, 60건)

출력:
친절한 직원분들이 상세한 안내와 함께 여행 정보까지 제공해주셔서 든든합니다. 청결하게 관리된 차량으로 쾌적한 드라이브를 즐길 수 있으며, 딜리버리 서비스도 원활하게 운영됩니다. 합리적인 가격에 차량 상태까지 양호해, 여행을 더욱 즐겁게 만들어주는 지점입니다.
</examples>"""

    ENHANCED_EXAMPLES_DEFAULT = """
<examples>
[기본 예시]
태그 분석:
[직원이 친절함]
- 친절 (긍정 85%, 120건)
- 안내 (긍정 72%, 45건)

[차량이 청결함]
- 청결 (긍정 80%, 70건)

[가격이 저렴함]
- 가격 (긍정 75%, 55건)

출력:
친절한 직원분들의 상세한 안내 덕분에 기분 좋게 이용을 시작할 수 있습니다. 차량은 청결하게 관리되어 있어 쾌적하며, 합리적인 가격으로 가성비도 뛰어납니다. 체계적인 서비스 운영 덕분에 처음 이용하시는 분들도 편하게 이용하실 수 있는 지점입니다.
</examples>"""

    @classmethod
    def create_enhanced_summary_prompt(
        cls,
        tag_sentiments: list[dict],
        review_count: int,
        representative_reviews: dict[str, list[str]] | None = None,
        branch_name: str | None = None,
        period_label: str | None = None,
        sentiment_stats: dict | None = None,
    ) -> tuple[str, str]:
        """
        카테고리 그룹핑된 태그+감정 데이터를 포함한 향상된 요약 프롬프트 생성

        Args:
            tag_sentiments: 카테고리별 그룹핑된 태그 감정 데이터
                [{"category": "직원이 친절함", "tags": [{"name": "친절", "positive_ratio": 85, "total": 120}, ...]}]
            review_count: 리뷰 수
            representative_reviews: 감정별 리뷰 {"positive": [...], "negative": [...]}
            branch_name: 지점명
            period_label: 기간 라벨 (예: "최근 3개월")
            sentiment_stats: 전체 감정 통계 {"positive": N, "negative": N, "total": N}

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        branch_type = cls.detect_branch_type(branch_name)
        region = cls.extract_region(branch_name)
        region_emphasis = (
            REGION_CONFIG["region_emphasis"].get(region, []) if region else []
        )

        # 시스템 프롬프트 = 기본 + 유형별 enhanced 예시
        enhanced_examples_map = {
            BranchType.AIRPORT: cls.ENHANCED_EXAMPLES_AIRPORT,
            BranchType.CITY: cls.ENHANCED_EXAMPLES_CITY,
            BranchType.TOURIST: cls.ENHANCED_EXAMPLES_TOURIST,
            BranchType.DEFAULT: cls.ENHANCED_EXAMPLES_DEFAULT,
        }
        examples = enhanced_examples_map.get(branch_type, cls.ENHANCED_EXAMPLES_DEFAULT)

        system_prompt = cls.SUMMARY_SYSTEM + examples

        # 카테고리별 태그 분석 텍스트
        tag_analysis_text = cls._format_tag_sentiments(tag_sentiments)

        # 리뷰 텍스트 포맷팅
        reviews_text = cls._format_representative_reviews(representative_reviews)

        # 전체 감정 비율
        sentiment_text = cls._format_sentiment_text(sentiment_stats)

        # 지역 텍스트
        region_text = ""
        if region:
            region_text = f"\n- 지역: {region}"
            if region_emphasis:
                region_text += f" (강조 포인트: {', '.join(region_emphasis)})"

        # 유저 프롬프트
        user_prompt = f"""다음 데이터를 바탕으로 렌터카 지점 소개 문구를 작성해주세요.

<data>
- 지점명: {branch_name or "미지정"}
- 분석 기간: {period_label or "전체"}
- 분석 리뷰 수: {review_count}개{sentiment_text}{region_text}
</data>

<tag_analysis>
{tag_analysis_text if tag_analysis_text else "(태그 데이터 없음)"}
</tag_analysis>

<representative_reviews>
{reviews_text if reviews_text else "(리뷰 없음)"}
</representative_reviews>

위 태그 분석과 리뷰를 기반으로 자연스럽게 이어지는 하나의 문단(200~250자)을 작성하세요.
카테고리별 핵심 강점을 자연스럽게 녹여서 표현하세요."""

        return system_prompt, user_prompt

    @classmethod
    def _format_tag_sentiments(cls, tag_sentiments: list[dict]) -> str:
        """카테고리별 그룹핑된 태그 감정 데이터를 텍스트로 포맷팅"""
        if not tag_sentiments:
            return ""

        lines = []
        for group in tag_sentiments:
            category = group.get("category", "기타")
            tags = group.get("tags", [])
            if not tags:
                continue

            lines.append(f"[{category}]")
            for tag in tags:
                name = tag.get("name", "")
                pos_ratio = tag.get("positive_ratio", 0)
                neg_ratio = tag.get("negative_ratio", 0)
                total = tag.get("total", 0)

                if neg_ratio > pos_ratio:
                    lines.append(f"- {name} (부정 {neg_ratio}%, {total}건)")
                else:
                    lines.append(f"- {name} (긍정 {pos_ratio}%, {total}건)")

            lines.append("")  # 그룹 간 빈 줄

        return "\n".join(lines).strip()

    @classmethod
    def _format_representative_reviews(
        cls, reviews: dict[str, list[str]] | None
    ) -> str:
        """감정별 분리된 리뷰 텍스트 포맷팅"""
        if not reviews:
            return ""

        lines = []
        positive = reviews.get("positive", [])
        negative = reviews.get("negative", [])

        if positive:
            lines.append("긍정 리뷰:")
            for idx, review in enumerate(positive, 1):
                lines.append(f'{idx}. "{review[:200]}"')

        if negative:
            if lines:
                lines.append("")
            lines.append("부정 리뷰:")
            for idx, review in enumerate(negative, 1):
                lines.append(f'{idx}. "{review[:200]}"')

        return "\n".join(lines)

    @classmethod
    def _format_sentiment_text(cls, sentiment_stats: dict | None) -> str:
        """전체 감정 비율 텍스트 생성 (두 빌더 공통)"""
        if not sentiment_stats:
            return ""
        total = sentiment_stats.get("total", 0)
        if total <= 0:
            return ""
        pos_pct = round(sentiment_stats.get("positive", 0) / total * 100)
        neg_pct = round(sentiment_stats.get("negative", 0) / total * 100)
        return f"\n- 전체 긍정률: {pos_pct}%, 부정률: {neg_pct}%"

    @classmethod
    def get_default_summary(cls, keywords: list[str]) -> str:
        """기본 요약 (LLM 실패시)"""
        if keywords:
            return f"{', '.join(keywords[:3])} 관련 긍정적인 리뷰가 많습니다."
        return "전반적으로 긍정적인 리뷰가 많습니다."

    @classmethod
    def get_insufficient_reviews_message(
        cls, branch_name: str, review_count: int
    ) -> str:
        """리뷰 부족 시 기본 메시지"""
        return (
            f"{branch_name}의 분석 가능한 리뷰가 {review_count}건으로 충분하지 않습니다. "
            "더 많은 리뷰가 축적되면 상세한 분석이 가능합니다."
        )


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

            if pos_ratio >= STRENGTH_POSITIVE_RATIO:
                positive_tags.append(f"{name}(긍정 {pos_ratio}%)")
            if neg_ratio >= IMPROVEMENT_NEGATIVE_RATIO:
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

    # ============================================================
    # 리포트 전용 프롬프트 (구조화된 분석 리포트)
    # ============================================================
    REPORT_SYSTEM_PROMPT = """<role>
당신은 카모아 렌터카의 지점 운영 컨설턴트입니다.
고객 리뷰 데이터를 분석하여 지점 운영에 실질적으로 도움이 되는 분석 리포트를 작성합니다.
</role>

<task>
주어진 태그별 감정 데이터, 차량 분석, 실제 리뷰를 종합하여 하나의 자연스러운 리포트 문단을 작성하세요.
</task>

<output_format>
하나의 흐름으로 이어지는 설명식 문단(400~600자)으로 작성합니다.
분석 기간과 리뷰 수 개요로 시작하여, 긍정/부정 건수와 주요 강점을 서술하고,
개선이 필요한 부분을 언급한 뒤, 운영 관점의 제안으로 자연스럽게 마무리합니다.
섹션 구분이나 제목 없이 문장이 매끄럽게 이어지도록 작성하세요.
</output_format>

<writing_style>
- 객관적이고 분석적인 톤
- 숫자 데이터를 근거로 활용
- 통계 건수를 근거로 서술
- 운영자 관점에서 실용적인 인사이트 제공
- 접속사를 활용해 문장 간 자연스럽게 연결
</writing_style>

<data_usage_rules>
- 부정률이 20% 이상인 태그는 반드시 리포트에서 언급하세요
- 수치 데이터를 최소 3회 이상 인용하세요 (예: "긍정 102건/120건", "부정 18건")
- 운영 제안은 구체적 액션으로 작성하세요:
  나쁜 예: "서비스 개선이 필요합니다"
  좋은 예: "전화응대 부정률이 35%로 높으므로, 전화 응대 매뉴얼 재교육을 권장합니다"
</data_usage_rules>

<constraints>
- 마크다운 서식 전면 금지: **, *, -, #, [], () 등 일체 사용 금지
- 번호 매기기(1. 2. 3.) 금지, 글머리 기호(-, *) 금지
- 대괄호 섹션 제목([핵심 요약] 등) 금지
- 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천", "무조건"
- 제공되지 않은 정보 추측 금지
- 전체 400~600자 분량
- 반드시 순수 텍스트 문단으로만 작성
</constraints>"""

    @classmethod
    def create_report_prompt(
        cls,
        branch_name: str,
        start_date: str,
        end_date: str,
        total_reviews: int,
        tag_sentiments: list[dict],
        sentiment_stats: dict,
        sample_reviews: list[str],
        vehicle_summary: str | None = None,
    ) -> tuple[str, str]:
        """
        리포트 전용 프롬프트 생성 (구조화된 3섹션 리포트)

        Args:
            branch_name: 지점명
            start_date: 시작일
            end_date: 종료일
            total_reviews: 총 리뷰 수
            tag_sentiments: 태그별 감정 데이터
            sentiment_stats: 전체 감정 통계
            sample_reviews: 대표 리뷰 텍스트 리스트
            vehicle_summary: 차량 분석 요약 텍스트

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

            if pos_ratio >= STRENGTH_POSITIVE_RATIO:
                positive_tags.append(f"{name}(긍정 {pos}건/{total}건)")
            if neg_ratio >= IMPROVEMENT_NEGATIVE_RATIO:
                negative_tags.append(f"{name}(부정 {neg}건/{total}건)")

        # 전체 감정 건수
        total_sentiment = sentiment_stats.get("total", 0)
        pos_count = sentiment_stats.get("positive", 0)
        neg_count = sentiment_stats.get("negative", 0)

        # 부정률 20%+ 태그 개수
        high_neg_count = len(negative_tags)

        # 대표 리뷰 포맷팅 (최대 8개)
        reviews_text = ""
        if sample_reviews:
            for idx, review in enumerate(sample_reviews[:8], 1):
                review_truncated = str(review)[:250]
                reviews_text += f'{idx}. "{review_truncated}"\n'

        # 차량 분석 텍스트
        vehicle_text = vehicle_summary if vehicle_summary else "(차량 분석 데이터 없음)"

        user_prompt = f"""다음 데이터를 바탕으로 렌터카 지점 운영 리포트를 작성해주세요.

<data>
- 지점명: {branch_name}
- 분석 기간: {start_date} ~ {end_date}
- 총 리뷰 수: {total_reviews}건
- 전체 긍정: {pos_count}건, 부정: {neg_count}건 (총 {total_sentiment}건)
</data>

<tag_analysis>
[강점 태그]
{', '.join(positive_tags) if positive_tags else '없음'}

[주의 태그 - 반드시 리포트에 반영]
{', '.join(negative_tags) if negative_tags else '없음'}

전체 태그 중 부정률 20% 이상: {high_neg_count}개
</tag_analysis>

<vehicle_analysis>
{vehicle_text}
</vehicle_analysis>

<sample_reviews>
{reviews_text if reviews_text else "(대표 리뷰 없음)"}
</sample_reviews>

위 데이터를 기반으로 하나의 자연스러운 문단으로 분석 리포트를 작성하세요.
개요, 강점, 개선점, 운영 제안이 끊김 없이 이어지도록 서술하세요."""

        return cls.REPORT_SYSTEM_PROMPT, user_prompt

    @classmethod
    def get_insufficient_reviews_message(
        cls, branch_name: str, review_count: int
    ) -> str:
        """리뷰 부족 시 기본 메시지"""
        return (
            f"{branch_name}의 분석 가능한 리뷰가 {review_count}건으로 충분하지 않습니다. "
            "더 많은 리뷰가 축적되면 상세한 분석이 가능합니다."
        )


    # ============================================================
    # 업체 평가 프롬프트 (독립 LLM 호출)
    # ============================================================
    AFFILIATE_EVAL_SYSTEM_PROMPT = """<role>
당신은 카모아 렌터카의 지점 운영 컨설턴트입니다.
고객 리뷰 데이터를 분석하여 업체 서비스 평가를 작성합니다.
</role>

<task>
주어진 태그별 감정 통계와 태그 순위 데이터를 분석하여 업체 서비스 평가 텍스트를 작성하세요.
잘한점을 7, 개선점을 3 비율로 서술합니다.
잘한점 칭찬으로 시작하고, 개선점에 대한 구체적 액션 제안, 보완 시 기대효과로 마무리합니다.
</task>

<writing_style>
- 객관적이고 분석적인 톤
- 건수 데이터를 근거로 활용
- 잘한점을 먼저 언급한 후 개선점 서술
- 보완 시 예상되는 긍정적 효과로 마무리
</writing_style>

<constraints>
- 마크다운 서식 전면 금지: **, *, -, #, [], () 등 사용 금지
- 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천"
- 제공되지 않은 정보 추측 금지
- 리뷰 원문을 직접 인용하지 마세요
- 150-250자 분량
- 반드시 순수 텍스트 문단으로만 작성
</constraints>"""

    # ============================================================
    # 차량 평가 프롬프트 (독립 LLM 호출)
    # ============================================================
    VEHICLE_EVAL_SYSTEM_PROMPT = """<role>
당신은 카모아 렌터카의 지점 운영 컨설턴트입니다.
고객 리뷰 데이터를 분석하여 차량 상태 평가를 작성합니다.
</role>

<task>
주어진 태그별 감정 통계와 차량 순위 데이터를 분석하여 차량 평가 텍스트를 작성하세요.
강점을 7, 아쉬운점을 3 비율로 서술합니다.
강점을 먼저 나열하고, 아쉬운점에 대한 구체적 개선 방안, 보완 시 기대효과로 마무리합니다.
차량 모델명과 수치를 반드시 인용하세요.
</task>

<writing_style>
- 객관적이고 분석적인 톤
- 숫자 데이터를 근거로 활용
- 강점을 먼저 나열한 후 아쉬운점 서술
- 보완 시 예상되는 긍정적 효과로 마무리
</writing_style>

<constraints>
- 마크다운 서식 전면 금지: **, *, -, #, [], () 등 사용 금지
- 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천"
- 제공되지 않은 정보 추측 금지
- 150-250자 분량
- 반드시 순수 텍스트 문단으로만 작성
</constraints>"""

    @classmethod
    def create_affiliate_evaluation_prompt(
        cls,
        branch_name: str,
        tag_details: list[dict],
        top_positive_tags: list[dict],
        top_negative_tags: list[dict],
        sample_reviews: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        업체 평가 텍스트 프롬프트 생성 (독립 LLM 호출)

        Args:
            tag_details: 업체 카테고리 태그 통계
                [{"tag_name": str, "category_name": str, "positive": int, "negative": int, "total": int}]

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        from infrastructure.llm.prompt_helpers import format_tag_stats_lines

        tag_stats_text = format_tag_stats_lines(tag_details)

        pos_lines = "\n".join(
            f"  {i+1}. {t.get('tag_name', '')}({t.get('count', 0)}건)"
            for i, t in enumerate(top_positive_tags[:5])
        ) or "  데이터 없음"

        neg_lines = "\n".join(
            f"  {i+1}. {t.get('tag_name', '')}({t.get('count', 0)}건)"
            for i, t in enumerate(top_negative_tags[:5])
        ) or "  데이터 없음"

        user_prompt = f"""다음 데이터를 바탕으로 {branch_name}의 업체 서비스 평가 텍스트를 작성하세요.

<affiliate_analysis>
태그별 분석:
{tag_stats_text}
잘한점 Top 5:
{pos_lines}
개선점 Top 5:
{neg_lines}
</affiliate_analysis>

잘한점 칭찬으로 시작하고, 개선점 및 보완 시 예상효과를 포함하여 150-250자로 작성하세요."""

        return cls.AFFILIATE_EVAL_SYSTEM_PROMPT, user_prompt

    @classmethod
    def create_vehicle_evaluation_prompt(
        cls,
        branch_name: str,
        tag_details: list[dict],
        top_liked_vehicles: list[dict],
        top_disliked_vehicles: list[dict],
        sample_reviews: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        차량 평가 텍스트 프롬프트 생성 (독립 LLM 호출)

        Args:
            tag_details: 차량 카테고리 태그 통계
                [{"tag_name": str, "category_name": str, "positive": int, "negative": int, "total": int}]

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        from infrastructure.llm.prompt_helpers import format_tag_stats_lines

        tag_stats_text = format_tag_stats_lines(tag_details)

        liked_lines = "\n".join(
            f"  {i+1}. {v.get('model', '')}(호평 {v.get('ratio', 0)}건) {', '.join(v.get('tags', [])[:3])}"
            for i, v in enumerate(top_liked_vehicles[:5])
        ) or "  데이터 없음"

        disliked_lines = "\n".join(
            f"  {i+1}. {v.get('model', '')}(불만 {v.get('ratio', 0)}건) {', '.join(v.get('tags', [])[:3])}"
            for i, v in enumerate(top_disliked_vehicles[:5])
        ) or "  데이터 없음"

        reviews_text = ""
        if sample_reviews:
            for idx, review in enumerate(sample_reviews[:5], 1):
                reviews_text += f'{idx}. "{str(review)[:100]}"\n'

        user_prompt = f"""다음 데이터를 바탕으로 {branch_name}의 차량 평가 텍스트를 작성하세요.

<vehicle_analysis>
태그별 분석:
{tag_stats_text}
호평 차량 Top 5:
{liked_lines}
불만 차량 Top 5:
{disliked_lines}
</vehicle_analysis>

{f'<sample_reviews>{chr(10)}{reviews_text}</sample_reviews>' if reviews_text else ''}

강점 나열로 시작하고, 아쉬운점 및 보완 시 예상효과를 포함하여 150-250자로 작성하세요."""

        return cls.VEHICLE_EVAL_SYSTEM_PROMPT, user_prompt


class OperationalSummaryPromptBuilder:
    """운영 분석 요약 프롬프트 생성기

    마케팅 카피와 달리 객관적/분석적 톤으로 강점+개선영역+인사이트를 제공합니다.
    """

    SYSTEM_PROMPT = """<role>
당신은 카모아 렌터카 운영팀의 데이터 분석 전문가입니다.
고객 리뷰 데이터를 분석하여 지점 운영 개선에 도움이 되는 객관적인 분석 요약을 작성합니다.
</role>

<task>
주어진 카테고리별 태그 감정 데이터와 대표 리뷰를 바탕으로 운영 분석 요약을 작성하세요.
강점과 개선이 필요한 영역을 균형 있게 서술하고, 운영 인사이트를 제공합니다.
</task>

<output_format>
하나의 자연스러운 문단(250~350자)으로 작성:
1. 분석 기간과 전체 감정 비율 개요
2. 강점 영역 (긍정 비율 높은 카테고리/태그)
3. 개선 필요 영역 (부정 비율 높은 태그 + 구체적 피드백)
4. 운영 인사이트 (데이터 기반 제안)

문장들이 자연스럽게 흘러가도록 연결하세요.
</output_format>

<writing_style>
- 객관적이고 분석적인 톤
- 숫자 데이터를 근거로 활용 (긍정률, 건수)
- 부정 피드백은 구체적으로 서술 (어떤 문제인지)
- 운영자 관점에서 실용적인 인사이트 제공
- 접속사를 활용해 문장 간 자연스럽게 연결
</writing_style>

<constraints>
- 마크다운, 이모지, 특수문자 사용 금지
- 과장 표현 금지: "최고", "완벽", "강력추천", "무조건"
- 긍정 편향 금지: 부정 피드백도 반드시 포함
- 제공되지 않은 정보 추측 금지
</constraints>"""

    EXAMPLES = """
<examples>
[운영 분석 예시 1]
태그 분석:
[직원이 친절함]
- 친절 (긍정 88%, 150건)
- 안내 (긍정 72%, 60건)
- 전화응대 (부정 35%, 20건)

[차량이 청결함]
- 청결 (긍정 65%, 80건)
- 냄새 (부정 45%, 15건)

출력:
최근 3개월간 총 245건의 리뷰를 분석한 결과, 전체 긍정률 78%로 양호한 수준입니다. 직원 친절도가 88%의 높은 긍정률을 기록하며 핵심 강점으로 확인되었고, 안내 서비스에 대해서도 72%의 만족도를 보이고 있습니다. 다만 전화응대 관련 부정 피드백이 35%로 나타나 응대 품질 개선이 필요하며, 차량 냄새에 대한 불만도 45%로 높아 실내 청소 프로세스 점검이 권장됩니다. 전반적으로 대면 서비스 품질은 우수하나, 비대면 채널과 차량 관리 부문에 집중적인 개선이 이루어지면 고객 만족도를 한 단계 높일 수 있을 것으로 분석됩니다.

[운영 분석 예시 2]
태그 분석:
[가격이 저렴함]
- 가격 (긍정 82%, 95건)
- 보험 (부정 40%, 25건)

[배달 서비스가 우수함]
- 딜리버리 (긍정 90%, 110건)

출력:
최근 6개월간 230건의 리뷰를 분석한 결과 전체 긍정률이 81%입니다. 딜리버리 서비스가 90%의 높은 긍정률로 가장 강력한 차별화 요소이며, 가격 만족도도 82%로 우수합니다. 반면 보험 관련 불만이 40%로 나타나, 보험 옵션 안내 과정의 투명성 강화가 필요합니다. 딜리버리 서비스의 높은 만족도를 마케팅에 적극 활용하면서, 보험 안내 프로세스를 개선하면 전환율 향상에 기여할 수 있을 것입니다.
</examples>"""

    @classmethod
    def create_prompt(
        cls,
        tag_sentiments: list[dict],
        review_count: int,
        representative_reviews: dict[str, list[str]] | None = None,
        branch_name: str | None = None,
        period_label: str | None = None,
        sentiment_stats: dict | None = None,
    ) -> tuple[str, str]:
        """
        운영 분석 요약 프롬프트 생성

        Args:
            tag_sentiments: 카테고리별 그룹핑된 태그 감정 데이터
            review_count: 리뷰 수
            representative_reviews: 감정별 리뷰 {"positive": [...], "negative": [...]}
            branch_name: 지점명
            period_label: 기간 라벨
            sentiment_stats: 전체 감정 통계

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        system_prompt = cls.SYSTEM_PROMPT + cls.EXAMPLES

        # 카테고리별 태그 분석 (SummaryPromptBuilder의 포맷터 재사용)
        tag_analysis_text = SummaryPromptBuilder._format_tag_sentiments(tag_sentiments)

        # 리뷰 텍스트 포맷팅
        reviews_text = SummaryPromptBuilder._format_representative_reviews(
            representative_reviews
        )

        # 전체 감정 비율 (SummaryPromptBuilder의 공유 메서드 재사용)
        sentiment_text = SummaryPromptBuilder._format_sentiment_text(sentiment_stats)

        user_prompt = f"""다음 데이터를 바탕으로 렌터카 지점의 운영 분석 요약을 작성해주세요.

<data>
- 지점명: {branch_name or "미지정"}
- 분석 기간: {period_label or "전체"}
- 분석 리뷰 수: {review_count}개{sentiment_text}
</data>

<tag_analysis>
{tag_analysis_text if tag_analysis_text else "(태그 데이터 없음)"}
</tag_analysis>

<representative_reviews>
{reviews_text if reviews_text else "(리뷰 없음)"}
</representative_reviews>

위 데이터를 기반으로 강점, 개선 영역, 운영 인사이트를 포함한 분석 요약(250~350자)을 작성하세요.
부정 피드백이 있다면 구체적으로 언급하고, 데이터 기반의 운영 제안을 포함하세요."""

        return system_prompt, user_prompt
