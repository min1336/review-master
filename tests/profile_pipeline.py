"""
파이프라인 CPU/메모리 프로파일링 스크립트

NLP 컴포넌트별 CPU 시간 + 메모리 사용량을 측정합니다.
DB 연결 없이 순수 연산 부분만 프로파일링합니다.

Usage:
    cd app && python -m tests.profile_pipeline
    또는
    python tests/profile_pipeline.py
"""

from __future__ import annotations

import gc
import os
import resource
import sys
import time
import tracemalloc

# app/ 디렉토리를 PYTHONPATH에 추가
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


# ─────────────────────────────────────────────────
# 샘플 리뷰 데이터 (실제 렌트카 리뷰 패턴)
# ─────────────────────────────────────────────────
SAMPLE_REVIEWS = [
    "직원분이 정말 친절하게 안내해 주셨고, 차량 상태도 깨끗했습니다. 다음에도 이용하고 싶어요!",
    "차량에 흠집이 있었고 실내가 더러웠어요. 직원은 불친절했습니다.",
    "가격 대비 만족스러운 서비스였습니다. 차량도 깨끗하고 직원도 친절했어요.",
    "배차가 너무 늦었어요. 30분이나 기다렸습니다. 차량 상태는 괜찮았지만 대기 시간이 너무 길었어요.",
    "최고입니다! 차량 컨디션도 좋고 직원분도 너무 친절하시고 가격도 합리적이에요. 강추합니다!",
    "차량이 낡아서 에어컨이 잘 안 됐어요. 여름에 에어컨 없으면 정말 힘들어요.",
    "좋아요",
    "네이비게이션이 구형이라 불편했고, 블루투스 연결도 안 됐습니다.",
    "예약 과정이 간편하고 반납도 빨랐어요. 전반적으로 만족합니다.",
    "차량은 좋았는데 보험 설명이 부족했어요. 좀 더 자세한 안내가 필요합니다.",
    "사고 처리가 빠르고 보상도 잘 해주셨어요. 위기 대응이 좋습니다.",
    "연료가 거의 없는 상태로 인수했는데, 반납 시엔 가득 채워야 한다니 불합리합니다.",
    "픽업 서비스가 정말 편리했어요. 공항에서 바로 탈 수 있어서 좋았습니다.",
    "차에서 담배 냄새가 심하게 났어요. 금연 차량이라고 해놓고 냄새가 나다니 실망입니다.",
    "가성비 최고! 이 가격에 이 정도면 완벽합니다. 다음에도 꼭 이용할게요.",
    "직원이 친절하지 않아서 기분이 좋지 않았어요.",
    "불편한 점 없이 잘 이용했습니다. 감사합니다.",
    "차가 깨끗하고 새 차 같았어요. 냄새도 없고 시트도 편안했습니다.",
    "예약했는데 차량이 없다고 해서 한참 기다렸어요. 예약 시스템 개선이 필요합니다.",
    "전반적으로 괜찮았지만 반납 절차가 복잡했어요. 좀 더 간소화하면 좋겠습니다.",
]

# 50건, 100건 규모 테스트용 확장
REVIEWS_50 = SAMPLE_REVIEWS * 3  # 60건 (20 * 3) → 50건 슬라이스
REVIEWS_100 = SAMPLE_REVIEWS * 5  # 100건


