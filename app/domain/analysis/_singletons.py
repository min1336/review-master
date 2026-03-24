"""NLP 모델 싱글턴 팩토리 — 프로세스당 1개 인스턴스

ONNX 임베딩 모델(~200MB), Kiwi 형태소 분석기(~50MB) 등
무거운 NLP 리소스를 모듈 레벨 전역 변수로 관리하여
UnifiedPipeline 인스턴스가 여러 번 생성되더라도 모델을 재로드하지 않는다.

asyncio.to_thread() 환경에서 동시 호출 시 중복 초기화를 방지하기 위해
threading.RLock(재진입 가능)을 사용한 Double-Checked Locking 패턴을 적용한다.
RLock을 쓰는 이유: get_sentiment_analyzer()가 _lock 보유 중 get_hybrid_classifier()를
호출하므로, 비재진입 Lock이면 데드락이 발생한다.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_kiwi_usage_lock = threading.Lock()
_kiwi = None
_hybrid_classifier = None
_sentiment_analyzer = None


def get_kiwi():
    """Kiwi 형태소 분석기 싱글턴 반환 (스레드 안전)"""
    global _kiwi
    if _kiwi is None:
        with _lock:
            if _kiwi is None:
                try:
                    from kiwipiepy import Kiwi

                    _kiwi = Kiwi()
                    logger.info("Kiwi 형태소 분석기 초기화 완료 (싱글턴)")
                except ImportError:
                    logger.warning("Kiwi 미설치 - 정규식 폴백 사용")
    return _kiwi


def kiwi_tokenize(text: str) -> list[Any]:
    """스레드 안전한 Kiwi tokenize 래퍼.

    Kiwi 내부 C++ 상태는 멀티스레드 동시 접근이 안전하지 않으므로
    _kiwi_usage_lock으로 직렬화한다. asyncio.to_thread()로 호출해도 안전.
    """
    kiwi = get_kiwi()
    if kiwi is None:
        return []
    with _kiwi_usage_lock:
        return kiwi.tokenize(text)


def get_hybrid_classifier():
    """HybridClassifier 싱글턴 반환 (스레드 안전)"""
    global _hybrid_classifier
    if _hybrid_classifier is None:
        with _lock:
            if _hybrid_classifier is None:
                from domain.analysis import HybridClassifier

                _hybrid_classifier = HybridClassifier(lazy_load=True)
                logger.info("HybridClassifier 초기화 완료 (싱글턴)")
    return _hybrid_classifier


def get_sentiment_analyzer():
    """UnifiedSentimentAnalyzer 싱글턴 반환 (스레드 안전)"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        with _lock:
            if _sentiment_analyzer is None:
                from domain.analysis import UnifiedSentimentAnalyzer

                _sentiment_analyzer = UnifiedSentimentAnalyzer(
                    lazy_load=True,
                    hybrid_classifier=get_hybrid_classifier(),
                )
                logger.info("UnifiedSentimentAnalyzer 초기화 완료 (싱글턴)")
    return _sentiment_analyzer
