"""
감정 판단 공유 프리미티브

hybrid_classifier.py와 absa.py에서 공통으로 사용하는
저수준 감정 판단 함수 모음.

- detect_keyword_sentiment: 단일 키워드 감정 판단 (regex)
- detect_keyword_sentiment_with_context: 키워드 + 문맥 감정 판단
- check_double_negation: 이중부정 검사
- count_sentiment_matches: 긍정/부정 패턴 카운트
"""

from __future__ import annotations

import re

from core.constants import CONTEXT_WINDOW_SIZE

from .patterns import (
    DOUBLE_NEGATION_REGEX,
    NEGATIVE_REGEX,
    POSITIVE_EXCEPTION_REGEX,
    POSITIVE_REGEX,
)

# 부정 표현 패턴 (문맥 윈도우 내에서 사용)
_NEGATION_PATTERN = re.compile(
    r"지\s*않|지\s*못|못\s*하|(?<![가-힣])안\s*하|안\s*좋|너무\s*안"
)


def check_double_negation(text: str) -> bool:
    """이중부정 여부 판단 (불편하지 않다 -> 긍정)"""
    return bool(DOUBLE_NEGATION_REGEX.search(text))


def count_sentiment_matches(text: str) -> tuple[int, int]:
    """텍스트 내 긍정/부정 패턴 매칭 수 반환

    Returns:
        (positive_count, negative_count)
    """
    positive_count = len(POSITIVE_REGEX.findall(text))
    negative_count = len(NEGATIVE_REGEX.findall(text))
    return positive_count, negative_count


def detect_keyword_sentiment(keyword: str) -> str:
    """키워드의 감정 판단 (규칙 기반 regex)

    Args:
        keyword: 단일 키워드

    Returns:
        "positive", "negative", 또는 "neutral"
    """
    if not keyword:
        return "neutral"

    if POSITIVE_EXCEPTION_REGEX.search(keyword):
        return "positive"

    if NEGATIVE_REGEX.search(keyword):
        return "negative"

    if POSITIVE_REGEX.search(keyword):
        return "positive"

    return "neutral"


def detect_keyword_sentiment_with_context(
    keyword: str, context: str, window_size: int = CONTEXT_WINDOW_SIZE
) -> str:
    """문맥을 고려한 키워드 감정 판단

    Args:
        keyword: 단일 키워드
        context: 원본 리뷰 텍스트
        window_size: 키워드 주변 문맥 윈도우 크기 (글자)

    Returns:
        "positive", "negative", 또는 "neutral"
    """
    base_sentiment = detect_keyword_sentiment(keyword)

    if not context or keyword not in context:
        return base_sentiment

    pos = context.find(keyword)
    if pos == -1:
        return base_sentiment

    start = max(0, pos - window_size)
    end = min(len(context), pos + len(keyword) + window_size)
    window = context[start:end]

    # 이중부정 -> 긍정
    if check_double_negation(window):
        return "positive"

    # 긍정 예외
    has_positive_exception = POSITIVE_EXCEPTION_REGEX.search(window)
    if has_positive_exception and base_sentiment in ["positive", "neutral"]:
        return "positive"

    # 부정 표현 패턴
    has_negation = _NEGATION_PATTERN.search(window)
    if base_sentiment == "positive" and has_negation and not has_positive_exception:
        return "negative"

    if base_sentiment != "neutral":
        return base_sentiment

    if NEGATIVE_REGEX.search(window):
        return "negative"

    if POSITIVE_REGEX.search(window):
        return "positive"

    return "neutral"
