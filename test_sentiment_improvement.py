#!/usr/bin/env python3
"""
감정 분류 개선 검증 테스트

문제 리뷰들이 올바르게 긍정으로 분류되는지 확인
"""

import sys
from pathlib import Path

# 프로젝트 경로 설정 (main.py와 동일)
APP_DIR = Path(__file__).parent / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent))

from app.domain.analysis.absa import RuleBasedABSA


def test_misclassified_reviews():
    """중립으로 잘못 분류되던 리뷰들 테스트"""

    absa = RuleBasedABSA()

    test_cases = [
        ("잘 이용 했습니다", "positive", 0.75),
        ("친절도최고. 가격도최고 차상태도최고.반납도쉬움.^^매번여기만이용^^", "positive", 0.9),
        ("차량 상태 좋고 저렴하게 잘 이용했어요", "positive", 0.75),
        ("제주겨울이라 전기차 사륜구동이 필요했는데 저렴하게 빌릴수있었어요. 전화문의시 응대도 빠르시구 차도 깨끗했습니다!! 다음에 또 이용할거같아요", "positive", 0.7),
        ("잘 이용햇습니다", "positive", 0.75),
        ("전체적으로 좋았습니다", "positive", 0.85),
        # 추가 테스트
        ("최고입니다", "positive", 0.85),
        ("만족합니다", "positive", 0.75),
        ("좋았어요", "positive", 0.7),
        ("완벽했어요", "positive", 0.85),
    ]

    print("=" * 80)
    print("감정 분류 개선 검증 테스트")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for text, expected_sentiment, min_confidence in test_cases:
        sentiment, confidence = absa._determine_sentiment(text)

        # 결과 검증
        sentiment_ok = sentiment == expected_sentiment
        confidence_ok = confidence >= min_confidence

        status = "✅ PASS" if (sentiment_ok and confidence_ok) else "❌ FAIL"

        print(f"{status} | {text[:40]:40s}")
        print(f"       Expected: {expected_sentiment:8s} (conf ≥ {min_confidence:.2f})")
        print(f"       Got:      {sentiment:8s} (conf = {confidence:.2f})")

        if not sentiment_ok:
            print(f"       ⚠️  Wrong sentiment: expected {expected_sentiment}, got {sentiment}")
        if not confidence_ok:
            print(f"       ⚠️  Low confidence: expected ≥{min_confidence:.2f}, got {confidence:.2f}")

        if sentiment_ok and confidence_ok:
            passed += 1
        else:
            failed += 1

        print()

    print("=" * 80)
    print(f"결과: {passed}/{len(test_cases)} 통과 ({passed/len(test_cases)*100:.1f}%)")
    if failed > 0:
        print(f"⚠️  {failed}개 실패")
    else:
        print("✅ 모든 테스트 통과!")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = test_misclassified_reviews()
    exit(0 if success else 1)
