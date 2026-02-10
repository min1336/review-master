"""
규칙 기반 ABSA (Aspect-Based Sentiment Analysis)

비용 없이 로컬에서 실행되는 ABSA 구현:
1. 문장 분리 (절 단위) - ClauseChunker 사용
2. Aspect 추출 (키워드 매칭)
3. Opinion 연결 (동일 문장/절 내)
4. 감정 판단 (패턴 매칭) - patterns.py 사용

사용법:
    from analysis import RuleBasedABSA

    absa = RuleBasedABSA()
    results = absa.analyze("직원이 친절했지만 차량이 더러웠어요")
    # [
    #   {'aspect': '직원이 친절함', 'sentiment': 'positive', ...},
    #   {'aspect': '차량이 청결함', 'sentiment': 'negative', ...}
    # ]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .chunker import ClauseChunker
from .patterns import (
    DOUBLE_NEGATION_REGEX,
    GENERAL_POSITIVE_KEYWORDS,
    NEGATIVE_REGEX,
    POSITIVE_EXCEPTION_REGEX,
    POSITIVE_REGEX,
)

logger = logging.getLogger(__name__)


@dataclass
class AspectOpinion:
    """Aspect-Opinion-Sentiment 결과"""

    aspect: str  # 태그명 (직원이 친절함, 차량이 청결함 등)
    opinion: str  # 원문에서 추출한 의견 표현
    sentiment: str  # positive, negative, neutral
    confidence: float  # 신뢰도 (0.0 ~ 1.0)
    keywords: list[str]  # 매칭된 키워드들


class RuleBasedABSA:
    """
    규칙 기반 Aspect-Based Sentiment Analysis

    처리 흐름:
    1. 리뷰를 절(clause) 단위로 분리
    2. 각 절에서 Aspect 키워드 탐지
    3. 동일 절 내에서 Opinion/Sentiment 판단
    4. 결과 병합 및 반환
    """

    # =========================================================================
    # Aspect 키워드 사전 (태그별)
    # =========================================================================

    # 문맥 필요 키워드: 키워드 → (태그, 필요 문맥 키워드들)
    # v4.0: 7개 문장형 태그로 재정의
    CONTEXT_REQUIRED_KEYWORDS = {
        "늦": (
            "배달 서비스가 우수함",
            ["배차", "차량", "픽업", "도착", "출발", "시간", "대기", "기다"],
        ),
        "빨리": ("배달 서비스가 우수함", ["배차", "차량", "픽업", "처리", "배달", "대기"]),
        "빠르": ("배달 서비스가 우수함", ["배차", "차량", "픽업", "처리", "배달", "대기"]),
    }

    # v4.0: 7개 문장형 태그
    ASPECT_KEYWORDS = {
        "직원이 친절함": [
            "직원",
            "사장",
            "사장님",
            "알바",
            "스태프",
            "응대",
            "안내",
            "설명",
            "인사",
            "배웅",
            "친절",
            "불친절",
            "태도",
            "상담",
            "도움",
            "배려",
            "미소",
            "표정",
            "무례",
            "무뚝뚝",
            "서비스",
            "고객",
        ],
        "사고 처리를 잘해줌": [
            "보험",
            "보장",
            "면책",
            "자기부담",
            "자차",
            "대인",
            "대물",
            "완전자차",
            "슈퍼",
            "풀커버",
            "안심",
            "사고",
            "접수",
            "처리",
            "보상",
            "배상",
            "손해",
            "긁",
            "부딪",
            "충돌",
            "파손",
            "수리",
            "수리비",
            "사고접수",
            "사고처리",
        ],
        "주유비 부담 없음": [
            "주유",
            "연료",
            "기름",
            "휘발유",
            "경유",
            "가솔린",
            "디젤",
            "충전",
            "전기차",
            "충전소",
            "주유소",
            "연비",
            "기름값",
            "만땅",
            "반납시주유",
            "주유량",
            "연료비",
        ],
        "가격이 저렴함": [
            "가격",
            "가성비",
            "비용",
            "요금",
            "돈",
            "금액",
            "원",
            "저렴",
            "싼",
            "싸",
            "비싸",
            "비싼",
            "적정",
            "합리",
            "할인",
            "쿠폰",
            "이벤트",
            "혜택",
            "프로모션",
            "호구",
            "호갱",
            "바가지",
            "폭리",
            "추가비용",
            "추가금",
            "부담금",
            "렌트비",
            "수수료",
            "정산",
            "결제",
        ],
        "차량이 청결함": [
            "내부",
            "실내",
            "시트",
            "좌석",
            "바닥",
            "매트",
            "트렁크",
            "청결",
            "청소",
            "깨끗",
            "지저분",
            "더러",
            "더럽",
            "드러",
            "냄새",
            "담배",
            "악취",
            "퀴퀴",
            "쩔어",
            "냄새나",
            "공기",
            "먼지",
            "얼룩",
            "이물질",
            "쓰레기",
            "머리카락",
            "에어컨냄새",
            "위생",
            "세차",
        ],
        "차량외관이 좋음": [
            "외관",
            "외부",
            "외형",
            "겉",
            "바디",
            "스크래치",
            "흠집",
            "긁힘",
            "찍힘",
            "찌그러짐",
            "깨진",
            "범퍼",
            "휠",
            "바퀴",
            "타이어",
            "유리",
            "창문",
            "미러",
            "사이드미러",
            "도색",
            "페인트",
            "광택",
            "브레이크",
            "제동",
            "핸들",
            "엔진",
            "시동",
            "오래된",
            "낡은",
            "연식",
            "노후",
            "빵꾸",
            "펑크",
            "에어컨",
            "히터",
            "네비게이션",
            "블랙박스",
            "후방카메라",
            "신차",
            "구형",
            "주행거리",
            "성능",
        ],
        "배달 서비스가 우수함": [
            "배차",
            "차종",
            "차량변경",
            "대차",
            "차종변경",
            "배정",
            "배달",
            "딜리버리",
            "탁송",
            "대기",
            "기다",
            "지연",
            "약속",
            "예약시간",
            "도착시간",
            "재촉",
            "독촉",
            "급하",
            "서두르",
            "노쇼",
            "반납",
            "픽업",
            "인수",
            "수령",
            "전달",
            "인계",
            "반환",
            "출차",
            "입차",
            "절차",
            "간편",
            "간단",
            "복잡",
            "위치",
            "공항",
            "역",
            "터미널",
            "접근성",
        ],
    }

    # 긍정 키워드 + 없다 → 부정
    POSITIVE_NEGATION_PATTERNS = [
        (r"친절.{0,5}없", "negative"),
        (r"설명.{0,5}없", "negative"),
        (r"안내.{0,5}없", "negative"),
        (r"배려.{0,5}없", "negative"),
    ]

    def __init__(self, chunker: ClauseChunker | None = None):
        """
        초기화

        Args:
            chunker: 절 분리기 (기본값: 새로 생성)
        """
        self._chunker = chunker or ClauseChunker()

        # Aspect 키워드 → 태그 역매핑
        self._keyword_to_aspect = {}
        for aspect, keywords in self.ASPECT_KEYWORDS.items():
            for kw in keywords:
                self._keyword_to_aspect[kw] = aspect

    def analyze(self, review: str) -> list[dict]:
        """
        단일 리뷰 ABSA 분석

        Args:
            review: 리뷰 텍스트

        Returns:
            [{'aspect': '직원이 친절함', 'opinion': '직원이 친절했어요',
              'sentiment': 'positive', 'confidence': 0.9, 'keywords': ['직원', '친절']}]
        """
        if not review or len(review.strip()) < 3:
            return []

        # 1. 절 단위로 분리 (ClauseChunker 사용)
        clauses = self._chunker.chunk(review)

        # 2. 각 절에서 Aspect-Opinion-Sentiment 추출
        results = []
        for clause in clauses:
            clause_results = self._analyze_clause(clause)
            results.extend(clause_results)

        # 3. 중복 제거 및 병합
        merged = self._merge_results(results)

        return [self._to_dict(r) for r in merged]

    def analyze_batch(self, reviews: list[str]) -> list[list[dict]]:
        """배치 분석"""
        return [self.analyze(review) for review in reviews]

    def _analyze_clause(self, clause: str) -> list[AspectOpinion]:
        """단일 절 분석"""
        results = []

        # 1. Aspect 키워드 찾기
        found_aspects = self._find_aspects(clause)

        if not found_aspects:
            return []

        # 2. 감정 판단
        sentiment, confidence = self._determine_sentiment(clause)

        # 3. 각 Aspect에 대해 결과 생성
        for aspect, keywords in found_aspects.items():
            results.append(
                AspectOpinion(
                    aspect=aspect,
                    opinion=clause,
                    sentiment=sentiment,
                    confidence=confidence,
                    keywords=keywords,
                )
            )

        return results

    def _find_aspects(self, text: str) -> dict[str, list[str]]:
        """텍스트에서 Aspect 키워드 찾기"""
        found = {}  # {aspect: [keywords]}
        text_lower = text.lower()

        # 1. 일반 ASPECT_KEYWORDS 매칭
        for keyword, aspect in self._keyword_to_aspect.items():
            if keyword in text_lower:
                # 일반 긍정어는 단독 사용 시 제외
                if keyword in GENERAL_POSITIVE_KEYWORDS:
                    continue

                if aspect not in found:
                    found[aspect] = []
                found[aspect].append(keyword)

        # 2. 문맥 필요 키워드 처리
        for keyword, (
            aspect,
            context_keywords,
        ) in self.CONTEXT_REQUIRED_KEYWORDS.items():
            if keyword in text_lower:
                has_context = any(ctx in text_lower for ctx in context_keywords)
                if has_context:
                    if aspect not in found:
                        found[aspect] = []
                    if keyword not in found[aspect]:
                        found[aspect].append(keyword)

        return found

    def _determine_sentiment(self, text: str) -> tuple[str, float]:
        """감정 판단 (patterns.py 사용)"""

        # 1. 긍정 예외 체크 (오탐 방지)
        if POSITIVE_EXCEPTION_REGEX.search(text):
            return "positive", 0.8

        # 2. 이중부정 체크 (최우선)
        if DOUBLE_NEGATION_REGEX.search(text):
            return "positive", 0.95

        # 3. 긍정+부정 체크 (친절+없다 = 부정)
        for pattern, sentiment in self.POSITIVE_NEGATION_PATTERNS:
            if re.search(pattern, text):
                return sentiment, 0.9

        # 4. 일반 패턴 매칭
        positive_matches = len(POSITIVE_REGEX.findall(text))
        negative_matches = len(NEGATIVE_REGEX.findall(text))

        # "없" 특수 처리 - 앞 단어에 따라 판단
        if "없" in text:
            neg_keywords = ["불편", "불만", "문제", "걱정", "아쉬", "냄새", "흠"]
            for nk in neg_keywords:
                if nk in text and "없" in text[text.find(nk) : text.find(nk) + 10]:
                    positive_matches += 1
                    negative_matches = max(0, negative_matches - 1)

        # 5. 결과 판단
        if positive_matches > negative_matches:
            confidence = min(0.95, 0.6 + 0.1 * (positive_matches - negative_matches))
            return "positive", confidence
        elif negative_matches > positive_matches:
            confidence = min(0.95, 0.6 + 0.1 * (negative_matches - positive_matches))
            return "negative", confidence
        elif positive_matches > 0:
            return "positive", 0.5
        elif negative_matches > 0:
            return "negative", 0.5
        else:
            return self._infer_sentiment_from_context(text)

    def _infer_sentiment_from_context(self, text: str) -> tuple[str, float]:
        """패턴 매칭 실패 시 맥락 기반 감정 추론"""
        weak_positive = [
            "요",
            "네요",
            "습니다",
            "에요",
            "세요",
            "^^",
            "~",
            "!",
            "ㅎㅎ",
            "ㅋㅋ",
            "잘",
            "편",
            "쉽",
            "빠",
            "넓",
            "깔끔",
            "감사",
            "고마",
            "덕분",
            "좋",
        ]

        weak_negative = [
            "..",
            ";;;",
            "ㅜ",
            "ㅠ",
            ";;",
            "좀",
            "근데",
            "다만",
            "그런데",
            "힘들",
            "어렵",
            "불",
            "안",
        ]

        pos_score = sum(1 for p in weak_positive if p in text)
        neg_score = sum(1 for p in weak_negative if p in text)

        if len(text) > 50:
            pos_score += 1

        if pos_score > neg_score:
            return "positive", 0.4
        elif neg_score > pos_score:
            return "negative", 0.4
        else:
            return "positive", 0.3

    def _merge_results(self, results: list[AspectOpinion]) -> list[AspectOpinion]:
        """중복 Aspect 병합"""
        merged = {}

        for r in results:
            if r.aspect not in merged:
                merged[r.aspect] = r
            else:
                existing = merged[r.aspect]
                if r.confidence > existing.confidence:
                    merged[r.aspect] = AspectOpinion(
                        aspect=r.aspect,
                        opinion=f"{existing.opinion} / {r.opinion}",
                        sentiment=r.sentiment,
                        confidence=r.confidence,
                        keywords=list(set(existing.keywords + r.keywords)),
                    )
                else:
                    merged[r.aspect] = AspectOpinion(
                        aspect=existing.aspect,
                        opinion=f"{existing.opinion} / {r.opinion}",
                        sentiment=existing.sentiment,
                        confidence=existing.confidence,
                        keywords=list(set(existing.keywords + r.keywords)),
                    )

        return list(merged.values())

    def _to_dict(self, ao: AspectOpinion) -> dict:
        """AspectOpinion → dict 변환"""
        return {
            "aspect": ao.aspect,
            "opinion": ao.opinion,
            "sentiment": ao.sentiment,
            "confidence": ao.confidence,
            "keywords": ao.keywords,
        }

    # =========================================================================
    # HybridClassifier 호환 메서드
    # =========================================================================

    def classify_review(
        self, review: str, keywords: list[str] = None
    ) -> dict[str, dict[str, list[str]]]:
        """
        HybridClassifier 호환 API

        Args:
            review: 원본 리뷰 텍스트
            keywords: 추출된 키워드 리스트 (무시됨, 호환성용)

        Returns:
            {
                '직원이 친절함': {'positive': ['친절'], 'negative': [], 'neutral': []},
                '차량이 청결함': {'positive': [], 'negative': ['더러운'], 'neutral': []}
            }
        """
        from collections import defaultdict

        result = defaultdict(lambda: {"positive": [], "negative": [], "neutral": []})

        # ABSA 분석 수행
        absa_results = self.analyze(review)

        # 결과 변환
        for item in absa_results:
            aspect = item["aspect"]
            sentiment = item["sentiment"]
            keywords_found = item.get("keywords", [])

            for kw in keywords_found:
                if kw not in result[aspect][sentiment]:
                    result[aspect][sentiment].append(kw)

        # 빈 태그 제거
        return {
            tag: sentiments
            for tag, sentiments in result.items()
            if any(sentiments.values())
        }

    # =========================================================================
    # 유틸리티 메서드
    # =========================================================================

    def get_aspect_summary(self, results: list[dict]) -> dict[str, dict]:
        """분석 결과를 Aspect별로 요약"""
        summary = {}

        for r in results:
            aspect = r["aspect"]
            sentiment = r["sentiment"]

            if aspect not in summary:
                summary[aspect] = {
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0,
                    "opinions": [],
                }

            summary[aspect][sentiment] += 1
            summary[aspect]["opinions"].append(r["opinion"])

        return summary

    def format_results(self, results: list[dict]) -> str:
        """결과를 보기 좋게 포맷팅"""
        if not results:
            return "분석 결과 없음"

        lines = []
        for r in results:
            sentiment_symbol = {"positive": "+", "negative": "-", "neutral": "0"}.get(
                r["sentiment"], "?"
            )

            lines.append(
                f"  [{r['aspect']}]({sentiment_symbol}) {r['opinion'][:50]}..."
                if len(r["opinion"]) > 50
                else f"  [{r['aspect']}]({sentiment_symbol}) {r['opinion']}"
            )

        return "\n".join(lines)