# ─────────────────────────────────────────────────
# 측정 유틸리티
# ─────────────────────────────────────────────────
def get_rss_mb() -> float:
    """현재 프로세스의 RSS(물리 메모리) MB 반환"""
    # Linux: ru_maxrss는 KB 단위
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def profile_section(name: str, func, *args, **kwargs):
    """
    함수 실행 중 CPU 시간 + 메모리 변화량 측정

    Returns:
        (result, cpu_seconds, mem_peak_mb, mem_current_mb)
    """
    gc.collect()
    tracemalloc.start()
    rss_before = get_rss_mb()
    cpu_start = time.process_time()
    wall_start = time.monotonic()

    result = func(*args, **kwargs)

    cpu_elapsed = time.process_time() - cpu_start
    wall_elapsed = time.monotonic() - wall_start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after = get_rss_mb()

    print(f"  [{name}]")
    print(f"    CPU 시간:     {cpu_elapsed:.4f}s")
    print(f"    Wall 시간:    {wall_elapsed:.4f}s")
    print(f"    Python 메모리: current={current / 1024 / 1024:.2f}MB, peak={peak / 1024 / 1024:.2f}MB")
    print(f"    RSS 변화:     {rss_before:.1f}MB → {rss_after:.1f}MB (Δ{rss_after - rss_before:+.1f}MB)")
    print()

    return result, cpu_elapsed, peak / 1024 / 1024


# ─────────────────────────────────────────────────
# 1. 모델 초기화 프로파일링
# ─────────────────────────────────────────────────
def profile_initialization():
    """NLP 모델 초기화 비용 측정"""
    print("=" * 60)
    print("1. NLP 모델 초기화")
    print("=" * 60)

    # Kiwi 초기화
    def init_kiwi():
        from kiwipiepy import Kiwi
        return Kiwi()

    kiwi, cpu, mem = profile_section("Kiwi 형태소 분석기", init_kiwi)

    # ABSA 초기화
    def init_absa():
        from domain.analysis.absa import RuleBasedABSA
        return RuleBasedABSA()

    absa, cpu, mem = profile_section("RuleBasedABSA", init_absa)

    # HybridClassifier 초기화 (임베딩 모델 포함)
    def init_classifier():
        from domain.analysis.hybrid_classifier import HybridClassifier
        hc = HybridClassifier(lazy_load=True)
        hc._ensure_initialized()  # 임베딩 모델 강제 로딩
        return hc

    classifier, cpu, mem = profile_section("HybridClassifier + 임베딩 모델", init_classifier)

    # UnifiedSentimentAnalyzer 초기화
    def init_sentiment():
        from domain.analysis.sentiment_utils import UnifiedSentimentAnalyzer
        return UnifiedSentimentAnalyzer(
            lazy_load=True,
            hybrid_classifier=classifier,
        )

    analyzer, cpu, mem = profile_section("UnifiedSentimentAnalyzer", init_sentiment)

    return kiwi, absa, classifier, analyzer


# ─────────────────────────────────────────────────
# 2. 개별 컴포넌트 프로파일링
# ─────────────────────────────────────────────────
def profile_components(kiwi, absa, classifier, analyzer):
    """개별 NLP 컴포넌트별 처리 비용"""
    print("=" * 60)
    print("2. 개별 컴포넌트 — 단건 처리 (20건 평균)")
    print("=" * 60)

    total_kiwi_cpu = 0
    total_absa_cpu = 0
    total_classify_cpu = 0
    total_sentiment_cpu = 0

    for review in SAMPLE_REVIEWS:
        # Kiwi 토큰화
        _, cpu, _ = profile_section(
            f"Kiwi ({review[:15]}...)" if len(review) > 15 else f"Kiwi ({review})",
            kiwi.tokenize, review
        )
        total_kiwi_cpu += cpu

        # ABSA 분석
        _, cpu, _ = profile_section(
            f"ABSA ({review[:15]}...)" if len(review) > 15 else f"ABSA ({review})",
            absa.analyze, review
        )
        total_absa_cpu += cpu

        # HybridClassifier
        keywords = [t.form for t in kiwi.tokenize(review) if t.tag in ("NNG", "NNP", "VA", "VV")]
        _, cpu, _ = profile_section(
            f"Classify ({review[:15]}...)" if len(review) > 15 else f"Classify ({review})",
            classifier.classify_review, review, keywords
        )
        total_classify_cpu += cpu

        # Sentiment 분석
        _, cpu, _ = profile_section(
            f"Sentiment ({review[:15]}...)" if len(review) > 15 else f"Sentiment ({review})",
            analyzer.analyze, review, keywords
        )
        total_sentiment_cpu += cpu

    n = len(SAMPLE_REVIEWS)
    print("-" * 60)
    print(f"  단건 평균 CPU 시간 (20건 기준):")
    print(f"    Kiwi 토큰화:       {total_kiwi_cpu / n * 1000:.2f}ms")
    print(f"    ABSA 분석:         {total_absa_cpu / n * 1000:.2f}ms")
    print(f"    HybridClassifier:  {total_classify_cpu / n * 1000:.2f}ms")
    print(f"    Sentiment 분석:    {total_sentiment_cpu / n * 1000:.2f}ms")
    print(f"    합계 (1건):        {(total_kiwi_cpu + total_absa_cpu + total_classify_cpu + total_sentiment_cpu) / n * 1000:.2f}ms")
    print()


