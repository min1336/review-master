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
    #   {'aspect': '직원친절', 'sentiment': 'positive', ...},
    #   {'aspect': '청결', 'sentiment': 'negative', ...}
    # ]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .chunker import ClauseChunker
from .patterns import (
    ASPECT_KEYWORDS,
    CONCESSION_REGEX,
    GENERAL_POSITIVE_KEYWORDS,
    NEGATIVE_REGEX,
    POSITIVE_EXCEPTION_REGEX,
    POSITIVE_REGEX,
    STRONG_NEGATIVE_KEYWORDS,
)
from .sentiment_core import (
    _is_negation_prefixed_only,
    check_double_negation,
    count_sentiment_matches,
)

logger = logging.getLogger(__name__)


@dataclass
class AspectOpinion:
    """Aspect-Opinion-Sentiment 결과"""

    aspect: str  # 태그명 (직원친절, 청결 등)
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
    # Aspect 키워드: patterns.py TAG_REGISTRY에서 파생 (ASPECT_KEYWORDS)
    # =========================================================================

    # 문맥 필요 키워드: 키워드 → (태그, 필요 문맥 키워드들)
    # v4.0: 7개 문장형 태그로 재정의
    CONTEXT_REQUIRED_KEYWORDS = {
        "늦": (
            "배달",
            ["배차", "차량", "픽업", "도착", "출발", "시간", "대기", "기다"],
        ),
        "빨리": ("배달", ["배차", "차량", "픽업", "처리", "배달", "대기", "응대"]),
        "빠르": ("배달", ["배차", "차량", "픽업", "처리", "배달", "대기", "응대"]),
        "빨랐": ("배달", ["배차", "차량", "픽업", "처리", "배달", "대기"]),
        # 사고 처리 generic 키워드 — 사고/보험 문맥 필수
        "안심": ("사고 처리", ["보험", "사고", "면책", "자차", "커버", "보장", "보상"]),
        "처리": ("사고 처리", ["사고", "보험", "면책", "접수", "파손", "충돌", "수리"]),
        "접수": ("사고 처리", ["사고", "보험", "면책", "파손", "충돌"]),
        "책임": ("사고 처리", ["보험", "사고", "면책", "보장", "보상", "배상"]),
    }

    # 긍정 키워드 + 없다 → 부정 (사전 컴파일)
    POSITIVE_NEGATION_PATTERNS = [
        (re.compile(r"친절.{0,5}없"), "negative"),
        (re.compile(r"설명.{0,5}없"), "negative"),
        (re.compile(r"안내.{0,5}없"), "negative"),
        (re.compile(r"배려.{0,5}없"), "negative"),
    ]

    # 부정어 + "없" 이중부정 패턴 (사전 컴파일 — 루프 내 동적 re.search 제거)
    _NEG_ABSENCE_PATTERNS: list[tuple[str, re.Pattern]] = [
        (kw, re.compile(rf"{kw}.{{0,10}}없"))
        for kw in [
            "불편", "불만", "문제", "걱정", "아쉬", "냄새", "흠",
            "나쁜", "부담", "탈", "고장", "실망", "불안", "위험",
            "부족", "어려", "힘들",
        ]
    ]

    def __init__(self, chunker: ClauseChunker | None = None):
        """
        초기화

        Args:
            chunker: 절 분리기 (기본값: 새로 생성)
        """
        self._chunker = chunker or ClauseChunker(use_punctuation=True)

        # Aspect 키워드 → 태그 역매핑 (patterns.py TAG_REGISTRY에서 파생)
        self._keyword_to_aspect = {}
        for aspect, keywords in ASPECT_KEYWORDS.items():
            for kw in keywords:
                self._keyword_to_aspect[kw] = aspect

    def analyze(self, review: str) -> list[dict]:
        """
        단일 리뷰 ABSA 분석

        Args:
            review: 리뷰 텍스트

        Returns:
            [{'aspect': '직원친절', 'opinion': '직원이 친절했어요',
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

    # 부정 접두사 로직은 sentiment_core._is_negation_prefixed_only() 사용

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

                # 부정 접두사 복합어 안에서만 등장하면 제외 (불친절 → 친절 오탐 방지)
                if _is_negation_prefixed_only(keyword, text_lower):
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

    # 부정어+긍정어 패턴: 긍정 표현이 부정되는 경우
    NEGATED_POSITIVE_PATTERNS = [
        re.compile(r"친절.{0,6}(?:지\s*않|지\s*못|하지\s*않)"),
        re.compile(r"깨끗.{0,6}(?:지\s*않|하지\s*않)"),
        re.compile(r"좋.{0,6}(?:지\s*않|지\s*못)"),
        re.compile(r"편.{0,6}(?:지\s*않|하지\s*않)"),
    ]

    def _determine_sentiment(self, text: str) -> tuple[str, float]:
        """감정 판단 (patterns.py 사용)"""

        # 0. 이중부정 최우선 체크 (불편하지 않다 → 긍정)
        if check_double_negation(text):
            return "positive", 0.95

        # 1. 부정어+긍정어 패턴 체크 (친절하지 않, 깨끗하지 않 등)
        for pattern in self.NEGATED_POSITIVE_PATTERNS:
            if pattern.search(text):
                return "negative", 0.85

        # 2. 명확한 부정 패턴 선체크 (불친절, 비싸 등 접두사형 부정)
        strong_neg_count = sum(1 for p in STRONG_NEGATIVE_KEYWORDS if p in text)

        # POSITIVE_REGEX 결과 캐시 (중복 호출 방지)
        _pos_words_cache = POSITIVE_REGEX.findall(text)

        # 명확한 부정이 있는 경우 → 부정 우선
        if strong_neg_count > 0:
            positive_matches = len(_pos_words_cache)
            if strong_neg_count >= positive_matches:
                confidence = min(0.95, 0.7 + 0.05 * strong_neg_count)
                return "negative", confidence

        # 3. 긍정 예외 체크 (오탐 방지 — "틀림없", "거침없" 등)
        if POSITIVE_EXCEPTION_REGEX.search(text):
            if strong_neg_count == 0:
                return "positive", 0.8

        # 3. 긍정+부정 체크 (친절+없다 = 부정)
        for pattern, sentiment in self.POSITIVE_NEGATION_PATTERNS:
            if pattern.search(text):
                return sentiment, 0.9

        # 4. SHORT REVIEW BOOST: 30자 미만 + 명확한 긍정어 → 높은 confidence
        if len(text) < 30:
            # 짧은 리뷰에서 부정 패턴 먼저 체크
            if NEGATIVE_REGEX.search(text):
                return "negative", 0.7

            clear_positive_words = [
                "최고",
                "최곱",
                "좋았",
                "좋아요",
                "좋네요",
                "좋습니다",
                "만족",
                "완벽",
                "훌륭",
                "추천",
                "감사",
                "고마워",
            ]
            for word in clear_positive_words:
                if word in text:
                    return "positive", 0.85

            # "잘 이용" 패턴 (짧은 리뷰에서 흔한 긍정 표현)
            if "잘" in text and any(v in text for v in ["이용", "사용", "됐", "됐어"]):
                return "positive", 0.8

        # 5. 일반 패턴 매칭
        positive_matches, negative_matches = count_sentiment_matches(text)

        # "없" 특수 처리 - 부정 키워드 + 없 → 긍정 전환 (이중부정)
        if "없" in text:
            for nk, pattern in self._NEG_ABSENCE_PATTERNS:
                if nk in text and pattern.search(text):
                    positive_matches += 1
                    negative_matches = max(0, negative_matches - 1)

        # 6. 결과 판단
        if positive_matches > negative_matches:
            base_confidence = 0.6 + 0.1 * (positive_matches - negative_matches)

            # REPETITION DETECTION: Check for repeated positive words
            positive_words = _pos_words_cache
            unique_words = set(positive_words)
            repetition_ratio = len(positive_words) / max(len(unique_words), 1)

            # Boost confidence for repetition (e.g., "최고최고최고")
            if repetition_ratio >= 1.5:
                base_confidence = min(0.95, base_confidence + 0.15)

            return "positive", min(0.95, base_confidence)
        elif negative_matches > positive_matches:
            confidence = min(0.95, 0.6 + 0.1 * (negative_matches - positive_matches))
            return "negative", confidence
        elif positive_matches > 0:
            # At least 1 positive pattern → confidence 0.65 (not 0.5)
            return "positive", 0.65
        elif negative_matches > 0:
            return "negative", 0.5
        else:
            return self._infer_sentiment_from_context(text)

    def determine_text_sentiment(self, text: str) -> tuple[str, float]:
        """텍스트 전체의 감정 분석 (public API)"""
        if not text or not text.strip():
            return "neutral", 0.0
        return self._determine_sentiment(text)

    def _infer_sentiment_from_context(self, text: str) -> tuple[str, float]:
        """패턴 매칭 실패 시 맥락 기반 감정 추론 (Enhanced)"""

        # 1. STRONG positives (각각 confidence 값 부여)
        strong_positive = {
            "최고": 0.85,
            "최곱": 0.85,
            "완벽": 0.85,
            "훌륭": 0.85,
            "만족": 0.75,
            "추천": 0.75,
            "강추": 0.85,
            "감사": 0.7,
            "고마": 0.7,
        }

        # 2. MEDIUM positives
        medium_positive = {
            "좋았": 0.7,
            "좋아요": 0.7,
            "좋습": 0.7,
            "좋은": 0.65,
            "좋": 0.6,
            "잘": 0.6,
            "편": 0.55,
            "깔끔": 0.65,
            "빠": 0.55,
            "넓": 0.55,
        }

        # 3. WEAK positives (emoticons, particles)
        weak_positive = ["요", "네요", "습니다", "^^", "~", "!", "ㅎㅎ", "ㅋㅋ"]

        # Calculate max confidence
        max_confidence = 0.0
        strong_count = 0

        for word, conf in strong_positive.items():
            if word in text:
                count = text.count(word)
                strong_count += count
                # Repetition bonus: +0.05 per extra occurrence
                max_confidence = max(max_confidence, conf + (count - 1) * 0.05)

        medium_count = 0
        if max_confidence == 0:  # No strong positives
            for word, conf in medium_positive.items():
                if word in text:
                    medium_count += 1
                    max_confidence = max(max_confidence, conf)

        weak_count = sum(1 for w in weak_positive if w in text)

        # Negative check
        weak_negative = ["...", ";;;", "ㅜ", "ㅠ", "근데", "다만", "불"]
        neg_count = sum(1 for w in weak_negative if w in text)

        # Decision
        if strong_count > 0 and neg_count == 0:
            # Strong positive found → HIGH confidence
            return "positive", min(0.9, max_confidence)
        elif medium_count > 0 and neg_count == 0:
            # Medium positive found → MEDIUM confidence
            return "positive", min(0.8, max_confidence + medium_count * 0.03)
        elif (strong_count + medium_count) > 0 and (strong_count + medium_count + weak_count) > neg_count:
            # At least one meaningful positive (strong or medium) needed
            return "positive", min(0.7, 0.5 + 0.05 * (strong_count + medium_count))
        elif neg_count > 0:
            return "negative", 0.5
        else:
            return "neutral", 0.4  # Default neutral (no clear signal)

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
                '직원친절': {'positive': ['친절'], 'negative': [], 'neutral': []},
                '청결': {'positive': [], 'negative': ['더러운'], 'neutral': []}
            }
        """
        from collections import defaultdict

        result = defaultdict(lambda: {"positive": [], "negative": [], "neutral": []})

        # 절별 ABSA 분석
        clauses = self._chunker.chunk(review)
        for clause in clauses:
            clause_results = self._analyze_clause(clause)
            for ao in clause_results:
                aspect = ao.aspect
                sentiment = ao.sentiment
                for kw in ao.keywords:
                    if kw not in result[aspect][sentiment]:
                        result[aspect][sentiment].append(kw)

        # 양보/반전 구문 체크: 전체 리뷰에서 "걱정했는데 괜찮" 같은 패턴 감지
        has_concession = bool(CONCESSION_REGEX.search(review))

        # 동일 카테고리 positive+negative 충돌 해소
        resolved = {}
        for tag, sentiments in result.items():
            if not any(sentiments.values()):
                continue
            pos_kws = sentiments.get("positive", [])
            neg_kws = sentiments.get("negative", [])
            neu_kws = sentiments.get("neutral", [])

            if pos_kws and neg_kws:
                # 반전 구문이면서 부정 근거가 약할 때만 긍정 우선
                if has_concession and len(neg_kws) <= 1:
                    resolved[tag] = {"positive": pos_kws, "negative": [], "neutral": neu_kws}
                elif len(pos_kws) >= len(neg_kws):
                    resolved[tag] = {"positive": pos_kws, "negative": [], "neutral": neu_kws}
                else:
                    resolved[tag] = {"positive": [], "negative": neg_kws, "neutral": neu_kws}
            else:
                resolved[tag] = sentiments

        return {
            tag: sentiments
            for tag, sentiments in resolved.items()
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