# ─────────────────────────────────────────────────
# 3. 배치 프로파일링
# ─────────────────────────────────────────────────
def profile_batch(kiwi, absa, classifier, analyzer):
    """배치 처리 시 CPU/메모리 — 20, 50, 100건"""
    print("=" * 60)
    print("3. 배치 처리 (NLP only, DB 제외)")
    print("=" * 60)

    from core.stopwords import LexiconConfig

    def process_batch_nlp(reviews: list[str]):
        """DB 없이 NLP 파이프라인만 실행"""
        results = []
        for review in reviews:
            # 1. Kiwi 토큰화
            tokens = kiwi.tokenize(review)
            keywords = [
                t.form for t in tokens
                if t.tag in ("NNG", "NNP", "VA", "VV", "XR")
                and len(t.form) >= 2
                and t.form not in LexiconConfig.STOP_WORDS
            ]

            # 2. HybridClassifier (ABSA + 임베딩)
            tag_result = classifier.classify_review(review, keywords)

            # 3. 감정 분석
            sentiment_result = analyzer.analyze(review, keywords)

            results.append({
                "keywords": keywords,
                "tags": tag_result,
                "sentiment": sentiment_result.sentiment,
                "confidence": sentiment_result.confidence,
            })
        return results

    for label, batch in [("20건", SAMPLE_REVIEWS), ("50건", REVIEWS_50[:50]), ("100건", REVIEWS_100)]:
        profile_section(f"배치 NLP — {label}", process_batch_nlp, batch)


# ─────────────────────────────────────────────────
# 4. 전체 RSS 스냅샷
# ─────────────────────────────────────────────────
def profile_memory_snapshot():
    """현재 프로세스 전체 메모리 사용량"""
    print("=" * 60)
    print("4. 전체 프로세스 메모리")
    print("=" * 60)

    rss = get_rss_mb()
    print(f"  현재 RSS: {rss:.1f}MB")
    print(f"  Peak RSS: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.1f}MB")
    print()


# ─────────────────────────────────────────────────
# 5. tracemalloc Top 10
# ─────────────────────────────────────────────────
def profile_memory_top10(kiwi, classifier, analyzer):
    """100건 처리 시 메모리 할당 Top 10"""
    print("=" * 60)
    print("5. 메모리 할당 Top 10 (100건 배치)")
    print("=" * 60)

    from core.stopwords import LexiconConfig

    gc.collect()
    tracemalloc.start()

    for review in REVIEWS_100:
        tokens = kiwi.tokenize(review)
        keywords = [
            t.form for t in tokens
            if t.tag in ("NNG", "NNP", "VA", "VV", "XR")
            and len(t.form) >= 2
            and t.form not in LexiconConfig.STOP_WORDS
        ]
        classifier.classify_review(review, keywords)
        analyzer.analyze(review, keywords)

    snapshot = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot.statistics("lineno")
    print("  Top 10 메모리 할당:")
    for i, stat in enumerate(stats[:10], 1):
        print(f"    {i:2d}. {stat}")
    print()


# ─────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────
def main():
    lightweight = os.getenv("LIGHTWEIGHT_MODE", "false").lower() in ("true", "1", "yes")
    mode_label = "경량 모드 (임베딩 OFF)" if lightweight else "전체 모드 (임베딩 ON)"

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     Review Summary AI — 파이프라인 CPU/메모리 프로파일링     ║")
    print(f"║     모드: {mode_label:^46}║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    rss_start = get_rss_mb()
    print(f"  시작 RSS: {rss_start:.1f}MB")
    print()

    # 1. 초기화
    kiwi, absa, classifier, analyzer = profile_initialization()

    rss_after_init = get_rss_mb()
    print(f"  → 모델 로딩 후 RSS: {rss_after_init:.1f}MB (Δ{rss_after_init - rss_start:+.1f}MB)")
    print()

    # 2. 개별 컴포넌트 (상세 출력은 너무 길어지므로 요약만)
    profile_components_summary(kiwi, absa, classifier, analyzer)

    # 3. 배치 프로파일링
    profile_batch(kiwi, absa, classifier, analyzer)

    # 4. 전체 메모리
    profile_memory_snapshot()

    # 5. Top 10
    profile_memory_top10(kiwi, classifier, analyzer)

    print("프로파일링 완료!")


def profile_components_summary(kiwi, absa, classifier, analyzer):
    """개별 컴포넌트 요약 (상세 출력 생략)"""
    print("=" * 60)
    print("2. 개별 컴포넌트 — 단건 CPU 시간 평균 (20건)")
    print("=" * 60)

    from core.stopwords import LexiconConfig

    totals = {"kiwi": 0, "absa": 0, "classify": 0, "sentiment": 0}
    peaks = {"kiwi": 0, "absa": 0, "classify": 0, "sentiment": 0}

    for review in SAMPLE_REVIEWS:
        # Kiwi
        gc.collect()
        cpu_s = time.process_time()
        tokens = kiwi.tokenize(review)
        totals["kiwi"] += time.process_time() - cpu_s

        keywords = [
            t.form for t in tokens
            if t.tag in ("NNG", "NNP", "VA", "VV", "XR")
            and len(t.form) >= 2
            and t.form not in LexiconConfig.STOP_WORDS
        ]

        # ABSA
        cpu_s = time.process_time()
        absa.analyze(review)
        totals["absa"] += time.process_time() - cpu_s

        # HybridClassifier
        cpu_s = time.process_time()
        classifier.classify_review(review, keywords)
        totals["classify"] += time.process_time() - cpu_s

        # Sentiment
        cpu_s = time.process_time()
        analyzer.analyze(review, keywords)
        totals["sentiment"] += time.process_time() - cpu_s

    n = len(SAMPLE_REVIEWS)
    total_per_review = sum(totals.values()) / n

    print(f"  {'컴포넌트':<25} {'평균(ms)':>10} {'비율':>8}")
    print(f"  {'─' * 45}")
    for name, label in [("kiwi", "Kiwi 토큰화"), ("absa", "ABSA 분석"),
                         ("classify", "HybridClassifier"), ("sentiment", "Sentiment 분석")]:
        avg_ms = totals[name] / n * 1000
        pct = totals[name] / sum(totals.values()) * 100 if sum(totals.values()) > 0 else 0
        print(f"  {label:<25} {avg_ms:>8.2f}ms {pct:>6.1f}%")

    print(f"  {'─' * 45}")
    print(f"  {'합계 (1건당)':<25} {total_per_review * 1000:>8.2f}ms {'100.0':>6}%")
    print(f"  {'초당 처리량':<25} {1.0 / total_per_review if total_per_review > 0 else 0:>8.0f}건/s")
    print()


if __name__ == "__main__":
    main()
